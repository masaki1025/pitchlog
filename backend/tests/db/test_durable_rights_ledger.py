"""実peer主体/保護journal/同期PGを通すauthorityの接合を検査する。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from db_fixtures import _dsn_names

from pitchlog.durable_rights_ledger import adapter

from .durable_rights_ledger_support import (
    AuthorityDatabase,
    AuthorityResources,
    LedgerDatabase,
    docker,
    reserve_commit_failure,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture(scope="module")
def authority_resources() -> Iterator[AuthorityResources]:
    """独立シナリオごとの所有資源を一組ずつ保持する。"""
    resources = AuthorityResources()
    try:
        yield resources
    finally:
        resources.close()


@pytest.fixture
def authority_database(
    request: pytest.FixtureRequest, authority_resources: AuthorityResources
) -> AuthorityDatabase:
    """normal群を共有し、故障群は専用cluster/witnessへ直列に切り替える。"""
    if "dual_scenario" in request.fixturenames:
        return authority_resources.get(
            "dual:" + request.getfixturevalue("dual_scenario"), dual_peer=True
        )
    if "critical_scenario" in request.fixturenames:
        key = "critical:" + request.getfixturevalue("critical_scenario")
    elif "retention_scenario" in request.fixturenames:
        key = "retention:" + request.getfixturevalue("retention_scenario")
    else:
        key = (
            "fresh:" + request.getfixturevalue("fresh_scenario")
            if "fresh_scenario" in request.fixturenames
            else "normal"
        )
    return authority_resources.get(key)


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


def test_real_normal_admission_requires_original_database_and_legacy_refuses(
    authority_database: AuthorityDatabase, ledger_connections: LedgerDatabase
) -> None:
    """実同cluster/同postmasterの別DBと旧欠落genesisをstartup前に拒否する。"""
    from pathlib import Path

    from psycopg.conninfo import make_conninfo

    authority_database.stop()
    original_digest = authority_database.journal_digest()
    authority_database.prepare_legacy_genesis()
    legacy_digest = authority_database.journal_digest("legacy")
    try:
        assert authority_database.start(check=False) is False
        assert authority_database.journal_digest() == original_digest
        assert authority_database.journal_digest("legacy") == legacy_digest
    finally:
        authority_database.stop()
        authority_database.prepare_legacy_genesis(restore=True)
    authority_database.start()
    with psycopg.connect(
        ledger_connections.business_admin, autocommit=True
    ) as connection:
        connection.execute("CREATE DATABASE ledger_other")
    alternate = make_conninfo(ledger_connections.business_admin, dbname="ledger_other")
    ddl = (Path(adapter.__file__).parent / "business_identity.sql").read_text()
    # cluster roleは既存の実roleを使い、別DBへ同一正規observerだけを適用する。
    ddl = re.sub(r"^CREATE ROLE .*;\n", "", ddl, flags=re.MULTILINE)
    with psycopg.connect(alternate) as connection:
        connection.execute(ddl.encode())
    identity_query = (
        "SELECT pitchlog_ledger_observer.identity()->>'system_id',"
        "current_database(),"
        "pitchlog_ledger_observer.identity()->>'started_at'"
    )
    original = authority_database.probe(identity_query).split("|")
    other = authority_database.probe(identity_query, database="ledger_other").split("|")
    assert original[0] == other[0] and original[2] == other[2]
    assert original[1] == "ledger_fixture" and other[1] == "ledger_other"
    authority_database.stop()
    original_digest = authority_database.journal_digest()
    authority_database.switch_business_database("ledger_other")
    try:
        assert authority_database.start(check=False) is False
        assert authority_database.journal_digest() == original_digest
    finally:
        authority_database.stop()
        authority_database.switch_business_database("ledger_fixture")
    authority_database.start()
    assert (
        authority_database.client(
            "assert s.current_recovery_generation()==1; print('BOUND')"
        )
        == "BOUND"
    )


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
            assert configuration == ["search_path=pg_catalog, pitchlog_ledger, pg_temp"]
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


def _install_attacker_temp_tables(connection: psycopg.Connection) -> tuple:
    """呼出role所有の偽表とdefinerへの実ACLを作り、攻撃前提を成立させる。"""
    params = tuple(uuid4() for _ in range(4))
    connection.execute("CREATE TEMP TABLE state (singleton boolean,epoch bigint)")
    connection.execute("CREATE TEMP TABLE highwater (singleton boolean,value bigint)")
    connection.execute(
        "CREATE TEMP TABLE reservations (attempt_id uuid,tenant_id uuid,"
        "game_id uuid,start_request_id uuid,generation bigint,"
        "recovery_generation bigint,claimed boolean,quarantined boolean)"
    )
    connection.execute("INSERT INTO pg_temp.state VALUES(true,999)")
    connection.execute("INSERT INTO pg_temp.highwater VALUES(true,8888)")
    connection.execute(
        "INSERT INTO pg_temp.reservations VALUES(%s,%s,%s,%s,8888,999,false,false)",
        params,
    )
    # pg_tempはGRANTのschema名aliasではない。実namespaceへの有効USAGEを検証する。
    assert connection.execute(
        "SELECT has_schema_privilege('pitchlog_ledger_owner',"
        "pg_my_temp_schema(),'USAGE')"
    ).fetchone() == (True,)
    connection.execute(
        "GRANT ALL ON TABLE pg_temp.state,pg_temp.highwater,"
        "pg_temp.reservations TO pitchlog_ledger_owner"
    )
    connection.execute("SET LOCAL search_path=pg_catalog,pitchlog_ledger")
    # pg_tempを明示しない危険な解決では実際に偽表を読むことを確認する。
    assert connection.execute("SELECT epoch FROM state").fetchone() == (999,)
    assert connection.execute("SELECT value FROM highwater").fetchone() == (8888,)
    return params


def test_real_security_definers_resist_temp_shadowing_for_app_and_control(
    ledger_connections: LedgerDatabase,
) -> None:
    """PUBLIC TEMPを保持し、偽表にdefiner ACLがあっても全9関数は正規表を使う。"""
    with psycopg.connect(ledger_connections.primary_admin) as administrator:
        before = administrator.execute(
            "SELECT (SELECT epoch FROM pitchlog_ledger.state),"
            "(SELECT value FROM pitchlog_ledger.highwater),"
            "(SELECT count(*) FROM pitchlog_ledger.reservations)"
        ).fetchone()
        assert before is not None
        assert administrator.execute(
            "SELECT count(*) FROM pg_database d CROSS JOIN LATERAL "
            "aclexplode(COALESCE(d.datacl,acldefault('d',d.datdba))) a "
            "WHERE d.datname=current_database() AND a.grantee=0 "
            "AND a.privilege_type='TEMPORARY'"
        ).fetchone() == (1,)
    epoch, highwater, count = before
    with psycopg.connect(ledger_connections.endpoints.primary_dsn) as connection:
        fake = _install_attacker_temp_tables(connection)
        identity = connection.execute("SELECT pitchlog_ledger.identity()").fetchone()
        assert identity is not None
        assert (
            identity[0]["epoch"],
            identity[0]["highwater"],
            identity[0]["reservation_count"],
        ) == before
        assert connection.execute(
            "SELECT pitchlog_ledger.epoch_fence()"
        ).fetchone() == (epoch,)
        assert (
            connection.execute(
                "SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s)", fake
            ).fetchone()
            is None
        )
        params = tuple(uuid4() for _ in range(4))
        reserved = connection.execute(
            "SELECT * FROM pitchlog_ledger.reserve(%s,%s,%s,%s)", params
        ).fetchone()
        assert reserved is not None and reserved[:2] == (highwater + 1, epoch)
        claimed = connection.execute(
            "SELECT * FROM pitchlog_ledger.claim(%s,%s,%s,%s)", params
        ).fetchone()
        assert claimed is not None and claimed[:2] == (highwater + 1, epoch)
        assert claimed[5:] == (True, False)
        assert (
            connection.execute(
                "SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s)", params
            ).fetchone()
            == claimed
        )
        assert connection.execute("SELECT value FROM pg_temp.highwater").fetchone() == (
            8888,
        )
        assert connection.execute(
            "SELECT claimed FROM pg_temp.reservations"
        ).fetchone() == (False,)
        connection.rollback()
    with psycopg.connect(ledger_connections.endpoints.control_dsn) as connection:
        fake = _install_attacker_temp_tables(connection)
        assert connection.execute(
            "SELECT pitchlog_ledger.confirm_state(%s,%s,%s)", before
        ).fetchone() == (epoch,)
        page = connection.execute("SELECT pitchlog_ledger.audit_page(0,256)").fetchone()
        assert page is not None and all(
            row["attempt_id"] != str(fake[0]) for row in page[0]
        )
        assert connection.execute(
            "SELECT pitchlog_ledger.advance_epoch(%s)", (epoch,)
        ).fetchone() == (epoch + 1,)
        params = tuple(uuid4() for _ in range(4))
        with pytest.raises(psycopg.errors.RaiseException), connection.transaction():
            connection.execute(
                "SELECT * FROM pitchlog_ledger.reconcile(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (*params, highwater + 1, 999, False, True, highwater),
            )
        row = connection.execute(
            "SELECT * FROM pitchlog_ledger.reconcile(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (*params, highwater + 1, epoch + 1, False, True, highwater),
        ).fetchone()
        assert (
            row is not None
            and row[:2] == (highwater + 1, epoch + 1)
            and row[5:] == (False, True)
        )
        identity = connection.execute("SELECT pitchlog_ledger.identity()").fetchone()
        assert identity is not None
        assert (
            identity[0]["epoch"],
            identity[0]["highwater"],
            identity[0]["reservation_count"],
        ) == (epoch + 1, highwater + 1, count + 1)
        assert connection.execute("SELECT epoch FROM pg_temp.state").fetchone() == (
            999,
        )
        assert connection.execute("SELECT value FROM pg_temp.highwater").fetchone() == (
            8888,
        )
        assert connection.execute(
            "SELECT count(*) FROM pg_temp.reservations"
        ).fetchone() == (1,)
        connection.rollback()
    with psycopg.connect(ledger_connections.primary_admin) as administrator:
        assert (
            administrator.execute(
                "SELECT (SELECT epoch FROM pitchlog_ledger.state),"
                "(SELECT value FROM pitchlog_ledger.highwater),"
                "(SELECT count(*) FROM pitchlog_ledger.reservations)"
            ).fetchone()
            == before
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


@pytest.mark.parametrize(
    "fresh_scenario",
    ["success_concurrent", "restore_zero", "ack_loss", "body_exception", "past_intent"],
)
def test_real_fresh_activation_boundary(
    fresh_scenario: str,
    authority_database: AuthorityDatabase,
    ledger_connections: LedgerDatabase,
) -> None:
    """実journal/peer/PGの一度限り証拠、同居、応答喪失と旧0復元拒否を検査する。"""
    if fresh_scenario == "success_concurrent":
        _fresh_activation_success_and_concurrency(
            authority_database, ledger_connections
        )
    elif fresh_scenario == "restore_zero":
        authority_database.copy_pair()
        authority_database.start()
        assert (
            authority_database.client("""
