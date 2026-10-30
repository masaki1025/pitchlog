"""Manifest 全表の不変性宣言が PostgreSQL で強制されることを検査する。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from psycopg import sql

from pitchlog.authz.product_catalog import inspect_product_authz_catalog

from .conftest import DisposablePostgres, ProvisionedProductCatalog
from .test_alembic_migrations import (
    _alembic_config,
    _normalize_sql,
    _normalized_predicate,
    _sqlalchemy_url,
    _sync_trigger_catalog_contract,
)
from .test_product_authz_catalog import _bootstrap_superuser_oid

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _BACKEND_ROOT.parent / "contracts" / "db" / "schema-manifest.json"
_CHECK_VIOLATION_PATTERN = re.compile(
    r"\bRAISE\b.*?(?:USING\s+ERRCODE\s*=\s*|SQLSTATE\s*)'23514'",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class _ManifestTable:
    """不変性の強制判定に必要な manifest 1 表分の宣言。"""

    name: str
    columns: frozenset[str]
    protected_columns: frozenset[str]
    allowed_update_columns: frozenset[str]
    conditional_update_columns: frozenset[str]
    append_only: bool
    check_protected_columns: frozenset[str] = frozenset()


@dataclass(frozen=True)
class _CatalogTrigger:
    """既存ヘルパが PostgreSQL から取得したトリガ契約。"""

    name: str
    definition: str
    table: str
    columns: tuple[str, ...]
    enabled: str
    function_definition: str


@dataclass(frozen=True)
class _PopulationCounts:
    """空洞化を検出する 3 母集団の件数。"""

    manifest: int
    population: int
    database: int


def _load_manifest() -> dict[str, Any]:
    """不変性検査の唯一の宣言元となる manifest を返す。"""
    manifest: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return manifest


def _manifest_population(manifest: dict[str, Any]) -> tuple[_ManifestTable, ...]:
    """Manifest の全表から版管理差分に依存しない母集団を作る。"""
    return tuple(
        _ManifestTable(
            name=table["name"],
            columns=frozenset(column["name"] for column in table["columns"]),
            protected_columns=frozenset(table["immutability"]["protected_columns"]),
            allowed_update_columns=frozenset(
                table["immutability"]["allowed_update_columns"]
            ),
            conditional_update_columns=frozenset(
                table["immutability"]["conditional_update_columns"]
            ),
            append_only=table["lifecycle"]["append_mode"] == "追記専用",
        )
        for table in manifest["tables"]
    )


def _public_application_tables(connection: psycopg.Connection[Any]) -> set[str]:
    """Public schema の Alembic 管理表以外のユーザ表を返す。"""
    rows = connection.execute(
        """
        SELECT relation.relname
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relkind IN ('r', 'p')
          AND relation.relname <> 'alembic_version'
        ORDER BY relation.relname
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _catalog_triggers(
    connection: psycopg.Connection[Any],
) -> tuple[_CatalogTrigger, ...]:
    """全非内部トリガを列挙し、既存ヘルパで各契約を取得する。"""
    rows = connection.execute(
        """
        SELECT relation.relname, trigger_row.tgname
        FROM pg_trigger AS trigger_row
        JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND NOT trigger_row.tgisinternal
        ORDER BY relation.relname, trigger_row.tgname
        """
    ).fetchall()
    pairs = tuple((str(table), str(name)) for table, name in rows)
    names = tuple(name for _, name in pairs)
    if len(names) != len(set(names)):
        raise AssertionError("非内部トリガ名が public schema 内で一意ではない")

    contracts: list[_CatalogTrigger] = []
    for name in names:
        definition, table, columns, enabled, function = _sync_trigger_catalog_contract(
            connection, name
        )
        contracts.append(
            _CatalogTrigger(
                name=name,
                definition=definition,
                table=table,
                columns=tuple(columns),
                enabled=enabled,
                function_definition=function,
            )
        )
    if {(contract.table, contract.name) for contract in contracts} != set(pairs):
        raise AssertionError("列挙した非内部トリガと既存ヘルパの取得結果が一致しない")
    return tuple(contracts)


def _rg1_singleton_check_contract(table: dict[str, Any]) -> tuple[str, int, str] | None:
    """Manifestから固定ID列・値・主キー名を導出する。"""
    protected = table["immutability"]["protected_columns"]
    if len(protected) != 1:
        return None
    column = str(protected[0])
    checks = [
        match
        for expression in table["checks"]
        if (match := re.fullmatch(rf"{re.escape(column)}\s*=\s*(-?\d+)", expression))
    ]
    primary_keys = [
        item
        for item in table["unique_constraints"]
        if item["kind"] == "PRIMARY KEY" and item["columns"] == [column]
    ]
    if len(checks) != 1 or len(primary_keys) != 1:
        return None
    return column, int(checks[0].group(1)), str(primary_keys[0]["name"])


