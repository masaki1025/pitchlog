"""初球T1/T2を同じ固定artifactで一度評価する閉じたPython境界。

状態・終了条件は計算せず、partial T1を成功や保存許可へ変換しない。
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Self, TypeAlias

from pydantic import Field, TypeAdapter, ValidationError

from pitchlog.domainrt.first_pitch import (
    DecimalInteger,
    FirstPitchFailure,
    FirstPitchProtocolError,
    FirstPitchRequest,
    FirstPitchValue,
    _Envelope,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.host import open_domain_host

PositiveRuleInteger: TypeAlias = Annotated[
    DecimalInteger, Field(pattern=r"^[1-9][0-9]?$")
]


def _closed_wire_error() -> ValidationError:
    """元の入力を保持せず閉modelの境界エラーを返す。"""
    return ValidationError.from_exception_data(
        "CombinedRequest",
        [
            {
                "type": "value_error",
                "loc": (),
                "input": None,
                "ctx": {"error": ValueError("閉wire形又はmodel memberが不一致")},
            }
        ],
    )


def _check_frozen_members(value: object) -> None:
    """強制追加aliasや欠損を入れ子のmodel/tupleで検査する。意味は計算しない。"""
    if isinstance(value, _Frozen):
        if set(vars(value)) != set(type(value).model_fields) or value.model_extra:
            raise _closed_wire_error()
        for child in vars(value).values():
            _check_frozen_members(child)
    elif type(value) is tuple:
        for child in value:
            _check_frozen_members(child)


class _WireFrozen(_Frozen):
    """既不変基底を保ち、新しいwire DTOのJSON読取だけを厳密にする。"""

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        **kwargs: Any,
    ) -> Self:
        """既JSON拒否を再利用し、raw要求の別名/余剰の黙った正規化も拒否する。"""
        try:
            wire = json.loads(
                json_data,
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
        except (ValueError, TypeError):
            raise _closed_wire_error() from None
        result = super().model_validate_json(json_data, **kwargs)
        if result.model_dump(mode="json", by_alias=True) != wire:
            raise _closed_wire_error()
        return result


class ColdTierWire(_WireFrozen):
    """保存規則の段階形。正整数1〜99の表現だけを検証する。"""

    point_difference: PositiveRuleInteger = Field(alias="pointDifference")
    start_inning: PositiveRuleInteger = Field(alias="startInning")


class TiebreakWire(_WireFrozen):
    """保存TBの構造。適用可能性はartifactが判定する。"""

    start_inning: PositiveRuleInteger = Field(alias="startInning")
    runner_placement: Annotated[str, Field(min_length=1)] = Field(
        alias="runnerPlacement"
    )
    leadoff_rule: Annotated[str, Field(min_length=1)] = Field(alias="leadoffRule")


class SavedRuleWire(_WireFrozen):
    """受理済みschemaの保存規則wire。保存元の真正性を表さない。"""

    regulation_innings: PositiveRuleInteger = Field(alias="regulationInnings")
    cold_conditions: Annotated[tuple[ColdTierWire, ...], Field(max_length=16)] = Field(
        alias="coldConditions"
    )
    extension_limit: PositiveRuleInteger | None = Field(alias="extensionLimit")
    tiebreak: TiebreakWire | None
    dh: bool


class CombinedRequest(_WireFrozen):
    """既T1要求と保存規則を持つ新操作だけの閉要求。"""

    t1: FirstPitchRequest
    rules: SavedRuleWire


class _Regulation(_Frozen):
    """非該当根拠の固定観測形。判定式を持たない。"""

    kind: Literal["before-regulation-completion"]
    observed_inning: Literal["1"]
    observed_half: Literal["top"]


class _Regulation7(_Regulation):
    """規定7回の根拠形。"""

    regulation_innings: Literal["7"]


class _Regulation9(_Regulation):
    """規定9回の根拠形。"""

    regulation_innings: Literal["9"]


class _ColdBasis(_Frozen):
    """コールド設定なしの根拠tag。"""

    kind: Literal["no-configured-cold-condition"]


class _ExtraBasis(_Frozen):
    """延長境界前のtag。"""

    kind: Literal["before-extra-inning-boundary"]


class _ExtraNull(_ExtraBasis):
    """上限なしの根拠形。"""

    configured_extension_limit: None


class _Extra9(_ExtraBasis):
    """上限9回の根拠形。"""

    configured_extension_limit: Literal["9"]


class _WalkOffBasis(_Frozen):
    """表かつ得点不変の根拠tag。"""

    kind: Literal["top-half-without-score-change"]


class _Basis(_Frozen):
    """全4家族を省略しない根拠の共通形。"""

    cold: _ColdBasis
    walk_off: _WalkOffBasis


class _Basis7Null(_Basis):
    """schemaのR7/Lnull variant。"""

    regulation: _Regulation7
    extra_and_draw: _ExtraNull


class _Basis9Null(_Basis):
    """schemaのR9/Lnull variant。"""

    regulation: _Regulation9
    extra_and_draw: _ExtraNull


class _Basis9Limit9(_Basis):
    """schemaのR9/L9 variant。"""

    regulation: _Regulation9
    extra_and_draw: _Extra9


class _NoEndCore(_Frozen):
    """評価済み非該当の外形。既gameEndDecisionとは別の型。"""

    kind: Literal["evaluated-no-end-condition"]
    evaluation_point: Literal["post-play"]


class _NoEnd7Null(_NoEndCore):
    """規定7回/上限なしの閉variant。"""

    basis: _Basis7Null


class _NoEnd9Null(_NoEndCore):
    """規定9回/上限なしの閉variant。"""

    basis: _Basis9Null


class _NoEnd9Limit9(_NoEndCore):
    """規定9回/上限9回の閉variant。"""

    basis: _Basis9Limit9


T2NoEndCore: TypeAlias = _NoEnd7Null | _NoEnd9Null | _NoEnd9Limit9


class T2NotEvaluatedCore(_Frozen):
    """未評価の閉tag。続行許可やfalse decisionではない。"""

    kind: Literal["not-evaluated"]
    reason: Literal["input-not-in-closed-unit", "evaluation-unavailable"]


class CombinedValue(_Frozen):
    """同じartifactが両評価を完了した値。"""

    t1: FirstPitchValue
    t2: T2NoEndCore


class CombinedSuccess(_Envelope):
    """両評価済みの場合だけの数学接続成功。保存ACKではない。"""

    ok: Literal[True]
    value: CombinedValue


class PartialValue(_Frozen):
    """T1だけのpartial値。成功の代用にしない。"""

    t1: FirstPitchValue
    t2: T2NotEvaluatedCore


class _T2Error(_Frozen):
    """新操作だけのlocal未評価code。既T1の4codeへ加えない。"""

    code: Literal["T2_NOT_EVALUATED"]


class T2NotEvaluatedResponse(_Envelope):
    """partialは常にok:false。"""

    ok: Literal[False]
    error: _T2Error
    value: PartialValue


CombinedResponse: TypeAlias = (
    CombinedSuccess | FirstPitchFailure | T2NotEvaluatedResponse
)
_RESPONSE = TypeAdapter(CombinedResponse)


def decode_combined_response(raw: str) -> CombinedResponse:
    """既JSON拒否とalias-only検査を使って閉応答へ写す。

    Args:
        raw: 固定hostから受け取るJSON文字列。

    Returns:
        両評価成功、既T1非成功、又はT2未評価の非成功。

    Raises:
        FirstPitchProtocolError: 未知/壊れた応答を受けた場合。
    """
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        decoded = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        # 再利用modelが別名を正規化しても、余剰keyの黙認を許さない。
        if decoded.model_dump(mode="json", by_alias=True) != wire:
            raise ValueError("wireのkey又は表現が不一致")
        return decoded
    except (ValueError, ValidationError, TypeError):
        raise FirstPitchProtocolError("初球T1/T2応答が固定ABIに適合しません") from None


def evaluate_first_pitch_with_continuation(
    request: CombinedRequest,
) -> CombinedResponse:
    """既固定host/版/hash/lifetimeで新操作を一度だけ呼ぶ。

    Args:
        request: 閉要求。真正source・認可・記録権の証明ではない。

    Returns:
        型付きの両評価成功又は非成功。partialを成功に補完しない。

    Raises:
        TypeError: 要求が指定DTOの実型でない場合。
        ValidationError: 強制変更等で入れ子の型が壊れている場合。
        FirstPitchProtocolError: 応答が固定ABIと不一致の場合。
        DomainRuntimeError: 既hostの起動/境界/実行故障。
    """
    if type(request) is not CombinedRequest:
        raise TypeError("CombinedRequestの実型が必要です")
    _check_frozen_members(request)
    validated = CombinedRequest.model_validate(request)
    with open_domain_host() as host:
        return decode_combined_response(
            host.call(
                "deriveFirstPitchWithContinuation",
                validated.model_dump_json(by_alias=True),
            )
        )
