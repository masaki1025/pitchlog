"""実peer主体/保護journal/同期PGを通すauthorityの接合を検査する。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from db_fixtures import _dsn_names

from pitchlog.durable_rights_ledger import adapter

from .durable_rights_ledger_support import (
    AuthorityDatabase,
    LedgerDatabase,
    isolated_authority_database,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture(scope="module")
def authority_database() -> Iterator[AuthorityDatabase]:
    """このmodule専用の三cluster/保護volume/Unix主体を所有する。"""
    with isolated_authority_database() as authority:
        yield authority


@pytest.fixture
def ledger_connections(
    authority_database: AuthorityDatabase, monkeypatch: pytest.MonkeyPatch
) -> LedgerDatabase:
    """既存identity autouseを実接続DSNで実施し、無効化しない。"""
    database = authority_database.database
    admin_name, role_name = _dsn_names()
    monkeypatch.setenv(admin_name, database.primary_admin)
    monkeypatch.setenv(role_name, database.endpoints.primary_dsn)
    return database


@pytest.fixture
def admin_connection(
    ledger_connections: LedgerDatabase,
) -> Iterator[psycopg.Connection]:
    """共通identity検査へ専用の管理接続を渡す。"""
    connection = psycopg.connect(ledger_connections.primary_admin)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def tested_role_connection(
    ledger_connections: LedgerDatabase,
) -> Iterator[psycopg.Connection]:
    """共通identity検査へ実制限app接続を渡す。"""
    connection = psycopg.connect(ledger_connections.endpoints.primary_dsn)
    try:
        yield connection
    finally:
        connection.close()


def test_real_authority_reservation_claim_fence_and_business_rollback(
    authority_database: AuthorityDatabase, ledger_connections: LedgerDatabase
) -> None:
    """実Unix資格/共有fence/冪等予約/単一消費を実peerまで照合する。"""
    params = tuple(str(uuid4()) for _ in range(4))
    code = f"""
p=tuple(UUID(v) for v in {params!r})
with s.recovery_fence() as fence:
    reserved=s.reserve(*p)
    assert reserved.recovery_generation == fence.generation == 1
    assert s.reserve(*p) == reserved
    try: s.reserve(p[0],uuid4(),*p[2:])
    except LedgerUnavailable: pass
    else: raise AssertionError('owner accepted')
    s.claim(*p)
    import psycopg
    with psycopg.connect(host={ledger_connections.business!r},dbname='ledger_fixture',
                         user='pitchlog_fixture_business_writer',
                         password='pitchlog-public-disposable-ledger-fixture'
                         ) as business:
        business.execute('CREATE TEMP TABLE business_attempt (value bigint)')
        business.execute('INSERT INTO business_attempt VALUES (%s)',
                         (reserved.generation,))
        business.rollback()
        fence.assert_held()
    from concurrent.futures import ThreadPoolExecutor
    def reserve(_): return s.reserve(*(uuid4() for _ in range(4))).generation
    with ThreadPoolExecutor(max_workers=3) as pool:
        concurrent=list(pool.map(reserve,range(3)))
    assert len(set(concurrent)) == 3
    fence.assert_held()
try: fence.assert_held()
except LedgerUnavailable: pass
else: raise AssertionError('expired fence accepted')
for operation in (s.reserve,s.claim):
    try: operation(*p)
    except LedgerUnavailable: pass
    else: raise AssertionError('consumed reservation reused')
assert s.reserve(*(uuid4() for _ in range(4))).generation > reserved.generation
print(reserved.generation)
"""
    generation = int(authority_database.client(code))
    with psycopg.connect(ledger_connections.business_admin) as connection:
        connection.execute("CREATE TEMP TABLE business_attempt (value bigint)")
        connection.execute("INSERT INTO business_attempt VALUES (%s)", (generation,))
        connection.rollback()
    with psycopg.connect(ledger_connections.endpoints.standby_dsn) as connection:
        row = connection.execute(
            "SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s)", params
        ).fetchone()
        assert row is not None and row[0] == generation and row[5:] == (True, False)


def test_real_authority_parallel_and_clean_restart(
    authority_database: AuthorityDatabase, ledger_connections: LedgerDatabase
) -> None:
    """authority再起動は保護された成功集合を再照合し、高水位を下げない。"""
    params = tuple(str(uuid4()) for _ in range(4))
    first = int(
        authority_database.client(f"""