with s.fresh_activation() as (att,fence):
    assert att.highwater == att.reservation_count == 0
    assert fence.generation == att.pair_epoch == 1
print('ACTIVATED')
""")
            == "ACTIVATED"
        )
        authority_database.copy_pair(restore=True)
        authority_database.start()
        with psycopg.connect(ledger_connections.primary_admin) as connection:
            assert connection.execute(
                "SELECT value FROM pitchlog_ledger.highwater"
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*) FROM pitchlog_ledger.reservations"
            ).fetchone() == (0,)
        assert (
            authority_database.client("""
try:
    with s.fresh_activation(): raise AssertionError('old zero restored as fresh')
except LedgerUnavailable: pass
assert s.reserve(*(uuid4() for _ in range(4))).generation == 1
print('PAST_ACTIVATION_CLOSED')
""")
            == "PAST_ACTIVATION_CLOSED"
        )
        assert authority_database.event_counts().get("activation_open") == 1
    elif fresh_scenario in ("ack_loss", "body_exception"):
        if fresh_scenario == "ack_loss":
            operation = """
import socket
with s._channel() as lost:
    lost.sendall(b'{"operation":"fresh_activation_open"}\\n')
    lost.shutdown(socket.SHUT_RD)
    await_closed()
"""
        else:
            operation = """