def _rg1_singleton_check_enforced(
    connection: psycopg.Connection[Any], table: dict[str, Any]
) -> bool:
    """Manifestの固定ID CHECKと主キーが実DBに完全一致するか返す。"""
    contract = _rg1_singleton_check_contract(table)
    if contract is None:
        return False
    column, value, primary_key_name = contract
    rows = connection.execute(
        "SELECT conname, contype, pg_get_constraintdef(oid) "
        "FROM pg_constraint WHERE conrelid = 'public.rg1_restore_gate'::regclass"
    ).fetchall()
    observed = {
        str(name): (str(kind), str(definition)) for name, kind, definition in rows
    }
    return observed.get(primary_key_name) == (
        "p",
        f"PRIMARY KEY ({column})",
    ) and any(
        kind == "c" and definition == f"CHECK (({column} = {value}))"
        for kind, definition in observed.values()
    )


def _before_event_clause(definition: str) -> str | None:
    """pg_get_triggerdef 全文から BEFORE と ON の間のイベント句を返す。"""
    normalized = _normalize_sql(definition).upper()
    _, marker, after_before = normalized.partition(" BEFORE ")
    if not marker:
        return None
    event_clause, marker, _ = after_before.partition(" ON ")
    return event_clause if marker else None


def _trigger_events(definition: str) -> set[str]:
    """BEFORE トリガのイベント種別を集合で返す。"""
    clause = _before_event_clause(definition)
    if clause is None:
        return set()
    return set(re.findall(r"\b(?:INSERT|UPDATE|DELETE|TRUNCATE)\b", clause))


def _is_before_update(trigger: _CatalogTrigger) -> bool:
    """トリガが BEFORE UPDATE を含むか返す。"""
    return "UPDATE" in _trigger_events(trigger.definition)


def _population_counts(
    manifest_table_count: int,
    population: Sequence[_ManifestTable],
    database_tables: Collection[str],
) -> _PopulationCounts:
    """Manifest・検査母集団・実 DB の表数を返す。"""
    return _PopulationCounts(
        manifest=manifest_table_count,
        population=len(population),
        database=len(database_tables),
    )


