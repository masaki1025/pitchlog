"""宣言モデルを生成コアへ渡す前に5系統の意味検査を行う。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

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
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
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
            transitions_by_event[event_ref].append(cast(dict[str, object], raw_rule))
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
            "integer" if inferred and set(inferred) == {"integer"} else "numeric-value"
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
        typed = calculation.get("typedProgram")
        if isinstance(typed, dict):
            try:
                if typed.get("kind") == "primitive-refs":
                    if set(typed) != {
                        "kind",
                        "version",
                        "commonCalculationId",
                        "commonModelHash",
                        "refs",
                    }:
                        raise ValueError("参照modelの閉キーが不正")
                else:
                    validate_typed_program(typed)
            except ValueError as error:
                violations.append(
                    _violation(CheckId.TYPES_AND_RANGES, root, str(error))
                )
            continue

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
        check: CheckFunction = _CHECKS[check_id]
        violations.extend(check(model, schemas))
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


def validate_typed_program(program: Mapping[str, Any]) -> None:
    """型付きprimitiveの閉演算・参照・有限collectionを生成前に検査する。

    Args:
        program: D-1の追加typed-program宣言。

    Raises:
        ValueError: 型・未知参照・非有限reducer・演算が不正な場合。
    """
    import re

    version = program.get("version")
    required = {
        "numericEnvelope",
        "paProjection",
        "closedRecords",
        "metrics",
        "reducer",
        "version",
        "collections",
        "sql",
        "selection",
        "fields",
        "kind",
    }
    if version == 1:
        required |= {"pendingDecisions"}
    elif version in (2, 3):
        required |= {"decisions", "namedScopes", "derivedMetrics"}
    if version == 3:
        required.add("sourceProjections")
    if (
        type(version) is not int
        or version not in (1, 2, 3)
        or set(program) != required
        or program.get("kind") != "event-facts"
    ):
        raise ValueError("typed-programの閉キーまたは版が不正")
    validate_primitive_sql_binding(program["sql"])
    envelope = program["numericEnvelope"]
    if (
        envelope != {"minimum": 0, "maximum": None}
        or type(envelope["minimum"]) is not int
    ):
        raise ValueError("任意精度非負整数の宣言が必要")
    if version == 1:
        pending = program["pendingDecisions"]
        if not isinstance(pending, dict) or not 1 <= len(pending) <= 16:
            raise ValueError("未回答状態の閉宣言が必要")
        for name, state in pending.items():
            if (
                not isinstance(name, str)
                or not isinstance(state, dict)
                or set(state) != {"state", "decision_id", "value"}
            ):
                raise ValueError("未回答状態の型が不正")
            if (
                state["state"] != "decision_pending"
                or state["value"] is not None
                or type(state["decision_id"]) is not str
                or re.fullmatch(r"D[0-9]{2}", state["decision_id"]) is None
            ):
                raise ValueError("未回答を確定値へ置換できない")
    fields = program["fields"]
    collections = program["collections"]
    metrics = program["metrics"]
    if not isinstance(fields, dict) or not isinstance(collections, dict):
        raise ValueError("型付きfield/collectionが必要")
    if not isinstance(metrics, list) or not 1 <= len(metrics) <= 64:
        raise ValueError("primitive件数が不正")
    kinds = {"integer", "boolean", "string"}
    for path, field in fields.items():
        if not isinstance(path, str) or not re.fullmatch(r"[\w.-]+", path):
            raise ValueError("field pathが不正")
        if (
            not isinstance(field, dict)
            or not {"type", "nullable"} <= set(field)
            or set(field) - {"type", "nullable", "minimum", "maximum", "enum"}
        ):
            raise ValueError("field宣言が不正")
        if field["type"] not in kinds or type(field["nullable"]) is not bool:
            raise ValueError("field型が不正")
        for bound in ("minimum", "maximum"):
            if bound in field and (
                field["type"] != "integer"
                or type(field[bound]) is not int
                or field[bound] < 0
            ):
                raise ValueError("整数範囲の宣言が不正")
        if field.get("minimum", 0) > field.get("maximum", 2**256):
            raise ValueError("整数範囲が逆転")
        if "enum" in field:
            values = field["enum"]
            if (
                field["type"] != "string"
                or not isinstance(values, list)
                or not 1 <= len(values) <= 32
                or any(type(v) is not str for v in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError("閉enumの宣言が不正")

    for name, collection in collections.items():
        if not isinstance(name, str) or not isinstance(collection, dict):
            raise ValueError("collectionが不正")
        if set(collection) != {"maximumItems", "fields"}:
            raise ValueError("collectionの閉キーが不正")
        maximum = collection["maximumItems"]
        if type(maximum) is not int or not 1 <= maximum <= 4:
            raise ValueError("遷移内reducerの上限が不正")
        if not isinstance(collection["fields"], dict):
            raise ValueError("item型が不正")
        for descriptor in collection["fields"].values():
            if (
                not isinstance(descriptor, dict)
                or set(descriptor) != {"type", "nullable"}
                or descriptor["type"] not in kinds
                or type(descriptor["nullable"]) is not bool
            ):
                raise ValueError("item型が不正")
    records = program["closedRecords"]
    if (
        not isinstance(records, list)
        or len(records) > 16
        or any(type(v) is not str for v in records)
    ):
        raise ValueError("閉record pathが不正")
    for record in records:
        children = [
            path[len(record) + 1 :] for path in fields if path.startswith(record + ".")
        ]
        if not children or any("." in child for child in children):
            raise ValueError("閉recordのfield対応が不正")
    identifiers: set[str] = set()

    def infer(node: object, items: Mapping[str, Any]) -> str:
        if not isinstance(node, dict) or "op" not in node:
            raise ValueError("式の閉演算が必要")
        op = node["op"]
        if op == "literal" and set(node) == {"op", "value"}:
            value = node["value"]
            if value is None:
                return "null"
            if type(value) is bool:
                return "boolean"
            if type(value) is int and value >= 0:
                return "integer"
            if type(value) is str:
                return "string"
        if op == "ref" and set(node) == {"op", "path"}:
            path = node["path"]
            owner = (
                items if isinstance(path, str) and path.startswith("item.") else fields
            )
            key = path.removeprefix("item.") if owner is items else path
            if key not in owner:
                raise ValueError("未知の型付き参照")
            return owner[key]["type"]
        if op in {"and", "or", "add"} and set(node) == {"op", "args"}:
            args = node["args"]
            if not isinstance(args, list) or not 1 <= len(args) <= 32:
                raise ValueError("有限の演算引数が必要")
            expected = "integer" if op == "add" else "boolean"
            if any(infer(arg, items) != expected for arg in args):
                raise ValueError("演算引数の型違い")
            return expected
        if op in {"eq", "ne"} and set(node) == {"op", "left", "right"}:
            left, right = infer(node["left"], items), infer(node["right"], items)
            if left != right and "null" not in {left, right}:
                raise ValueError("比較対象の型違い")
            return "boolean"
        if op == "lookup" and set(node) == {"op", "value", "cases"}:
            if infer(node["value"], items) != "string":
                raise ValueError("enum lookup入力は文字列が必要")
            cases = node["cases"]
            if not isinstance(cases, dict) or not 1 <= len(cases) <= 32:
                raise ValueError("有限のenum lookupが必要")
            if any(type(v) is not int for v in cases.values()):
                raise ValueError("lookup出力は整数が必要")
            value_ref = node["value"]
            if value_ref.get("op") == "ref":
                descriptor = fields.get(value_ref.get("path"), {})
                if "enum" in descriptor and set(cases) != set(descriptor["enum"]):
                    raise ValueError("enum lookupが閉じた外延と一致しない")

            return "integer"
        raise ValueError("未知または余剰演算")

    if infer(program["selection"], {}) != "boolean":
        raise ValueError("選択条件はbooleanが必要")
    for metric in metrics:
        metric_keys = {
            "id",
            "relation",
            "guard",
            "available",
            "quantity",
            "credit",
        }
        if (
            version == 3
            and isinstance(metric, dict)
            and metric.get("id") == "batters_faced"
        ):
            if (
                set(metric) != {"id", "relation", "quantity", "projection"}
                or metric["projection"] != "batters_faced"
                or metric["relation"] != "source_projection"
                or "batters_faced" in identifiers
                or infer(metric["quantity"], {}) != "integer"
            ):
                raise ValueError("source projection metricの閉型違い")
            identifiers.add("batters_faced")
            continue
        if not isinstance(metric, dict) or set(metric) != metric_keys:
            raise ValueError("primitiveの閉キーが不正")
        name = metric["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError("primitive IDが不正")
        if name in identifiers:
            raise ValueError("primitive IDが重複")
        identifiers.add(name)
        relation = metric["relation"]
        if relation not in {"event", "completed_pa", *collections}:
            raise ValueError("未知のreducer source")
        items = collections[relation]["fields"] if relation in collections else {}
        if infer(metric["guard"], items) != "boolean":
            raise ValueError("guardはbooleanが必要")
        if infer(metric["available"], {}) != "boolean":
            raise ValueError("availabilityはbooleanが必要")
        if infer(metric["quantity"], items) != "integer":
            raise ValueError("寄与数量は整数が必要")
        if infer(metric["credit"], items) != "string":
            raise ValueError("帰属はID文字列が必要")
    if type(program["reducer"].get("initial")) is not int or program["reducer"] != {
        "id": "integer_add",
        "type": "integer",
        "initial": 0,
        "operator": "add",
    }:
        raise ValueError("共通reducerは整数addだけ")
    if version == 3:
        validate_source_projections(program)
    validate_derived_program(program)
    projection = program["paProjection"]
    if not isinstance(projection, dict) or set(projection) != {
        "guard",
        "fields",
        "metricFields",
    }:
        raise ValueError("PA投影が不正")
    if infer(projection["guard"], {}) != "boolean":
        raise ValueError("PA guardはbooleanが必要")
    if not isinstance(projection["fields"], dict) or not isinstance(
        projection["metricFields"], dict
    ):
        raise ValueError("PA field/refの閉型が不正")
    for expr in projection["fields"].values():
        infer(expr, {})
    if any(metric not in identifiers for metric in projection["metricFields"].values()):
        raise ValueError("未知のPA共通metric参照")


def validate_primitive_sql_binding(binding):
    """共通Sの固定role/版とSQL識別子を全targetの生成前に閉検査する。"""
    import re

    roles = {
        "facts",
        "versions",
        "sources",
        "games",
        "events",
        "plays",
        "slots",
        "generations",
        "ledger",
    }
    if type(binding) is not dict or set(binding) != roles | {
        "amountColumn",
        "metricColumn",
        "canonicalSelection",
    }:
        raise ValueError("SQL bindingの閉キー違反")
    selector = binding["canonicalSelection"]
    if (
        type(selector) is not dict
        or set(selector) != {"version", "kind"}
        or type(selector["version"]) is not int
        or selector != {"version": 1, "kind": "accepted-play-slot-v1"}
    ):
        raise ValueError("未登録canonical S選択です")
    for role in roles:
        schema = "sync_fence" if role in {"facts", "versions", "sources"} else "public"
        if (
            type(binding[role]) is not str
            or re.fullmatch(schema + r"\.[a-z][a-z0-9_]*", binding[role]) is None
        ):
            raise ValueError("SQL relation bindingが不正です")
    for role in ("amountColumn", "metricColumn"):
        if (
            type(binding[role]) is not str
            or re.fullmatch(r"[a-z][a-z0-9_]*", binding[role]) is None
        ):
            raise ValueError("SQL column bindingが不正です")


def validate_derived_program(program: Mapping[str, Any]) -> None:
    """v2の有限selector/ratio式/表示と採用状態を生成前に閉照合する。"""
    import re

    if program["version"] not in (2, 3):
        return
    groups = {
        "official": ["game_official", "game_semi_official"],
        "practice": ["game_open", "game_intrasquad", "game_other"],
        "all": [
            "game_official",
            "game_semi_official",
            "game_open",
            "game_intrasquad",
            "game_other",
        ],
    }
    if program["namedScopes"] != {"default": "all", "groups": groups}:
        raise ValueError("採用済みnamed scopeの閉集合が不一致")
    expected: dict[str, dict[str, object]] = {}
    for key in ("D02", "D03", "D04", "D05"):
        expected[key] = {
            "decision_id": key,
            "decision_state": "adopted",
            "choice": "A",
            "implementation_state": "pending"
            if key == "D03" or (key == "D04" and program["version"] == 2)
            else "available",
        }
        if key == "D03" or (key == "D04" and program["version"] == 2):
            expected[key].update({"source_state": "not_evaluated", "value": None})
    if program["decisions"] != expected:
        raise ValueError("採用状態と実装/source待ちの区別が不一致")
    names = {m["id"] for m in program["metrics"]}

    def identifier(value):
        return (
            type(value) is str and re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None
        )

    def infer(node, components):
        if type(node) is not dict:
            raise ValueError("比の閉式が必要")
        op = node.get("op")
        if op == "metric" and set(node) == {"op", "id"} and node["id"] in names:
            return "integer"
        if op == "component" and set(node) == {"op", "id"} and node["id"] in components:
            return "ratio"
        if (
            op == "literal"
            and set(node) == {"op", "value"}
            and type(node["value"]) is int
            and node["value"] >= 0
        ):
            return "integer"
        if op in ("add", "ratio-add") and set(node) == {"op", "args"}:
            args = node["args"]
            kind = "integer" if op == "add" else "ratio"
            if (
                type(args) is list
                and 1 <= len(args) <= 32
                and all(infer(x, components) == kind for x in args)
            ):
                return kind
        if op == "ratio" and set(node) == {"op", "numerator", "denominator"}:
            if (
                infer(node["numerator"], components)
                == infer(node["denominator"], components)
                == "integer"
            ):
                return "ratio"
        raise ValueError("未知/循環/型違いの比演算")

    derived = program["derivedMetrics"]
    if type(derived) is not list or not 1 <= len(derived) <= 16:
        raise ValueError("派生指標の有限宣言が必要")
    seen = set()
    for row in derived:
        if (
            type(row) is not dict
            or set(row) != {"id", "type", "components", "expression", "display"}
            or not identifier(row["id"])
            or row["id"] in seen | names
            or row["type"] != "ratio"
        ):
            raise ValueError("派生比の閉型/重複が不正")
        seen.add(row["id"])
        components = row["components"]
        if type(components) is not list or not 1 <= len(components) <= 8:
            raise ValueError("有限componentが必要")
        component_ids = set()
        for component in components:
            if (
                type(component) is not dict
                or set(component) != {"id", "expression"}
                or not identifier(component["id"])
                or component["id"] in component_ids
                or infer(component["expression"], set()) != "ratio"
            ):
                raise ValueError("componentの閉型/参照が不正")
            component_ids.add(component["id"])
        if infer(row["expression"], component_ids) != "ratio":
            raise ValueError("派生はintegerでなくratioが必要")
        display = row["display"]
        if (
            type(display) is not dict
            or set(display)
            != {"scale", "rounding", "leadingZero", "zeroDivisionGlyph", "denominators"}
            or type(display["scale"]) is not int
            or display["scale"] != 3
            or display["rounding"] != "half-up"
            or display["leadingZero"] is not True
            or display["zeroDivisionGlyph"] != "−"
        ):
            raise ValueError("採用済み最終比表示の指定が不一致")
        labels = display["denominators"]
        if (
            type(labels) is not list
            or len(labels) != 2
            or {x.get("component") for x in labels if type(x) is dict} != component_ids
        ):
            raise ValueError("両実分母の表示bindingが必要")
        for label in labels:
            if (
                type(label) is not dict
                or set(label) != {"component", "prefix", "suffix"}
                or any(
                    type(label[k]) is not str or not label[k]
                    for k in ("prefix", "suffix")
                )
            ):
                raise ValueError("分母表示の閉型が不正")


def validate_source_projections(program):
    """新source投影のshape・式・終結を有限型だけで検査する。"""
    projections = program["sourceProjections"]
    if type(projections) is not dict or set(projections) != {"batters_faced"}:
        raise ValueError("source投影の閉集合が不正")
    if [m["id"] for m in program["metrics"]][-1:] != ["batters_faced"] or len(
        program["metrics"]
    ) != 27:
        raise ValueError("BFは旧26に続く27番目が必要")

    def shape(node):
        if type(node) is not dict:
            raise ValueError("閉shapeが必要")
        if (
            set(node) == {"oneOf"}
            and type(node["oneOf"]) is list
            and 1 <= len(node["oneOf"]) <= 4
        ):
            for child in node["oneOf"]:
                shape(child)
        elif set(node) == {"const"} and type(node["const"]) is str:
            return
        elif (
            set(node) == {"enum"}
            and type(node["enum"]) is list
            and 1 <= len(node["enum"]) <= 8
            and all(type(x) is str for x in node["enum"])
        ):
            return
        elif node.get("type") == "string" and set(node) == {"type", "pattern"}:
            if node["pattern"] not in {
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![\s\S])",
                r"^[0-9a-f]{64}(?![\s\S])",
            }:
                raise ValueError("source shapeの未知文法")
        elif (
            node.get("type") == "object"
            and set(node) == {"type", "additionalProperties", "required", "properties"}
            and node["additionalProperties"] is False
            and type(node["properties"]) is dict
            and type(node["required"]) is list
            and len(node["required"]) == len(set(node["required"]))
            and set(node["required"]) == set(node["properties"])
            and 1 <= len(node["properties"]) <= 8
        ):
            for child in node["properties"].values():
                shape(child)
        else:
            raise ValueError("未知/余剰source shape")

    allowed = set(program["fields"]) | {
        "pa.bf_evidence",
        "pa.bf_evidence.kind",
        "pa.bf_evidence.reason",
        "pa.bf_evidence.pa_start_source.kind",
        "pa.bf_evidence.pa_start_source.id",
        "pa.bf_evidence.owner_field",
        "pa.bf_evidence.responsibility_ref.source_event_id",
        "pa.bf_evidence.responsibility_ref.artifact_sha256",
        "pa.starting_pitcher_id",
        "pa.pitcher_changes",
        "source.game_id",
        "source.versions.t1_artifact_sha256",
    }

    types = {key: value["type"] for key, value in program["fields"].items()}
    types.update({key: "string" for key in allowed - set(types)})
    types["pa.bf_evidence"] = "object"
    types["pa.pitcher_changes"] = "array"

    def expression(node):
        """source式も真偽・文字列・欠測・配列を混同させない。"""
        if type(node) is not dict:
            raise ValueError("閉source式が必要")
        op = node.get("op")
        if op == "literal" and set(node) == {"op", "value"}:
            value = node["value"]
            if value is None:
                return "null"
            if type(value) is bool:
                return "boolean"
            if type(value) is str:
                return "string"
            if type(value) is list and value == []:
                return "array"
        if op == "ref" and set(node) == {"op", "path"} and node["path"] in allowed:
            return types[node["path"]]
        if op in ("eq", "ne") and set(node) == {"op", "left", "right"}:
            left, right = expression(node["left"]), expression(node["right"])
            if left != right and "null" not in (left, right):
                raise ValueError("source比較の型違い")
            return "boolean"
        if (
            op in ("and", "or")
            and set(node) == {"op", "args"}
            and type(node["args"]) is list
            and 1 <= len(node["args"]) <= 8
        ):
            if any(expression(child) != "boolean" for child in node["args"]):
                raise ValueError("source論理式はbooleanだけ")
            return "boolean"
        if op == "choose" and set(node) == {"op", "when", "then", "otherwise"}:
            if expression(node["when"]) != "boolean":
                raise ValueError("source分岐条件はbooleanだけ")
            yes, no = expression(node["then"]), expression(node["otherwise"])
            if yes != no:
                raise ValueError("source分岐結果の型違い")
            return yes
        raise ValueError("未知/余剰source式")

    for plan in projections.values():
        if (
            type(plan) is not dict
            or set(plan) != {"checks", "rules"}
            or type(plan["checks"]) is not list
            or len(plan["checks"]) != 1
            or type(plan["rules"]) is not list
            or not 1 <= len(plan["rules"]) <= 32
        ):
            raise ValueError("source投影planの閉型違い")
        for check in plan["checks"]:
            if (
                set(check) != {"path", "schema", "optional"}
                or check["path"] != "pa.bf_evidence"
                or check["optional"] is not True
            ):
                raise ValueError("source shape参照不正")
            shape(check["schema"])
        for rule in plan["rules"]:
            action = rule.get("action")
            if action not in ("zero", "missing", "reject", "credit") or set(rule) != (
                {"when", "action", "value"}
                if action in ("missing", "credit")
                else {"when", "action"}
            ):
                raise ValueError("source投影action不正")
            if expression(rule["when"]) != "boolean":
                raise ValueError("source規則条件はbooleanだけ")
            if "value" in rule and expression(rule["value"]) != "string":
                raise ValueError("source理由/責任は文字列だけ")
        if (
            plan["rules"][-1].get("when") != {"op": "literal", "value": True}
            or plan["rules"][-1]["action"] != "credit"
        ):
            raise ValueError("source投影は有限終結が必要")