try:
    with s.fresh_activation() as (att,fence):
        assert fence.generation == 1
        raise RuntimeError('test business result unconfirmed')
except RuntimeError: pass
await_closed()
"""
        assert (
            authority_database.client(
                """
from time import monotonic,sleep
def await_closed():
    deadline=monotonic()+6
    while monotonic()<deadline:
        try: s.current_recovery_generation()
        except LedgerUnavailable: return
        sleep(.01)
    raise AssertionError('unterminated activation served as normal')
"""
                + operation
                + """
try:
    with s.fresh_activation(): raise AssertionError('in-doubt fresh repeated')
except LedgerUnavailable: pass
print('IN_DOUBT_CLOSED')
"""
            )
            == "IN_DOUBT_CLOSED"
        )
        counts = authority_database.event_counts()
        assert counts.get("activation_open") == 1 and counts.get("lease_close", 0) == 0
        authority_database.stop()
        assert authority_database.start(check=False) is False
    else:
        assert fresh_scenario == "past_intent"
        assert (
            authority_database.client("""
p=tuple(uuid4() for _ in range(4))
s.reserve(*p)
s.claim(*p)
try:
    with s.fresh_activation(): raise AssertionError('used history accepted as fresh')
except LedgerUnavailable: pass
print('INTENT_CLOSED')
""")
            == "INTENT_CLOSED"
        )
        assert authority_database.event_counts().get("activation_open", 0) == 0


def _fresh_activation_success_and_concurrency(
    authority: AuthorityDatabase,
    database: LedgerDatabase,
) -> None:
    """同じ実channelのmetadata/fenceを保持し、別主体の排他lock拒否を照合する。"""
    import select

    code = """
import json,sys
from dataclasses import asdict,FrozenInstanceError
from concurrent.futures import ThreadPoolExecutor
from pitchlog.durable_rights_ledger import adapter
with s._channel() as raw:
    try: adapter._request(raw,{'operation':'fresh_activation_open','highwater':0})
    except LedgerUnavailable: pass
    else: raise AssertionError('caller proof accepted')
with s.recovery_fence():
    try:
        with s.fresh_activation(): raise AssertionError('another active lease accepted')
    except LedgerUnavailable: pass
with s.fresh_activation() as (att,fence):
    assert type(att) is FreshActivationAttestation
    assert att.pair_epoch == fence.generation == 1
    assert att.highwater == att.reservation_count == 0
    assert att.activation_ordinal > 0
    try: att.database='forged'
    except FrozenInstanceError: pass
    else: raise AssertionError('attestation mutable')
    print(json.dumps(asdict(att),default=str),flush=True)
    assert sys.stdin.readline().strip() == 'CONTINUE'
    fence.assert_held()
    def issue(_):
        params=tuple(uuid4() for _ in range(4))
        result=s.reserve(*params)
        s.claim(*params)
        return result.generation
    with ThreadPoolExecutor(max_workers=3) as pool:
        values=list(pool.map(issue,range(3)))
    assert len(set(values)) == 3
    assert att.highwater == att.reservation_count == 0
    fence.assert_held()
    try:
        with s.fresh_activation(): raise AssertionError('second fresh accepted')
    except LedgerUnavailable: pass
try: fence.assert_held()
except LedgerUnavailable: pass
else: raise AssertionError('expired activation fence accepted')
try:
    with s.fresh_activation(): raise AssertionError('past activation accepted')
