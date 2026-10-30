"""実開始応答V12・実loan・実writerで初球P2記録権Portを検査する。"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from db_fixtures import _dsn_names

from . import test_initial_game_start as start_tests
from . import test_initial_recording_right_scope as initial_tests
from .sync_writer_binding_support import (
    binding_app,
    binding_broker,
    owned_binding_database,
)

pytestmark = pytest.mark.requires_db
admin_connection = initial_tests.admin_connection
tested_role_connection = initial_tests.tested_role_connection
product_node_binary = start_tests.product_node_binary
start_database = start_tests.start_database
_OWNED_VOLUMES: dict[object, set[str]] = {}


def _capture_owned_mounts(owner) -> None:
    """fixtureが所有する実containerのmountだけを生存中に記録する。"""
    database = owner.authority.database
    volumes = _OWNED_VOLUMES[owner]
    for name in (
        database.primary,
        database.standby,
        database.business,
        *owner.authority._names,
    ):
        observed = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Mounts}}", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if observed.returncode:
            continue
        volumes.update(
            row["Name"]
            for row in json.loads(observed.stdout)
            if row["Type"] == "volume"
        )


@pytest.fixture
def initial_scope_database(monkeypatch) -> Iterator[object]:
    """正規installerの自己所有3PGを既開始fixtureへ貸与する。"""
    volumes: set[str] = set()
    try:
        with owned_binding_database(monkeypatch) as owner:
            _OWNED_VOLUMES[owner] = volumes
            admin_name, role_name = _dsn_names()
            monkeypatch.setenv(admin_name, owner.authority.database.primary_admin)
            monkeypatch.setenv(
                role_name, owner.authority.database.endpoints.primary_dsn
            )
            _capture_owned_mounts(owner)
            try:
                yield owner
            finally:
                _OWNED_VOLUMES.pop(owner, None)
    finally:
        for name in sorted(volumes):
            exists = subprocess.run(
                ["docker", "volume", "inspect", name], capture_output=True, check=False
            )
            if exists.returncode:
                continue
            users = subprocess.check_output(
                ["docker", "ps", "-aq", "--filter", "volume=" + name], text=True
            ).strip()
            assert not users, "自己所有volumeが使用中"
            subprocess.run(
                ["docker", "volume", "rm", name], capture_output=True, check=True
            )


def test_owned_real_started_v12_actual_loan_and_right_function(start_database):
    """生V12をappから取り出さず、実発行→正常/旧proof→全rollbackを確認する。"""
    db = start_database
    token, subject = uuid4(), uuid4()
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.system_settings(key,value) "
            "VALUES ('auth.token_ttl_seconds','3600') ON CONFLICT(key) "
            "DO UPDATE SET value=EXCLUDED.value"
        )
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(tenant_id,id) VALUES (%s,%s)",
            (db.tenant_id, subject),
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
            (db.tenant_id, token, subject),
        )
    body = f"""
import base64
sys.path.insert(0,'/fixture/backend/tests')
stage=0
def trace_failure(kind,value,tb):
 print(json.dumps({{'fixture_failure':kind.__name__,
  'frames':[('u09_stage',stage),
            *[(f.name,f.lineno) for f in traceback.extract_tb(tb)]]}}))
sys.excepthook=trace_failure
from pydantic import SecretStr
from sqlalchemy import event
from test_initial_game_start_components import _body
from pitchlog.api.schemas.game_start import GameStartRequest
from pitchlog.repositories.game_start import InitialStartPayload,_entries
from pitchlog.recording_rights.initial_grant_broker import (
 _InitialBrokerClient,_BrokerIdentity,_EnrollDeviceCommand,_StartInitialGameCommand,
 _broker_generation)
