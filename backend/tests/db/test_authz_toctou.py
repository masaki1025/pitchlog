"""代表管理関数の TOCTOU 封鎖方式と線形化点を検証する。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pitchlog.authz.catalog import observe_function_dependency_relations

from .conftest import ProvisionedCatalog
from .test_authz_management_probe import (
    _BASELINE_FIXTURE,
    _DECISION_NOTE_RE,
    _MANAGEMENT_CONTRACT,
    _assert_failure_case_contract,
    _decision_ids_from_body,
    _effect_count,
    _insert_management_fixture,
    _invoke_management_function,
    _management_contract,
    _management_function_oid,
    _ManagementContract,
    _ManagementFixture,
)
from .test_authz_precondition_matrix import _assert_same_identifier_set, _only
from .test_authz_runtime_positive import _object_rows, _string, _string_tuple

pytestmark = pytest.mark.requires_db

_MUTANT_FUNCTION_ID = "toctou_separated_mutant"
_LOCK_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)\bFOR\s+UPDATE\b"),
    re.compile(r"(?i)\bFOR\s+SHARE\b"),
    re.compile(r"(?i)\bLOCK\s+TABLE\b"),
    re.compile(r"(?i)\bpg_advisory_[a-z_0-9]*\s*\("),
)

type _Relation = tuple[str, str]


@dataclass(frozen=True, slots=True)
class _DependencyContract:
    """資産から導出した管理関数の relation 依存契約。"""

    expected: frozenset[_Relation]
    authorization_sources: frozenset[_Relation]
    effect_targets: frozenset[_Relation]
    membership: _Relation
    grant: _Relation
    effect: _Relation


@dataclass(frozen=True, slots=True)
class _FunctionSqlBody:
    """PostgreSQL が保持する解析済み SQL 関数 body。"""

    is_preparsed: bool
    source: str | None


@dataclass(frozen=True, slots=True)
class _BlockingStrategy:
    """関数の依存集合と SQL body から判定した TOCTOU 封鎖方式。"""

    statement_count: int
    has_row_lock: bool
    has_authorization_embedding: bool


@dataclass(frozen=True, slots=True)
class _BarrierCase:
    """2 文 mutant の間へ無効化を介入させるかを表す。"""

    intervene: bool


@dataclass(frozen=True, slots=True)
class _MutantObservation:
    """2 文 mutant の認可読みと副作用書きの観測結果。"""

    authorized_before_barrier: bool
    grant_enabled_before_effect: bool
    inserted_rows: tuple[tuple[Any, ...], ...]
    effect_count_before: int
    effect_count_after: int


@dataclass(frozen=True, slots=True)
class _LinearizationOrder:
    """単一文の前後どちらで付与を無効化するかを表す。"""

    disable_before_call: bool


def _relation_ids(relations: frozenset[_Relation] | set[_Relation]) -> frozenset[str]:
    """Relation 組を SHA-256 exact-set 比較用の識別子集合へ変換する。"""
    return frozenset(".".join(relation) for relation in relations)


def _assert_same_relations(
    actual: frozenset[_Relation] | set[_Relation],
    expected: frozenset[_Relation] | set[_Relation],
    label: str,
) -> None:
    """Relation 集合を値と SHA-256 の双方で exact-set 比較する。"""
    _assert_same_identifier_set(
        _relation_ids(actual),
        _relation_ids(expected),
        label,
    )


def _dependency_contract(
    asset: dict[str, object], contract: _ManagementContract
) -> _DependencyContract:
    """依存表と認可・副作用の役割を DDL 資産だけから導出する。"""
    function = _only(
        tuple(
            row
            for row in _object_rows(asset.get("functions"), "functions")
            if row.get("function_id") == contract.function_id
        ),
        f"管理関数 {contract.function_id}",
    )
    if not isinstance(function, dict):
        raise AssertionError("管理関数資産がobjectでない")

    tables = _object_rows(asset.get("tables"), "tables")
    table_by_id = {
        _string(row.get("table_id"), "tables.table_id"): row for row in tables
    }
    if len(table_by_id) != len(tables):
        raise AssertionError("tables.table_idが重複している")

    dependency_table_ids = frozenset(
        _string_tuple(
            function.get("dependency_table_ids"),
            f"{contract.function_id}.dependency_table_ids",
        )
    )
    missing_table_ids = dependency_table_ids - table_by_id.keys()
    if missing_table_ids:
        raise AssertionError(f"依存表がtablesに存在しない: {sorted(missing_table_ids)}")

    relation_by_table_id: dict[str, _Relation] = {
        table_id: (
            _string(table_by_id[table_id].get("schema_id"), f"{table_id}.schema_id"),
            table_id,
        )
        for table_id in dependency_table_ids
    }
    authorization_table_ids: set[str] = set()
    effect_table_ids: set[str] = set()
    for access in _object_rows(
        function.get("owner_dependency_acl"),
        f"{contract.function_id}.owner_dependency_acl",
    ):
        table_id = _string(
            access.get("table_id"),
            f"{contract.function_id}.owner_dependency_acl.table_id",
        )
        privileges = frozenset(
            privilege.upper()
            for privilege in _string_tuple(
                access.get("privilege_ids"),
                f"{contract.function_id}.{table_id}.privilege_ids",
            )
        )
        if "SELECT" in privileges:
            authorization_table_ids.add(table_id)
        if "INSERT" in privileges:
            effect_table_ids.add(table_id)

    if not authorization_table_ids or not effect_table_ids:
        raise AssertionError("認可供給元または副作用対象を資産から導出できない")
    if authorization_table_ids & effect_table_ids:
        raise AssertionError("認可供給元と副作用対象が分離していない")
    _assert_same_identifier_set(
        frozenset(authorization_table_ids | effect_table_ids),
        dependency_table_ids,
        "管理関数ACLとdependency_table_ids",
    )

    authorization_sources = frozenset(
        relation_by_table_id[table_id] for table_id in authorization_table_ids
    )
    effect_targets = frozenset(
        relation_by_table_id[table_id] for table_id in effect_table_ids
    )
    expected = frozenset(relation_by_table_id.values())
    expected_effect = {
        (
            contract.table_privileges.schema_id,
            contract.table_privileges.table_id,
        )
    }
    _assert_same_relations(
        effect_targets,
        expected_effect,
        "ステップ11契約と管理関数の副作用対象",
    )

    grant_table_id = _only(
        tuple(
            table_id
            for table_id in authorization_table_ids
            if {"enabled", "grant_kind"}.issubset(
                set(
                    _string_tuple(
                        table_by_id[table_id].get("row_shape_ids"),
                        f"{table_id}.row_shape_ids",
                    )
                )
            )
        ),
        "grant行形状を持つ認可供給表",
    )
    membership_table_id = _only(
        tuple(
            table_id
            for table_id in authorization_table_ids
            if {"group_role", "status"}.issubset(
                set(
                    _string_tuple(
                        table_by_id[table_id].get("row_shape_ids"),
                        f"{table_id}.row_shape_ids",
                    )
                )
            )
        ),
        "membership行形状を持つ認可供給表",
    )
    effect = _only(tuple(effect_targets), "副作用対象relation")
    if not isinstance(grant_table_id, str) or not isinstance(membership_table_id, str):
        raise AssertionError("認可供給表IDが文字列でない")
    if not isinstance(effect, tuple) or len(effect) != 2:
        raise AssertionError("副作用対象relationが不正")
    return _DependencyContract(
        expected=expected,
        authorization_sources=authorization_sources,
        effect_targets=effect_targets,
        membership=relation_by_table_id[membership_table_id],
        grant=relation_by_table_id[grant_table_id],
        effect=effect,
    )


def _function_sql_body(
    connection: psycopg.Connection[Any], function_oid: int
) -> _FunctionSqlBody:
    """``prosqlbody`` の有無と deparse された SQL body だけを取得する。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT routine.prosqlbody IS NOT NULL,
                   pg_catalog.pg_get_function_sqlbody(routine.oid)
            FROM pg_catalog.pg_proc AS routine
            WHERE routine.oid = %s
            """,
            (function_oid,),
        )
        rows = tuple(cursor.fetchall())
    row = _only(rows, f"関数OID {function_oid} のSQL body")
    if (
        not isinstance(row, tuple)
        or len(row) != 2
        or not isinstance(row[0], bool)
        or (row[1] is not None and not isinstance(row[1], str))
    ):
        raise AssertionError("関数SQL bodyのカタログ値が不正")
    return _FunctionSqlBody(is_preparsed=row[0], source=row[1])


def _required_sql_body(body: _FunctionSqlBody) -> str:
    """解析済み SQL-standard body と非 NULL の出力を要求する。"""
    if not body.is_preparsed or body.source is None:
        raise AssertionError("prosqlbodyがNULLまたはSQL bodyを取得できない")
    return body.source


def _top_level_statement_count(sql_body: str) -> int:
    """文字列リテラルと括弧内を飛ばしてトップレベルの文数を数える。"""
    count = 0
    parenthesis_depth = 0
    in_string = False
    index = 0
    while index < len(sql_body):
        character = sql_body[index]
        following = sql_body[index + 1 : index + 2]
        if in_string:
            if character == "\\" and following:
                index += 2
                continue
            if character == "'" and following == "'":
                index += 2
                continue
            if character == "'":
                in_string = False
            index += 1
            continue
        if character == "'":
            in_string = True
        elif character == "(":
            parenthesis_depth += 1
        elif character == ")":
            parenthesis_depth -= 1
            if parenthesis_depth < 0:
                raise AssertionError("SQL bodyの括弧深さが負になった")
        elif character == ";" and parenthesis_depth == 0:
            count += 1
        index += 1
    if in_string or parenthesis_depth != 0:
        raise AssertionError("SQL bodyの文字列または括弧が閉じていない")
    if count == 0:
        raise AssertionError("SQL bodyのトップレベル文終端がない")
    return count


def _has_lock_strategy(sql_body: str) -> bool:
    """SQL body に lock 方式を示す文字列が存在するか返す。"""
    return any(pattern.search(sql_body) is not None for pattern in _LOCK_PATTERNS)


def _blocking_strategy(
    body: _FunctionSqlBody, *, dependencies_match: bool
) -> _BlockingStrategy:
    """解析済み body・文数・依存集合から 2 方式の実装有無を判定する。"""
    source = _required_sql_body(body)
    statement_count = _top_level_statement_count(source)
    return _BlockingStrategy(
        statement_count=statement_count,
        has_row_lock=_has_lock_strategy(source),
        has_authorization_embedding=(
            body.is_preparsed and statement_count == 1 and dependencies_match
        ),
    )


def _assert_blocking_strategy(strategy: _BlockingStrategy) -> None:
    """2 方式のどちらも実装されていない構成を拒否する。"""
    if not (strategy.has_row_lock or strategy.has_authorization_embedding):
        raise AssertionError("TOCTOU封鎖方式が実装されていない")


def _observed_dependencies(
    catalog: ProvisionedCatalog,
    function_oid: int,
    dependency_contract: _DependencyContract,
) -> frozenset[_Relation]:
    """ステップ 6 の公開観測関数で ``pg_depend`` を exact-set 検査する。"""
    observed = frozenset(
        observe_function_dependency_relations(catalog.admin, function_oid)
    )
    catalog.admin.rollback()
    _assert_same_relations(
        observed,
        dependency_contract.expected,
        "pg_dependと資産の管理関数依存relation",
    )
    assert dependency_contract.authorization_sources.issubset(observed)
    assert dependency_contract.effect_targets.issubset(observed)
    return observed


def _mutant_queries(
    dependency_contract: _DependencyContract,
) -> tuple[sql.Composed, sql.Composed]:
    """認可 SELECT と無条件副作用 INSERT を別々の実行文として作る。"""
    authorization = sql.SQL(
        """
        SELECT EXISTS (
            SELECT 1
            FROM {} AS caller_membership
            JOIN {} AS target_grant
              ON target_grant.group_id = caller_membership.group_id
            WHERE
                -- DECISION: MANAGEMENT_REQUESTER_CONTEXT_PRESENT
                %s IS NOT NULL
                AND
                -- DECISION: MANAGEMENT_GROUP_SCOPE
                caller_membership.group_id = %s
                AND
                -- DECISION: MANAGEMENT_REQUESTER_MEMBERSHIP_EFFECTIVE
                caller_membership.tenant_id = %s
                AND caller_membership.status = 'active'
                AND
                -- DECISION: MANAGEMENT_ADMIN_ROLE_REQUIRED
                caller_membership.group_role = 'admin'
                AND
                -- DECISION: MANAGEMENT_TARGET_GRANT_SCOPE
                target_grant.tenant_id = %s
                AND
                -- DECISION: MANAGEMENT_EFFECT_KIND_MATCH
                target_grant.grant_kind = %s
                AND
                -- DECISION: MANAGEMENT_TARGET_GRANT_ENABLED
                target_grant.enabled
        )
        """
    ).format(
        sql.Identifier(*dependency_contract.membership),
        sql.Identifier(*dependency_contract.grant),
    )
    effect = sql.SQL(
        """
        INSERT INTO {} (group_id, tenant_id, effect_kind)
        VALUES (%s, %s, %s)
        RETURNING TRUE
        """
    ).format(sql.Identifier(*dependency_contract.effect))
    return authorization, effect


def _replace_driver_parameters(source: str, expressions: tuple[str, ...]) -> str:
    """Psycopg placeholder を負例関数の引数参照へ順に置換する。"""
    if source.count("%s") != len(expressions):
        raise AssertionError("mutant SQLの引数数が一致しない")
    for expression in expressions:
        source = source.replace("%s", expression, 1)
    return source


def _separated_mutant_definition(
    contract: _ManagementContract,
    dependency_contract: _DependencyContract,
) -> str:
    """実行する 2 文と同じ SQL から lock なし負例関数定義を作る。"""
    authorization, effect = _mutant_queries(dependency_contract)
    authorization_source = _replace_driver_parameters(
        authorization.as_string(),
        (
            "p_requester_tenant_id",
            "p_group_id",
            "p_requester_tenant_id",
            "p_tenant_id",
            "p_effect_kind",
        ),
    ).strip()
    authorization_source += (
        "\nAND 'escaped '' quote; value' = 'escaped '' quote; value'"
    )
    effect_source = _replace_driver_parameters(
        effect.as_string(),
        ("p_group_id", "p_tenant_id", "p_effect_kind"),
    )
    function_name = sql.Identifier(
        contract.schema_id,
        _MUTANT_FUNCTION_ID,
    ).as_string()
    return f"""
        CREATE FUNCTION {function_name}(
            p_requester_tenant_id BIGINT,
            p_group_id BIGINT,
            p_tenant_id BIGINT,
            p_effect_kind TEXT
        )
        RETURNS BOOLEAN
        LANGUAGE SQL
        BEGIN ATOMIC
            {authorization_source};
            {effect_source};
        END
    """


def _create_separated_mutant(
    catalog: ProvisionedCatalog,
    contract: _ManagementContract,
    dependency_contract: _DependencyContract,
) -> int:
    """トップレベル 2 文を持つ検査用の別名関数を一時作成する。"""
    definition = _separated_mutant_definition(contract, dependency_contract)
    with catalog.admin.cursor() as cursor:
        cursor.execute(definition.encode("utf-8"))
        cursor.execute(
            """
            SELECT routine.oid
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = %s
              AND routine.proname = %s
            ORDER BY pg_catalog.pg_get_function_identity_arguments(routine.oid)
            """,
            (contract.schema_id, _MUTANT_FUNCTION_ID),
        )
        rows = tuple(cursor.fetchall())
    catalog.admin.commit()
    row = _only(rows, "2文mutant関数のOID")
    if not isinstance(row, tuple) or not row or not isinstance(row[0], int):
        raise AssertionError("2文mutant関数のOIDが整数でない")
    return row[0]


def _drop_separated_mutant(
    catalog: ProvisionedCatalog, contract: _ManagementContract
) -> None:
    """検査用の別名関数だけを削除する。"""
    catalog.admin.rollback()
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("DROP FUNCTION {}(BIGINT, BIGINT, BIGINT, TEXT)").format(
                sql.Identifier(contract.schema_id, _MUTANT_FUNCTION_ID)
            )
        )
    catalog.admin.commit()


def _assert_mutant_decision_set(authorization: sql.Composed) -> None:
    """2 文 mutant の認可条件を凍結済み DECISION 集合と照合する。"""
    source = authorization.as_string()
    decision_ids = tuple(
        match.group("decision_id") for match in _DECISION_NOTE_RE.finditer(source)
    )
    if not decision_ids or len(decision_ids) != len(set(decision_ids)):
        raise AssertionError("mutantのDECISIONノートが空または重複している")
    _assert_same_identifier_set(
        frozenset(decision_ids),
        _decision_ids_from_body(),
        "2文mutantと凍結済みbodyのDECISIONノート",
    )


def _grant_parameters(fixture: _ManagementFixture) -> tuple[object, ...]:
    """対象 grant 行を一意に選ぶパラメータ列を返す。"""
    return (
        fixture.grant_group_id,
        fixture.grant_tenant_id,
        fixture.grant_kind,
    )


def _target_grant_enabled(
    connection: psycopg.Connection[Any],
    dependency_contract: _DependencyContract,
    fixture: _ManagementFixture,
) -> bool:
    """対象 grant 行の enabled を別接続から一意に取得する。"""
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                """
                SELECT enabled
                FROM {}
                WHERE group_id = %s
                  AND tenant_id = %s
                  AND grant_kind = %s
                """
            ).format(sql.Identifier(*dependency_contract.grant)),
            _grant_parameters(fixture),
        )
        rows = tuple(cursor.fetchall())
    row = _only(rows, "対象grant行")
    if not isinstance(row, tuple) or not row or not isinstance(row[0], bool):
        raise AssertionError("対象grant行のenabledが真偽値でない")
    return row[0]


def _disable_target_grant(
    connection: psycopg.Connection[Any],
    dependency_contract: _DependencyContract,
    fixture: _ManagementFixture,
) -> None:
    """接続 B で有効な対象 grant 行だけを無効化して commit する。"""
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                """
                UPDATE {}
                SET enabled = FALSE
                WHERE group_id = %s
                  AND tenant_id = %s
                  AND grant_kind = %s
                  AND enabled
                RETURNING enabled
                """
            ).format(sql.Identifier(*dependency_contract.grant)),
            _grant_parameters(fixture),
        )
        rows = tuple(cursor.fetchall())
    row = _only(rows, "無効化する対象grant行")
    if row != (False,):
        raise AssertionError("対象grant行を無効化できない")
    connection.commit()


def _mutant_authorized(
    cursor: psycopg.Cursor[Any],
    authorization: sql.Composed,
    fixture: _ManagementFixture,
) -> bool:
    """接続 A の最初の文で全 DECISION 条件の認可結果を読む。"""
    cursor.execute(
        authorization,
        (
            fixture.requester_context_tenant_id,
            fixture.invocation_group_id,
            fixture.requester_context_tenant_id,
            fixture.invocation_target_tenant_id,
            fixture.invocation_effect_kind,
        ),
    )
    row = cursor.fetchone()
    if row is None or not isinstance(row[0], bool):
        raise AssertionError("mutantの認可結果を取得できない")
    return row[0]


def _run_separated_mutant(
    catalog: ProvisionedCatalog,
    contract: _ManagementContract,
    dependency_contract: _DependencyContract,
    fixture: _ManagementFixture,
    barrier: _BarrierCase,
) -> _MutantObservation:
    """接続 A の 2 文間へ接続 B の commit を決定的に挿入する。"""
    authorization, effect = _mutant_queries(dependency_contract)
    _assert_mutant_decision_set(authorization)
    effect_count_before = _effect_count(catalog, contract)
    catalog.admin.rollback()

    try:
        with catalog.admin.cursor() as cursor_a:
            cursor_a.execute("BEGIN")
            authorized = _mutant_authorized(cursor_a, authorization, fixture)

            if barrier.intervene:
                connection_b_dsn = make_conninfo(catalog.cluster.admin_dsn)
                with psycopg.connect(connection_b_dsn) as connection_b:
                    _disable_target_grant(
                        connection_b,
                        dependency_contract,
                        fixture,
                    )
                    grant_enabled = _target_grant_enabled(
                        connection_b,
                        dependency_contract,
                        fixture,
                    )
                    connection_b.rollback()
            else:
                grant_enabled = fixture.grant_enabled

            cursor_a.execute(
                effect,
                (
                    fixture.invocation_group_id,
                    fixture.invocation_target_tenant_id,
                    fixture.invocation_effect_kind,
                ),
            )
            inserted_rows = tuple(tuple(row) for row in cursor_a.fetchall())
        catalog.admin.commit()
    except Exception:
        catalog.admin.rollback()
        raise

    effect_count_after = _effect_count(catalog, contract)
    return _MutantObservation(
        authorized_before_barrier=authorized,
        grant_enabled_before_effect=grant_enabled,
        inserted_rows=inserted_rows,
        effect_count_before=effect_count_before,
        effect_count_after=effect_count_after,
    )


def _assert_toctou_exposed(observation: _MutantObservation) -> None:
    """認可後に失効したのに副作用が残った観測だけを TOCTOU と認める。"""
    assert observation.authorized_before_barrier, "barrier前の認可が真でない"
    assert not observation.grant_enabled_before_effect, (
        "副作用時にも付与が有効でありTOCTOUは成立していない"
    )
    assert observation.inserted_rows == ((True,),)
    assert observation.effect_count_after == (
        observation.effect_count_before + len(observation.inserted_rows)
    )


@pytest.fixture(
    params=(_BarrierCase(intervene=True), _BarrierCase(intervene=False)),
    ids=("barrier-between-statements", "barrier-removed-red-control"),
)
def mutant_barrier_case(request: pytest.FixtureRequest) -> _BarrierCase:
    """介入ありと、TOCTOU 主張が red になる介入なしを供給する。"""
    value = request.param
    if not isinstance(value, _BarrierCase):
        raise AssertionError("barrier fixtureの型が不正")
    return value


def test_management_function_has_single_statement_dependency_enclosure(
    provisioned_catalog: ProvisionedCatalog,
) -> None:
    """全依存表が解析済み単一文にあり、lock なしの方式②である。"""
    _assert_failure_case_contract()
    contract = _management_contract(provisioned_catalog.asset)
    assert contract == _MANAGEMENT_CONTRACT
    dependency_contract = _dependency_contract(provisioned_catalog.asset, contract)

    function_oid = _management_function_oid(provisioned_catalog, contract)
    observed = _observed_dependencies(
        provisioned_catalog,
        function_oid,
        dependency_contract,
    )
    body = _function_sql_body(provisioned_catalog.admin, function_oid)
    source = _required_sql_body(body)
    strategy = _blocking_strategy(
        body,
        dependencies_match=observed == dependency_contract.expected,
    )
    assert body.is_preparsed
    assert source
    assert strategy == _BlockingStrategy(
        statement_count=1,
        has_row_lock=False,
        has_authorization_embedding=True,
    )
    _assert_blocking_strategy(strategy)
    provisioned_catalog.admin.rollback()

    mutant_created = False
    try:
        mutant_oid = _create_separated_mutant(
            provisioned_catalog,
            contract,
            dependency_contract,
        )
        mutant_created = True
        mutant_observed = _observed_dependencies(
            provisioned_catalog,
            mutant_oid,
            dependency_contract,
        )
        mutant_body = _function_sql_body(provisioned_catalog.admin, mutant_oid)
        mutant_source = _required_sql_body(mutant_body)
        mutant_strategy = _blocking_strategy(
            mutant_body,
            dependencies_match=mutant_observed == dependency_contract.expected,
        )
        assert mutant_body.is_preparsed
        assert _top_level_statement_count(mutant_source) == 2
        assert mutant_strategy == _BlockingStrategy(
            statement_count=2,
            has_row_lock=False,
            has_authorization_embedding=False,
        )
        with pytest.raises(
            AssertionError,
            match="TOCTOU封鎖方式が実装されていない",
        ):
            _assert_blocking_strategy(mutant_strategy)
    finally:
        if mutant_created:
            _drop_separated_mutant(provisioned_catalog, contract)


def test_two_statement_mutant_exposes_toctou_only_with_barrier(
    provisioned_catalog: ProvisionedCatalog,
    mutant_barrier_case: _BarrierCase,
) -> None:
    """2 文 mutant は認可直後の無効化介入がある場合だけ TOCTOU になる。"""
    contract = _management_contract(provisioned_catalog.asset)
    dependency_contract = _dependency_contract(provisioned_catalog.asset, contract)
    _insert_management_fixture(provisioned_catalog, _BASELINE_FIXTURE)

    observation = _run_separated_mutant(
        provisioned_catalog,
        contract,
        dependency_contract,
        _BASELINE_FIXTURE,
        mutant_barrier_case,
    )
    assert observation.authorized_before_barrier
    assert observation.inserted_rows == ((True,),)
    assert observation.effect_count_after == (
        observation.effect_count_before + len(observation.inserted_rows)
    )

    if mutant_barrier_case.intervene:
        _assert_toctou_exposed(observation)
    else:
        with pytest.raises(
            AssertionError,
            match="副作用時にも付与が有効でありTOCTOUは成立していない",
        ):
            _assert_toctou_exposed(observation)


@pytest.mark.parametrize(
    "order",
    (
        _LinearizationOrder(disable_before_call=True),
        _LinearizationOrder(disable_before_call=False),
    ),
    ids=("connection-b-commits-first", "connection-a-statement-finishes-first"),
)
def test_single_statement_result_depends_only_on_commit_order(
    provisioned_catalog: ProvisionedCatalog,
    management_caller_connection: psycopg.Connection[Any],
    order: _LinearizationOrder,
) -> None:
    """B の commit と A の単一文の順序だけで副作用 0 行または 1 行になる。"""
    contract = _management_contract(provisioned_catalog.asset)
    dependency_contract = _dependency_contract(provisioned_catalog.asset, contract)
    _insert_management_fixture(provisioned_catalog, _BASELINE_FIXTURE)
    management_caller_connection.rollback()
    effect_count_before = _effect_count(provisioned_catalog, contract)

    if order.disable_before_call:
        _disable_target_grant(
            provisioned_catalog.admin,
            dependency_contract,
            _BASELINE_FIXTURE,
        )
    returned_rows = _invoke_management_function(
        management_caller_connection,
        contract,
        _BASELINE_FIXTURE,
    )
    management_caller_connection.commit()
    if not order.disable_before_call:
        _disable_target_grant(
            provisioned_catalog.admin,
            dependency_contract,
            _BASELINE_FIXTURE,
        )

    expected_rows: tuple[tuple[Any, ...], ...] = ()
    if not order.disable_before_call:
        expected_rows = (
            (
                True,
                _BASELINE_FIXTURE.invocation_group_id,
                _BASELINE_FIXTURE.invocation_target_tenant_id,
                _BASELINE_FIXTURE.invocation_effect_kind,
            ),
        )
    effect_count_after = _effect_count(provisioned_catalog, contract)
    assert returned_rows == expected_rows
    assert effect_count_after == effect_count_before + len(expected_rows)
    assert not _target_grant_enabled(
        provisioned_catalog.admin,
        dependency_contract,
        _BASELINE_FIXTURE,
    )
    provisioned_catalog.admin.rollback()
