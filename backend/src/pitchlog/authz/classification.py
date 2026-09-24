"""製品表の物理プロファイルと露出の事実を純粋関数で検査する。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

PROFILE_NAMES = frozenset(
    {
        "tenant_owned",
        "self_tenant_row",
        "effective_group_control",
        "global_read_only",
        "function_only",
    }
)
FACT_KINDS = frozenset(
    {
        "non_tenant",
        "control_resource",
        "mixed_ownership_rule_resource",
        "admin_only",
        "pre_auth_only",
        "migration_only",
        "secret_column",
    }
)
FUNCTION_ONLY_FACT_KINDS = frozenset(
    {
        "mixed_ownership_rule_resource",
        "admin_only",
        "pre_auth_only",
        "migration_only",
    }
)
FUNCTION_OWNER_UNITS = frozenset({"U-A1", "U-A2", "U-X1", "migration_batch"})
CANONICAL_SOURCE_PATH = "docs/design/data-model.md"


class ProductClassificationError(ValueError):
    """製品表分類の入力不正または割り当て違反を表す。

    Attributes:
        violations: fail-closed で収集した違反の安定順列。
    """

    def __init__(self, violations: Iterable[str]) -> None:
        """違反を空でないタプルとして保持する。

        Args:
            violations: 検出した違反。
        """
        self.violations = tuple(violations)
        if not self.violations:
            raise ValueError("違反がない状態では例外を構築できない")
        super().__init__("製品表分類が不正:\n- " + "\n- ".join(self.violations))


def load_json_object(path: Path) -> dict[str, object]:
    """UTF-8 の JSON object を読み込む。

    Args:
        path: 読み込む資産のパス。

    Returns:
        文字列キーだけを持つ JSON object。

    Raises:
        ProductClassificationError: ファイルまたは JSON の形式が不正な場合。
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProductClassificationError(
            (f"JSON資産を読めない: {path}: {error}",)
        ) from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ProductClassificationError((f"JSON資産がobjectではない: {path}",))
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _object_rows(
    value: object,
    label: str,
    violations: list[str],
) -> tuple[dict[str, object], ...]:
    """文字列キーの object 配列を検証して返す。"""
    if not isinstance(value, list):
        violations.append(f"{label}はobject配列でなければならない")
        return ()
    rows: list[dict[str, object]] = []
    for index, raw_row in enumerate(value):
        row_label = f"{label}[{index}]"
        if not isinstance(raw_row, dict) or not all(
            isinstance(key, str) for key in raw_row
        ):
            violations.append(f"{row_label}は文字列キーのobjectでなければならない")
            continue
        rows.append(
            {key: item for key, item in raw_row.items() if isinstance(key, str)}
        )
    return tuple(rows)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
    violations: list[str],
) -> None:
    """Object のキー集合を exact-set で検査する。"""
    actual = frozenset(value)
    if actual != expected:
        violations.append(
            f"{label}のキーが不一致: 期待={sorted(expected)}, 実際={sorted(actual)}"
        )


def _required_text(
    value: object,
    label: str,
    violations: list[str],
) -> str | None:
    """空でない文字列だけを返す。"""
    if not isinstance(value, str) or not value:
        violations.append(f"{label}は空でない文字列でなければならない")
        return None
    return value


def _manifest_columns(
    manifest: Mapping[str, object],
    violations: list[str],
) -> dict[str, frozenset[str]]:
    """Manifest の全表と列を重複なく読み取る。"""
    result: dict[str, frozenset[str]] = {}
    for index, table_row in enumerate(
        _object_rows(manifest.get("tables"), "manifest.tables", violations)
    ):
        label = f"manifest.tables[{index}]"
        table_name = _required_text(table_row.get("name"), f"{label}.name", violations)
        column_names: list[str] = []
        for column_index, column_row in enumerate(
            _object_rows(table_row.get("columns"), f"{label}.columns", violations)
        ):
            column_name = _required_text(
                column_row.get("name"),
                f"{label}.columns[{column_index}].name",
                violations,
            )
            if column_name is not None:
                column_names.append(column_name)
        if len(column_names) != len(set(column_names)):
            violations.append(f"{label}.columnsに列名の重複がある")
        if table_name is None:
            continue
        if table_name in result:
            violations.append(f"manifest.tablesに表名の重複がある: {table_name}")
            continue
        result[table_name] = frozenset(column_names)
    if not result:
        violations.append("manifest.tablesから表を1件も導出できない")
    return result


