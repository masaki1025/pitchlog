"""凍結基準台帳の作業ツリー不変条件を検査する。"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Final

from frozen_baselines import (
    COMPARISON_STRATEGIES,
    ComparisonStrategy,
    FrozenBaselineError,
    IdentityValue,
    collect_materials,
    load_frozen_baseline_ledger,
    parse_frozen_baseline_ledger,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = Path("contracts/authz/frozen-baselines.json")
SCHEMA_PATH = Path("contracts/authz/frozen-baselines.schema.json")
SCAN_ALLOWLIST_PATH = Path("scripts/frozen-baseline-scan-allowlist.json")
SCAN_SOURCE_ROOTS: Final[tuple[str, ...]] = ("scripts", "tests", "backend/tests")
SCAN_ALLOWLIST_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    {"schema_version", "asset_kind", "entries"}
)
SCAN_ALLOWLIST_ENTRY_KEYS: Final[frozenset[str]] = frozenset(
    {"path", "value", "reason", "pending_removal"}
)
SCAN_ALLOWLIST_ASSET_KIND = "frozen_baseline_scan_allowlist"
SCAN_VALUE_PATTERN = re.compile(r"\b(?:[0-9a-f]{64}|[0-9a-f]{40})\b")
SCAN_ALLOWLIST_VALUE_PATTERN = re.compile(r"(?:[0-9a-f]{64}|[0-9a-f]{40})")

TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "asset_kind",
        "acceptance",
        "movement_rules",
        "implementation_bindings",
        "placements",
        "declarations",
        "history",
    }
)
MOVEMENT_TRIGGERS: Final[frozenset[str]] = frozenset(
    {
        "value_change",
        "replacement",
        "addition",
        "removal",
        "location_change",
        "first_placement",
        "rule_self_change",
    }
)
UNIVERSAL_LOWER_BOUND: Final[frozenset[str]] = frozenset(
    {
        "set",
        "value",
        "placement",
        "target_correspondence",
        "identity_interpretation",
    }
)
CHANGE_ASPECTS: Final[frozenset[str]] = frozenset(
    {
        "frozen_targets",
        "identity",
        "granularity",
        "basis_series",
        "movement_rules",
        "implementation_bindings",
        "acceptance",
        "series_retired",
    }
)
CODE_ASSET_PATHS: Final[frozenset[str]] = frozenset(
    {"scripts/frozen_baselines.py", "scripts/check_frozen_baselines.py"}
)
LEGACY_PLACEMENTS: Final[dict[str, list[dict[str, str]]]] = {
    "oracle_input": [
        {
            "kind": "python_assignment",
            "path": "scripts/check_authz_catalog.py",
            "symbol": "ORACLE_INPUT_BASELINE_COMMIT",
        }
    ]
}
ABSENT: Final[dict[str, bool]] = {"absent": True}
BOOTSTRAP_ACCEPTANCE_ID = "masaki1025/pitchlog#73"
BOOTSTRAP_TRIGGERS: Final[tuple[str, ...]] = (
    "value_change",
    "replacement",
    "addition",
    "removal",
    "location_change",
    "first_placement",
    "rule_self_change",
)
BOOTSTRAP_LOWER_BOUND: Final[tuple[str, ...]] = (
    "set",
    "value",
    "placement",
    "target_correspondence",
    "identity_interpretation",
)
BOOTSTRAP_TARGETS: Final[tuple[str, ...]] = (
    "contracts/authz/oracle-seal.lock.json#/oracle_commit",
    "contracts/authz/attack-tree.json#/oracle_context/oracle_commit",
    "contracts/authz/boundary-proposal.json#/oracle_context/oracle_commit",
    "contracts/authz/claim-mutant-map.json#/oracle_context/oracle_commit",
    "contracts/authz/ddl-elements.json#/oracle_context/oracle_commit",
    "contracts/authz/rejected-configs.json#/oracle_context/oracle_commit",
    "contracts/authz/verification-evidence.json#/oracle_context/oracle_commit",
)


class FrozenBaselineCheckError(ValueError):
    """凍結基準台帳の不変条件違反を表す。"""


@dataclass(frozen=True, order=True)
class _ScanKey:
    """走査候補をパスと値の組で識別する。"""

    path: str
    value: str


@dataclass(frozen=True)
class _ScanAllowlistEntry:
    """走査allow-listの1エントリを保持する。"""

    path: str
    value: str
    reason: str
    pending_removal: bool

    @property
    def key(self) -> _ScanKey:
        """エントリの識別単位であるパスと値の組を返す。"""
        return _ScanKey(self.path, self.value)


@dataclass(frozen=True)
class _SourceScan:
    """本文走査の出現回数と一意な組を保持する。"""

    occurrences: int
    occurrences_40: int
    occurrences_64: int
    pairs: frozenset[_ScanKey]


# 初回だけ許す債務は検査器側で閉じ、headの申告を期待値にしない。
# 値を分割して、検査器自身が走査候補を新設する自己参照を避ける。
BOOTSTRAP_PENDING_REMOVAL_KEYS: Final[frozenset[_ScanKey]] = frozenset(
    {
        _ScanKey(
            "backend/tests/db/authz/mutation_composition.py",
            "099a8fa20595c25f553b46de" + "dcaaa9660dd03c2e",
        ),
        _ScanKey(
            "scripts/check_docs_status.py",
            "523ecfd1db94c0c494b9b722b05cf4b3"
            + "c7d4562a1a6f2648fd9b76d5074a8e52",
        ),
        _ScanKey(
            "tests/test_check_authz_catalog.py",
            "56c281c409e972927940fad8" + "30aa38352df32f1e",
        ),
        _ScanKey(
            "tests/test_core_guard.py",
            "56c281c409e972927940fad8" + "30aa38352df32f1e",
        ),
    }
)


@dataclass(frozen=True)
class _PullRequestEvent:
    """受理遷移に必要なpull_request eventの値を保持する。"""

    base_ref: str
    base_sha: str
    head_sha: str
    repository: str
    number: int

    @property
    def acceptance_id(self) -> str:
        """repository名とPR番号から受理IDを導出する。"""
        return f"{self.repository}#{self.number}"


def _load_schema(path: Path) -> dict[str, Any]:
    """JSON Schemaをobjectとして読み取る。"""
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrozenBaselineCheckError(f"JSON Schemaを解析できない: {exc}") from exc
    if not isinstance(value, dict):
        raise FrozenBaselineCheckError("JSON Schemaのトップレベルがobjectでない")
    return value


def _json_type_matches(value: Any, type_name: str) -> bool:
    """Python値が指定JSON型に一致するか返す。"""
    type_table = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    predicate = type_table.get(type_name)
    if predicate is None:
        raise FrozenBaselineCheckError(f"未対応のJSON Schema type: {type_name}")
    return predicate(value)


def _json_equal(left: Any, right: Any) -> bool:
    """boolとintegerを混同せずJSON値を比較する。"""
    if type(left) is not type(right):
        return False
    return bool(left == right)


def _resolve_schema_reference(root_schema: dict[str, Any], reference: str) -> dict[str, Any]:
    """同一schema内のlocal referenceを解決する。"""
    if not reference.startswith("#/"):
        raise FrozenBaselineCheckError(f"外部JSON Schema参照は使えない: {reference}")
    current: Any = root_schema
    for token in reference.removeprefix("#/").split("/"):
        if not isinstance(current, dict) or token not in current:
            raise FrozenBaselineCheckError(f"JSON Schema参照を解決できない: {reference}")
        current = current[token]
    if not isinstance(current, dict):
        raise FrozenBaselineCheckError(f"JSON Schema参照先がobjectでない: {reference}")
    return current


def _validate_schema(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
) -> None:
    """本台帳schemaで使用するJSON Schemaキーワードを検証する。"""
    reference = schema.get("$ref")
    if isinstance(reference, str):
        referenced_schema = _resolve_schema_reference(root_schema, reference)
        _validate_schema(value, referenced_schema, root_schema, path)
        return

    variants = schema.get("oneOf")
    if isinstance(variants, list):
        matched = 0
        for variant in variants:
            if not isinstance(variant, dict):
                raise FrozenBaselineCheckError(f"JSON SchemaのoneOfが不正: {path}")
            try:
                _validate_schema(value, variant, root_schema, path)
            except FrozenBaselineCheckError:
                continue
            matched += 1
        if matched != 1:
            raise FrozenBaselineCheckError(f"schema: {path}: oneOfに一意に一致しない")
        return

    if "const" in schema and not _json_equal(value, schema["const"]):
        raise FrozenBaselineCheckError(
            f"schema: {path}: const不一致: 期待={schema['const']!r}; 実際={value!r}"
        )
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and not any(
        _json_equal(value, candidate) for candidate in enum_values
    ):
        raise FrozenBaselineCheckError(f"schema: {path}: enum外の値: {value!r}")

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _json_type_matches(value, expected_type):
        raise FrozenBaselineCheckError(
            f"schema: {path}: 型不一致: 期待={expected_type}; 実際={type(value).__name__}"
        )

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            missing = sorted(set(required) - set(value))
            if missing:
                raise FrozenBaselineCheckError(f"schema: {path}: 必須キー不足: {missing!r}")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise FrozenBaselineCheckError(f"JSON Schemaのpropertiesが不正: {path}")
        additional = schema.get("additionalProperties", True)
        unknown = sorted(set(value) - set(properties))
        if additional is False and unknown:
            raise FrozenBaselineCheckError(f"schema: {path}: 未知キー: {unknown!r}")
        property_names = schema.get("propertyNames")
        for key, child in value.items():
            if isinstance(property_names, dict):
                _validate_schema(key, property_names, root_schema, f"{path}.<key>")
            child_schema = properties.get(key)
            if child_schema is None and isinstance(additional, dict):
                child_schema = additional
            if child_schema is not None:
                if not isinstance(child_schema, dict):
                    raise FrozenBaselineCheckError(
                        f"JSON Schemaのproperty定義が不正: {path}.{key}"
                    )
                _validate_schema(child, child_schema, root_schema, f"{path}.{key}")

    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise FrozenBaselineCheckError(
                f"schema: {path}: 配列要素数が下限未満: {len(value)} < {minimum}"
            )
        if isinstance(maximum, int) and len(value) > maximum:
            raise FrozenBaselineCheckError(
                f"schema: {path}: 配列要素数が上限超過: {len(value)} > {maximum}"
            )
        if schema.get("uniqueItems") is True:
            canonical = [
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for item in value
            ]
            if len(canonical) != len(set(canonical)):
                raise FrozenBaselineCheckError(f"schema: {path}: 配列要素が重複している")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, root_schema, f"{path}[{index}]")

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            raise FrozenBaselineCheckError(f"schema: {path}: 文字列が短すぎる")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise FrozenBaselineCheckError(f"schema: {path}: pattern不一致: {value!r}")
        if schema.get("format") == "date":
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise FrozenBaselineCheckError(
                    f"schema: {path}: 実在する日付でない: {value}"
                ) from exc
            if parsed.isoformat() != value:
                raise FrozenBaselineCheckError(
                    f"schema: {path}: ISO日付でない: {value}"
                )


def _expect_object(value: Any, label: str) -> dict[str, Any]:
    """値をobjectとして返し、異なる場合は検査エラーにする。"""
    if not isinstance(value, dict):
        raise FrozenBaselineCheckError(f"{label} はobjectでなければならない")
    return value


def _expect_list(value: Any, label: str) -> list[Any]:
    """値をarrayとして返し、異なる場合は検査エラーにする。"""
    if not isinstance(value, list):
        raise FrozenBaselineCheckError(f"{label} はarrayでなければならない")
    return value


def _check_exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    """objectのキー集合が期待集合と完全一致することを検査する。"""
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise FrozenBaselineCheckError(
            f"{label} のキーがexact-set不一致: 不足={missing!r}; 過剰={unexpected!r}"
        )


def _normalize_unordered_json(value: Any) -> Any:
    """changesの順序非依存なJSON値を再帰的な決定的正規形へ変換する。

    dictはキー順、listは正規化済み要素のJSON表現順に揃える。
    """
    if isinstance(value, dict):
        return {
            key: _normalize_unordered_json(value[key])
            for key in sorted(value)
        }
    if isinstance(value, list):
        normalized_items = [_normalize_unordered_json(item) for item in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    return value


def _check_empty_changes_move_identity(
    record: dict[str, Any], record_index: int, changes: list[Any]
) -> None:
    """changes が空なら識別値か配置の移動を主張していることを検査する。"""
    if changes:
        return
    prior_identity = record.get("prior_identity")
    new_identity = record.get("new_identity")
    placement_change = record.get("placement_change")
    if not (
        isinstance(prior_identity, dict)
        and isinstance(new_identity, dict)
        and isinstance(placement_change, dict)
        and "before" in placement_change
        and "after" in placement_change
    ):
        return
    identity_moved = prior_identity != new_identity
    placement_moved = placement_change["before"] != placement_change["after"]
    if not identity_moved and not placement_moved:
        raise FrozenBaselineCheckError(
            f"history[{record_index}]: changes が空で識別値も配置も動かず、"
            "何も主張していない"
        )


def _check_history_change_is_effective(
    change: dict[str, Any], record_index: int, change_index: int
) -> None:
    """changes entry が意味上の規範状態変更を主張していることを検査する。

    changesのaspectは台帳文書の8事項に閉じている。そのlistは順序に意味を持たず、
    movement_rules.triggersとuniversal_lower_boundはfrozenset、declarations配下の
    frozen_targetsの導出値もfrozensetで扱う。implementation_bindings.code_assetsは
    別検査がpath昇順を強制するため、再帰的な正規形で比較してよい。
    placement_changeはchangesのaspectではなく射程外とする。
    """
    if (
        "before" in change
        and "after" in change
        and _normalize_unordered_json(change["before"])
        == _normalize_unordered_json(change["after"])
    ):
        raise FrozenBaselineCheckError(
            f"history[{record_index}].changes[{change_index}]: "
            "before と after が意味上同一で、何も変更していない"
        )


def _precheck_history(ledger: dict[str, Any]) -> None:
    """schema検査より先に履歴のfail-closed条件を明確なエラーへする。"""
    history = ledger.get("history")
    if not isinstance(history, list):
        return
    for record_index, raw_record in enumerate(history):
        if not isinstance(raw_record, dict):
            continue
        if "placement_change" not in raw_record:
            raise FrozenBaselineCheckError(
                f"replay: history[{record_index}].placement_change がなく placements を復元できない"
            )
        raw_changes = raw_record.get("changes")
        if isinstance(raw_changes, list):
            _check_empty_changes_move_identity(raw_record, record_index, raw_changes)
            for change_index, raw_change in enumerate(raw_changes):
                if not isinstance(raw_change, dict):
                    continue
                _check_history_change_is_effective(
                    raw_change, record_index, change_index
                )
                aspect = raw_change.get("aspect")
                if isinstance(aspect, str) and aspect not in CHANGE_ASPECTS:
                    raise FrozenBaselineCheckError(
                        "未知の changes[].aspect: "
                        f"history[{record_index}].changes[{change_index}]={aspect}"
                    )
        for state_name in ("prior_identity", "new_identity"):
            raw_state = raw_record.get(state_name)
            if not isinstance(raw_state, dict):
                continue
            present = raw_state.get("present")
            values = raw_state.get("values")
            if present is False and isinstance(values, list) and values:
                message = (
                    f"history[{record_index}].{state_name}: present=false なら "
                    "values は空配列でなければならない"
                )
                raise FrozenBaselineCheckError(message)
            if present is True and isinstance(values, list) and not values:
                message = (
                    f"history[{record_index}].{state_name}: present=true なら "
                    "values は空であってはならない"
                )
                raise FrozenBaselineCheckError(
                    message
                )


def _check_movement_rules(ledger: dict[str, Any]) -> None:
    """移動規則の閉じた集合と参照整合を検査する。"""
    rules = _expect_object(ledger["movement_rules"], "movement_rules")
    _check_exact_keys(
        rules,
        frozenset({"triggers", "universal_lower_bound", "additional_targets", "self_change"}),
        "movement_rules",
    )
    triggers = _expect_list(rules["triggers"], "movement_rules.triggers")
    trigger_set = frozenset(triggers)
    if len(triggers) != len(trigger_set):
        raise FrozenBaselineCheckError("movement_rules.triggers が重複している")
    if trigger_set != MOVEMENT_TRIGGERS:
        raise FrozenBaselineCheckError(
            "movement_rules.triggers が閉じた集合と不一致: "
            f"不足={sorted(MOVEMENT_TRIGGERS - trigger_set)!r}; "
            f"過剰={sorted(trigger_set - MOVEMENT_TRIGGERS)!r}"
        )

    lower_bound = _expect_list(
        rules["universal_lower_bound"], "movement_rules.universal_lower_bound"
    )
    lower_bound_set = frozenset(lower_bound)
    if len(lower_bound) != len(lower_bound_set):
        raise FrozenBaselineCheckError("movement_rules.universal_lower_bound が重複している")
    if lower_bound_set != UNIVERSAL_LOWER_BOUND:
        raise FrozenBaselineCheckError(
            "movement_rules.universal_lower_bound は5軸すべてが必須: "
            f"不足={sorted(UNIVERSAL_LOWER_BOUND - lower_bound_set)!r}; "
            f"過剰={sorted(lower_bound_set - UNIVERSAL_LOWER_BOUND)!r}"
        )

    additional_targets = _expect_object(
        rules["additional_targets"], "movement_rules.additional_targets"
    )
    unknown_triggers = sorted(set(additional_targets) - trigger_set)
    if unknown_triggers:
        raise FrozenBaselineCheckError(
            "movement_rules.additional_targets に triggers 外のキーがある: "
            f"{unknown_triggers!r}"
        )
    declared_series = set(_expect_object(ledger["declarations"], "declarations"))
    for trigger, raw_targets in additional_targets.items():
        targets = _expect_list(raw_targets, f"movement_rules.additional_targets.{trigger}")
        if len(targets) != len(set(targets)):
            raise FrozenBaselineCheckError(
                f"movement_rules.additional_targets.{trigger} が重複している"
            )
        unknown_series = sorted(set(targets) - declared_series)
        if unknown_series:
            raise FrozenBaselineCheckError(
                f"movement_rules.additional_targets.{trigger} に未知系列がある: {unknown_series!r}"
            )

    self_change = _expect_object(rules["self_change"], "movement_rules.self_change")
    _check_exact_keys(
        self_change,
        frozenset({"trigger", "targets"}),
        "movement_rules.self_change",
    )
    if self_change != {"trigger": "rule_self_change", "targets": ["*"]}:
        raise FrozenBaselineCheckError("movement_rules.self_change の形が不正")


def _safe_asset_path(root: Path, path_text: str) -> Path:
    """コード資産パスを検証して絶対パスへ変換する。"""
    pure_path = PurePosixPath(path_text)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise FrozenBaselineCheckError(f"code_assets.path がリポジトリ相対でない: {path_text}")
    return root.joinpath(*pure_path.parts)


def _module_defines_symbol(path: Path, symbol: str) -> bool:
    """Pythonソースがトップレベルでsymbolを定義しているか返す。"""
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise FrozenBaselineCheckError(f"registryソースを解析できない: {path}: {exc}") from exc
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == symbol for target in targets):
                return True
    return False


def _check_implementation_bindings(root: Path, ledger: dict[str, Any]) -> None:
    """実装資産の生bytes digest、順序、registryを検査する。"""
    bindings = _expect_object(ledger["implementation_bindings"], "implementation_bindings")
    _check_exact_keys(
        bindings,
        frozenset({"code_assets", "strategy_keys", "registry"}),
        "implementation_bindings",
    )
    code_assets = _expect_list(bindings["code_assets"], "implementation_bindings.code_assets")
    paths = [
        str(_expect_object(item, "code_assets item").get("path")) for item in code_assets
    ]
    if paths != sorted(paths):
        raise FrozenBaselineCheckError("implementation_bindings.code_assets は path 昇順でない")
    if len(paths) != len(set(paths)):
        raise FrozenBaselineCheckError("implementation_bindings.code_assets の path が重複している")
    if frozenset(paths) != CODE_ASSET_PATHS:
        raise FrozenBaselineCheckError(
            "implementation_bindings.code_assets の対象がexact-set不一致: "
            f"不足={sorted(CODE_ASSET_PATHS - frozenset(paths))!r}; "
            f"過剰={sorted(frozenset(paths) - CODE_ASSET_PATHS)!r}"
        )
    for index, raw_asset in enumerate(code_assets):
        asset = _expect_object(raw_asset, f"code_assets[{index}]")
        path_text = str(asset["path"])
        path = _safe_asset_path(root, path_text)
        if path.is_symlink():
            raise FrozenBaselineCheckError(f"code_assets は symlink を許可しない: {path_text}")
        try:
            actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise FrozenBaselineCheckError(f"code_assets を読めない: {path_text}: {exc}") from exc
        if asset["sha256"] != actual_digest:
            raise FrozenBaselineCheckError(
                f"implementation_bindings.code_assets の sha256 が不一致: {path_text}"
            )

    registry = _expect_object(bindings["registry"], "implementation_bindings.registry")
    registry_path_text = str(registry["path"])
    if registry_path_text not in CODE_ASSET_PATHS:
        raise FrozenBaselineCheckError("implementation_bindings.registry.path が code_assets 外")
    registry_path = _safe_asset_path(root, registry_path_text)
    symbol = str(registry["symbol"])
    if not _module_defines_symbol(registry_path, symbol):
        raise FrozenBaselineCheckError(
            f"implementation_bindings.registry.symbol が実在しない: {registry_path_text}:{symbol}"
        )

    recorded_strategy_keys = bindings["strategy_keys"]
    actual_strategy_keys = sorted(
        f"{identity}/{granularity}"
        for identity, granularity in COMPARISON_STRATEGIES
    )
    if recorded_strategy_keys != actual_strategy_keys:
        raise FrozenBaselineCheckError(
            "implementation_bindings.strategy_keys がregistryと不一致: "
            f"期待={actual_strategy_keys!r}; 実際={recorded_strategy_keys!r}"
        )


def _identity_values(raw_values: Any, label: str) -> frozenset[IdentityValue]:
    """履歴の識別値配列を重複のない値集合へ変換する。"""
    values = _expect_list(raw_values, label)
    result = frozenset(
        IdentityValue(
            kind=str(_expect_object(raw_value, f"{label} item")["kind"]),
            value=str(_expect_object(raw_value, f"{label} item")["value"]),
        )
        for raw_value in values
    )
    if len(result) != len(values):
        raise FrozenBaselineCheckError(f"{label} が重複している")
    return result


def _latest_history_by_series(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """各系列の履歴末尾を返す。"""
    latest: dict[str, dict[str, Any]] = {}
    for index, raw_record in enumerate(_expect_list(ledger["history"], "history")):
        record = _expect_object(raw_record, f"history[{index}]")
        latest[str(record["series"])] = record
    return latest


def _derive_current_identities(
    root: Path,
    ledger: dict[str, Any],
    strategies: Mapping[tuple[str, str], ComparisonStrategy] | None = None,
) -> dict[str, frozenset[IdentityValue]]:
    """宣言から素材を収集し指定registry戦略で現在の識別値を導出する。"""
    strategy_registry = COMPARISON_STRATEGIES if strategies is None else strategies
    declarations = _expect_object(ledger["declarations"], "declarations")
    used_strategy_keys: set[tuple[str, str]] = set()
    derived: dict[str, frozenset[IdentityValue]] = {}
    for series, raw_declaration in declarations.items():
        declaration = _expect_object(raw_declaration, f"declarations.{series}")
        basis_series = str(declaration["basis_series"])
        if basis_series not in declarations:
            raise FrozenBaselineCheckError(
                f"declarations.{series}.basis_series が未知系列を参照している: {basis_series}"
            )
        strategy_key = (str(declaration["identity"]), str(declaration["granularity"]))
        strategy = strategy_registry.get(strategy_key)
        if strategy is None:
            raise FrozenBaselineCheckError(
                f"declarations.{series} の identity/granularity に戦略がない: "
                f"{strategy_key[0]}/{strategy_key[1]}"
            )
        used_strategy_keys.add(strategy_key)
        targets = [str(target) for target in _expect_list(
            declaration["frozen_targets"], f"declarations.{series}.frozen_targets"
        )]
        requested_paths = sorted({target.partition("#")[0] for target in targets})
        try:
            materials = collect_materials(root, targets, requested_paths)
            strategy_values = strategy(materials, targets)
        except (FrozenBaselineError, OSError) as exc:
            message = f"declarations.{series} の戦略実行に失敗: {exc}"
            raise FrozenBaselineCheckError(message) from exc
        derived[series] = frozenset(strategy_values)

    unused = set(strategy_registry) - used_strategy_keys
    if unused:
        formatted = sorted(f"{identity}/{granularity}" for identity, granularity in unused)
        raise FrozenBaselineCheckError(f"どの宣言からも参照されない戦略がある: {formatted!r}")
    return derived


def _extract_python_string_assignment_from_bytes(
    source: bytes,
    path_text: str,
    symbol: str,
) -> str:
    """Python生bytesのトップレベル文字列定数をASTから抽出する。"""
    try:
        tree = ast.parse(source, filename=path_text)
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise FrozenBaselineCheckError(
            f"placement_change.before のソースを解析できない: {path_text}: {exc}"
        ) from exc
    values: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == symbol for target in node.targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    values.append(node.value.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == symbol:
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    values.append(node.value.value)
    if len(values) != 1:
        raise FrozenBaselineCheckError(
            "placement_change.before の python_assignment が一意に実在しない: "
            f"{path_text}:{symbol}"
        )
    return values[0]


def _extract_python_string_assignment(root: Path, locator: dict[str, Any]) -> str:
    """作業ツリーのpython_assignment locatorから文字列定数を抽出する。"""
    path_text = str(locator["path"])
    path = _safe_asset_path(root, path_text)
    symbol = str(locator["symbol"])
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise FrozenBaselineCheckError(
            f"placement_change.before のソースを読めない: {path_text}: {exc}"
        ) from exc
    return _extract_python_string_assignment_from_bytes(source, path_text, symbol)


def _expected_ledger_placement(series: str) -> list[dict[str, str]]:
    """現在台帳内の系列を指す導出済みlocatorを返す。"""
    return [{"kind": "ledger_series", "path": LEDGER_PATH.as_posix(), "series": series}]


def _check_derived_history_values(
    ledger: dict[str, Any],
    current_identities: dict[str, frozenset[IdentityValue]],
) -> None:
    """履歴の申告値をソース・素材・locatorからの導出値と照合する。"""
    declarations = _expect_object(ledger["declarations"], "declarations")
    records_by_series: dict[str, list[dict[str, Any]]] = {}
    for index, raw_record in enumerate(_expect_list(ledger["history"], "history")):
        record = _expect_object(raw_record, f"history[{index}]")
        records_by_series.setdefault(str(record["series"]), []).append(record)
    if set(records_by_series) != set(declarations):
        raise FrozenBaselineCheckError(
            "history末尾の系列がdeclarationsとexact-set不一致: "
            f"不足={sorted(set(declarations) - set(records_by_series))!r}; "
            f"過剰={sorted(set(records_by_series) - set(declarations))!r}"
        )
    placements = _expect_object(ledger["placements"], "placements")
    for series, records in records_by_series.items():
        first_placement = _expect_object(
            records[0]["placement_change"], f"history.{series}[0].placement_change"
        )
        first_before = first_placement["before"]
        expected_before = LEGACY_PLACEMENTS.get(series)
        if first_before != expected_before:
            raise FrozenBaselineCheckError(
                f"history.{series}.placement_change.before が導出値と不一致"
            )
        previous_after: Any = None
        previous_new: dict[str, Any] | None = None
        for record_index, record in enumerate(records):
            placement_change = _expect_object(
                record["placement_change"],
                f"history.{series}[{record_index}].placement_change",
            )
            before = placement_change["before"]
            after = placement_change["after"]
            prior_state = _expect_object(
                record["prior_identity"],
                f"history.{series}[{record_index}].prior_identity",
            )
            if record_index == 0:
                actual_prior = _identity_values(
                    prior_state["values"],
                    f"history.{series}[0].prior_identity.values",
                )
                # 移設後の作業ツリーにはbeforeの定数が存在しない。初回priorと
                # base treeの定数の一致はacceptance bootstrapで機械照合する。
                if prior_state["present"] is not True or not actual_prior:
                    raise FrozenBaselineCheckError(
                        f"history.{series}.prior_identity が存在する識別値でない"
                    )
            else:
                if before != previous_after:
                    raise FrozenBaselineCheckError(
                        f"history.{series}.placement_change の前後が連続していない"
                    )
                if prior_state != previous_new:
                    raise FrozenBaselineCheckError(
                        f"history.{series}.prior_identity が直前new_identityと不一致"
                    )
            derived_moved = before != after
            if record["moved"] is not derived_moved:
                raise FrozenBaselineCheckError(
                    f"history.{series}.moved がlocator導出値と不一致"
                )
            previous_after = copy.deepcopy(after)
            previous_new = copy.deepcopy(
                _expect_object(
                    record["new_identity"],
                    f"history.{series}[{record_index}].new_identity",
                )
            )

        expected_after = _expected_ledger_placement(series)
        if previous_after != expected_after:
            raise FrozenBaselineCheckError(
                f"history.{series}.placement_change.after が導出値と不一致"
            )
        if placements.get(series) != expected_after:
            raise FrozenBaselineCheckError(f"placements.{series} が台帳系列locatorと不一致")
        if previous_new is None:
            raise FrozenBaselineCheckError(f"history.{series} に記録がない")
        actual_new = _identity_values(
            previous_new["values"], f"history.{series}.new_identity.values"
        )
        if previous_new["present"] is not True or not actual_new:
            raise FrozenBaselineCheckError(
                f"history.{series}.new_identity が存在する識別値でない"
            )

    _check_basis_correspondence(ledger, current_identities)


def _check_basis_correspondence(
    ledger: dict[str, Any],
    current_identities: Mapping[str, frozenset[IdentityValue]],
) -> None:
    """各宣言の導出値をbasis系列の履歴末尾と照合する。"""
    declarations = _expect_object(ledger["declarations"], "declarations")
    latest = _latest_history_by_series(ledger)
    for series, raw_declaration in declarations.items():
        declaration = _expect_object(raw_declaration, f"declarations.{series}")
        basis_series = str(declaration["basis_series"])
        basis_record = latest.get(basis_series)
        if basis_record is None:
            raise FrozenBaselineCheckError(
                f"declarations.{series}.basis_series の履歴がない: {basis_series}"
            )
        basis_state = _expect_object(
            basis_record["new_identity"],
            f"history.{basis_series}.new_identity",
        )
        basis_values = _identity_values(
            basis_state["values"],
            f"history.{basis_series}.new_identity.values",
        )
        if basis_state["present"] is not True or current_identities[series] != basis_values:
            if basis_series == series:
                raise FrozenBaselineCheckError(
                    f"history.{series}.new_identity が戦略の導出値と不一致"
                )
            raise FrozenBaselineCheckError(
                f"declarations.{series} の導出値がbasis_series={basis_series}の"
                "履歴末尾と不一致"
            )


def _value_or_absent(container: Mapping[str, Any], key: str) -> Any:
    """キーが無い状態をsentinelへ変換して返す。"""
    return copy.deepcopy(container[key]) if key in container else copy.deepcopy(ABSENT)


def _assign_or_remove(container: dict[str, Any], key: str, value: Any) -> None:
    """sentinelならキーを除去し、それ以外なら値を代入する。"""
    if value == ABSENT:
        container.pop(key, None)
    else:
        container[key] = copy.deepcopy(value)


def _first_change_before(
    history: list[Any],
    series: str,
    aspect: str,
) -> tuple[bool, Any]:
    """系列・aspectの最初のbeforeを返す。"""
    for raw_record in history:
        record = _expect_object(raw_record, "history record")
        if record["series"] != series:
            continue
        for raw_change in _expect_list(record["changes"], "history changes"):
            change = _expect_object(raw_change, "history change")
            if change["aspect"] == aspect:
                return True, copy.deepcopy(change["before"])
    return False, None


def _initial_replay_state(ledger: dict[str, Any]) -> dict[str, Any]:
    """最初のbeforeと未変更規範値からreplay開始状態を組み立てる。"""
    history = _expect_list(ledger["history"], "history")
    state: dict[str, Any] = {}
    for aspect in ("acceptance", "movement_rules", "implementation_bindings"):
        found = False
        initial: Any = None
        for raw_record in history:
            record = _expect_object(raw_record, "history record")
            for raw_change in _expect_list(record["changes"], "history changes"):
                change = _expect_object(raw_change, "history change")
                if change["aspect"] == aspect:
                    found = True
                    initial = copy.deepcopy(change["before"])
                    break
            if found:
                break
        if found:
            _assign_or_remove(state, aspect, initial)
        else:
            state[aspect] = copy.deepcopy(ledger[aspect])

    declarations = _expect_object(ledger["declarations"], "declarations")
    state_declarations: dict[str, Any] = {}
    for series, raw_declaration in declarations.items():
        declaration = _expect_object(raw_declaration, f"declarations.{series}")
        initial_declaration: dict[str, Any] = {}
        for aspect in ("frozen_targets", "identity", "granularity", "basis_series"):
            found, before = _first_change_before(history, series, aspect)
            if found:
                _assign_or_remove(initial_declaration, aspect, before)
            elif aspect == "basis_series":
                initial_declaration[aspect] = copy.deepcopy(declaration[aspect])
        if initial_declaration:
            state_declarations[series] = initial_declaration
    state["declarations"] = state_declarations

    initial_placements: dict[str, Any] = {}
    for raw_record in history:
        record = _expect_object(raw_record, "history record")
        series = str(record["series"])
        if series not in initial_placements:
            placement_change = _expect_object(record["placement_change"], "placement_change")
            initial_placements[series] = copy.deepcopy(placement_change["before"])
    state["placements"] = initial_placements
    return state


def _apply_change(state: dict[str, Any], series: str, change: dict[str, Any]) -> None:
    """1件のaspect変更をbefore連続性検査付きでreplayする。"""
    aspect = str(change["aspect"])
    if aspect in {"acceptance", "movement_rules", "implementation_bindings"}:
        current = _value_or_absent(state, aspect)
        if current != change["before"]:
            raise FrozenBaselineCheckError(f"replay: {aspect} の before が直前状態と不一致")
        _assign_or_remove(state, aspect, change["after"])
        return

    declarations = _expect_object(state["declarations"], "replay declarations")
    if aspect == "series_retired":
        current = _value_or_absent(declarations, series)
        if current != change["before"]:
            raise FrozenBaselineCheckError(
                f"replay: declarations.{series} の before が直前状態と不一致"
            )
        _assign_or_remove(declarations, series, change["after"])
        return

    declaration = declarations.setdefault(series, {})
    if not isinstance(declaration, dict):
        raise FrozenBaselineCheckError(f"replay: declarations.{series} がobjectでない")
    current = _value_or_absent(declaration, aspect)
    if current != change["before"]:
        raise FrozenBaselineCheckError(
            f"replay: declarations.{series}.{aspect} の before が直前状態と不一致"
        )
    _assign_or_remove(declaration, aspect, change["after"])


def _check_replay(ledger: dict[str, Any]) -> None:
    """changesとplacement_changeをfoldして規範状態5つとの完全一致を検査する。"""
    state = _initial_replay_state(ledger)
    seen_batches: set[tuple[str, str]] = set()
    for record_index, raw_record in enumerate(_expect_list(ledger["history"], "history")):
        record = _expect_object(raw_record, f"history[{record_index}]")
        series = str(record["series"])
        batch_key = (str(record["acceptance_id"]), series)
        if batch_key in seen_batches:
            raise FrozenBaselineCheckError(
                f"replay: acceptance_idとseriesが重複している: {batch_key!r}"
            )
        seen_batches.add(batch_key)
        seen_aspects: set[str] = set()
        for raw_change in _expect_list(record["changes"], f"history[{record_index}].changes"):
            change = _expect_object(raw_change, f"history[{record_index}].change")
            aspect = str(change["aspect"])
            if aspect in seen_aspects:
                raise FrozenBaselineCheckError(
                    f"replay: 同一batchでaspectが重複している: {aspect}"
                )
            seen_aspects.add(aspect)
            _apply_change(state, series, change)

        placement_change = _expect_object(
            record["placement_change"], f"history[{record_index}].placement_change"
        )
        placements = _expect_object(state["placements"], "replay placements")
        current_placement = _value_or_absent(placements, series)
        if current_placement != placement_change["before"]:
            raise FrozenBaselineCheckError(
                f"replay: placements.{series} の before が直前状態と不一致"
            )
        _assign_or_remove(placements, series, placement_change["after"])

    normative_state = {
        "acceptance": ledger["acceptance"],
        "movement_rules": ledger["movement_rules"],
        "implementation_bindings": ledger["implementation_bindings"],
        "placements": ledger["placements"],
        "declarations": ledger["declarations"],
    }
    if state != normative_state:
        raise FrozenBaselineCheckError(
            "replay: fold(changes[] と placement_change) が規範状態5つと不一致"
        )


def _read_pull_request_event() -> _PullRequestEvent:
    """GITHUB_EVENT_PATHから受理遷移に必要な値を読み取る。"""
    event_path_text = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path_text:
        raise FrozenBaselineCheckError("GITHUB_EVENT_PATH が設定されていない")
    event_path = Path(event_path_text)
    try:
        event = json.loads(event_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrozenBaselineCheckError(
            f"GITHUB_EVENT_PATH のJSONを読み取れない: {event_path}: {exc}"
        ) from exc
    if not isinstance(event, dict):
        raise FrozenBaselineCheckError("GITHUB_EVENT_PATH のトップレベルがobjectでない")
    pull_request = event.get("pull_request")
    repository = event.get("repository")
    if not isinstance(pull_request, dict) or not isinstance(repository, dict):
        raise FrozenBaselineCheckError("pull_request event の必須objectがない")
    base = pull_request.get("base")
    head = pull_request.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        raise FrozenBaselineCheckError("pull_request.base/head がobjectでない")
    base_ref = base.get("ref")
    base_sha = base.get("sha")
    head_sha = head.get("sha")
    repository_name = repository.get("full_name")
    number = pull_request.get("number")
    if not all(
        isinstance(value, str) and value
        for value in (base_ref, base_sha, head_sha, repository_name)
    ):
        raise FrozenBaselineCheckError("pull_request event の文字列値が不足している")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise FrozenBaselineCheckError("pull_request.number が正の整数でない")
    return _PullRequestEvent(
        base_ref=base_ref,
        base_sha=base_sha,
        head_sha=head_sha,
        repository=repository_name,
        number=number,
    )


def _run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """指定rootでgitを環境依存の文字列復号なしに実行する。"""
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise FrozenBaselineCheckError(f"gitを実行できない: {exc}") from exc


def _resolve_commit(root: Path, revision: str, label: str) -> str:
    """revisionを完全なcommit SHAへ解決する。"""
    result = _run_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if result.returncode != 0:
        raise FrozenBaselineCheckError(f"{label} をcommitとして解決できない: {revision}")
    resolved = result.stdout.decode("ascii", errors="strict").strip()
    if re.fullmatch(r"[0-9a-f]{40}", resolved) is None:
        raise FrozenBaselineCheckError(f"{label} の解決結果が完全SHAでない: {resolved}")
    return resolved


def _head_parents(root: Path) -> tuple[str, ...]:
    """checkoutされたHEADの親SHAを順序どおり返す。"""
    result = _run_git(root, "rev-list", "--parents", "-n", "1", "HEAD")
    if result.returncode != 0:
        raise FrozenBaselineCheckError("HEAD の親を取得できない")
    fields = result.stdout.decode("ascii", errors="strict").split()
    if not fields or re.fullmatch(r"[0-9a-f]{40}", fields[0]) is None:
        raise FrozenBaselineCheckError("HEAD の親情報が不正")
    parents = tuple(fields[1:])
    if any(re.fullmatch(r"[0-9a-f]{40}", parent) is None for parent in parents):
        raise FrozenBaselineCheckError("HEAD の親SHAが不正")
    return parents


def _git_tree_entry(root: Path, revision: str, path_text: str) -> tuple[str, str] | None:
    """revisionの指定pathについてmodeとobject種別を返す。"""
    result = _run_git(root, "ls-tree", revision, "--", path_text)
    if result.returncode != 0:
        raise FrozenBaselineCheckError(
            f"git treeを確認できない: {revision}:{path_text}"
        )
    output = result.stdout.decode("utf-8", errors="strict").strip()
    if not output:
        return None
    metadata, separator, observed_path = output.partition("\t")
    fields = metadata.split()
    if not separator or len(fields) != 3 or observed_path != path_text:
        raise FrozenBaselineCheckError(
            f"git tree entryが一意な形式でない: {revision}:{path_text}"
        )
    return fields[0], fields[1]


def _git_file_bytes(root: Path, revision: str, path_text: str) -> bytes:
    """revisionのtreeにある通常ファイルの生bytesを返す。"""
    entry = _git_tree_entry(root, revision, path_text)
    if entry is None:
        raise FrozenBaselineCheckError(f"git treeにファイルがない: {revision}:{path_text}")
    mode, object_type = entry
    if mode == "120000":
        raise FrozenBaselineCheckError(f"git treeのsymlinkは読まない: {revision}:{path_text}")
    if object_type != "blob":
        raise FrozenBaselineCheckError(f"git tree entryがblobでない: {revision}:{path_text}")
    result = _run_git(root, "show", f"{revision}:{path_text}")
    if result.returncode != 0:
        raise FrozenBaselineCheckError(f"git treeのblobを読めない: {revision}:{path_text}")
    return result.stdout


def _normative_state(ledger: dict[str, Any]) -> dict[str, Any]:
    """台帳から規範状態5つを深いコピーで返す。"""
    return {
        "acceptance": copy.deepcopy(ledger["acceptance"]),
        "movement_rules": copy.deepcopy(ledger["movement_rules"]),
        "implementation_bindings": copy.deepcopy(ledger["implementation_bindings"]),
        "placements": copy.deepcopy(ledger["placements"]),
        "declarations": copy.deepcopy(ledger["declarations"]),
    }


def _check_ledger_structure(root: Path, ledger: dict[str, Any]) -> None:
    """作業ツリーに依存しない台帳構造を検査する。"""
    _check_exact_keys(ledger, TOP_LEVEL_KEYS, "トップレベル")
    _precheck_history(ledger)
    schema = _load_schema(root / SCHEMA_PATH)
    _validate_schema(ledger, schema, schema, "$")
    _check_movement_rules(ledger)


def _check_base_code_assets(root: Path, base_sha: str, ledger: dict[str, Any]) -> None:
    """base treeのcode_assetsをbase台帳の生bytes digestと照合する。"""
    bindings = _expect_object(ledger["implementation_bindings"], "implementation_bindings")
    assets = _expect_list(bindings["code_assets"], "implementation_bindings.code_assets")
    for index, raw_asset in enumerate(assets):
        asset = _expect_object(raw_asset, f"base code_assets[{index}]")
        path_text = str(asset["path"])
        actual = hashlib.sha256(_git_file_bytes(root, base_sha, path_text)).hexdigest()
        if asset["sha256"] != actual:
            raise FrozenBaselineCheckError(
                f"base implementation_bindings.code_assets の sha256 が不一致: {path_text}"
            )
    registry = _expect_object(bindings["registry"], "implementation_bindings.registry")
    registry_path = str(registry["path"])
    registry_source = _git_file_bytes(root, base_sha, registry_path)
    symbol = str(registry["symbol"])
    try:
        tree = ast.parse(registry_source, filename=f"{base_sha}:{registry_path}")
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise FrozenBaselineCheckError(f"base registryを解析できない: {exc}") from exc
    if not any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == symbol
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        for node in tree.body
    ):
        raise FrozenBaselineCheckError(
            f"base implementation_bindings.registry.symbol が実在しない: {registry_path}:{symbol}"
        )


def _bootstrap_expected_state(root: Path) -> dict[str, Any]:
    """検査器側で閉じた初回規範状態5つを現在の生bytesから構成する。"""
    code_assets = [
        {
            "path": path_text,
            "sha256": hashlib.sha256(_safe_asset_path(root, path_text).read_bytes()).hexdigest(),
        }
        for path_text in sorted(CODE_ASSET_PATHS)
    ]
    return {
        "acceptance": {
            "unit": "pull_request",
            "base_ref": "develop",
            "prior_state": "event.pull_request.base.sha",
            "posterior_state": "checkout_head",
            "parent_check": {"first": "base.sha", "second": "head.sha"},
            "acceptance_id_source": "repository_and_pr_number",
            "self_reference": "none",
        },
        "movement_rules": {
            "triggers": list(BOOTSTRAP_TRIGGERS),
            "universal_lower_bound": list(BOOTSTRAP_LOWER_BOUND),
            "additional_targets": {},
            "self_change": {"trigger": "rule_self_change", "targets": ["*"]},
        },
        "implementation_bindings": {
            "code_assets": code_assets,
            "strategy_keys": ["literal_commit_string/json_pointer_value"],
            "registry": {
                "path": "scripts/frozen_baselines.py",
                "symbol": "COMPARISON_STRATEGIES",
            },
        },
        "placements": {"oracle_input": _expected_ledger_placement("oracle_input")},
        "declarations": {
            "oracle_input": {
                "frozen_targets": list(BOOTSTRAP_TARGETS),
                "identity": "literal_commit_string",
                "granularity": "json_pointer_value",
                "basis_series": "oracle_input",
            }
        },
    }


def _check_bootstrap(
    root: Path,
    base_sha: str,
    event: _PullRequestEvent,
    head_ledger: dict[str, Any],
) -> None:
    """base台帳不在時に検査器側の閉じた初回遷移だけを許可する。"""
    expected_state = _bootstrap_expected_state(root)
    if _normative_state(head_ledger) != expected_state:
        raise FrozenBaselineCheckError(
            "bootstrap: 規範状態5つが検査器側の初回exact-setと不一致"
        )
    if event.acceptance_id != BOOTSTRAP_ACCEPTANCE_ID:
        raise FrozenBaselineCheckError(
            "bootstrap: base台帳不在を許す初回acceptance_idと不一致: "
            f"期待={BOOTSTRAP_ACCEPTANCE_ID}; 実際={event.acceptance_id}"
        )
    history = _expect_list(head_ledger["history"], "history")
    if len(history) != 1:
        raise FrozenBaselineCheckError(
            f"bootstrap: 初回履歴は1件でなければならない: 実際={len(history)}"
        )
    record = _expect_object(history[0], "history[0]")
    if record["acceptance_id"] != event.acceptance_id:
        raise FrozenBaselineCheckError(
            "bootstrap: 初回記録のacceptance_idがevent導出値と不一致"
        )
    legacy_locator = LEGACY_PLACEMENTS["oracle_input"][0]
    legacy_path = legacy_locator["path"]
    source = _git_file_bytes(root, base_sha, legacy_path)
    prior_value = _extract_python_string_assignment_from_bytes(
        source,
        legacy_path,
        legacy_locator["symbol"],
    )
    expected_prior = frozenset(
        {IdentityValue(kind="literal_commit_string", value=prior_value)}
    )
    prior_state = _expect_object(record["prior_identity"], "history[0].prior_identity")
    actual_prior = _identity_values(
        prior_state["values"], "history[0].prior_identity.values"
    )
    if prior_state["present"] is not True or actual_prior != expected_prior:
        raise FrozenBaselineCheckError(
            "bootstrap: prior_identity がbase treeの移設元定数と不一致"
        )


def _history_record_key(record: dict[str, Any]) -> tuple[str, str]:
    """履歴レコードを受理IDと系列の組へ変換する。"""
    return str(record.get("acceptance_id")), str(record.get("series"))


def _check_history_append_only(
    base_ledger: dict[str, Any],
    head_ledger: dict[str, Any],
) -> list[dict[str, Any]]:
    """base履歴がhead履歴の逐語的prefixであることを検査し追記分を返す。"""
    base_history = [
        _expect_object(record, f"base history[{index}]")
        for index, record in enumerate(_expect_list(base_ledger["history"], "base history"))
    ]
    head_history = [
        _expect_object(record, f"head history[{index}]")
        for index, record in enumerate(_expect_list(head_ledger["history"], "head history"))
    ]
    if len(head_history) < len(base_history):
        raise FrozenBaselineCheckError(
            "historyの既存記録が削除された: "
            f"base={len(base_history)}; head={len(head_history)}"
        )
    for index, base_record in enumerate(base_history):
        head_record = head_history[index]
        if base_record == head_record:
            continue
        if len(base_history) == len(head_history) and _history_record_key(
            base_record
        ) != _history_record_key(head_record):
            raise FrozenBaselineCheckError(
                f"historyの同数置換を検出した: index={index}"
            )
        raise FrozenBaselineCheckError(
            f"historyの既存記録が書き換えられた: index={index}"
        )
    return head_history[len(base_history) :]


def _base_value_for_change(
    base_state: dict[str, Any],
    series: str,
    aspect: str,
) -> Any:
    """batch各recordのbeforeと比較するbase規範値を返す。"""
    if aspect in {"acceptance", "movement_rules", "implementation_bindings"}:
        return _value_or_absent(base_state, aspect)
    declarations = _expect_object(base_state["declarations"], "base declarations")
    if aspect == "series_retired":
        return _value_or_absent(declarations, series)
    raw_declaration = declarations.get(series)
    if not isinstance(raw_declaration, dict):
        return copy.deepcopy(ABSENT)
    return _value_or_absent(raw_declaration, aspect)


def _apply_acceptance_batch(
    base_ledger: dict[str, Any],
    head_ledger: dict[str, Any],
    records: list[dict[str, Any]],
    acceptance_id: str,
) -> None:
    """同一acceptance_idの追記record群をbase状態へ原子的にfoldする。"""
    base_state = _normative_state(base_ledger)
    state = copy.deepcopy(base_state)
    seen_pairs: set[tuple[str, str]] = set()
    seen_global_aspects: set[str] = set()
    for index, record in enumerate(records):
        if record["acceptance_id"] != acceptance_id:
            raise FrozenBaselineCheckError(
                "追記recordのacceptance_idがevent導出値と不一致: "
                f"index={index}; 期待={acceptance_id}; 実際={record['acceptance_id']}"
            )
        series = str(record["series"])
        pair = (acceptance_id, series)
        if pair in seen_pairs:
            raise FrozenBaselineCheckError(
                f"batch内で(acceptance_id, series)が重複している: {pair!r}"
            )
        seen_pairs.add(pair)
        changes = [
            _expect_object(change, f"batch[{index}].changes[{change_index}]")
            for change_index, change in enumerate(
                _expect_list(record["changes"], f"batch[{index}].changes")
            )
        ]
        for change in changes:
            aspect = str(change["aspect"])
            expected_before = _base_value_for_change(base_state, series, aspect)
            if change["before"] != expected_before:
                raise FrozenBaselineCheckError(
                    "batch内recordのbeforeが同じbase状態を指していない: "
                    f"series={series}; aspect={aspect}"
                )
            if aspect in {"acceptance", "movement_rules", "implementation_bindings"}:
                if aspect in seen_global_aspects:
                    raise FrozenBaselineCheckError(
                        f"batch内でglobal aspectが複数回変更された: {aspect}"
                    )
                seen_global_aspects.add(aspect)
            _apply_change(state, series, change)

        placement_change = _expect_object(
            record["placement_change"], f"batch[{index}].placement_change"
        )
        base_placements = _expect_object(base_state["placements"], "base placements")
        expected_placement = _value_or_absent(base_placements, series)
        if placement_change["before"] != expected_placement:
            raise FrozenBaselineCheckError(
                "batch内recordのplacement beforeが同じbase状態を指していない: "
                f"series={series}"
            )
        placements = _expect_object(state["placements"], "batch placements")
        _assign_or_remove(placements, series, placement_change["after"])

    if state != _normative_state(head_ledger):
        raise FrozenBaselineCheckError(
            "受理batchの原子的fold結果がHEADの規範状態5つと不一致"
        )


def _check_commit_reachability(
    root: Path,
    current_identities: dict[str, frozenset[IdentityValue]],
) -> None:
    """commit識別値がobjectとして存在しHEADの祖先でもあることを検査する。"""
    values = sorted(
        {
            identity.value
            for identities in current_identities.values()
            for identity in identities
            if identity.kind == "literal_commit_string"
        }
    )
    for value in values:
        existence = _run_git(root, "cat-file", "-e", f"{value}^{{commit}}")
        if existence.returncode != 0:
            raise FrozenBaselineCheckError(f"識別値commitを解決できない: {value}")
        ancestry = _run_git(root, "merge-base", "--is-ancestor", value, "HEAD")
        if ancestry.returncode == 1:
            raise FrozenBaselineCheckError(f"識別値commitがHEADから到達不能: {value}")
        if ancestry.returncode != 0:
            raise FrozenBaselineCheckError(
                f"識別値commitの到達可能性を確認できない: {value}"
            )


def check_acceptance(root: Path, ledger_path: Path) -> tuple[str, ...]:
    """pull_request eventとcheckout HEADの受理遷移を検査する。

    Args:
        root: git repositoryと作業ツリーのルート。
        ledger_path: HEAD側で内部不変量検査済みの台帳パス。

    Returns:
        標準出力へ明示する受理経路の説明。

    Raises:
        FrozenBaselineCheckError: event、git状態、遷移のいずれかが不正な場合。
    """
    event = _read_pull_request_event()
    if not (root / ".git").exists():
        raise FrozenBaselineCheckError("受理遷移検査には .git が必要")
    base_sha = _resolve_commit(root, event.base_sha, "event.pull_request.base.sha")
    head_sha = _resolve_commit(root, event.head_sha, "event.pull_request.head.sha")
    if event.base_ref != "develop":
        return (
            "frozen-baselines: acceptance not evaluated: "
            f"pull_request.base.ref={event.base_ref!r} は develop でない",
        )
    parents = _head_parents(root)
    if len(parents) != 2:
        raise FrozenBaselineCheckError(
            f"HEAD は2親のsynthetic mergeでない: parents={len(parents)}"
        )
    # この親照合が保証するのはeventとcheckoutの整合だけである。
    # baseの最新性はgithub-setup.md 2章 手続2の「base SHA の 3 点一致と head の拘束」が
    # 担い、台帳は保証しない(行番号は他PRのマージでずれるため節で指す)。
    if parents[0] != base_sha:
        raise FrozenBaselineCheckError(
            f"HEADの第1親がbase.shaと不一致: 期待={base_sha}; 実際={parents[0]}"
        )
    if parents[1] != head_sha:
        raise FrozenBaselineCheckError(
            f"HEADの第2親がhead.shaと不一致: 期待={head_sha}; 実際={parents[1]}"
        )

    head_ledger = load_frozen_baseline_ledger(ledger_path)
    current_identities = _derive_current_identities(root, head_ledger)
    base_entry = _git_tree_entry(root, base_sha, LEDGER_PATH.as_posix())
    _check_acceptance_scan_transition(
        root,
        base_sha,
        base_ledger_present=base_entry is not None,
    )
    if base_entry is None:
        # head側の検査器を実行する循環は残る。初回の信頼根は人間の逐行確認である。
        _check_bootstrap(root, base_sha, event, head_ledger)
        _check_commit_reachability(root, current_identities)
        return (
            "frozen-baselines: bootstrap acceptance: 初回の信頼根は人間の逐行確認",
            "frozen-baselines: bootstrap経路は、台帳を含むbase SHAで新たに評価される"
            "develop宛PRでは到達しない",
        )

    base_bytes = _git_file_bytes(root, base_sha, LEDGER_PATH.as_posix())
    try:
        base_ledger = parse_frozen_baseline_ledger(
            base_bytes,
            f"{base_sha}:{LEDGER_PATH.as_posix()}",
        )
    except FrozenBaselineError as exc:
        raise FrozenBaselineCheckError(f"base台帳を解析できない: {exc}") from exc
    _check_ledger_structure(root, base_ledger)
    _check_replay(base_ledger)
    _check_base_code_assets(root, base_sha, base_ledger)
    appended = _check_history_append_only(base_ledger, head_ledger)
    _apply_acceptance_batch(base_ledger, head_ledger, appended, event.acceptance_id)
    _check_commit_reachability(root, current_identities)
    return ()


def _is_scan_source_path(path_text: str) -> bool:
    """相対パスが走査母集団のPythonファイルか返す。"""
    pure_path = PurePosixPath(path_text)
    if (
        pure_path.is_absolute()
        or pure_path.as_posix() != path_text
        or ".." in pure_path.parts
        or pure_path.suffix != ".py"
    ):
        return False
    return pure_path.parts[:1] in {("scripts",), ("tests",)} or pure_path.parts[
        :2
    ] == ("backend", "tests")


def _parse_scan_allowlist(data: bytes, source: str) -> tuple[_ScanAllowlistEntry, ...]:
    """走査allow-listをexact-schemaで解析する。"""
    try:
        raw_allowlist = parse_frozen_baseline_ledger(data, source)
    except FrozenBaselineError as exc:
        raise FrozenBaselineCheckError(f"allow-listを解析できない: {exc}") from exc
    _check_exact_keys(raw_allowlist, SCAN_ALLOWLIST_ROOT_KEYS, "allow-list")
    if raw_allowlist["schema_version"] != 1 or isinstance(
        raw_allowlist["schema_version"], bool
    ):
        raise FrozenBaselineCheckError("allow-list.schema_version は1でなければならない")
    if raw_allowlist["asset_kind"] != SCAN_ALLOWLIST_ASSET_KIND:
        raise FrozenBaselineCheckError(
            "allow-list.asset_kind は frozen_baseline_scan_allowlist でなければならない"
        )

    entries: list[_ScanAllowlistEntry] = []
    seen: set[_ScanKey] = set()
    for index, raw_entry in enumerate(
        _expect_list(raw_allowlist["entries"], "allow-list.entries")
    ):
        label = f"allow-list.entries[{index}]"
        entry = _expect_object(raw_entry, label)
        _check_exact_keys(entry, SCAN_ALLOWLIST_ENTRY_KEYS, label)
        path_text = entry["path"]
        if not isinstance(path_text, str) or not _is_scan_source_path(path_text):
            raise FrozenBaselineCheckError(
                f"{label}.path が走査母集団の相対Pythonパスでない"
            )
        value = entry["value"]
        if (
            not isinstance(value, str)
            or SCAN_ALLOWLIST_VALUE_PATTERN.fullmatch(value) is None
        ):
            raise FrozenBaselineCheckError(
                f"{label}.value が40桁または64桁の小文字hexでない"
            )
        reason = entry["reason"]
        if not isinstance(reason, str) or not reason.strip():
            raise FrozenBaselineCheckError(f"{label}.reason が空である")
        pending_removal = entry["pending_removal"]
        if not isinstance(pending_removal, bool):
            raise FrozenBaselineCheckError(f"{label}.pending_removal が真偽値でない")
        parsed_entry = _ScanAllowlistEntry(
            path=path_text,
            value=value,
            reason=reason,
            pending_removal=pending_removal,
        )
        if parsed_entry.key in seen:
            raise FrozenBaselineCheckError(
                "allow-listの(path, value)が重複している: "
                f"{_format_scan_keys({parsed_entry.key})}"
            )
        seen.add(parsed_entry.key)
        entries.append(parsed_entry)
    return tuple(entries)


def _scan_python_sources(root: Path) -> _SourceScan:
    """3母集団の全Python本文から40桁・64桁hexを部分一致で走査する。"""
    pairs: set[_ScanKey] = set()
    occurrences = 0
    occurrences_40 = 0
    occurrences_64 = 0
    for source_root in SCAN_SOURCE_ROOTS:
        directory = root / source_root
        if not directory.is_dir() or directory.is_symlink():
            raise FrozenBaselineCheckError(
                f"走査母集団のdirectoryを読めない: {source_root}"
            )
        for path in sorted(directory.rglob("*.py")):
            relative_path = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file():
                raise FrozenBaselineCheckError(
                    f"走査母集団の通常ファイルでない: {relative_path}"
                )
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise FrozenBaselineCheckError(
                    f"走査母集団をUTF-8で読めない: {relative_path}: {exc}"
                ) from exc
            for match in SCAN_VALUE_PATTERN.finditer(source):
                value = match.group(0)
                pairs.add(_ScanKey(relative_path, value))
                occurrences += 1
                if len(value) == 40:
                    occurrences_40 += 1
                else:
                    occurrences_64 += 1
    return _SourceScan(
        occurrences=occurrences,
        occurrences_40=occurrences_40,
        occurrences_64=occurrences_64,
        pairs=frozenset(pairs),
    )


def _format_scan_keys(keys: set[_ScanKey] | frozenset[_ScanKey]) -> str:
    """走査キー集合を安定したエラー表示へ変換する。"""
    return "[" + ", ".join(f"({key.path}, {key.value})" for key in sorted(keys)) + "]"


def _check_scan_matches_allowlist(
    scan: _SourceScan,
    entries: tuple[_ScanAllowlistEntry, ...],
) -> None:
    """走査結果とallow-listを(path, value)の双方向exact-setで照合する。"""
    declared = frozenset(entry.key for entry in entries)
    unlisted = scan.pairs - declared
    if unlisted:
        raise FrozenBaselineCheckError(
            "走査で見つかったがallow-listにない(path, value): "
            f"{_format_scan_keys(unlisted)}"
        )
    stale = declared - scan.pairs
    if stale:
        raise FrozenBaselineCheckError(
            "allow-listにあるが走査で見つからない(path, value): "
            f"{_format_scan_keys(stale)}"
        )


def _check_scan_allowlist_transition(
    *,
    base_ledger_present: bool,
    base_entries: tuple[_ScanAllowlistEntry, ...] | None,
    head_entries: tuple[_ScanAllowlistEntry, ...],
) -> None:
    """bootstrapまたは通常規則でallow-listの遷移を検査する。"""
    if not base_ledger_present and base_entries is None:
        pending = frozenset(
            entry.key for entry in head_entries if entry.pending_removal
        )
        if pending != BOOTSTRAP_PENDING_REMOVAL_KEYS:
            raise FrozenBaselineCheckError(
                "allow-list bootstrapのpending_removal exact-setが不一致: "
                f"不足={_format_scan_keys(BOOTSTRAP_PENDING_REMOVAL_KEYS - pending)}; "
                f"過剰={_format_scan_keys(pending - BOOTSTRAP_PENDING_REMOVAL_KEYS)}"
            )
        return
    if not base_ledger_present:
        raise FrozenBaselineCheckError(
            "allow-list通常規則: baseに台帳がないのにallow-listがある"
        )
    if base_entries is None:
        raise FrozenBaselineCheckError(
            "allow-list通常規則: baseに台帳があるのにallow-listがない"
        )

    base_by_key = {entry.key: entry for entry in base_entries}
    head_by_key = {entry.key: entry for entry in head_entries}
    additions = frozenset(head_by_key.keys() - base_by_key.keys())
    if additions:
        raise FrozenBaselineCheckError(
            "allow-list通常規則: エントリ追加は禁止: "
            f"{_format_scan_keys(additions)}"
        )
    for key in sorted(base_by_key.keys() & head_by_key.keys()):
        before = base_by_key[key]
        after = head_by_key[key]
        if not before.pending_removal and after.pending_removal:
            raise FrozenBaselineCheckError(
                "allow-list通常規則: pending_removal false→trueは禁止: "
                f"{_format_scan_keys({key})}"
            )
        if before.pending_removal and not after.pending_removal:
            raise FrozenBaselineCheckError(
                "allow-list通常規則: pending_removal true→falseは禁止: "
                f"{_format_scan_keys({key})}"
            )
        if before.reason != after.reason:
            raise FrozenBaselineCheckError(
                "allow-list通常規則: reason変更は禁止: "
                f"{_format_scan_keys({key})}"
            )
    # pending_removalの除去期限は機械保証しない。除去は後続タスクの管理統制が担う。


def check_synthetic_source_scan(
    root: Path,
    head_allowlist_path: Path,
    *,
    base_allowlist_path: Path | None,
    base_ledger_present: bool,
) -> _SourceScan:
    """合成fixtureだけで走査とallow-list遷移規則を検査する。

    Args:
        root: scripts、tests、backend/testsを持つ合成fixtureのルート。
        head_allowlist_path: final head相当の合成allow-list。
        base_allowlist_path: base相当の合成allow-list。初回はNone。
        base_ledger_present: baseに台帳が存在するか。

    Returns:
        出現回数と一意な(path, value)組を持つ走査結果。

    Raises:
        FrozenBaselineCheckError: 走査、schema、遷移のいずれかが不正な場合。
        OSError: 合成allow-listを読み取れない場合。
    """
    resolved_root = root.resolve()
    if resolved_root == REPOSITORY_ROOT.resolve():
        raise FrozenBaselineCheckError(
            "実リポジトリの走査は--invariants-onlyまたは--acceptanceを使う"
        )
    head_entries = _parse_scan_allowlist(
        head_allowlist_path.read_bytes(), str(head_allowlist_path)
    )
    base_entries = (
        None
        if base_allowlist_path is None
        else _parse_scan_allowlist(
            base_allowlist_path.read_bytes(), str(base_allowlist_path)
        )
    )
    scan = _scan_python_sources(resolved_root)
    _check_scan_matches_allowlist(scan, head_entries)
    _check_scan_allowlist_transition(
        base_ledger_present=base_ledger_present,
        base_entries=base_entries,
        head_entries=head_entries,
    )
    return scan


def _load_worktree_scan_allowlist(root: Path) -> tuple[_ScanAllowlistEntry, ...]:
    """作業ツリーのproduction allow-listを読み取る。"""
    path = root / SCAN_ALLOWLIST_PATH
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise FrozenBaselineCheckError(
            f"production allow-listを読めない: {SCAN_ALLOWLIST_PATH.as_posix()}: {exc}"
        ) from exc
    return _parse_scan_allowlist(data, str(path))


def check_repository_source_scan(root: Path) -> _SourceScan:
    """実リポジトリのPython本文走査をproduction allow-listと照合する。

    Args:
        root: scripts、tests、backend/testsを持つリポジトリルート。

    Returns:
        出現回数と一意な(path, value)組を持つ走査結果。

    Raises:
        FrozenBaselineCheckError: 走査またはallow-listが不正な場合。
    """
    entries = _load_worktree_scan_allowlist(root)
    scan = _scan_python_sources(root)
    _check_scan_matches_allowlist(scan, entries)
    return scan


def _check_acceptance_scan_transition(
    root: Path,
    base_sha: str,
    *,
    base_ledger_present: bool,
) -> None:
    """base treeと作業ツリーのproduction allow-list遷移を検査する。"""
    head_entries = _load_worktree_scan_allowlist(root)
    base_allowlist_entry = _git_tree_entry(
        root,
        base_sha,
        SCAN_ALLOWLIST_PATH.as_posix(),
    )
    base_entries = None
    if base_allowlist_entry is not None:
        base_entries = _parse_scan_allowlist(
            _git_file_bytes(root, base_sha, SCAN_ALLOWLIST_PATH.as_posix()),
            f"{base_sha}:{SCAN_ALLOWLIST_PATH.as_posix()}",
        )
    _check_scan_allowlist_transition(
        base_ledger_present=base_ledger_present,
        base_entries=base_entries,
        head_entries=head_entries,
    )


def check_invariants(root: Path, ledger_path: Path) -> None:
    """作業ツリーだけを使って凍結基準台帳の不変条件を検査する。

    Args:
        root: 素材・実装・schemaを解決するリポジトリルート。
        ledger_path: 検査する台帳。テストでは一時複製を指定できる。

    Raises:
        FrozenBaselineCheckError: 台帳が不変条件に違反する場合。
        FrozenBaselineError: 台帳自体を読み取れない場合。
        OSError: 必須ファイルを読み取れない場合。
    """
    ledger = load_frozen_baseline_ledger(ledger_path)
    _check_ledger_structure(root, ledger)
    _check_implementation_bindings(root, ledger)
    current_identities = _derive_current_identities(root, ledger)
    _check_derived_history_values(ledger, current_identities)
    _check_replay(ledger)
    check_repository_source_scan(root)


def _ci_requests_acceptance() -> bool:
    """CIイベント名から受理遷移検査を実行するか決める。

    Raises:
        FrozenBaselineCheckError: イベント名が未設定または未対応の場合。
    """
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name == "pull_request":
        return True
    if event_name in {"push", "workflow_dispatch"}:
        return False
    rendered = "<未設定>" if event_name is None else repr(event_name)
    raise FrozenBaselineCheckError(
        f"GITHUB_EVENT_NAME が未設定または未対応: {rendered}"
    )


def _build_parser() -> argparse.ArgumentParser:
    """イベント別の凍結基準検査を選択するCLI parserを作る。"""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "走査母集団は scripts/、tests/、backend/tests/ 配下の *.py で、"
            "本文中の40桁・64桁小文字hexを対象とします。"
            "非保証: 隣接文字列連結など、ソース上に連続して現れない形で"
            "再構成された定数は走査できません。"
            "--invariants-onlyと--acceptanceと--ciは実リポジトリを走査し、"
            "--scan-fixtureは合成fixture専用です。pending_removalの除去は"
            "後続タスクによる管理統制です。"
        ),
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--invariants-only", action="store_true")
    modes.add_argument("--acceptance", action="store_true")
    modes.add_argument(
        "--ci",
        action="store_true",
        help="GITHUB_EVENT_NAMEに応じて不変量検査か受理遷移検査を実行する",
    )
    modes.add_argument(
        "--scan-fixture",
        type=Path,
        metavar="HEAD_ALLOWLIST",
        help="合成fixture上だけで走査とallow-list遷移を検査する",
    )
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--base-scan-allowlist", type=Path)
    parser.add_argument("--base-ledger-present", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI引数を解釈して不変条件検査の終了コードを返す。"""
    args = _build_parser().parse_args(argv)
    root = args.root.resolve()
    ledger_path = args.ledger if args.ledger is not None else root / LEDGER_PATH
    try:
        if args.scan_fixture is not None:
            scan = check_synthetic_source_scan(
                root,
                args.scan_fixture,
                base_allowlist_path=args.base_scan_allowlist,
                base_ledger_present=args.base_ledger_present,
            )
            messages = (
                "frozen-baselines: synthetic scan fixture OK: "
                f"occurrences={scan.occurrences}; pairs={len(scan.pairs)}",
            )
        else:
            if args.base_scan_allowlist is not None or args.base_ledger_present:
                raise FrozenBaselineCheckError(
                    "scan fixture用引数は--scan-fixtureなしでは使えない"
                )
            acceptance_requested = (
                _ci_requests_acceptance() if args.ci else args.acceptance
            )
            check_invariants(root, ledger_path)
            messages = (
                check_acceptance(root, ledger_path) if acceptance_requested else ()
            )
    except (FrozenBaselineCheckError, FrozenBaselineError, OSError) as exc:
        print(f"frozen-baselines: ERROR: {exc}", file=sys.stderr)
        return 1
    for message in messages:
        print(message)
    print("frozen-baselines: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
