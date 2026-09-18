"""テナント境界試験の平場エントリーポイント。

構成検査・DB 統合・故障注入・変異検査を後続ステップも本モジュールへ追加する。
現段階では、明示 import した DB fixture の解決と共有に加え、アプリ用物理接続の
ロール名・全属性・到達閉包・初期 GUC・トランザクション終了状態を検証する。
"""

import secrets
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
import pytest
from db_fixtures import (
    DisposablePostgres,
    _authenticated_identity,
    _SessionResourceRegistry,
    admin_connection,
    disposable_postgres_cluster,
    tested_role_connection,
    verify_connection_identities,
)
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.pq import TransactionStatus
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from pitchlog.authz.runtime_contract import (
    APPLICATION_ROLE_NAME,
    DANGEROUS_ENDPOINT_FIXTURES,
)
from pitchlog.db.config import DatabaseConfigurationError
from pitchlog.db.engine import (
    _verify_application_role_connection,
    create_database_engine,
)

# DB fixture は backend/tests/conftest.py を経由せず、平場へ明示的に再公開する。
__all__ = (
    "admin_connection",
    "disposable_postgres_cluster",
    "tested_role_connection",
    "verify_connection_identities",
)

_ROLE_NAMES = {
    "table_owner": "tenant_guard_table_owner",
    "ordinary_login": "tenant_guard_ordinary_login",
    "shared_function_owner": "tenant_guard_shared_function_owner",
    "management_function_owner": "tenant_guard_management_function_owner",
    "migration_batch": "tenant_guard_migration_batch",
    "superuser": "tenant_guard_superuser",
    "bypassrls": "tenant_guard_bypassrls",
    "schema_owner": "tenant_guard_schema_owner",
    "middle_one": "tenant_guard_middle_one",
    "middle_two": "tenant_guard_middle_two",
}
_NAME_NEGATIVE_IDS = {
    "table_owner",
    "ordinary_login",
    "shared_function_owner",
    "management_function_owner",
    "migration_batch",
    "superuser",
    "set_role_impersonation",
}


@dataclass(frozen=True, slots=True)
class _ApplicationRoleDatabase:
    """使い捨てクラスタ上のアプリ用ロール検査構成。"""

    cluster: DisposablePostgres
    admin: psycopg.Connection[Any]
    application_dsn: str
    application_url: str
    role_urls: dict[str, str]
    dangerous_roles: dict[str, str]


def _sqlalchemy_url(dsn: str, *, options: str | None = None) -> str:
    """Libpq DSN を SQLAlchemy の psycopg URL へ変換する。

    Args:
        dsn: 使い捨てクラスタの libpq DSN。
        options: 接続開始時に渡す PostgreSQL options。

    Returns:
        パスワードを含むテスト専用 SQLAlchemy URL。
    """
    values = conninfo_to_dict(dsn)
    query = {} if options is None else {"options": options}
    username = values.get("user")
    password = values.get("password")
    host = values.get("host")
    port = values.get("port")
    database = values.get("dbname")
    return URL.create(
        "postgresql+psycopg",
        username=None if username is None else str(username),
        password=None if password is None else str(password),
        host=None if host is None else str(host),
        port=None if port is None else int(port),
        database=None if database is None else str(database),
        query=query,
    ).render_as_string(hide_password=False)


def _create_role(
    admin: psycopg.Connection[Any],
    role_name: str,
    *,
    login: bool,
    password: str | None = None,
    superuser: bool = False,
    bypassrls: bool = False,
) -> None:
    """負例に必要な属性を固定してロールを作成する。"""
    login_clause = sql.SQL("LOGIN") if login else sql.SQL("NOLOGIN")
    superuser_clause = sql.SQL("SUPERUSER") if superuser else sql.SQL("NOSUPERUSER")
    bypass_clause = sql.SQL("BYPASSRLS") if bypassrls else sql.SQL("NOBYPASSRLS")
    password_clause = (
        sql.SQL("")
        if password is None
        else sql.SQL(" PASSWORD {}").format(sql.Literal(password))
    )
    with admin.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "CREATE ROLE {} WITH {} {} {} NOCREATEROLE NOCREATEDB "
                "NOREPLICATION NOINHERIT{}"
            ).format(
                sql.Identifier(role_name),
                login_clause,
                superuser_clause,
                bypass_clause,
                password_clause,
            )
        )


