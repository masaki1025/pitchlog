"""実制限role・物理同期複製・業務独立clusterで台帳候補を検証する。"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from time import monotonic
from uuid import uuid4

import psycopg
import pytest
from db_fixtures import _dsn_names

from pitchlog.durable_rights_ledger import (
    DurableLedger,
    LedgerOutcomeUnconfirmed,
    LedgerUnavailable,
    adapter,
)
from pitchlog.recording_rights.initial_grant import ReservedGeneration

from .durable_rights_ledger_support import LedgerDatabase, isolated_ledger_database

pytestmark = pytest.mark.requires_db


@pytest.fixture(scope="module")
def ledger_database() -> Iterator[LedgerDatabase]:
    """このmoduleだけの三台と専用volume/networkを所有する。"""
    with isolated_ledger_database() as database:
        yield database


@pytest.fixture
def ledger_connections(
    ledger_database: LedgerDatabase, monkeypatch: pytest.MonkeyPatch
) -> LedgerDatabase:
    """既存identity autouseへ専用DSNを明示し、照合を実施させる。"""
    admin_name, role_name = _dsn_names()
    monkeypatch.setenv(admin_name, ledger_database.primary_admin)
    monkeypatch.setenv(role_name, ledger_database.endpoints.primary_dsn)
    return ledger_database


@pytest.fixture
def admin_connection(
    ledger_connections: LedgerDatabase,
) -> Iterator[psycopg.Connection]:
    """共通identity検査へ実管理接続を渡す。"""
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


def test_real_reservation_claim_and_business_rollback(
    ledger_connections: LedgerDatabase,
) -> None:
    """実同期保全・同owner再照会・一度消費と業務rollback後不再利用。"""
    source = DurableLedger(ledger_connections.endpoints)
    params = tuple(uuid4() for _ in range(4))
    with source.recovery_fence() as fence:
        reserved = source.reserve(*params)
        assert type(reserved) is ReservedGeneration
        assert reserved.recovery_generation == fence.generation
        assert source.reserve(*params) == reserved
        with pytest.raises(LedgerUnavailable):
            source.reserve(params[0], uuid4(), *params[2:])
        source.claim(*params)
        with psycopg.connect(ledger_connections.business_admin) as business:
            business.execute("CREATE TEMP TABLE business_attempt (value bigint)")
            business.execute(
                "INSERT INTO business_attempt VALUES (%s)", (reserved.generation,)
            )
            business.rollback()
        fence.assert_held()
    with pytest.raises(LedgerUnavailable):
        fence.assert_held()
    with pytest.raises(LedgerUnavailable):
        source.claim(*params)
    with pytest.raises(LedgerUnavailable):
        source.reserve(*params)
    next_reserved = source.reserve(*(uuid4() for _ in range(4)))
    assert next_reserved.generation > reserved.generation
    with psycopg.connect(ledger_connections.endpoints.standby_dsn) as standby:
        row = standby.execute(
            "SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s)", params
        ).fetchone()
        assert row is not None and row[0] == reserved.generation and row[-1] is True


def test_real_parallel_and_fence_blocks_epoch(
    ledger_connections: LedgerDatabase,
) -> None:
    """高水位を並列直列化し、共有fenceはepoch更新だけを阻止する。"""
    endpoints = ledger_connections.endpoints
    source = DurableLedger(endpoints)
    attempts = [tuple(uuid4() for _ in range(4)) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        reservations = list(
            pool.map(lambda params: DurableLedger(endpoints).reserve(*params), attempts)
        )
    assert len({value.generation for value in reservations}) == 8
    epoch = source.current_recovery_generation()
    with source.recovery_fence() as fence:
        source.reserve(*(uuid4() for _ in range(4)))
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(source.advance_recovery_generation, epoch)
            with pytest.raises(LedgerUnavailable):
                pending.result(timeout=8)
        assert fence.generation == epoch
    assert source.advance_recovery_generation(epoch) == epoch + 1
    with pytest.raises(LedgerUnavailable):
        source.claim(*attempts[0])
    with pytest.raises(LedgerUnavailable):
        source.advance_recovery_generation(epoch)


def test_real_roles_owner_and_cluster_refusals(
    ledger_connections: LedgerDatabase,
) -> None:
    """直接DML・制御role逸脱・owner再束縛・同cluster誤接続を拒否する。"""
    endpoints = ledger_connections.endpoints
    source = DurableLedger(endpoints)
    params = tuple(uuid4() for _ in range(4))
    source.reserve(*params)
    with pytest.raises(LedgerUnavailable):
        source.claim(params[0], uuid4(), *params[2:])
    with pytest.raises(LedgerUnavailable):
        source.reserve(uuid4(), *params[1:])
    for dsn, sql in (
        (endpoints.primary_dsn, "UPDATE pitchlog_ledger.highwater SET value=0"),
        (endpoints.primary_dsn, "SELECT * FROM pitchlog_ledger.reservations"),
        (endpoints.primary_dsn, "SELECT pitchlog_ledger.advance_epoch(1)"),
        (endpoints.control_dsn, "SELECT pitchlog_ledger.epoch_fence()"),
        (endpoints.control_dsn, "DELETE FROM pitchlog_ledger.reservations"),
    ):
        with psycopg.connect(dsn) as connection:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(sql)
            connection.rollback()
    with pytest.raises(LedgerUnavailable):
        DurableLedger(replace(endpoints, business_dsn=ledger_connections.primary_admin))
    with pytest.raises(LedgerUnavailable):
        DurableLedger(replace(endpoints, standby_dsn=endpoints.primary_dsn))


def test_real_cancelled_sync_commit_is_unconfirmed(
    ledger_connections: LedgerDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """実standby停止時のCOMMITを有限取消し、同attemptの再利用を防ぐ。"""
    source = DurableLedger(ledger_connections.endpoints)
    params = tuple(uuid4() for _ in range(4))
    original = adapter._commit

    def stop_then_commit(connection: psycopg.Connection, timeout: float) -> None:
        ledger_connections.standby_running(False)
        original(connection, timeout)

    started = monotonic()
    try:
        with monkeypatch.context() as local:
            local.setattr(adapter, "_commit", stop_then_commit)
            with pytest.raises(
                LedgerOutcomeUnconfirmed, match="^ledger outcome unconfirmed$"
            ):
                source.reserve(*params)
        assert monotonic() - started < 15
    finally:
        ledger_connections.standby_running(True)
    # 元instanceは再起動したpeerを許可しない。取消済み番号の不存在も仮定しない。
    with pytest.raises(LedgerUnavailable):
        source.reserve(*params)
    with psycopg.connect(ledger_connections.primary_admin) as primary:
        row = primary.execute(
            "SELECT * FROM pitchlog_ledger.reservations WHERE attempt_id=%s",
            (params[0],),
        ).fetchone()
        assert row is not None  # PostgreSQLはlocal commit後に同期待機を取り消した。


def test_real_manifest_acl_and_function_owners(
    ledger_connections: LedgerDatabase,
) -> None:
    """全表/関数/role/search_pathの実カタログをmanifestへ照合する。"""
    import json
    from pathlib import Path

    manifest = json.loads((Path(adapter.__file__).parent / "manifest.json").read_text())
    with psycopg.connect(ledger_connections.primary_admin) as connection:
        roles = connection.execute(
            "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, "
            "rolcreaterole, rolreplication FROM pg_roles WHERE rolname IN "
            "('pitchlog_ledger_owner','pitchlog_ledger_app','pitchlog_ledger_control')"
            " ORDER BY rolname"
        ).fetchall()
        assert roles == [
            ("pitchlog_ledger_app", True, False, False, False, False),
            ("pitchlog_ledger_control", True, False, False, False, False),
            ("pitchlog_ledger_owner", False, False, False, False, False),
        ]
        tables = connection.execute(
            "SELECT c.relname, r.rolname FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner "
            "WHERE n.nspname='pitchlog_ledger' AND c.relkind='r'"
        ).fetchall()
        assert set(tables) == {
            (table, "pitchlog_ledger_owner") for table in manifest["tables"]
        }
        functions = connection.execute(
            "SELECT p.proname, pg_get_function_identity_arguments(p.oid), "
            "r.rolname, p.prosecdef, p.proconfig, p.oid FROM pg_proc p JOIN "
            "pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON "
            "r.oid=p.proowner WHERE n.nspname='pitchlog_ledger'"
        ).fetchall()
        assert len(functions) == len(manifest["functions"]) == 6
        for name, _, owner, security_definer, configuration, oid in functions:
            assert owner == "pitchlog_ledger_owner" and security_definer is True
            assert configuration == ["search_path=pg_catalog, pitchlog_ledger"]
            acl = connection.execute(
                "SELECT CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE "
                "pg_get_userbyid(x.grantee) END FROM pg_proc p CROSS JOIN LATERAL"
                " aclexplode(p.proacl) x WHERE p.oid=%s AND "
                "x.privilege_type='EXECUTE'",
                (oid,),
            ).fetchall()
            expected = {"pitchlog_ledger_owner"}
            expected.update(
                "pitchlog_ledger_" + role
                for signature, allowed in manifest["functions"].items()
                if signature.split("(")[0] == name
                for role in allowed
            )
            assert {row[0] for row in acl} == expected


def test_real_async_downgrade_and_replay_delay_are_refused(
    ledger_connections: LedgerDatabase,
) -> None:
    """同期設定不一致は発行前拒否、実replay遅延は成功へ写さない。"""
    source = DurableLedger(ledger_connections.endpoints)
    with psycopg.connect(ledger_connections.primary_admin, autocommit=True) as primary:
        try:
            primary.execute("ALTER SYSTEM SET synchronous_standby_names = ''")
            primary.execute("SELECT pg_reload_conf()")
            from time import sleep

            sleep(0.1)
            with pytest.raises(LedgerUnavailable):
                source.reserve(*(uuid4() for _ in range(4)))
        finally:
            primary.execute(
                "ALTER SYSTEM SET synchronous_standby_names = "
                "'FIRST 1 (ledger_standby)'"
            )
            primary.execute("SELECT pg_reload_conf()")
    sleep(0.1)
    params = tuple(uuid4() for _ in range(4))
    with psycopg.connect(ledger_connections.standby_admin, autocommit=True) as standby:
        standby.execute("SELECT pg_wal_replay_pause()")
        try:
            with pytest.raises(LedgerOutcomeUnconfirmed):
                source.reserve(*params)
        finally:
            standby.execute("SELECT pg_wal_replay_resume()")
    # 再照会は同attemptだけ。新attemptや未使用という仮定を作らない。
    reserved = source.reserve(*params)
    assert source.reserve(*params) == reserved


def test_real_success_survives_owned_primary_stop(
    ledger_connections: LedgerDatabase,
) -> None:
    """成功応答直後の実primary停止後にも指定standbyで予約集合を読める。"""
    from .durable_rights_ledger_support import _wait, docker

    source = DurableLedger(ledger_connections.endpoints)
    with psycopg.connect(ledger_connections.primary_admin) as primary:
        primary.execute(
            "UPDATE pitchlog_ledger.highwater SET value=9223372036854775806"
        )
    params = tuple(uuid4() for _ in range(4))
    reserved = source.reserve(*params)
    assert reserved.generation == 2**63 - 1
    with pytest.raises(LedgerUnavailable):
        source.reserve(*(uuid4() for _ in range(4)))
    source.claim(*params)
    epoch = source.current_recovery_generation()
    try:
        docker("stop", ledger_connections.primary)
        with psycopg.connect(ledger_connections.endpoints.standby_dsn) as standby:
            row = standby.execute(
                "SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s)", params
            ).fetchone()
            assert row is not None and row[0] == reserved.generation and row[-1] is True
            identity = standby.execute("SELECT pitchlog_ledger.identity()").fetchone()
            assert identity is not None and identity[0]["epoch"] == epoch
        with pytest.raises(LedgerUnavailable):
            source.current_recovery_generation()
    finally:
        docker("start", ledger_connections.primary)
        _wait(ledger_connections.primary_admin)
    with pytest.raises(LedgerUnavailable):
        source.reserve(*(uuid4() for _ in range(4)))
