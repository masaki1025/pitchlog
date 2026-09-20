"""表示生成物に対する五系統の変異演算子を提供する。

`ADR-003 D-11 ② 決定表` の表示系だけを扱い、変異の生成と判定を分離する。
実行と生存判定はステップ 39 の変異エンジンへ委ね、formatter の生成は既存の
`pitchlog.domaingen.formatter` を正とする。
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

from pitchlog.domainmut.engine import (
    Mutant,
    MutantExecutor,
    MutationEngineError,
    MutationGeneration,
    MutationOperator,
    MutationReport,
    SyntheticMutationTarget,
    run_mutations,
)

EQUIVALENCE_LEDGER_PATH = "backend/domain/mutation-equivalents.json"


class DisplayMutationKind(StrEnum):
    """表示系変異演算子の閉じた五系統。"""

    STRING_LITERAL = "string-literal"
    TEMPLATE_PLACEHOLDER = "template-placeholder"
    ENUM_MAP = "enum-map"
    PRIMITIVE_PARAMETER = "primitive-parameter"
    FORMATTER_INVOCATION = "formatter-invocation"


class FormatterRoute(StrEnum):
    """製品表示呼出箇所が値を表示へ渡す経路。"""

    FORMATTER = "formatter"
    RAW_VALUE = "raw-value"
    LANGUAGE_DEFAULT = "language-default-stringification"


@dataclass(frozen=True, slots=True)
class FormatterInvocation:
    """formatter 呼出しの変異に必要な製品経路の合成入力。

    Attributes:
        rule_id: 呼び出す表示規則 ID。
        numeric_value: formatter が受け取る構造化数値。
        language_value: 言語既定文字列化へ渡される言語上の値。
        route: formatter を経由するかを表す経路。
    """

    rule_id: str
    numeric_value: object
    language_value: object
    route: FormatterRoute = FormatterRoute.FORMATTER


@dataclass(frozen=True, slots=True)
class DisplayMutationSource:
    """表示宣言の中間表現と製品側 formatter 呼出しを結ぶ変異対象。

    Attributes:
        intermediate: ステップ 26 が生成した言語非依存中間表現。
        invocation: formatter 呼出しの合成入力。
        mutation_kind: 適用済みの表示系統。元入力では ``None``。
        mutation_detail: 同一系統内の変異箇所。元入力では ``None``。
    """

    intermediate: Mapping[str, object]
    invocation: FormatterInvocation
    mutation_kind: DisplayMutationKind | None = None
    mutation_detail: str | None = None


@dataclass(frozen=True, slots=True)
class EquivalenceReferral:
    """人手判定が必要な mutant を後続の台帳へ送る記録。"""

    mutant_id: str
    ledger_path: str
    reason: str
    required_judge: str


def _source(
    target: SyntheticMutationTarget,
) -> DisplayMutationSource | None:
    """表示変異対象だけを返し、他種別には適用しない。"""
    if not isinstance(target.source, DisplayMutationSource):
        return None
    return target.source


def _mutable_intermediate(source: DisplayMutationSource) -> dict[str, object]:
    """変異ごとに独立した中間表現の写しを返す。"""
    value = copy.deepcopy(source.intermediate)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("intermediate が文字列キーの object でない")
    return value


def _rules(intermediate: Mapping[str, object]) -> list[dict[str, object]]:
    """中間表現の表示規則を mutable object として返す。"""
    raw_rules = intermediate.get("displayRules")
    if not isinstance(raw_rules, list):
        return []
    return [
        cast(dict[str, object], rule)
        for rule in raw_rules
        if isinstance(rule, dict) and all(isinstance(key, str) for key in rule)
    ]


def _changed_source(
    source: DisplayMutationSource,
    intermediate: Mapping[str, object],
    kind: DisplayMutationKind,
    detail: str,
    *,
    invocation: FormatterInvocation | None = None,
) -> DisplayMutationSource:
    """一変異の位置を記録した表示ソースを返す。"""
    return DisplayMutationSource(
        intermediate=intermediate,
        invocation=source.invocation if invocation is None else invocation,
        mutation_kind=kind,
        mutation_detail=detail,
    )


def _mutant(
    target: SyntheticMutationTarget,
    operator_id: str,
    index: int,
    source: DisplayMutationSource,
    *,
    equivalence_claimed: bool = False,
) -> Mutant:
    """表示変異を安定 ID 付き mutant にする。"""
    detail = source.mutation_detail or f"mutation-{index}"
    return Mutant(
        mutant_id=(
            f"{target.calculation}.{target.target_id}.{operator_id}.{index}.{detail}"
        ),
        calculation=target.calculation,
        target_id=target.target_id,
        operator_id=operator_id,
        mutated=source,
        equivalence_claimed=equivalence_claimed,
    )


def _replace_display(value: str) -> str:
    """元値と必ず異なる表示リテラルを返す。"""
    return f"{value}__mutated__"


@dataclass(frozen=True, slots=True)
class StringLiteralMutationOperator:
    """表示用の文字列リテラルを置換する。"""

    operator_id: str = "display-string-literal"

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """Null 代替と整数部助数詞を一箇所ずつ置換する。"""
        source = _source(target)
        if source is None:
            return MutationGeneration((), ())
        changes: list[DisplayMutationSource] = []
        for rule_index, rule in enumerate(_rules(source.intermediate)):
            if rule.get("kind") != "numeric-primitive":
                continue
            primitive = rule.get("primitive")
            if not isinstance(primitive, dict):
                continue
            for field in ("substitute", "integerSuffix"):
                value = primitive.get(field)
                if not isinstance(value, str):
                    continue
                intermediate = _mutable_intermediate(source)
                changed_rule = _rules(intermediate)[rule_index]
                changed_primitive = cast(dict[str, object], changed_rule["primitive"])
                changed_primitive[field] = _replace_display(value)
                changes.append(
                    _changed_source(
                        source,
                        intermediate,
                        DisplayMutationKind.STRING_LITERAL,
                        f"displayRules-{rule_index}-{field}",
                    )
                )
        mutants = tuple(
            _mutant(target, self.operator_id, index, changed)
            for index, changed in enumerate(changes, start=1)
        )
        return MutationGeneration(mutants, ())


_PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_.-]*)\}")


def _swap_first_two_placeholders(pattern: str) -> str | None:
    """先頭二つの placeholder の位置を入れ替える。"""
    matches = tuple(_PLACEHOLDER.finditer(pattern))
    if len(matches) < 2:
        return None
    first, second = matches[:2]
    return "".join(
        (
            pattern[: first.start()],
            second.group(0),
            pattern[first.end() : second.start()],
            first.group(0),
            pattern[second.end() :],
        )
    )


@dataclass(frozen=True, slots=True)
class TemplatePlaceholderMutationOperator:
    """template placeholder を削除または入れ替える。"""

    operator_id: str = "display-template-placeholder"

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """各 placeholder の削除と先頭二つの入替を生成する。"""
        source = _source(target)
        if source is None:
            return MutationGeneration((), ())
        changes: list[DisplayMutationSource] = []
        for rule_index, rule in enumerate(_rules(source.intermediate)):
            if rule.get("kind") != "template":
                continue
            pattern = rule.get("pattern")
            if not isinstance(pattern, str):
                continue
            for placeholder_index, match in enumerate(
                _PLACEHOLDER.finditer(pattern),
                start=1,
            ):
                intermediate = _mutable_intermediate(source)
                changed_rule = _rules(intermediate)[rule_index]
                changed_rule["pattern"] = (
                    pattern[: match.start()] + pattern[match.end() :]
                )
                changes.append(
                    _changed_source(
                        source,
                        intermediate,
                        DisplayMutationKind.TEMPLATE_PLACEHOLDER,
                        f"displayRules-{rule_index}-delete-{placeholder_index}",
                    )
                )
            swapped = _swap_first_two_placeholders(pattern)
            if swapped is not None and swapped != pattern:
                intermediate = _mutable_intermediate(source)
                _rules(intermediate)[rule_index]["pattern"] = swapped
                changes.append(
                    _changed_source(
                        source,
                        intermediate,
                        DisplayMutationKind.TEMPLATE_PLACEHOLDER,
                        f"displayRules-{rule_index}-swap",
                    )
                )
        mutants = tuple(
            _mutant(target, self.operator_id, index, changed)
            for index, changed in enumerate(changes, start=1)
        )
        return MutationGeneration(mutants, ())


@dataclass(frozen=True, slots=True)
class EnumMapMutationOperator:
    """enum 写像テーブルの表示値と対応順を変異する。"""

    operator_id: str = "display-enum-map"

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """表示値の置換と値列の回転を一件ずつ生成する。"""
        source = _source(target)
        if source is None:
            return MutationGeneration((), ())
        changes: list[DisplayMutationSource] = []
        for rule_index, rule in enumerate(_rules(source.intermediate)):
            if rule.get("kind") != "enum-map":
                continue
            members = rule.get("members")
            if not isinstance(members, list):
                continue
            valid_members = [member for member in members if isinstance(member, dict)]
            for member_index, member in enumerate(valid_members):
                display = member.get("display")
                if not isinstance(display, str):
                    continue
                intermediate = _mutable_intermediate(source)
                changed_members = cast(
                    list[dict[str, object]],
                    _rules(intermediate)[rule_index]["members"],
                )
                changed_members[member_index]["display"] = _replace_display(display)
                changes.append(
                    _changed_source(
                        source,
                        intermediate,
                        DisplayMutationKind.ENUM_MAP,
                        f"displayRules-{rule_index}-value-{member_index}",
                    )
                )
            displays = [member.get("display") for member in valid_members]
            if len(displays) >= 2 and all(isinstance(item, str) for item in displays):
                intermediate = _mutable_intermediate(source)
                changed_members = cast(
                    list[dict[str, object]],
                    _rules(intermediate)[rule_index]["members"],
                )
                rotated = displays[1:] + displays[:1]
                for member, display in zip(changed_members, rotated, strict=True):
                    member["display"] = display
                changes.append(
                    _changed_source(
                        source,
                        intermediate,
                        DisplayMutationKind.ENUM_MAP,
                        f"displayRules-{rule_index}-order",
                    )
                )
        mutants = tuple(
            _mutant(target, self.operator_id, index, changed)
            for index, changed in enumerate(changes, start=1)
        )
        return MutationGeneration(mutants, ())


def _primitive_change(
    source: DisplayMutationSource,
    rule_index: int,
    field: str,
    value: object,
) -> DisplayMutationSource:
    """数値 primitive の指定パラメータだけを変更する。"""
    intermediate = _mutable_intermediate(source)
    rule = _rules(intermediate)[rule_index]
    primitive = cast(dict[str, object], rule["primitive"])
    primitive[field] = value
    return _changed_source(
        source,
        intermediate,
        DisplayMutationKind.PRIMITIVE_PARAMETER,
        f"displayRules-{rule_index}-{field}",
    )


@dataclass(frozen=True, slots=True)
class PrimitiveParameterMutationOperator:
    """表示 primitive の五つの契約パラメータを変異する。"""

    operator_id: str = "display-primitive-parameter"

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """scale・丸め・先頭0・記号・剰余0形の変異を生成する。"""
        source = _source(target)
        if source is None:
            return MutationGeneration((), ())
        changes: list[DisplayMutationSource] = []
        for rule_index, rule in enumerate(_rules(source.intermediate)):
            if rule.get("kind") != "numeric-primitive":
                continue
            primitive = rule.get("primitive")
            if not isinstance(primitive, dict):
                continue
            scale = primitive.get("scale")
            if isinstance(scale, int) and not isinstance(scale, bool):
                changes.append(
                    _primitive_change(source, rule_index, "scale", scale + 1)
                )
            if "rounding" in primitive:
                changes.append(
                    _primitive_change(
                        source,
                        rule_index,
                        "rounding",
                        "mutated-rounding",
                    )
                )
            leading_zero = primitive.get("leadingZero")
            if isinstance(leading_zero, bool):
                changes.append(
                    _primitive_change(
                        source,
                        rule_index,
                        "leadingZero",
                        not leading_zero,
                    )
                )
            if "symbol" in primitive:
                changes.append(
                    _primitive_change(
                        source,
                        rule_index,
                        "symbol",
                        "mutated-symbol",
                    )
                )
            zero_remainder = primitive.get("zeroRemainder")
            if zero_remainder in {"omit-fraction", "show-zero-fraction"}:
                replacement = (
                    "show-zero-fraction"
                    if zero_remainder == "omit-fraction"
                    else "omit-fraction"
                )
                changes.append(
                    _primitive_change(
                        source,
                        rule_index,
                        "zeroRemainder",
                        replacement,
                    )
                )
        mutants = tuple(
            _mutant(target, self.operator_id, index, changed)
            for index, changed in enumerate(changes, start=1)
        )
        return MutationGeneration(mutants, ())


def _invocation_scale(source: DisplayMutationSource) -> int | None:
    """呼出対象が固定小数なら宣言された scale を返す。"""
    for rule in _rules(source.intermediate):
        if rule.get("id") != source.invocation.rule_id:
            continue
        primitive = rule.get("primitive")
        if not isinstance(primitive, dict):
            return None
        if primitive.get("kind") != "fixed-decimal":
            return None
        scale = primitive.get("scale")
        if isinstance(scale, int) and not isinstance(scale, bool):
            return scale
        return None
    return None


@dataclass(frozen=True, slots=True)
class FormatterInvocationMutationOperator:
    """formatter 呼出しを削除し、または言語既定文字列化へ置換する。"""

    operator_id: str = "display-formatter-invocation"

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """二つの迂回経路を生成し、scale 0 の同値候補だけを印付けする。"""
        source = _source(target)
        if source is None:
            return MutationGeneration((), ())
        scale = _invocation_scale(source)
        raw_source = _changed_source(
            source,
            source.intermediate,
            DisplayMutationKind.FORMATTER_INVOCATION,
            f"delete-call-scale-{scale}",
            invocation=replace(
                source.invocation,
                route=FormatterRoute.RAW_VALUE,
            ),
        )
        default_source = _changed_source(
            source,
            source.intermediate,
            DisplayMutationKind.FORMATTER_INVOCATION,
            f"language-default-scale-{scale}",
            invocation=replace(
                source.invocation,
                route=FormatterRoute.LANGUAGE_DEFAULT,
            ),
        )
        scale_zero = scale == 0
        return MutationGeneration(
            (
                _mutant(target, self.operator_id, 1, raw_source),
                _mutant(
                    target,
                    self.operator_id,
                    2,
                    default_source,
                    equivalence_claimed=scale_zero,
                ),
            ),
            (),
        )


DISPLAY_OPERATORS = {
    DisplayMutationKind.STRING_LITERAL: StringLiteralMutationOperator(),
    DisplayMutationKind.TEMPLATE_PLACEHOLDER: (TemplatePlaceholderMutationOperator()),
    DisplayMutationKind.ENUM_MAP: EnumMapMutationOperator(),
    DisplayMutationKind.PRIMITIVE_PARAMETER: PrimitiveParameterMutationOperator(),
    DisplayMutationKind.FORMATTER_INVOCATION: FormatterInvocationMutationOperator(),
}
_DISPLAY_OPERATOR_IDS = frozenset(
    operator.operator_id for operator in DISPLAY_OPERATORS.values()
)


def require_display_operator_application(
    targets: Iterable[SyntheticMutationTarget],
    operators: Iterable[MutationOperator],
) -> None:
    """表示生成物を持つ計算へ表示系演算子が一つ以上あることを要求する。"""
    target_items = tuple(targets)
    operator_ids = {operator.operator_id for operator in operators}
    calculations = {
        target.calculation
        for target in target_items
        if isinstance(target.source, DisplayMutationSource)
    }
    if calculations and not operator_ids.intersection(_DISPLAY_OPERATOR_IDS):
        raise MutationEngineError(
            f"表示生成物を持つ対象計算に表示系演算子がない: {sorted(calculations)!r}"
        )


def equivalence_referrals(mutants: Iterable[Mutant]) -> tuple[EquivalenceReferral, ...]:
    """自己申告で除外せず、人手判定が必要な候補を台帳へ送る。"""
    return tuple(
        EquivalenceReferral(
            mutant_id=mutant.mutant_id,
            ledger_path=EQUIVALENCE_LEDGER_PATH,
            reason=(
                "固定小数 scale=0 では formatter と言語既定文字列化の"
                "表示が同一になり得る"
            ),
            required_judge="PO",
        )
        for mutant in mutants
        if mutant.equivalence_claimed
    )


def run_display_mutations(
    targets: Iterable[SyntheticMutationTarget],
    operators: Iterable[MutationOperator],
    executor: MutantExecutor,
    approved_equivalent_ids: Iterable[str] = (),
) -> MutationReport:
    """適用義務を確認して既存の変異エンジンへ処理を委譲する。"""
    target_items = tuple(targets)
    operator_items = tuple(operators)
    require_display_operator_application(target_items, operator_items)
    return run_mutations(
        targets=target_items,
        operators=operator_items,
        executor=executor,
        approved_equivalent_ids=approved_equivalent_ids,
    )


__all__ = [
    "DISPLAY_OPERATORS",
    "EQUIVALENCE_LEDGER_PATH",
    "DisplayMutationKind",
    "DisplayMutationSource",
    "EnumMapMutationOperator",
    "EquivalenceReferral",
    "FormatterInvocation",
    "FormatterInvocationMutationOperator",
    "FormatterRoute",
    "PrimitiveParameterMutationOperator",
    "StringLiteralMutationOperator",
    "TemplatePlaceholderMutationOperator",
    "equivalence_referrals",
    "require_display_operator_application",
    "run_display_mutations",
]
