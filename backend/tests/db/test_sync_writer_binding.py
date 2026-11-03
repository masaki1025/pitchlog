"""実製品のwriter SQL境界。外部lease/broker縦断の成立とは区別する。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from psycopg import sql

from .sync_writer_binding_support import (
    ACTOR,
    APP,
    _literal,
    assert_statement,
    owned_binding_database,
    prepare_binding_database,
)
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture
def initial_scope_database(monkeypatch):
    """既autouseの実identity検査を保ったowned3PGを供給する。"""
    from db_fixtures import _dsn_names

    with owned_binding_database(monkeypatch) as owner:
        admin_name, role_name = _dsn_names()
        monkeypatch.setenv(admin_name, owner.authority.database.primary_admin)
        monkeypatch.setenv(role_name, owner.authority.database.endpoints.primary_dsn)
        yield owner


@pytest.fixture
def binding_database(initial_scope_database):
    """正式供給のない表/関数をfixture専用DDLで補わない。"""
    return prepare_binding_database(initial_scope_database)


def _publish(db, writer, *, ttl=20):
    """Actual writer自己観測とcontrol専用LOGINから限定SQLを検査する。"""
    tenant, game = db.owner.tenant_id, db.owner.game_id
    attempt, phase, device = (uuid4() for _ in range(3))
    writer.query("BEGIN")
    writer.query(
        "SELECT set_config('app.tenant_id'," + _literal(str(tenant)) + ",true)"
    )
    identity = json.loads(
        writer.query(
            "SELECT row_to_json(i) FROM sync_fence_api.read_writer_identity("
            + _literal(tenant)
            + ") i"
        )[0]
    )
    nonce = hashlib.sha256(b"public-disposable-sync-binding-vector").digest()
    assert len(nonce) == 32
    binding = {
        "authority_id": str(uuid4()),
        "control_instance": str(uuid4()),
        "business_instance": str(uuid4()),
        "restore_epoch": str(uuid4()),
        "control_version": 1,
        "issuer": str(uuid4()),
        "lease_id": str(uuid4()),
        "device_id": str(device),
        "game_id": str(game),
        "wire_d4": "fixture-one",
        "internal_generation": 1,
        "recovery_generation": 1,
        "codec_version": 1,
        "request_fingerprint": "public-request-fp",
        "d5": str(uuid4()),
        "event_fingerprint": "public-event-fp",
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(),
        **identity,
    }
    with db.peer(ACTOR) as actor:
        statement = (
            sql.SQL(
                "SELECT sync_fence_api.publish_writer_binding({},{},{},{}::jsonb,{})"
            )
            .format(
                *(
                    sql.Literal(v)
                    for v in (
                        tenant,
                        attempt,
                        phase,
                        json.dumps(binding),
                        hashlib.sha256(nonce).digest(),
                    )
                )
            )
            .as_string()
        )
        actor.query(statement)
    return tenant, attempt, phase, nonce, device, game, binding


def _close_observe(db, values):
    """入口close commit後の別実LOGIN/sessionからのみ観測する。"""
    tenant, attempt, phase, _, _, _, binding = values
    close = uuid4()
    args = ",".join(
        _literal(v) for v in (tenant, attempt, phase, binding["lease_id"], close)
    )
    with db.peer(ACTOR) as actor:
        actor.query("SELECT sync_fence_api.close_writer_binding(" + args + ")")
    with db.peer(ACTOR) as observer:
        return observer.query(
            "SELECT outcome FROM sync_fence_api.observe_writer_binding(" + args + ")"
        )


def test_real_same_writer_admission_commit_and_closed_gate(binding_database):
    """実app同TX通過はcommit観測となり、閉じた入口へ後着進入しない。"""
    db = binding_database
    with db.peer() as writer:
        values = _publish(db, writer)
        writer.query(assert_statement(*values[:6]))
        writer.query("COMMIT")
        assert _close_observe(db, values) == ("COMMITTED",)
        writer.query("BEGIN")
        writer.query(
            "SELECT set_config('app.tenant_id'," + _literal(str(values[0])) + ",true)"
        )
        _, state = writer.execute(assert_statement(*values[:6]))
        assert state != "00000"
        writer.query("ROLLBACK")


def test_real_other_transaction_rejected_and_outer_rollback_observed(binding_database):
    """nonceを知っても別TXは拒否し、実outer abortだけrollbackとする。"""
    db = binding_database
    with db.peer() as original, db.peer() as other:
        values = _publish(db, original)
        other.query("BEGIN")
        other.query(
            "SELECT set_config('app.tenant_id'," + _literal(str(values[0])) + ",true)"
        )
        _, state = other.execute(assert_statement(*values[:6]))
        assert state != "00000"
        other.query("ROLLBACK")
        original.query("ROLLBACK")
        assert _close_observe(db, values) == ("ROLLBACK_CONFIRMED",)


def test_real_unasserted_live_transaction_is_not_rollback(binding_database):
    """未進入の生存TXは閉入口だけ。取消/全終了証拠へ昇格しない。"""
    db = binding_database
    with db.peer() as writer:
        values = _publish(db, writer)
        assert _close_observe(db, values) == ("ENTRY_CLOSED_UNADMITTED",)
        _, state = writer.execute(assert_statement(*values[:6]))
        assert state != "00000"
        writer.query("ROLLBACK")


def test_real_admission_inside_savepoint_is_rejected(binding_database):
    """subtransactionのadmissionをtop-level成功と扱わない。"""
    db = binding_database
    with db.peer() as writer:
        values = _publish(db, writer)
        writer.query("SAVEPOINT nested")
        _, state = writer.execute(assert_statement(*values[:6]))
        assert state != "00000"
        writer.query("ROLLBACK TO SAVEPOINT nested")
        assert _close_observe(db, values) == ("ENTRY_CLOSED_UNADMITTED",)
        writer.query("ROLLBACK")


def test_real_direct_auxiliary_dml_and_other_roles_are_denied(binding_database):
    """app/actorの直接security原本読書きを製品ACLで拒否する。"""
    db = binding_database
    for role in (APP, ACTOR):
        with db.peer(role) as peer:
            for statement in (
                "SELECT * FROM sync_fence.writer_bindings",
                "DELETE FROM sync_fence.writer_admissions",
                "TRUNCATE sync_fence.writer_bindings",
            ):
                _, state = peer.execute(statement)
                assert state == "42501"


def test_real_expired_binding_does_not_authorize_writer(binding_database):
    """実clockの期限後は同writer/同nonceでも拒否する。"""
    db = binding_database
    with db.peer() as writer:
        values = _publish(db, writer, ttl=1)
        writer.query("SELECT pg_sleep(1.1)")
        _, state = writer.execute(assert_statement(*values[:6]))
        assert state != "00000"
        writer.query("ROLLBACK")
        assert _close_observe(db, values) == ("ROLLBACK_CONFIRMED",)


def test_real_nested_rollback_preserves_outer_admission(binding_database):
    """外側でのadmission後の既D5 savepointは外側資格を失わせない。"""
    db = binding_database
    with db.peer() as writer:
        values = _publish(db, writer)
        writer.query(assert_statement(*values[:6]))
        writer.query("SAVEPOINT existing_d5_guard")
        writer.query("SELECT 1")
        writer.query("ROLLBACK TO SAVEPOINT existing_d5_guard")
        writer.query("RELEASE SAVEPOINT existing_d5_guard")
        writer.query(assert_statement(*values[:6]))
        writer.query("COMMIT")
        assert _close_observe(db, values) == ("COMMITTED",)


def test_real_cookie_v3_control_nonce_same_writer_u1_and_terminal(
    initial_scope_database,
):
    """実認証/実外部fence/実control PG/同writer U1/実終結を縦断する。"""
    from uuid import UUID

    import psycopg

    from pitchlog.repositories.initial_recording_right import _credential_digest

    from .sync_writer_binding_support import binding_app, binding_broker

    db = initial_scope_database
    # 試合の事前行はこのN1-U2単体fixtureの準備に限る。UI作成/開始実証とは別。
    issued = db.actor("grant=issue(); print(json.dumps(receipt(grant)))")
    token, subject = UUID(int=7201), UUID(int=7202)
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.system_settings(key,value) VALUES "
            "('auth.token_ttl_seconds','3600') ON CONFLICT(key) "
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
    before = db.authority.event_counts()
    credential = _credential_digest("credential-a").hex()
    body = f"""