p=tuple(UUID(v) for v in {params!r})
print(s.reserve(*p).generation)
""")
    )
    authority_database.stop()
    authority_database.start()
    assert (
        int(
            authority_database.client(f"""
p=tuple(UUID(v) for v in {params!r})
assert s.reserve(*p).generation == {first}
from concurrent.futures import ThreadPoolExecutor
def reserve(_): return s.reserve(*(uuid4() for _ in range(4))).generation
with ThreadPoolExecutor(max_workers=3) as pool:
    values=list(pool.map(reserve,range(6)))
assert len(set(values)) == 6
assert min(values) > {first}
print(max(values))
""")
        )
        > first
    )
    # 実RG1 close proof未接合のepoch更新は通常運転中も閉じたまま。
    assert (
        authority_database.client("""
try: s.advance_recovery_generation(1)
except LedgerUnavailable: print('CLOSED')
else: raise AssertionError('epoch opened')
""")
        == "CLOSED"
    )


def test_real_roles_and_business_observer_are_limited(
    authority_database: AuthorityDatabase, ledger_connections: LedgerDatabase
) -> None:
    """別UID拒否と直接DML/制御操作拒否、専用observerだけの権限を照合する。"""
    assert not authority_database.client("print('FORBIDDEN')", uid=20003, check=False)
    assert authority_database.probe("SELECT session_user,current_user") == (
        "pitchlog_ledger_identity_probe|pitchlog_ledger_identity_probe"
    )
    for statement in (
        "SELECT * FROM public.tenants",
        "INSERT INTO public.tenants DEFAULT VALUES",
        "UPDATE public.tenants SET enabled=false",
        "SELECT * FROM authn.login_attempt('x','x','x')",
    ):
        assert authority_database.probe(statement, refused=True) == "DENIED"
    endpoints = ledger_connections.endpoints
    for dsn, sql in (
        (endpoints.primary_dsn, "UPDATE pitchlog_ledger.highwater SET value=0"),
        (endpoints.primary_dsn, "SELECT * FROM pitchlog_ledger.reservations"),
        (endpoints.primary_dsn, "SELECT pitchlog_ledger.audit_page(0,256)"),
        (endpoints.primary_dsn, "SELECT pitchlog_ledger.confirm_state(1,0,0)"),
        (endpoints.primary_dsn, "SELECT pitchlog_ledger.advance_epoch(1)"),
        (endpoints.control_dsn, "SELECT pitchlog_ledger.epoch_fence()"),
        (endpoints.control_dsn, "DELETE FROM pitchlog_ledger.reservations"),
    ):
        with psycopg.connect(dsn) as connection:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(sql)
            connection.rollback()
    with psycopg.connect(ledger_connections.business_admin) as connection:
        # PostgreSQL既定PUBLIC権限は拡張/取消せず、新probeへの直接grantを拒否する。
        assert connection.execute(
            "SELECT has_function_privilege('pitchlog_ledger_identity_probe',"
            "'pg_catalog.pg_control_system()','EXECUTE')"
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT count(*) FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) a "
            "WHERE p.oid='pg_catalog.pg_control_system()'::regprocedure "
            "AND a.grantee=(SELECT oid FROM pg_roles WHERE "
            "rolname='pitchlog_ledger_identity_probe')"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT has_schema_privilege('pitchlog_ledger_identity_probe',"
            "'pitchlog_ledger_observer','USAGE')"
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT count(*) FROM pg_auth_members WHERE member IN ("
            "SELECT oid FROM pg_roles WHERE rolname LIKE 'pitchlog_ledger_identity_%')"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT has_table_privilege('pitchlog_ledger_identity_probe',"
            "'public.tenants','SELECT,INSERT,UPDATE,DELETE')"
        ).fetchone() == (False,)
        assert connection.execute(
            "SELECT has_function_privilege('pitchlog_ledger_identity_probe',"
            "'authn.login_attempt(text,text,text)','EXECUTE')"
        ).fetchone() == (False,)
        roles = connection.execute(
            "SELECT rolname,rolsuper,rolbypassrls,rolcreatedb,"
            "rolcreaterole,rolreplication "
            "FROM pg_roles WHERE rolname LIKE 'pitchlog_ledger_identity_%' "
            "ORDER BY rolname"
        ).fetchall()
        assert roles == [
            (name, False, False, False, False, False)
            for name in (
                "pitchlog_ledger_identity_owner",
                "pitchlog_ledger_identity_probe",
            )
        ]


def test_real_manifest_acl_and_function_owners(
    ledger_connections: LedgerDatabase,
) -> None:
    """全関数/所有role/search_pathを実カタログとmanifestで照合する。"""
    from pathlib import Path

    manifest = json.loads((Path(adapter.__file__).parent / "manifest.json").read_text())
    with psycopg.connect(ledger_connections.primary_admin) as connection:
        functions = connection.execute(
            "SELECT p.proname,r.rolname,p.prosecdef,p.proconfig,p.oid FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON "
            "r.oid=p.proowner WHERE n.nspname='pitchlog_ledger'"
        ).fetchall()
        assert len(functions) == len(manifest["functions"]) == 9
        for name, owner, security_definer, configuration, oid in functions:
            assert owner == "pitchlog_ledger_owner" and security_definer is True
            assert configuration == ["search_path=pg_catalog, pitchlog_ledger"]
            acl = connection.execute(
                "SELECT CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE "
                "pg_get_userbyid(x.grantee) END FROM pg_proc p CROSS JOIN LATERAL "
                "aclexplode(p.proacl) x WHERE p.oid=%s AND x.privilege_type='EXECUTE'",
                (oid,),
            ).fetchall()
            expected = {"pitchlog_ledger_owner"} | {
                "pitchlog_ledger_" + role
                for signature, allowed in manifest["functions"].items()
                if signature.split("(")[0] == name
                for role in allowed
            }
            assert {row[0] for row in acl} == expected


def test_real_control_barrier_changes_no_domain_values(
    ledger_connections: LedgerDatabase,
) -> None:
    """実CAS不一致は拒否し、同期barrier成功でもepoch/H/countを変えない。"""
    with psycopg.connect(ledger_connections.endpoints.control_dsn) as connection:
        before = connection.execute("SELECT pitchlog_ledger.identity()").fetchone()
        assert before is not None
        identity = before[0]
        expected = (
            identity["epoch"],
            identity["highwater"],
            identity["reservation_count"],
        )
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(
                "SELECT pitchlog_ledger.confirm_state(%s,%s,%s)",
                (expected[0], expected[1] + 1, expected[2]),
            )
        connection.rollback()
        assert connection.execute(
            "SELECT pitchlog_ledger.confirm_state(%s,%s,%s)", expected
        ).fetchone() == (1,)
        connection.commit()
        after = connection.execute("SELECT pitchlog_ledger.identity()").fetchone()
        assert after is not None
        assert (
            tuple(after[0][key] for key in ("epoch", "highwater", "reservation_count"))
            == expected
        )


def test_real_peer_stop_refuses_issuance_then_attaches_known_pair(
    authority_database: AuthorityDatabase, ledger_connections: LedgerDatabase
) -> None:
    """実peer不在を非同期へ降格せず、peer再起動後もjournal照合なしで再開しない。"""
    with psycopg.connect(ledger_connections.primary_admin) as connection:
        before = connection.execute(
            "SELECT value FROM pitchlog_ledger.highwater"
        ).fetchone()
    ledger_connections.standby_running(False)
    try:
        assert (
            authority_database.client("""
