"""共有越境経路のうち DB 層で表現できる拒否例を検証する。

``http-route-matrix.json`` の deny 6 セルは、``shared_screen`` と ``export``、
または ``shared_aggregate_export`` と ``screen`` の組合せ不一致を HTTP 層で
404 にするケースである。いずれも ``required_grant_ids`` は空であり、拒否理由は
付与ではない。一方、DB 関数は ``p_granularity`` だけを受け取り、呼出元の
``route_class`` や ``channel`` を観測できない。このため deny セル群は DB 層では
表現せず、所有者である ``TSK-217.http-cell.*`` に委ねる。本モジュールは deny
セルとの 1:1 対応も、その合格を満たしたという主張も行わない。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeAlias

import psycopg
import pytest
from psycopg import sql

from .conftest import ProvisionedCatalog
from .test_authz_runtime_positive import (
    _POSITIVE_CASES,
    _fetch_authorized_shared_rows,
    _insert_runtime_fixture,
    _PositiveRuntimeFixture,
    _ProbeInvocation,
    _ReturnedRow,
    _runtime_fixture_definition,
)

pytestmark = pytest.mark.requires_db

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_REJECTED_CONFIGS_PATH = _REPOSITORY_ROOT / "contracts/authz/rejected-configs.json"
_AUTHORIZED_SHARED_ROWS_REGPROCEDURE = (
    "authz_private.authorized_shared_rows(bigint,bigint[],text)"
)
_RETURN_SIGNATURE_GUARD = "return_signature"
_SELF_OWNERSHIP_GUARD = "self_ownership"
_TRUSTED_SEARCH_PATH_ROWS: Final[frozenset[str]] = frozenset({"trusted-row"})
_ATTACKER_SEARCH_PATH_ROWS: Final[frozenset[str]] = frozenset({"attacker-row"})


@dataclass(frozen=True, slots=True)
class _RejectedConfiguration:
    """凍結資産から読んだ不採用構成と実測結果。"""

    rejection_id: str
    configuration_id: str
    observed_result: str


@dataclass(frozen=True, slots=True)
class _StructurallyDeniedResource:
    """常時 404 資源と、その構造上の拒否方式。"""

    resource_id: str
    requirement_label: str
    guard_kind: str


# 典拠: docs/design/data-model.md §3-6 の認可行列下段、および要件正本
# FR-034 の認可行列下段。この定数自体を唯一の一覧とし、件数を別に保持しない。
_STRUCTURALLY_DENIED_RESOURCES: Final[tuple[_StructurallyDeniedResource, ...]] = (
    _StructurallyDeniedResource(
        "raw_pitch_records",
        "1球単位の生記録（FR-031 の88列CSVを含む）",
        _RETURN_SIGNATURE_GUARD,
    ),
    _StructurallyDeniedResource(
        "karte_findings",
        "カルテの所見",
        _RETURN_SIGNATURE_GUARD,
    ),
    _StructurallyDeniedResource(
        "third_party_opponent_data",
        "第三者として記録した対戦相手データ",
        _SELF_OWNERSHIP_GUARD,
    ),
    _StructurallyDeniedResource(
        "body_profile_distribution",
        "身体プロフィールの分布",
        _RETURN_SIGNATURE_GUARD,
    ),
)

_AUTHORIZED_RETURN_SIGNATURE: Final[tuple[tuple[str, str], ...]] = (
    ("tenant_id", "bigint"),
    ("resource_kind", "text"),
    ("ownership_kind", "text"),
    ("payload", "jsonb"),
)

if len({resource.resource_id for resource in _STRUCTURALLY_DENIED_RESOURCES}) != len(
    _STRUCTURALLY_DENIED_RESOURCES
):
    raise AssertionError("常時404資源のresource_idが重複している")
if {resource.guard_kind for resource in _STRUCTURALLY_DENIED_RESOURCES} != {
    _RETURN_SIGNATURE_GUARD,
    _SELF_OWNERSHIP_GUARD,
}:
    raise AssertionError("常時404資源の構造上の拒否方式が閉じていない")


def _required_string(value: object, label: str) -> str:
    """資産値から空でない文字列を取得する。

    Args:
        value: 検査対象の資産値。
        label: エラーへ付ける資産位置。

    Returns:
        空でない文字列。
    """
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{label}は空でない文字列でなければならない")
    return value


def _load_rejected_configurations() -> tuple[_RejectedConfiguration, ...]:
    """不採用構成の全件を凍結資産の ``rejections`` 配列から読む。

    Returns:
        資産順の不採用構成。件数は配列からのみ導出する。
    """
    try:
        asset = json.loads(_REJECTED_CONFIGS_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AssertionError(f"不採用構成資産を読めない: {error}") from error
    if not isinstance(asset, dict):
        raise AssertionError("不採用構成資産はJSON objectでなければならない")
    rows = asset.get("rejections")
    if (
        not isinstance(rows, list)
        or not rows
        or not all(isinstance(row, dict) for row in rows)
    ):
        raise AssertionError("rejected-configs.rejectionsは空でないobject配列が必要")

    configurations = tuple(
        _RejectedConfiguration(
            rejection_id=_required_string(
                row.get("rejection_id"), "rejections.rejection_id"
            ),
            configuration_id=_required_string(
                row.get("configuration_id"), "rejections.configuration_id"
            ),
            observed_result=_required_string(
                row.get("observed_result"), "rejections.observed_result"
            ),
        )
        for row in rows
        if isinstance(row, dict)
    )
    rejection_ids = tuple(case.rejection_id for case in configurations)
    configuration_ids = tuple(case.configuration_id for case in configurations)
    if len(rejection_ids) != len(set(rejection_ids)):
        raise AssertionError("rejection_idが重複している")
    if len(configuration_ids) != len(set(configuration_ids)):
        raise AssertionError("configuration_idが重複している")
    return configurations


def _shared_runtime_scenario(
    provisioned_catalog: ProvisionedCatalog,
) -> tuple[_PositiveRuntimeFixture, _ProbeInvocation]:
    """ステップ 7 の fixture 定義を拒否例用クラスタへ投入する。

    Args:
        provisioned_catalog: 適用済みの使い捨て構成。

    Returns:
        共通 fixture と、非共有対象を含む主呼び出し。
    """
    fixture, invocation = _shared_runtime_scenario_definition()
    _insert_runtime_fixture(provisioned_catalog, fixture)
    return fixture, invocation


def _shared_runtime_scenario_definition() -> tuple[
    _PositiveRuntimeFixture, _ProbeInvocation
]:
    """ステップ 7 の fixture からステップ 8 の拒否シナリオを選ぶ。

    Returns:
        共通 fixture と、非共有対象を含む主呼び出し。
    """
    case = next(iter(_POSITIVE_CASES))
    fixture = _runtime_fixture_definition(case)
    unshared_tenant_ids = {
        row.tenant_id
        for row in fixture.business_rows
        if row.exclusion_kind == "target_grant_incomplete"
    }
    if not unshared_tenant_ids:
        raise AssertionError("ステップ7 fixtureに対象側非共有行がない")
    matching_invocations = tuple(
        invocation
        for invocation in fixture.invocations
        if unshared_tenant_ids.intersection(invocation.target_tenant_ids)
    )
    try:
        (invocation,) = matching_invocations
    except ValueError as error:
        raise AssertionError(
            "対象側非共有行の主呼び出しを一意に導出できない"
        ) from error
    return fixture, invocation


def _fetch_shared_rows_and_rollback(
    connection: psycopg.Connection[Any],
    fixture: _PositiveRuntimeFixture,
    invocation: _ProbeInvocation,
) -> frozenset[_ReturnedRow]:
    """共有関数を実行し、トランザクションを閉じて結果を返す。

    Args:
        connection: 実際の LOGIN ロールで認証した接続。
        fixture: ステップ 7 の共通 fixture。
        invocation: 呼び出すグループと対象集合。

    Returns:
        正規化済みの返却行集合。
    """
    try:
        return _fetch_authorized_shared_rows(connection, fixture, invocation)
    finally:
        connection.rollback()


def _red_message(case: _RejectedConfiguration) -> str:
    """資産由来の rejection ID と実測結果だけで失敗理由を作る。"""
    return f"{case.rejection_id}: {case.observed_result}"


def _assert_expected_rows(
    actual: frozenset[_ReturnedRow],
    expected: frozenset[_ReturnedRow],
    failure_message: str,
) -> None:
    """採用構成の返却集合を検査する。

    Args:
        actual: 実 PostgreSQL の返却集合。
        expected: fixture 由来の期待集合。
        failure_message: 不一致時の理由。
    """
    assert actual == expected, failure_message


def _grant_outsider_schema_usage(
    provisioned_catalog: ProvisionedCatalog,
    outsider_role_connection: psycopg.Connection[Any],
) -> None:
    """関数 ACL だけを検査できるよう無所属ロールへ schema 到達性を与える。"""
    with outsider_role_connection.cursor() as cursor:
        cursor.execute("SELECT session_user")
        row = cursor.fetchone()
    outsider_role_connection.rollback()
    if row is None or not isinstance(row[0], str):
        raise AssertionError("無所属ロールのsession_userを取得できない")
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA authz_private TO {}").format(
                sql.Identifier(row[0])
            )
        )
    provisioned_catalog.admin.commit()


def _assert_public_execution_denied(
    connection: psycopg.Connection[Any],
    fixture: _PositiveRuntimeFixture,
    invocation: _ProbeInvocation,
    failure_message: str,
) -> None:
    """無所属ロールによる共有関数実行が権限エラーになることを要求する。

    Args:
        connection: 無所属ロール自身で認証した接続。
        fixture: ステップ 7 の共通 fixture。
        invocation: 越境行を返し得る呼び出し。
        failure_message: 実行できた場合の理由。
    """
    try:
        _fetch_authorized_shared_rows(connection, fixture, invocation)
    except psycopg.errors.InsufficientPrivilege:
        connection.rollback()
        return
    connection.rollback()
    raise AssertionError(failure_message)


def _function_definition(provisioned_catalog: ProvisionedCatalog) -> str:
    """適用済み共有関数の定義を ``pg_proc`` から得る。"""
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure(%s))",
            (_AUTHORIZED_SHARED_ROWS_REGPROCEDURE,),
        )
        row = cursor.fetchone()
    provisioned_catalog.admin.rollback()
    if row is None or not isinstance(row[0], str):
        raise AssertionError("authorized_shared_rowsの関数定義を取得できない")
    return row[0]


def _function_owner(provisioned_catalog: ProvisionedCatalog) -> str:
    """適用済み共有関数の所有ロールをカタログから得る。"""
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT owner.rolname
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = routine.proowner
            WHERE routine.oid = pg_catalog.to_regprocedure(%s)
            """,
            (_AUTHORIZED_SHARED_ROWS_REGPROCEDURE,),
        )
        row = cursor.fetchone()
    provisioned_catalog.admin.rollback()
    if row is None or not isinstance(row[0], str):
        raise AssertionError("authorized_shared_rowsの所有ロールを取得できない")
    return row[0]


