"""認証の限定関数、認証表の直接アクセス、ID の露出を実 DB で検査する。"""

from __future__ import annotations

import json
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Event
from typing import Any, LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _app_dsn,
    _counter,
    _scalar,
    _seed_settings,
    _setting,
    _wait_for_lock,
)

pytestmark = pytest.mark.requires_db

_LIMITED_CALLS: tuple[tuple[str, LiteralString, tuple[object, ...]], ...] = (
    (
        "authn.issue_initial_password(uuid, text)",
        "SELECT authn.issue_initial_password(%s, %s)",
        (UUID(int=0), None),
    ),
    (
        "authn.reset_password(uuid, text)",
        "SELECT authn.reset_password(%s, %s)",
        (UUID(int=0), None),
    ),
    (
        "authn.revoke_tenant_tokens(uuid)",
        "SELECT authn.revoke_tenant_tokens(%s)",
        (UUID(int=0),),
    ),
    (
        "authn.record_admin_login_failure(text)",
        "SELECT authn.record_admin_login_failure(%s)",
        ("untrusted",),
    ),
)
_FUNCTION_ONLY_COLUMNS = {
    "tenant_auth_subjects": "tenant_id",
    "tenant_credentials": "generation",
    "tenant_tokens": "expires_at",
    "rate_limit_counters": "attempt_count",
}
_ADMIN_SETTINGS = {
    "auth.admin_login.max_failures": 2,
    "auth.admin_login.window_seconds": 4_000_000_000,
    "auth.admin_login.lock_seconds": 60,
}


def _admin_dsn(catalog: ProvisionedProductCatalog) -> str:
    """試験クラスタの superuser を製品 DB へ接続する。"""
    database = catalog.observer.info.dbname
    assert database is not None
    return make_conninfo(catalog.cluster.admin_dsn, dbname=database)


def _call_management(
    catalog: ProvisionedProductCatalog,
    statement: LiteralString,
    params: tuple[object, ...],
) -> Any:
    """NOLOGIN の管理関数所有ロールとして限定関数を呼び、確定する。"""
    with psycopg.connect(_admin_dsn(catalog)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE pitchlog_management_fn_owner")
            cursor.execute(statement, params)
            row = cursor.fetchone()
            assert row is not None
            return row[0]


def _tenant_only(catalog: ProvisionedProductCatalog) -> tuple[UUID, str]:
    """認証主体を持たないテナントを作る。"""
    tenant_id = uuid4()
    name = f"team{tenant_id.hex[:12]}"
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.tenants(id, name) VALUES (%s, %s)",
            (tenant_id, name),
        )
    catalog.applicator.commit()
    return tenant_id, name


def _credential(
    catalog: ProvisionedProductCatalog, tenant_id: UUID
) -> tuple[UUID, str, int, datetime] | None:
    """認証情報のハッシュ・世代・日時を内部側から読む。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT subject.id, credential.password_hash, credential.generation,
                   credential.password_changed_at
            FROM public.tenant_auth_subjects AS subject
            JOIN public.tenant_credentials AS credential
              ON credential.auth_subject_id = subject.id
            WHERE subject.tenant_id = %s
            """,
            (tenant_id,),
        )
        row = cursor.fetchone()
    catalog.observer.rollback()
    return row


