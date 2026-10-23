"""試合の適用規則を既存の凍結契約に従って検証・変換する。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Final, cast
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.protocols import Validator

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[5]
    / "contracts/state-transition/game_end_contract_schema_v1.json"
)
_RULE_REF: Final = "#/$defs/ruleSnapshot"
_VALUE_KEYS: Final = frozenset(
    {"regulationInnings", "coldConditions", "extensionLimit", "tiebreak", "dh"}
)
_PAYLOAD_KEYS: Final = _VALUE_KEYS | {"ruleSetId"}
_RUNNER_PLACEMENT: Final = "no_out_first_second"
_LEADOFF_RULE: Final = "continue_lineup"


class RuleSnapshotFailure(StrEnum):
    """入力を受理できない固定分類。"""

    SHAPE = "shape_invalid"
    VALUE = "value_invalid"
    CORRELATION = "correlation_invalid"
    UNRESOLVED = "correlation_unresolved"


class RuleSnapshotInvalid(ValueError):
    """規則値を検証済みとして扱えない場合の失敗。"""

    def __init__(self, kind: RuleSnapshotFailure) -> None:
        """入力内容を例外文に含めずに分類を保持する。

        Args:
            kind: 拒否した検証境界。
        """
        self.kind = kind
        super().__init__(f"適用規則を検証できません: {kind.value}")


class RuleSnapshotContractUnavailable(RuntimeError):
    """凍結schemaを読み取れず、入力の判定を完了できない場合の失敗。"""


def _require_exact_integer(value: object) -> None:
    """構造化済みDTOではfloatやboolを整数fieldとして扱わない。"""
    if type(value) is not int:
        raise RuleSnapshotInvalid(RuleSnapshotFailure.SHAPE)


@dataclass(frozen=True, slots=True)
class ColdTier:
    """コールド条件の一段。"""

    point_difference: int
    start_inning: int

    def __post_init__(self) -> None:
        """直接構築でも整数fieldのexact型を保証する。"""
        _require_exact_integer(self.point_difference)
        _require_exact_integer(self.start_inning)


@dataclass(frozen=True, slots=True)
class TiebreakRule:
    """タイブレーク規則の値。"""

    start_inning: int
    runner_placement: str
    leadoff_rule: str

    def __post_init__(self) -> None:
        """直接構築でも開始回のexact整数型を保証する。"""
        _require_exact_integer(self.start_inning)


@dataclass(frozen=True, slots=True)
class StructuralRuleSnapshot:
    """6-key形・UUID・5値schemaを検証した値。相関と出所は未証明。"""

    rule_set_id: UUID
    regulation_innings: int
    cold_conditions: tuple[ColdTier, ...]
    extension_limit: int | None
    tiebreak: TiebreakRule | None
    dh: bool

    def __post_init__(self) -> None:
        """直接構築した値にも構造・値域検証を適用する。"""
        _validate_structural(self)


@dataclass(frozen=True, slots=True)
class DomainValidatedRuleSnapshot:
    """付録F-1の相関を検査した値。規則行の出所は未証明。"""

    structural: StructuralRuleSnapshot

    def __post_init__(self) -> None:
        """直接構築でも単一の相関検査を通す。"""
        if type(self.structural) is not StructuralRuleSnapshot:
            raise RuleSnapshotInvalid(RuleSnapshotFailure.SHAPE)
        _validate_structural(self.structural)
        _validate_correlations(self.structural)


@lru_cache(maxsize=1)
def _validator() -> Validator:
    """既存の凍結schemaから5値のvalidatorを作る。"""
    try:
        contract = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        if (
            type(contract) is not dict
            or contract.get("x-pitchlog-rule-snapshot-definition") != _RULE_REF
        ):
            raise RuleSnapshotContractUnavailable("規則snapshotの契約位置が不正です")
        schema = {
            "$schema": contract["$schema"],
            "$defs": contract["$defs"],
            "$ref": _RULE_REF,
        }
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)
    except RuleSnapshotContractUnavailable:
        raise
    except (OSError, ValueError, KeyError, TypeError, SchemaError) as exc:
        raise RuleSnapshotContractUnavailable(
            "規則snapshotの凍結契約を読み取れません"
        ) from exc


def _validate_values(values: dict[str, object]) -> None:
    """既存schemaへ5値だけを投影して形と単独値域を検査する。"""
    error = next(iter(_validator().iter_errors(values)), None)
    if error is not None:
        raise RuleSnapshotInvalid(_schema_failure(error)) from None
    tiebreak = values["tiebreak"]
    if tiebreak is not None:
        if type(tiebreak) is not dict:
            raise AssertionError("schema検証後のタイブレーク型が不正です")
        typed_tiebreak = cast(dict[str, object], tiebreak)
        if (
            typed_tiebreak["runnerPlacement"] != _RUNNER_PLACEMENT
            or typed_tiebreak["leadoffRule"] != _LEADOFF_RULE
        ):
            raise RuleSnapshotInvalid(RuleSnapshotFailure.VALUE)


def _schema_failure(error: ValidationError) -> RuleSnapshotFailure:
    """schema違反を固定の公開分類へ写す。"""
    shape_validators = {
        "type",
        "required",
        "additionalProperties",
        "maxItems",
        "minItems",
    }
    if error.validator in shape_validators:
        return RuleSnapshotFailure.SHAPE
    if error.validator == "oneOf":
        matching_type_errors = [
            child for child in error.context if child.validator != "type"
        ]
        if not matching_type_errors:
            return RuleSnapshotFailure.SHAPE
        if any(child.validator in shape_validators for child in matching_type_errors):
            return RuleSnapshotFailure.SHAPE
    return RuleSnapshotFailure.VALUE


def _values_from_structural(value: StructuralRuleSnapshot) -> dict[str, object]:
    """不変型を既存5値schema用の新しい値へ変換する。"""
    if type(value.cold_conditions) is not tuple or any(
        type(tier) is not ColdTier for tier in value.cold_conditions
    ):
        raise RuleSnapshotInvalid(RuleSnapshotFailure.SHAPE)
    if value.tiebreak is not None and type(value.tiebreak) is not TiebreakRule:
        raise RuleSnapshotInvalid(RuleSnapshotFailure.SHAPE)
    for tier in value.cold_conditions:
        _require_exact_integer(tier.point_difference)
        _require_exact_integer(tier.start_inning)
    if value.tiebreak is not None:
        _require_exact_integer(value.tiebreak.start_inning)
    return {
        "regulationInnings": value.regulation_innings,
        "coldConditions": [
            {"pointDifference": tier.point_difference, "startInning": tier.start_inning}
            for tier in value.cold_conditions
        ],
        "extensionLimit": value.extension_limit,
        "tiebreak": (
            None
            if value.tiebreak is None
            else {
                "startInning": value.tiebreak.start_inning,
                "runnerPlacement": value.tiebreak.runner_placement,
                "leadoffRule": value.tiebreak.leadoff_rule,
            }
        ),
        "dh": value.dh,
    }


def _validate_structural(value: StructuralRuleSnapshot) -> None:
    """直接生成・変換・再利用の全経路で構造契約を確認する。"""
    if type(value.rule_set_id) is not UUID:
        raise RuleSnapshotInvalid(RuleSnapshotFailure.VALUE)
    _require_exact_integer(value.regulation_innings)
    if value.extension_limit is not None:
        _require_exact_integer(value.extension_limit)
    _validate_values(_values_from_structural(value))


def _decode_uuid(value: object) -> UUID:
    """正規の小文字・ハイフン付きUUID文字列だけを受理する。"""
    if type(value) is not str:
        raise RuleSnapshotInvalid(RuleSnapshotFailure.VALUE)
    try:
        parsed = UUID(value)
    except ValueError:
        raise RuleSnapshotInvalid(RuleSnapshotFailure.VALUE) from None
    if str(parsed) != value:
        raise RuleSnapshotInvalid(RuleSnapshotFailure.VALUE)
    return parsed


def decode_structure(value: object) -> StructuralRuleSnapshot:
    """JSONB値の形・UUID・5値の単独値域を検査する。

    Args:
        value: DBまたはJSON由来の未検証値。

    Returns:
        相関・出所をまだ証明していない不変値。

    Raises:
        RuleSnapshotInvalid: 値を構造検証済みとして受理できない場合。
        RuleSnapshotContractUnavailable: 凍結schemaを読めない場合。
    """
    if type(value) is not dict or set(value) != _PAYLOAD_KEYS:
        raise RuleSnapshotInvalid(RuleSnapshotFailure.SHAPE)
    raw = cast(dict[str, object], value)
    rule_set_id = _decode_uuid(raw["ruleSetId"])
    values = {key: raw[key] for key in _VALUE_KEYS}
    _validate_values(values)
    cold = cast(list[dict[str, object]], values["coldConditions"])
    tiebreak = cast(dict[str, object] | None, values["tiebreak"])
    extension_limit = values["extensionLimit"]
    # schemaのintegerは9.0等も受理するため、検証後に同じ値のintへ写す。
    return StructuralRuleSnapshot(
        rule_set_id=rule_set_id,
        regulation_innings=int(cast(int | float, values["regulationInnings"])),
        cold_conditions=tuple(
            ColdTier(
                int(cast(int | float, tier["pointDifference"])),
                int(cast(int | float, tier["startInning"])),
            )
            for tier in cold
        ),
        extension_limit=(
            None if extension_limit is None else int(cast(int | float, extension_limit))
        ),
        tiebreak=(
            None
            if tiebreak is None
            else TiebreakRule(
                int(cast(int | float, tiebreak["startInning"])),
                cast(str, tiebreak["runnerPlacement"]),
                cast(str, tiebreak["leadoffRule"]),
            )
        ),
        dh=cast(bool, values["dh"]),
    )


def validate_correlations(
    value: StructuralRuleSnapshot,
) -> DomainValidatedRuleSnapshot:
    """単一の相関検査を通し、未検証値をドメイン検証済みへ昇格する。"""
    return DomainValidatedRuleSnapshot(value)


def _validate_correlations(value: StructuralRuleSnapshot) -> None:
    """付録F-1の保存時相関と未裁定のコールド条件を判定する。"""
    if value.extension_limit is not None and (
        value.extension_limit < value.regulation_innings
    ):
        raise RuleSnapshotInvalid(RuleSnapshotFailure.CORRELATION)
    if value.tiebreak is not None and (
        value.tiebreak.start_inning <= value.regulation_innings
        or (
            value.extension_limit is not None
            and value.tiebreak.start_inning > value.extension_limit
        )
    ):
        raise RuleSnapshotInvalid(RuleSnapshotFailure.CORRELATION)
    if any(
        tier.start_inning > value.regulation_innings for tier in value.cold_conditions
    ):
        # FR-014の拒否例と付録F-1 DRAW-04の閉じた受理条件の裁定前。
        raise RuleSnapshotInvalid(RuleSnapshotFailure.UNRESOLVED)


def decode_applied_rules(value: object) -> DomainValidatedRuleSnapshot:
    """保存済みJSONBを形・値域・相関まで検証して読む。"""
    return validate_correlations(decode_structure(value))


def encode_applied_rules(value: DomainValidatedRuleSnapshot) -> dict[str, object]:
    """相関検証済み値だけを6-key JSONBへ変換する。

    Args:
        value: 相関検証済みの値。規則行の出所は別途確認する。

    Returns:
        新しい6-key JSONB値。DB保存成功は表さない。

    Raises:
        TypeError: 構造検証済みだけの値など、公開型以外を渡した場合。
        RuleSnapshotInvalid: 値が検証後に改ざんされた場合。
    """
    if type(value) is not DomainValidatedRuleSnapshot:
        raise TypeError("相関検証済みの適用規則が必要です")
    structural = value.structural
    _validate_structural(structural)
    _validate_correlations(structural)
    return {
        "ruleSetId": str(structural.rule_set_id),
        **_values_from_structural(structural),
    }
