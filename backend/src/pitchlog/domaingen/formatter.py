"""表示規則から formatter とテスト専用参照実装を生成する。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from pitchlog.domaingen.backends import (
    TARGET_CLASSES,
    GeneratedArtifact,
    Language,
    generate_language_artifacts,
)

_GENERATOR_ID = "pitchlog.domaingen.formatter.generate_display_artifacts"
_WRAPPER_DELIVERY = "wrapper-only-fragment"
_REFERENCE_DELIVERY = "test-only-property-layer"
_PYTHON_WRAPPER_NAME = "__pitchlog_generated_wrapper__"
_REFERENCE_MODULE_NAME = "__pitchlog_property_reference__"
_HASH_PREFIX = "sha256:"


class FormatterGenerationError(Exception):
    """表示生成物を宣言から生成できないことを表す。"""


class DisplayPurpose(StrEnum):
    """本ステップが生成する表示用途の閉じた集合。"""

    FORMATTER = "formatter"
    REFERENCE = "property-reference"
    ENUM_MAP_RECEIVER = "enum-map-receiver"


@dataclass(frozen=True, slots=True)
class GeneratedProvenance:
    """生成元と生成器の再実行に必要な provenance。

    Attributes:
        generator_id: 生成器の安定 ID。
        generator_version: 中間表現が持つ生成器 version。
        source_id: 宣言モデルの生成元条項 ID。
        source_hashes: コアが付与した段別 hash。
        content_hash: 本生成器が出力した内容の hash。
    """

    generator_id: str
    generator_version: str
    source_id: str
    source_hashes: tuple[str, ...]
    content_hash: str


@dataclass(frozen=True, slots=True)
class GeneratedDisplayArtifact:
    """表示生成器がメモリ上に返す生成物。

    Attributes:
        calculation_id: 対象計算 ID。
        direct_target_id: 直接呼び出し対象 ID。
        target_class: target matrix の区分。
        language: 出力言語。
        purpose: formatter・参照実装・写像受け口の別。
        delivery: 製品直結を許さない配布形態。
        content: 生成された実装内容。
        provenance: 再生成で照合できる生成由来。
    """

    calculation_id: str
    direct_target_id: str
    target_class: str
    language: Language
    purpose: DisplayPurpose
    delivery: str
    content: str
    provenance: GeneratedProvenance


@dataclass(frozen=True, slots=True)
class MatrixEvaluation:
    """全 target matrix の生成可否を表す機械評価。

    Attributes:
        expected: 契約が要求する区分集合。
        generated: 必要生成物がすべて得られた区分集合。
        failures: 生成不能だった区分と理由。
    """

    expected: frozenset[str]
    generated: frozenset[str]
    failures: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """全区分を生成できた場合だけ真を返す。"""
        return self.generated == self.expected and not self.failures


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise FormatterGenerationError(f"{label}が object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """配列を返す。"""
    if not isinstance(value, list):
        raise FormatterGenerationError(f"{label}が array でない")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise FormatterGenerationError(f"{label}が空でない文字列でない")
    return value


def _content_hash(content: str) -> str:
    """生成内容の SHA-256 hash を返す。"""
    digest = hashlib.sha256(content.encode()).hexdigest()
    return f"{_HASH_PREFIX}{digest}"


def _provenance(
    generator_version: str,
    source_id: str,
    source_hashes: tuple[str, ...],
    content: str,
) -> GeneratedProvenance:
    """生成器と入力段へ戻れる provenance を作る。"""
    return GeneratedProvenance(
        generator_id=_GENERATOR_ID,
        generator_version=generator_version,
        source_id=source_id,
        source_hashes=source_hashes,
        content_hash=_content_hash(content),
    )


def _artifact(
    *,
    calculation_id: str,
    direct_target_id: str,
    target_class: str,
    language: Language,
    purpose: DisplayPurpose,
    delivery: str,
    content: str,
    generator_version: str,
    source_id: str,
    source_hashes: tuple[str, ...],
) -> GeneratedDisplayArtifact:
    """共通 provenance を持つ表示生成物を返す。"""
    return GeneratedDisplayArtifact(
        calculation_id=calculation_id,
        direct_target_id=direct_target_id,
        target_class=target_class,
        language=language,
        purpose=purpose,
        delivery=delivery,
        content=content,
        provenance=_provenance(
            generator_version,
            source_id,
            source_hashes,
            content,
        ),
    )


def _python_helpers(module_name: str) -> list[str]:
    """Python formatter が共有する構造化数値 helper を生成する。"""
    return [
        "from decimal import Decimal, ROUND_HALF_UP",
        "from fractions import Fraction",
        "",
        f"if __name__ != {module_name!r}:",
        "    raise ImportError('生成物は指定ラッパー経由でのみ使用できます')",
        "",
        "def _pitchlog_number(value):",
        "    if value is None:",
        "        return None",
        "    kind = value['kind']",
        "    if kind == 'integer':",
        "        return Decimal(value['value'])",
        "    if kind == 'exact-decimal':",
        "        return Decimal(value['value'])",
        "    if kind == 'rational':",
        "        return Decimal(value['numerator']) / Decimal(value['denominator'])",
        "    raise ValueError('未知の NumericValue')",
        "",
        "def _pitchlog_fraction(value):",
        "    kind = value['kind']",
        "    if kind == 'integer':",
        "        return Fraction(value['value'], 1)",
        "    if kind == 'exact-decimal':",
        "        return Fraction(Decimal(value['value']))",
        "    if kind == 'rational':",
        "        return Fraction(value['numerator'], value['denominator'])",
        "    raise ValueError('未知の NumericValue')",
        "",
        "def _pitchlog_without_leading_zero(text):",
        "    if text.startswith('-0.'):",
        "        return '-.' + text[3:]",
        "    if text.startswith('0.'):",
        "        return '.' + text[2:]",
        "    return text",
        "",
    ]


def _python_numeric_branch(rule: Mapping[str, object]) -> list[str]:
    """数値 primitive 一つ分の Python 分岐本文を生成する。"""
    primitive = _object(rule.get("primitive"), "displayRule.primitive")
    kind = _string(primitive.get("kind"), "displayRule.primitive.kind")
    if kind in {"fixed-decimal", "percentage"}:
        scale = primitive.get("scale")
        leading_zero = primitive.get("leadingZero")
        if not isinstance(scale, int) or not isinstance(leading_zero, bool):
            raise FormatterGenerationError("数値 primitive の引数が不正")
        multiplier = " * Decimal(100)" if kind == "percentage" else ""
        suffix = " + '%'" if kind == "percentage" else ""
        return [
            "        number = _pitchlog_number(value)",
            "        if number is None:",
            "            raise ValueError('null は null-substitute で表示します')",
            f"        number = number{multiplier}",
            f"        quantum = Decimal(1).scaleb(-{scale})",
            "        rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)",
            f"        text = format(rounded, '.{scale}f')",
            *(
                []
                if leading_zero
                else ["        text = _pitchlog_without_leading_zero(text)"]
            ),
            f"        return text{suffix}",
        ]
    if kind == "mixed-fraction":
        denominator = primitive.get("denominator")
        suffix = primitive.get("integerSuffix")
        zero_remainder = primitive.get("zeroRemainder")
        if not isinstance(denominator, int) or not isinstance(suffix, str):
            raise FormatterGenerationError("混合分数 primitive の引数が不正")
        return [
            "        if value is None:",
            "            raise ValueError('null は null-substitute で表示します')",
            "        fraction = _pitchlog_fraction(value)",
            "        sign = '-' if fraction < 0 else ''",
            "        fraction = abs(fraction)",
            "        whole = fraction.numerator // fraction.denominator",
            f"        units = fraction * {denominator}",
            "        remainder = units.numerator // units.denominator",
            f"        remainder %= {denominator}",
            f"        whole_text = f'{{sign}}{{whole}}{suffix}'",
            *(
                ["        if remainder == 0:", "            return whole_text"]
                if zero_remainder == "omit-fraction"
                else []
            ),
            f"        return f'{{whole_text}}{{remainder}}/{denominator}'",
        ]
    if kind == "null-substitute":
        substitute = primitive.get("substitute")
        if not isinstance(substitute, str):
            raise FormatterGenerationError("null 代替 primitive の引数が不正")
        return [
            "        if value is not None:",
            "            raise ValueError('null 代替は null にだけ適用できます')",
            f"        return {substitute!r}",
        ]
    raise FormatterGenerationError(f"未知の数値 primitive: {kind}")


def _python_rule_branch(rule: Mapping[str, object], first: bool) -> list[str]:
    """表示規則一つ分の Python dispatcher 分岐を生成する。"""
    rule_id = _string(rule.get("id"), "displayRule.id")
    kind = _string(rule.get("kind"), "displayRule.kind")
    prefix = "if" if first else "elif"
    lines = [f"    {prefix} rule_id == {rule_id!r}:"]
    if kind == "numeric-primitive":
        return [*lines, *_python_numeric_branch(rule)]
    if kind == "enum-map":
        members = _array(rule.get("members"), "displayRule.members")
        mapping = {
            _string(_object(member, "member").get("value"), "member.value"):
            _string(_object(member, "member").get("display"), "member.display")
            for member in members
        }
        return [*lines, f"        return {mapping!r}[value]"]
    if kind == "template":
        pattern = rule.get("pattern")
        placeholders = _object(rule.get("placeholders"), "displayRule.placeholders")
        if not isinstance(pattern, str):
            raise FormatterGenerationError("template pattern が文字列でない")
        template_lines = [*lines, f"        result = {pattern!r}"]
        for name in placeholders:
            template_lines.append(
                f"        result = result.replace({f'{{{name}}}'!r}, atoms[{name!r}])"
            )
        return [*template_lines, "        return result"]
    raise FormatterGenerationError(f"未知の表示規則: {kind}")


def _python_formatter_content(
    rules: tuple[Mapping[str, object], ...],
    *,
    reference: bool,
) -> str:
    """宣言済み表示規則から Python formatter 本文を生成する。"""
    module_name = _REFERENCE_MODULE_NAME if reference else _PYTHON_WRAPPER_NAME
    lines = _python_helpers(module_name)
    lines.extend(
        [
            "def _pitchlog_format(rule_id, value, atoms=None):",
            "    atoms = {} if atoms is None else atoms",
        ]
    )
    for index, rule in enumerate(rules):
        lines.extend(_python_rule_branch(rule, index == 0))
    lines.append("    raise KeyError(rule_id)")
    if reference:
        lines.extend(
            [
                "",
                "def _pitchlog_reference(rule_id, value, atoms=None):",
                "    return _pitchlog_format(rule_id, value, atoms)",
            ]
        )
    return "\n".join(lines) + "\n"


def _typescript_helpers() -> list[str]:
    """TypeScript formatter が共有する helper を生成する。"""
    return [
        "const wrapper = globalThis;",
        "if (wrapper.__PITCHLOG_GENERATED_WRAPPER__ !== true) {",
        '  throw new Error("生成物は指定ラッパー経由でのみ使用できます");',
        "}",
        "function pitchlogNumber(value) {",
        "  if (value === null) return null;",
        "  if (value.kind === 'integer') return value.value;",
        "  if (value.kind === 'exact-decimal') return Number(value.value);",
        "  if (value.kind === 'rational') return value.numerator / value.denominator;",
        "  throw new Error('未知の NumericValue');",
        "}",
        "function pitchlogHalfUp(value, scale) {",
        "  const factor = 10 ** scale;",
        "  return Math.sign(value) * "
        "Math.floor(Math.abs(value) * factor + 0.5) / factor;",
        "}",
        "function pitchlogWithoutLeadingZero(text) {",
        "  if (text.startsWith('-0.')) return '-.' + text.slice(3);",
        "  if (text.startsWith('0.')) return '.' + text.slice(2);",
        "  return text;",
        "}",
    ]


def _typescript_numeric_branch(rule: Mapping[str, object]) -> list[str]:
    """数値 primitive 一つ分の TypeScript 分岐本文を生成する。"""
    primitive = _object(rule.get("primitive"), "displayRule.primitive")
    kind = _string(primitive.get("kind"), "displayRule.primitive.kind")
    if kind in {"fixed-decimal", "percentage"}:
        scale = primitive.get("scale")
        leading_zero = primitive.get("leadingZero")
        if not isinstance(scale, int) or not isinstance(leading_zero, bool):
            raise FormatterGenerationError("数値 primitive の引数が不正")
        multiplier = " * 100" if kind == "percentage" else ""
        suffix = " + '%'" if kind == "percentage" else ""
        return [
            "      let number = pitchlogNumber(value);",
            "      if (number === null) throw new Error('null は別規則で表示します');",
            f"      number = number{multiplier};",
            f"      let text = pitchlogHalfUp(number, {scale}).toFixed({scale});",
            *(
                []
                if leading_zero
                else ["      text = pitchlogWithoutLeadingZero(text);"]
            ),
            f"      return text{suffix};",
        ]
    if kind == "mixed-fraction":
        denominator = primitive.get("denominator")
        suffix = primitive.get("integerSuffix")
        zero_remainder = primitive.get("zeroRemainder")
        if not isinstance(denominator, int) or not isinstance(suffix, str):
            raise FormatterGenerationError("混合分数 primitive の引数が不正")
        return [
            "      const number = pitchlogNumber(value);",
            "      if (number === null) throw new Error('null は別規則で表示します');",
            "      const sign = number < 0 ? '-' : '';",
            "      const absolute = Math.abs(number);",
            "      const whole = Math.floor(absolute);",
            f"      const remainder = Math.round((absolute - whole) * {denominator});",
            f"      const wholeText = sign + whole + {json.dumps(suffix)};",
            *(
                ["      if (remainder === 0) return wholeText;"]
                if zero_remainder == "omit-fraction"
                else []
            ),
            f"      return wholeText + remainder + '/{denominator}';",
        ]
    if kind == "null-substitute":
        substitute = primitive.get("substitute")
        if not isinstance(substitute, str):
            raise FormatterGenerationError("null 代替 primitive の引数が不正")
        return [
            "      if (value !== null) throw new Error('null 専用の規則です');",
            f"      return {json.dumps(substitute, ensure_ascii=False)};",
        ]
    raise FormatterGenerationError(f"未知の数値 primitive: {kind}")


def _typescript_rule_case(rule: Mapping[str, object]) -> list[str]:
    """表示規則一つ分の TypeScript dispatcher 分岐を生成する。"""
    rule_id = _string(rule.get("id"), "displayRule.id")
    kind = _string(rule.get("kind"), "displayRule.kind")
    lines = [f"    case {json.dumps(rule_id)}:"]
    if kind == "numeric-primitive":
        return [*lines, *_typescript_numeric_branch(rule)]
    if kind == "enum-map":
        members = _array(rule.get("members"), "displayRule.members")
        mapping = {
            _string(_object(member, "member").get("value"), "member.value"):
            _string(_object(member, "member").get("display"), "member.display")
            for member in members
        }
        encoded = json.dumps(mapping, ensure_ascii=False, sort_keys=True)
        return [*lines, f"      return {encoded}[value];"]
    if kind == "template":
        pattern = rule.get("pattern")
        placeholders = _object(rule.get("placeholders"), "displayRule.placeholders")
        if not isinstance(pattern, str):
            raise FormatterGenerationError("template pattern が文字列でない")
        template_lines = [
            *lines,
            f"      let result = {json.dumps(pattern, ensure_ascii=False)};",
        ]
        for name in placeholders:
            marker = json.dumps(f"{{{name}}}")
            encoded_name = json.dumps(name)
            template_lines.append(
                f"      result = result.split({marker})"
                f".join(atoms[{encoded_name}]);"
            )
        return [*template_lines, "      return result;"]
    raise FormatterGenerationError(f"未知の表示規則: {kind}")


def _typescript_formatter_content(
    rules: tuple[Mapping[str, object], ...],
) -> str:
    """宣言済み表示規則から TypeScript formatter 本文を生成する。"""
    lines = _typescript_helpers()
    lines.extend(
        [
            "function pitchlogFormat(ruleId, value, atoms = {}) {",
            "  switch (ruleId) {",
        ]
    )
    for rule in rules:
        lines.extend(_typescript_rule_case(rule))
    lines.extend(
        [
            "    default:",
            "      throw new Error('未知の表示規則: ' + ruleId);",
            "  }",
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


def _rule_index(intermediate: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """中間表現の表示規則を ID で一意に索引化する。"""
    indexed: dict[str, dict[str, object]] = {}
    rules = _array(intermediate.get("displayRules"), "displayRules")
    for index, raw_rule in enumerate(rules):
        rule = _object(raw_rule, f"displayRules[{index}]")
        rule_id = _string(rule.get("id"), f"displayRules[{index}].id")
        if rule_id in indexed:
            raise FormatterGenerationError(f"表示規則 ID が重複: {rule_id}")
        indexed[rule_id] = rule
    return indexed


def _selected_rules(
    declaration: Mapping[str, object],
    rules: Mapping[str, dict[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """計算宣言が参照する表示規則を宣言順で返す。"""
    references = _array(declaration.get("displayRuleRefs"), "displayRuleRefs")
    if not references:
        raise FormatterGenerationError("表示規則を参照しない計算は表示生成できない")
    selected: list[Mapping[str, object]] = []
    for raw_reference in references:
        reference = _string(raw_reference, "displayRuleRefs[]")
        try:
            selected.append(rules[reference])
        except KeyError as error:
            raise FormatterGenerationError(f"未知の表示規則: {reference}") from error
    return tuple(selected)


def _target_hashes(target: Mapping[str, object]) -> tuple[str, ...]:
    """コアが付与した target の全段 hash を順序どおり返す。"""
    hashes: list[str] = []
    for raw_stage in _array(target.get("stages"), "target.stages"):
        stage = _object(raw_stage, "target.stages[]")
        hashes.append(_string(stage.get("sourceHash"), "stage.sourceHash"))
    return tuple(hashes)


def _formatter_hashes(
    target_class: str,
    target: Mapping[str, object],
) -> tuple[str, ...]:
    """対象区分の formatter が依拠する段 hash を返す。"""
    stages = _array(target.get("stages"), "target.stages")
    if target_class == "beta-1-5":
        for raw_stage in stages:
            stage = _object(raw_stage, "target.stages[]")
            if stage.get("stage") == "formatter":
                return (_string(stage.get("sourceHash"), "stage.sourceHash"),)
        raise FormatterGenerationError("beta-1-5 に formatter 段がない")
    return _target_hashes(target)


def _receiver_artifact(
    calculation_id: str,
    direct_target_id: str,
    language_artifacts: tuple[GeneratedArtifact, ...],
) -> GeneratedArtifact:
    """ステップ 27 が生成した β⑦ の写像受け口を一意に返す。"""
    matches = tuple(
        artifact
        for artifact in language_artifacts
        if artifact.calculation_id == calculation_id
        and artifact.direct_target_id == direct_target_id
        and artifact.target_class == "beta-7"
        and artifact.language is Language.PYTHON
    )
    if len(matches) != 1:
        raise FormatterGenerationError("β⑦ の写像適用受け口が一意でない")
    return matches[0]


def generate_display_artifacts(
    intermediate: Mapping[str, object],
) -> tuple[GeneratedDisplayArtifact, ...]:
    """中間表現から formatter・参照実装・β⑦受け口を生成する。

    Args:
        intermediate: ステップ 26 の言語非依存中間表現。

    Returns:
        製品経路へ配置しない provenance 付き表示生成物。

    Raises:
        FormatterGenerationError: 表示規則または target matrix が不正な場合。
    """
    generator_version = _string(
        intermediate.get("generatorVersion"),
        "generatorVersion",
    )
    rules = _rule_index(intermediate)
    try:
        language_artifacts = generate_language_artifacts(intermediate)
    except Exception as error:
        raise FormatterGenerationError(f"言語 backend の生成に失敗: {error}") from error

    artifacts: list[GeneratedDisplayArtifact] = []
    calculations = _array(intermediate.get("calculations"), "calculations")
    for calculation_index, raw_calculation in enumerate(calculations):
        calculation = _object(
            raw_calculation,
            f"calculations[{calculation_index}]",
        )
        calculation_id = _string(
            calculation.get("calculationId"),
            "calculation.calculationId",
        )
        source_id = _string(calculation.get("sourceId"), "calculation.sourceId")
        declaration = _object(
            calculation.get("declaration"),
            "calculation.declaration",
        )
        selected_rules = _selected_rules(declaration, rules)
        targets = _array(calculation.get("targets"), "calculation.targets")
        for raw_target in targets:
            target = _object(raw_target, "calculation.targets[]")
            direct_target_id = _string(
                target.get("directTargetId"),
                "target.directTargetId",
            )
            target_class = _string(target.get("targetClass"), "target.targetClass")
            source_hashes = _target_hashes(target)
            reference_content = _python_formatter_content(
                selected_rules,
                reference=True,
            )
            artifacts.append(
                _artifact(
                    calculation_id=calculation_id,
                    direct_target_id=direct_target_id,
                    target_class=target_class,
                    language=Language.PYTHON,
                    purpose=DisplayPurpose.REFERENCE,
                    delivery=_REFERENCE_DELIVERY,
                    content=reference_content,
                    generator_version=generator_version,
                    source_id=source_id,
                    source_hashes=source_hashes,
                )
            )

            if target_class in {"alpha", "beta-1-5"}:
                formatter_hashes = _formatter_hashes(target_class, target)
                python_content = _python_formatter_content(
                    selected_rules,
                    reference=False,
                )
                artifacts.append(
                    _artifact(
                        calculation_id=calculation_id,
                        direct_target_id=direct_target_id,
                        target_class=target_class,
                        language=Language.PYTHON,
                        purpose=DisplayPurpose.FORMATTER,
                        delivery=_WRAPPER_DELIVERY,
                        content=python_content,
                        generator_version=generator_version,
                        source_id=source_id,
                        source_hashes=formatter_hashes,
                    )
                )
                if target_class == "alpha":
                    typescript_content = _typescript_formatter_content(selected_rules)
                    artifacts.append(
                        _artifact(
                            calculation_id=calculation_id,
                            direct_target_id=direct_target_id,
                            target_class=target_class,
                            language=Language.TYPESCRIPT,
                            purpose=DisplayPurpose.FORMATTER,
                            delivery=_WRAPPER_DELIVERY,
                            content=typescript_content,
                            generator_version=generator_version,
                            source_id=source_id,
                            source_hashes=formatter_hashes,
                        )
                    )

            if target_class == "beta-7":
                receiver = _receiver_artifact(
                    calculation_id,
                    direct_target_id,
                    language_artifacts,
                )
                artifacts.append(
                    _artifact(
                        calculation_id=calculation_id,
                        direct_target_id=direct_target_id,
                        target_class=target_class,
                        language=Language.PYTHON,
                        purpose=DisplayPurpose.ENUM_MAP_RECEIVER,
                        delivery=_WRAPPER_DELIVERY,
                        content=receiver.content,
                        generator_version=generator_version,
                        source_id=source_id,
                        source_hashes=(receiver.source_hash,),
                    )
                )
    return tuple(artifacts)


def verify_generated_provenance(
    artifact: GeneratedDisplayArtifact,
    intermediate: Mapping[str, object],
) -> bool:
    """生成器を再実行し、成果物が手書きでないことを検証する。

    Args:
        artifact: 由来を検証する表示生成物。
        intermediate: 再生成に使う宣言モデル由来の中間表現。

    Returns:
        再生成物に同一成果物が存在し、内容 hash も一致すれば真。
    """
    if artifact.provenance.generator_id != _GENERATOR_ID:
        return False
    if artifact.provenance.content_hash != _content_hash(artifact.content):
        return False
    try:
        regenerated = generate_display_artifacts(intermediate)
    except FormatterGenerationError:
        return False
    return artifact in regenerated


def evaluate_target_matrix(
    intermediate: Mapping[str, object],
) -> MatrixEvaluation:
    """全 target matrix の必要生成物が実際に生成できるか評価する。

    Args:
        intermediate: 全区分を含むステップ 26 の中間表現。

    Returns:
        4 区分の実測結果。1 区分でも不足すれば `complete` は偽。
    """
    expected = frozenset(TARGET_CLASSES)
    try:
        language_artifacts = generate_language_artifacts(intermediate)
        display_artifacts = generate_display_artifacts(intermediate)
    except Exception as error:
        return MatrixEvaluation(expected, frozenset(), (str(error),))

    requirements = {
        "alpha": (
            {(Language.PYTHON, None), (Language.TYPESCRIPT, None)},
            {
                (Language.PYTHON, DisplayPurpose.FORMATTER),
                (Language.TYPESCRIPT, DisplayPurpose.FORMATTER),
                (Language.PYTHON, DisplayPurpose.REFERENCE),
            },
        ),
        "beta-1-5": (
            {(Language.SQL, None), (Language.PYTHON, None)},
            {
                (Language.PYTHON, DisplayPurpose.FORMATTER),
                (Language.PYTHON, DisplayPurpose.REFERENCE),
            },
        ),
        "beta-7": (
            {(Language.SQL, None), (Language.PYTHON, None)},
            {
                (Language.PYTHON, DisplayPurpose.ENUM_MAP_RECEIVER),
                (Language.PYTHON, DisplayPurpose.REFERENCE),
            },
        ),
        "beta-6-8": (
            {(Language.PYTHON, None)},
            {(Language.PYTHON, DisplayPurpose.REFERENCE)},
        ),
    }
    generated: set[str] = set()
    failures: list[str] = []
    for target_class in sorted(expected):
        language_observed = {
            (artifact.language, None)
            for artifact in language_artifacts
            if artifact.target_class == target_class
        }
        display_observed = {
            (artifact.language, artifact.purpose)
            for artifact in display_artifacts
            if artifact.target_class == target_class
        }
        language_required, display_required = requirements[target_class]
        missing_language = language_required - language_observed
        missing_display = display_required - display_observed
        if missing_language or missing_display:
            failures.append(
                f"{target_class}: language={sorted(map(str, missing_language))!r}, "
                f"display={sorted(map(str, missing_display))!r}"
            )
            continue
        generated.add(target_class)
    return MatrixEvaluation(expected, frozenset(generated), tuple(failures))


__all__ = [
    "DisplayPurpose",
    "FormatterGenerationError",
    "GeneratedDisplayArtifact",
    "GeneratedProvenance",
    "MatrixEvaluation",
    "evaluate_target_matrix",
    "generate_display_artifacts",
    "verify_generated_provenance",
]
