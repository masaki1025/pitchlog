"""最初の一球を固定製品artifactで評価する型付きJSON境界。

計算・認可・記録権・Ready・保存の証明は作らない。DTOは構造/表現だけを検証し、
対応する操作/状態の判断は単一TS artifactへ渡す。未知の応答は成功へ補完しない。
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from pitchlog.domainrt.host import open_domain_host

_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)", re.ASCII)


def _canonical_unsigned(value: str) -> str:
    """値を計算せず、境界の非負十進文字列表現だけを検査する。"""
    if _DECIMAL.fullmatch(value) is None:
        raise ValueError("canonicalな非負十進文字列が必要")
    return value


DecimalInteger: TypeAlias = Annotated[str, AfterValidator(_canonical_unsigned)]
ErrorCode: TypeAlias = Literal[
    "INVALID_JSON", "INVALID_REQUEST", "INVALID_DECIMAL_INTEGER", "UNSUPPORTED_T1_SCOPE"
]


class _Frozen(BaseModel):
    """全入れ子で暗黙変換と余分fieldを拒否する不変DTO。"""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
        validate_by_alias=True,
        validate_by_name=True,
    )


class Score(_Frozen):
    """得点または回別得点の閉じた組。"""

    home: DecimalInteger
    away: DecimalInteger


class StateFields(_Frozen):
    """数学核へ渡す状態。対応scopeの判定はartifactが所有する。"""

    half: Literal["top", "bottom"] = Field(alias="state.half")
    strikes: DecimalInteger = Field(alias="state.count.strikes")
    balls: DecimalInteger = Field(alias="state.count.balls")
    outs: DecimalInteger = Field(alias="state.outs")
    runners: Literal[
        "empty",
        "first",
        "second",
        "third",
        "first-second",
        "first-third",
        "second-third",
        "loaded",
    ] = Field(alias="state.runners")
    batting_order: DecimalInteger = Field(alias="state.battingOrder")
    tiebreak_active: bool = Field(alias="state.tiebreakActive")
    game_ended: bool = Field(alias="state.gameEnded")
    inning: DecimalInteger = Field(alias="state.inning")
    score: Score = Field(alias="state.score")


class Scoreboard(_Frozen):
    """実呼出側が供給する投影。欠落を0で生成しない。"""

    inning_scores: Score = Field(alias="inningScores")
    hits: DecimalInteger
    errors: DecimalInteger
    strikeouts: DecimalInteger
    walks: DecimalInteger


class StateSnapshot(_Frozen):
    """渡された状態と投影の値。出所や権限を証明する型ではない。"""

    state_fields: StateFields = Field(alias="stateFields")
    scoreboard: Scoreboard


class FirstPitchRequest(_Frozen):
    """閉じた要求形。型が正しい未対応値もartifactへ渡して非成功とする。"""

    event_kind: str = Field(alias="eventKind")
    result_id: str = Field(alias="resultId")
    pitch_event_kind: str = Field(alias="pitchEventKind")
    before: StateSnapshot


class UnchangedCount(_Frozen):
    """値を補わないカウント不変の外形。"""

    kind: Literal["unchanged"]


class DeltaCount(_Frozen):
    """artifactから返されたカウント差分。値の計算はしない。"""

    kind: Literal["delta"]
    value: DecimalInteger


class CountEffect(_Frozen):
    """この一球に受理済みのカウント効果外形。"""

    strikes: UnchangedCount
    balls: DeltaCount


class BatterDestination(_Frozen):
    """打者続行の閉じた外形。"""

    kind: Literal["continue"]


class RunnerAdvance(_Frozen):
    """走者なしの進塁外形。"""

    modality: Literal["not-applicable"]
    destination: None


class RunnerAdvances(_Frozen):
    """3塁分の進塁外形。"""

    first: RunnerAdvance
    second: RunnerAdvance
    third: RunnerAdvance


class OutEffect(_Frozen):
    """アウト効果。空対象列はtupleで保持する。"""

    count: DecimalInteger
    targets: tuple[()]


class StatFlags(_Frozen):
    """既23flagの値だけを保持し、Pythonで導出しない。"""

    innings_outs: bool = Field(alias="投球回算入アウト")
    pitch: bool = Field(alias="投球数")
    strikeout_pitcher: bool = Field(alias="奪三振")
    walk_pitcher: bool = Field(alias="与四球")
    hit_by_pitch_pitcher: bool = Field(alias="与死球")
    hit_allowed: bool = Field(alias="被安打")
    home_run_allowed: bool = Field(alias="被本塁打")
    run_allowed: bool = Field(alias="失点")
    error: bool = Field(alias="失策")
    plate_appearance: bool = Field(alias="打席")
    at_bat: bool = Field(alias="打数")
    hit: bool = Field(alias="安打")
    home_run: bool = Field(alias="本塁打")
    total_bases: bool = Field(alias="塁打")
    sacrifice_bunt: bool = Field(alias="犠打")
    sacrifice_fly: bool = Field(alias="犠飛")
    walk: bool = Field(alias="四球")
    hit_by_pitch: bool = Field(alias="死球")
    strikeout_batter: bool = Field(alias="三振")
    batting_interference: bool = Field(alias="打撃妨害出塁")
    runner_interference: bool = Field(alias="走塁妨害出塁")
    run: bool = Field(alias="得点")
    rbi: bool = Field(alias="打点")


class BeforeAfter(_Frozen):
    """返却された前後値。大小や差をPythonで再計算しない。"""

    before: DecimalInteger
    after: DecimalInteger


class HistoryStateDifference(_Frozen):
    """この一球の変更欄だけを保持する。"""

    balls: BeforeAfter = Field(alias="state.count.balls")


class UnchangedScoreboard(_Frozen):
    """差分の空object。絶対投影の補完ではない。"""


class HistoryDifference(_Frozen):
    """状態差分と寄与flag。既stack全体を生成しない。"""

    state_fields: HistoryStateDifference = Field(alias="stateFields")
    scoreboard: UnchangedScoreboard
    stat_flags: StatFlags = Field(alias="statFlags")


class HistoryEntry(_Frozen):
    """返却された単一confirmed差分。"""

    kind: Literal["confirmed-play"]
    difference: HistoryDifference


class FirstPitchValue(_Frozen):
    """単一artifactの成功値8member。"""

    count_effect: CountEffect = Field(alias="countEffect")
    plate_appearance_ended: bool = Field(alias="plateAppearanceEnded")
    batter_destination: BatterDestination = Field(alias="batterDestination")
    runner_default_advance: RunnerAdvances = Field(alias="runnerDefaultAdvance")
    out_effect: OutEffect = Field(alias="outEffect")
    stat_flags: StatFlags = Field(alias="statFlags")
    after: StateSnapshot
    history_context: tuple[HistoryEntry] = Field(alias="historyContext")


class _Envelope(_Frozen):
    """boolのliteralで数値0/1を同値として扱わない。"""

    ok: bool

    @field_validator("ok", mode="before")
    @classmethod
    def _exact_bool(cls, value: object) -> object:
        """JSONのboolだけを受け取る。"""
        if type(value) is not bool:
            raise ValueError("okにはboolが必要")
        return value


class FirstPitchSuccess(_Envelope):
    """数学核の成功。取引/保存ACKを意味しない。"""

    ok: Literal[True]
    value: FirstPitchValue


class FirstPitchError(_Frozen):
    """受理済みのartifact-local4codeだけを保持する。"""

    code: ErrorCode


class FirstPitchFailure(_Envelope):
    """数学核の非成功。sync拒否IDやD5状態へ変換しない。"""

    ok: Literal[False]
    error: FirstPitchError


FirstPitchResponse: TypeAlias = FirstPitchSuccess | FirstPitchFailure
_RESPONSE = TypeAdapter(FirstPitchResponse)


class FirstPitchProtocolError(RuntimeError):
    """未知/壊れた応答を非成功の例外として扱う。"""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """壊れたguest応答の重複memberを拒否する。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("重複member")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    """JSONでない非有限数の拡張を受け付けない。"""
    raise ValueError("非JSON数値")