def _classification_profiles(
    classification: Mapping[str, object],
    violations: list[str],
) -> dict[str, str]:
    """分類資産から表とプロファイルの一意な写像を読み取る。"""
    _require_exact_keys(
        classification,
        frozenset({"schema_version", "tables"}),
        "table-classification",
        violations,
    )
    if classification.get("schema_version") != 1:
        violations.append("table-classification.schema_versionは1でなければならない")

    profiles: dict[str, str] = {}
    for index, row in enumerate(
        _object_rows(
            classification.get("tables"), "table-classification.tables", violations
        )
    ):
        label = f"table-classification.tables[{index}]"
        table_name = _required_text(row.get("table"), f"{label}.table", violations)
        profile = _required_text(row.get("profile"), f"{label}.profile", violations)
        if profile not in PROFILE_NAMES:
            violations.append(f"{label}.profileが閉じた列挙にない: {profile!r}")
        is_function_only = profile == "function_only"
        expected_keys = (
            frozenset({"table", "profile", "access_path"})
            if is_function_only
            else frozenset({"table", "profile"})
        )
        _require_exact_keys(row, expected_keys, label, violations)
        if is_function_only:
            access_path = row.get("access_path")
            if not isinstance(access_path, dict) or not all(
                isinstance(key, str) for key in access_path
            ):
                violations.append(f"{label}.access_pathはobjectでなければならない")
            else:
                normalized_access_path = {
                    key: item
                    for key, item in access_path.items()
                    if isinstance(key, str)
                }
                _require_exact_keys(
                    normalized_access_path,
                    frozenset({"reason", "owner_unit"}),
                    f"{label}.access_path",
                    violations,
                )
                _required_text(
                    normalized_access_path.get("reason"),
                    f"{label}.access_path.reason",
                    violations,
                )
                owner_unit = _required_text(
                    normalized_access_path.get("owner_unit"),
                    f"{label}.access_path.owner_unit",
                    violations,
                )
                if owner_unit not in FUNCTION_OWNER_UNITS:
                    violations.append(
                        f"{label}.access_path.owner_unitが閉じた列挙にない: "
                        f"{owner_unit!r}"
                    )
        if table_name is None or profile not in PROFILE_NAMES:
            continue
        if table_name in profiles:
            violations.append(
                f"table-classification.tablesに表名の重複がある: {table_name}"
            )
            continue
        profiles[table_name] = profile

    used_profiles = frozenset(profiles.values())
    if used_profiles != PROFILE_NAMES:
        violations.append(
            "物理プロファイルの種類が不一致: "
            f"期待={sorted(PROFILE_NAMES)}, 実際={sorted(used_profiles)}"
        )
    return profiles


def _validate_evidence(
    value: object,
    label: str,
    canonical_source: str,
    violations: list[str],
) -> None:
    """典拠の引用が正本に一字一句存在することを検査する。"""
    rows = _object_rows(value, label, violations)
    if not rows:
        violations.append(f"{label}には典拠が1件以上必要")
        return
    for index, row in enumerate(rows):
        evidence_label = f"{label}[{index}]"
        _require_exact_keys(
            row,
            frozenset({"section", "quote"}),
            evidence_label,
            violations,
        )
        _required_text(row.get("section"), f"{evidence_label}.section", violations)
        quote = _required_text(row.get("quote"), f"{evidence_label}.quote", violations)
        if quote is not None and quote not in canonical_source:
            violations.append(f"{evidence_label}.quoteが正本に一字一句存在しない")