def _subject_count(catalog: ProvisionedProductCatalog, tenant_id: UUID) -> int:
    """テナントの認証主体の件数を読む。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.count(*) FROM public.tenant_auth_subjects "
            "WHERE tenant_id = %s",
            (tenant_id,),
        )
        row = cursor.fetchone()
    catalog.observer.rollback()
    assert row is not None
    return int(row[0])


def _outsider_dsn(catalog: ProvisionedProductCatalog) -> tuple[str, str]:
    """スキーマ名は解決できるが権限を持たない LOGIN ロールを作る。"""
    role = f"authn_outsider_{uuid4().hex[:12]}"
    password = secrets.token_urlsafe(24)
    database = catalog.observer.info.dbname
    assert database is not None
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(role)
            )
        )
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public, authn, authn_crypto TO {}").format(
                sql.Identifier(role)
            )
        )
    catalog.applicator.commit()
    return role, make_conninfo(catalog.owner_dsn, user=role, password=password)


def _assert_sqlstate(
    connection: psycopg.Connection[Any],
    statement: LiteralString | sql.Composed,
    params: tuple[object, ...] = (),
    *,
    expected: str = "42501",
) -> None:
    """実接続で SQLSTATE を確かめ、次の検査に備えて rollback する。"""
    try:
        with pytest.raises(psycopg.Error) as raised:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
        assert raised.value.sqlstate == expected
    finally:
        connection.rollback()


def test_limited_functions_only_management_role_can_execute(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """管理ロールだけに EXECUTE を許し、各 LOGIN ロールの直呼びを 42501 にする。"""
    catalog = provisioned_product_catalog
    outsider_role, outsider_dsn = _outsider_dsn(catalog)
    app_dsn = _app_dsn(catalog)
    denied = (
        ("pitchlog_app", app_dsn),
        ("pitchlog_owner", catalog.owner_dsn),
        (outsider_role, outsider_dsn),
    )
    for signature, statement, params in _LIMITED_CALLS:
        with catalog.observer.cursor() as cursor:
            for role in ("pitchlog_management_fn_owner", *(name for name, _ in denied)):
                cursor.execute(
                    "SELECT pg_catalog.has_function_privilege("
                    "%s, %s::pg_catalog.regprocedure, 'EXECUTE')",
                    (role, signature),
                )
                row = cursor.fetchone()
                assert row == (role == "pitchlog_management_fn_owner",)
        catalog.observer.rollback()
        for _, dsn in denied:
            with psycopg.connect(dsn) as connection:
                _assert_sqlstate(connection, statement, params)


def test_initial_password_policy_single_subject_and_cost_twelve(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """弱い・NULL の PW を拒否し、初回だけ cost 12 の資格情報を作る。"""
    catalog = provisioned_product_catalog
    tenant_id, _ = _tenant_only(catalog)
    for weak in ("A123456", "abcdefgh", "12345678", None):
        assert (
            _call_management(
                catalog,
                "SELECT authn.issue_initial_password(%s, %s)",
                (tenant_id, weak),
            )
            == ""
        )
        assert _subject_count(catalog, tenant_id) == 0
    password = secrets.token_urlsafe(24) + "A1"
    assert (
        _call_management(
            catalog,
            "SELECT authn.issue_initial_password(%s, %s)",
            (tenant_id, password),
        )
        == ""
    )
    before = _credential(catalog, tenant_id)
    assert before is not None
    assert before[2] == 1
    assert re.fullmatch(r"\$2[aby]\$12\$[./A-Za-z0-9]{53}", before[1])
    assert _subject_count(catalog, tenant_id) == 1
    with pytest.raises(psycopg.errors.UniqueViolation) as raised:
        _call_management(
            catalog,
            "SELECT authn.issue_initial_password(%s, %s)",
            (tenant_id, secrets.token_urlsafe(24) + "A1"),
        )
    assert raised.value.diag.constraint_name == "uq_tenant_auth_subjects_tenant"
    assert _subject_count(catalog, tenant_id) == 1
    assert _credential(catalog, tenant_id) == before


def test_reset_password_rejects_weak_without_update_and_advances_generation(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """弱い PW で三つの保存値を保ち、有効な PW だけで世代を進める。"""
    catalog = provisioned_product_catalog
    tenant_id, _ = _tenant_only(catalog)
    original_password = secrets.token_urlsafe(24) + "A1"
    assert (
        _call_management(
            catalog,
            "SELECT authn.issue_initial_password(%s, %s)",
            (tenant_id, original_password),
        )
        == ""
    )
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            """
            UPDATE public.tenant_credentials AS credential
            SET password_changed_at = pg_catalog.clock_timestamp() - interval '1 day'
            FROM public.tenant_auth_subjects AS subject
            WHERE credential.auth_subject_id = subject.id
              AND subject.tenant_id = %s
            """,
            (tenant_id,),
        )
    catalog.applicator.commit()
    before = _credential(catalog, tenant_id)
    assert before is not None
    for weak in ("A123456", "abcdefgh", "12345678", None):
        assert (
            _call_management(
                catalog,
                "SELECT authn.reset_password(%s, %s)",
                (tenant_id, weak),
            )
            == ""
        )
        assert _credential(catalog, tenant_id) == before
    replacement = secrets.token_urlsafe(24) + "A1"
    assert (
        _call_management(
            catalog,
            "SELECT authn.reset_password(%s, %s)",
            (tenant_id, replacement),
        )
        == ""
    )
    after = _credential(catalog, tenant_id)
    assert after is not None
    assert after[0] == before[0]
    assert after[1] != before[1]
    assert after[2] == before[2] + 1
    assert after[3] > before[3]
    assert re.fullmatch(r"\$2[aby]\$12\$[./A-Za-z0-9]{53}", after[1])
    with catalog.observer.cursor() as cursor:
        cursor.execute("SELECT authn_crypto.crypt(%s, %s)", (replacement, after[1]))
        assert cursor.fetchone() == (after[1],)
    catalog.observer.rollback()


def test_revoke_tenant_tokens_invalidates_existing_and_accepts_no_subject(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """世代繰り上げで既存トークンを失効させ、主体不在なら何もせず成功する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    tenant_id, name = _tenant_only(catalog)
    password = secrets.token_urlsafe(24) + "A1"
    assert (
        _call_management(
            catalog,
            "SELECT authn.issue_initial_password(%s, %s)",
            (tenant_id, password),
        )
        == ""
    )
    token = _scalar(app_dsn, "SELECT authn.login(%s, %s)", (name, password))
    assert isinstance(token, UUID)
    assert _scalar(app_dsn, "SELECT authn.verify_token(%s)", (token,)) == tenant_id
    before = _credential(catalog, tenant_id)
    assert before is not None
    assert (
        _call_management(
            catalog,
            "SELECT authn.revoke_tenant_tokens(%s)",
            (tenant_id,),
        )
        == ""
    )
    after = _credential(catalog, tenant_id)
    assert after is not None
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] == before[2] + 1
    assert after[3] == before[3]
    assert _scalar(app_dsn, "SELECT authn.verify_token(%s)", (token,)) is None
    empty_tenant, _ = _tenant_only(catalog)
    assert (
        _call_management(
            catalog,
            "SELECT authn.revoke_tenant_tokens(%s)",
            (empty_tenant,),
        )
        == ""
    )
    assert _subject_count(catalog, empty_tenant) == 0


