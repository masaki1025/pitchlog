"""受理済み無走者BB/HBPを唯一のTS artifactへ一度だけ渡す閉境界。"""

from __future__ import annotations

import json
from typing import Annotated, Literal, TypeAlias

from pydantic import AfterValidator, Field, TypeAdapter, ValidationError

from pitchlog.domainrt.first_pitch import (
    DecimalInteger,
    ErrorCode,
    RunnerAdvances,
    Score,
    Scoreboard,
    StateFields,
    StatFlags,
    _Envelope,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.ordinary_pitch import (
    HistoryScoreboardDifference as _BoardDifference,
)
from pitchlog.domainrt.ordinary_pitch import (
    HistoryStateDifference as _StateDifference,
)
from pitchlog.domainrt.ordinary_pitch import (
    _OrdinaryFlags,
)


def _positive(value: str) -> str:
    """算術を行わず、正整数の境界表現だけを検査する。"""
    if value == "0":
        raise ValueError("正整数文字列が必要")
    return value


PositiveInteger: TypeAlias = Annotated[DecimalInteger, AfterValidator(_positive)]
Runners: TypeAlias = Literal[
    "empty",
    "first",
    "second",
    "third",
    "first-second",
    "first-third",
    "second-third",
    "first-second-third",
]


class TerminalStateFields(StateFields):
    """旧ABIのloadedを正準語彙へ黙って読み替えない新入力。"""

    runners: Runners = Field(alias="state.runners")
    inning: PositiveInteger = Field(alias="state.inning")


class TerminalSnapshot(_Frozen):
    """入力の実状態と投影。scope/関係条件はTS核が判断する。"""

    state_fields: TerminalStateFields = Field(alias="stateFields")
    scoreboard: Scoreboard


class _IntegerPair(_Frozen):
    """正準非負整数の履歴前後値。"""

    before: DecimalInteger
    after: DecimalInteger


class _PositivePair(_Frozen):
    """回の正整数前後値。"""

    before: PositiveInteger
    after: PositiveInteger


class _RunnersPair(_Frozen):
    """新ABIの正準占有語彙だけを受け取る。"""

    before: Runners
    after: Runners


class _ScorePair(_Frozen):
    """得点の非負整数前後値。"""

    before: Score
    after: Score


class TerminalStateDifference(_StateDifference):
    """履歴構造を共有し、新契約の整数/占有表現へ限定する。"""

    strikes: _IntegerPair | None = Field(default=None, alias="state.count.strikes")
    balls: _IntegerPair | None = Field(default=None, alias="state.count.balls")
    outs: _IntegerPair | None = Field(default=None, alias="state.outs")
    runners: _RunnersPair | None = Field(default=None, alias="state.runners")
    batting_order: _IntegerPair | None = Field(default=None, alias="state.battingOrder")
    inning: _PositivePair | None = Field(default=None, alias="state.inning")
    score: _ScorePair | None = Field(default=None, alias="state.score")


class TerminalBoardDifference(_BoardDifference):
    """全投影差分を非負整数表現で保持する。"""

    inning_scores: _ScorePair | None = Field(default=None, alias="inningScores")
    hits: _IntegerPair | None = None
    errors: _IntegerPair | None = None
    strikeouts: _IntegerPair | None = None
    walks: _IntegerPair | None = None


class TerminalDifference(_Frozen):
    """全23flagと省略を保った差分。再計算しない。"""

    state_fields: TerminalStateDifference = Field(alias="stateFields")
    scoreboard: TerminalBoardDifference
    stat_flags: StatFlags = Field(alias="statFlags")


class TerminalHistoryEntry(_Frozen):
    """確認済み履歴の構造。真正性は別境界が所有する。"""

    kind: Literal["confirmed-play"]
    difference: TerminalDifference


class TerminalHistory(_Frozen):
    """必須の既履歴stack。既定空値を生成しない。"""

    stack: tuple[TerminalHistoryEntry, ...]


class TerminalPitchRequest(_Frozen):
    """型の正しい範囲外操作もartifactへ渡して非成功にする。"""

    event_kind: str = Field(alias="eventKind")
    result_id: str = Field(alias="resultId")
    pitch_event_kind: str = Field(alias="pitchEventKind")
    before: TerminalSnapshot
    history: TerminalHistory


class _Reset(_Frozen):
    """value補完を許さないreset外形。"""

    kind: Literal["reset"]


class _CountEffect(_Frozen):
    """両カウントresetの閉効果。"""

    strikes: _Reset
    balls: _Reset


class _Reach(_Frozen):
    """無走者操作の一塁到達外形。"""

    kind: Literal["reach"]
    base: Literal["1"]


class _ZeroOut(_Frozen):
    """アウト0・空対象の閉効果。"""

    count: Literal["0"]
    targets: tuple[()]


class _WalkFlags(_OrdinaryFlags):
    """既23flagの四球パターン。計算や結果lookupは行わない。"""

    walk_pitcher: Literal[True] = Field(alias="与四球")
    plate_appearance: Literal[True] = Field(alias="打席")
    walk: Literal[True] = Field(alias="四球")


class _HitByPitchFlags(_OrdinaryFlags):
    """既23flagの死球パターン。"""

    hit_by_pitch_pitcher: Literal[True] = Field(alias="与死球")
    plate_appearance: Literal[True] = Field(alias="打席")
    hit_by_pitch: Literal[True] = Field(alias="死球")


class _AfterState(TerminalStateFields):
    """成功応答に許された有限状態軸。"""

    strikes: Literal["0"] = Field(alias="state.count.strikes")
    balls: Literal["0"] = Field(alias="state.count.balls")
    outs: Literal["0", "1", "2"] = Field(alias="state.outs")
    runners: Literal["first"] = Field(alias="state.runners")
    batting_order: Literal["1", "2", "3", "4", "5", "6", "7", "8", "9"] = Field(
        alias="state.battingOrder"
    )
    game_ended: Literal[False] = Field(alias="state.gameEnded")


class _After(_Frozen):
    """核の実出力を保持する状態/投影。"""

    state_fields: _AfterState = Field(alias="stateFields")
    scoreboard: Scoreboard


class TerminalPitchValue(_Frozen):
    """閉契約8member。Pythonは履歴・カウント・打順を計算しない。"""

    count_effect: _CountEffect = Field(alias="countEffect")
    plate_appearance_ended: Literal[True] = Field(alias="plateAppearanceEnded")
    batter_destination: _Reach = Field(alias="batterDestination")
    runner_default_advance: RunnerAdvances = Field(alias="runnerDefaultAdvance")
    out_effect: _ZeroOut = Field(alias="outEffect")
    stat_flags: _WalkFlags | _HitByPitchFlags = Field(alias="statFlags")
    after: _After
    history_context: tuple[TerminalHistoryEntry, ...] = Field(
        alias="historyContext", min_length=1
    )


class TerminalPitchSuccess(_Envelope):
    """数学成功。T2/認可/保存成功へ読み替えない。"""

    ok: Literal[True]
    value: TerminalPitchValue


class _Error(_Frozen):
    """既4codeだけを受け付ける。"""

    code: ErrorCode


class TerminalPitchFailure(_Envelope):
    """未対応操作を含む閉じた非成功。"""

    ok: Literal[False]
    error: _Error


TerminalPitchResponse: TypeAlias = TerminalPitchSuccess | TerminalPitchFailure
_RESPONSE = TypeAdapter(TerminalPitchResponse)


class TerminalPitchProtocolError(RuntimeError):
    """壊れた応答を成功へ補完せず拒否する。"""


def decode_terminal_pitch_response(raw: str) -> TerminalPitchResponse:
    """重複/非有限値/余剰/型変換/欠落を拒否して全wire値を写す。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        parsed = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        result = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        dumped = result.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if json.dumps(parsed, sort_keys=True) != json.dumps(dumped, sort_keys=True):
            raise ValueError("厳密なwire構造/型が一致しない")
        return result
    except (ValueError, ValidationError, TypeError):
        raise TerminalPitchProtocolError(
            "打席終了応答が固定ABIに適合しません"
        ) from None


def evaluate_terminal_pitch(request: TerminalPitchRequest) -> TerminalPitchResponse:
    """固定製品hostを一回だけ呼び、別計算も期待lookupも置かない。"""
    if type(request) is not TerminalPitchRequest:
        raise TypeError("TerminalPitchRequestの実型が必要です")
    # 再検証でも省略された任意差分をnullへ補完しない。
    validated = TerminalPitchRequest.model_validate_json(
        request.model_dump_json(by_alias=True, exclude_unset=True),
        by_alias=True,
        by_name=False,
    )
    with open_domain_host() as host:
        return decode_terminal_pitch_response(
            host.call(
                "deriveTerminalPitch",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