except LedgerUnavailable: pass
print('FRESH_AND_D4',flush=True)
"""
    process = authority.client_process(code)
    try:
        assert process.stdout is not None
        readable, _, _ = select.select([process.stdout], [], [], 15)
        assert readable, "real fresh client did not acquire lease"
        line = process.stdout.readline()
        assert line.startswith("{"), "real fresh client did not return metadata"
        att = json.loads(line)
        actual = authority.probe(
            "SELECT pitchlog_ledger_observer.identity()->>'system_id',"
            "current_database(),"
            "pitchlog_ledger_observer.identity()->>'started_at'"
        ).split("|")
        assert (
            att["business_system_id"],
            att["database"],
            att["postmaster_started_at"],
        ) == tuple(actual)
        with psycopg.connect(database.primary_admin) as controller:
            controller.execute("SET lock_timeout='150ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                controller.execute(
                    "SELECT epoch FROM pitchlog_ledger.state WHERE singleton FOR UPDATE"
                )
            controller.rollback()
        output, error = process.communicate("CONTINUE\n", timeout=20)
        assert process.returncode == 0, "real fresh client failed: " + error[-1200:]
        assert output.strip() == "FRESH_AND_D4"
        assert authority.event_counts().get("activation_open") == 1
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)


def _dual_raw_refused(
    authority: AuthorityDatabase,
    role: str,
    request: dict[str, object],
    *,
    uid: int,
    gid: int | None = None,
    supplemental_generation: bool = False,
    dead_listener: bool = False,
) -> None:
    """公開clientの事前拒否を迂回し、実listener/peercredの拒否を観測する。"""
    assert role in {"generation", "fresh_controller"}
    path = (
        "/control/run/service.sock"
        if role == "generation"
        else "/control/run/controller.sock"
    )
    command = authority.command(uid=uid, gid=gid)
    if supplemental_generation:
        # 負例だけでFS group到達性を与え、kernelのprimary GID照合を実証する。
        command[1:1] = ["--group-add", "20002"]
    code = f"""
import socket,json
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
    c.settimeout(2)
    try:
        c.connect({path!r})
    except OSError:
        assert {dead_listener!r},'expected live listener was inaccessible'
        reply=b''
    else:
        try:
            c.sendall((json.dumps({request!r})+'\\n').encode())
            reply=c.recv(4096)
        except ConnectionError:
            reply=b''
    assert not reply or json.loads(reply)=={{'status':'unavailable'}}
print('RAW_REFUSED')
"""
    assert docker(*command, "-c", code) == "RAW_REFUSED"


@pytest.mark.parametrize("dual_scenario", ["simultaneous"])
def test_real_dual_peer_fresh_and_generation_share_one_worker(
    authority_database: AuthorityDatabase,
    ledger_connections: LedgerDatabase,
    dual_scenario: str,
) -> None:
    """別UID fresh lease中に実actorが予約/claimし、同じepoch/単一journalを使う。"""
    import select

    assert dual_scenario == "simultaneous"
    authority = authority_database
    process = authority.client_process(
        """
import sys
with s.fresh_activation() as (att,fence):
    assert att.pair_epoch==1 and att.highwater==att.reservation_count==0
    print('DUAL_FRESH_READY',flush=True)
    assert sys.stdin.readline().strip()=='CHECK'
    fence.assert_held()
    print('SAME_CHANNEL_FENCE_HELD',flush=True)
print('DUAL_FRESH_CLOSED',flush=True)
""",
        controller=True,
    )
    try:
        assert process.stdout is not None and process.stdin is not None
        ready, _, _ = select.select([process.stdout], [], [], 15)
        assert ready and process.stdout.readline().strip() == "DUAL_FRESH_READY"
        assert (
            authority.client("""
params=tuple(uuid4() for _ in range(4))
with s.recovery_fence() as fence:
    assert fence.generation==1
    reservation=s.reserve(*params)
    assert reservation.generation==1 and reservation.recovery_generation==1
    s.claim(*params)
    fence.assert_held()
print('GENERATION_CLAIMED')
""")
            == "GENERATION_CLAIMED"
        )
        with psycopg.connect(ledger_connections.primary_admin) as contender:
            with pytest.raises(psycopg.errors.LockNotAvailable):
                contender.execute(
                    "SELECT epoch FROM pitchlog_ledger.state FOR UPDATE NOWAIT"
                )
        process.stdin.write("CHECK\n")
        process.stdin.flush()
        ready, _, _ = select.select([process.stdout], [], [], 10)
        assert ready and process.stdout.readline().strip() == "SAME_CHANNEL_FENCE_HELD"
        process.communicate(timeout=10)
        assert process.returncode == 0
        success = _ledger_retention_snapshot(ledger_connections.primary_admin)
        assert success[0] == len(success[1]) == 1 and success[1][0][6:] == (True, False)
        assert _ledger_retention_snapshot(ledger_connections.standby_admin) == success
        events = authority.event_counts()
        assert events["activation_open"] == 1 and events["lease_open"] == 1
        assert events["lease_close"] == 2
        assert (
            authority.controller_client("""
try:
    with s.fresh_activation(): raise AssertionError('fresh repeated')
except LedgerUnavailable: print('PAST_ACTIVATION_REFUSED')
""")
            == "PAST_ACTIVATION_REFUSED"
        )
        assert authority.client("print(s.current_recovery_generation())") == "1"
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)


@pytest.mark.parametrize("dual_scenario", ["rejections"])
def test_real_dual_peer_operations_and_kernel_subjects_are_closed(
    authority_database: AuthorityDatabase,
    ledger_connections: LedgerDatabase,
    dual_scenario: str,
) -> None:
    """相互操作/偽role/別UID/別primary GIDはPG/journal変化なしに拒否する。"""
    assert dual_scenario == "rejections"
    authority = authority_database
    journal = authority.journal_state()
    counts = authority.event_counts()
    before = _ledger_retention_snapshot(ledger_connections.primary_admin)
    for role, uid, operations in (
        (
            "generation",
            20002,
            ("fresh_activation_open", "advance", "fence_check", "fence_close"),
        ),
        (
            "fresh_controller",
            20004,
            (
                "epoch",
                "reserve",
                "claim",
                "fence_open",
                "fence_check",
                "fence_close",
                "advance",
            ),
        ),
    ):
        for operation in operations:
            _dual_raw_refused(authority, role, {"operation": operation}, uid=uid)
    _dual_raw_refused(
        authority,
        "generation",
        {"operation": "fresh_activation_open", "role": "fresh_controller"},
        uid=20002,
    )
    _dual_raw_refused(
        authority, "generation", {"operation": "epoch"}, uid=20005, gid=20002
    )
    _dual_raw_refused(
        authority,
        "generation",
        {"operation": "epoch"},
        uid=20002,
        gid=20005,
        supplemental_generation=True,
    )
    # endpoint constructorも、相手endpointを同じ権利へ読み替えない。
    assert (
        authority.client("""