try: s.reserve(*(uuid4() for _ in range(4)))
except LedgerUnavailable: print('CLOSED')
else: raise AssertionError('missing peer accepted')
""")
            == "CLOSED"
        )
    finally:
        ledger_connections.standby_running(True)
    assert (
        authority_database.client("""
try: s.reserve(*(uuid4() for _ in range(4)))
except LedgerUnavailable: print('CLOSED')
else: raise AssertionError('peer restart silently accepted')
""")
        == "CLOSED"
    )
    with psycopg.connect(ledger_connections.primary_admin) as connection:
        assert (
            connection.execute("SELECT value FROM pitchlog_ledger.highwater").fetchone()
            == before
        )
    authority_database.stop()
    authority_database.start()
    assert (
        authority_database.client(
            "assert s.current_recovery_generation()==1; print('ATTACHED')"
        )
        == "ATTACHED"
    )


def test_real_pair_rollback_reconciles_from_protected_success_set(
    authority_database: AuthorityDatabase, ledger_connections: LedgerDatabase
) -> None:
    """両PGを実旧backupへ戻しても独立witnessの予約/claimを取り戻す。"""
    params = tuple(str(uuid4()) for _ in range(4))
    authority_database.copy_pair()
    authority_database.start()
    generation = int(
        authority_database.client(f"""
