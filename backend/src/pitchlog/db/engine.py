"""アプリケーション用 SQLAlchemy engine を生成する。"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.pq import TransactionStatus
from sqlalchemy import Engine, create_engine, event

from pitchlog.authz.runtime_contract import (
    APPLICATION_ROLE_ATTRIBUTES,
    APPLICATION_ROLE_NAME,
    PROTECTED_FUNCTIONS,
    PROTECTED_SCHEMAS,
    PROTECTED_TABLES,
    ApplicationRoleAttributes,
)
from pitchlog.db.config import (
    DatabaseConfigurationError,
    require_database_configuration,
)
from pitchlog.db.url import normalize_postgresql_url

_DATABASE_URL_VARIABLE = "PITCHLOG_DATABASE_URL"
_DATABASE_POOLED_VARIABLE = "PITCHLOG_DATABASE_POOLED"
_ROLE_ATTRIBUTE_NAMES = (
    "rolsuper",
    "rolbypassrls",
    "rolcanlogin",
    "rolcreaterole",
    "rolcreatedb",
    "rolreplication",
    "rolinherit",
)


@dataclass(frozen=True, slots=True)
class _MembershipEdge:
    """ロールメンバーシップの有向辺と三つの option を保持する。"""

    member: str
    role: str
    admin_option: bool
    inherit_option: bool
    set_option: bool


@dataclass(frozen=True, slots=True)
class _ConnectionObservation:
    """物理接続から取得した真正性判定用の観測値を保持する。"""

    session_user: str
    current_user: str
    attributes: ApplicationRoleAttributes | None
    tenant_id: str | None
    memberships: tuple[_MembershipEdge, ...]
    dangerous_roles: frozenset[str]


def _role_attribute_violations(
    attributes: ApplicationRoleAttributes | None,
) -> list[str]:
    """期待アプリロールの属性不一致を列挙する。

    Args:
        attributes: カタログから観測した期待名ロールの全属性。

    Returns:
        期待値との不一致。完全一致なら空配列。
    """
    if attributes is None:
        return [f"期待アプリロールが存在しない: {APPLICATION_ROLE_NAME}"]
    return [
        f"ロール属性が不一致: {attribute_name}"
        for attribute_name in _ROLE_ATTRIBUTE_NAMES
        if getattr(attributes, attribute_name)
        != getattr(APPLICATION_ROLE_ATTRIBUTES, attribute_name)
    ]


def _membership_closure(
    seeds: set[str],
    memberships: tuple[_MembershipEdge, ...],
    option_name: str,
) -> set[str]:
    """指定 option が有効な辺だけでロール到達閉包を計算する。

    Args:
        seeds: 閉包の開始ロール集合。
        memberships: PostgreSQL のロールメンバーシップ辺。
        option_name: ``set_option`` または ``inherit_option``。

    Returns:
        開始ロールを含む推移閉包。
    """
    reachable = set(seeds)
    changed = True
    while changed:
        changed = False
        for membership in memberships:
            if membership.member not in reachable:
                continue
            if not getattr(membership, option_name):
                continue
            if membership.role in reachable:
                continue
            reachable.add(membership.role)
            changed = True
    return reachable


def _membership_violations(
    memberships: tuple[_MembershipEdge, ...],
    dangerous_roles: frozenset[str],
) -> list[str]:
    """危険終点への混合閉包到達と ADMIN OPTION を列挙する。"""
    set_reachable = _membership_closure(
        {APPLICATION_ROLE_NAME}, memberships, "set_option"
    )
    effective_reachable = _membership_closure(
        set_reachable, memberships, "inherit_option"
    )
    violations = [
        f"危険ロールへ到達可能: {role_name}"
        for role_name in sorted(effective_reachable & dangerous_roles)
    ]
    violations.extend(
        f"ADMIN OPTION を保持: {membership.member}->{membership.role}"
        for membership in memberships
        if membership.admin_option and membership.member in effective_reachable
    )
    return violations


def _connection_observation_violations(
    observation: _ConnectionObservation,
) -> list[str]:
    """物理接続の観測値をランタイム契約と照合する。"""
    violations: list[str] = []
    if observation.session_user != APPLICATION_ROLE_NAME:
        violations.append("session_user が期待アプリロール名と不一致")
    if observation.current_user != APPLICATION_ROLE_NAME:
        violations.append("current_user が期待アプリロール名と不一致")
    violations.extend(_role_attribute_violations(observation.attributes))
    violations.extend(
        _membership_violations(
            observation.memberships,
            observation.dangerous_roles,
        )
    )
    if observation.tenant_id not in (None, ""):
        violations.append("接続開始時から app.tenant_id が設定済み")
    return violations


def _verify_application_role_connection(
    connection: psycopg.Connection[Any],
) -> None:
    """アプリ用の物理接続をカタログ照合し、検査トランザクションを閉じる。

    Args:
        connection: SQLAlchemy が確立した psycopg 物理接続。

    Raises:
        DatabaseConfigurationError: 接続主体、属性、到達性、GUC、または
            トランザクション状態が契約と一致しない場合。
    """
    observation: _ConnectionObservation | None = None
    inspection_error: psycopg.Error | None = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    session_user::text,
                    current_user::text,
                    current_setting('app.tenant_id', true)
                """
            )
            identity_row = cursor.fetchone()
            if identity_row is None:
                raise DatabaseConfigurationError("接続主体を観測できない")

            cursor.execute(
                """
                SELECT
                    rolsuper,
                    rolbypassrls,
                    rolcanlogin,
                    rolcreaterole,
                    rolcreatedb,
                    rolreplication,
                    rolinherit
                FROM pg_catalog.pg_roles
                WHERE rolname = %s
                """,
                (APPLICATION_ROLE_NAME,),
            )
            attribute_row = cursor.fetchone()
            attributes = (
                None
                if attribute_row is None
                else ApplicationRoleAttributes(
                    rolsuper=bool(attribute_row[0]),
                    rolbypassrls=bool(attribute_row[1]),
                    rolcanlogin=bool(attribute_row[2]),
                    rolcreaterole=bool(attribute_row[3]),
                    rolcreatedb=bool(attribute_row[4]),
                    rolreplication=bool(attribute_row[5]),
                    rolinherit=bool(attribute_row[6]),
                )
            )

            cursor.execute(
                """
                SELECT member.rolname, granted.rolname,
                       membership.admin_option,
                       membership.inherit_option,
                       membership.set_option
                FROM pg_catalog.pg_auth_members AS membership
                JOIN pg_catalog.pg_roles AS member
                  ON member.oid = membership.member
                JOIN pg_catalog.pg_roles AS granted
                  ON granted.oid = membership.roleid
                ORDER BY 1, 2
                """
            )
            memberships = tuple(
                _MembershipEdge(
                    member=str(row[0]),
                    role=str(row[1]),
                    admin_option=bool(row[2]),
                    inherit_option=bool(row[3]),
                    set_option=bool(row[4]),
                )
                for row in cursor.fetchall()
            )

            cursor.execute(
                """
                SELECT rolname, rolsuper, rolbypassrls
                FROM pg_catalog.pg_roles
                WHERE rolsuper OR rolbypassrls
                """
            )
            dangerous_roles = {str(row[0]) for row in cursor.fetchall()}

            cursor.execute(
                """
                SELECT owner.rolname
                FROM pg_catalog.pg_namespace AS namespace
                JOIN pg_catalog.pg_roles AS owner
                  ON owner.oid = namespace.nspowner
                WHERE namespace.nspname = ANY(%s)
                """,
                (list(PROTECTED_SCHEMAS),),
            )
            dangerous_roles.update(str(row[0]) for row in cursor.fetchall())

            table_schemas = [schema for schema, _ in PROTECTED_TABLES]
            table_names = [table for _, table in PROTECTED_TABLES]
            cursor.execute(
                """
                SELECT owner.rolname
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                JOIN pg_catalog.pg_roles AS owner
                  ON owner.oid = relation.relowner
                WHERE relation.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND (namespace.nspname, relation.relname) IN (
                      SELECT * FROM unnest(%s::text[], %s::text[])
                  )
                """,
                (table_schemas, table_names),
            )
            dangerous_roles.update(str(row[0]) for row in cursor.fetchall())

            function_schemas = [schema for schema, _, _ in PROTECTED_FUNCTIONS]
            function_names = [function for _, function, _ in PROTECTED_FUNCTIONS]
            function_arguments = [arguments for _, _, arguments in PROTECTED_FUNCTIONS]
            cursor.execute(
                """
                SELECT owner.rolname
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                JOIN pg_catalog.pg_roles AS owner
                  ON owner.oid = routine.proowner
                WHERE (
                    namespace.nspname,
                    routine.proname,
                    pg_catalog.pg_get_function_identity_arguments(routine.oid)
                ) IN (
                    SELECT * FROM unnest(%s::text[], %s::text[], %s::text[])
                )
                """,
                (function_schemas, function_names, function_arguments),
            )
            dangerous_roles.update(str(row[0]) for row in cursor.fetchall())

        observation = _ConnectionObservation(
            session_user=str(identity_row[0]),
            current_user=str(identity_row[1]),
            attributes=attributes,
            tenant_id=None if identity_row[2] is None else str(identity_row[2]),
            memberships=memberships,
            dangerous_roles=frozenset(dangerous_roles),
        )
    except psycopg.Error as error:
        inspection_error = error
    finally:
        try:
            connection.rollback()
        except psycopg.Error as error:
            raise DatabaseConfigurationError(
                "アプリ用接続の真正性検査を rollback できない"
            ) from error

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise DatabaseConfigurationError(
            "アプリ用接続の真正性検査後もトランザクションが idle でない"
        )
    if inspection_error is not None:
        raise DatabaseConfigurationError(
            "アプリ用接続の真正性検査 SQL を完了できない"
        ) from inspection_error
    if observation is None:
        raise DatabaseConfigurationError("アプリ用接続の真正性を観測できない")

    violations = _connection_observation_violations(observation)
    if violations:
        raise DatabaseConfigurationError(
            "アプリ用接続の真正性検査に失敗: " + "; ".join(violations)
        )


