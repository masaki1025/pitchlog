"""正規捕球三振を単一artifactへ一回渡す、両cursor専用の閉境界。"""

from __future__ import annotations

import json
from typing import Literal, TypeAlias

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from pitchlog.domainrt.first_pitch import (
    DecimalInteger,
    ErrorCode,
    Scoreboard,
    StatFlags,
    _Envelope,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.ordinary_pitch import _OptionalDifference, _OrdinaryFlags
from pitchlog.domainrt.terminal_pitch import (
    Runners,
    TerminalBoardDifference,
    TerminalSnapshot,
    TerminalStateDifference,
    _CountEffect,
)
from pitchlog.domainrt.terminal_pitch import (
    _AfterState as _TerminalAfterState,
)

Order: TypeAlias = Literal["1", "2", "3", "4", "5", "6", "7", "8", "9"]


class BattingOrderBySide(_Frozen):
    """readonly入力。値域・active相関の数学判定は唯一artifactが行う。"""

    away: DecimalInteger
    home: DecimalInteger


class StrikeoutSnapshot(TerminalSnapshot):
    """旧Snapshotを広げず、このvariantだけ両cursorを必須にする。"""

    batting_order_by_side: BattingOrderBySide = Field(alias="battingOrderBySide")


class _OrderPair(_Frozen):
    """変更したcursorの正準前後値。"""

    before: Order
    after: Order


class CursorDifference(_OptionalDifference):
    """省略と明示nullを区別し、二チーム以外を拒否する。"""

    away: _OrderPair | None = None
    home: _OrderPair | None = None


class StrikeoutDifference(_OptionalDifference):
    """旧履歴tailも保持する新履歴型。差分計算はPythonで行わない。"""

    state_fields: TerminalStateDifference = Field(alias="stateFields")
    scoreboard: TerminalBoardDifference
    stat_flags: StatFlags = Field(alias="statFlags")
    batting_order_by_side: CursorDifference | None = Field(
        default=None, alias="battingOrderBySide"
    )


class StrikeoutHistoryEntry(_Frozen):
    """確定プレイの全差分と23flagを写す。"""

    kind: Literal["confirmed-play"]
    difference: StrikeoutDifference


class _History(_Frozen):
    """履歴の空値を補完せず要求する。"""

    stack: tuple[StrikeoutHistoryEntry, ...]


class StrikeoutPitchRequest(_Frozen):
    """型の正しいscope外操作もartifactで非成功にする閉入力。"""

    event_kind: str = Field(alias="eventKind")
    result_id: str = Field(alias="resultId")
    pitch_event_kind: str = Field(alias="pitchEventKind")
    before: StrikeoutSnapshot
    history: _History


class _Out(_Frozen):
    """打者outだけの行き先。"""

    kind: Literal["out"]


class _OneOut(_Frozen):
    """正規捕球三振の打者1outだけを受け取る。"""

    count: Literal["1"]
    targets: tuple[Literal["batter"]]


class _StrikeoutFlags(_OrdinaryFlags):
    """SO-01/02の6true/17false。算式や期待lookupは持たない。"""

    innings_outs: Literal[True] = Field(alias="投球回算入アウト")
    strikeout_pitcher: Literal[True] = Field(alias="奪三振")
    plate_appearance: Literal[True] = Field(alias="打席")
    at_bat: Literal[True] = Field(alias="打数")
    strikeout_batter: Literal[True] = Field(alias="三振")


class _AfterState(_TerminalAfterState):
    """count reset/未終了を保持し、after占有はこの操作の全8値。"""

    runners: Runners = Field(alias="state.runners")


class _AfterOrders(BattingOrderBySide):
    """成功した両cursorは1..9の閉値。"""

    away: Order
    home: Order


class _After(_Frozen):
    """核の実afterと全投影/両cursor。値の補完・再計算はしない。"""

    state_fields: _AfterState = Field(alias="stateFields")
    scoreboard: Scoreboard
    batting_order_by_side: _AfterOrders = Field(alias="battingOrderBySide")


class _RunnerAdvance(_Frozen):
    """実在塁のholdと不在塁だけの外形。移動先は推測しない。"""

    modality: Literal["hold", "not-applicable"]
    destination: None


class _RunnerAdvances(_Frozen):
    """三塁分の保持効果を型として受け取る。"""

    first: _RunnerAdvance
    second: _RunnerAdvance
    third: _RunnerAdvance


class StrikeoutPitchValue(_Frozen):
    """全8比較面。入力に対する数学相関は単一artifactが所有する。"""

    count_effect: _CountEffect = Field(alias="countEffect")
    plate_appearance_ended: Literal[True] = Field(alias="plateAppearanceEnded")
    batter_destination: _Out = Field(alias="batterDestination")
    runner_default_advance: _RunnerAdvances = Field(alias="runnerDefaultAdvance")
    out_effect: _OneOut = Field(alias="outEffect")
    stat_flags: _StrikeoutFlags = Field(alias="statFlags")
    after: _After
    history_context: tuple[StrikeoutHistoryEntry, ...] = Field(
        alias="historyContext", min_length=1
    )

    @model_validator(mode="after")
    def _require_cursor_head(self) -> StrikeoutPitchValue:
        """新headの必須cursor差分だけを検査し、過去tailを再計算しない。"""
        cursors = self.history_context[0].difference.batting_order_by_side
        if cursors is None or not cursors.model_fields_set:
            raise ValueError("新三振headのcursor差分が必要")
        return self


class StrikeoutPitchSuccess(_Envelope):
    """数学成功。T2/記録権/保存/画面成功の代用にしない。"""

    ok: Literal[True]
    value: StrikeoutPitchValue


class _Error(_Frozen):
    """既4codeだけの失敗。"""

    code: ErrorCode


class StrikeoutPitchFailure(_Envelope):
    """未対応操作を成功へfallbackしない。"""

    ok: Literal[False]
    error: _Error


StrikeoutPitchResponse: TypeAlias = StrikeoutPitchSuccess | StrikeoutPitchFailure
_RESPONSE = TypeAdapter(StrikeoutPitchResponse)


class StrikeoutPitchProtocolError(RuntimeError):
    """壊れたartifact応答を閉じて拒否する。"""


def decode_strikeout_pitch_response(raw: str) -> StrikeoutPitchResponse:
    """重複/非有限値/alias/coercion/余剰/欠落を拒否し全wire値を保持する。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        parsed = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        response = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        dumped = response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if json.dumps(parsed, sort_keys=True) != json.dumps(dumped, sort_keys=True):
            raise ValueError("応答の構造/JSON型が変わった")
        return response
    except (ValueError, TypeError, ValidationError):
        raise StrikeoutPitchProtocolError("三振応答が固定ABIに適合しません") from None


def evaluate_strikeout_pitch(request: StrikeoutPitchRequest) -> StrikeoutPitchResponse:
    """実型を再検証し、固定製品hostを一回だけ呼ぶ。Python計算は持たない。"""
    if type(request) is not StrikeoutPitchRequest:
        raise TypeError("StrikeoutPitchRequestの実型が必要です")
    validated = StrikeoutPitchRequest.model_validate_json(
        request.model_dump_json(by_alias=True, exclude_unset=True),
        by_alias=True,
        by_name=False,
    )
    with open_domain_host() as host:
        return decode_strikeout_pitch_response(
            host.call(
                "deriveStrikeoutPitch",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
