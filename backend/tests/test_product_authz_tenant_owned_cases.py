"""製品 RLS の実 DB ケースを DB なしで検査する。"""

from __future__ import annotations

import inspect
from typing import cast

import product_authz_tenant_owned_cases as cases
import pytest
from psycopg import Connection, sql

# c2e5e4ddの旧public50/tenant32を全順序付きで固定する。
_EXPECTED_PUBLIC_TABLES = (
    "tenants",
    "team_records",
    "players",
    "games",
    "lineup_memories",
    "game_lineups",
    "participation_intervals",
    "rule_sets",
    "game_type_rule_defaults",
    "tournament_rule_assignments",
    "event_slots",
    "operation_events",
    "play_rows",
    "play_runners",
    "temporary_player_id_mappings",
    "idempotency_ledger",
    "rejected_event_originals",
    "evacuated_event_originals",
    "recording_generations",
    "medical_notes",
    "medical_note_versions",
    "pdf_export_records",
    "system_vocabularies",
    "admin_vocabularies",
    "tenant_vocabularies",
    "system_settings",
    "tenant_auth_subjects",
    "tenant_credentials",
    "admin_credentials",
    "admin_sessions",
    "tenant_tokens",
    "admin_operation_logs",
    "player_merge_events",
    "player_move_records",
    "rate_limit_counters",
    "analysis_groups",
    "group_memberships",
    "sharing_grants",
    "group_invitations",
    "invalidation_intents",
    "migration_quarantine",
    "migrated_final_lineups",
    "migration_runs",
    "migration_resolution_reports",
    "migration_warning_reports",
    "rg1_restore_gate",
    "trusted_devices",
    "game_start_requests",
    "game_start_attempts",
    "recording_right_deliveries",
)
_EXPECTED_PUBLIC_TENANT_TABLES = (
    "team_records",
    "players",
    "games",
    "lineup_memories",
    "game_lineups",
    "participation_intervals",
    "tournament_rule_assignments",
    "event_slots",
    "operation_events",
    "play_rows",
    "play_runners",
    "temporary_player_id_mappings",
    "idempotency_ledger",
    "rejected_event_originals",
    "evacuated_event_originals",
    "recording_generations",
    "medical_notes",
    "medical_note_versions",
    "pdf_export_records",
    "tenant_vocabularies",
    "tenant_auth_subjects",
    "tenant_tokens",
    "admin_operation_logs",
    "player_merge_events",
    "player_move_records",
    "group_memberships",
    "invalidation_intents",
    "migrated_final_lineups",
    "trusted_devices",
    "game_start_requests",
    "game_start_attempts",
    "recording_right_deliveries",
)
_EXPECTED_PRIVATE_TABLES = (
    "writer_bindings",
    "writer_admissions",
    "first_ball_write_admissions",
    "ordinary_pitch_checkpoints",
    "ordinary_pitch_write_admissions",
    "ordinary_pitch_history",
)


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


def test_public_seed_population_and_private_function_only_population_are_exact() -> (
    None
):
    """旧public50/tenant32全表を保ち、私有3表をseed/DMLから分ける。"""
    assert (
        tuple(
            row["name"]
            for row in cases.manifest_tables()
            if cases.table_schema(str(row["name"])) == "public"
        )
        == _EXPECTED_PUBLIC_TABLES
    )
    assert cases.tenant_id_table_names() == _EXPECTED_PUBLIC_TENANT_TABLES
    assert cases.private_function_only_table_names() == _EXPECTED_PRIVATE_TABLES
    assert {row.table for row in cases.seed_rows()}.isdisjoint(_EXPECTED_PRIVATE_TABLES)
    for table in _EXPECTED_PRIVATE_TABLES:
        assert cases.table_schema(table) == "sync_fence"
        with pytest.raises(AssertionError, match="汎用INSERTは禁止"):
            cases.insert_statement(cases.SeedRow(table, {}))
        with pytest.raises(AssertionError, match="未定義"):
            cases.insert_candidate(table, cases.TENANT_A)
    with pytest.raises(AssertionError, match="manifest外"):
        cases.table_schema("unregistered")


@pytest.mark.parametrize("schema", ("unknown", "", "sync_fence"))
def test_table_schema_rejects_wrong_public_namespace(monkeypatch, schema: str) -> None:
    """既public表を誤namespaceへ移したモデルを正規fixtureへ使わない。"""
    from types import SimpleNamespace

    from sqlalchemy import Column, Integer, MetaData, Table

    metadata = MetaData()
    Table("games", metadata, Column("id", Integer), schema=schema)
    monkeypatch.setattr(cases, "Base", SimpleNamespace(metadata=metadata))
    with pytest.raises(AssertionError, match="未登録"):
        cases.table_schema("games")