def _verify_without_bypassrls_is_red(
    case: _RejectedConfiguration,
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
    outsider_role_connection: psycopg.Connection[Any],
    fixture: _PositiveRuntimeFixture,
    invocation: _ProbeInvocation,
) -> None:
    """関数所有者から BYPASSRLS を外すと正例の行が消えることを示す。"""
    del outsider_role_connection
    baseline = _fetch_shared_rows_and_rollback(app_role_connection, fixture, invocation)
    _assert_expected_rows(baseline, invocation.expected_rows, "採用構成の正例が不成立")

    owner = _function_owner(provisioned_catalog)
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER ROLE {} NOBYPASSRLS").format(sql.Identifier(owner))
        )
    provisioned_catalog.admin.commit()

    mutated = _fetch_shared_rows_and_rollback(app_role_connection, fixture, invocation)
    message = _red_message(case)
    with pytest.raises(AssertionError, match=re.escape(message)):
        _assert_expected_rows(mutated, invocation.expected_rows, message)
    assert mutated == frozenset(), case.observed_result


def _recreate_function_with_default_acl(
    provisioned_catalog: ProvisionedCatalog,
) -> None:
    """共有関数を drop/create し、新規関数の PUBLIC 既定 ACL へ戻す。"""
    definition = _function_definition(provisioned_catalog)
    create_definition = definition.replace(
        "CREATE OR REPLACE FUNCTION",
        "CREATE FUNCTION",
        1,
    )
    if create_definition == definition:
        raise AssertionError("pg_get_functiondefのCREATE句を変換できない")
    owner = _function_owner(provisioned_catalog)
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            "DROP FUNCTION authz_private.authorized_shared_rows(BIGINT, BIGINT[], TEXT)"
        )
        cursor.execute(create_definition.encode("utf-8"))
        cursor.execute(
            sql.SQL(
                "ALTER FUNCTION authz_private.authorized_shared_rows("
                "BIGINT, BIGINT[], TEXT) OWNER TO {}"
            ).format(sql.Identifier(owner))
        )
    provisioned_catalog.admin.commit()


