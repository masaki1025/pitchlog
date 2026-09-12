"""Manifest と実 PostgreSQL カタログの横断 audit を行う。

manifest に載っている表の全数性は機械で閉じず、`N1` の受入証跡(ステップ 27)で閉じる。
このモジュールが閉じるのは、manifest に記録済みのカタログ構造と横断不変条件である。

`composite: false` の FK が意味上テナントに閉じた親を指すかはカタログから機械判定せず、
N1/N3 と同じく受入証跡で人が確認する。manifest が判定済みの `composite` と
`cross_tenant` は、その宣言どおりの物理構造であることだけを機械検査する。
移行が行を作り得る表と `import_batch_id` 対象表の全数性も manifest から生成せず、
N1/N7 の受入証跡で人が確認する。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from psycopg import sql

from .conftest import DisposablePostgres
from .test_alembic_migrations import (
    _alembic_config,
    _index_catalog_contract,
    _normalize_sql,
    _normalized_predicate,
    _sqlalchemy_url,
)

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _BACKEND_ROOT.parent / "contracts" / "db" / "schema-manifest.json"
_ALEMBIC_INTERNAL_TABLES = {"alembic_version"}
# data-model.md 12-3 節「移行バッチの退役」の不変条件 5 が列挙する 7 件。
_CANONICAL_RETIREMENT_CONSTRAINTS = {
    "lineup_memories": "uq_lineup_memories_active",
    "participation_intervals": "uq_participation_intervals_active",
    "operation_events": "uq_operation_events_active_d2",
    "play_runners": "uq_play_runners_active",
    "recording_generations": "uq_recording_generations_migration",
    "medical_notes": "uq_medical_notes_active",
    "migrated_final_lineups": "uq_migrated_final_lineups_active",
}
_AUDIT_AUTHORITIES = {
    "1_tenant_owned_foreign_keys": (
        "manifest の composite 宣言。composite=false の意味上の閉域性は受入証跡"
    ),
    "2_cross_tenant_foreign_keys": "manifest の cross_tenant 宣言",
    "3_no_delete_cascade": "manifest の MATCH・on_delete 宣言",
    "4_column_nullability": "manifest の全列 nullable 宣言",
    "5_forbidden_columns": "manifest の forbidden_columns 宣言",
    "6_unique_predicates": (
        "manifest の述語全文。business_unique の母集団は正本3-4節の判定表"
    ),
    "7_tenant_id_not_null": "manifest で tenant_id が nullable=false の表",
    "8_import_batch_identifier": (
        "manifest の import_batch_id 宣言。対象の全数性は N1/N7 の受入証跡"
    ),
    "9_retirement_predicates": "正本12-3節の不変条件5と manifest の lifecycle",
    "10_no_deleted_at_collapse": "manifest の列・禁止列宣言",
    "canonical_global_uniqueness": (
        "正本3-4節の判定列に束縛済みの manifest source_row.scope"
    ),
}


@dataclass(frozen=True)
class _ColumnContract:
    """列のカタログ契約。"""

    table: str
    name: str
    data_type: str
    nullable: bool
    default: str | None


@dataclass(frozen=True)
class _UniqueContract:
    """主キー・一意制約・部分一意索引のカタログ契約。"""

    table: str
    name: str
    kind: str
    columns: tuple[str, ...]
    predicate: str | None


@dataclass(frozen=True)
class _ForeignKeyContract:
    """外部キーの物理カタログ契約。"""

    table: str
    name: str
    columns: tuple[str, ...]
    target_table: str
    target_columns: tuple[str, ...]
    match: str
    on_delete: str


@dataclass(frozen=True)
class _CheckContract:
    """CHECK の PostgreSQL 正規形。"""

    table: str
    expression: str
    validated: bool


@dataclass(frozen=True)
class _IndexContract:
    """非一意索引のカタログ契約。"""

    table: str
    name: str
    columns: tuple[str, ...]
    predicate: str | None


def _load_manifest() -> dict[str, Any]:
    """スキーマ契約 manifest を読み込む。"""
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _set_violations(label: str, expected: set[Any], actual: set[Any]) -> list[str]:
    """期待集合と観測集合の exact-set 差分だけを返す。"""
    violations = [
        f"{label}: 実スキーマに不足: {item!r}"
        for item in sorted(expected - actual, key=repr)
    ]
    violations.extend(
        f"{label}: 実スキーマに余剰: {item!r}"
        for item in sorted(actual - expected, key=repr)
    )
    return violations


def _table_catalog(connection: psycopg.Connection[Any]) -> set[str]:
    """Public schema の通常表を pg_class から返す。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT relation.relname
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relkind IN ('r', 'p')
            ORDER BY relation.relname
            """
        )
        rows = cursor.fetchall()
    return {str(row[0]) for row in rows} - _ALEMBIC_INTERNAL_TABLES


def _normalized_type(data_type: str) -> str:
    """PostgreSQL の型表示を manifest の型名へ正規化する。"""
    if data_type == "timestamp with time zone":
        return "timestamptz"
    return data_type


def _strip_balanced_outer_parentheses(expression: str) -> str:
    """式全体だけを囲む括弧を除去する。"""
    value = expression.strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        encloses_entire_expression = True
        for position, character in enumerate(value):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            if depth == 0 and position != len(value) - 1:
                encloses_entire_expression = False
                break
        if not encloses_entire_expression:
            break
        value = value[1:-1].strip()
    return value


def _normalized_default(default: str | None) -> str | None:
    """単純既定値へ PostgreSQL が補うスカラー型 cast だけを除去する。"""
    if default is None:
        return None
    value = _strip_balanced_outer_parentheses(_normalize_sql(default))
    return re.sub(r"::(?:text|bigint|integer|boolean)\b", "", value)


def _column_catalog(
    connection: psycopg.Connection[Any],
) -> set[_ColumnContract]:
    """全列の名前・型・NULL 性・既定値を pg_attribute から返す。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                relation.relname,
                attribute.attname,
                format_type(attribute.atttypid, attribute.atttypmod),
                NOT attribute.attnotnull,
                pg_get_expr(default_row.adbin, default_row.adrelid, true)
            FROM pg_attribute AS attribute
            JOIN pg_class AS relation ON relation.oid = attribute.attrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            LEFT JOIN pg_attrdef AS default_row
              ON default_row.adrelid = attribute.attrelid
             AND default_row.adnum = attribute.attnum
            WHERE namespace.nspname = 'public'
              AND relation.relkind IN ('r', 'p')
              AND relation.relname <> ALL(%s)
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
            ORDER BY relation.relname, attribute.attnum
            """,
            (sorted(_ALEMBIC_INTERNAL_TABLES),),
        )
        rows = cursor.fetchall()
    return {
        _ColumnContract(
            table=str(table),
            name=str(name),
            data_type=_normalized_type(str(data_type)),
            nullable=bool(nullable),
            default=_normalized_default(None if default is None else str(default)),
        )
        for table, name, data_type, nullable, default in rows
    }


def _manifest_columns(manifest: Mapping[str, Any]) -> set[_ColumnContract]:
    """Manifest の列をカタログ比較用集合にする。"""
    return {
        _ColumnContract(
            table=table["name"],
            name=column["name"],
            data_type=column["type"],
            nullable=column["nullable"],
            default=_normalized_default(column["default"]),
        )
        for table in manifest["tables"]
        for column in table["columns"]
    }


def _index_kinds(
    connection: psycopg.Connection[Any],
) -> dict[str, str | None]:
    """索引名ごとに主キー・一意制約・独立索引の区分を返す。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT index_relation.relname, constraint_row.contype
            FROM pg_index AS index_row
            JOIN pg_class AS index_relation
              ON index_relation.oid = index_row.indexrelid
            JOIN pg_class AS table_relation
              ON table_relation.oid = index_row.indrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = table_relation.relnamespace
            LEFT JOIN pg_constraint AS constraint_row
              ON constraint_row.conindid = index_row.indexrelid
             AND constraint_row.contype IN ('p', 'u')
            WHERE namespace.nspname = 'public'
              AND table_relation.relname <> ALL(%s)
            ORDER BY index_relation.relname
            """,
            (sorted(_ALEMBIC_INTERNAL_TABLES),),
        )
        rows = cursor.fetchall()
    return {
        str(name): None if constraint_type is None else str(constraint_type)
        for name, constraint_type in rows
    }


def _unique_catalog(
    connection: psycopg.Connection[Any],
) -> set[_UniqueContract]:
    """全主キー・一意制約・部分一意索引を pg_index から返す。"""
    kinds = _index_kinds(connection)
    contracts: set[_UniqueContract] = set()
    for name, constraint_type in kinds.items():
        definition, table, columns, predicate, unique = _index_catalog_contract(
            connection, name
        )
        del definition
        if not unique:
            continue
        kind = {
            "p": "PRIMARY KEY",
            "u": "UNIQUE",
            None: "UNIQUE INDEX",
        }[constraint_type]
        contracts.add(
            _UniqueContract(
                table=table,
                name=name,
                kind=kind,
                columns=tuple(columns),
                predicate=predicate,
            )
        )
    return contracts


def _manifest_unique_constraints(
    manifest: Mapping[str, Any],
) -> set[_UniqueContract]:
    """Manifest の一意構造をカタログ比較用集合にする。"""
    return {
        _UniqueContract(
            table=table["name"],
            name=constraint["name"],
            kind=constraint["kind"],
            columns=tuple(constraint["columns"]),
            predicate=_normalized_predicate(constraint["predicate"]),
        )
        for table in manifest["tables"]
        for constraint in table["unique_constraints"]
    }


def _index_catalog(
    connection: psycopg.Connection[Any],
) -> set[_IndexContract]:
    """全非一意索引を列順・方向と述語つきで返す。"""
    contracts: set[_IndexContract] = set()
    for name in _index_kinds(connection):
        definition, table, columns, predicate, unique = _index_catalog_contract(
            connection, name
        )
        del definition
        if unique:
            continue
        contracts.add(
            _IndexContract(
                table=table,
                name=name,
                columns=tuple(columns),
                predicate=predicate,
            )
        )
    return contracts


def _manifest_indexes(manifest: Mapping[str, Any]) -> set[_IndexContract]:
    """Manifest の非一意索引をカタログ比較用集合にする。"""
    return {
        _IndexContract(
            table=table["name"],
            name=index["name"],
            columns=tuple(index["columns"]),
            predicate=_normalized_predicate(index["predicate"]),
        )
        for table in manifest["tables"]
        for index in table["indexes"]
    }


def _foreign_key_catalog(
    connection: psycopg.Connection[Any],
) -> set[_ForeignKeyContract]:
    """全 FK の両端・列順・MATCH・削除動作を pg_constraint から返す。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                source_relation.relname,
                constraint_row.conname,
                ARRAY(
                    SELECT source_attribute.attname
                    FROM unnest(constraint_row.conkey)
                        WITH ORDINALITY AS key_column(attnum, position)
                    JOIN pg_attribute AS source_attribute
                      ON source_attribute.attrelid = constraint_row.conrelid
                     AND source_attribute.attnum = key_column.attnum
                    ORDER BY key_column.position
                ),
                target_relation.relname,
                ARRAY(
                    SELECT target_attribute.attname
                    FROM unnest(constraint_row.confkey)
                        WITH ORDINALITY AS key_column(attnum, position)
                    JOIN pg_attribute AS target_attribute
                      ON target_attribute.attrelid = constraint_row.confrelid
                     AND target_attribute.attnum = key_column.attnum
                    ORDER BY key_column.position
                ),
                constraint_row.confmatchtype,
                constraint_row.confdeltype
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS source_relation
              ON source_relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS source_namespace
              ON source_namespace.oid = source_relation.relnamespace
            JOIN pg_class AS target_relation
              ON target_relation.oid = constraint_row.confrelid
            JOIN pg_namespace AS target_namespace
              ON target_namespace.oid = target_relation.relnamespace
            WHERE constraint_row.contype = 'f'
              AND source_namespace.nspname = 'public'
              AND target_namespace.nspname = 'public'
            ORDER BY source_relation.relname, constraint_row.conname
            """
        )
        rows = cursor.fetchall()
    match_types = {"s": "SIMPLE", "f": "FULL", "p": "PARTIAL"}
    delete_actions = {
        "a": "NO ACTION",
        "r": "RESTRICT",
        "c": "CASCADE",
        "n": "SET NULL",
        "d": "SET DEFAULT",
    }
    return {
        _ForeignKeyContract(
            table=str(table),
            name=str(name),
            columns=tuple(str(column) for column in columns),
            target_table=str(target_table),
            target_columns=tuple(str(column) for column in target_columns),
            match=match_types[str(match)],
            on_delete=delete_actions[str(on_delete)],
        )
        for table, name, columns, target_table, target_columns, match, on_delete in rows
    }


def _manifest_foreign_keys(
    manifest: Mapping[str, Any],
) -> set[_ForeignKeyContract]:
    """Manifest の FK を物理カタログ比較用集合にする。"""
    return {
        _ForeignKeyContract(
            table=table["name"],
            name=foreign_key["name"],
            columns=tuple(foreign_key["columns"]),
            target_table=foreign_key["references"]["table"],
            target_columns=tuple(foreign_key["references"]["columns"]),
            match=foreign_key["match"],
            on_delete=foreign_key["on_delete"],
        )
        for table in manifest["tables"]
        for foreign_key in table["foreign_keys"]
    }


def _check_catalog(
    connection: psycopg.Connection[Any],
) -> list[_CheckContract]:
    """実 CHECK の式と検証状態を pg_constraint から返す。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                relation.relname,
                pg_get_expr(
                    constraint_row.conbin,
                    constraint_row.conrelid,
                    true
                ),
                constraint_row.convalidated
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation
              ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE constraint_row.contype = 'c'
              AND namespace.nspname = 'public'
            ORDER BY relation.relname, constraint_row.conname
            """
        )
        rows = cursor.fetchall()
    return [
        _CheckContract(
            table=str(table),
            expression=_normalize_sql(str(expression)),
            validated=bool(validated),
        )
        for table, expression, validated in rows
    ]


def _manifest_checks(
    connection: psycopg.Connection[Any], manifest: Mapping[str, Any]
) -> list[_CheckContract]:
    """Manifest の CHECK を PostgreSQL 自身で同じ正規形へパースする。"""
    contracts: list[_CheckContract] = []
    with connection.cursor() as cursor:
        for table_number, table in enumerate(manifest["tables"]):
            if not table["checks"]:
                continue
            temporary_table = f"schema_audit_expected_{table_number}"
            cursor.execute(
                sql.SQL("CREATE TEMP TABLE {} (LIKE {}.{})").format(
                    sql.Identifier(temporary_table),
                    sql.Identifier("public"),
                    sql.Identifier(table["name"]),
                )
            )
            try:
                for check_number, expression in enumerate(table["checks"]):
                    cursor.execute(
                        sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK ({})").format(
                            sql.Identifier(temporary_table),
                            sql.Identifier(f"schema_audit_check_{check_number}"),
                            sql.SQL(expression),
                        )
                    )
                cursor.execute(
                    """
                    SELECT pg_get_expr(conbin, conrelid, true), convalidated
                    FROM pg_constraint
                    WHERE contype = 'c'
                      AND conrelid = to_regclass(%s)
                    ORDER BY conname
                    """,
                    (temporary_table,),
                )
                contracts.extend(
                    _CheckContract(
                        table=table["name"],
                        expression=_normalize_sql(str(expression)),
                        validated=bool(validated),
                    )
                    for expression, validated in cursor.fetchall()
                )
            finally:
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {}").format(
                        sql.Identifier(temporary_table)
                    )
                )
    return contracts


def _column_map(
    columns: Iterable[_ColumnContract],
) -> dict[str, dict[str, _ColumnContract]]:
    """列契約を表名と列名で引ける辞書へ変換する。"""
    result: dict[str, dict[str, _ColumnContract]] = {}
    for column in columns:
        result.setdefault(column.table, {})[column.name] = column
    return result


def _manifest_table_map(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Manifest の表を表名で引ける辞書へ変換する。"""
    return {table["name"]: table for table in manifest["tables"]}


