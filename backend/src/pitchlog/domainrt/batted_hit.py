"""無走者4安打を唯一artifactへ一回渡す閉境界。計算式は保持しない。"""

from __future__ import annotations

import json
from typing import Literal, Self, TypeAlias

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from pitchlog.domainrt.first_pitch import (
    ErrorCode,
    Scoreboard,
    _Envelope,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.ordinary_pitch import _OrdinaryFlags
from pitchlog.domainrt.strikeout_pitch import (
    StrikeoutHistoryEntry,
    StrikeoutSnapshot,
    _AfterOrders,
    _AfterState,
)
from pitchlog.domainrt.terminal_pitch import _CountEffect

BattedHitResultId: TypeAlias = Literal[
    "batting-result.single",
    "batting-result.double",
    "batting-result.triple",
    "batting-result.home-run",
]


class _History(_Frozen):
    """既履歴tailを必須入力とし空値を補完しない。"""

    stack: tuple[StrikeoutHistoryEntry, ...]


class BattedHitRequest(_Frozen):
    """確定済み観測の有限タグと既正準状態を写す。保存資格ではない。"""

    event_kind: Literal["batting-result"] = Field(alias="eventKind")
    result_id: BattedHitResultId = Field(alias="resultId")
    pitch_event_kind: Literal["pitch-event"] = Field(alias="pitchEventKind")
    official_scoring_payload: Literal["no-error"] = Field(
        alias="officialScoringPayload"
    )
    interference_ruling: Literal["not-required"] = Field(alias="interferenceRuling")
    runner_advance_overrides: Literal["not-applied"] = Field(
        alias="runnerAdvanceOverrides"
    )
    third_out_observation: Literal["none"] = Field(alias="thirdOutObservation")
    before: StrikeoutSnapshot
    history: _History


class _HitFlags(_OrdinaryFlags):
    """非HRの6true/17falseを型として検査する。"""

    hit_allowed: Literal[True] = Field(alias="被安打")
    plate_appearance: Literal[True] = Field(alias="打席")
    at_bat: Literal[True] = Field(alias="打数")
    hit: Literal[True] = Field(alias="安打")
    total_bases: Literal[True] = Field(alias="塁打")


class _HomeRunFlags(_HitFlags):
    """無走者HRの追加5trueを型として検査する。"""

    home_run_allowed: Literal[True] = Field(alias="被本塁打")
    home_run: Literal[True] = Field(alias="本塁打")
    run_allowed: Literal[True] = Field(alias="失点")
    run: Literal[True] = Field(alias="得点")
    rbi: Literal[True] = Field(alias="打点")


class _AbsentRunner(_Frozen):
    """beforeの不在走者。打者の到達塁を混入させない。"""

    modality: Literal["not-applicable"]
    destination: None


class _RunnerAdvances(_Frozen):
    """不在の三塁をすべて必須にする。"""

    first: _AbsentRunner
    second: _AbsentRunner
    third: _AbsentRunner


class _NoOut(_Frozen):
    """併発アウトを許さない閉効果。"""

    count: Literal["0"]
    targets: tuple[()]


class _First(_Frozen):
    """単打の打者到達。"""

    kind: Literal["reach"]
    base: Literal["1"]


class _Second(_Frozen):
    """二塁打の打者到達。"""

    kind: Literal["reach"]
    base: Literal["2"]


class _Third(_Frozen):
    """三塁打の打者到達。"""

    kind: Literal["reach"]
    base: Literal["3"]


class _Score(_Frozen):
    """本塁打はbaseを追加しない。"""

    kind: Literal["score"]


class _FirstState(_AfterState):
    """単打の受信after型。数学を再計算しない。"""

    runners: Literal["first"] = Field(alias="state.runners")
    tiebreak_active: Literal[False] = Field(alias="state.tiebreakActive")


class _SecondState(_FirstState):
    """二塁打の受信after型。"""

    runners: Literal["second"] = Field(alias="state.runners")


class _ThirdState(_FirstState):
    """三塁打の受信after型。"""

    runners: Literal["third"] = Field(alias="state.runners")


class _EmptyState(_FirstState):
    """本塁打の受信after型。"""

    runners: Literal["empty"] = Field(alias="state.runners")


class _FirstAfter(_Frozen):
    """単打の全投影と両cursor。"""

    state_fields: _FirstState = Field(alias="stateFields")
    scoreboard: Scoreboard
    batting_order_by_side: _AfterOrders = Field(alias="battingOrderBySide")


class _SecondAfter(_FirstAfter):
    """二塁打の全投影。"""

    state_fields: _SecondState = Field(alias="stateFields")


class _ThirdAfter(_FirstAfter):
    """三塁打の全投影。"""

    state_fields: _ThirdState = Field(alias="stateFields")


class _EmptyAfter(_FirstAfter):
    """本塁打の全投影。"""

    state_fields: _EmptyState = Field(alias="stateFields")


class _Value(_Frozen):
    """新headの必須差分と既tailを型だけで保持する。"""

    count_effect: _CountEffect = Field(alias="countEffect")
    plate_appearance_ended: Literal[True] = Field(alias="plateAppearanceEnded")
    runner_default_advance: _RunnerAdvances = Field(alias="runnerDefaultAdvance")
    out_effect: _NoOut = Field(alias="outEffect")
    stat_flags: _HitFlags = Field(alias="statFlags")
    history_context: tuple[StrikeoutHistoryEntry, ...] = Field(
        alias="historyContext", min_length=1
    )

    @model_validator(mode="after")
    def _require_cursor_head(self) -> Self:
        """変更された新head cursorを要求し、過去履歴を再計算しない。"""
        cursor = self.history_context[0].difference.batting_order_by_side
        if cursor is None or not cursor.model_fields_set:
            raise ValueError("打球headの非空cursor差分が必要")
        head_flags = self.history_context[0].difference.stat_flags
        if head_flags.model_dump(by_alias=True) != self.stat_flags.model_dump(
            by_alias=True
        ):
            raise ValueError("打球headとvalueの23flagが不一致")
        return self


class _SingleValue(_Value):
    """単打の閉応答。"""

    batter_destination: _First = Field(alias="batterDestination")
    after: _FirstAfter


class _DoubleValue(_Value):
    """二塁打の閉応答。"""

    batter_destination: _Second = Field(alias="batterDestination")
    after: _SecondAfter


class _TripleValue(_Value):
    """三塁打の閉応答。"""

    batter_destination: _Third = Field(alias="batterDestination")
    after: _ThirdAfter


class _HomeRunValue(_Value):
    """本塁打の閉応答。"""

    batter_destination: _Score = Field(alias="batterDestination")
    stat_flags: _HomeRunFlags = Field(alias="statFlags")
    after: _EmptyAfter


class BattedHitSuccess(_Envelope):
    """実artifactによる数学成功。保存/ACKを意味しない。"""

    ok: Literal[True]
    value: _SingleValue | _DoubleValue | _TripleValue | _HomeRunValue


class _Error(_Frozen):
    """既4codeだけを許す。"""

    code: ErrorCode


class BattedHitFailure(_Envelope):
    """閉じた非成功。"""

    ok: Literal[False]
    error: _Error


BattedHitResponse: TypeAlias = BattedHitSuccess | BattedHitFailure
_RESPONSE = TypeAdapter(BattedHitResponse)


class BattedHitProtocolError(RuntimeError):
    """壊れた応答を成功へ補完できないことを表す。"""


def decode_batted_hit_response(raw: str) -> BattedHitResponse:
    """重複/非有限/余剰/型変換/欠落/省略差分補完を拒否する。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        parsed = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        response = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        dumped = response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if json.dumps(parsed, sort_keys=True) != json.dumps(dumped, sort_keys=True):
            raise ValueError("応答のwire構造またはJSON型が変わった")
        return response
    except (ValueError, TypeError, ValidationError):
        raise BattedHitProtocolError("打球応答が固定ABIに適合しません") from None


def evaluate_batted_hit(request: BattedHitRequest) -> BattedHitResponse:
    """固定製品hostを一回だけ呼び、別計算・期待lookupを行わない。"""
    if type(request) is not BattedHitRequest:
        raise TypeError("BattedHitRequestの実型が必要です")
    validated = BattedHitRequest.model_validate_json(
        request.model_dump_json(by_alias=True, exclude_unset=True),
        by_alias=True,
        by_name=False,
    )
    with open_domain_host() as host:
        return decode_batted_hit_response(
            host.call(
                "deriveBattedHit",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