from pitchlog.repositories.initial_recording_right import _credential_digest
from pitchlog.repositories import transaction
from pitchlog.repositories.transaction import _port_predecision_phase
from pitchlog.sync.ports import _issue_port_writer,require_registered_port
from pitchlog.sync.first_ball_recording_rights import FirstBallRecordingRightsPort
from pitchlog.sync.tokens import PortBindCurrentDeviceToken
import pitchlog.sync.port_guard
identity=_BrokerIdentity(context.tenant_id,uuid4(),SecretStr(cookie))
client=_InitialBrokerClient()
stage=1
pair_reply=client.call(_EnrollDeviceCommand(identity))
assert pair_reply.status=='enrolled' and pair_reply.value is not None
pair=pair_reply.value
raw=_body(10)
raw.update(device_id=str(pair.device_id),device_credential=pair.device_credential.get_secret_value(),
           start_request_id='{db.start_request_id}')
request=GameStartRequest.model_validate(raw)
command=_StartInitialGameCommand(identity,UUID('{db.game_id}'),request.start_request_id,
 request.device_id,request.device_credential,
 InitialStartPayload(_entries(request.away),_entries(request.home)))
stage=2
first=client.call(command)
assert first.status=='started' and first.value is not None
proof=first.value.recording_right_proof.get_secret_value()
d4=first.value.d4
generation=_broker_generation(d4,context.tenant_id,UUID('{db.game_id}'))
port=FirstBallRecordingRightsPort();require_registered_port(port)
class PlannedRollback(Exception): pass
checks=[]
def probe(presented, expected):
 global stage
 stage=3
 try:
  with tenant_transaction_scope(context) as tx:
   authority=AuthorityBinding(UUID(int=7101),UUID(int=7102),UUID(int=7103))
   attempt=AttemptBinding(authority,context.tenant_id,pair.device_id,UUID('{db.game_id}'),
    d4,generation,uuid4(),1,'public-u09-request-fp',1)
   phase=EventPhaseBinding(attempt,uuid4(),1,1,uuid4(),'public-u09-event-fp')
   stage=4
   control.bind_writer(tx,context,phase,cookie=cookie)
   writer=_issue_port_writer(tx.run)
   seen=[]
   session,_=transaction._TRANSACTION_RUNTIMES[tx._state_key]
   def observe(conn,cursor,statement,parameters,execution,many):
    seen.append(statement)
   event.listen(session.get_bind(),'before_cursor_execute',observe)
   try:
    stage=5
    with _port_predecision_phase(tx,'rg1-precheck'):
     assert port.read_rg1_before_d5(writer) is True
    stage=6
    with _port_predecision_phase(tx,'device'):
     result=writer.run(PortBindCurrentDeviceToken(
      _credential_digest(pair.device_credential.get_secret_value())))
     assert result.rows==((True,),)
    before=sum('check_current_right(' in sql for sql in seen)
    stage=7
    with _port_predecision_phase(tx,'rights'):
     assert port.holds_recording_right(
      str(attempt.game_id),d4,presented,writer) is expected
    after=sum('check_current_right(' in sql for sql in seen)
    assert after-before==(0 if presented is None else 1)
    stage=8
    with _port_predecision_phase(tx,'rg1-commit'):
     assert port.check_rg1_before_commit(writer) is True
    checks.append(True)
   finally:
    event.remove(session.get_bind(),'before_cursor_execute',observe)
    writer._close()
   stage=9
   raise PlannedRollback()
 except PlannedRollback: pass
probe(proof,True)
raw_proof=base64.urlsafe_b64decode(proof+'=')
wrong=base64.urlsafe_b64encode(bytes([raw_proof[0]^1])+raw_proof[1:]).decode().rstrip('=')
probe(wrong,False)
probe(None,False)
print(json.dumps({{'real_start_v12':True,'actual_loan_and_writer':True,
 'right_sql_once':True,'bad_proof_sql_zero':True,'right_and_rg1_checks':checks}}))
"""
    with db.broker_worker(token), binding_broker(db, token):
        _capture_owned_mounts(db)
        result = binding_app(db, body)
    assert result == {
        "real_start_v12": True,
        "actual_loan_and_writer": True,
        "right_sql_once": True,
        "bad_proof_sql_zero": True,
        "right_and_rg1_checks": [True, True, True],
    }
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.first_ball_write_admissions"
        ).fetchone() == (0,)
        assert admin.execute(
            "SELECT count(*) FROM public.operation_events"
        ).fetchone() == (0,)
        assert admin.execute("SELECT count(*) FROM public.play_rows").fetchone() == (0,)
