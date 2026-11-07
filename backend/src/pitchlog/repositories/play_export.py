"""毎球CSVの同一snapshot読取をtenant/gameへ限定する。

このmoduleは保存値の抽出だけを行い、T1/T2の再計算・全件集計・座標変換を持たない。
未供給の列は ``PlayExportMissingSupply`` で明示し、NULL/0/現在名簿で補わない。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import islice
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from pitchlog.db.game_state.models import (
    Game,
    GameLineup,
    ParticipationInterval,
    PlayRow,
    PlayRunner,
)
from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.db.tenant_isolation.models import (
    AdminVocabulary,
    Player,
    TeamRecord,
    TenantVocabulary,
)
from pitchlog.exports.play_rows import PlayExportSupplyError
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.play_export_source_codec import (
    PlayExportSourceError,
    SourceIdentity,
    SourceVersion,
)
from pitchlog.repositories.play_export_source_operations import ReadPlayExportSources
from pitchlog.repositories.play_export_spool import DiskRows, current_row_store
from pitchlog.repositories.transaction import (
    _TRANSACTION_RUNTIMES,
    _require_play_export_scope,
    _TenantTransaction,
)

_PAGE = 500


class PlayExportNotFound(Exception):
    """可視な試合が無い/別tenant。"""


class PlayExportMissingSupply(PlayExportSupplyError):
    """88列/サイドカーの提供元が不足している。"""

    def __init__(self, columns: tuple[str, ...], reason: str):
        """不足列と固定理由だけを保持する。"""
        self.columns = columns
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class PlayExportBundle:
    """同一RR snapshotから読んだ保存値。完成値への写像は別層。"""

    game: dict[str, Any]
    plays: Sequence[dict[str, Any]]
    runners: Sequence[dict[str, Any]]
    events: Sequence[dict[str, Any]]
    lineups: Sequence[dict[str, Any]]
    participations: Sequence[dict[str, Any]]
    players: Sequence[dict[str, Any]]
    teams: Sequence[dict[str, Any]]
    tenant_vocabularies: Sequence[dict[str, Any]]
    admin_vocabularies: Sequence[dict[str, Any]]
    snapshots: Sequence[dict[str, Any]]
    runner_snapshots: Sequence[dict[str, Any]]
    snapshot_available: bool
    audit_plays: Sequence[dict[str, Any]] | None = None
    source_version: SourceVersion | None = None
    source_identities: Sequence[dict[str, Any]] | None = None


def _session(handle: _TenantTransaction) -> tuple[Session, UUID]:
    """実scopeのhandleだけから同Sessionとtenantを取り出す。"""
    _require_play_export_scope(handle)
    key = handle._state_key
    if key is None or key not in _TRANSACTION_RUNTIMES:
        raise TenantBindingError("毎球CSV scopeが失効しています")
    return _TRANSACTION_RUNTIMES[key][0], handle._bound_tenant_id


def _new_rows():
    """要求が退避scopeを持つ場合だけディスク集合を作る。"""
    store = current_row_store()
    return [] if store is None else store.rows()


def _new_keys():
    """参照キーも同じ有限退避へ束縛する。"""
    store = current_row_store()
    return set() if store is None else store.keys()


def _freeze_rows(rows):
    """ディスク集合を全量tupleへ戻さない。"""
    return rows if isinstance(rows, DiskRows) else tuple(rows)


def _chunks(values):
    """入力を一度だけ走査し最大500keyずつ読む。"""
    iterator = iter(values)
    while chunk := tuple(islice(iterator, _PAGE)):
        yield chunk


def _rows(session: Session, statement: Any) -> Sequence[dict[str, Any]]:
    """server-side有限cursorから私有ディスクへ一行ずつ写す。"""
    result = _new_rows()
    with session.execute(
        statement.execution_options(stream_results=True, yield_per=_PAGE)
    ) as cursor:
        result.extend(dict(row) for row in cursor.mappings())
    return _freeze_rows(result)


def _plays_for_source_page(
    session: Session, tenant: UUID, game_id: UUID, page: tuple[SourceIdentity, ...]
):
    """唯一Sが渡した最大500の物理原本を同じtenant/game/source版へ結ぶ。"""
    if not page or len(page) > _PAGE:
        raise PlayExportMissingSupply(
            ("有効source",), "current-source-page-unavailable"
        )
    table, event = PlayRow.__table__, OperationEvent.__table__
    identifiers = tuple(source.play_row_id for source in page)
    if len(set(identifiers)) != len(identifiers):
        raise PlayExportMissingSupply(("有効source",), "duplicate-current-source")
    rows = _rows(
        session,
        select(*table.c)
        .select_from(
            table.join(
                event,
                and_(
                    event.c.tenant_id == table.c.tenant_id,
                    event.c.game_id == table.c.game_id,
                    event.c.id == table.c.source_event_id,
                    event.c.ledger_kind == "accepted",
                    event.c.is_tombstone.is_(False),
                    event.c.replaced_at.is_(None),
                    event.c.retired_at.is_(None),
                ),
            )
        )
        .where(
            table.c.tenant_id == tenant,
            table.c.game_id == game_id,
            table.c.id.in_(identifiers),
        ),
    )
    indexed = (
        rows.index_by("id")
        if isinstance(rows, DiskRows)
        else {row["id"]: row for row in rows}
    )
    if len(rows) != len(page) or len(indexed) != len(page):
        raise PlayExportMissingSupply(("有効source",), "current-source-row-unavailable")
    for source in page:
        row = indexed[source.play_row_id]
        if (
            row["source_event_id"] != source.source_event_id
            or type(row["version"]) is not int
            or row["version"] != source.play_row_version
        ):
            raise PlayExportMissingSupply(
                ("有効source",), "current-source-row-mismatch"
            )
        yield row


def _read_current_plays(handle, session: Session, tenant: UUID, game_id: UUID):
    """Raw hidden走査をせず、真正同RR readerを全page消費して件数を閉じる。"""
    plays, identities = _new_rows(), _new_rows()
    reader = ReadPlayExportSources(handle, game_id)
    try:
        for page in reader.pages(page_size=_PAGE):
            if len(plays) + len(page) > 100000:
                raise PlayExportMissingSupply(("プレイ行",), "current-source-limit")
            plays.extend(_plays_for_source_page(session, tenant, game_id, page))
            for source in page:
                identities.extend(
                    (
                        {
                            "recording_generation": source.recording_generation,
                            "d1": source.d1,
                            "d2": source.d2,
                            "source_event_id": source.source_event_id,
                            "play_row_id": source.play_row_id,
                            "slot_version": source.slot_version,
                            "play_row_version": source.play_row_version,
                            "base_event_id": source.base_event_id,
                            "source_fingerprint": source.source_fingerprint,
                        },
                    )
                )
    except PlayExportSourceError as error:
        raise PlayExportMissingSupply(
            ("有効source",), "current-source-unavailable"
        ) from error
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == "22023":
            raise PlayExportMissingSupply(
                ("有効source",), "current-source-unavailable"
            ) from error
        raise
    if len(plays) != reader.version.source_count or len(identities) != len(plays):
        raise PlayExportMissingSupply(("有効source",), "current-source-count-mismatch")
    return _freeze_rows(plays), _freeze_rows(identities), reader.version


def _read_runners(
    session: Session, tenant: UUID, play_ids: Iterable[UUID]
) -> Sequence[dict[str, Any]]:
    """ページ内play_idを一括結合し、N+1を作らない。"""
    table = PlayRunner.__table__
    result = _new_rows()
    for chunk in _chunks(play_ids):
        if not chunk:
            continue
        statement = (
            select(*table.c)
            .where(table.c.tenant_id == tenant, table.c.play_id.in_(chunk))
            .order_by(table.c.play_id.asc(), table.c.base.asc(), table.c.id.asc())
        )
        result.extend(_rows(session, statement))
    return _freeze_rows(result)


def _read_events(session: Session, tenant: UUID, game_id: UUID):
    """全受理原本を500行keysetで読む。NULL位置は独立id系列とする。"""
    table = OperationEvent.__table__
    result = _new_rows()
    for null_position in (False, True):
        cursor = None
        while True:
            statement = select(*table.c).where(
                table.c.tenant_id == tenant,
                table.c.game_id == game_id,
                table.c.ledger_kind == "accepted",
                table.c.d2.is_(None) if null_position else table.c.d2.is_not(None),
            )
            if null_position:
                statement = statement.order_by(table.c.id.asc())
                if cursor is not None:
                    statement = statement.where(table.c.id > cursor[1])
            else:
                statement = statement.order_by(table.c.d2.asc(), table.c.id.asc())
                if cursor is not None:
                    statement = statement.where(
                        or_(
                            table.c.d2 > cursor[0],
                            and_(table.c.d2 == cursor[0], table.c.id > cursor[1]),
                        )
                    )
            rows = _rows(session, statement.limit(_PAGE))
            result.extend(rows)
            if len(rows) < _PAGE:
                break
            cursor = (rows[-1]["d2"], rows[-1]["id"])
    return _freeze_rows(result)


def require_visible_export_game(handle: _TenantTransaction, game_id: UUID) -> None:
    """送出直前の新しいtenant snapshotで可視性だけを再照合する。"""
    session, tenant = _session(handle)
    table = Game.__table__
    visible = session.execute(
        select(table.c.id).where(
            table.c.tenant_id == tenant,
            table.c.id == game_id,
            table.c.hidden_at.is_(None),
            table.c.trashed_at.is_(None),
            table.c.status.not_in(("hidden", "trashed")),
        )
    ).scalar_one_or_none()
    if visible is None:
        raise PlayExportNotFound("対象試合を取得できません")


def _read_references(
    session: Session,
    tenant: UUID,
    player_ids: Iterable[UUID],
    team_ids: Iterable[UUID],
    tenant_vocab_keys: Iterable[str],
    admin_vocab_keys: Iterable[str],
):
    """当該試合が参照する表示行だけを同snapshotで読む。"""
    players = Player.__table__
    teams = TeamRecord.__table__
    tenant_vocab = TenantVocabulary.__table__
    admin_vocab = AdminVocabulary.__table__
    player_rows = _new_rows()
    team_rows = _new_rows()
    tenant_rows = _new_rows()
    admin_rows = _new_rows()
    for chunk in _chunks(player_ids):
        if chunk:
            player_rows.extend(
                _rows(
                    session,
                    select(*players.c)
                    .where(players.c.tenant_id == tenant, players.c.id.in_(chunk))
                    .order_by(players.c.id),
                )
            )
    for chunk in _chunks(team_ids):
        if chunk:
            team_rows.extend(
                _rows(
                    session,
                    select(*teams.c)
                    .where(teams.c.tenant_id == tenant, teams.c.id.in_(chunk))
                    .order_by(teams.c.id),
                )
            )
    for chunk in _chunks(tenant_vocab_keys):
        if chunk:
            tenant_rows.extend(
                _rows(
                    session,
                    select(*tenant_vocab.c)
                    .where(
                        tenant_vocab.c.tenant_id == tenant,
                        tenant_vocab.c.key.in_(chunk),
                    )
                    .order_by(tenant_vocab.c.key),
                )
            )
    for chunk in _chunks(admin_vocab_keys):
        if chunk:
            admin_rows.extend(
                _rows(
                    session,
                    select(*admin_vocab.c)
                    .where(admin_vocab.c.key.in_(chunk))
                    .order_by(admin_vocab.c.key),
                )
            )
    return (
        _freeze_rows(player_rows),
        _freeze_rows(team_rows),
        _freeze_rows(tenant_rows),
        _freeze_rows(admin_rows),
    )


def _optional_snapshot_tables(session: Session) -> tuple[str | None, str | None]:
    """候補snapshot表の有無を実DBで確認し、未適用を黙って空にしない。"""
    rows = session.execute(
        text(
            "SELECT to_regclass('public.play_export_snapshots'),"
            "to_regclass('public.play_export_runner_snapshots')"
        )
    ).one()
    snapshot = rows[0]
    runner = rows[1]
    return (
        None if snapshot is None else str(snapshot),
        None if runner is None else str(runner),
    )


def read_play_export(handle: _TenantTransaction, game_id: UUID) -> PlayExportBundle:
    """試合・プレイ・イベント・出場・参照・候補snapshotを同一RRで読む。

    Args:
        handle: ``play_export_read_scope`` が発行した実handle。
        game_id: 出力対象の試合。

    Returns:
        同一snapshotの保存値。完成値への写像・T1再計算は行わない。

    Raises:
        PlayExportNotFound: 可視な試合が無い/別tenant。
        TenantBindingError: scope/handleが真正でない。
    """
    session, tenant = _session(handle)
    game_table = Game.__table__
    game_rows = _rows(
        session,
        select(*game_table.c).where(
            game_table.c.tenant_id == tenant,
            game_table.c.id == game_id,
            game_table.c.hidden_at.is_(None),
            game_table.c.trashed_at.is_(None),
            game_table.c.status.not_in(("hidden", "trashed")),
        ),
    )
    if len(game_rows) != 1:
        raise PlayExportNotFound("対象試合を取得できません")
    game = game_rows[0]

    plays, source_identities, source_version = _read_current_plays(
        handle, session, tenant, game_id
    )
    # 取消・訂正前の物理行も同じRRから保持し、旧snapshotの原本を検証する。
    audit_plays = _rows(
        session,
        select(*PlayRow.__table__.c)
        .where(
            PlayRow.__table__.c.tenant_id == tenant,
            PlayRow.__table__.c.game_id == game_id,
        )
        .order_by(PlayRow.__table__.c.play_number, PlayRow.__table__.c.id),
    )
    play_ids = (row["id"] for row in plays)
    runners = _read_runners(session, tenant, play_ids)
    events = _read_events(session, tenant, game_id)

    lineup_table = GameLineup.__table__
    lineups = _rows(
        session,
        select(*lineup_table.c)
        .where(lineup_table.c.tenant_id == tenant, lineup_table.c.game_id == game_id)
        .order_by(lineup_table.c.id),
    )
    participation_table = ParticipationInterval.__table__
    participations = _rows(
        session,
        select(*participation_table.c)
        .where(
            participation_table.c.tenant_id == tenant,
            participation_table.c.game_id == game_id,
        )
        .order_by(
            participation_table.c.valid_from_d2.asc(),
            participation_table.c.slot_kind.asc(),
            participation_table.c.slot.asc(),
            participation_table.c.id.asc(),
        ),
    )

    player_ids = _new_keys()
    for row in plays:
        for key in ("batter_id", "pitcher_id", "catcher_id", "resolved_fielder_id"):
            if row.get(key) is not None:
                player_ids.add(row[key])
    for row in runners:
        for key in ("runner_id", "responsible_pitcher_id"):
            if row.get(key) is not None:
                player_ids.add(row[key])
    for row in lineups:
        for entry in row.get("entries_with_uniform_number_snapshot") or []:
            if type(entry) is dict and type(entry.get("player_id")) is str:
                try:
                    player_ids.add(UUID(entry["player_id"]))
                except ValueError:
                    continue
    for row in participations:
        if row.get("player_id") is not None:
            player_ids.add(row["player_id"])

    team_ids = {game["away_team_record_id"], game["home_team_record_id"]}
    tenant_vocab_keys = _new_keys()
    admin_vocab_keys = _new_keys()
    for row in plays:
        for key in (
            "strategy_key",
            "strategy_detail_key",
            "strategy_result_key",
            "pitch_type_key",
        ):
            if row.get(key) is not None:
                tenant_vocab_keys.add(row[key])
        for key in (
            "batting_result_key",
            "secondary_batting_result_key",
            "batted_ball_type",
            "batted_ball_strength",
        ):
            if row.get(key) is not None:
                admin_vocab_keys.add(row[key])
    players, teams, tenant_vocab_rows, admin_vocab_rows = _read_references(
        session,
        tenant,
        player_ids,
        team_ids,
        tenant_vocab_keys,
        admin_vocab_keys,
    )

    snapshot_name, runner_snapshot_name = _optional_snapshot_tables(session)
    snapshot_rows: Sequence[dict[str, Any]] = ()
    runner_snapshot_rows: Sequence[dict[str, Any]] = ()
    if snapshot_name is not None:
        snapshot_rows = _rows(
            session,
            text(
                f"SELECT * FROM {snapshot_name} WHERE tenant_id=:tenant_id "
                "AND game_id=:game_id ORDER BY captured_at,play_row_id"
            ).bindparams(tenant_id=tenant, game_id=game_id),
        )
    if runner_snapshot_name is not None:
        runner_snapshot_rows = _rows(
            session,
            text(
                f"SELECT * FROM {runner_snapshot_name} WHERE tenant_id=:tenant_id "
                "AND game_id=:game_id ORDER BY play_id,base"
            ).bindparams(tenant_id=tenant, game_id=game_id),
        )
    return PlayExportBundle(
        game=game,
        plays=_freeze_rows(plays),
        runners=runners,
        events=events,
        lineups=lineups,
        participations=participations,
        players=players,
        teams=teams,
        tenant_vocabularies=tenant_vocab_rows,
        admin_vocabularies=admin_vocab_rows,
        snapshots=snapshot_rows,
        runner_snapshots=runner_snapshot_rows,
        snapshot_available=snapshot_name is not None,
        audit_plays=audit_plays,
        source_version=source_version,
        source_identities=source_identities,
    )
