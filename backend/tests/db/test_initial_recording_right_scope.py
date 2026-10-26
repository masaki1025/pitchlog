"""単一issuer/実台帳/実actor scopeの接合。開始HTTP/UIの成功ではない。"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from db_fixtures import _dsn_names

from .initial_recording_right_scope_support import (
    InitialGrantDatabase,
    isolated_initial_grant_database,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture
def initial_scope_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InitialGrantDatabase]:
    """owned3PGだけを供給し、既autouseの実identity検査を無効化しない。"""
    with isolated_initial_grant_database(monkeypatch) as database:
        admin_name, role_name = _dsn_names()
        monkeypatch.setenv(admin_name, database.authority.database.primary_admin)
        monkeypatch.setenv(role_name, database.authority.database.endpoints.primary_dsn)
        yield database


@pytest.fixture
def admin_connection(
    initial_scope_database: InitialGrantDatabase,
) -> Iterator[psycopg.Connection]:
    """既identity autouseへ所有primaryの実adminを渡す。"""
    with psycopg.connect(
        initial_scope_database.authority.database.primary_admin
    ) as connection:
        yield connection


@pytest.fixture
def tested_role_connection(
    initial_scope_database: InitialGrantDatabase,
) -> Iterator[psycopg.Connection]:
    """既identity autouseへ所有primaryの実限定roleを渡す。"""
    with psycopg.connect(
        initial_scope_database.authority.database.endpoints.primary_dsn
    ) as connection:
        yield connection


def test_real_initial_scope_app_actor_acl_and_memberships(
    initial_scope_database: InitialGrantDatabase,
) -> None:
    """app/actorを実LOGINで分離し、秘密表DML/任意D4とapp9EXECUTEを拒否する。"""
    app = initial_scope_database.acl_probe("app")
    actor = initial_scope_database.acl_probe("actor")
    assert app == {
        "identity": ["pitchlog_app", "pitchlog_app"],
        "states": ["42501"] * 26,
    }
    assert actor == {
        "identity": ["pitchlog_initial_actor", "pitchlog_initial_actor"],
        "states": ["42501"] * 17,
    }
    assert initial_scope_database.ledger_snapshot() == ()


def test_real_initial_scope_commits_and_replays_same_v12_without_reserving(
    initial_scope_database: InitialGrantDatabase,
) -> None:
    """実reserve/claimと暗号保存後、同request再交付は同V12で予約を増やさない。"""
    database = initial_scope_database
    result = database.actor("""
first=issue()
second=issue(replace(owner,attempt_id=uuid4()))
assert first.recording_right_proof==second.recording_right_proof
assert first==second
print(json.dumps(receipt(first)))
""")
    assert result["game_id"] == str(database.game_id)
    assert result["device_id"] == str(database.device_id)
    assert type(result["generation"]) is int and result["generation"] == 1
    assert result["epoch"] == "1"
    rows = database.ledger_snapshot()
    assert len(rows) == 1
    assert rows[0] == (
        database.attempt_id,
        database.tenant_id,
        database.game_id,
        database.start_request_id,
        1,
        1,
        True,
        False,
    )
    saved = database.storage()
    assert all(len(rows) == 1 for rows in saved.values())
    generation = saved["recording_generations"][0]
    assert generation["generation"] == 1
    assert generation["kind"] == "normal" and generation["issuance_order"] == 1
    assert generation["confirmed_watermark"] == generation["applied_prefix"] == 0
    assert generation["holder_device"] == str(database.device_id)
    assert generation["proof_digest"] == "\\x" + result["proof_digest"]
    assert generation["recovery_generation"] == 1
    delivery = saved["recording_right_deliveries"][0]
    assert delivery["key_id"] == "k1"
    assert len(delivery["nonce"]) == 2 + 12 * 2
    assert len(delivery["ciphertext"]) == 2 + 48 * 2
    assert saved["game_start_attempts"][0]["outcome"] == "committed"
    # grant-only部品はゲーム開始/初期名簿保存をまだ実装していない。
    with psycopg.connect(database.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT status,started_at FROM public.games WHERE id=%s",
            (database.game_id,),
        ).fetchone() == ("preparing", None)
        assert admin.execute("SELECT count(*) FROM public.game_lineups").fetchone() == (
            0,
        )


@pytest.mark.parametrize("reason", ("wrong", "missing", "revoked", "tenant", "foreign"))
def test_real_initial_scope_rejects_credentials_or_owner_before_reservation(
    initial_scope_database: InitialGrantDatabase,
    reason: str,
) -> None:
    """無効資格/失効/別tenant ownerは実台帳の予約前に停止する。"""
    database = initial_scope_database
    if reason == "revoked":
        with psycopg.connect(database.authority.database.business_admin) as admin:
            admin.execute(
                "UPDATE public.trusted_devices SET revoked_at=CURRENT_TIMESTAMP "
                "WHERE tenant_id=%s AND device_id=%s",
                (database.tenant_id, database.device_id),
            )
    mutations = {
        "wrong": "issue(credential='incorrect-public-vector')",
        "missing": "issue(replace(owner,device_id=uuid4()))",
        "revoked": "issue()",
        "tenant": f"issue(replace(owner,tenant_id=UUID('{database.other_tenant_id}')))",
        "foreign": (
            f"issue(replace(owner,tenant_id=UUID('{database.other_tenant_id}')),"
            f"selected_context=make_tenant_context(UUID('{database.other_tenant_id}')))"
        ),
    }
    result = database.actor(f"""