def _configure_application_role_database(
    cluster: DisposablePostgres,
    admin: psycopg.Connection[Any],
) -> _ApplicationRoleDatabase:
    """真正性検査の正例と全負例を同じ隔離クラスタへ構成する。"""
    passwords = {
        role_id: secrets.token_urlsafe(24)
        for role_id in (
            "table_owner",
            "ordinary_login",
            "shared_function_owner",
            "management_function_owner",
            "migration_batch",
            "superuser",
        )
    }
    application_password = secrets.token_urlsafe(24)
    _create_role(
        admin,
        APPLICATION_ROLE_NAME,
        login=True,
        password=application_password,
    )
    for role_id in (
        "table_owner",
        "ordinary_login",
        "shared_function_owner",
        "management_function_owner",
        "migration_batch",
    ):
        _create_role(
            admin,
            _ROLE_NAMES[role_id],
            login=True,
            password=passwords[role_id],
        )
    _create_role(
        admin,
        _ROLE_NAMES["superuser"],
        login=True,
        password=passwords["superuser"],
        superuser=True,
    )
    _create_role(
        admin,
        _ROLE_NAMES["bypassrls"],
        login=False,
        bypassrls=True,
    )
    for role_id in ("schema_owner", "middle_one", "middle_two"):
        _create_role(admin, _ROLE_NAMES[role_id], login=False)

    with admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER SCHEMA public OWNER TO {}").format(
                sql.Identifier(_ROLE_NAMES["schema_owner"])
            )
        )
        cursor.execute("CREATE TABLE public.tenants (id integer)")
        cursor.execute(
            sql.SQL("ALTER TABLE public.tenants OWNER TO {}").format(
                sql.Identifier(_ROLE_NAMES["table_owner"])
            )
        )
        cursor.execute(
            """
            CREATE FUNCTION public.prevent_team_records_kind_update()
            RETURNS integer LANGUAGE sql AS 'SELECT 1'
            """
        )
        cursor.execute(
            sql.SQL(
                "ALTER FUNCTION public.prevent_team_records_kind_update() OWNER TO {}"
            ).format(sql.Identifier(_ROLE_NAMES["shared_function_owner"]))
        )
        cursor.execute(
            """
            CREATE FUNCTION public.prevent_admin_sessions_identity_update()
            RETURNS integer LANGUAGE sql AS 'SELECT 1'
            """
        )
        cursor.execute(
            sql.SQL(
                "ALTER FUNCTION public.prevent_admin_sessions_identity_update() "
                "OWNER TO {}"
            ).format(sql.Identifier(_ROLE_NAMES["management_function_owner"]))
        )

    application_dsn = make_conninfo(
        cluster.role_dsn_template,
        user=APPLICATION_ROLE_NAME,
        password=application_password,
    )
    role_urls = {
        role_id: _sqlalchemy_url(
            make_conninfo(
                cluster.role_dsn_template,
                user=_ROLE_NAMES[role_id],
                password=password,
            )
        )
        for role_id, password in passwords.items()
    }
    return _ApplicationRoleDatabase(
        cluster=cluster,
        admin=admin,
        application_dsn=application_dsn,
        application_url=_sqlalchemy_url(application_dsn),
        role_urls=role_urls,
        dangerous_roles={
            "superuser": _ROLE_NAMES["superuser"],
            "bypassrls": _ROLE_NAMES["bypassrls"],
            "schema_owner": _ROLE_NAMES["schema_owner"],
            "table_owner": _ROLE_NAMES["table_owner"],
            "function_owner": _ROLE_NAMES["shared_function_owner"],
        },
    )