def _seed_admin_settings(catalog: ProvisionedProductCatalog) -> None:
    """管理者計数に必要な 3 キーを設定する。"""
    for key, value in _ADMIN_SETTINGS.items():
        _setting(catalog, key, value)


def test_admin_counter_is_separate_from_team_and_locks_at_threshold(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """管理者の単位を team: と分離し、閾値で拒否を返す。"""
    catalog = provisioned_product_catalog
    _seed_admin_settings(catalog)
    _seed_settings(catalog)
    scope = f"scope{uuid4().hex[:12]}"
    assert (
        _call_management(
            catalog,
            "SELECT authn.record_admin_login_failure(%s)",
            (scope,),
        )
        is False
    )
    assert (
        _call_management(
            catalog,
            "SELECT authn.record_admin_login_failure(%s)",
            (scope,),
        )
        is True
    )
    assert [row[1] for row in _counter(catalog, f"admin:{scope}")] == [2]
    app_dsn = _app_dsn(catalog)
    assert (
        _scalar(
            app_dsn,
            "SELECT authn.login(%s, %s)",
            (scope, secrets.token_urlsafe(24)),
        )
        is None
    )
    assert [row[1] for row in _counter(catalog, f"team:{scope}")] == [1]
    assert [row[1] for row in _counter(catalog, f"admin:{scope}")] == [2]


def test_admin_counter_bad_settings_fail_closed(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """管理者用 3 キーの欠落・文字列・0 以下・小数では計数せず拒否する。"""
    catalog = provisioned_product_catalog
    _seed_admin_settings(catalog)
    for key, valid in _ADMIN_SETTINGS.items():
        for invalid in (None, "invalid", 0, -1, 1.5):
            with catalog.applicator.cursor() as cursor:
                if invalid is None:
                    cursor.execute(
                        "DELETE FROM public.system_settings WHERE key = %s", (key,)
                    )
                else:
                    cursor.execute(
                        "UPDATE public.system_settings "
                        "SET value = %s::jsonb WHERE key = %s",
                        (json.dumps(invalid), key),
                    )
            catalog.applicator.commit()
            scope = f"bad{uuid4().hex[:12]}"
            assert (
                _call_management(
                    catalog,
                    "SELECT authn.record_admin_login_failure(%s)",
                    (scope,),
                )
                is True
            )
            assert _counter(catalog, f"admin:{scope}") == []
            _setting(catalog, key, valid)


def test_admin_counter_first_row_is_serialized(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """空の窓で先行トランザクションを保持し、後続の勧告ロック待ちと件数を検査する。"""
    catalog = provisioned_product_catalog
    _seed_admin_settings(catalog)
    _setting(catalog, "auth.admin_login.max_failures", 1000)
    scope = f"parallel{uuid4().hex[:12]}"
    ready = Event()
    release = Event()
    pids: list[int] = []

    def attempt(*, hold: bool) -> bool:
        with psycopg.connect(_admin_dsn(catalog)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE pitchlog_management_fn_owner")
                cursor.execute("SELECT pg_catalog.pg_backend_pid()")
                pid_row = cursor.fetchone()
                assert pid_row is not None
                if not hold:
                    pids.append(int(pid_row[0]))
                cursor.execute("SELECT authn.record_admin_login_failure(%s)", (scope,))
                result = cursor.fetchone()
                assert result == (False,)
                if hold:
                    ready.set()
                    assert release.wait(15)
                return bool(result[0])

    with ThreadPoolExecutor(max_workers=5) as pool:
        leader = pool.submit(attempt, hold=True)
        assert ready.wait(15)
        followers = [pool.submit(attempt, hold=False) for _ in range(4)]
        deadline = time.monotonic() + 15
        while len(pids) < len(followers) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(pids) == len(followers)
        try:
            _wait_for_lock(catalog, pids, advisory=True)
        finally:
            release.set()
        assert leader.result(timeout=15) is False
        assert [item.result(timeout=15) for item in followers] == [False] * 4
    assert [row[1] for row in _counter(catalog, f"admin:{scope}")] == [5]


def test_function_only_tables_deny_direct_dml_to_untrusted_login_roles(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """表所有者以外の LOGIN ロールに 4 表の直接 DML を許さない。"""
    catalog = provisioned_product_catalog
    outsider_role, outsider_dsn = _outsider_dsn(catalog)
    for role, dsn in (
        ("pitchlog_app", _app_dsn(catalog)),
        (outsider_role, outsider_dsn),
    ):
        with psycopg.connect(dsn) as connection:
            for table, column in _FUNCTION_ONLY_COLUMNS.items():
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    with catalog.observer.cursor() as observer:
                        observer.execute(
                            "SELECT pg_catalog.has_table_privilege(%s, %s, %s)",
                            (role, f"public.{table}", privilege),
                        )
                        assert observer.fetchone() == (False,)
                    catalog.observer.rollback()
                relation = sql.Identifier("public", table)
                statements = (
                    sql.SQL("SELECT * FROM {} LIMIT 0").format(relation),
                    sql.SQL("INSERT INTO {} DEFAULT VALUES").format(relation),
                    sql.SQL("UPDATE {} SET {} = {} WHERE false").format(
                        relation, sql.Identifier(column), sql.Identifier(column)
                    ),
                    sql.SQL("DELETE FROM {} WHERE false").format(relation),
                )
                for statement in statements:
                    _assert_sqlstate(connection, statement)


def test_pgcrypto_members_deny_execute_to_app_and_outsider(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """スキーマ USAGE を試験中に与えても拡張の関数 ACL が実行を拒否する。"""
    catalog = provisioned_product_catalog
    outsider_role, outsider_dsn = _outsider_dsn(catalog)
    with catalog.applicator.cursor() as cursor:
        cursor.execute("GRANT USAGE ON SCHEMA authn_crypto TO pitchlog_app")
    catalog.applicator.commit()
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT procedure.oid
            FROM pg_catalog.pg_proc AS procedure
            JOIN pg_catalog.pg_depend AS dependency
              ON dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
             AND dependency.objid = procedure.oid
             AND dependency.refclassid =
                 'pg_catalog.pg_extension'::pg_catalog.regclass
             AND dependency.deptype = 'e'
            JOIN pg_catalog.pg_extension AS extension
              ON extension.oid = dependency.refobjid
            WHERE extension.extname = 'pgcrypto'
              AND procedure.pronamespace =
                  'authn_crypto'::pg_catalog.regnamespace
            """
        )
        members = [row[0] for row in cursor.fetchall()]
        assert len(members) >= 2
        for role in ("pitchlog_app", outsider_role):
            for function_oid in members:
                cursor.execute(
                    "SELECT pg_catalog.has_function_privilege("
                    "%s, %s::pg_catalog.oid, 'EXECUTE')",
                    (role, function_oid),
                )
                assert cursor.fetchone() == (False,)
    catalog.observer.rollback()
    for dsn in (_app_dsn(catalog), outsider_dsn):
        with psycopg.connect(dsn) as connection:
            _assert_sqlstate(
                connection,
                "SELECT authn_crypto.crypt(%s, %s)",
                (
                    secrets.token_urlsafe(24),
                    "$2a$12$abcdefghijklmnopqrstuug/hOvRed88u/sCt2izp9NATk2M3qMx6",
                ),
            )
            _assert_sqlstate(connection, "SELECT authn_crypto.gen_salt('bf')")


def test_composite_subject_fk_rejects_token_for_another_tenant(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Superuser の直接 INSERT でもトークンと主体のテナント不一致を拒否する。"""
    catalog = provisioned_product_catalog
    first_tenant, _ = _tenant_only(catalog)
    second_tenant, _ = _tenant_only(catalog)
    assert (
        _call_management(
            catalog,
            "SELECT authn.issue_initial_password(%s, %s)",
            (first_tenant, secrets.token_urlsafe(24) + "A1"),
        )
        == ""
    )
    credential = _credential(catalog, first_tenant)
    assert credential is not None
    token_id = uuid4()
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as raised:
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.tenant_tokens
                    (id, tenant_id, auth_subject_id, credential_generation,
                     expires_at, last_used_at)
                VALUES (%s, %s, %s, 1,
                        pg_catalog.clock_timestamp() + interval '1 hour',
                        pg_catalog.clock_timestamp())
                """,
                (token_id, second_tenant, credential[0]),
            )
    assert raised.value.diag.constraint_name == "fk_tenant_tokens_subject"
    catalog.applicator.rollback()
    with catalog.observer.cursor() as cursor:
        cursor.execute("SELECT 1 FROM public.tenant_tokens WHERE id = %s", (token_id,))
        assert cursor.fetchone() is None
    catalog.observer.rollback()


def test_authn_result_types_are_exact_and_verify_returns_tenant_id(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """関数戻り値の集合を照合し、検証が返す UUID はテナント ID と確かめる。"""
    catalog = provisioned_product_catalog
    expected = {
        ("login", "text, text"): "uuid",
        ("verify_token", "uuid"): "uuid",
        ("logout", "uuid"): "void",
        ("change_password", "uuid, text, text"): "boolean",
        ("issue_initial_password", "uuid, text"): "void",
        ("reset_password", "uuid, text"): "void",
        ("revoke_tenant_tokens", "uuid"): "void",
        ("record_admin_login_failure", "text"): "boolean",
        ("password_policy_ok", "text"): "boolean",
        ("setting_positive_integer", "text"): "bigint",
        ("record_failure", "text, bigint, bigint, bigint, boolean"): "boolean",
    }
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT procedure.proname,
                   pg_catalog.oidvectortypes(procedure.proargtypes),
                   pg_catalog.format_type(procedure.prorettype, NULL)
            FROM pg_catalog.pg_proc AS procedure
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = procedure.pronamespace
            WHERE namespace.nspname = 'authn'
            """
        )
        actual = {(row[0], row[1]): row[2] for row in cursor.fetchall()}
    catalog.observer.rollback()
    assert actual == expected
    assert {name for (name, _), result in actual.items() if result == "uuid"} == {
        "login",
        "verify_token",
    }
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    tenant_id, name = _tenant_only(catalog)
    password = secrets.token_urlsafe(24) + "A1"
    assert (
        _call_management(
            catalog,
            "SELECT authn.issue_initial_password(%s, %s)",
            (tenant_id, password),
        )
        == ""
    )
    token = _scalar(app_dsn, "SELECT authn.login(%s, %s)", (name, password))
    assert isinstance(token, UUID)
    assert token != tenant_id
    assert _scalar(app_dsn, "SELECT authn.verify_token(%s)", (token,)) == tenant_id
