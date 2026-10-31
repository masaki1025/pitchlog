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
        if column.get("nullable") is False
        and column.get("default") is None
        and "generated_expression" not in column
    }
    assert required <= set(row.values), (row.table, required - set(row.values))


def _assert_fk_targets_precede(
    row: cases.SeedRow,
    preceding_rows: tuple[cases.SeedRow, ...],
) -> None:
    """値を持つ全 FK が先行行を exact に参照することを確かめる。"""
    table = _manifest_by_name()[row.table]
    text_defaults = {
        str(column["name"]): default[1:-1]
        for column in _object_rows(table.get("columns"), f"{row.table}.columns")
        if isinstance((default := column.get("default")), str)
        and default.startswith("'")
        and default.endswith("'")
    }
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
    """22 表と 32 表を manifest・露出事実だけから導く。"""
    tenant_id_tables = cases.tenant_id_table_names()
    tenant_owned_tables = cases.tenant_owned_table_names()
    helper_source = inspect.getsource(cases)

    assert len(tenant_id_tables) == 32
    assert len(tenant_owned_tables) == 22
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
    """32 表すべてに A/B 行があり、必須列と FK の投入順を満たす。"""
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


def test_initial_storage_seeds_preserve_nonowned_denial_and_closed_values() -> None:
    """初期権4表の制約用seedでapp権限や製品成功を成立させない。"""
    initial = {
        "trusted_devices",
        "game_start_requests",
        "game_start_attempts",
        "recording_right_deliveries",
    }
    assert initial.isdisjoint(cases.tenant_owned_table_names())
    assert "recording_generations" not in cases.tenant_owned_table_names()
    for table in initial:
        rows = [row for row in cases.seed_rows() if row.table == table]
        assert len(rows) == 2
        assert {row.values["tenant_id"] for row in rows} == {
            cases.TENANT_A,
            cases.TENANT_B,
        }
        for row in rows:
            if table == "trusted_devices":
                assert isinstance(row.values["credential_digest"], bytes)
                assert len(row.values["credential_digest"]) == 32
            elif table == "game_start_requests":
                assert isinstance(row.values["request_digest"], bytes)
                assert len(row.values["request_digest"]) == 32
            elif table == "game_start_attempts":
                assert row.values["outcome"] == "pending"
                assert row.values.get("resolved_at") is None
            else:
                assert row.values["generation"] == 1
                assert row.values["key_id"] == "public-fixture-only"
                assert (
                    isinstance(row.values["nonce"], bytes)
                    and len(row.values["nonce"]) == 12
                )
                assert (
                    isinstance(row.values["ciphertext"], bytes)
                    and len(row.values["ciphertext"]) == 48
                )


def test_static_migration_sql_expands_only_literal_tuple_loops(tmp_path) -> None:
    """SQL定数と有限tupleを順序通り読み、任意実行・動的loopを許さない。"""
    import pytest

    path = tmp_path / "0001.py"
    path.write_text(
        "SQL = 'first'\nTABLES = ('one', 'two')\n"
        "def upgrade():\n"
        "    op.execute(SQL)\n"
        "    for table in TABLES:\n"
        "        op.execute(f'next {table}')\n"
    )
    assert cases._upgrade_sql(path) == ("first", "next one", "next two")
    for source in (
        "def upgrade():\n    op.execute(unknown())\n",
        "def upgrade():\n    for table in unknown():\n        op.execute(f'{table}')\n",
        "def upgrade():\n    op.execute(f'{unknown}')\n",
        "def upgrade():\n    if unknown:\n        op.execute('hidden')\n",
    ):
        path.write_text(source)
        with pytest.raises(AssertionError, match="静的|定数tuple|未対応"):
            cases._upgrade_sql(path)


