"""通常33投球を単一TS artifactへ渡す閉じた型付き境界。

Pythonはカウント・差分・履歴pushを計算しない。履歴は構造だけを検証し、
過去計算の真正性、認可、同期、保存を証明したとは扱わない。
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import (
    AfterValidator,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from pitchlog.domainrt.first_pitch import (
    BatterDestination,
    DeltaCount,
    ErrorCode,
    OutEffect,
    RunnerAdvances,
    Score,
    StateFields,
    StateSnapshot,
    StatFlags,
    UnchangedCount,
    _Envelope,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.host import open_domain_host

_SIGNED = re.compile(r"(?:0|[1-9][0-9]*|-[1-9][0-9]*)", re.ASCII)


def _canonical_signed(value: str) -> str:
    """履歴の既契約にある符号付きcanonical表現だけを受け付ける。"""
    if _SIGNED.fullmatch(value) is None:
        raise ValueError("canonicalな十進整数文字列が必要")
    return value


SignedInteger: TypeAlias = Annotated[str, AfterValidator(_canonical_signed)]


class _SignedScore(_Frozen):
    """履歴の得点前後値。意味の補完や再計算は行わない。"""

    home: SignedInteger
    away: SignedInteger


class _IntegerPair(_Frozen):
    """履歴の整数前後値。"""

    before: SignedInteger
    after: SignedInteger


class _HalfPair(_Frozen):
    """履歴の攻守前後値。"""

    before: Literal["top", "bottom"]
    after: Literal["top", "bottom"]


class _RunnersPair(_Frozen):
    """履歴の塁占有前後値。"""

    before: Literal[
        "empty",
        "first",
        "second",
        "third",
        "first-second",
        "first-third",
        "second-third",
        "loaded",
    ]
    after: Literal[
        "empty",
        "first",
        "second",
        "third",
        "first-second",
        "first-third",
        "second-third",
        "loaded",
    ]


class _BooleanPair(_Frozen):
    """数値から暗黙変換しない真理値前後値。"""

    before: bool
    after: bool


class _ScorePair(_Frozen):
    """得点組の前後値。"""

    before: _SignedScore
    after: _SignedScore


class _OptionalDifference(_Frozen):
    """省略欄は省略として保持し、明示nullは受理しない。"""

    @field_validator("*", mode="before")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        """任意差分欄のnull補完を拒否する。"""
        if value is None:
            raise ValueError("差分欄にnullは指定できない")
        return value


class HistoryStateDifference(_OptionalDifference):
    """契約の全状態差分欄だけを保持する。"""

    half: _HalfPair | None = Field(default=None, alias="state.half")
    strikes: _IntegerPair | None = Field(default=None, alias="state.count.strikes")
    balls: _IntegerPair | None = Field(default=None, alias="state.count.balls")
    outs: _IntegerPair | None = Field(default=None, alias="state.outs")
    runners: _RunnersPair | None = Field(default=None, alias="state.runners")
    batting_order: _IntegerPair | None = Field(default=None, alias="state.battingOrder")
    tiebreak_active: _BooleanPair | None = Field(
        default=None, alias="state.tiebreakActive"
    )
    game_ended: _BooleanPair | None = Field(default=None, alias="state.gameEnded")
    inning: _IntegerPair | None = Field(default=None, alias="state.inning")
    score: _ScorePair | None = Field(default=None, alias="state.score")


class HistoryScoreboardDifference(_OptionalDifference):
    """契約の全投影差分欄だけを保持する。"""

    inning_scores: _ScorePair | None = Field(default=None, alias="inningScores")
    hits: _IntegerPair | None = None
    errors: _IntegerPair | None = None
    strikeouts: _IntegerPair | None = None
    walks: _IntegerPair | None = None


class HistoryDifference(_Frozen):
    """入力・出力に共通の閉履歴差分。"""

    state_fields: HistoryStateDifference = Field(alias="stateFields")
    scoreboard: HistoryScoreboardDifference
    stat_flags: StatFlags = Field(alias="statFlags")


class HistoryEntry(_Frozen):
    """正式confirmed-playだけを保持する。"""

    kind: Literal["confirmed-play"]
    difference: HistoryDifference


class History(_Frozen):
    """既定値を持たない必須stack。"""

    stack: tuple[HistoryEntry, ...]


class OrdinaryPitchRequest(_Frozen):
    """型が正しいscope外要求もTSで非成功にするための閉入力。"""

    event_kind: str = Field(alias="eventKind")
    result_id: str = Field(alias="resultId")
    pitch_event_kind: str = Field(alias="pitchEventKind")
    before: StateSnapshot
    history: History


class _OneDelta(DeltaCount):
    """今回受理済みの差分値1だけを受け取る。"""

    value: Literal["1"]


class _ZeroOut(OutEffect):
    """通常投球のアウト不変を閉じる。"""

    count: Literal["0"]


class _OrdinaryFlags(StatFlags):
    """通常投球で受理済みの23flagの値を検査する。"""

    innings_outs: Literal[False] = Field(alias="投球回算入アウト")
    pitch: Literal[True] = Field(alias="投球数")
    strikeout_pitcher: Literal[False] = Field(alias="奪三振")
    walk_pitcher: Literal[False] = Field(alias="与四球")
    hit_by_pitch_pitcher: Literal[False] = Field(alias="与死球")
    hit_allowed: Literal[False] = Field(alias="被安打")
    home_run_allowed: Literal[False] = Field(alias="被本塁打")
    run_allowed: Literal[False] = Field(alias="失点")
    error: Literal[False] = Field(alias="失策")
    plate_appearance: Literal[False] = Field(alias="打席")
    at_bat: Literal[False] = Field(alias="打数")
    hit: Literal[False] = Field(alias="安打")
    home_run: Literal[False] = Field(alias="本塁打")
    total_bases: Literal[False] = Field(alias="塁打")
    sacrifice_bunt: Literal[False] = Field(alias="犠打")
    sacrifice_fly: Literal[False] = Field(alias="犠飛")
    walk: Literal[False] = Field(alias="四球")
    hit_by_pitch: Literal[False] = Field(alias="死球")
    strikeout_batter: Literal[False] = Field(alias="三振")
    batting_interference: Literal[False] = Field(alias="打撃妨害出塁")
    runner_interference: Literal[False] = Field(alias="走塁妨害出塁")
    run: Literal[False] = Field(alias="得点")
    rbi: Literal[False] = Field(alias="打点")


class _ZeroScore(Score):
    """通常投球応答の不変得点。"""

    home: Literal["0"]
    away: Literal["0"]


class _OrdinaryAfterState(StateFields):
    """今回の狭い操作単位の応答範囲だけを受け取る。"""

    half: Literal["top"] = Field(alias="state.half")
    strikes: Literal["0", "1", "2"] = Field(alias="state.count.strikes")
    balls: Literal["0", "1", "2", "3"] = Field(alias="state.count.balls")
    outs: Literal["0"] = Field(alias="state.outs")
    runners: Literal["empty"] = Field(alias="state.runners")
    batting_order: Literal["1"] = Field(alias="state.battingOrder")
    tiebreak_active: Literal[False] = Field(alias="state.tiebreakActive")
    game_ended: Literal[False] = Field(alias="state.gameEnded")
    inning: Literal["1"] = Field(alias="state.inning")
    score: _ZeroScore = Field(alias="state.score")


class _ZeroBoard(_Frozen):
    """今回操作が変更しない投影の応答値。"""

    inning_scores: _ZeroScore = Field(alias="inningScores")
    hits: Literal["0"]
    errors: Literal["0"]
    strikeouts: Literal["0"]
    walks: Literal["0"]


class _OrdinaryAfter(_Frozen):
    """通常投球の閉じた状態・投影。"""

    state_fields: _OrdinaryAfterState = Field(alias="stateFields")
    scoreboard: _ZeroBoard


class _BallEffect(_Frozen):
    """ballの閉効果。"""

    strikes: UnchangedCount
    balls: _OneDelta


class _StrikeEffect(_Frozen):
    """strikeの閉効果。"""

    strikes: _OneDelta
    balls: UnchangedCount


class OrdinaryPitchValue(_Frozen):
    """数学核が返した8memberを保持し、履歴を追加計算しない。"""

    count_effect: _BallEffect | _StrikeEffect = Field(alias="countEffect")
    plate_appearance_ended: Literal[False] = Field(alias="plateAppearanceEnded")
    batter_destination: BatterDestination = Field(alias="batterDestination")
    runner_default_advance: RunnerAdvances = Field(alias="runnerDefaultAdvance")
    out_effect: _ZeroOut = Field(alias="outEffect")
    stat_flags: _OrdinaryFlags = Field(alias="statFlags")
    after: _OrdinaryAfter
    history_context: tuple[HistoryEntry, ...] = Field(
        alias="historyContext", min_length=1
    )

    @model_validator(mode="after")
    def _closed_response_branch(self) -> Self:
        """効果・先頭差分の閉schemaだけを照合し、値を計算しない。"""
        head = self.history_context[0].difference
        state = head.state_fields.model_dump(by_alias=True, exclude_unset=True)
        board = head.scoreboard.model_dump(by_alias=True, exclude_unset=True)
        _OrdinaryFlags.model_validate(head.stat_flags.model_dump(by_alias=True))
        if board:
            raise ValueError("通常投球の先頭投影差分は空が必要")
        if isinstance(self.count_effect, _BallEffect):
            if set(state) != {
                "state.count.balls"
            } or self.after.state_fields.balls not in {"1", "2", "3"}:
                raise ValueError("ball応答の閉schemaと不一致")
        elif set(state) != {
            "state.count.strikes"
        } or self.after.state_fields.strikes not in {"1", "2"}:
            raise ValueError("strike応答の閉schemaと不一致")
        return self


class OrdinaryPitchSuccess(_Envelope):
    """数学成功だけを示し保存ACKには使用しない。"""

    ok: Literal[True]
    value: OrdinaryPitchValue


class _Error(_Frozen):
    """旧4code以外を拒否する。"""

    code: ErrorCode


class OrdinaryPitchFailure(_Envelope):
    """既4codeの非成功。"""

    ok: Literal[False]
    error: _Error


OrdinaryPitchResponse: TypeAlias = OrdinaryPitchSuccess | OrdinaryPitchFailure
_RESPONSE = TypeAdapter(OrdinaryPitchResponse)


class OrdinaryPitchProtocolError(RuntimeError):
    """壊れた応答を成功補完せず拒否する。"""


def decode_ordinary_pitch_response(raw: str) -> OrdinaryPitchResponse:
    """応答の全wire memberを閉DTOへ写し、型の取りこぼしを拒否する。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        parsed = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        result = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        dumped = result.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if json.dumps(parsed, sort_keys=True) != json.dumps(dumped, sort_keys=True):
            raise ValueError("wire構造または厳密な型が一致しない")
        return result
    except (ValueError, ValidationError, TypeError):
        raise OrdinaryPitchProtocolError(
            "通常投球応答が固定ABIに適合しません"
        ) from None


def evaluate_ordinary_pitch(request: OrdinaryPitchRequest) -> OrdinaryPitchResponse:
    """固定製品Node hostを一度だけ呼び、Pythonの別計算を置かない。"""
    if type(request) is not OrdinaryPitchRequest:
        raise TypeError("OrdinaryPitchRequestの実型が必要です")
    validated = OrdinaryPitchRequest.model_validate(request)
    with open_domain_host() as host:
        return decode_ordinary_pitch_response(
            host.call(
                "deriveOrdinaryPitch",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