try: DurableLedger(Path('/control/public/controller-endpoint.json'))
except LedgerUnavailable: print('OTHER_ENDPOINT_REFUSED')
else: raise AssertionError('controller endpoint accepted by generation UID')
""")
        == "OTHER_ENDPOINT_REFUSED"
    )
    assert (
        authority.controller_client("""
try: DurableLedger(Path('/control/public/endpoint.json'))
except LedgerUnavailable: print('OTHER_ENDPOINT_REFUSED')
else: raise AssertionError('generation endpoint accepted by controller UID')
""")
        == "OTHER_ENDPOINT_REFUSED"
    )
    assert authority.journal_state() == journal and authority.event_counts() == counts
    assert _ledger_retention_snapshot(ledger_connections.primary_admin) == before
    assert _ledger_retention_snapshot(ledger_connections.standby_admin) == before


@pytest.mark.parametrize("dual_scenario", ["disconnect"])
def test_real_dual_peer_controller_disconnect_blocks_both_and_restart(
    authority_database: AuthorityDatabase,
    ledger_connections: LedgerDatabase,
    dual_scenario: str,
) -> None:
    """controller未終端leaseで共有blockedを立て、actor/再起動を閉じる。"""
    assert dual_scenario == "disconnect"
    authority = authority_database
    assert (
        authority.controller_client("""
import os
with s.fresh_activation():
    print('OPEN_THEN_DISCONNECTED',flush=True)
    os._exit(0)
""")
        == "OPEN_THEN_DISCONNECTED"
    )
    assert (
        authority.client("""
import time
deadline=time.monotonic()+5
while True:
    try: s.current_recovery_generation()
    except LedgerUnavailable: break
    assert time.monotonic()<deadline,'shared worker did not fail closed'
    time.sleep(0.05)
try: s.reserve(*(uuid4() for _ in range(4)))
except LedgerUnavailable: print('SHARED_BLOCKED')
else: raise AssertionError('actor issued after controller disconnect')
""")
        == "SHARED_BLOCKED"
    )
    assert authority.event_counts().get("lease_close", 0) == 0
    assert _ledger_retention_snapshot(ledger_connections.primary_admin) == (0, ())
    authority.stop()
    assert authority.start(check=False) is False


@pytest.mark.parametrize("dual_scenario", ["startup-partial", "database-peer-mismatch"])
def test_real_dual_peer_partial_endpoint_publish_never_becomes_ready(
    authority_database: AuthorityDatabase,
    ledger_connections: LedgerDatabase,
    dual_scenario: str,
) -> None:
    """第2endpoint配置の実失敗は両端点を閉じ、generationだけでreadyにしない。"""
    authority = authority_database
    before = _ledger_retention_snapshot(ledger_connections.primary_admin)
    counts = authority.event_counts()
    authority.stop()
    mutation = (
        "value['peers'][1]['endpoint_path']='/control/unprovided/controller-endpoint.json'"
        if dual_scenario == "startup-partial"
        else "value['database_uid']=20006;value['database_gid']=20006"
    )
    code = (
        """
from pathlib import Path
from pitchlog.durable_rights_ledger.authority import _config,_write_root_json
p=Path('/control/settings/config.json')
value=_config(p)
"""
        + mutation
        + "\n"
        + """
_write_root_json(p,value,0o640,value['authority_gid'])
"""
    )
    docker(*authority.command(root=True), "-c", code)
    assert authority.start(check=False) is False
    _dual_raw_refused(
        authority, "generation", {"operation": "epoch"}, uid=20002, dead_listener=True
    )
    _dual_raw_refused(
        authority,
        "fresh_controller",
        {"operation": "fresh_activation_open"},
        uid=20004,
        dead_listener=True,
    )
    assert _ledger_retention_snapshot(ledger_connections.primary_admin) == before
    after = authority.event_counts()
    for event in ("intent", "confirmed", "activation_open", "lease_open"):
        assert after.get(event, 0) == counts.get(event, 0)


@pytest.mark.parametrize(
    "critical_scenario",
    (
        "reserve_commit_abort",
        "fresh_close_ack_loss",
        "fresh_close_kernel_write_refused",
    ),
)
def test_real_critical_journal_commit_boundaries(
    critical_scenario: str,
    authority_database: AuthorityDatabase,
    ledger_connections: LedgerDatabase,
) -> None:
    """実INTENT後のCOMMIT拒否と、実終端後のACK未読を専用pairで検査する。"""
    if critical_scenario == "reserve_commit_abort":
        _reserve_commit_abort_then_quarantine(authority_database, ledger_connections)
    elif critical_scenario == "fresh_close_ack_loss":
        _fresh_close_ack_loss_after_durable_end(authority_database)
    else:
        assert critical_scenario == "fresh_close_kernel_write_refused"
        _fresh_close_kernel_write_refused(authority_database)


def _reserve_commit_abort_then_quarantine(
    authority: AuthorityDatabase, database: LedgerDatabase
) -> None:
    """実DML/INTENT後の取消を隔離予約へ復旧し、実standbyでも非再利用を検査する。"""
    params = tuple(uuid4() for _ in range(4))
    wire_params = tuple(str(value) for value in params)
    with reserve_commit_failure(database) as fault:
        assert (
            authority.client(f"""
