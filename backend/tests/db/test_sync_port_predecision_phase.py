"""実owned PG/brokerの同writer上で判定Portの業務DMLを遮断する。

実Port登録/credential transport/HTTP成功を証明しない。既fixtureの実cookie・
BindingControl・製品scopeを使い、SQL呼出を観測してからouter rollbackする。
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from db_fixtures import _dsn_names

from .sync_writer_binding_support import (
    binding_app,
    binding_broker,
    owned_binding_database,
)
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture
def initial_scope_database(monkeypatch) -> Iterator[object]:
    """共有DSNを参照せずfixture所有資源だけを認可基線付きで作る。"""
    with owned_binding_database(monkeypatch) as owner:
        admin_name, role_name = _dsn_names()
        monkeypatch.setenv(admin_name, owner.authority.database.primary_admin)
        monkeypatch.setenv(role_name, owner.authority.database.endpoints.primary_dsn)
        yield owner


def test_owned_actual_bound_phase_blocks_port_dml_then_allows_core_read(
    initial_scope_database,
):
    """5phaseのDML/未知read/savepointはSQL0、同handleの核readは実DBへ届く。"""
    owner = initial_scope_database
    issued = owner.actor("grant=issue(); print(json.dumps(receipt(grant)))")
    token, subject = uuid4(), uuid4()
    with psycopg.connect(owner.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.system_settings(key,value) VALUES "
            "('auth.token_ttl_seconds','3600') ON CONFLICT(key) "
            "DO UPDATE SET value=EXCLUDED.value"
        )
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(tenant_id,id) VALUES (%s,%s)",
            (owner.tenant_id, subject),
        )
        admin.execute(
            "INSERT INTO public.tenant_credentials(auth_subject_id,password_hash,"
            "generation) VALUES (%s,'public-unused-login-vector',1)",
            (subject,),
        )
        admin.execute(
            "INSERT INTO public.tenant_tokens(tenant_id,id,auth_subject_id,"
            "credential_generation,expires_at,last_used_at) VALUES "
            "(%s,%s,%s,1,clock_timestamp()+interval '1 hour',clock_timestamp())",
            (owner.tenant_id, token, subject),
        )
    body = f"""
from sqlalchemy import event
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.transaction import (
 _TRANSACTION_RUNTIMES,_port_predecision_phase)
from pitchlog.sync.ports import _issue_port_writer
from pitchlog.sync.tokens import GameReadToken,RecordingPrefixUpdateToken
class PlannedRollback(Exception): pass
report={{}}
try:
 with tenant_transaction_scope(context) as tx:
  authority=AuthorityBinding(UUID(int=7101),UUID(int=7102),UUID(int=7103))
  attempt=AttemptBinding(authority,context.tenant_id,UUID('{owner.device_id}'),
   UUID('{owner.game_id}'),'fixture-first-ball',{issued["generation"]},
   uuid4(),1,'public-phase-rq',1)
  phase=EventPhaseBinding(attempt,uuid4(),1,1,uuid4(),'public-phase-ev')
  bound=control.bind_writer(tx,context,phase,cookie=cookie)
  session,_=_TRANSACTION_RUNTIMES[tx._state_key]
  statements=[]
  event.listen(session.get_bind(),'before_cursor_execute',
   lambda *args: statements.append('sql'))
  writer=_issue_port_writer(tx.run)
  assert writer._execute.__self__ is tx
  try:
   for kind in ('rg1-precheck','rg1-commit','device','rights','content'):
    with _port_predecision_phase(tx,kind):
     baseline=len(statements)
     for action in (
      lambda: writer.run(RecordingPrefixUpdateToken(attempt.game_id,1,1,1)),
      lambda: tx.run_in_savepoint(GameReadToken(attempt.game_id))):
      try: action()
      except TenantBindingError: pass
      else: raise AssertionError('判定中書込又はsavepointを受理')
     assert len(statements)==baseline
    report[kind]=True
   before=len(statements)
   rows=writer.run(GameReadToken(attempt.game_id)).rows
   assert len(rows)==1 and len(statements)>before
   report['same_handle_core_read']=True
   report['writer_same_bound_method']=writer._execute.__self__ is tx
  finally: writer._close()
  raise PlannedRollback()
except PlannedRollback: pass
print(json.dumps(report))
"""
    with binding_broker(owner, token):
        result = binding_app(owner, body)
    assert result == {
        "rg1-precheck": True,
        "rg1-commit": True,
        "device": True,
        "rights": True,
        "content": True,
        "same_handle_core_read": True,
        "writer_same_bound_method": True,
    }