authority=AuthorityBinding(UUID(int=7101),UUID(int=7102),UUID(int=7103))
attempt=AttemptBinding(authority,context.tenant_id,UUID('{db.device_id}'),
 UUID('{db.game_id}'),'fixture-first-ball',{issued["generation"]},uuid4(),1,
 'public-single-request-fp',1)
phase=EventPhaseBinding(attempt,uuid4(),1,1,uuid4(),'public-single-event-fp')
with tenant_transaction_scope(context) as tx:
 bound=control.bind_writer(tx,context,phase,cookie=cookie)
 bound.assert_current()
 device=tx.run_function(_BindFirstBallDeviceToken(attempt.attempt_id,
  phase.phase_id,bound._lease.nonce,attempt.device_id,attempt.game_id,
  bytes.fromhex('{credential}')))
 assert device.rows==((True,),)
 right=tx.run_function(_CheckFirstBallRightToken(attempt.attempt_id,
  phase.phase_id,bound._lease.nonce,attempt.device_id,attempt.game_id,
  attempt.internal_generation,1,bytes.fromhex('{issued["proof_digest"]}')))
 assert right.rows==((True,True),)
class PlannedRollback(Exception):
 pass
try:
 with tenant_transaction_scope(context) as tx:
  second_attempt=AttemptBinding(authority,context.tenant_id,attempt.device_id,
   attempt.game_id,attempt.wire_d4,attempt.internal_generation,uuid4(),1,
   'public-second-request-fp',1)
  second_phase=EventPhaseBinding(second_attempt,uuid4(),1,1,uuid4(),
   'public-second-event-fp')
  control.bind_writer(tx,context,second_phase,cookie=cookie)
  raise PlannedRollback('controlled outer rollback')