def _public_acl_state(
    provisioned_catalog: ProvisionedCatalog,
) -> tuple[bool, bool]:
    """共有関数が既定 ACL か、および PUBLIC が実行可能かを返す。"""
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT routine.proacl IS NULL,
                   EXISTS (
                       SELECT 1
                       FROM pg_catalog.aclexplode(
                           COALESCE(
                               routine.proacl,
                               pg_catalog.acldefault('f', routine.proowner)
                           )
                       ) AS privilege
                       WHERE privilege.grantee = 0
                         AND privilege.privilege_type = 'EXECUTE'
                   )
            FROM pg_catalog.pg_proc AS routine
            WHERE routine.oid = pg_catalog.to_regprocedure(%s)
            """,
            (_AUTHORIZED_SHARED_ROWS_REGPROCEDURE,),
        )
        row = cursor.fetchone()
    provisioned_catalog.admin.rollback()
    if row is None:
        raise AssertionError("authorized_shared_rowsのACLを取得できない")
    return bool(row[0]), bool(row[1])


def _verify_public_execute_default_is_red(
    case: _RejectedConfiguration,
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
    outsider_role_connection: psycopg.Connection[Any],
    fixture: _PositiveRuntimeFixture,
    invocation: _ProbeInvocation,
) -> None:
    """関数を PUBLIC 既定 ACL に戻すと無所属ロールが越境することを示す。"""
    del app_role_connection
    _grant_outsider_schema_usage(provisioned_catalog, outsider_role_connection)
    _assert_public_execution_denied(
        outsider_role_connection,
        fixture,
        invocation,
        "採用構成でPUBLICが共有関数を実行できた",
    )

    _recreate_function_with_default_acl(provisioned_catalog)
    assert _public_acl_state(provisioned_catalog) == (True, True)
    message = _red_message(case)
    with pytest.raises(AssertionError, match=re.escape(message)):
        _assert_public_execution_denied(
            outsider_role_connection,
            fixture,
            invocation,
            message,
        )
    mutated = _fetch_shared_rows_and_rollback(
        outsider_role_connection, fixture, invocation
    )
    assert mutated == invocation.expected_rows, case.observed_result
    assert mutated, case.observed_result


def _connection_role(connection: psycopg.Connection[Any]) -> str:
    """実接続の ``session_user`` を返す。"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT session_user")
        row = cursor.fetchone()
    connection.rollback()
    if row is None or not isinstance(row[0], str):
        raise AssertionError("実接続のsession_userを取得できない")
    return row[0]