def _exposure_fact_sets(
    exposure_facts: Mapping[str, object],
    manifest_columns: Mapping[str, frozenset[str]],
    canonical_source: str,
    violations: list[str],
) -> tuple[dict[str, frozenset[str]], frozenset[tuple[str, str]]]:
    """露出の事実を検査し、種類別の表集合と秘密列集合を返す。"""
    _require_exact_keys(
        exposure_facts,
        frozenset({"schema_version", "canonical_source", "facts"}),
        "exposure-facts",
        violations,
    )
    if exposure_facts.get("schema_version") != 1:
        violations.append("exposure-facts.schema_versionは1でなければならない")
    if exposure_facts.get("canonical_source") != CANONICAL_SOURCE_PATH:
        violations.append(
            "exposure-facts.canonical_sourceは"
            f"{CANONICAL_SOURCE_PATH!r}でなければならない"
        )

    table_facts: dict[str, set[str]] = {
        kind: set() for kind in FACT_KINDS - {"secret_column"}
    }
    secret_columns: set[tuple[str, str]] = set()
    seen_kinds: set[str] = set()
    for fact_index, fact in enumerate(
        _object_rows(exposure_facts.get("facts"), "exposure-facts.facts", violations)
    ):
        label = f"exposure-facts.facts[{fact_index}]"
        _require_exact_keys(fact, frozenset({"kind", "entries"}), label, violations)
        kind = _required_text(fact.get("kind"), f"{label}.kind", violations)
        if kind not in FACT_KINDS:
            violations.append(f"{label}.kindが閉じた列挙にない: {kind!r}")
            continue
        if kind in seen_kinds:
            violations.append(f"exposure-facts.factsに種類の重複がある: {kind}")
            continue
        seen_kinds.add(kind)

        entries = _object_rows(fact.get("entries"), f"{label}.entries", violations)
        if not entries:
            violations.append(f"{label}.entriesには事実が1件以上必要")
        for entry_index, entry in enumerate(entries):
            entry_label = f"{label}.entries[{entry_index}]"
            expected_keys = (
                frozenset({"table", "column", "reason", "evidence"})
                if kind == "secret_column"
                else frozenset({"table", "reason", "evidence"})
            )
            _require_exact_keys(entry, expected_keys, entry_label, violations)
            table_name = _required_text(
                entry.get("table"), f"{entry_label}.table", violations
            )
            _required_text(entry.get("reason"), f"{entry_label}.reason", violations)
            _validate_evidence(
                entry.get("evidence"),
                f"{entry_label}.evidence",
                canonical_source,
                violations,
            )
            if table_name is None:
                continue
            if table_name not in manifest_columns:
                violations.append(
                    f"{entry_label}.tableがmanifestに存在しない: {table_name}"
                )
            if kind != "secret_column":
                if table_name in table_facts[kind]:
                    violations.append(f"{label}.entriesに表の重複がある: {table_name}")
                table_facts[kind].add(table_name)
                continue

            column_name = _required_text(
                entry.get("column"), f"{entry_label}.column", violations
            )
            if column_name is None:
                continue
            column_key = (table_name, column_name)
            if column_key in secret_columns:
                violations.append(
                    f"秘密の列の事実に重複がある: {table_name}.{column_name}"
                )
            secret_columns.add(column_key)
            if column_name not in manifest_columns.get(table_name, frozenset()):
                violations.append(
                    f"{entry_label}が指す列がmanifestに存在しない: "
                    f"{table_name}.{column_name}"
                )

    if seen_kinds != FACT_KINDS:
        violations.append(
            "露出の事実の種類が不一致: "
            f"期待={sorted(FACT_KINDS)}, 実際={sorted(seen_kinds)}"
        )
    return (
        {kind: frozenset(tables) for kind, tables in table_facts.items()},
        frozenset(secret_columns),
    )


def _record_exact_set_mismatch(
    *,
    label: str,
    expected: frozenset[str],
    actual: frozenset[str],
    violations: list[str],
) -> None:
    """文字列集合の不足と余分を1件の違反として記録する。"""
    if expected == actual:
        return
    violations.append(
        f"{label}が不一致: 不足={sorted(expected - actual)}, "
        f"余分={sorted(actual - expected)}"
    )