def _cross_table_audit_violations(
    manifest: Mapping[str, Any],
    columns: set[_ColumnContract],
    unique_constraints: set[_UniqueContract],
    foreign_keys: set[_ForeignKeyContract],
) -> dict[str, list[str]]:
    """正本の判定と manifest の宣言を根拠に横断差分を返す。"""
    table_map = _manifest_table_map(manifest)
    columns_by_table = _column_map(columns)
    unique_by_name = {constraint.name: constraint for constraint in unique_constraints}
    foreign_keys_by_name = {
        foreign_key.name: foreign_key for foreign_key in foreign_keys
    }
    manifest_foreign_keys = {
        foreign_key["name"]: foreign_key
        for table in manifest["tables"]
        for foreign_key in table["foreign_keys"]
    }

    tenant_foreign_key_violations = [
        f"{name}: manifest の composite={expected['composite']} と実 FK が一致しない"
        for name, expected in sorted(manifest_foreign_keys.items())
        if name not in foreign_keys_by_name
        or (len(foreign_keys_by_name[name].columns) > 1) != bool(expected["composite"])
    ]

    expected_cross_tenant = {
        foreign_key["name"]
        for table in manifest["tables"]
        for foreign_key in table["foreign_keys"]
        if foreign_key["cross_tenant"]
    }
    actual_cross_tenant = {
        name for name in expected_cross_tenant if name in foreign_keys_by_name
    }
    cross_tenant_violations = _set_violations(
        "越境 FK", expected_cross_tenant, actual_cross_tenant
    )

    delete_action_violations = [
        f"{foreign_key.name}: ON DELETE CASCADE は禁止"
        for foreign_key in sorted(foreign_keys, key=lambda item: item.name)
        if foreign_key.on_delete == "CASCADE"
    ]

    expected_nullability = {
        (table["name"], column["name"], column["nullable"])
        for table in manifest["tables"]
        for column in table["columns"]
    }
    actual_nullability = {
        (column.table, column.name, column.nullable) for column in columns
    }
    nullability_violations = _set_violations(
        "列単位 NULL 性", expected_nullability, actual_nullability
    )

    forbidden_column_violations = [
        f"{table_name}: 禁止列が実在する: {column}"
        for table_name, table in sorted(table_map.items())
        for column in sorted(
            set(table["forbidden_columns"]) & set(columns_by_table.get(table_name, {}))
        )
    ]

    expected_predicates = {
        (
            table["name"],
            constraint["name"],
            _normalized_predicate(constraint["predicate"]),
        )
        for table in manifest["tables"]
        for constraint in table["unique_constraints"]
    }
    actual_predicates = {
        (constraint.table, constraint.name, constraint.predicate)
        for constraint in unique_constraints
    }
    predicate_violations = _set_violations(
        "一意構造の述語", expected_predicates, actual_predicates
    )

    required_nonnull_tenant_tables = {
        table["name"]
        for table in manifest["tables"]
        for column in table["columns"]
        if column["name"] == "tenant_id" and not column["nullable"]
    }
    nullable_tenant_violations = [
        f"{table}: manifest が要求する tenant_id NOT NULL を満たさない"
        for table in sorted(required_nonnull_tenant_tables)
        if "tenant_id" not in columns_by_table.get(table, {})
        or columns_by_table[table]["tenant_id"].nullable
    ]

    migration_created_tables = {
        table["name"]
        for table in manifest["tables"]
        if any(column["name"] == "import_batch_id" for column in table["columns"])
    }
    import_batch_violations = [
        f"{table}: import_batch_id が実スキーマにない"
        for table in sorted(migration_created_tables)
        if "import_batch_id" not in columns_by_table.get(table, {})
    ]

    retirement_tables = {
        table["name"]
        for table in manifest["tables"]
        if table["lifecycle"]["migration_retirement"] == "退役述語を持つ"
    }
    retirement_violations = _set_violations(
        "退役述語対象",
        set(_CANONICAL_RETIREMENT_CONSTRAINTS),
        retirement_tables,
    )
    if len(retirement_tables) != 7:
        retirement_violations.append(
            f"退役述語対象: 7 件ではない: {len(retirement_tables)} 件"
        )
    for table, constraint_name in _CANONICAL_RETIREMENT_CONSTRAINTS.items():
        if "retired_at" not in columns_by_table.get(table, {}):
            retirement_violations.append(f"{table}: retired_at が実スキーマにない")
        constraint = unique_by_name.get(constraint_name)
        if constraint is None or constraint.table != table:
            retirement_violations.append(
                f"{table}: 退役述語の一意構造がない: {constraint_name}"
            )
        elif (
            constraint.predicate is None
            or "retired_at IS NULL" not in constraint.predicate
        ):
            retirement_violations.append(
                f"{constraint_name}: retired_at IS NULL を述語に持たない"
            )

    deleted_at_violations = [
        f"{table}: deleted_at 単一列へ削除系統を畳んでいる"
        for table, table_columns in sorted(columns_by_table.items())
        if "deleted_at" in table_columns
    ]

    business_constraints = {
        constraint["name"]: constraint
        for table in manifest["tables"]
        for constraint in table["unique_constraints"]
        if "business_unique" in constraint["roles"]
    }
    business_constraint_tables = {
        constraint["name"]: table["name"]
        for table in manifest["tables"]
        for constraint in table["unique_constraints"]
        if "business_unique" in constraint["roles"]
    }
    canonical_outside = {
        name
        for name, constraint in business_constraints.items()
        if constraint["source_row"]["scope"] == "outside"
    }
    global_uniqueness_violations = [
        f"{name}: 正本でテナント外だが表が tenant_id を持つ"
        for name in sorted(canonical_outside)
        if "tenant_id" in columns_by_table.get(business_constraint_tables[name], {})
    ]
    if len(business_constraints) != 27:
        global_uniqueness_violations.append(
            f"business_unique が 27 件ではない: {len(business_constraints)} 件"
        )
    if len(canonical_outside) != 4:
        global_uniqueness_violations.append(
            f"テナント外 business_unique が 4 件ではない: {len(canonical_outside)} 件"
        )

    violations = {
        "1_tenant_owned_foreign_keys": tenant_foreign_key_violations,
        "2_cross_tenant_foreign_keys": cross_tenant_violations,
        "3_no_delete_cascade": delete_action_violations,
        "4_column_nullability": nullability_violations,
        "5_forbidden_columns": forbidden_column_violations,
        "6_unique_predicates": predicate_violations,
        "7_tenant_id_not_null": nullable_tenant_violations,
        "8_import_batch_identifier": import_batch_violations,
        "9_retirement_predicates": retirement_violations,
        "10_no_deleted_at_collapse": deleted_at_violations,
        "canonical_global_uniqueness": global_uniqueness_violations,
    }
    if set(violations) != set(_AUDIT_AUTHORITIES):
        raise AssertionError("横断 audit の項目と判定根拠の一覧が一致しない")
    return violations


