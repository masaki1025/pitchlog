"""唯一Sのidentityと物理行の閉結合を実SQLiteで検証する（PG認可ではない）。"""

from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import JSON, Column, MetaData, Table, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from test_play_export_effective_versions import _recorded

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.exports.play_export_csv import missing_supply_columns, snapshot_id_for
from pitchlog.repositories import play_export as repository
from pitchlog.repositories.play_export_source_codec import SourceIdentity, SourceVersion
from pitchlog.repositories.play_export_spool import DiskRows, ExportRowStore

TENANT, GAME = UUID(int=1), UUID(int=2)


def _table(model, metadata):
    """同じORM列の型を使い、SQLiteでJSONBだけをJSONへ写す。"""
    return Table(
        model.__table__.name,
        metadata,
        *[
            Column(
                column.name, JSON() if isinstance(column.type, JSONB) else column.type
            )
            for column in model.__table__.columns
        ],
    )


def _source(index):
    """S発行の代用ではない、閉結合入力の単位値を作る。"""
    return SourceIdentity(
        1,
        index + 1,
        index * 1000 + 1,
        UUID(int=1000 + index),
        UUID(int=2000 + index),
        1,
        1,
        UUID(int=1000 + index),
        "a" * 64,
    )


def _world(count):
    """全物理行をSQLへ入れ、SELECTの結果をfixtureで返さない。"""
    metadata = MetaData()
    plays, events = _table(PlayRow, metadata), _table(OperationEvent, metadata)
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    values = [_source(n) for n in range(count)]
    with engine.begin() as connection:
        connection.execute(
            events.insert(),
            [
                {
                    "id": s.source_event_id,
                    "tenant_id": TENANT,
                    "game_id": GAME,
                    "ledger_kind": "accepted",
                    "is_tombstone": False,
                    "event_kind": "play_input",
                    "generation": 1,
                    "d1": s.d1,
                    "d2": s.d2,
                }
                for s in values
            ],
        )
        connection.execute(
            plays.insert(),
            [
                {
                    "id": s.play_row_id,
                    "tenant_id": TENANT,
                    "game_id": GAME,
                    "source_event_id": s.source_event_id,
                    "play_number": s.d1,
                    "version": s.play_row_version,
                }
                for s in values
            ],
        )
    return engine, plays, events, values


@pytest.mark.parametrize("count", [1, 500, 501])
@pytest.mark.parametrize("spool", [False, True])
def test_current_source_pages_are_read_once_without_raw_row_fallback(
    monkeypatch, count, spool
):
    """合成readerのpage境界だけを置き、各原本は実SQLで一括取得する。"""
    engine, _plays, _events, values = _world(count)
    version = SourceVersion(UUID(int=9), 1, "b" * 64, count, "current_open", "1:3:")

    class Reader:
        def __init__(self, handle, game):
            self.version = version

        def pages(self, *, page_size):
            assert page_size == 500
            for start in range(0, count, page_size):
                yield tuple(values[start : start + page_size])

    monkeypatch.setattr(repository, "ReadPlayExportSources", Reader)
    queries = []

    def observe(_conn, _cursor, statement, *_rest):
        if "FROM play_rows JOIN operation_events" in statement:
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        with Session(engine) as session, ExportRowStore() as store:
            if spool:
                with store.capture():
                    actual, identities, bound = repository._read_current_plays(
                        object(), session, TENANT, GAME
                    )
                assert isinstance(actual, DiskRows) and isinstance(identities, DiskRows)
            else:
                actual, identities, bound = repository._read_current_plays(
                    object(), session, TENANT, GAME
                )
            assert [row["id"] for row in actual] == [s.play_row_id for s in values]
            assert len(identities) == count and bound == version
            assert len(queries) == (count + 499) // 500
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "bad", ["tenant", "game", "event", "version", "ledger", "missing"]
)
def test_wrong_physical_scope_or_source_is_not_exported(bad):
    """別scope/別event/版/退避原本を正しいsourceの代わりへ使わない。"""
    engine, plays, events, values = _world(1)
    try:
        with engine.begin() as connection:
            if bad == "tenant":
                connection.execute(plays.update().values(tenant_id=UUID(int=99)))
            if bad == "game":
                connection.execute(plays.update().values(game_id=UUID(int=99)))
            if bad == "event":
                connection.execute(plays.update().values(source_event_id=UUID(int=99)))
            if bad == "version":
                connection.execute(plays.update().values(version=2))
            if bad == "ledger":
                connection.execute(events.update().values(ledger_kind="evacuated"))
            if bad == "missing":
                values[0] = replace(values[0], play_row_id=UUID(int=999))
        with (
            Session(engine) as session,
            pytest.raises(repository.PlayExportMissingSupply),
        ):
            list(
                repository._plays_for_source_page(session, TENANT, GAME, tuple(values))
            )
    finally:
        engine.dispose()


def test_nonhidden_old_p3_row_does_not_choose_itself():
    """P3旧行の非hiddenを有効判定にせず、指定されたeffective行だけ読む。"""
    engine, plays, events, values = _world(2)
    target = replace(
        values[1], d1=1, slot_version=2, base_event_id=values[0].source_event_id
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                events.update()
                .where(events.c.id == target.source_event_id)
                .values(event_kind="play_change")
            )
        with Session(engine) as session:
            rows = list(
                repository._plays_for_source_page(session, TENANT, GAME, (target,))
            )
        assert [row["id"] for row in rows] == [target.play_row_id]
        assert rows[0]["source_event_id"] == target.source_event_id
    finally:
        engine.dispose()


def test_version_identity_changes_manifest_but_snapshot_transaction_does_not():
    """終了版や有効source変更を束縛し、無関係なRR開始番号は版へ混ぜない。"""
    base = _recorded()
    physical = base.plays[0]
    identity = {
        "play_row_id": physical["id"],
        "source_event_id": physical["source_event_id"],
        "play_row_version": physical["version"],
    }
    version = SourceVersion(UUID(int=9), 1, "a" * 64, 1, "current_open", "1:3:")
    scoped = replace(base, source_version=version, source_identities=(identity,))
    assert missing_supply_columns(scoped) == ()
    assert snapshot_id_for(scoped) != snapshot_id_for(
        replace(scoped, source_version=replace(version, revision=2))
    )
    assert snapshot_id_for(scoped) == snapshot_id_for(
        replace(scoped, source_version=replace(version, transaction_id="2:4:"))
    )
    assert missing_supply_columns(replace(scoped, source_identities=())) == tuple(
        range(88)
    )
    assert missing_supply_columns(replace(scoped, source_version=None)) == tuple(
        range(88)
    )
