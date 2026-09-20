"""凍結基準台帳の作業ツリー不変条件を検査する。"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Final

from frozen_baselines import (
    COMPARISON_STRATEGIES,
    FrozenBaselineError,
    IdentityValue,
    collect_materials,
    load_frozen_baseline_ledger,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = Path("contracts/authz/frozen-baselines.json")
SCHEMA_PATH = Path("contracts/authz/frozen-baselines.schema.json")

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


class FrozenBaselineCheckError(ValueError):
    """凍結基準台帳の不変条件違反を表す。"""


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
            for change_index, raw_change in enumerate(raw_changes):
                if not isinstance(raw_change, dict):
                    continue
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
) -> dict[str, frozenset[IdentityValue]]:
    """宣言から素材を収集しregistry戦略で現在の識別値を導出する。"""
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
        strategy = COMPARISON_STRATEGIES.get(strategy_key)
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

    unused = set(COMPARISON_STRATEGIES) - used_strategy_keys
    if unused:
        formatted = sorted(f"{identity}/{granularity}" for identity, granularity in unused)
        raise FrozenBaselineCheckError(f"どの宣言からも参照されない戦略がある: {formatted!r}")
    return derived


def _extract_python_string_assignment(root: Path, locator: dict[str, Any]) -> str:
    """python_assignment locatorのトップレベル文字列定数をASTから抽出する。"""
    path_text = str(locator["path"])
    path = _safe_asset_path(root, path_text)
    symbol = str(locator["symbol"])
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
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


def _expected_ledger_placement(series: str) -> list[dict[str, str]]:
    """現在台帳内の系列を指す導出済みlocatorを返す。"""
    return [{"kind": "ledger_series", "path": LEDGER_PATH.as_posix(), "series": series}]


def _check_derived_history_values(
    root: Path,
    ledger: dict[str, Any],
    current_identities: dict[str, frozenset[IdentityValue]],
) -> None:
    """履歴の申告値をソース・素材・locatorからの導出値と照合する。"""
    latest = _latest_history_by_series(ledger)
    declarations = _expect_object(ledger["declarations"], "declarations")
    if set(latest) != set(declarations):
        raise FrozenBaselineCheckError(
            "history末尾の系列がdeclarationsとexact-set不一致: "
            f"不足={sorted(set(declarations) - set(latest))!r}; "
            f"過剰={sorted(set(latest) - set(declarations))!r}"
        )
    for series, record in latest.items():
        placement_change = _expect_object(
            record["placement_change"], f"history.{series}.placement_change"
        )
        before = placement_change["before"]
        legacy_locator = _expect_object(
            _expect_list(before, f"history.{series}.placement_change.before")[0],
            f"history.{series}.placement_change.before[0]",
        )
        prior_value = _extract_python_string_assignment(root, legacy_locator)
        expected_before = LEGACY_PLACEMENTS.get(series)
        if before != expected_before:
            raise FrozenBaselineCheckError(
                f"history.{series}.placement_change.before が導出値と不一致"
            )
        after = placement_change["after"]
        expected_after = _expected_ledger_placement(series)
        if after != expected_after:
            raise FrozenBaselineCheckError(
                f"history.{series}.placement_change.after が導出値と不一致"
            )
        placements = _expect_object(ledger["placements"], "placements")
        if placements.get(series) != expected_after:
            raise FrozenBaselineCheckError(f"placements.{series} が台帳系列locatorと不一致")

        expected_prior = frozenset(
            {IdentityValue(kind="literal_commit_string", value=prior_value)}
        )
        prior_state = _expect_object(record["prior_identity"], f"history.{series}.prior_identity")
        actual_prior = _identity_values(
            prior_state["values"], f"history.{series}.prior_identity.values"
        )
        if prior_state["present"] is not True or actual_prior != expected_prior:
            raise FrozenBaselineCheckError(
                f"history.{series}.prior_identity が移設元ソースの導出値と不一致"
            )

        new_state = _expect_object(record["new_identity"], f"history.{series}.new_identity")
        actual_new = _identity_values(
            new_state["values"], f"history.{series}.new_identity.values"
        )
        if new_state["present"] is not True or actual_new != current_identities[series]:
            raise FrozenBaselineCheckError(
                f"history.{series}.new_identity が戦略の導出値と不一致"
            )
        derived_moved = before != after
        if record["moved"] is not derived_moved:
            raise FrozenBaselineCheckError(f"history.{series}.moved がlocator導出値と不一致")


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
    _check_exact_keys(ledger, TOP_LEVEL_KEYS, "トップレベル")
    _precheck_history(ledger)
    schema = _load_schema(root / SCHEMA_PATH)
    _validate_schema(ledger, schema, schema, "$")
    _check_movement_rules(ledger)
    _check_implementation_bindings(root, ledger)
    current_identities = _derive_current_identities(root, ledger)
    _check_derived_history_values(root, ledger, current_identities)
    _check_replay(ledger)


def _build_parser() -> argparse.ArgumentParser:
    """git非依存の不変条件検査だけを受け付けるCLI parserを作る。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invariants-only", action="store_true")
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--ledger", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI引数を解釈して不変条件検査の終了コードを返す。"""
    args = _build_parser().parse_args(argv)
    if not args.invariants_only:
        print(
            "frozen-baselines: ERROR: 本ステップでは --invariants-only だけを実装している",
            file=sys.stderr,
        )
        return 2
    root = args.root.resolve()
    ledger_path = args.ledger if args.ledger is not None else root / LEDGER_PATH
    try:
        check_invariants(root, ledger_path)
    except (FrozenBaselineCheckError, FrozenBaselineError, OSError) as exc:
        print(f"frozen-baselines: ERROR: {exc}", file=sys.stderr)
        return 1
    print("frozen-baselines: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