def _enforcement_violations(
    *,
    manifest_table_count: int,
    population: Sequence[_ManifestTable],
    database_tables: set[str],
    triggers: Sequence[_CatalogTrigger],
) -> list[str]:
    """全表の不変性宣言と強制の不一致を返す。"""
    violations: list[str] = []
    counts = _population_counts(manifest_table_count, population, database_tables)
    if counts.population == 0:
        violations.append("検査母集団が空")
    if len({counts.manifest, counts.population, counts.database}) != 1:
        violations.append(
            "表母集団の件数が不一致: "
            f"manifest={counts.manifest}, "
            f"population={counts.population}, database={counts.database}"
        )

    population_names = [table.name for table in population]
    if len(population_names) != len(set(population_names)):
        violations.append("検査母集団の表名が重複")
    population_name_set = set(population_names)
    if population_name_set != database_tables:
        violations.append(
            "検査母集団と実 DB の表集合が不一致: "
            f"不足={sorted(database_tables - population_name_set)!r}, "
            f"余剰={sorted(population_name_set - database_tables)!r}"
        )

    triggers_by_table: dict[str, list[_CatalogTrigger]] = {}
    for trigger in triggers:
        if _is_before_update(trigger):
            triggers_by_table.setdefault(trigger.table, []).append(trigger)

    for table in population:
        table_triggers = triggers_by_table.get(table.name, [])
        if not table.check_protected_columns <= table.protected_columns:
            violations.append(
                f"{table.name}: CHECKで保護する列がprotected宣言から外れた"
            )
        if table.check_protected_columns and table.conditional_update_columns:
            if not (
                table.name == "rg1_restore_gate"
                and table.protected_columns == {"singleton_id"}
                and table.allowed_update_columns == {"state"}
                and table.conditional_update_columns == {"recovery_generation"}
                and not table.append_only
            ):
                violations.append(f"{table.name}: CHECK代替の条件更新が閉契約外")
        if table.append_only:
            if table.protected_columns != table.columns:
                violations.append(f"{table.name}: 追記専用だが protected != columns")
            if table.allowed_update_columns:
                violations.append(
                    f"{table.name}: 追記専用だが allowed_update_columns が非空"
                )
            if len(table_triggers) != 1:
                violations.append(
                    f"{table.name}: BEFORE UPDATE OR DELETE トリガ本数が不一致: "
                    f"expected=1, actual={len(table_triggers)}"
                )
            else:
                trigger = table_triggers[0]
                if _trigger_events(trigger.definition) != {"UPDATE", "DELETE"}:
                    violations.append(f"{table.name}: 追記専用トリガのイベントが不一致")
                if trigger.columns:
                    violations.append(
                        f"{table.name}: 追記専用トリガに UPDATE OF 列がある: "
                        f"{list(trigger.columns)!r}"
                    )
        elif table.protected_columns - table.check_protected_columns:
            if len(table_triggers) != 1:
                violations.append(
                    f"{table.name}: BEFORE UPDATE OF トリガ本数が不一致: "
                    f"expected=1, actual={len(table_triggers)}"
                )
            else:
                trigger = table_triggers[0]
                expected_columns = (
                    table.protected_columns | table.conditional_update_columns
                )
                if set(trigger.columns) != expected_columns:
                    violations.append(
                        f"{table.name}: tgattr 列集合が不一致: "
                        f"expected={sorted(expected_columns)!r}, "
                        f"actual={sorted(trigger.columns)!r}"
                    )
                clause = _before_event_clause(trigger.definition)
                if clause is None or not clause.startswith("UPDATE OF "):
                    violations.append(f"{table.name}: BEFORE UPDATE OF トリガではない")
                if _trigger_events(trigger.definition) != {"UPDATE"}:
                    violations.append(f"{table.name}: UPDATE 以外のイベントを含む")
        elif table.check_protected_columns and table_triggers:
            violations.append(
                f"{table.name}: 固定CHECK列に予期しないBEFORE UPDATEトリガがある"
            )
        elif table_triggers:
            violations.append(
                f"{table.name}: protected が空だが BEFORE UPDATE トリガがある: "
                f"{sorted(trigger.name for trigger in table_triggers)!r}"
            )

        for trigger in table_triggers:
            if trigger.enabled != "O":
                violations.append(
                    f"{table.name}.{trigger.name}: tgenabled が O ではない: "
                    f"{trigger.enabled}"
                )
            if " FOR EACH ROW " not in _normalize_sql(trigger.definition).upper():
                violations.append(f"{table.name}.{trigger.name}: FOR EACH ROW ではない")
            if _CHECK_VIOLATION_PATTERN.search(trigger.function_definition) is None:
                violations.append(
                    f"{table.name}.{trigger.name}: 関数が SQLSTATE 23514 を投げない"
                )
    return violations


def _observed_contract(
    connection: psycopg.Connection[Any],
    *,
    historical_rg1: bool = False,
    privileged_role_oids: frozenset[int] | None = None,
) -> tuple[
    dict[str, Any],
    tuple[_ManifestTable, ...],
    set[str],
    tuple[_CatalogTrigger, ...],
]:
    """宣言母集団と実 DB の表・トリガ契約を一度に返す。"""
    manifest = _load_manifest()
    population = _manifest_population(manifest)
    rg1_table = next(table for table in population if table.name == "rg1_restore_gate")
    rg1_manifest = next(
        table for table in manifest["tables"] if table["name"] == "rg1_restore_gate"
    )
    revision = connection.execute(
        "SELECT version_num FROM public.alembic_version"
    ).fetchall()
    if historical_rg1:
        assert revision == [("0032_rg1_restore_gate",)]
        columns = connection.execute(
            "SELECT attname FROM pg_attribute "
            "WHERE attrelid='public.rg1_restore_gate'::regclass "
            "AND attnum>0 AND NOT attisdropped"
        ).fetchall()
        assert {row[0] for row in columns} == {"singleton_id", "state"}
        # 固定ID変異だけは実0032の二列契約で比較する。現manifest正例ではない。
        rg1_table = replace(
            rg1_table,
            columns=rg1_table.columns - {"recovery_generation"},
            conditional_update_columns=frozenset(),
        )
    else:
        assert revision == [("0036_initial_right_storage",)]
        assert rg1_table.protected_columns == {"singleton_id"}
        assert rg1_table.allowed_update_columns == {"state"}
        assert rg1_table.conditional_update_columns == {"recovery_generation"}
        assert not rg1_table.append_only
        epoch = connection.execute(
            "SELECT format_type(atttypid,atttypmod), attnotnull "
            "FROM pg_attribute WHERE attrelid='public.rg1_restore_gate'::regclass "
            "AND attname='recovery_generation' AND NOT attisdropped"
        ).fetchall()
        assert epoch == [("bigint", False)], "RG1 epoch列の契約が不一致"
        checks = connection.execute(
            "SELECT pg_get_expr(conbin,conrelid), convalidated FROM pg_constraint "
            "WHERE conrelid='public.rg1_restore_gate'::regclass "
            "AND conname='ck_rg1_restore_gate_recovery_generation' AND contype='c'"
        ).fetchall()
        assert len(checks) == 1 and checks[0][1] is True, "RG1 epoch CHECKが欠落"
        assert _normalized_predicate(checks[0][0]) == (
            "recovery_generation IS NULL OR recovery_generation > 0"
        ), "RG1 epoch CHECKが不一致"
        # 条件更新はCHECKだけでなく、固定関数/owner/ACL/RLSの実catalogへ束縛する。
        assert privileged_role_oids is not None
        report = inspect_product_authz_catalog(
            connection, privileged_role_oids=privileged_role_oids
        )
        assert report.ok, "RG1の条件更新を担う認可catalogが不一致"
    if _rg1_singleton_check_enforced(connection, rg1_manifest):
        rg1_table = replace(
            rg1_table,
            check_protected_columns=rg1_table.protected_columns,
        )
    population = _replace_table(population, rg1_table)
    return (
        manifest,
        population,
        _public_application_tables(connection),
        _catalog_triggers(connection),
    )