p=tuple(UUID(v) for v in {params!r})
r=s.reserve(*p)
s.claim(*p)
print(r.generation)
""")
    )
    authority_database.copy_pair(restore=True)
    authority_database.start()
    assert (
        authority_database.client(f"""
p=tuple(UUID(v) for v in {params!r})
for op in (s.reserve,s.claim):
    try: op(*p)
    except LedgerUnavailable: pass
    else: raise AssertionError('restored consumed generation reused')
assert s.reserve(*(uuid4() for _ in range(4))).generation > {generation}
print('RESTORED')
""")
        == "RESTORED"
    )
    with psycopg.connect(ledger_connections.endpoints.standby_dsn) as connection:
        row = connection.execute(
            "SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s)", params
        ).fetchone()
        assert row is not None and row[0] == generation and row[5:] == (True, False)


def test_real_replay_failure_is_unconfirmed_and_restart_reconciles(
    authority_database: AuthorityDatabase, ledger_connections: LedgerDatabase
) -> None:
    """実peer replay停止後の応答は未確定、再開時は同attemptだけ照合する。"""
    params = tuple(str(uuid4()) for _ in range(4))
    with psycopg.connect(
        ledger_connections.standby_admin, autocommit=True
    ) as connection:
        connection.execute("SELECT pg_wal_replay_pause()")
        try:
            assert (
                authority_database.client(f"""
p=tuple(UUID(v) for v in {params!r})
try: s.reserve(*p)
except LedgerOutcomeUnconfirmed: print('UNCONFIRMED')
else: raise AssertionError('unconfirmed reservation acknowledged')
""")
                == "UNCONFIRMED"
            )
            # clientの期限だけでなく、停止を維持したまま実authorityの閉状態を確認する。
            assert not authority_database.client(
                "print(s.current_recovery_generation())", check=False
            )
        finally:
            connection.execute("SELECT pg_wal_replay_resume()")
    authority_database.stop()
    authority_database.start()
    assert (
        authority_database.client(f"""
p=tuple(UUID(v) for v in {params!r})
r=s.reserve(*p)
assert s.reserve(*p)==r
print('RECONCILED')
""")
        == "RECONCILED"
    )


def test_real_unterminated_lease_blocks_live_and_restart(
    authority_database: AuthorityDatabase, ledger_connections: LedgerDatabase
) -> None:
    """業務終了不明の実leaseを自己判断で閉じず、live/再起動とも拒否する。"""
    assert (
        authority_database.client("""
import os
context=s.recovery_fence()
fence=context.__enter__()
assert fence.generation == 1
print('LEASE_HELD',flush=True)
os._exit(0)
""")
        == "LEASE_HELD"
    )
    assert not authority_database.client(
        "print(s.current_recovery_generation())", check=False
    )
    authority_database.stop()
    assert authority_database.start(check=False) is False