@pytest.fixture
def application_role_database(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> Iterator[_ApplicationRoleDatabase]:
    """アプリ用ロール真正性検査を隔離した実 DB で供給する。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            yield _configure_application_role_database(cluster, admin)


def _application_engine(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> Engine:
    """指定 URL を既存の単一アプリ経路へ設定して engine を作る。"""
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", database_url)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    return create_database_engine()


def _grant_memberships(
    admin: psycopg.Connection[Any],
    grants: tuple[tuple[str, str, bool, bool, bool], ...],
) -> None:
    """メンバーシップ辺を option の完全指定で作成する。"""
    with admin.cursor() as cursor:
        for role_name, member_name, admin_value, inherit_value, set_value in grants:
            cursor.execute(
                sql.SQL(
                    "GRANT {} TO {} WITH ADMIN {}, INHERIT {}, SET {}"
                ).format(
                    sql.Identifier(role_name),
                    sql.Identifier(member_name),
                    sql.SQL("TRUE" if admin_value else "FALSE"),
                    sql.SQL("TRUE" if inherit_value else "FALSE"),
                    sql.SQL("TRUE" if set_value else "FALSE"),
                )
            )


def _revoke_memberships(
    admin: psycopg.Connection[Any],
    grants: tuple[tuple[str, str, bool, bool, bool], ...],
) -> None:
    """作成したメンバーシップ辺を逆順に除去する。"""
    with admin.cursor() as cursor:
        for role_name, member_name, _, _, _ in reversed(grants):
            cursor.execute(
                sql.SQL("REVOKE {} FROM {}").format(
                    sql.Identifier(role_name),
                    sql.Identifier(member_name),
                )
            )


def _assert_duplicate_fixture_registrations_share_one_session_resource() -> None:
    """二つの登録経路が単一資源を共有し、最後の解放時だけ破棄する。"""
    registry = _SessionResourceRegistry()
    resource_key = object()
    expected_resource = object()
    setup_count = 0
    teardown_count = 0

    @contextmanager
    def create_resource() -> Iterator[object]:
        nonlocal setup_count, teardown_count
        setup_count += 1
        try:
            yield expected_resource
        finally:
            teardown_count += 1

    db_conftest_registration = registry.acquire(resource_key, create_resource)
    flat_module_registration = registry.acquire(resource_key, create_resource)
    with db_conftest_registration as db_resource:
        with flat_module_registration as flat_resource:
            assert db_resource is flat_resource
            assert setup_count == 1
            assert teardown_count == 0
        assert teardown_count == 0
    assert teardown_count == 1


@pytest.mark.requires_db
def test_explicit_database_fixtures_preserve_connection_identities(
    admin_connection: psycopg.Connection[Any],
    tested_role_connection: psycopg.Connection[Any],
    verify_connection_identities: None,
) -> None:
    """平場から解決した接続が別々の認証主体を保つことを確認する。"""
    _assert_duplicate_fixture_registrations_share_one_session_resource()
    assert verify_connection_identities is None
    admin_identity = _authenticated_identity(admin_connection)
    tested_role_identity = _authenticated_identity(tested_role_connection)
    assert admin_identity[0] == admin_identity[1]
    assert tested_role_identity[0] == tested_role_identity[1]
    assert admin_identity != tested_role_identity


@pytest.mark.requires_db
def test_application_role_is_verified_on_first_physical_connection(
    application_role_database: _ApplicationRoleDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Engine 生成ではなく最初の物理接続時に真正性検査を完了する。"""
    engine = _application_engine(
        monkeypatch,
        application_role_database.application_url,
    )
    try:
        with engine.connect() as connection:
            raw_connection = connection.connection.driver_connection
            assert isinstance(raw_connection, psycopg.Connection)
            assert raw_connection.info.transaction_status is TransactionStatus.IDLE
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    finally:
        engine.dispose()


@pytest.mark.requires_db
def test_all_wrong_role_names_are_rejected_at_connect(
    application_role_database: _ApplicationRoleDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """所有者・通常・バッチ・superuser の全名前負例を接続時に拒否する。"""
    observed_ids = set(application_role_database.role_urls)
    assert observed_ids | {"set_role_impersonation"} == _NAME_NEGATIVE_IDS

    for role_id, role_url in application_role_database.role_urls.items():
        engine = _application_engine(monkeypatch, role_url)
        try:
            with pytest.raises(
                DatabaseConfigurationError,
                match="session_user が期待アプリロール名と不一致",
            ):
                engine.connect()
        finally:
            engine.dispose()


@pytest.mark.requires_db
def test_set_role_impersonation_is_rejected_and_rolled_back(
    application_role_database: _ApplicationRoleDatabase,
) -> None:
    """current_user だけを期待名にした SET ROLE 偽装を拒否する。"""
    with psycopg.connect(application_role_database.cluster.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET ROLE {}").format(sql.Identifier(APPLICATION_ROLE_NAME))
            )
        with pytest.raises(
            DatabaseConfigurationError,
            match="session_user が期待アプリロール名と不一致",
        ):
            _verify_application_role_connection(connection)
        assert connection.info.transaction_status is TransactionStatus.IDLE


@pytest.mark.requires_db
def test_same_role_name_with_each_security_attribute_is_rejected(
    application_role_database: _ApplicationRoleDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """期待名を保った SUPERUSER・BYPASSRLS・CREATEROLE を個別に拒否する。"""
    attribute_mutations = (
        ("SUPERUSER", "NOSUPERUSER", "rolsuper"),
        ("BYPASSRLS", "NOBYPASSRLS", "rolbypassrls"),
        ("CREATEROLE", "NOCREATEROLE", "rolcreaterole"),
    )
    for enabled_clause, disabled_clause, attribute_name in attribute_mutations:
        with application_role_database.admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE {} {}").format(
                    sql.Identifier(APPLICATION_ROLE_NAME),
                    sql.SQL(enabled_clause),
                )
            )
        engine = _application_engine(
            monkeypatch,
            application_role_database.application_url,
        )
        try:
            with pytest.raises(
                DatabaseConfigurationError,
                match=rf"ロール属性が不一致: {attribute_name}",
            ):
                engine.connect()
        finally:
            engine.dispose()
            with application_role_database.admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL("ALTER ROLE {} {}").format(
                        sql.Identifier(APPLICATION_ROLE_NAME),
                        sql.SQL(disabled_clause),
                    )
                )