def test_table_schema_rejects_name_collision_and_private_downgrade(monkeypatch) -> None:
    """同名衝突と私有表のpublic降格をSQL生成前に拒否する。"""
    from types import SimpleNamespace

    from sqlalchemy import Column, Integer, MetaData, Table

    metadata = MetaData()
    Table("games", metadata, Column("id", Integer))
    Table("games", metadata, Column("id", Integer), schema="sync_fence")
    Table("writer_bindings", metadata, Column("id", Integer), schema="public")
    monkeypatch.setattr(cases, "Base", SimpleNamespace(metadata=metadata))
    with pytest.raises(AssertionError, match="同名衝突"):
        cases.table_schema("games")
    with pytest.raises(AssertionError, match="未登録"):
        cases.table_schema("writer_bindings")


@pytest.mark.parametrize("schema", ("public", "sync_fence"))
def test_index_catalog_lookup_binds_schema_and_preserves_five_values(
    schema: str,
) -> None:
    """同名索引をschemaで分け、既定public呼出と5返却値を保持する。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from db.test_alembic_migrations import _index_catalog_contract

    calls = []
    rows = {
        ("same_index", "public"): ("public sql", "games", ["id"], None, True),
        ("same_index", "sync_fence"): (
            "private sql",
            "writer_bindings",
            ["lease_id"],
            None,
            True,
        ),
    }

    @contextmanager
    def cursor():
        def execute(query, params):
            assert "namespace.nspname = %s" in query
            assert "namespace.oid = index_relation.relnamespace" in query
            calls.append(params)

        yield SimpleNamespace(execute=execute, fetchone=lambda: rows.get(calls[-1]))

    connection = cast(Connection[tuple[object, ...]], SimpleNamespace(cursor=cursor))
    result = (
        _index_catalog_contract(connection, "same_index")
        if schema == "public"
        else _index_catalog_contract(connection, "same_index", schema=schema)
    )
    assert result == rows[("same_index", schema)]
    assert calls == [("same_index", schema)]
    with pytest.raises(AssertionError, match="存在しない"):
        _index_catalog_contract(connection, "missing", schema=schema)
    before = list(calls)
    with pytest.raises(AssertionError, match="未登録"):
        _index_catalog_contract(connection, "same_index", schema="unknown")
    assert calls == before


@pytest.mark.parametrize(
    "constraint", ("uq_sync_writer_binding_lease", "uq_sync_writer_binding_nonce")
)
@pytest.mark.parametrize("field", ("columns", "source_row", "roles", "predicate"))
def test_schema_audit_private_unique_exception_is_exact(
    constraint: str, field: str
) -> None:
    """旧31/対象外5を保ち、6-1-aの2制約だけへ全field例外を閉じる。"""
    import copy

    from db import test_schema_audit as audit

    manifest = audit._load_manifest()
    rows = [
        c
        for t in manifest["tables"]
        for c in t["unique_constraints"]
        if "business_unique" in c["roles"]
    ]
    assert len(rows) == 31 + 2
    assert len([c for c in rows if c["source_row"].get("scope") == "outside"]) == 5 + 2
    changed = copy.deepcopy(manifest)
    table = next(t for t in changed["tables"] if t["name"] == "writer_bindings")
    row = next(c for c in table["unique_constraints"] if c["name"] == constraint)
    row[field] = (
        [] if field in ("columns", "roles") else {} if field == "source_row" else "true"
    )
    # rolesを外す改変も、有限2件の欠落として拒否する。
    with pytest.raises(ValueError, match="exact2"):
        audit._cross_table_audit_violations(
            changed,
            audit._manifest_columns(changed),
            audit._manifest_unique_constraints(changed),
            audit._manifest_foreign_keys(changed),
        )


@pytest.mark.parametrize(
    "mode", ("extra", "wrong_table", "unknown_source", "duplicate")
)
def test_schema_audit_unique_exception_cannot_expand(mode: str) -> None:
    """例外の余剰・別表への移動・原典の付替えを拒否する。"""
    import copy

    from db import test_schema_audit as audit

    changed = copy.deepcopy(audit._load_manifest())
    table = next(t for t in changed["tables"] if t["name"] == "writer_bindings")
    row = next(
        c
        for c in table["unique_constraints"]
        if c["name"] == "uq_sync_writer_binding_lease"
    )
    if mode == "extra":
        table["unique_constraints"].append(
            {**copy.deepcopy(row), "name": "unknown_unique"}
        )
    elif mode == "duplicate":
        next(t for t in changed["tables"] if t["name"] == "games")[
            "unique_constraints"
        ].append(copy.deepcopy(row))
    elif mode == "wrong_table":
        table["unique_constraints"].remove(row)
        next(t for t in changed["tables"] if t["name"] == "games")[
            "unique_constraints"
        ].append(row)
    else:
        row["source_row"]["section"] = "unknown"
    with pytest.raises(ValueError, match="exact2"):
        audit._cross_table_audit_violations(
            changed,
            audit._manifest_columns(changed),
            audit._manifest_unique_constraints(changed),
            audit._manifest_foreign_keys(changed),
        )