def _validate_observed_contract(
    manifest: dict[str, Any],
    population: Sequence[_ManifestTable],
    database_tables: set[str],
    triggers: Sequence[_CatalogTrigger],
) -> list[str]:
    """観測済みの宣言・表・トリガを全表判定へ渡す。"""
    return _enforcement_violations(
        manifest_table_count=len(manifest["tables"]),
        population=population,
        database_tables=database_tables,
        triggers=triggers,
    )


def _replace_table(
    population: Sequence[_ManifestTable], replacement: _ManifestTable
) -> tuple[_ManifestTable, ...]:
    """負例用に指定した manifest 行だけを差し替える。"""
    return tuple(
        replacement if table.name == replacement.name else table for table in population
    )


def _single_table_trigger(
    triggers: Sequence[_CatalogTrigger], table_name: str
) -> _CatalogTrigger:
    """指定表の BEFORE UPDATE トリガを一意に返す。"""
    matches = [
        trigger
        for trigger in triggers
        if trigger.table == table_name and _is_before_update(trigger)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"{table_name}: 負例の対象トリガを一意に解決できない: {len(matches)}"
        )
    return matches[0]


def _trigger_function_name(definition: str) -> str:
    """pg_get_triggerdef 全文から呼び出し先関数名を返す。"""
    match = re.search(
        r"EXECUTE FUNCTION ([a-zA-Z0-9_.]+)\(\)", _normalize_sql(definition)
    )
    if match is None:
        raise AssertionError("トリガ全文から関数名を解決できない")
    return match.group(1)


def _create_update_of_trigger(
    connection: psycopg.Connection[Any],
    trigger: _CatalogTrigger,
    columns: Sequence[str],
) -> None:
    """負例の後始末または生成用に UPDATE OF トリガを構成する。"""
    if not columns:
        raise AssertionError("UPDATE OF トリガには 1 列以上が必要")
    function_name = _trigger_function_name(trigger.definition)
    connection.execute(
        sql.SQL(
            "CREATE TRIGGER {} BEFORE UPDATE OF {} ON {} "
            "FOR EACH ROW EXECUTE FUNCTION {}()"
        ).format(
            sql.Identifier(trigger.name),
            sql.SQL(", ").join(sql.Identifier(column) for column in columns),
            sql.Identifier(trigger.table),
            sql.Identifier(*function_name.split(".")),
        )
    )


