"""実製品のwriter SQL境界。外部lease/broker縦断の成立とは区別する。"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
import sqlalchemy as sa
from psycopg import sql

from .rg1_lifecycle_support import docker
from .sync_writer_binding_support import (
    ACTOR,
    APP,
    BindingPeer,
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


@pytest.mark.parametrize("d1less", [False, True])
def test_control_retirement_blocks_old_attempt_and_keeps_new_attempt(
    initial_scope_database,
    d1less,
):
    """実制御PGで旧試行を遮断し、別試行の同原文登録は維持する。"""
    register_function = (
        "register_d1less_phase" if d1less else "register_first_ball_phase"
    )
    read_function = (
        "read_p3_attempt_recovery_state" if d1less else "read_attempt_recovery_state"
    )
    owner = initial_scope_database
    cluster = owner.authority
    issuer = docker(
        "exec",
        cluster.binding_control,
        "psql",
        "-X",
        "-A",
        "-t",
        "-q",
        "-U",
        "postgres",
        "-d",
        "binding_control_fixture",
        "-c",
        "SELECT authority_id FROM sync_control.authorities WHERE state='active'",
    ).strip()
    authority = {
        "authority_id": issuer,
        "control_instance": str(UUID(int=7101)),
        "business_instance": str(UUID(int=7102)),
        "restore_epoch": str(UUID(int=7103)),
        "control_version": 1,
    }
    tenant, device, game, attempt, phase, d5 = (uuid4() for _ in range(6))
    original = {
        **authority,
        "attempt_id": str(attempt),
        "device_id": str(device),
        "game_id": str(game),
        "wire_d4": "original-D4",
        "internal_generation": 1,
        "codec_version": 1,
        "request_fingerprint": "original-request",
        "phase_id": str(phase),
        "d5": str(d5),
        "event_fingerprint": "original-event",
        "body_fingerprint": "a" * 64,
    }
    if d1less:
        original["phase_kind"] = "d1less"
    with BindingPeer(
        cluster.binding_control, "binding_control_fixture", ACTOR
    ) as actor:
        registration = (
            f"SELECT sync_control.{register_function}("
            + _literal(tenant)
            + ","
            + _literal(json.dumps(original))
            + "::jsonb)"
        )
        assert actor.execute(registration)[1] == "00000"
        own_reader = "read_d1less_phase" if d1less else "read_first_ball_phase"
        other_reader = "read_first_ball_phase" if d1less else "read_d1less_phase"
        read_args = ",".join(_literal(v) for v in (tenant, attempt, phase))
        assert (
            json.loads(
                actor.query(
                    f"SELECT context_json FROM sync_control.{own_reader}({read_args})"
                )[0]
            )
            == original
        )
        assert actor.query(
            f"SELECT count(*) FROM sync_control.{other_reader}({read_args})"
        ) == ("0",)
        invalid = {**original, "phase_kind": "unknown"}
        assert (
            actor.execute(
                registration.replace(json.dumps(original), json.dumps(invalid))
            )[1]
            == "42501"
        )
        if d1less:
            invalid = {**original, "d1": 1}
            assert (
                actor.execute(
                    registration.replace(json.dumps(original), json.dumps(invalid))
                )[1]
                == "42501"
            )
        retire = (
            "SELECT sync_control.retire_sync_attempt("
            + ",".join(
                _literal(value)
                for value in (
                    tenant,
                    attempt,
                    device,
                    game,
                    "original-D4",
                    1,
                    "original-request",
                    issuer,
                    7,
                    "a" * 64,
                )
            )
            + ")"
        )
        assert actor.query(retire) == ("retired",)
        assert actor.query(retire) == ("retired",)
        assert actor.execute(registration)[1] == "42501"
        altered = {**original, "request_fingerprint": "other-request"}
        assert (
            actor.execute(
                registration.replace(json.dumps(original), json.dumps(altered))
            )[1]
            == "42501"
        )
        fresh = {**original, "attempt_id": str(uuid4()), "phase_id": str(uuid4())}
        assert (
            actor.execute(
                registration.replace(json.dumps(original), json.dumps(fresh))
            )[1]
            == "00000"
        )

    # 未登録と旧NULLの差は、fixture側の推論でなく製品固定関数の実値で判定する。
    def register(value):
        return (
            f"SELECT sync_control.{register_function}("
            + _literal(tenant)
            + ","
            + _literal(json.dumps(value))
            + "::jsonb)"
        )

    def body_state(value, body="a" * 64):
        values = (
            tenant,
            value["attempt_id"],
            device,
            game,
            "original-D4",
            1,
            "original-request",
            issuer,
            d5,
            "original-event",
            body,
        )
        return (
            f"SELECT sync_control.{read_function}("
            + ",".join(_literal(v) for v in values)
            + ")"
        )

    def retirement(value, body="a" * 64):
        values = (
            tenant,
            value["attempt_id"],
            device,
            game,
            "original-D4",
            1,
            "original-request",
            issuer,
            7,
            body,
        )
        return (
            "SELECT sync_control.retire_sync_attempt("
            + ",".join(_literal(v) for v in values)
            + ")"
        )

    with BindingPeer(
        cluster.binding_control, "binding_control_fixture", ACTOR
    ) as actor:
        legacy = {**original, "attempt_id": str(uuid4()), "phase_id": str(uuid4())}
        legacy.pop("body_fingerprint")
        assert actor.execute(register(legacy))[1] == "00000"
        assert actor.query(body_state(legacy)) == ("unresolved",)
        assert actor.execute(retirement(legacy))[1] == "42501"
        never = {**original, "attempt_id": str(uuid4()), "phase_id": str(uuid4())}
        assert actor.query(body_state(never)) == ("absent",)
        assert actor.query(retirement(never)) == ("retired",)
        assert actor.query(body_state(never)) == ("matching",)
        assert actor.query(body_state(never, "b" * 64)) == ("unresolved",)
        assert actor.execute(retirement(never, "b" * 64))[1] == "42501"
        assert actor.execute(register(never))[1] == "42501"

    def blocked(peer, statement):
        pid = int(peer.query("SELECT pg_backend_pid()")[0])
        done = threading.Event()
        result = {}

        def run():
            try:
                result["value"] = peer.execute(statement)
            finally:
                done.set()

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            observed = docker(
                "exec",
                cluster.binding_control,
                "psql",
                "-X",
                "-A",
                "-t",
                "-q",
                "-U",
                "postgres",
                "-d",
                "binding_control_fixture",
                "-c",
                "SELECT wait_event_type||':'||wait_event "
                "FROM pg_stat_activity WHERE pid=" + str(pid),
            ).strip()
            if observed == "Lock:advisory":
                assert not done.is_set()
                return worker, done, result
            time.sleep(0.02)
        pytest.fail("control登録/遮断が同じ鍵で実待機しない")

    for register_first in (True, False):
        value = {**original, "attempt_id": str(uuid4()), "phase_id": str(uuid4())}
        with (
            BindingPeer(
                cluster.binding_control, "binding_control_fixture", ACTOR
            ) as first,
            BindingPeer(
                cluster.binding_control, "binding_control_fixture", ACTOR
            ) as second,
        ):
            first.query("BEGIN")
            first.query(register(value) if register_first else retirement(value))
            worker, done, result = blocked(
                second, retirement(value) if register_first else register(value)
            )
            first.query("COMMIT")
            assert done.wait(3)
            worker.join(timeout=1)
            assert result["value"][1] == ("00000" if register_first else "42501")
            assert first.query(body_state(value)) == ("matching",)


def _publish(
    db,
    writer,
    *,
    ttl=20,
    attempt_id=None,
    device_id=None,
    authority_id=None,
    publish=True,
):
    """Actual writer自己観測とcontrol専用LOGINから限定SQLを検査する。"""
    tenant, game = db.owner.tenant_id, db.owner.game_id
    attempt, phase, device = attempt_id or uuid4(), uuid4(), device_id or uuid4()
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
        "authority_id": str(authority_id or uuid4()),
        "control_instance": str(uuid4()),
        "business_instance": str(uuid4()),
        "restore_epoch": str(uuid4()),
        "control_version": 1,
        "issuer": str(authority_id or uuid4()),
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
    if publish:
        with db.peer(ACTOR) as actor:
            actor.query(
                _publish_statement(
                    (tenant, attempt, phase, nonce, device, game, binding)
                )
            )
    return tenant, attempt, phase, nonce, device, game, binding


def _publish_statement(values):
    """同一実writer identityから固定publish SQLを組み立てる。"""
    tenant, attempt, phase, nonce, _, _, binding = values
    return (
        sql.SQL("SELECT sync_fence_api.publish_writer_binding({},{},{},{}::jsonb,{})")
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


def _business_retirement_statement(
    values, authority_id, *, d4="fixture-one", d5=None, event_fingerprint=None
):
    """既writer原本に対応する単一SQLだけをactor試験へ渡す。"""
    tenant, attempt, _, _, device, game, binding = values
    return (
        "SELECT sync_fence_api.retire_sync_attempt("
        + ",".join(
            _literal(value)
            for value in (
                tenant,
                attempt,
                device,
                game,
                d5 or binding["d5"],
                d4,
                1,
                binding["request_fingerprint"],
                event_fingerprint or binding["event_fingerprint"],
                authority_id,
                1,
            )
        )
        + ")"
    )


def test_business_retirement_serializes_publish_and_checks_actual_xid(
    binding_database,
):
    """publish前後の同試行を実業務鍵で分離し、未終結を許可しない。"""
    db = binding_database
    from pitchlog.authz.product_catalog import inspect_product_authz_catalog

    with psycopg.connect(db.owner.authority.database.business_admin) as admin:
        role = admin.execute(
            "SELECT oid FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert role is not None
        catalog = inspect_product_authz_catalog(
            admin,
            privileged_role_oids=frozenset({role[0]}),
        )
        assert catalog.ok, [value.check_id for value in catalog.violations]
        assert admin.execute(
            "SELECT has_function_privilege('pitchlog_app',"
            "'sync_fence_api.retire_sync_attempt("
            "uuid,uuid,uuid,uuid,uuid,text,bigint,text,text,uuid,bigint)',"
            "'EXECUTE'),has_function_privilege('pitchlog_sync_binding_actor',"
            "'sync_fence_api.retire_sync_attempt("
            "uuid,uuid,uuid,uuid,uuid,text,bigint,text,text,uuid,bigint)',"
            "'EXECUTE')"
        ).fetchone() == (False, True)
    authority = uuid4()
    with db.peer(APP) as writer:
        before = _publish(db, writer, authority_id=authority, publish=False)
        with db.peer(ACTOR) as actor:
            retire = _business_retirement_statement(before, authority)
            assert actor.query(retire) == ("retired",)
            assert actor.query(retire) == ("retired",)
            assert actor.execute(_publish_statement(before))[1] == "42501"
            assert (
                actor.execute(
                    _business_retirement_statement(before, authority, d4="altered")
                )[1]
                == "42501"
            )
            assert (
                actor.execute(
                    _business_retirement_statement(before, authority, d5=uuid4())
                )[1]
                == "42501"
            )
            assert (
                actor.execute(
                    _business_retirement_statement(
                        before, authority, event_fingerprint="other-event"
                    )
                )[1]
                == "42501"
            )
        writer.query("ROLLBACK")
    with db.peer(APP) as writer:
        published = _publish(db, writer, authority_id=authority)
        with db.peer(ACTOR) as actor:
            assert actor.query(
                _business_retirement_statement(published, authority)
            ) == ("unresolved",)
        writer.query("ROLLBACK")
    assert _close_observe(db, published) == ("ROLLBACK_CONFIRMED",)
    with db.peer(ACTOR) as actor:
        assert actor.query(_business_retirement_statement(published, authority)) == (
            "retired",
        )


def test_existing_writer_definition_upgrades_only_from_exact_old_source(
    binding_database,
):
    """旧正式4trigger/2関数を同一DB内で再現し、限定migrationを実行する。"""
    source_root = Path(__file__).resolve().parents[3]
    revision = "a0c192a0e282479790eb8daae6b025a4952022fc"
    function_paths = (
        "FUNCTION:sync_fence_api:publish_writer_binding"
        "(uuid, uuid, uuid, jsonb, bytea).sql",
        "FUNCTION:sync_fence_api:guard_writer_records().sql",
    )
    previous: list[str] = []
    for filename in function_paths:
        value = subprocess.check_output(
            [
                "git",
                "show",
                f"{revision}:contracts/authz/product/function-bodies/functions/{filename}",
            ],
            cwd=source_root,
            text=True,
        )
        previous.append(
            value.split("\nALTER FUNCTION", 1)[0].replace(
                "CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1
            )
        )
    migration = importlib.import_module(
        "migrations.versions.0046_sync_attempt_retirement"
    )
    from psycopg.conninfo import conninfo_to_dict

    engine = sa.create_engine(
        "postgresql+psycopg://",
        connect_args=conninfo_to_dict(
            binding_database.owner.authority.database.business_admin
        ),
    )
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:

                def execute_body(value: str) -> None:
                    raw_connection = connection.connection.driver_connection
                    assert raw_connection is not None
                    with raw_connection.cursor() as cursor:
                        cursor.execute(value.encode("utf-8"))

                for trigger in (
                    "sync_attempt_retirement_immutable",
                    "sync_attempt_retirement_no_truncate",
                ):
                    connection.exec_driver_sql(
                        f"DROP TRIGGER {trigger} ON sync_fence.attempt_retirements"
                    )
                for value in previous:
                    execute_body(value)
                altered = previous[0].replace(
                    "writer publication rejected", "writer publication refused", 1
                )
                assert altered != previous[0]
                execute_body(altered)
                with pytest.raises(RuntimeError, match="定義・権限が一致しない"):
                    migration._upgrade_existing_functions(connection)
                execute_body(previous[0])
                migration._upgrade_existing_functions(connection)
                rows = connection.exec_driver_sql(
                    "SELECT tgname FROM pg_trigger WHERE tgrelid="
                    "'sync_fence.attempt_retirements'::regclass "
                    "AND NOT tgisinternal ORDER BY tgname"
                ).fetchall()
                assert rows == [
                    ("sync_attempt_retirement_immutable",),
                    ("sync_attempt_retirement_no_truncate",),
                ]
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _blocked_on_advisory(db, peer, statement):
    """別実接続が同鍵のadvisory xact lockで待つ事実だけを返す。"""
    pid = int(peer.query("SELECT pg_backend_pid()")[0])
    done = threading.Event()
    result = {}

    def run():
        try:
            result["value"] = peer.execute(statement)
        finally:
            done.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 3
    with psycopg.connect(db.owner.authority.database.business_admin) as admin:
        while time.monotonic() < deadline:
            observed = admin.execute(
                "SELECT wait_event_type,wait_event FROM pg_stat_activity WHERE pid=%s",
                (pid,),
            ).fetchone()
            if observed == ("Lock", "advisory"):
                assert not done.is_set()
                return worker, done, result
            time.sleep(0.02)
    pytest.fail("旧試行のpublish/retireが同業務鍵で待機しない")


def test_business_retirement_and_publish_are_actually_serialized(binding_database):
    """両先行順を実二接続で競合させ、同鍵遮断が原子的なことを確認する。"""
    db = binding_database
    authority = uuid4()
    with db.peer(APP) as writer, db.peer(ACTOR) as first, db.peer(ACTOR) as second:
        values = _publish(db, writer, authority_id=authority, publish=False)
        first.query("BEGIN")
        first.query(_publish_statement(values))
        worker, done, result = _blocked_on_advisory(
            db, second, _business_retirement_statement(values, authority)
        )
        first.query("COMMIT")
        assert done.wait(3)
        worker.join(timeout=1)
        assert result["value"] == (("unresolved",), "00000")
        writer.query("ROLLBACK")
    assert _close_observe(db, values) == ("ROLLBACK_CONFIRMED",)
    with db.peer(APP) as writer, db.peer(ACTOR) as first, db.peer(ACTOR) as second:
        values = _publish(db, writer, authority_id=authority, publish=False)
        first.query("BEGIN")
        first.query(_business_retirement_statement(values, authority))
        worker, done, result = _blocked_on_advisory(
            db, second, _publish_statement(values)
        )
        first.query("COMMIT")
        assert done.wait(3)
        worker.join(timeout=1)
        assert result["value"][1] == "42501"
        writer.query("ROLLBACK")


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