p=tuple(UUID(v) for v in {wire_params!r})
try: s.reserve(*p)
except LedgerOutcomeUnconfirmed: pass
else: raise AssertionError('aborted COMMIT acknowledged as reserved')
try: s.current_recovery_generation()
except LedgerUnavailable: pass
else: raise AssertionError('pending INTENT did not close live authority')
print('ABORT_UNCONFIRMED_AND_CLOSED')
""")
            == "ABORT_UNCONFIRMED_AND_CLOSED"
        )
        assert fault.observed() == (1, 1, 1, 1)
        counts = authority.event_counts()
        assert counts.get("intent") == 1
        assert counts.get("confirmed", 0) == counts.get("quarantined", 0) == 0
        # 取引内では予約1/highwater1に実到達したが、PGはCOMMIT前に全取消した。
        with psycopg.connect(database.primary_admin) as observer:
            assert observer.execute(
                "SELECT (SELECT value FROM pitchlog_ledger.highwater),"
                "(SELECT count(*) FROM pitchlog_ledger.reservations)"
            ).fetchone() == (0, 0)
    # 故障triggerを撤去してから同じjournalを通常startupへ渡す。
    authority.stop()
    authority.start()
    expected = (1, 1, *params[1:], False, True)
    with psycopg.connect(database.primary_admin) as observer:
        assert (
            observer.execute(
                "SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s)", params
            ).fetchone()
            == expected
        )
        assert observer.execute(
            "SELECT value FROM pitchlog_ledger.highwater"
        ).fetchone() == (1,)
    counts = authority.event_counts()
    assert counts.get("intent") == counts.get("quarantined") == 1
    assert counts.get("confirmed", 0) == 0
    assert (
        authority.client(f"""
p=tuple(UUID(v) for v in {wire_params!r})
for operation in (s.reserve,s.claim):
    try: operation(*p)
    except LedgerUnavailable: pass
    else: raise AssertionError('quarantined generation returned to unused')
assert s.current_recovery_generation()==1
assert s.reserve(*(uuid4() for _ in range(4))).generation==2
print('QUARANTINED_AND_NOT_REUSED')
""")
        == "QUARANTINED_AND_NOT_REUSED"
    )
    counts = authority.event_counts()
    assert counts.get("intent") == 2 and counts.get("confirmed") == 1
    assert counts.get("quarantined") == 1
    # primaryの停止後も、実指定standbyに隔離行と次のhighwaterが残る。
    authority.stop()
    docker("stop", "--time", "3", database.primary)
    with psycopg.connect(database.standby_admin) as observer:
        assert observer.execute("SELECT pg_is_in_recovery()").fetchone() == (True,)
        assert (
            observer.execute(
                "SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s)", params
            ).fetchone()
            == expected
        )
        assert observer.execute(
            "SELECT (SELECT value FROM pitchlog_ledger.highwater),"
            "(SELECT count(*) FROM pitchlog_ledger.reservations)"
        ).fetchone() == (2, 2)


def _fresh_close_ack_loss_after_durable_end(authority: AuthorityDatabase) -> None:
    """実close要求後にACKを読まず、耐久終了を未終端へ改変しないことを検査する。"""
    import select
    from time import monotonic, sleep

    code = """
import socket,sys
from pitchlog.durable_rights_ledger import adapter
with s._channel() as channel:
    att=adapter._activation_from(
        adapter._request(channel,{'operation':'fresh_activation_open'},mutation=True))
    assert att.highwater==att.reservation_count==0 and att.pair_epoch==1
    assert adapter._request(channel,{'operation':'fence_check'}) is None
    channel.sendall(b'{"operation":"fence_close"}\\n')
    channel.shutdown(socket.SHUT_RD)
    print('CLOSE_SENT_ACK_UNREAD',flush=True)
    assert sys.stdin.readline().strip()=='FINISH'
print('CHANNEL_CLOSED_WITHOUT_ACK',flush=True)
"""
    process = authority.client_process(code)
    try:
        assert process.stdout is not None
        readable, _, _ = select.select([process.stdout], [], [], 15)
        assert readable, "実close送信の期限超過"
        assert process.stdout.readline().strip() == "CLOSE_SENT_ACK_UNREAD"
        deadline = monotonic() + 6
        while authority.event_counts().get("lease_close", 0) != 1:
            assert monotonic() < deadline, "ACK未読のcloseが実終端へ到達しない"
            sleep(0.05)
        # 実mutexを再取得するepoch要求は、append/fsync終了後の閉鎖していない状態を照合。
        assert (
            authority.client("assert s.current_recovery_generation()==1; print('LIVE')")
            == "LIVE"
        )
        output, _ = process.communicate("FINISH\n", timeout=10)
        assert process.returncode == 0, "実peer clientのclose ACK未読試験が失敗"
        assert output.strip() == "CHANNEL_CLOSED_WITHOUT_ACK"
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
    counts = authority.event_counts()
    assert counts.get("activation_open") == counts.get("lease_close") == 1
    assert counts.get("intent", 0) == 0
    authority.stop()
    authority.start()
    assert authority.event_counts() == {
        **counts,
        "attached": counts.get("attached", 0) + 1,
    }
    assert (
        authority.client("""
