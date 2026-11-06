"""イベント抽出の500境界とNULL位置を実SQLで検査する（PG認可試験ではない）。"""

from uuid import UUID

import pytest
from sqlalchemy import JSON, Column, MetaData, Table, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.repositories.play_export import _read_events


@pytest.mark.parametrize("count", [500, 501, 2001])
def test_event_keyset_has_no_gap_and_keeps_null_d2(count: int) -> None:
    """旧2000件上限を越え、同位置/NULL/退役原本を重複欠落なしで読む。"""
    # 実ORMの同じ列/同じSELECTをSQLiteでも実行し、fixtureの返し値でページを模倣しない。
    table = Table(
        "operation_events",
        MetaData(),
        *[
            Column(c.name, JSON() if isinstance(c.type, JSONB) else c.type)
            for c in OperationEvent.__table__.columns
        ],
    )
    engine = create_engine("sqlite://")
    table.metadata.create_all(engine)
    tenant, game = UUID(int=1), UUID(int=2)
    rows = [
        {
            "id": UUID(int=100 + i),
            "tenant_id": tenant,
            "game_id": game,
            "d2": i // 2 if i < count else None,
            "ledger_kind": "accepted",
            "is_tombstone": False,
            "migration_unverified": False,
            "payload": {},
            "state_diff": None,
        }
        for i in range(count + 3)
    ]
    # 拒否/別tenantを同じtableへ含め、同じSQLの絞り込みも確認する。
    rows += [
        dict(rows[0], id=UUID(int=count + 200), ledger_kind="evacuated"),
        dict(rows[0], id=UUID(int=count + 201), tenant_id=UUID(int=9)),
    ]
    try:
        with engine.begin() as connection:
            connection.execute(table.insert(), rows)
        with Session(engine) as session:
            actual = _read_events(session, tenant, game)
        assert [row["id"] for row in actual] == [row["id"] for row in rows[:-2]]
        assert len({row["id"] for row in actual}) == count + 3
        assert [row["d2"] for row in actual[-3:]] == [None, None, None]
    finally:
        engine.dispose()