try:
    {mutations[reason]}
except InitialGrantUnavailable:
    print(json.dumps({{'refused':True}}))
else:
    raise AssertionError('invalid owner/credential acknowledged')
""")
    assert result == {"refused": True}
    assert database.ledger_snapshot() == ()
    assert all(rows == [] for rows in database.storage().values())


@pytest.mark.parametrize("mutation", ("payload", "device"))
def test_real_initial_scope_replay_rejects_owner_changes(
    initial_scope_database: InitialGrantDatabase,
    mutation: str,
) -> None:
    """同一requestを別payload/端末へ結び直さず、保存/実予約を維持する。"""
    database = initial_scope_database
    first = database.actor("print(json.dumps(receipt(issue())))")
    before = database.storage()
    reservations = database.ledger_snapshot()
    changed = (
        "replace(owner,request_digest=b'x'*32,attempt_id=uuid4())"
        if mutation == "payload"
        else f"replace(owner,device_id=UUID('{database.other_device_id}'),"
        "attempt_id=uuid4())"
    )
    result = database.actor(f"""
from sqlalchemy.exc import DBAPIError
try:
    issue({changed})
except (InitialGrantConflict,InitialGrantUnavailable,DBAPIError) as error:
    print(json.dumps({{'refused':True,'error_type':type(error).__name__}}))
else:
    raise AssertionError('changed replay acknowledged')
""")
    assert result["refused"] is True
    assert database.storage() == before
    assert database.ledger_snapshot() == reservations
    assert database.actor("print(json.dumps(receipt(issue())))") == first


@pytest.mark.parametrize("stage", ("generation", "delivery", "commit"))
def test_real_initial_scope_fault_rolls_back_all_business_inserts(
    initial_scope_database: InitialGrantDatabase,
    stage: str,
) -> None:
    """片側INSERT/遅延commit故障は実到達し、D4消費を巻き戻したと断定しない。"""
    from typing import Literal, cast

    database = initial_scope_database
    with database.fault(cast(Literal["generation", "delivery", "commit"], stage)):
        result = database.actor("""
from sqlalchemy.exc import DBAPIError
try:
    issue()
except DBAPIError as error:
    print(json.dumps({'refused':True,'error_type':type(error).__name__}))
else:
    raise AssertionError('failed transaction acknowledged')
""")
        assert result["refused"] is True
    saved = database.storage()
    assert saved["recording_generations"] == saved["recording_right_deliveries"] == []
    assert len(saved["game_start_requests"]) == len(saved["game_start_attempts"]) == 1
    assert saved["game_start_attempts"][0]["outcome"] == "pending"
    reservations = database.ledger_snapshot()
    assert len(reservations) == 1 and reservations[0][4:] == (1, 1, True, False)
    # 業務側rollback確定でもclaim済みD4を再利用/別attemptへ自動再送しない。
    retry = database.actor("""
from pitchlog.durable_rights_ledger import LedgerUnavailable,LedgerOutcomeUnconfirmed
from pitchlog.repositories.rg1 import RG1Unavailable
try:
    issue(replace(owner,attempt_id=uuid4()))
except (LedgerUnavailable,LedgerOutcomeUnconfirmed,
        InitialGrantUnavailable,RG1Unavailable) as error:
    print(json.dumps({'refused':True,'error_type':type(error).__name__}))
else:
    raise AssertionError('unresolved/claimed attempt automatically reissued')
