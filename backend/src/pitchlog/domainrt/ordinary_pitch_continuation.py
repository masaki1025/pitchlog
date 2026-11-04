"""通常投球T1/T2の有限prefix ABIを単一artifactへ渡す閉型境界。

状態・終了条件・履歴は計算しない。参照の構造検査は保存原本の真正性を
証明せず、この数学結果を記録権や保存ACKとして利用しない。
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Self, TypeAlias
from uuid import UUID

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
    DecimalInteger,
    FirstPitchRequest,
    StateSnapshot,
    UnchangedCount,
    _Envelope,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.first_pitch_continuation import (
    SavedRuleWire,
    T2NoEndCore,
    _check_frozen_members,
    _closed_wire_error,
    _WireFrozen,
)
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.ordinary_pitch import _OneDelta, _OrdinaryFlags, _ZeroOut


def _canonical_uuid(value: str) -> str:
    """UUIDの大小文字・省略形・末尾空白を補修せず拒否する。"""
    if str(UUID(value)) != value:
        raise ValueError("正準UUIDが必要")
    return value


CanonicalUuid: TypeAlias = Annotated[str, AfterValidator(_canonical_uuid)]
PositiveInteger: TypeAlias = Annotated[DecimalInteger, Field(pattern=r"^[1-9][0-9]*$")]


class PrefixRef(_WireFrozen):
    """通常投球専用の確認水位。D4と一般履歴長を同一視しない。"""

    version: Literal["1"]
    tenant_id: CanonicalUuid = Field(alias="tenantId")
    game_id: CanonicalUuid = Field(alias="gameId")
    generation: Annotated[str, Field(min_length=1, max_length=128)]
    length: DecimalInteger


class OrdinaryT2Basis(_WireFrozen):
    """終了理由を再計算せず、artifactの全根拠を保存する。"""

    regulation_innings: PositiveInteger = Field(alias="regulationInnings")
    inning: PositiveInteger
    half: Literal["top", "bottom"]
    half_completed: Literal[False] = Field(alias="halfCompleted")
    cold_branches: Annotated[
        tuple[Literal["COLD-01", "COLD-04", "COLD-06"], ...], Field(max_length=16)
    ] = Field(alias="coldBranches")
    cold_aggregate: Literal["COLD-07"] = Field(alias="coldAggregate")
    draw_branch: Literal["DRAW-07", "DRAW-08"] = Field(alias="drawBranch")
    score_unchanged: Literal[True] = Field(alias="scoreUnchanged")
    outs_unchanged: Literal[True] = Field(alias="outsUnchanged")
    prior_open: Literal[True] = Field(alias="priorOpen")
    tiebreak_active: bool = Field(alias="tiebreakActive")
    configured_extension_limit: PositiveInteger | None = Field(
        alias="configuredExtensionLimit"
    )

    @field_validator(
        "half_completed",
        "score_unchanged",
        "outs_unchanged",
        "prior_open",
        mode="before",
    )
    @classmethod
    def _strict_boolean(cls, value: object) -> object:
        """Literal boolへ数値を暗黙変換しない。"""
        if type(value) is not bool:
            raise ValueError("真理値が必要")
        return value


class OrdinaryT2(_WireFrozen):
    """初球だけのT2を無断拡張せず、通常37の根拠形を区別する。"""

    kind: Literal["evaluated-no-end-condition"]
    scope: Literal["ordinary37"]
    evaluation_point: Literal["post-play"]
    basis: OrdinaryT2Basis


class _PriorCommon(_WireFrozen):
    """前回の確認済み原本から接続側が供給する値の外形。"""

    prefix_ref: PrefixRef = Field(alias="prefixRef")
    rules: SavedRuleWire
    after: StateSnapshot


class StartedPrior(_PriorCommon):
    """開始原典を表す候補。実開始済みかは別途検証する。"""

    kind: Literal["started-initial"]
    t2: None


class EvaluatedPrior(_PriorCommon):
    """前回のT2を省略せずartifactへ渡す。"""

    kind: Literal["evaluated-prefix"]
    t2: T2NoEndCore | OrdinaryT2


class LockedPrior(_PriorCommon):
    """入力lockの原本を成功へ変換しない。"""

    kind: Literal["locked-prefix"]
    t2: None


class OrdinaryContinuationRequest(_WireFrozen):
    """全履歴を要求しない新operation専用の閉要求。"""

    version: Literal["1"]
    prefix_ref: PrefixRef = Field(alias="prefixRef")
    rules: SavedRuleWire
    t1: FirstPitchRequest
    prior: Annotated[
        StartedPrior | EvaluatedPrior | LockedPrior, Field(discriminator="kind")
    ]

    @classmethod
    def model_validate_json(
        cls, json_data: str | bytes | bytearray, **kwargs: Any
    ) -> Self:
        """入れ子の旧modelでも数値と真理値の正規化を黙認しない。"""
        result = super().model_validate_json(json_data, **kwargs)
        wire = json.loads(
            json_data,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        if json.dumps(
            result.model_dump(mode="json", by_alias=True), sort_keys=True
        ) != (json.dumps(wire, sort_keys=True)):
            raise _closed_wire_error()
        return result


class _CountEffect(_Frozen):
    """差分または不変の構造だけを表す。"""

    strikes: UnchangedCount | _OneDelta
    balls: UnchangedCount | _OneDelta


class _RunnerHold(_Frozen):
    """今回の投球で移動を伴わない走者効果の閉形。"""

    modality: Literal["hold", "not-applicable"]
    destination: None


class _RunnerHolds(_Frozen):
    """実在塁の意味をPythonで再推定しない。"""

    first: _RunnerHold
    second: _RunnerHold
    third: _RunnerHold


class _StrictFlags(_OrdinaryFlags):
    """23個のboolに数値を受け入れない外形。"""

    @field_validator("*", mode="before")
    @classmethod
    def _strict_boolean(cls, value: object) -> object:
        """規範値の補完・計算はせず型だけを検査する。"""
        if type(value) is not bool:
            raise ValueError("真理値が必要")
        return value


class OrdinaryContinuationT1(_WireFrozen):
    """全履歴と区別した、今回のT1全値。"""

    count_effect: _CountEffect = Field(alias="countEffect")
    plate_appearance_ended: Literal[False] = Field(alias="plateAppearanceEnded")
    batter_destination: BatterDestination = Field(alias="batterDestination")
    runner_default_advance: _RunnerHolds = Field(alias="runnerDefaultAdvance")
    out_effect: _ZeroOut = Field(alias="outEffect")
    stat_flags: _StrictFlags = Field(alias="statFlags")
    after: StateSnapshot

    @field_validator("plate_appearance_ended", mode="before")
    @classmethod
    def _strict_boolean(cls, value: object) -> object:
        """Literal falseに数値0を受け入れない。"""
        if type(value) is not bool:
            raise ValueError("真理値が必要")
        return value


class _UnsignedPair(_Frozen):
    """差分の前後値を保持する。差分の算出は行わない。"""

    before: DecimalInteger
    after: DecimalInteger


class _HistoryCount(_Frozen):
    """空差分のファウルも表現し、明示nullは拒否する。"""

    balls: _UnsignedPair | None = Field(default=None, alias="state.count.balls")
    strikes: _UnsignedPair | None = Field(default=None, alias="state.count.strikes")

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> Self:
        """未指定と明示nullの区別を維持する。"""
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("差分の明示nullは不可")
        return self


class _Empty(_Frozen):
    """今回のscoreboard差分は空objectだけを受ける。"""


class _HistoryDifference(_Frozen):
    """既T1が返した一件分の差分を保持する。"""

    state_fields: _HistoryCount = Field(alias="stateFields")
    scoreboard: _Empty
    stat_flags: _StrictFlags = Field(alias="statFlags")


class NewHistoryEntry(_Frozen):
    """prefix全履歴ではない今回の履歴一件。"""

    kind: Literal["confirmed-play"]
    difference: _HistoryDifference


class OrdinaryContinuationValue(_WireFrozen):
    """同一artifactから得た両評価と新履歴をそのまま返す。"""

    t1: OrdinaryContinuationT1
    t2: OrdinaryT2
    new_history_entry: NewHistoryEntry = Field(alias="newHistoryEntry")
    previous_prefix_ref: PrefixRef = Field(alias="previousPrefixRef")
    next_prefix_ref: PrefixRef = Field(alias="nextPrefixRef")


class OrdinaryContinuationSuccess(_Envelope):
    """数学成功。保存・認可・記録権の成功ではない。"""

    ok: Literal[True]
    value: OrdinaryContinuationValue


class _Error(_Frozen):
    """新operationの閉じた非成功code。"""

    code: Literal[
        "INVALID_JSON",
        "INVALID_REQUEST",
        "INVALID_DECIMAL_INTEGER",
        "UNSUPPORTED_T1_SCOPE",
        "T2_NOT_EVALUATED",
    ]


class OrdinaryContinuationFailure(_Envelope):
    """未評価を成功に補完しない。"""

    ok: Literal[False]
    error: _Error


OrdinaryContinuationResponse: TypeAlias = (
    OrdinaryContinuationSuccess | OrdinaryContinuationFailure
)
_RESPONSE = TypeAdapter(OrdinaryContinuationResponse)


class OrdinaryContinuationProtocolError(RuntimeError):
    """固定ABIへ適合しないhost応答。"""


def decode_ordinary_continuation_response(raw: str) -> OrdinaryContinuationResponse:
    """重複key/非有限数/未知field/黙った正規化を拒否する。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        response = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        dumped = response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if json.dumps(dumped, sort_keys=True) != json.dumps(wire, sort_keys=True):
            raise ValueError("wireのkey又は表現が不一致")
        return response
    except (ValueError, TypeError, ValidationError):
        raise OrdinaryContinuationProtocolError(
            "通常継続応答が固定ABIに適合しません"
        ) from None


def evaluate_ordinary_pitch_with_continuation(
    request: OrdinaryContinuationRequest,
) -> OrdinaryContinuationResponse:
    """既固定hostを一度呼び、Pythonに計算の代替実装を置かない。"""
    if type(request) is not OrdinaryContinuationRequest:
        raise TypeError("OrdinaryContinuationRequestの実型が必要です")
    _check_frozen_members(request)
    validated = OrdinaryContinuationRequest.model_validate(request)
    with open_domain_host() as host:
        return decode_ordinary_continuation_response(
            host.call(
                "deriveOrdinaryPitchWithContinuation",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
