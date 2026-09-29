"""その他プロファイルの導出・投入計画・補助関数変異を DB なしで検査する。"""

from __future__ import annotations

import inspect

import product_authz_other_profiles_cases as cases
from product_authz_tenant_owned_cases import (
    TENANT_A,
    TENANT_B,
    SeedRow,
    insert_statement,
)
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


def _assert_required_columns(row: SeedRow) -> None:
    """投入行が既知列だけを使い、既定値のない必須列を持つ。"""
    manifest = _manifest_by_name()[row.table]
    columns = _object_rows(manifest.get("columns"), f"{row.table}.columns")
    known = {str(column["name"]) for column in columns}
    required = {
        str(column["name"])
        for column in columns
        if column.get("nullable") is False and column.get("default") is None
    }
    assert set(row.values) <= known
    assert required <= set(row.values), (row.table, required - set(row.values))


def _assert_fk_targets_precede(
    row: SeedRow,
    preceding_rows: tuple[SeedRow, ...],
) -> None:
    """値を持つ FK が先行する投入行を exact に参照する。"""
    manifest = _manifest_by_name()[row.table]
    foreign_keys = _object_rows(
        manifest.get("foreign_keys"),
        f"{row.table}.foreign_keys",
    )
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
        assert all(value is not None for value in values)
        assert any(
            parent.table == parent_table
            and tuple(parent.values.get(str(column)) for column in parent_columns)
            == values
            for parent in preceding_rows
        ), (row.table, foreign_key.get("name"), values)


def test_other_profile_sets_are_derived_without_classification_asset() -> None:
    """Manifest と露出事実だけで 1・4・4・13 表を exact に導く。"""
    profiles = cases.profile_table_names()
    helper_source = inspect.getsource(cases)

    assert {name: len(tables) for name, tables in profiles.items()} == {
        "tenant_owned": 23,
        "self_tenant_row": 1,
        "effective_group_control": 4,
        "global_read_only": 4,
        "function_only": 13,
    }
    assigned = tuple(table for tables in profiles.values() for table in tables)
    assert len(assigned) == len(set(assigned)) == 45
    assert set(assigned) == set(cases.manifest_table_names())
    assert "table-classification.json" not in helper_source


def test_other_profile_seed_plan_is_nonempty_and_in_fk_order() -> None:
    """全対象表に行があり、追加行が必須列と FK 順を満たす。"""
    rows = cases.other_profile_seed_rows()
    for index, row in enumerate(rows):
        _assert_required_columns(row)
        _assert_fk_targets_precede(row, rows[:index])
        statement, params = insert_statement(row)
        assert isinstance(statement, sql.Composed)
        assert len(params) == len(row.values)
        assert statement.as_string().startswith(f'INSERT INTO "public"."{row.table}" (')

    seeded_tables = {row.table for row in rows}
    profiles = cases.profile_table_names()
    assert set(profiles["self_tenant_row"]) <= seeded_tables
    assert set(profiles["effective_group_control"]) <= seeded_tables
    assert set(profiles["global_read_only"]) <= seeded_tables
    assert set(profiles["function_only"]) <= seeded_tables

    tenant_rows = {
        row.values["id"]
        for row in rows
        if row.table == "tenants" and "id" in row.values
    }
    assert {TENANT_A, TENANT_B, cases.TENANT_DISABLED} <= tenant_rows

    assignments = tuple(
        row
        for row in rows
        if row.table == "tournament_rule_assignments"
        and str(row.values["tournament_key"]).startswith("step8-")
    )
    assert {row.values["tenant_id"] for row in assignments} == {TENANT_A, TENANT_B}
    assert len({row.values["rule_set_id"] for row in assignments}) == 2


def test_control_matrix_has_every_row_and_expected_cell() -> None:
    """6 状態の各グループに 4 制御資源の行を用意する。"""
    rows = cases.other_profile_seed_rows()
    matrix = cases.control_matrix_cases()
    assert {case.case_id for case in matrix} == {
        "member",
        "admin",
        "non_member",
        "left",
        "terminated",
        "disabled_tenant",
    }

    memberships = tuple(row for row in rows if row.table == "group_memberships")
    for case in matrix:
        assert any(
            row.table == "analysis_groups" and row.values.get("id") == case.group_id
            for row in rows
        )
        matching_memberships = tuple(
            row for row in memberships if row.values.get("group_id") == case.group_id
        )
        assert len(matching_memberships) == 1
        membership_id = matching_memberships[0].values["id"]
        assert any(
            row.table == "sharing_grants"
            and row.values.get("membership_id") == membership_id
            for row in rows
        )
        assert any(
            row.table == "group_invitations"
            and row.values.get("group_id") == case.group_id
            for row in rows
        )

    expected = {
        case.case_id: (case.general_visible, case.invitation_visible) for case in matrix
    }
    assert expected == {
        "member": (True, False),
        "admin": (True, True),
        "non_member": (False, False),
        "left": (False, False),
        "terminated": (False, False),
        "disabled_tenant": (False, False),
    }


def test_each_helper_mutation_removes_one_condition_and_changes_exact_cells() -> None:
    """補助関数の 6 条件を 1 個ずつ外した後の行列を固定する。"""
    original = cases.membership_helper_create_sql()
    mutations = cases.helper_condition_mutations()
    case_ids = {case.case_id for case in cases.control_matrix_cases()}
    baseline_general = {"member", "admin"}
    baseline_invitation = {"admin"}

    assert len(mutations) == 6
    assert len({mutation.condition_id for mutation in mutations}) == len(mutations)
    assert all(original.count(mutation.original_sql) == 1 for mutation in mutations)
    for mutation in mutations:
        mutated = cases.mutated_membership_helper_sql(mutation)
        assert mutated != original
        assert mutation.original_sql not in mutated
        assert mutation.general_visible_cases <= case_ids
        assert mutation.invitation_visible_cases <= case_ids
        assert (
            set(mutation.general_visible_cases) != baseline_general
            or set(mutation.invitation_visible_cases) != baseline_invitation
            or mutation.nonexistent_general_visible
            or mutation.nonexistent_invitation_visible
        )