""")
    assert retry["refused"] is True
    assert database.ledger_snapshot() == reservations
    assert database.storage() == saved


def test_b1_real_peer_cookie_verification_revocation_and_global_grants(
    initial_scope_database: InitialGrantDatabase,
    tmp_path,
) -> None:
    """公開vector/実peer/正式authnだけを接合し、enroll成功を作らない。"""
    import json
    from uuid import uuid4

    from psycopg import sql

    from pitchlog.authz.product_catalog import inspect_product_authz_catalog
    from pitchlog.authz.product_role_contract import generate_lifecycle_role_sql

    db = initial_scope_database
    token, subject = uuid4(), uuid4()
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            (
                "INSERT INTO public.system_settings(key,value) VALUES ('a"
                "uth.token_ttl_seconds','3600') ON CONFLICT(key) DO UPDAT"
                "E SET value=EXCLUDED.value"
            )
        )
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(tenant_id,id) VALUES (%s,%s)",
            (db.tenant_id, subject),
        )
        admin.execute(
            (
                "INSERT INTO public.tenant_credentials(auth_subject_id,pa"
                "ssword_hash,generation) VALUES (%s,'public-fixture-not-u"
                "sed-for-login',1)"
            ),
            (subject,),
        )
        admin.execute(
            (
                "INSERT INTO public.tenant_tokens(tenant_id,id,auth_subje"
                "ct_id,credential_generation,expires_at,last_used_at) VAL"
                "UES (%s,%s,%s,1,clock_timestamp()+interval '5 minutes',c"
                "lock_timestamp()-interval '1 day')"
            ),
            (db.tenant_id, token, subject),
        )
        before = admin.execute(
            "SELECT expires_at,last_used_at FROM public.tenant_tokens WHERE id=%s",
            (token,),
        ).fetchone()

    def check(tenant=db.tenant_id):
        return db.verifier(f"""
result=_issue_initial_broker_context(SecretStr(signer.encode(UUID('{token}'))),UUID('{tenant}'),verifier)
print(json.dumps({{
    'verified':result is not None,
    'tenant_matches':result is not None and result[0].tenant_id==UUID('{db.tenant_id}')
}}))
""")

    assert check() == dict(verified=True, tenant_matches=True)
    assert db.verifier_peer_rejections() == {"20003": True, "20002": True}
    assert check(db.other_tenant_id) == dict(verified=False, tenant_matches=False)
    with psycopg.connect(db.authority.database.business_admin) as admin:
        after = admin.execute(
            "SELECT expires_at,last_used_at FROM public.tenant_tokens WHERE id=%s",
            (token,),
        ).fetchone()
        assert (
            before is not None
            and after is not None
            and after[0] > before[0]
            and after[1] > before[1]
        )
    for mutation, restore, args in [
        (
            (
                "UPDATE public.tenant_tokens "
                "SET last_used_at=clock_timestamp()-interval '2 days', "
                "expires_at=clock_timestamp()-interval '1 day' WHERE id=%s"
            ),
            (
                "UPDATE public.tenant_tokens SET expires_at=clock_timesta"
                "mp()+interval '5 minutes' WHERE id=%s"
            ),
            (token,),
        ),
        (
            (
                "UPDATE public.tenant_credentials SET generation=2 WHERE "
                "auth_subject_id=%s"
            ),
            (
                "UPDATE public.tenant_credentials SET generation=1 WHERE "
                "auth_subject_id=%s"
            ),
            (subject,),
        ),
        (
            (
                "UPDATE public.tenants SET enabled=false, "
                "disabled_at=clock_timestamp() WHERE id=%s"
            ),
            ("UPDATE public.tenants SET enabled=true, disabled_at=NULL WHERE id=%s"),
            (db.tenant_id,),
        ),
    ]:
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(mutation.encode(), args)
        assert check() == dict(verified=False, tenant_matches=False)
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(restore.encode(), args)
    rejected = db.verifier(f"""
from pitchlog.recording_rights.initial_grant_broker import (
    _verify_initial_cookie,_auth_verifier_state
)
bad=_verify_initial_cookie(verifier,SecretStr(str(UUID('{token}'))))
tampered=_verify_initial_cookie(verifier,SecretStr(signer.encode(UUID('{token}'))+'x'))
assert bad is None and tampered is None
engine=_auth_verifier_state(verifier).engine
with engine.begin() as conn:
    identity=list(conn.exec_driver_sql(
        'SELECT session_user,current_user,current_database()').one())
codes=[]
for statement in [
    'SELECT authn.logout(NULL::uuid)',
    'SELECT * FROM public.tenant_tokens','SELECT * FROM public.players'
]:
    try:
        with engine.begin() as conn:conn.exec_driver_sql(statement)
    except Exception:codes.append('denied')
    else:raise AssertionError('unexpected verifier authority')