def test_all_manifest_immutability_declarations_are_enforced(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Manifest 全表の宣言と実 DB の強制を双方向・非空で突合する。"""
    connection = provisioned_product_catalog.applicator
    privileged = frozenset({_bootstrap_superuser_oid(provisioned_product_catalog)})
    with connection.transaction(force_rollback=True):
        manifest, population, database_tables, triggers = _observed_contract(
            connection, privileged_role_oids=privileged
        )

    counts = _population_counts(len(manifest["tables"]), population, database_tables)
    assert counts.manifest > 0
    assert counts.manifest == counts.population == counts.database
    assert (
        _validate_observed_contract(manifest, population, database_tables, triggers)
        == []
    )


def test_rg1_fixed_id_check_removal_is_detected(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RG1の固定ID CHECKを外すと保護列の強制不足を検出する。"""
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        command.upgrade(_alembic_config(), "0032_rg1_restore_gate")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            rg1_manifest = next(
                table
                for table in _load_manifest()["tables"]
                if table["name"] == "rg1_restore_gate"
            )
            before_manifest, before_population, before_tables, before_triggers = (
                _observed_contract(connection, historical_rg1=True)
            )
            assert not any(
                "rg1_restore_gate" in violation
                for violation in _validate_observed_contract(
                    before_manifest, before_population, before_tables, before_triggers
                )
            )
            contract = _rg1_singleton_check_contract(rg1_manifest)
            assert contract is not None
            column, value, _ = contract
            check_rows = connection.execute(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'public.rg1_restore_gate'::regclass "
                "AND contype = 'c' AND pg_get_constraintdef(oid) = %s",
                (f"CHECK (({column} = {value}))",),
            ).fetchall()
            assert len(check_rows) == 1
            connection.execute(
                sql.SQL(
                    "ALTER TABLE public.rg1_restore_gate DROP CONSTRAINT {}"
                ).format(sql.Identifier(str(check_rows[0][0])))
            )
            connection.execute(
                sql.SQL(
                    "UPDATE public.rg1_restore_gate SET {} = %s WHERE {} = %s"
                ).format(sql.Identifier(column), sql.Identifier(column)),
                (value + 1, value),
            )
            assert connection.execute(
                sql.SQL("SELECT {} FROM public.rg1_restore_gate").format(
                    sql.Identifier(column)
                )
            ).fetchall() == [(value + 1,)]
            manifest, population, database_tables, triggers = _observed_contract(
                connection, historical_rg1=True
            )
    assert any(
        "rg1_restore_gate: BEFORE UPDATE OF トリガ本数が不一致: "
        "expected=1, actual=0" in violation
        for violation in _validate_observed_contract(
            manifest, population, database_tables, triggers
        )
    )


def test_immutability_enforcement_mutations_are_detected(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """N-1〜N-5 の単独変異をすべて不変性検査が拒否すると示す。"""
    connection = provisioned_product_catalog.applicator
    privileged = frozenset({_bootstrap_superuser_oid(provisioned_product_catalog)})
    with connection.transaction(force_rollback=True):
        manifest, population, database_tables, triggers = _observed_contract(
            connection, privileged_role_oids=privileged
        )
        assert (
            _validate_observed_contract(manifest, population, database_tables, triggers)
            == []
        )

        # N-1: ステップ 2 を戻した状態と同じく players のトリガを除く。
        player_trigger = _single_table_trigger(triggers, "players")
        connection.execute(
            sql.SQL("DROP TRIGGER {} ON {}").format(
                sql.Identifier(player_trigger.name),
                sql.Identifier(player_trigger.table),
            )
        )
        without_player_trigger = _catalog_triggers(connection)
        n1_violations = _validate_observed_contract(
            manifest, population, database_tables, without_player_trigger
        )
        assert any(
            "players: BEFORE UPDATE OF トリガ本数が不一致: "
            "expected=1, actual=0" in violation
            for violation in n1_violations
        )
        _create_update_of_trigger(connection, player_trigger, player_trigger.columns)
        assert (
            _validate_observed_contract(
                manifest, population, database_tables, _catalog_triggers(connection)
            )
            == []
        )

        # N-3: protected 列を 1 つ OF リストから外す。
        guarded_trigger = _single_table_trigger(triggers, "recording_generations")
        guarded_table = next(
            table for table in population if table.name == guarded_trigger.table
        )
        removed_column = next(
            column
            for column in guarded_trigger.columns
            if column in guarded_table.protected_columns
        )
        remaining_columns = tuple(
            column for column in guarded_trigger.columns if column != removed_column
        )
        connection.execute(
            sql.SQL("DROP TRIGGER {} ON {}").format(
                sql.Identifier(guarded_trigger.name),
                sql.Identifier(guarded_trigger.table),
            )
        )
        _create_update_of_trigger(connection, guarded_trigger, remaining_columns)
        n3_violations = _validate_observed_contract(
            manifest, population, database_tables, _catalog_triggers(connection)
        )
        assert any(
            f"{guarded_trigger.table}: tgattr 列集合が不一致" in violation
            for violation in n3_violations
        )

    tables_by_name = {table.name: table for table in population}

    # N-2: 宣言の protected に実在する未分類列を 1 つ足す。
    players = tables_by_name["players"]
    added_column = sorted(
        players.columns
        - players.protected_columns
        - players.allowed_update_columns
        - players.conditional_update_columns
    )[0]
    n2_population = _replace_table(
        population,
        replace(
            players,
            protected_columns=players.protected_columns | {added_column},
        ),
    )
    n2_violations = _validate_observed_contract(
        manifest, n2_population, database_tables, triggers
    )
    assert any(
        "players: tgattr 列集合が不一致" in violation for violation in n2_violations
    )

    rg1 = tables_by_name["rg1_restore_gate"]
    rg1_without_protected = _replace_table(
        population, replace(rg1, protected_columns=frozenset())
    )
    assert any(
        "rg1_restore_gate: CHECKで保護する列がprotected宣言から外れた" in violation
        for violation in _validate_observed_contract(
            manifest, rg1_without_protected, database_tables, triggers
        )
    )

    # protected が空の表へ BEFORE UPDATE トリガを足す逆向きの乖離も拒否する。
    unprotected_table = next(
        table
        for table in population
        if not table.append_only and not table.protected_columns
    )
    unexpected_trigger = replace(
        player_trigger,
        name="unexpected_immutability_probe",
        table=unprotected_table.name,
    )
    reverse_violations = _validate_observed_contract(
        manifest,
        population,
        database_tables,
        (*triggers, unexpected_trigger),
    )
    assert any(
        f"{unprotected_table.name}: protected が空だが BEFORE UPDATE トリガがある"
        in violation
        for violation in reverse_violations
    )

    # N-4: 母集団が空の場合と manifest より 1 表少ない場合を拒否する。
    n4_empty = _validate_observed_contract(manifest, (), database_tables, triggers)
    n4_short = _validate_observed_contract(
        manifest, population[:-1], database_tables, triggers
    )
    assert "検査母集団が空" in n4_empty
    assert any("表母集団の件数が不一致" in item for item in n4_empty)
    assert any("表母集団の件数が不一致" in item for item in n4_short)

    # N-5: 単調増加列の conditional 宣言だけを除く。
    recording_generations = tables_by_name["recording_generations"]
    n5_population = _replace_table(
        population,
        replace(recording_generations, conditional_update_columns=frozenset()),
    )
    n5_violations = _validate_observed_contract(
        manifest, n5_population, database_tables, triggers
    )
    assert any(
        "recording_generations: tgattr 列集合が不一致" in violation
        for violation in n5_violations
    )


@pytest.mark.parametrize(
    "mutation", ["epoch-check", "extra-grant", "extra-conditional"]
)
def test_rg1_epoch_certification_rejects_unverified_conditions(
    provisioned_product_catalog: ProvisionedProductCatalog, mutation: str
) -> None:
    """条件更新のCHECK代替を実epoch・認可と閉列集合へ束縛する。"""
    catalog = provisioned_product_catalog
    privileged = frozenset({_bootstrap_superuser_oid(catalog)})
    with catalog.applicator.transaction(force_rollback=True):
        manifest, population, tables, triggers = _observed_contract(
            catalog.applicator, privileged_role_oids=privileged
        )
        assert _validate_observed_contract(manifest, population, tables, triggers) == []
        if mutation == "extra-conditional":
            gate = next(row for row in population if row.name == "rg1_restore_gate")
            changed = _replace_table(
                population,
                replace(
                    gate,
                    conditional_update_columns=frozenset(
                        {"recovery_generation", "state"}
                    ),
                ),
            )
            assert any(
                "CHECK代替の条件更新が閉契約外" in value
                for value in _validate_observed_contract(
                    manifest, changed, tables, triggers
                )
            )
        else:
            if mutation == "epoch-check":
                catalog.applicator.execute(
                    "ALTER TABLE public.rg1_restore_gate "
                    "DROP CONSTRAINT ck_rg1_restore_gate_recovery_generation"
                )
                reason = "RG1 epoch CHECK"
            else:
                catalog.applicator.execute(
                    "GRANT EXECUTE ON FUNCTION rg1_api.rg1_read_open(uuid) TO PUBLIC"
                )
                reason = "認可catalog"
            with pytest.raises(AssertionError, match=reason):
                _observed_contract(catalog.applicator, privileged_role_oids=privileged)