def _nonempty_violations(
    violations: Mapping[str, list[str]],
) -> dict[str, list[str]]:
    """空でない差分項目だけを返す。"""
    return {name: errors for name, errors in violations.items() if errors}


def test_schema_manifest_matches_catalog_and_cross_table_rules(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifest 全構造と横断不変条件を実 PostgreSQL で exact-set 突合する。"""
    manifest = _load_manifest()
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL",
            _sqlalchemy_url(cluster.admin_dsn),
        )
        command.upgrade(_alembic_config(), "head")

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            expected_tables = {table["name"] for table in manifest["tables"]}
            actual_tables = _table_catalog(connection)
            expected_columns = _manifest_columns(manifest)
            actual_columns = _column_catalog(connection)
            expected_unique = _manifest_unique_constraints(manifest)
            actual_unique = _unique_catalog(connection)
            expected_foreign_keys = _manifest_foreign_keys(manifest)
            actual_foreign_keys = _foreign_key_catalog(connection)
            expected_checks = _manifest_checks(connection, manifest)
            actual_checks = _check_catalog(connection)
            expected_indexes = _manifest_indexes(manifest)
            actual_indexes = _index_catalog(connection)

            check_violations = _set_violations(
                "CHECK", set(expected_checks), set(actual_checks)
            )
            if len(expected_checks) != len(actual_checks):
                check_violations.append(
                    "CHECK: 件数不一致: "
                    f"期待 {len(expected_checks)} / 実際 {len(actual_checks)}"
                )
            catalog_violations = {
                "tables": _set_violations("表", expected_tables, actual_tables),
                "columns": _set_violations("列", expected_columns, actual_columns),
                "unique_constraints": _set_violations(
                    "一意構造", expected_unique, actual_unique
                ),
                "foreign_keys": _set_violations(
                    "FK", expected_foreign_keys, actual_foreign_keys
                ),
                "checks": check_violations,
                "indexes": _set_violations("索引", expected_indexes, actual_indexes),
            }
            cross_table_violations = _cross_table_audit_violations(
                manifest,
                actual_columns,
                actual_unique,
                actual_foreign_keys,
            )

            # 既存差分の有無に依存せず、余剰 1 表が新しい差分になる負例を固定する。
            before_extra_table = set(catalog_violations["tables"])
            connection.execute("CREATE TABLE schema_audit_unexpected (id integer)")
            try:
                after_extra_table = set(
                    _set_violations("表", expected_tables, _table_catalog(connection))
                )
            finally:
                connection.execute("DROP TABLE schema_audit_unexpected")
            assert after_extra_table - before_extra_table == {
                "表: 実スキーマに余剰: 'schema_audit_unexpected'"
            }
            assert before_extra_table <= after_extra_table

            all_violations = {
                **_nonempty_violations(catalog_violations),
                **_nonempty_violations(cross_table_violations),
            }
            assert all_violations == {}
