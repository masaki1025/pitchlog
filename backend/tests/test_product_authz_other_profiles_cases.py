"""その他プロファイルの導出・投入計画・補助関数変異を DB なしで検査する。"""

from __future__ import annotations

import inspect
from typing import cast

import product_authz_other_profiles_cases as cases
from product_authz_tenant_owned_cases import (
    TENANT_A,
    TENANT_B,
    SeedRow,
    insert_statement,
    private_function_only_table_names,
)
from psycopg import Connection, sql


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
        if column.get("nullable") is False
        and column.get("default") is None
        and "generated_expression" not in column
    }
    assert set(row.values) <= known
    assert required <= set(row.values), (row.table, required - set(row.values))


def _assert_fk_targets_precede(
    row: SeedRow,
    preceding_rows: tuple[SeedRow, ...],
) -> None:
    """値を持つ FK が先行する投入行を exact に参照する。"""
    manifest = _manifest_by_name()[row.table]
    text_defaults = {
        str(column["name"]): default[1:-1]
        for column in _object_rows(manifest.get("columns"), f"{row.table}.columns")
        if isinstance((default := column.get("default")), str)
        and default.startswith("'")
        and default.endswith("'")
    }
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
        values = tuple(
            row.values.get(str(column), text_defaults.get(str(column)))
            for column in child_columns
        )
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
    """Manifest と露出事実だけで 1・4・4・18表と列限定1表を exact に導く。"""
    profiles = cases.profile_table_names()
    helper_source = inspect.getsource(cases)

    assert {name: len(tables) for name, tables in profiles.items()} == {
        "tenant_owned": 22,
        "self_tenant_row": 1,
        "effective_group_control": 4,
        "global_read_only": 4,
        "function_only": 18 + len(private_function_only_table_names()),
        "column_restricted": 1,
    }
    assigned = tuple(table for tables in profiles.values() for table in tables)
    assert (
        len(assigned)
        == len(set(assigned))
        == 50 + len(private_function_only_table_names())
    )
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
    assert "rg1_restore_gate" in profiles["function_only"]
    assert "rg1_restore_gate" not in seeded_tables
    assert (
        set(profiles["function_only"])
        - {"rg1_restore_gate", *private_function_only_table_names()}
        <= seeded_tables
    )
    assert set(private_function_only_table_names()).isdisjoint(seeded_tables)

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


def test_generation_secret_columns_are_separate_and_closed(monkeypatch) -> None:
    """既列の読取を保ち、秘密列母集団の欠落・余剰・重複を拒否する。"""
    import copy

    import pytest

    assert cases.generation_secret_columns() == ("proof_digest", "recovery_generation")
    assert cases.profile_table_names()["column_restricted"] == (
        "recording_generations",
    )
    assert "recording_generations" not in cases.function_only_table_names()
    asset = cases._load_object(cases._EXPOSURE_FACTS_PATH)
    original = copy.deepcopy(asset)
    for mode in ("missing", "extra", "duplicate"):
        changed = copy.deepcopy(original)
        entries = next(
            f["entries"] for f in changed["facts"] if f["kind"] == "secret_column"
        )
        target = next(r for r in entries if r["table"] == "recording_generations")
        if mode == "missing":
            entries.remove(target)
        else:
            entries.append(
                {**target, "column": "unknown"} if mode == "extra" else dict(target)
            )
        monkeypatch.setattr(cases, "_load_object", lambda path, asset=changed: asset)
        with pytest.raises(AssertionError, match="exact2"):
            cases.generation_secret_columns()


def test_private_function_only_fact_is_exact_and_never_seeded() -> None:
    """新露出事実3表だけを関数限定へ加え、既public seedを保つ。"""
    expected = {"writer_bindings", "writer_admissions", "first_ball_write_admissions"}
    assert (
        set(cases.exposure_fact_table_names("sync_writer_binding_storage")) == expected
    )
    assert set(private_function_only_table_names()) == expected
    assert expected <= set(cases.function_only_table_names())
    assert expected.isdisjoint(cases.profile_table_names()["tenant_owned"])
    assert expected.isdisjoint(row.table for row in cases.other_profile_seed_rows())


