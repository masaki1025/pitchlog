"""宣言モデルを生成コアへ渡す前に5系統の意味検査を行う。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from pitchlog.domaingen import core


class CheckId(StrEnum):
    """ADR-003 D-1 正本の射程行が要求する生成前検査。"""

    TRANSITIONS = "transition-coverage-determinism"
    TYPES_AND_RANGES = "type-and-integer-range"
    DIVISION_ROUNDING = "explicit-division-rounding"
    DISPLAY_PARAMETERS = "display-primitive-parameters"
    DISPLAY_ATOM_BOUNDARY = "numeric-value-display-atom-boundary"


CHECK_IDS = frozenset(CheckId)


@dataclass(frozen=True, slots=True)
class CheckViolation:
    """一つの生成前検査違反。

    Attributes:
        check_id: 違反を検出した検査系統。
        path: 宣言モデル内の位置。
        message: 違反内容。
    """

    check_id: CheckId
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class PregenReport:
    """実行した検査集合と検出結果。

    Attributes:
        attempted: 実際に起動した検査 ID 集合。
        violations: 個別に帰属可能な違反列。
    """

    attempted: frozenset[CheckId]
    violations: tuple[CheckViolation, ...]

    @property
    def passed(self) -> bool:
        """違反が0件なら真を返す。"""
        return not self.violations


class PregenCheckError(Exception):
    """生成前検査が不正な宣言を拒否したことを表す。"""

    def __init__(self, report: PregenReport) -> None:
        """検査報告を保持して例外を初期化する。"""
        self.report = report
        details = "; ".join(
            f"{item.check_id.value}@{item.path}: {item.message}"
            for item in report.violations
        )
        super().__init__(details)


CheckFunction = Callable[
    [Mapping[str, object], core.SourceSchemas],
    list[CheckViolation],
]


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise PregenCheckError(
            PregenReport(
                frozenset(),
                (
                    CheckViolation(
                        CheckId.TYPES_AND_RANGES,
                        label,
                        "object でない",
                    ),
                ),
            )
        )
    return cast(dict[str, object], value)


def _array(value: object) -> list[object]:
    """配列ならその値、それ以外なら空配列を返す。"""
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def _string(value: object) -> str | None:
    """空でない文字列だけを返す。"""
    if isinstance(value, str) and value:
        return value
    return None


def _calculations(
    model: Mapping[str, object],
) -> Iterable[tuple[int, dict[str, object]]]:
    """計算宣言を index と組にして列挙する。"""
    for index, value in enumerate(_array(model.get("calculations"))):
        if isinstance(value, dict) and all(isinstance(key, str) for key in value):
            yield index, cast(dict[str, object], value)


def _violation(
    check_id: CheckId,
    path: str,
    message: str,
) -> CheckViolation:
    """検査違反を簡潔に構築する。"""
    return CheckViolation(check_id, path, message)


def _check_transitions(
    model: Mapping[str, object],
    schemas: core.SourceSchemas,
) -> list[CheckViolation]:
    """全イベントに一意な遷移があることを検査する。"""
    del schemas
    violations: list[CheckViolation] = []
    for index, calculation in _calculations(model):
        path = f"$.calculations[{index}]"
        event_ids = {
            event_id
            for raw_event in _array(calculation.get("events"))
            if isinstance(raw_event, dict)
            if (event_id := _string(raw_event.get("eventId"))) is not None
        }
        transitions_by_event: dict[str, list[dict[str, object]]] = defaultdict(list)
        for raw_rule in _array(calculation.get("rules")):
            if not isinstance(raw_rule, dict) or raw_rule.get("kind") != "transition":
                continue
            event_ref = _string(raw_rule.get("eventRef"))
            if event_ref is None:
                continue
            transitions_by_event[event_ref].append(
                cast(dict[str, object], raw_rule)
            )
        for event_id in sorted(event_ids):
            count = len(transitions_by_event[event_id])
            if count == 0:
                violations.append(
                    _violation(
                        CheckId.TRANSITIONS,
                        f"{path}.events[{event_id}]",
                        "対応する遷移がなく網羅されていない",
                    )
                )
            elif count > 1:
                violations.append(
                    _violation(
                        CheckId.TRANSITIONS,
                        f"{path}.events[{event_id}]",
                        "複数の遷移が成立し決定的でない",
                    )
                )
        for event_ref in sorted(set(transitions_by_event) - event_ids):
            violations.append(
                _violation(
                    CheckId.TRANSITIONS,
                    f"{path}.rules",
                    f"未知イベントへの遷移: {event_ref}",
                )
            )
    return violations


def _integer_numeric_value(value: object) -> int | None:
    """構造化整数なら値を返す。"""
    if not isinstance(value, dict) or value.get("kind") != "integer":
        return None
    integer = value.get("value")
    if isinstance(integer, int) and not isinstance(integer, bool):
        return integer
    return None


def _field_kind(field: Mapping[str, object]) -> str | None:
    """フィールド宣言の型 kind を返す。"""
    field_type = field.get("type")
    if not isinstance(field_type, dict):
        return None
    return _string(field_type.get("kind"))


def _fields(
    calculation: Mapping[str, object],
) -> Iterable[tuple[str, dict[str, object]]]:
    """計算内の全フィールド宣言を JSON path と組にして列挙する。"""
    for collection in ("inputs", "outputs"):
        for index, raw_field in enumerate(_array(calculation.get(collection))):
            if isinstance(raw_field, dict):
                yield f"{collection}[{index}]", cast(dict[str, object], raw_field)
    for collection in ("states", "events"):
        for owner_index, raw_owner in enumerate(_array(calculation.get(collection))):
            if not isinstance(raw_owner, dict):
                continue
            for field_index, raw_field in enumerate(_array(raw_owner.get("fields"))):
                if isinstance(raw_field, dict):
                    yield (
                        f"{collection}[{owner_index}].fields[{field_index}]",
                        cast(dict[str, object], raw_field),
                    )


def _reference_types(
    calculation: Mapping[str, object],
) -> dict[str, dict[str, str]]:
    """参照種別ごとの field ID と型 kind の対応を返す。"""
    scopes: dict[str, dict[str, str]] = {
        "input-ref": {},
        "state-ref": {},
        "event-ref": {},
        "output-ref": {},
    }
    for collection, reference_kind in (
        ("inputs", "input-ref"),
        ("outputs", "output-ref"),
    ):
        for raw_field in _array(calculation.get(collection)):
            if not isinstance(raw_field, dict):
                continue
            field_id = _string(raw_field.get("fieldId"))
            kind = _field_kind(raw_field)
            if field_id is not None and kind is not None:
                scopes[reference_kind][field_id] = kind
    for collection, reference_kind in (
        ("states", "state-ref"),
        ("events", "event-ref"),
    ):
        for raw_owner in _array(calculation.get(collection)):
            if not isinstance(raw_owner, dict):
                continue
            for raw_field in _array(raw_owner.get("fields")):
                if not isinstance(raw_field, dict):
                    continue
                field_id = _string(raw_field.get("fieldId"))
                kind = _field_kind(raw_field)
                if field_id is not None and kind is not None:
                    scopes[reference_kind][field_id] = kind
    return scopes


def _expression_kind(
    expression: object,
    references: Mapping[str, Mapping[str, str]],
) -> str | None:
    """式の宣言型を副作用なしで推論する。"""
    if not isinstance(expression, dict):
        return None
    kind = expression.get("kind")
    if kind == "numeric-literal":
        value = expression.get("value")
        return "integer" if _integer_numeric_value(value) is not None else "numeric"
    if kind == "boolean-literal" or kind == "comparison":
        return "boolean"
    if kind == "enum-literal":
        return "enum"
    if kind in {"arithmetic", "extremum", "round"}:
        operands = expression.get("operands")
        if kind == "round":
            operands = [expression.get("value")]
        inferred = [
            _expression_kind(operand, references) for operand in _array(operands)
        ]
        if kind == "arithmetic" and expression.get("operator") == "divide":
            return "numeric-value"
        if kind == "round" and expression.get("scale") != 0:
            return "numeric-value"
        return (
            "integer"
            if inferred and set(inferred) == {"integer"}
            else "numeric-value"
        )
    if isinstance(kind, str) and kind.endswith("-ref"):
        field_ref = _string(expression.get("fieldRef"))
        if kind in {"accumulator-ref", "item-ref"}:
            return "numeric"
        if field_ref is not None:
            return references.get(kind, {}).get(field_ref)
    return None


def _check_types_and_ranges(
    model: Mapping[str, object],
    schemas: core.SourceSchemas,
) -> list[CheckViolation]:
    """フィールド型・整数範囲・遷移代入型を検査する。"""
    del schemas
    violations: list[CheckViolation] = []
    for calculation_index, calculation in _calculations(model):
        root = f"$.calculations[{calculation_index}]"
        state_fields: dict[str, dict[str, object]] = {}
        for path, field in _fields(calculation):
            kind = _field_kind(field)
            field_path = f"{root}.{path}"
            if kind == "integer" and field.get("range") is not None:
                value_range = field.get("range")
                if not isinstance(value_range, dict):
                    violations.append(
                        _violation(
                            CheckId.TYPES_AND_RANGES,
                            f"{field_path}.range",
                            "整数範囲が object でない",
                        )
                    )
                else:
                    minimum = _integer_numeric_value(value_range.get("minimum"))
                    maximum = _integer_numeric_value(value_range.get("maximum"))
                    if minimum is None or maximum is None or minimum > maximum:
                        violations.append(
                            _violation(
                                CheckId.TYPES_AND_RANGES,
                                f"{field_path}.range",
                                "整数の最小値・最大値が不正",
                            )
                        )
            if path.startswith("states["):
                field_id = _string(field.get("fieldId"))
                if field_id is not None:
                    state_fields[field_id] = field

        references = _reference_types(calculation)
        for rule_index, raw_rule in enumerate(_array(calculation.get("rules"))):
            if not isinstance(raw_rule, dict) or raw_rule.get("kind") != "transition":
                continue
            for assignment_index, raw_assignment in enumerate(
                _array(raw_rule.get("nextState"))
            ):
                if not isinstance(raw_assignment, dict):
                    continue
                field_ref = _string(raw_assignment.get("fieldRef"))
                assignment_path = (
                    f"{root}.rules[{rule_index}].nextState[{assignment_index}]"
                )
                target = state_fields.get(field_ref or "")
                if target is None:
                    violations.append(
                        _violation(
                            CheckId.TYPES_AND_RANGES,
                            f"{assignment_path}.fieldRef",
                            "未知の状態フィールド",
                        )
                    )
                    continue
                expected = _field_kind(target)
                observed = _expression_kind(raw_assignment.get("value"), references)
                compatible = expected == observed or (
                    expected == "numeric-value" and observed == "integer"
                )
                if not compatible:
                    violations.append(
                        _violation(
                            CheckId.TYPES_AND_RANGES,
                            f"{assignment_path}.value",
                            f"代入型が不一致: expected={expected}, actual={observed}",
                        )
                    )
    return violations


def _walk_expressions(
    value: object,
    path: str,
    under_round: bool = False,
) -> Iterable[tuple[dict[str, object], str, bool]]:
    """式木の各 object を丸め内外の情報とともに列挙する。"""
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_expressions(child, f"{path}[{index}]", under_round)
        return
    if not isinstance(value, dict):
        return
    mapping = cast(dict[str, object], value)
    kind = mapping.get("kind")
    current_under_round = under_round or kind == "round"
    if isinstance(kind, str):
        yield mapping, path, under_round
    for key, child in mapping.items():
        if key == "kind":
            continue
        yield from _walk_expressions(
            child,
            f"{path}.{key}",
            current_under_round,
        )


def _check_division_rounding(
    model: Mapping[str, object],
    schemas: core.SourceSchemas,
) -> list[CheckViolation]:
    """除算が明示的な丸め式の内側にあることを検査する。"""
    del schemas
    violations: list[CheckViolation] = []
    for calculation_index, calculation in _calculations(model):
        for rule_index, rule in enumerate(_array(calculation.get("rules"))):
            path = f"$.calculations[{calculation_index}].rules[{rule_index}]"
            for expression, expression_path, under_round in _walk_expressions(
                rule,
                path,
            ):
                if (
                    expression.get("kind") == "arithmetic"
                    and expression.get("operator") == "divide"
                    and not under_round
                ):
                    violations.append(
                        _violation(
                            CheckId.DIVISION_ROUNDING,
                            expression_path,
                            "除算が明示的な round 式に包まれていない",
                        )
                    )
    return violations


def _resolve_local_ref(schema: Mapping[str, object], ref: str) -> dict[str, object]:
    """語彙 schema 内のローカル参照を解決する。"""
    if not ref.startswith("#/"):
        raise ValueError(f"ローカル参照でない: {ref}")
    node: object = schema
    for token in ref[2:].split("/"):
        node = _object(node, ref)[token]
    return _object(node, ref)


def _numeric_primitive_parameters(
    vocabulary: Mapping[str, object],
) -> dict[str, frozenset[str]]:
    """数値 primitive の kind と必須引数を語彙 schema から導出する。"""
    definitions = _object(vocabulary.get("$defs"), "vocabulary.$defs")
    numeric = _object(definitions.get("NumericPrimitive"), "NumericPrimitive")
    parameters: dict[str, frozenset[str]] = {}
    for raw_branch in _array(numeric.get("oneOf")):
        branch = _object(raw_branch, "NumericPrimitive.oneOf[]")
        ref = _string(branch.get("$ref"))
        if ref is None:
            continue
        resolved = _resolve_local_ref(vocabulary, ref)
        properties = _object(resolved.get("properties"), f"{ref}.properties")
        kind_schema = _object(properties.get("kind"), f"{ref}.kind")
        kind = _string(kind_schema.get("const"))
        required = _array(resolved.get("required"))
        if kind is None or not all(isinstance(item, str) for item in required):
            raise ValueError(f"数値 primitive schema が不正: {ref}")
        parameters[kind] = frozenset(cast(list[str], required))
    return parameters


def _check_display_parameters(
    model: Mapping[str, object],
    schemas: core.SourceSchemas,
) -> list[CheckViolation]:
    """各数値表示 primitive が schema 由来の全引数を持つか検査する。"""
    parameters = _numeric_primitive_parameters(schemas.vocabulary)
    violations: list[CheckViolation] = []
    for index, raw_rule in enumerate(_array(model.get("displayRules"))):
        if (
            not isinstance(raw_rule, dict)
            or raw_rule.get("kind") != "numeric-primitive"
        ):
            continue
        primitive = raw_rule.get("primitive")
        path = f"$.displayRules[{index}].primitive"
        if not isinstance(primitive, dict):
            violations.append(
                _violation(
                    CheckId.DISPLAY_PARAMETERS,
                    path,
                    "primitive 宣言が object でない",
                )
            )
            continue
        kind = _string(primitive.get("kind"))
        expected = parameters.get(kind or "")
        if expected is None:
            violations.append(
                _violation(
                    CheckId.DISPLAY_PARAMETERS,
                    path,
                    f"未知の数値 primitive: {kind}",
                )
            )
            continue
        missing = expected - set(primitive)
        if missing:
            violations.append(
                _violation(
                    CheckId.DISPLAY_PARAMETERS,
                    path,
                    f"必須引数が不足: {sorted(missing)!r}",
                )
            )
    return violations


def _numeric_value_kinds(vocabulary: Mapping[str, object]) -> frozenset[str]:
    """NumericValue の object 形の kind を語彙 schema から導出する。"""
    definitions = _object(vocabulary.get("$defs"), "vocabulary.$defs")
    numeric = _object(definitions.get("NumericValue"), "NumericValue")
    kinds: set[str] = set()
    for raw_branch in _array(numeric.get("oneOf")):
        if not isinstance(raw_branch, dict):
            continue
        ref = _string(raw_branch.get("$ref"))
        if ref is None:
            continue
        resolved = _resolve_local_ref(vocabulary, ref)
        properties = _object(resolved.get("properties"), f"{ref}.properties")
        kind_schema = _object(properties.get("kind"), f"{ref}.kind")
        kind = _string(kind_schema.get("const"))
        if kind is not None:
            kinds.add(kind)
    return frozenset(kinds)


def _check_display_atom_boundary(
    model: Mapping[str, object],
    schemas: core.SourceSchemas,
) -> list[CheckViolation]:
    """Template の差し込みが DisplayAtom を経由することを検査する。"""
    numeric_kinds = _numeric_value_kinds(schemas.vocabulary)
    violations: list[CheckViolation] = []
    for rule_index, raw_rule in enumerate(_array(model.get("displayRules"))):
        if not isinstance(raw_rule, dict) or raw_rule.get("kind") != "template":
            continue
        placeholders = raw_rule.get("placeholders")
        if not isinstance(placeholders, dict):
            continue
        for name, value in placeholders.items():
            direct_numeric = value is None or (
                isinstance(value, dict) and value.get("kind") in numeric_kinds
            )
            if direct_numeric:
                violations.append(
                    _violation(
                        CheckId.DISPLAY_ATOM_BOUNDARY,
                        f"$.displayRules[{rule_index}].placeholders.{name}",
                        "NumericValue が DisplayAtom を経由せず差し込まれている",
                    )
                )
    return violations


_CHECKS: dict[CheckId, CheckFunction] = {
    CheckId.TRANSITIONS: _check_transitions,
    CheckId.TYPES_AND_RANGES: _check_types_and_ranges,
    CheckId.DIVISION_ROUNDING: _check_division_rounding,
    CheckId.DISPLAY_PARAMETERS: _check_display_parameters,
    CheckId.DISPLAY_ATOM_BOUNDARY: _check_display_atom_boundary,
}


def run_pregen_checks(
    model: Mapping[str, object],
    schemas: core.SourceSchemas,
) -> PregenReport:
    """登録された生成前検査を独立に実行する。

    Args:
        model: 生成コアへ渡す前の宣言モデル。
        schemas: 語彙と宣言フィールドの正である既存 schema 群。
    Returns:
        実行した母集合と個別違反を持つ報告。
    """
    attempted = frozenset(_CHECKS)
    violations: list[CheckViolation] = []
    for check_id in sorted(attempted, key=lambda item: item.value):
        violations.extend(_CHECKS[check_id](model, schemas))
    return PregenReport(attempted, tuple(violations))


def generate_checked(
    model: Mapping[str, object],
    manifest: Mapping[str, object],
    schemas: core.SourceSchemas,
    root: Path,
) -> dict[str, object]:
    """5系統を通過した宣言だけをステップ 26 の生成コアへ渡す。

    Args:
        model: 検査対象の宣言モデル。
        manifest: ステップ 7 のマニフェスト。
        schemas: 既存の宣言モデル・マニフェスト・語彙 schema。
        root: 生成元条項を照合するリポジトリルート。
    Returns:
        ステップ 26 が生成した中間表現。

    Raises:
        PregenCheckError: 有効な検査が違反を1件以上検出した場合。
        core.GenerationError: 検査後の schema 検証または生成に失敗した場合。
    """
    report = run_pregen_checks(model, schemas)
    if not report.passed:
        raise PregenCheckError(report)
    return core.generate_intermediate_representation(
        model,
        manifest,
        schemas,
        root,
    )


__all__ = [
    "CHECK_IDS",
    "CheckId",
    "CheckViolation",
    "PregenCheckError",
    "PregenReport",
    "generate_checked",
    "run_pregen_checks",
]