@pytest.mark.requires_db
def test_each_dangerous_endpoint_category_is_rejected(
    application_role_database: _ApplicationRoleDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """危険終点5分類を資産の exact-set どおり実 DB で拒否する。"""
    fixture_categories = {
        category for category, _ in DANGEROUS_ENDPOINT_FIXTURES
    }
    assert fixture_categories == set(application_role_database.dangerous_roles)

    for category, fixture_id in DANGEROUS_ENDPOINT_FIXTURES:
        dangerous_role = application_role_database.dangerous_roles[category]
        grants = (
            (
                dangerous_role,
                APPLICATION_ROLE_NAME,
                False,
                False,
                True,
            ),
        )
        _grant_memberships(application_role_database.admin, grants)
        engine = _application_engine(
            monkeypatch,
            application_role_database.application_url,
        )
        try:
            with pytest.raises(
                DatabaseConfigurationError,
                match=rf"危険ロールへ到達可能: {dangerous_role}",
            ):
                engine.connect()
        finally:
            engine.dispose()
            _revoke_memberships(application_role_database.admin, grants)
        assert fixture_id.startswith("DANGER_")


@pytest.mark.requires_db
def test_set_inherit_multihop_and_mixed_reachability_are_rejected(
    application_role_database: _ApplicationRoleDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SET・INHERIT の直接、多段、混合閉包を独立 fixture として拒否する。"""
    dangerous_role = _ROLE_NAMES["table_owner"]
    middle = _ROLE_NAMES["middle_one"]
    cases = {
        "set_direct": (
            (dangerous_role, APPLICATION_ROLE_NAME, False, False, True),
        ),
        "set_multihop": (
            (middle, APPLICATION_ROLE_NAME, False, False, True),
            (dangerous_role, middle, False, False, True),
        ),
        "inherit_direct": (
            (dangerous_role, APPLICATION_ROLE_NAME, False, True, False),
        ),
        "inherit_multihop": (
            (middle, APPLICATION_ROLE_NAME, False, True, False),
            (dangerous_role, middle, False, True, False),
        ),
        "set_then_inherit": (
            (middle, APPLICATION_ROLE_NAME, False, False, True),
            (dangerous_role, middle, False, True, False),
        ),
    }
    assert set(cases) == {
        "set_direct",
        "set_multihop",
        "inherit_direct",
        "inherit_multihop",
        "set_then_inherit",
    }

    for grants in cases.values():
        _grant_memberships(application_role_database.admin, grants)
        engine = _application_engine(
            monkeypatch,
            application_role_database.application_url,
        )
        try:
            with pytest.raises(
                DatabaseConfigurationError,
                match=rf"危険ロールへ到達可能: {dangerous_role}",
            ):
                engine.connect()
        finally:
            engine.dispose()
            _revoke_memberships(application_role_database.admin, grants)


@pytest.mark.requires_db
def test_admin_option_is_rejected_without_set_or_inherit(
    application_role_database: _ApplicationRoleDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SET=false・INHERIT=false でも ADMIN OPTION を独立に拒否する。"""
    ordinary_role = _ROLE_NAMES["ordinary_login"]
    grants = (
        (ordinary_role, APPLICATION_ROLE_NAME, True, False, False),
    )
    _grant_memberships(application_role_database.admin, grants)
    engine = _application_engine(
        monkeypatch,
        application_role_database.application_url,
    )
    try:
        with pytest.raises(DatabaseConfigurationError, match="ADMIN OPTION を保持"):
            engine.connect()
    finally:
        engine.dispose()
        _revoke_memberships(application_role_database.admin, grants)


@pytest.mark.requires_db
def test_nonempty_tenant_guc_at_connection_start_is_rejected(
    application_role_database: _ApplicationRoleDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSN options で接続前に設定されたテナント GUC を拒否する。"""
    database_url = _sqlalchemy_url(
        application_role_database.application_dsn,
        options="-c app.tenant_id=preconfigured-tenant",
    )
    engine = _application_engine(monkeypatch, database_url)
    try:
        with pytest.raises(
            DatabaseConfigurationError,
            match="接続開始時から app.tenant_id が設定済み",
        ):
            engine.connect()
    finally:
        engine.dispose()


@pytest.mark.requires_db
def test_rejected_inspection_rolls_back_and_same_connection_can_be_rechecked(
    application_role_database: _ApplicationRoleDatabase,
) -> None:
    """拒否後も同じ物理接続を idle に戻し、再検査を有効に保つ。"""
    with psycopg.connect(application_role_database.application_dsn) as connection:
        with application_role_database.admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE {} CREATEROLE").format(
                    sql.Identifier(APPLICATION_ROLE_NAME)
                )
            )
        try:
            with pytest.raises(
                DatabaseConfigurationError,
                match="rolcreaterole",
            ):
                _verify_application_role_connection(connection)
            assert connection.info.transaction_status is TransactionStatus.IDLE
        finally:
            with application_role_database.admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL("ALTER ROLE {} NOCREATEROLE").format(
                        sql.Identifier(APPLICATION_ROLE_NAME)
                    )
                )

        _verify_application_role_connection(connection)
        assert connection.info.transaction_status is TransactionStatus.IDLE