def _validate_assignment_conditions(
    profiles: Mapping[str, str],
    manifest_columns: Mapping[str, frozenset[str]],
    table_facts: Mapping[str, frozenset[str]],
    secret_columns: frozenset[tuple[str, str]],
    violations: list[str],
) -> None:
    """詳細設計 1-5-b の割り当て条件をすべて論理積で検査する。"""
    secret_tables = frozenset(table_name for table_name, _ in secret_columns)
    special_tables = frozenset(
        table_name
        for kind in FUNCTION_ONLY_FACT_KINDS
        for table_name in table_facts[kind]
    )
    exposed_tables = frozenset(
        table_name for tables in table_facts.values() for table_name in tables
    )

    for table_name, profile in profiles.items():
        columns = manifest_columns.get(table_name, frozenset())
        if table_name in special_tables and profile != "function_only":
            violations.append(
                f"{table_name}: 特別な露出の事実を持つ表はfunction_onlyだけを許す"
            )
        if profile == "function_only" and table_name not in special_tables:
            violations.append(
                f"{table_name}: function_onlyには所有混在・管理者専用・"
                "認証前専用・移行専用のいずれかの事実が必要"
            )
        if profile == "tenant_owned":
            if "tenant_id" not in columns:
                violations.append(f"{table_name}: tenant_ownedにtenant_id列がない")
            if table_name in secret_tables:
                violations.append(f"{table_name}: tenant_ownedに秘密の列がある")
            if table_name in exposed_tables:
                violations.append(f"{table_name}: tenant_ownedに露出の事実がある")
        elif profile == "self_tenant_row":
            if table_name != "tenants":
                violations.append(f"{table_name}: self_tenant_rowはtenantsだけを許す")
        elif profile == "effective_group_control":
            if table_name not in table_facts["control_resource"]:
                violations.append(
                    f"{table_name}: effective_group_controlに制御資源の事実がない"
                )
        elif profile == "global_read_only":
            if table_name not in table_facts["non_tenant"]:
                violations.append(
                    f"{table_name}: global_read_onlyに非テナントの事実がない"
                )
            if "tenant_id" in columns:
                violations.append(f"{table_name}: global_read_onlyにtenant_id列がある")
            if table_name in secret_tables:
                violations.append(f"{table_name}: global_read_onlyに秘密の列がある")

    for table_name in table_facts["control_resource"]:
        if profiles.get(table_name) != "effective_group_control":
            violations.append(
                f"{table_name}: 制御資源はeffective_group_controlでなければならない"
            )
    for table_name in table_facts["non_tenant"]:
        if profiles.get(table_name) != "global_read_only":
            violations.append(
                f"{table_name}: 非テナント資源はglobal_read_onlyでなければならない"
            )


def validate_product_table_classification(
    *,
    classification: Mapping[str, object],
    exposure_facts: Mapping[str, object],
    manifest: Mapping[str, object],
    model_tables: Iterable[str],
    canonical_source: str,
) -> None:
    """製品表分類と露出の事実を純粋に検査する。

    Args:
        classification: ``table-classification.json`` の JSON object。
        exposure_facts: ``exposure-facts.json`` の JSON object。
        manifest: ``schema-manifest.json`` の JSON object。
        model_tables: ``Base.metadata`` から呼び出し側が導いた表名。
        canonical_source: ``data-model.md`` の全文。

    Raises:
        ProductClassificationError: 形式、母集合、典拠、割り当てのいずれかが
            fail-closed の条件を満たさない場合。
    """
    violations: list[str] = []
    manifest_columns = _manifest_columns(manifest, violations)
    profiles = _classification_profiles(classification, violations)
    table_facts, secret_columns = _exposure_fact_sets(
        exposure_facts,
        manifest_columns,
        canonical_source,
        violations,
    )

    raw_model_tables = tuple(model_tables)
    if not all(
        isinstance(table_name, str) and table_name for table_name in raw_model_tables
    ):
        violations.append("model_tablesは空でない文字列だけでなければならない")
    if len(raw_model_tables) != len(set(raw_model_tables)):
        violations.append("model_tablesに表名の重複がある")
    model_table_set = frozenset(raw_model_tables)
    manifest_table_set = frozenset(manifest_columns)
    classification_table_set = frozenset(profiles)
    _record_exact_set_mismatch(
        label="Base.metadataとmanifestの母集合",
        expected=manifest_table_set,
        actual=model_table_set,
        violations=violations,
    )
    _record_exact_set_mismatch(
        label="分類資産とmanifestの母集合",
        expected=manifest_table_set,
        actual=classification_table_set,
        violations=violations,
    )
    _validate_assignment_conditions(
        profiles,
        manifest_columns,
        table_facts,
        secret_columns,
        violations,
    )

    if violations:
        raise ProductClassificationError(violations)