def _verify_application_role_on_connect(
    dbapi_connection: object,
    _connection_record: object,
) -> None:
    """SQLAlchemy の物理接続イベントから真正性検査を呼び出す。"""
    if not isinstance(dbapi_connection, psycopg.Connection):
        raise DatabaseConfigurationError("psycopg 以外の DBAPI 接続を拒否した")
    _verify_application_role_connection(dbapi_connection)


def engine_connect_args(pooled: bool) -> dict[str, object]:
    """Pooler 利用有無から psycopg の接続引数を導出する。

    Args:
        pooled: Transaction pooler を経由するか。

    Returns:
        SQLAlchemy engine に渡す psycopg 接続引数。
    """
    if pooled:
        return {"prepare_threshold": None}
    return {}


def engine_connect_args_violations(
    pooled: bool, connect_args: Mapping[str, object]
) -> list[str]:
    """Pooler 設定と psycopg 接続引数の違反を返す。

    Args:
        pooled: Transaction pooler を経由するか。
        connect_args: 検査対象の psycopg 接続引数。

    Returns:
        検出した違反の一覧。
    """
    if pooled and (
        "prepare_threshold" not in connect_args
        or connect_args["prepare_threshold"] is not None
    ):
        return ["pooler 利用時は prepare_threshold=None が必要"]
    if not pooled and "prepare_threshold" in connect_args:
        return ["pooler 非利用時は prepare_threshold を指定しない"]
    return []