try:
    with s.fresh_activation(): raise AssertionError('past activation reopened as fresh')
except LedgerUnavailable: pass
assert s.current_recovery_generation()==1
print('DURABLE_CLOSE_RETAINED')
""")
        == "DURABLE_CLOSE_RETAINED"
    )
    after = authority.event_counts()
    assert after.get("activation_open") == after.get("lease_close") == 1
    assert after.get("intent", 0) == 0


def _fresh_close_kernel_write_refused(authority: AuthorityDatabase) -> None:
    """実workerのfile-size上限でclose書込みを拒否し、未終端を維持する。"""
    import select

    code = """
import select,sys
from pitchlog.durable_rights_ledger import adapter
with s._channel() as channel:
    att=adapter._activation_from(
        adapter._request(channel,{'operation':'fresh_activation_open'},mutation=True))
    assert att.highwater==att.reservation_count==0 and att.pair_epoch==1
    assert adapter._request(channel,{'operation':'fence_check'}) is None
    print('FRESH_HELD_BEFORE_LIMIT',flush=True)
    while not select.select([sys.stdin],[],[],.1)[0]:
        assert adapter._request(channel,{'operation':'fence_check'}) is None
    assert sys.stdin.readline().strip()=='CLOSE'
    try: adapter._request(channel,{'operation':'fence_close'},mutation=True)
    except LedgerOutcomeUnconfirmed: print('KERNEL_CLOSE_UNCONFIRMED',flush=True)
    else: raise AssertionError('kernel-refused close acknowledged')
"""
    process = authority.client_process(code)
    try:
        assert process.stdout is not None
        readable, _, _ = select.select([process.stdout], [], [], 15)
        assert readable, "limit前の実fresh openが期限超過"
        assert process.stdout.readline().strip() == "FRESH_HELD_BEFORE_LIMIT"
        before = authority.journal_state()
        counts = authority.event_counts()
        assert counts.get("activation_open") == 1
        assert counts.get("lease_close", 0) == counts.get("intent", 0) == 0
        limited = authority.limit_worker_journal_growth(before[0])
        assert limited["worker_ppid"] == 1
        assert limited["worker_uid"] == limited["caller_uid"] == 20001
        assert limited["journal_size"] == before[0]
        assert limited["limited_limits"] == [before[0], limited["original_limits"][1]]
        output, _ = process.communicate("CLOSE\n", timeout=10)
        assert process.returncode == 0, "実closeの未確定応答を受け取れない"
        assert output.strip() == "KERNEL_CLOSE_UNCONFIRMED"
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
    # fsync故障全般の再現ではない。今回は新close frameの最初の書込みが拒否された。
    assert authority.journal_state() == before
    assert authority.event_counts() == counts
    assert not authority.client("print(s.current_recovery_generation())", check=False)
    authority.stop()
    original_soft = limited["original_limits"][0]
    assert authority.fresh_process_file_size_limit() == original_soft
    # 新processの元limitでも実未終端検査で拒否する。journalの補修/close追記なし。
    assert authority.start(check=False) is False
    assert authority.journal_state() == before
    assert authority.event_counts() == counts


def _ledger_retention_snapshot(
    dsn: str,
) -> tuple[int, tuple[tuple[object, ...], ...]]:
    """所有fixture内の有限な全予約行/全列とhighwaterを独立読取する。"""
    with psycopg.connect(dsn) as observer:
        highwater = observer.execute(
            "SELECT value FROM pitchlog_ledger.highwater"
        ).fetchone()
        assert highwater is not None and type(highwater[0]) is int
        rows = observer.execute(
            "SELECT * FROM pitchlog_ledger.reservations ORDER BY generation"
        ).fetchall()
        return highwater[0], tuple(rows)


def _acknowledged_retention_set(
    authority: AuthorityDatabase, database: LedgerDatabase
) -> tuple[int, tuple[tuple[object, ...], ...]]:
    """正規clientのreserve/claim成功2組を別の実DB観測へ固定する。"""
    assert (
        authority.client("""
for generation in (1,2):
    params=tuple(uuid4() for _ in range(4))
    assert s.reserve(*params).generation==generation
    s.claim(*params)
print('TWO_CLAIMED_ACKNOWLEDGED')
""")
        == "TWO_CLAIMED_ACKNOWLEDGED"
    )
    success = _ledger_retention_snapshot(database.primary_admin)
    assert success[0] == len(success[1]) == 2
    assert [row[4] for row in success[1]] == [1, 2]
    assert all(row[6:] == (True, False) for row in success[1])
    assert _ledger_retention_snapshot(database.standby_admin) == success
    return success


def _assert_retention_issuance_refused(authority: AuthorityDatabase) -> None:
    """実clientで新発行を拒否し、常拒否APIを成功へ読み替えない。"""
    assert (
        authority.client("""