def decode_first_pitch_response(raw: str) -> FirstPitchResponse:
    """固定ABIを検証し、全入れ子が不変の応答DTOへ読む。

    Args:
        raw: hostから受け取ったJSON文字列。

    Returns:
        成功または既4codeの非成功DTO。

    Raises:
        FirstPitchProtocolError: 未知code、型/field/整数表現等の違反。
    """
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        parsed = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        result = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        # aliasと属性名の同時指定等で、検証後にwire memberを黙って落とさない。
        if parsed != result.model_dump(mode="json", by_alias=True):
            raise ValueError("wireの全構造がDTOのalias表現と不一致")
        return result
    except (ValueError, ValidationError, TypeError):
        raise FirstPitchProtocolError("数学核の応答が固定ABIに適合しません") from None


def evaluate_first_pitch(request: FirstPitchRequest) -> FirstPitchResponse:
    """製品固定root/hash/Node版と既寿命制限で数学核だけを評価する。

    Args:
        request: 型付き要求。対応scopeの可否は単一artifactが判定する。

    Returns:
        数学核の成功値または既4codeの非成功。認可/保存証明ではない。

    Raises:
        TypeError: 要求が指定DTOの実型でない。
        ValidationError: 強制変更等で要求の型が壊れている。
        FirstPitchProtocolError: host応答が固定ABIに適合しない。
        DomainRuntimeError: 既hostの起動/境界/実行故障。
    """
    if type(request) is not FirstPitchRequest:
        raise TypeError("FirstPitchRequestの実型が必要です")
    validated = FirstPitchRequest.model_validate(request)
    with open_domain_host() as host:
        return decode_first_pitch_response(
            host.call("deriveState", validated.model_dump_json(by_alias=True))
        )
