"""正式installer/Cookie/記録権で作ったnative原本を登録readで読む。"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest
from psycopg import sql

from pitchlog.repositories.recorded_snapshot_operations import (
    RECORDED_EVENT_COLUMNS,
    RECORDED_PLAY_ROW_COLUMNS,
    RECORDED_SLOT_COLUMNS,
)

from .sync_writer_binding_support import binding_app
from .test_first_ball_projection_atomic import (
    _foreign_snapshot,
)
from .test_first_ball_projection_atomic import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_projection_atomic import (
    projection_env as projection_env,
)
from .test_first_ball_projection_atomic import (
    test_owned_registered_projection_atomic as _create_native,
)
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db

_TABLES = (
    ("operation_events", RECORDED_EVENT_COLUMNS, "generation,d1,d2,id"),
    ("event_slots", RECORDED_SLOT_COLUMNS, "generation,d1"),
    ("play_rows", RECORDED_PLAY_ROW_COLUMNS, "play_number,id"),
)


def _snapshot(env: Any) -> dict[str, list[list[str | None]]]:
    """adminは独立期待値を読むだけ。native原本の投入には使わない。"""
    result = {}
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        for table, columns, order in _TABLES:
            rows = conn.execute(
                sql.SQL(
                    "SELECT {} FROM public.{} WHERE tenant_id=%s AND "
                    "game_id=%s ORDER BY {} LIMIT 2"
                ).format(
                    sql.SQL(",").join(map(sql.Identifier, columns)),
                    sql.Identifier(table),
                    sql.SQL(",").join(
                        sql.SQL("{} ASC NULLS LAST").format(sql.Identifier(key))
                        for key in order.split(",")
                    ),
                ),
                (env.ctx.tenant, env.ctx.game),
            ).fetchall()
            result[table] = [
                [None if v is None else str(v) for v in row] for row in rows
            ]
    return result


def test_registered_reads_actual_cookie_native_all_columns_and_isolation(
    projection_env: Any,
) -> None:
    """実保存3集合の全21/5/41列、別tenant/別game非曝露と不変を確認する。"""
    env = projection_env
    _create_native(env, "accepted")
    expected = _snapshot(env)
    assert [len(expected[name][0]) for name, _, _ in _TABLES] == [21, 5, 41]
    foreign_before = _foreign_snapshot(env)
    body = f"""
from pitchlog.repositories.recorded_snapshot_operations import (
 RecordedEventRowsReadToken,RecordedEventSlotsReadToken,RecordedPlayRowsReadToken)
types=(RecordedEventRowsReadToken,RecordedEventSlotsReadToken,RecordedPlayRowsReadToken)
result={{}}
with tenant_transaction_scope(context) as tx:
 for kind,name in zip(types,('operation_events','event_slots','play_rows'),strict=True):
  rows=tx.run(kind(UUID('{env.ctx.game}'))).rows
  assert type(rows) is tuple and all(type(row) is tuple for row in rows)
  result[name]=[[None if v is None else str(v) for v in row] for row in rows]
  assert tx.run(kind(UUID('{env.foreign_game}'))).rows==()
  assert tx.run(kind(uuid4())).rows==()
print(json.dumps(result))
"""
    assert binding_app(env.owner, body) == expected
    assert _foreign_snapshot(env) == foreign_before
    assert _snapshot(env) == expected
    # 第二/第三の履歴も正式tokenで作る。lifecycle/世代を絞って隠さず上限2。
    body = f"""
from pitchlog.sync.tokens import (
 IdempotencyLedgerInsertToken,EventSlotInsertToken,OperationEventInsertToken)
from pitchlog.repositories.recorded_snapshot_operations import (
 RecordedEventRowsReadToken,RecordedEventSlotsReadToken,RecordedPlayRowsReadToken)
with tenant_transaction_scope(context) as tx:
 for d1 in (2,3):
  d5=uuid4()
  token=IdempotencyLedgerInsertToken(d5,'accepted','wire-v1:'+'a'*64,'{{}}')
  assert tx.run(token).rows==((1,),)
  token=EventSlotInsertToken(UUID('{env.ctx.game}'),{env.ctx.generation},d1)
  assert tx.run(token).rows==((1,),)
  token=OperationEventInsertToken(uuid4(),UUID('{env.ctx.game}'),d5,
   'play_input','{{}}',{env.ctx.generation},d1,d1,'{{}}')
  assert tx.run(token).rows==((1,),)
with tenant_transaction_scope(context) as tx:
 result={{}}
 types=(RecordedEventRowsReadToken,RecordedEventSlotsReadToken,RecordedPlayRowsReadToken)
 for kind,name in zip(types,
  ('operation_events','event_slots','play_rows'),strict=True):
  rows=tx.run(kind(UUID('{env.ctx.game}'))).rows
  result[name]=[[None if v is None else str(v) for v in row] for row in rows]
print(json.dumps(result))
"""
    actual = binding_app(env.owner, body)
    assert actual == _snapshot(env)
    assert [len(actual[name]) for name, _, _ in _TABLES] == [2, 2, 1]
    assert _foreign_snapshot(env) == foreign_before


def test_registered_read_fake_and_expired_handles_issue_zero_sql(
    projection_env: Any,
) -> None:
    """実SQL観測はscope準備後から。未知/派生型と失効handleをSQL前に拒否する。"""
    body = """
from sqlalchemy import event
from pitchlog.repositories.transaction import _TRANSACTION_RUNTIMES
from pitchlog.repositories.base import _TenantOperationError
from pitchlog.repositories.recorded_snapshot_operations import (
 RecordedEventRowsReadToken,RecordedEventSlotsReadToken,RecordedPlayRowsReadToken)
types=(RecordedEventRowsReadToken,RecordedEventSlotsReadToken,RecordedPlayRowsReadToken)
statements=[]
with tenant_transaction_scope(context) as tx:
 session,_=_TRANSACTION_RUNTIMES[tx._state_key]
 engine=session.get_bind()
 def observe(*args): statements.append(True)
 event.listen(engine,'before_cursor_execute',observe)
 try:
  for kind in types:
   for fake in (type('UnknownSameCap',(),{'capability_id':kind._capability}),
    type('DerivedRecorded',(kind,),{})):
    try: tx.run(object.__new__(fake))
    except _TenantOperationError: pass
    else: raise AssertionError('未知型成功')
  assert statements==[]
 finally: event.remove(engine,'before_cursor_execute',observe)
event.listen(engine,'before_cursor_execute',observe)
try:
 for kind in types:
  try: tx.run(kind(uuid4()))
  except RuntimeError: pass
  else: raise AssertionError('失効handle成功')
 assert statements==[]
finally: event.remove(engine,'before_cursor_execute',observe)
print(json.dumps(dict(sql=0,unknown_rejected=True,expired_rejected=True)))
"""
    assert binding_app(projection_env.owner, body) == {
        "sql": 0,
        "unknown_rejected": True,
        "expired_rejected": True,
    }