def test_initial_guard_has_exact_four_connections_and_delete_expectation(
    monkeypatch,
) -> None:
    """共有guardの正規4接続とSQL由来のDELETE拒否を欠落・余剰から守る。"""
    from pathlib import Path

    import product_authz_cross_cutting_cases as cross
    import pytest

    name = "protect_initial_right_storage"
    expected = {
        (name, table, f"trg_{table}_initial_right_guard")
        for table in (
            "trusted_devices",
            "game_start_requests",
            "game_start_attempts",
            "recording_right_deliveries",
        )
    }
    identities = cases._migration_attached_trigger_identities()
    assert len(identities) == 43
    assert len(set(identities)) == 43
    assert {row for row in identities if row[0] == name} == expected
    expectation = next(
        e for e in cross.trigger_expectations() if e.function_name == name
    )
    assert (expectation.sqlstate, expectation.message) == (
        "23514",
        "initial right storage cannot be physically deleted",
    )
    migration = Path(cases._MIGRATIONS_PATH) / "0036_initial_recording_right_storage.py"
    sql = "\n".join(cases._upgrade_sql(migration))
    assert "NEW.proof_digest" in sql and "NEW.recovery_generation" in sql
    assert f"RAISE EXCEPTION '{expectation.message}' USING ERRCODE = '23514'" in sql
    for row in expected:
        monkeypatch.setattr(
            cross,
            "_migration_attached_trigger_identities",
            lambda row=row: tuple(item for item in identities if item != row),
        )
        with pytest.raises(AssertionError, match="4接続identity"):
            cross.trigger_expectations()
    for changed in (
        (*identities, next(iter(expected))),
        (*identities, (name, "games", "unexpected")),
    ):
        monkeypatch.setattr(
            cross,
            "_migration_attached_trigger_identities",
            lambda changed=changed: changed,
        )
        with pytest.raises(AssertionError, match="4接続identity"):
            cross.trigger_expectations()


def test_schema_audit_accepts_exact_canonical_and_quote_sources() -> None:
    """DBなしで旧29＋新quote2の全横断auditと不正原典拒否を確認する。"""
    import copy

    import pytest
    from db import test_schema_audit as audit

    manifest = audit._load_manifest()
    columns = audit._manifest_columns(manifest)
    uniques = audit._manifest_unique_constraints(manifest)
    foreign_keys = audit._manifest_foreign_keys(manifest)
    violations = audit._cross_table_audit_violations(
        manifest, columns, uniques, foreign_keys
    )
    assert audit._nonempty_violations(violations) == {}
    for mode in ("unknown_quote", "missing_scope"):
        changed = copy.deepcopy(manifest)
        constraints = [
            c
            for t in changed["tables"]
            for c in t["unique_constraints"]
            if "business_unique" in c["roles"]
        ]
        if mode == "unknown_quote":
            next(c for c in constraints if "quote" in c["source_row"])["source_row"][
                "section"
            ] = "unknown"
        else:
            del next(c for c in constraints if "scope" in c["source_row"])[
                "source_row"
            ]["scope"]
        with pytest.raises(ValueError):
            audit._cross_table_audit_violations(changed, columns, uniques, foreign_keys)


def test_owned_seed_database_closure_rejects_foreign_or_wrong_database(
    monkeypatch,
) -> None:
    """所有factoryの固定seedだけへ閉鎖SQLを発行し、外部供給へ転用しない。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    import db_fixtures
    import pytest

    cluster = db_fixtures.DisposablePostgres("owned-container", "owned-seed", "unused")
    executed = []
    connected = []
    database_name = "pitchlog_disposable"

    @contextmanager
    def connect(dsn):
        connected.append(dsn)
        yield SimpleNamespace(
            info=SimpleNamespace(dbname=database_name),
            execute=lambda query: executed.append(query.as_string()),
        )

    monkeypatch.setattr(db_fixtures.psycopg, "connect", connect)
    with pytest.raises(AssertionError):
        db_fixtures._close_owned_seed_database_access(cluster)
    assert connected == executed == []
    monkeypatch.setitem(db_fixtures._DISPOSABLE_CLUSTER_OWNERS, id(cluster), cluster)
    db_fixtures._close_owned_seed_database_access(cluster)
    assert connected == ["owned-seed"]
    assert executed == [
        'REVOKE CONNECT, TEMPORARY ON DATABASE "pitchlog_disposable" FROM PUBLIC'
    ]
    executed.clear()
    database_name = "foreign_database"
    with pytest.raises(AssertionError):
        db_fixtures._close_owned_seed_database_access(cluster)
    assert executed == []