def _install_search_path_probe(
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """信頼済み表と同名の一時表を持つ search_path 攻撃条件を作る。"""
    owner = _function_owner(provisioned_catalog)
    app_role = _connection_role(app_role_connection)
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE authz_private.search_path_probe_rows (
                marker TEXT NOT NULL
            )
            """
        )
        cursor.executemany(
            "INSERT INTO authz_private.search_path_probe_rows (marker) VALUES (%s)",
            tuple((marker,) for marker in _TRUSTED_SEARCH_PATH_ROWS),
        )
        cursor.execute(
            sql.SQL(
                "GRANT SELECT ON TABLE authz_private.search_path_probe_rows TO {}"
            ).format(sql.Identifier(owner))
        )
        # 文字列形式の SQL body は実行時に relation 名を解決するため、
        # pg_temp の位置による差を一時リレーションで観測できる。
        cursor.execute(
            """
            CREATE FUNCTION authz_private.search_path_relation_probe()
            RETURNS TABLE (marker TEXT)
            LANGUAGE SQL
            STABLE
            SECURITY DEFINER
            SET search_path = pg_catalog, authz_private, pg_temp
            AS 'SELECT marker FROM search_path_probe_rows'
            """
        )
        cursor.execute(
            sql.SQL(
                "ALTER FUNCTION authz_private.search_path_relation_probe() OWNER TO {}"
            ).format(sql.Identifier(owner))
        )
        cursor.execute(
            """
            REVOKE ALL PRIVILEGES
                ON FUNCTION authz_private.search_path_relation_probe()
                FROM PUBLIC
            """
        )
        cursor.execute(
            sql.SQL(
                "GRANT EXECUTE ON FUNCTION "
                "authz_private.search_path_relation_probe() TO {}"
            ).format(sql.Identifier(app_role))
        )
    provisioned_catalog.admin.commit()

    with app_role_connection.cursor() as cursor:
        cursor.execute(
            "CREATE TEMPORARY TABLE search_path_probe_rows (marker TEXT NOT NULL)"
        )
        cursor.executemany(
            "INSERT INTO search_path_probe_rows (marker) VALUES (%s)",
            tuple((marker,) for marker in _ATTACKER_SEARCH_PATH_ROWS),
        )
        cursor.execute(
            sql.SQL("GRANT SELECT ON TABLE search_path_probe_rows TO {}").format(
                sql.Identifier(owner)
            )
        )
    app_role_connection.commit()


def _search_path_probe_rows(
    app_role_connection: psycopg.Connection[Any],
) -> frozenset[str]:
    """一時リレーションを置いた実接続から probe 関数を呼ぶ。"""
    try:
        with app_role_connection.cursor() as cursor:
            cursor.execute(
                "SELECT marker FROM authz_private.search_path_relation_probe()"
            )
            return frozenset(str(row[0]) for row in cursor.fetchall())
    finally:
        app_role_connection.rollback()


def _verify_missing_explicit_pg_temp_is_red(
    case: _RejectedConfiguration,
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
    outsider_role_connection: psycopg.Connection[Any],
    fixture: _PositiveRuntimeFixture,
    invocation: _ProbeInvocation,
) -> None:
    """末尾 pg_temp を外すと同名一時リレーションが先に解決されることを示す。"""
    del outsider_role_connection, fixture, invocation
    _install_search_path_probe(provisioned_catalog, app_role_connection)
    baseline = _search_path_probe_rows(app_role_connection)
    _assert_search_path_rows(
        baseline,
        _TRUSTED_SEARCH_PATH_ROWS,
        "採用構成で一時リレーションの乗っ取りが成立した",
    )

    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            """
            ALTER FUNCTION authz_private.search_path_relation_probe()
            SET search_path = pg_catalog, authz_private
            """
        )
    provisioned_catalog.admin.commit()
    mutated = _search_path_probe_rows(app_role_connection)
    message = _red_message(case)
    with pytest.raises(AssertionError, match=re.escape(message)):
        _assert_search_path_rows(mutated, _TRUSTED_SEARCH_PATH_ROWS, message)
    assert mutated == _ATTACKER_SEARCH_PATH_ROWS, case.observed_result


def _assert_search_path_rows(
    actual: frozenset[str],
    expected: frozenset[str],
    failure_message: str,
) -> None:
    """search_path probe が信頼済み relation だけを見たことを要求する。"""
    assert actual == expected, failure_message


_RejectionVerifier: TypeAlias = Callable[
    [
        _RejectedConfiguration,
        ProvisionedCatalog,
        psycopg.Connection[Any],
        psycopg.Connection[Any],
        _PositiveRuntimeFixture,
        _ProbeInvocation,
    ],
    None,
]

_REJECTION_VERIFIERS: Final[dict[str, _RejectionVerifier]] = {
    "SECURITY_DEFINER_WITHOUT_BYPASSRLS_OWNER": _verify_without_bypassrls_is_red,
    "FUNCTION_WITH_PUBLIC_EXECUTE_DEFAULT": _verify_public_execute_default_is_red,
    "SEARCH_PATH_WITHOUT_EXPLICIT_TRAILING_PG_TEMP": (
        _verify_missing_explicit_pg_temp_is_red
    ),
}
_REJECTED_CONFIGURATIONS = _load_rejected_configurations()
if {case.configuration_id for case in _REJECTED_CONFIGURATIONS} != set(
    _REJECTION_VERIFIERS
):
    raise AssertionError("資産の不採用構成と実行時変異がexact-set一致しない")


def test_app_role_cannot_read_other_tenant_rows_without_function(
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """最低要求①: アプリ用ロールの直接 SELECT を自テナント行に限定する。"""
    requester_tenant_id = 8100
    other_tenant_id = 8101
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO probe_data.probe_business_rows
                (tenant_id, resource_kind, ownership_kind, payload)
            VALUES (%s, 'team_statistics', 'self', '{}'::JSONB)
            """,
            ((requester_tenant_id,), (other_tenant_id,)),
        )
    provisioned_catalog.admin.commit()

    try:
        with app_role_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                (str(requester_tenant_id),),
            )
            cursor.execute("SELECT tenant_id FROM probe_data.probe_business_rows")
            actual_tenant_ids = {int(row[0]) for row in cursor.fetchall()}
    finally:
        app_role_connection.rollback()
    assert actual_tenant_ids == {requester_tenant_id}
    assert other_tenant_id not in actual_tenant_ids