except PlannedRollback:
 pass
else:
 raise AssertionError('outer rollback was not propagated')
print(json.dumps(dict(actual_cookie=True,actual_u1_device=True,
 actual_u1_right=True,actual_commit_and_terminal=True,actual_rollback=True)))
"""
    with binding_broker(db, token):
        assert binding_app(db, body) == dict(
            actual_cookie=True,
            actual_u1_device=True,
            actual_u1_right=True,
            actual_commit_and_terminal=True,
            actual_rollback=True,
        )
    after = db.authority.event_counts()
    for event in ("binding_intent", "binding_published", "binding_terminal"):
        assert after.get(event, 0) - before.get(event, 0) == 2
    assert after.get("lease_close", 0) - before.get("lease_close", 0) == 2
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT state,count(*) FROM sync_fence.writer_bindings GROUP BY state"
        ).fetchall() == [("closed", 2)]
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.writer_admissions"
        ).fetchone() == (1,)

    # 固定private guardはprivileged試験DMLでも効く。新data/業務結果を作らない。
    for statement in (
        "UPDATE sync_fence.writer_bindings SET state='open',close_id=NULL",
        "UPDATE sync_fence.writer_bindings SET backend_pid=backend_pid+1",
        "DELETE FROM sync_fence.writer_admissions",
        "TRUNCATE sync_fence.writer_bindings CASCADE",
    ):
        with psycopg.connect(db.authority.database.business_admin) as admin:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                admin.execute(statement)