try: s.reserve(*(uuid4() for _ in range(4)))
except LedgerUnavailable: print('NEW_ISSUANCE_REFUSED')
else: raise AssertionError('unsafe new issuance acknowledged')
""")
        == "NEW_ISSUANCE_REFUSED"
    )


@pytest.mark.parametrize(
    "retention_scenario",
    (
        "promote_with_primary_alive",
        "promote_after_primary_stopped",
        "old_zero_pair_and_witness_lost",
        "business_only_two_restores",
    ),
)
def test_real_retention_faults_close_and_preserve_success(
    retention_scenario: str,
    authority_database: AuthorityDatabase,
    ledger_connections: LedgerDatabase,
) -> None:
    """実昇格/保全喪失/業務復元の安全閉鎖と既成功集合保持だけを検査する。"""
    if retention_scenario == "old_zero_pair_and_witness_lost":
        authority_database.copy_pair()
        authority_database.start()
    success = _acknowledged_retention_set(authority_database, ledger_connections)
    counts = authority_database.event_counts()
    journal = authority_database.journal_state()
    if retention_scenario == "old_zero_pair_and_witness_lost":
        _old_zero_pair_and_witness_lost(authority_database, ledger_connections)
        return
    if retention_scenario == "business_only_two_restores":
        _business_only_two_restores(
            authority_database, ledger_connections, success, counts, journal
        )
        return
    if retention_scenario == "promote_after_primary_stopped":
        docker("stop", "--time", "3", ledger_connections.primary)
        assert (
            docker(
                "inspect", "--format", "{{.State.Running}}", ledger_connections.primary
            )
            == "false"
        )
    else:
        assert retention_scenario == "promote_with_primary_alive"
        assert (
            docker(
                "inspect", "--format", "{{.State.Running}}", ledger_connections.primary
            )
            == "true"
        )
        with psycopg.connect(ledger_connections.primary_admin) as old_primary:
            assert old_primary.execute("SELECT pg_is_in_recovery()").fetchone() == (
                False,
            )
    ledger_connections.promote_standby()
    # 正規の全域closeProof/epoch前進は未提供。実昇格だけで発行許可を作らない。
    _assert_retention_issuance_refused(authority_database)
    assert authority_database.event_counts() == counts
    assert authority_database.journal_state() == journal
    if retention_scenario == "promote_with_primary_alive":
        assert _ledger_retention_snapshot(ledger_connections.primary_admin) == success
    assert _ledger_retention_snapshot(ledger_connections.standby_admin) == success


def _old_zero_pair_and_witness_lost(
    authority: AuthorityDatabase, database: LedgerDatabase
) -> None:
    """実成功後の両台帳を古0へ復元し、witness喪失時の再enrollを拒否する。"""
    preserved = authority.witness_files()
    authority.copy_pair(restore=True)
    assert _ledger_retention_snapshot(database.primary_admin) == (0, ())
    assert _ledger_retention_snapshot(database.standby_admin) == (0, ())
    assert authority.witness_files() == preserved
    authority.lose_witness()
    assert authority.witness_files(preserved=True) == preserved
    assert authority.witness_path_missing()
    assert authority.start(check=False) is False
    _assert_retention_issuance_refused(authority)
    assert (
        authority.client("""
try:
    with s.fresh_activation(): raise AssertionError('lost witness reenrolled')
except LedgerUnavailable: print('NO_AUTOMATIC_FRESH_ENROLLMENT')
""")
        == "NO_AUTOMATIC_FRESH_ENROLLMENT"
    )
    assert authority.witness_path_missing()
    assert authority.witness_files(preserved=True) == preserved
    assert _ledger_retention_snapshot(database.primary_admin) == (0, ())
    assert _ledger_retention_snapshot(database.standby_admin) == (0, ())


def _business_only_two_restores(
    authority: AuthorityDatabase,
    database: LedgerDatabase,
    success: tuple[int, tuple[tuple[object, ...], ...]],
    counts: dict[str, int],
    journal: tuple[int, str],
) -> None:
    """実business物理復元2回を台帳/保護journalの全保持と分けて照合する。"""
    import select

    identity_sql = (
        "SELECT pitchlog_ledger_observer.identity()->>'system_id',current_database(),"
        "pitchlog_ledger_observer.identity()->>'started_at'"
    )
    original = authority.probe(identity_sql).split("|")
    authority.backup_business()
    assert authority.probe(identity_sql).split("|") == original
    # 起動拒否で旧socketが消えても、元の実clientの新発行呼出し自体を検証する。
    process = authority.client_process("""
import sys
print('ORIGINAL_CLIENT_READY',flush=True)
for iteration in (1,2):
    assert sys.stdin.readline().strip()=='TRY'
    try: s.reserve(*(uuid4() for _ in range(4)))
    except LedgerUnavailable: print('RESTORE_REFUSED_'+str(iteration),flush=True)
    else: raise AssertionError('restored business allowed new issuance')
""")
    try:
        assert process.stdout is not None and process.stdin is not None
        ready, _, _ = select.select([process.stdout], [], [], 15)
        assert ready and process.stdout.readline().strip() == "ORIGINAL_CLIENT_READY"
        previous = original
        for iteration in (1, 2):
            authority.restore_business()
            actual = authority.probe(identity_sql).split("|")
            assert actual[:2] == original[:2]
            assert actual[2] != original[2] and actual[2] != previous[2]
            previous = actual
            process.stdin.write("TRY\n")
            process.stdin.flush()
            ready, _, _ = select.select([process.stdout], [], [], 15)
            assert ready and process.stdout.readline().strip() == (
                "RESTORE_REFUSED_" + str(iteration)
            )
            assert _ledger_retention_snapshot(database.primary_admin) == success
            assert _ledger_retention_snapshot(database.standby_admin) == success
            assert authority.journal_state() == journal
            assert authority.event_counts() == counts
            authority.stop()
            assert authority.start(check=False) is False
            assert authority.journal_state() == journal
            assert authority.event_counts() == counts
        process.communicate(timeout=5)
        assert process.returncode == 0, "実復元clientの拒否確認が完走しない"
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