def test_schema_audit_catalog_preserves_namespace_and_fk_endpoints() -> None:
    """実DBなしで観測schemaを失わず、同名/未知/私有降格を閉じる。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    import pytest
    from db import test_schema_audit as audit

    rows = [
        ("public", "alembic_version"),
        ("public", "games"),
        ("sync_fence", "writer_bindings"),
    ]
    statements = []

    @contextmanager
    def cursor():
        def execute(query, params=None):
            statements.append((query, params))

        yield SimpleNamespace(execute=execute, fetchall=lambda: rows)

    connection = cast(Connection[tuple[object, ...]], SimpleNamespace(cursor=cursor))
    assert audit._table_catalog(connection) == {"games", "writer_bindings"}
    assert "namespace.nspname IN ('public', 'sync_fence')" in statements[-1][0]
    rows = [("sync_fence", "unexpected")]
    with pytest.raises(AssertionError, match="未登録"):
        audit._table_catalog(connection)
    rows = [("public", "writer_bindings")]
    with pytest.raises(AssertionError, match="未登録"):
        audit._table_catalog(connection)
    rows = [
        (
            "sync_fence",
            "public",
            "writer_bindings",
            "fk_test",
            ["tenant_id", "game_id"],
            "games",
            ["tenant_id", "id"],
            "f",
            "r",
        )
    ]
    expected = audit._ForeignKeyContract(
        "writer_bindings",
        "fk_test",
        ("tenant_id", "game_id"),
        "games",
        ("tenant_id", "id"),
        "FULL",
        "RESTRICT",
    )
    assert audit._foreign_key_catalog(connection) == {expected}
    assert "target_namespace.nspname," in statements[-1][0]
    rows = [
        (
            "sync_fence",
            "unknown",
            "writer_bindings",
            "fk_test",
            ["tenant_id"],
            "games",
            ["id"],
            "s",
            "a",
        )
    ]
    with pytest.raises(AssertionError, match="未登録"):
        audit._foreign_key_catalog(connection)


def test_schema_audit_private_catalog_paths_keep_schema(monkeypatch) -> None:
    """列/CHECK/索引/生成式の各観測も有限schemaを保持する。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from db import test_schema_audit as audit

    rows = [("sync_fence", "writer_bindings", "lease_id", "uuid", False, None)]
    statements = []

    @contextmanager
    def cursor():
        def execute(query, params=None):
            rendered = query if isinstance(query, str) else query.as_string()
            statements.append((rendered, params))

        yield SimpleNamespace(execute=execute, fetchall=lambda: rows)

    connection = cast(Connection[tuple[object, ...]], SimpleNamespace(cursor=cursor))
    assert audit._column_catalog(connection) == {
        audit._ColumnContract("writer_bindings", "lease_id", "uuid", False, None)
    }
    rows = [("sync_fence", "writer_bindings", "lease_id IS NOT NULL", True)]
    assert audit._check_catalog(connection) == [
        audit._CheckContract("writer_bindings", "lease_id IS NOT NULL", True)
    ]
    rows = [("sync_fence", "writer_bindings", "lease_index", "u")]
    assert audit._index_kinds(connection) == {("sync_fence", "lease_index"): "u"}
    calls = []
    is_unique = True

    def index_contract(actual, name, *, schema):
        assert actual is connection
        calls.append((name, schema))
        return "index SQL", "writer_bindings", ["lease_id"], None, is_unique

    monkeypatch.setattr(audit, "_index_catalog_contract", index_contract)
    assert audit._unique_catalog(connection) == {
        audit._UniqueContract(
            "writer_bindings", "lease_index", "UNIQUE", ("lease_id",), None
        )
    }
    is_unique = False
    assert audit._index_catalog(connection) == {
        audit._IndexContract("writer_bindings", "lease_index", ("lease_id",), None)
    }
    assert calls == [("lease_index", "sync_fence"), ("lease_index", "sync_fence")]
    rows = [("sync_fence", "writer_bindings", "derived", "1 + 2")]
    manifest = {
        "tables": [
            {
                "name": "writer_bindings",
                "columns": [{"name": "derived", "generated_expression": "1 + 2"}],
            }
        ]
    }
    assert audit._generated_expression_violations(connection, manifest) == []
    rows = [("lease_id IS NOT NULL", True)]
    manifest = {
        "tables": [{"name": "writer_bindings", "checks": ["lease_id IS NOT NULL"]}]
    }
    assert audit._manifest_checks(connection, manifest) == [
        audit._CheckContract("writer_bindings", "lease_id IS NOT NULL", True)
    ]
    assert any(
        'LIKE "sync_fence"."writer_bindings"' in query for query, _ in statements
    )