print(json.dumps({{'signature_rejected':True,
    'other_authn_and_tables_denied':len(codes),'identity':identity}}))
""")
    assert rejected == dict(
        signature_rejected=True,
        other_authn_and_tables_denied=3,
        identity=[
            "pitchlog_initial_auth_verifier",
            "pitchlog_initial_auth_verifier",
            "ledger_fixture",
        ],
    )

    with psycopg.connect(db.authority.database.business_admin) as admin:
        identity = admin.execute(
            "SELECT oid FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert identity is not None
        oid = identity[0]
        report = inspect_product_authz_catalog(
            admin, privileged_role_oids=frozenset({oid})
        )
        assert report.ok, [v.check_id for v in report.violations]
        admin.rollback()
    changes = [
        "CREATE FUNCTION authn.b1_unknown() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
        (
            "CREATE SCHEMA b1_unknown; CREATE FUNCTION b1_unknown.f()"
            " RETURNS integer LANGUAGE sql AS 'SELECT 1'; GRANT EXECU"
            "TE ON FUNCTION b1_unknown.f() TO pitchlog_initial_auth_v"
            "erifier"
        ),
        (
            "CREATE SCHEMA b1_unknown; CREATE TABLE b1_unknown.t(id i"
            "nteger); GRANT SELECT ON b1_unknown.t TO pitchlog_initia"
            "l_auth_verifier"
        ),
        "CREATE SCHEMA b1_unknown AUTHORIZATION pitchlog_initial_auth_verifier",
        (
            "CREATE SCHEMA b1_unknown; CREATE FUNCTION b1_unknown.f()"
            " RETURNS integer LANGUAGE sql AS 'SELECT 1'; ALTER FUNCT"
            "ION b1_unknown.f() OWNER TO pitchlog_initial_auth_verifi"
            "er"
        ),
        "GRANT CREATE ON SCHEMA authn TO PUBLIC",
        "CREATE TYPE authn.b1_unknown AS ENUM ('public-vector')",
        "GRANT CREATE ON DATABASE postgres TO pitchlog_initial_auth_verifier",
        "GRANT CREATE ON DATABASE postgres TO PUBLIC",
    ]
    for statement in changes:
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(statement.encode())
            report = inspect_product_authz_catalog(
                admin, privileged_role_oids=frozenset({oid})
            )
            assert "PRODUCT-CATALOG:INITIAL-VERIFIER-GLOBAL" in {
                v.check_id for v in report.violations
            }
            admin.rollback()
    # 新role一件にも旧6と同じ再適用/衝突全取消を実証する。
    role_sql = generate_lifecycle_role_sql("pitchlog_initial_auth_verifier")
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(role_sql.encode())
    for attribute in [
        "SUPERUSER",
        "BYPASSRLS",
        "NOLOGIN",
        "CREATEROLE",
        "CREATEDB",
        "REPLICATION",
        "INHERIT",
    ]:
        with pytest.raises(psycopg.Error):
            with psycopg.connect(db.authority.database.business_admin) as admin:
                admin.execute(
                    sql.SQL("ALTER ROLE pitchlog_initial_auth_verifier " + attribute)
                )
                admin.execute(role_sql.encode())
    for grant in [
        "GRANT pitchlog_app TO pitchlog_initial_auth_verifier",
        "GRANT pitchlog_initial_auth_verifier TO pitchlog_app",
    ]:
        with pytest.raises(psycopg.Error):
            with psycopg.connect(db.authority.database.business_admin) as admin:
                admin.execute(grant.encode())
                admin.execute(role_sql.encode())
    with psycopg.connect(db.authority.database.business_admin) as admin:
        final_report = inspect_product_authz_catalog(
            admin, privileged_role_oids=frozenset({oid})
        )
        assert final_report.ok, [v.check_id for v in final_report.violations]
        admin.rollback()
    assert check() == dict(verified=True, tenant_matches=True)
    (tmp_path / "b1-observations.json").write_text(
        json.dumps(
            {
                "cookie_verified": True,
                "TTL_before": [v.isoformat() for v in before],
                "TTL_after": [v.isoformat() for v in after],
                "negative_revocations": 3,
                "signature_and_acl": rejected,
                "peer_rejections": [20003, 20002],
                "unknown_global_permissions_ownership_rejected": len(changes),
                "role_attribute_collisions_rejected": 7,
                "membership_collisions_rejected": 2,
                "role_reapply_passed": True,
                "global_normal_after_rollback": final_report.ok,
                "no_enrollment_or_worker": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