def test_public_cannot_execute_shared_function(
    provisioned_catalog: ProvisionedCatalog,
    outsider_role_connection: psycopg.Connection[Any],
) -> None:
    """最低要求②: schema 到達可能な無所属ロールでも PUBLIC 実行を拒否する。"""
    _grant_outsider_schema_usage(provisioned_catalog, outsider_role_connection)
    with outsider_role_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_proc AS routine
                CROSS JOIN LATERAL pg_catalog.aclexplode(
                    COALESCE(
                        routine.proacl,
                        pg_catalog.acldefault('f', routine.proowner)
                    )
                ) AS privilege
                WHERE routine.oid = pg_catalog.to_regprocedure(%s)
                  AND privilege.grantee = 0
                  AND privilege.privilege_type = 'EXECUTE'
            )
            """,
            (_AUTHORIZED_SHARED_ROWS_REGPROCEDURE,),
        )
        public_execute = cursor.fetchone()
    outsider_role_connection.rollback()
    assert public_execute == (False,)

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with outsider_role_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM authz_private.authorized_shared_rows(
                    1::BIGINT,
                    ARRAY[2::BIGINT],
                    'team_statistics'::TEXT
                )
                """
            )
    outsider_role_connection.rollback()


def test_explicit_trailing_pg_temp_blocks_temporary_relation_hijack(
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """最低要求③: 末尾 pg_temp が同名一時リレーションの乗っ取りを防ぐ。"""
    _install_search_path_probe(provisioned_catalog, app_role_connection)
    actual = _search_path_probe_rows(app_role_connection)
    assert actual == _TRUSTED_SEARCH_PATH_ROWS
    assert actual.isdisjoint(_ATTACKER_SEARCH_PATH_ROWS)


def test_target_without_complete_grants_is_excluded_independently(
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """最低要求④: 要求元が付与していても対象側が非共有なら単独で拒否する。"""
    fixture, invocation = _shared_runtime_scenario(provisioned_catalog)
    unshared_tenant_ids = {
        row.tenant_id
        for row in fixture.business_rows
        if row.exclusion_kind == "target_grant_incomplete"
    }
    requester_enabled_grants = {
        grant_kind
        for group_id, tenant_id, grant_kind, enabled in fixture.grants
        if group_id == invocation.group_id
        and tenant_id == fixture.requester_tenant_id
        and enabled
    }
    case = next(
        case for case in _POSITIVE_CASES if case.granularity == fixture.granularity
    )
    required_grants = set(case.required_grant_kinds)
    assert requester_enabled_grants == required_grants
    for unshared_tenant_id in unshared_tenant_ids:
        target_enabled_grants = {
            grant_kind
            for group_id, tenant_id, grant_kind, enabled in fixture.grants
            if group_id == invocation.group_id
            and tenant_id == unshared_tenant_id
            and enabled
        }
        assert target_enabled_grants < required_grants

    actual = _fetch_shared_rows_and_rollback(app_role_connection, fixture, invocation)
    assert actual == invocation.expected_rows
    assert unshared_tenant_ids.isdisjoint(row.tenant_id for row in actual)


def test_structurally_denied_resources_are_absent_from_return_signature(
    provisioned_catalog: ProvisionedCatalog,
) -> None:
    """生記録・所見・身体分布に専用返却列がないことを pg_proc で示す。"""
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT routine.proargnames[position.index],
                   pg_catalog.format_type(
                       routine.proallargtypes[position.index],
                       NULL
                   )
            FROM pg_catalog.pg_proc AS routine
            CROSS JOIN LATERAL pg_catalog.generate_subscripts(
                routine.proallargtypes,
                1
            ) AS position(index)
            WHERE routine.oid = pg_catalog.to_regprocedure(%s)
              AND routine.proargmodes[position.index] = 't'
            ORDER BY position.index
            """,
            (_AUTHORIZED_SHARED_ROWS_REGPROCEDURE,),
        )
        actual_signature = tuple(
            (str(name), str(type_name)) for name, type_name in cursor.fetchall()
        )
    provisioned_catalog.admin.rollback()

    assert actual_signature == _AUTHORIZED_RETURN_SIGNATURE
    returned_column_ids = {name for name, _ in actual_signature}
    for resource in _STRUCTURALLY_DENIED_RESOURCES:
        if resource.guard_kind != _RETURN_SIGNATURE_GUARD:
            continue
        assert resource.resource_id not in returned_column_ids, (
            resource.requirement_label
        )


def _replace_self_ownership_filter(
    provisioned_catalog: ProvisionedCatalog,
) -> None:
    """第三者データ拒否の ``ownership_kind = 'self'`` だけを外す。"""
    definition = _function_definition(provisioned_catalog)
    mutated, replacements = re.subn(
        r"business_row\.ownership_kind\s*=\s*'self'(?:::(?:pg_catalog\.)?text)?",
        "TRUE",
        definition,
        count=1,
        flags=re.IGNORECASE,
    )
    if replacements != 1:
        raise AssertionError("ownership_kind='self'の絞り込みを一意に変異できない")
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.execute(mutated.encode("utf-8"))
    provisioned_catalog.admin.commit()


def test_removing_self_ownership_filter_exposes_third_party_row(
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """第三者データは self 絞り込みを外すと返ることを負例で示す。"""
    third_party_resources = tuple(
        resource
        for resource in _STRUCTURALLY_DENIED_RESOURCES
        if resource.guard_kind == _SELF_OWNERSHIP_GUARD
    )
    try:
        (third_party_resource,) = third_party_resources
    except ValueError as error:
        raise AssertionError(
            "self所有絞り込みの対象資源を一意に導出できない"
        ) from error
    fixture, invocation = _shared_runtime_scenario(provisioned_catalog)
    third_party_rows = frozenset(
        row.returned_row()
        for row in fixture.business_rows
        if row.exclusion_kind == "non_self_ownership"
        and row.tenant_id in invocation.target_tenant_ids
    )
    if not third_party_rows:
        raise AssertionError(
            f"ステップ7 fixtureに{third_party_resource.requirement_label}の行がない"
        )
    baseline = _fetch_shared_rows_and_rollback(app_role_connection, fixture, invocation)
    assert baseline == invocation.expected_rows
    assert baseline.isdisjoint(third_party_rows), third_party_resource.requirement_label

    _replace_self_ownership_filter(provisioned_catalog)
    mutated = _fetch_shared_rows_and_rollback(app_role_connection, fixture, invocation)
    assert mutated == invocation.expected_rows | third_party_rows
    assert third_party_rows <= mutated


@pytest.mark.parametrize(
    "case",
    _REJECTED_CONFIGURATIONS,
    ids=lambda case: case.rejection_id,
)
def test_rejected_configurations_make_runtime_acceptance_red(
    case: _RejectedConfiguration,
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
    outsider_role_connection: psycopg.Connection[Any],
) -> None:
    """資産の各不採用構成へ戻し、対応する実行時合格条件を red にする。"""
    fixture, invocation = _shared_runtime_scenario(provisioned_catalog)
    verifier = _REJECTION_VERIFIERS[case.configuration_id]
    verifier(
        case,
        provisioned_catalog,
        app_role_connection,
        outsider_role_connection,
        fixture,
        invocation,
    )