def _database_is_pooled(value: str) -> bool:
    """明示された pooler フラグを bool へ変換する。

    Args:
        value: 環境から取得済みの pooler フラグ。

    Returns:
        ``true`` なら True、``false`` なら False。

    Raises:
        DatabaseConfigurationError: ``true`` / ``false`` 以外の場合。
    """
    if value == "true":
        return True
    if value == "false":
        return False
    raise DatabaseConfigurationError(
        f"{_DATABASE_POOLED_VARIABLE} は true または false で指定する"
    )


def create_database_engine() -> Engine:
    """アプリケーション用 URL から SQLAlchemy engine を生成する。

    Returns:
        psycopg 3 を使用する同期 engine。
    """
    database_url = require_database_configuration(
        _DATABASE_URL_VARIABLE,
        os.environ.get(_DATABASE_URL_VARIABLE),
    )
    pooled_value = require_database_configuration(
        _DATABASE_POOLED_VARIABLE,
        os.environ.get(_DATABASE_POOLED_VARIABLE),
    )
    connect_args = engine_connect_args(_database_is_pooled(pooled_value))
    normalized_url = normalize_postgresql_url(database_url)
    engine = create_engine(normalized_url, connect_args=connect_args)
    event.listen(engine, "connect", _verify_application_role_on_connect)
    return engine
