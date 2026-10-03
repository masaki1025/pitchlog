"""製品 RLS の実 DB ケースを DB なしで検査する。"""

from __future__ import annotations

import inspect

import product_authz_tenant_owned_cases as cases
from psycopg import sql


def _manifest_by_name() -> dict[str, dict[str, object]]:
    """Manifest の表を名前で引ける形にする。"""
    return {
        str(table["name"]): table
        for table in cases.manifest_tables()
        if isinstance(table.get("name"), str)
    }


def _object_rows(value: object, label: str) -> tuple[dict[str, object], ...]:
    """Manifest 内の object 配列を検証して返す。"""
    assert isinstance(value, list), f"{label} は配列が必要"
    assert all(isinstance(row, dict) for row in value), f"{label} の要素が不正"
    return tuple(row for row in value if isinstance(row, dict))


def _column_names(table: dict[str, object]) -> frozenset[str]:
    """Manifest 表の列集合を返す。"""
    return frozenset(
        str(column["name"]) for column in _object_rows(table.get("columns"), "columns")
    )


def _assert_required_columns_are_present(row: cases.SeedRow) -> None:
    """投入行が既知列だけを使い、必須列をすべて持つことを確かめる。"""
    table = _manifest_by_name()[row.table]
    columns = _object_rows(table.get("columns"), f"{row.table}.columns")
    known_columns = _column_names(table)
    assert set(row.values) <= known_columns
    required = {
        str(column["name"])
        for column in columns
        if column.get("nullable") is False and column.get("default") is None
    }
    assert required <= set(row.values), (row.table, required - set(row.values))


def _assert_fk_targets_precede(
    row: cases.SeedRow,
    preceding_rows: tuple[cases.SeedRow, ...],
) -> None:
    """値を持つ全 FK が先行行を exact に参照することを確かめる。"""
    table = _manifest_by_name()[row.table]
    foreign_keys = _object_rows(table.get("foreign_keys"), f"{row.table}.foreign_keys")
    for foreign_key in foreign_keys:
        child_columns = foreign_key.get("columns")
        references = foreign_key.get("references")
        assert isinstance(child_columns, list)
        assert isinstance(references, dict)
        parent_table = references.get("table")
        parent_columns = references.get("columns")
        assert isinstance(parent_table, str)
        assert isinstance(parent_columns, list)
        values = tuple(row.values.get(str(column)) for column in child_columns)
        if all(value is None for value in values):
            continue
        if foreign_key.get("match") == "SIMPLE" and any(
            value is None for value in values
        ):
            continue
        assert all(value is not None for value in values), (
            row.table,
            foreign_key.get("name"),
        )
        assert any(
            parent.table == parent_table
            and tuple(parent.values.get(str(column)) for column in parent_columns)
            == values
            for parent in preceding_rows
        ), (row.table, foreign_key.get("name"), values)


def test_table_sets_are_derived_without_the_profile_assignment_asset() -> None:
    """23 表と 28 表を manifest・露出事実だけから導く。"""
    tenant_id_tables = cases.tenant_id_table_names()
    tenant_owned_tables = cases.tenant_owned_table_names()
    helper_source = inspect.getsource(cases)

    assert len(tenant_id_tables) == 28
    assert len(tenant_owned_tables) == 23
    assert set(tenant_owned_tables) < set(tenant_id_tables)
    assert all(
        "tenant_id" in _column_names(_manifest_by_name()[table])
        for table in tenant_id_tables
    )
    assert "classification" not in helper_source


def test_tenant_reassignment_guards_are_derived_from_manifest_and_migrations() -> None:
    """Tenant 不変列と upgrade のトリガ定義から 5 件を導く。"""
    owned = set(cases.tenant_owned_table_names())
    manifest_guarded: set[str] = set()
    for table in cases.manifest_tables():
        immutability = table.get("immutability")
        if (
            table.get("name") in owned
            and isinstance(immutability, dict)
            and "tenant_id" in immutability.get("protected_columns", [])
        ):
            manifest_guarded.add(str(table["name"]))
    guards = cases.tenant_update_guards()

    assert len(manifest_guarded) == 5
    assert {guard.table for guard in guards} == manifest_guarded
    assert len({guard.trigger_name for guard in guards}) == len(guards)
    assert len({guard.function_name for guard in guards}) == len(guards)
    assert len({guard.message for guard in guards}) == len(guards)
    assert all(guard.sqlstate == "23514" for guard in guards)
    assert all(guard.function_name.startswith("prevent_") for guard in guards)
    assert all(guard.message for guard in guards)


def test_seed_plan_covers_both_tenants_in_fk_dependency_order() -> None:
    """28 表すべてに A/B 行があり、必須列と FK の投入順を満たす。"""
    rows = cases.seed_rows()
    for index, row in enumerate(rows):
        _assert_required_columns_are_present(row)
        _assert_fk_targets_precede(row, rows[:index])

    for table in cases.tenant_id_table_names():
        observed_tenants = {
            row.values["tenant_id"]
            for row in rows
            if row.table == table and "tenant_id" in row.values
        }
        assert observed_tenants == set(cases.TENANT_IDS), table


def test_every_tenant_owned_insert_candidate_is_constraint_complete() -> None:
    """他 tenant INSERT 用の 23 行が既知列・必須列・FK を満たす。"""
    seed = cases.seed_rows()
    for table in cases.tenant_owned_table_names():
        candidate = cases.insert_candidate(table, cases.TENANT_B)
        _assert_required_columns_are_present(candidate)
        _assert_fk_targets_precede(candidate, seed)
        statement, params = cases.insert_statement(candidate)
        assert isinstance(statement, sql.Composed)
        assert len(params) == len(candidate.values)
        assert statement.as_string().startswith(f'INSERT INTO "public"."{table}" (')

        manifest = _manifest_by_name()[table]
        unique_constraints = _object_rows(
            manifest.get("unique_constraints"),
            f"{table}.unique_constraints",
        )
        for constraint in unique_constraints:
            if constraint.get("predicate") is not None:
                continue
            columns = constraint.get("columns")
            assert isinstance(columns, list)
            candidate_key = tuple(
                candidate.values.get(str(column)) for column in columns
            )
            assert all(value is not None for value in candidate_key)
            assert not any(
                row.table == table
                and tuple(row.values.get(str(column)) for column in columns)
                == candidate_key
                for row in seed
            ), (table, columns)
