"""v2 prefix/T2/runnerの閉数学境界。DB真正資格や保存ACKを発行しない。"""

from __future__ import annotations

import json
from typing import Annotated, Literal, TypeAlias

from pydantic import AfterValidator, Field, TypeAdapter, ValidationError

from pitchlog.domainrt.first_ball_projection import _canonical_sha256
from pitchlog.domainrt.first_pitch import (
    BatterDestination,
    DecimalInteger,
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
    _WireFrozen,
)
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.ordinary_pitch import _OneDelta, _OrdinaryFlags
from pitchlog.domainrt.ordinary_pitch_continuation import (
    CanonicalUuid,
    OrdinaryT2,
    OrdinaryT2Basis,
    _RunnerHolds,
)
from pitchlog.domainrt.ordinary_pitch_continuation import (
    PrefixRef as V1PrefixRef,
)
from pitchlog.domainrt.terminal_pitch import (
    PositiveInteger,
    TerminalHistoryEntry,
    TerminalSnapshot,
    _HitByPitchFlags,
    _Reach,
    _Reset,
    _WalkFlags,
    _ZeroOut,
)

Digest: TypeAlias = Annotated[str, AfterValidator(_canonical_sha256)]
BattingOrder: TypeAlias = Literal["1", "2", "3", "4", "5", "6", "7", "8", "9"]


class Checkpoint(_WireFrozen):
    """保存側が供給するcheckpoint。数学でID/digestを発行しない。"""

    id: CanonicalUuid
    revision: PositiveInteger
    digest: Digest


class PlayPrefixRef(_WireFrozen):
    """旧ordinary長と別のv2 play長。bridge元は不変で保持する。"""

    version: Literal["2"]
    scope: Literal["play-prefix-v2"]
    tenant_id: CanonicalUuid = Field(alias="tenantId")
    game_id: CanonicalUuid = Field(alias="gameId")
    generation: Annotated[str, Field(min_length=1, max_length=128)]
    length: DecimalInteger
    checkpoint: Checkpoint
    history_version: DecimalInteger = Field(alias="historyVersion")
    origin: V1PrefixRef


class PlayIdentity(_WireFrozen):
    """今回/最終playのsource ID組。実所有は保存資格側が確認する。"""

    event_id: CanonicalUuid = Field(alias="eventId")
    d5: CanonicalUuid
    play_id: CanonicalUuid = Field(alias="playId")


class SourcePosition(_WireFrozen):
    """要求D1/D2と読取適用水位。play長へ読み替えず、整合は保存側が検査する。"""

    d1: DecimalInteger
    d2: DecimalInteger
    applied_watermark: DecimalInteger = Field(alias="appliedWatermark")


class Participants(_WireFrozen):
    """実PA/守備配置のsourceから供給される識別子。"""

    batter_id: CanonicalUuid = Field(alias="batterId")
    pitcher_id: CanonicalUuid = Field(alias="pitcherId")
    batting_order: BattingOrder = Field(alias="battingOrder")


class NextBatter(_WireFrozen):
    """保存側の真正打順から供給される次打者。"""

    batter_id: CanonicalUuid = Field(alias="batterId")
    batting_order: BattingOrder = Field(alias="battingOrder")


class RunnerSnapshot(_WireFrozen):
    """占有enumから生成しない実runner/責任投手。"""

    runner_id: CanonicalUuid = Field(alias="runnerId")
    responsible_pitcher_id: CanonicalUuid = Field(alias="responsiblePitcherId")
    base: Literal["1", "2", "3"]
    status: Literal["継続"]
    status_source: Literal["auto"] = Field(alias="statusSource")


class PlayT2(_WireFrozen):
    """共通TS核が実評価した非成立根拠。lock/未評価を補完しない。"""

    kind: Literal["evaluated-no-end-condition"]
    scope: Literal["play-prefix-v2"]
    evaluation_point: Literal["post-play"]
    basis: OrdinaryT2Basis


class BridgeEvidence(_WireFrozen):
    """v1原典/全play/履歴/最終sourceの内部一致だけを表す証拠形。"""

    kind: Literal["started-initial", "ordinary-only-confirmed"]
    v1_ref: V1PrefixRef = Field(alias="v1Ref")
    ordinary_play_count: DecimalInteger = Field(alias="ordinaryPlayCount")
    all_play_count: DecimalInteger = Field(alias="allPlayCount")
    history_depth: DecimalInteger = Field(alias="historyDepth")
    last_source: PlayIdentity | None = Field(alias="lastSource")
    prior_artifact_sha256: Digest = Field(alias="priorArtifactSha256")
    rules_digest: Digest = Field(alias="rulesDigest")
    layout_digest: Digest = Field(alias="layoutDigest")
    checkpoint: Checkpoint


class PaStartSource(_WireFrozen):
    """開始原典または直前PAを終了した実play sourceの識別子。"""

    kind: Literal["started-game", "confirmed-play"]
    id: CanonicalUuid


class ResponsibilityEvidence(_WireFrozen):
    """A-2の実PA/交代原典が供給する閉証拠。未解決をflattenしない。"""

    kind: Literal["no-change", "one-change", "unresolved"]
    pa_start_source: PaStartSource = Field(alias="paStartSource")
    previous_pitcher_id: CanonicalUuid | None = Field(alias="previousPitcherId")
    strikes_at_change: DecimalInteger | None = Field(alias="strikesAtChange")
    balls_at_change: DecimalInteger | None = Field(alias="ballsAtChange")


class PlayPrefixSource(_WireFrozen):
    """保存原本を確認するstep4が供給する構造。自己申告だけで資格にしない。"""

    kind: Literal["bridged-v1", "evaluated-prefix-v2", "locked-prefix-v2"]
    prefix_ref: PlayPrefixRef = Field(alias="prefixRef")
    rules: SavedRuleWire
    after: TerminalSnapshot
    t2: PlayT2 | OrdinaryT2 | T2NoEndCore | None
    history_depth: DecimalInteger = Field(alias="historyDepth")
    play_count: DecimalInteger = Field(alias="playCount")
    last_source: PlayIdentity | None = Field(alias="lastSource")
    position: SourcePosition
    prior_artifact_sha256: Digest = Field(alias="priorArtifactSha256")
    execution_artifact_sha256: Digest = Field(alias="executionArtifactSha256")
    rules_digest: Digest = Field(alias="rulesDigest")
    layout_digest: Digest = Field(alias="layoutDigest")
    runners: Annotated[tuple[RunnerSnapshot, ...], Field(max_length=3)]
    participants: Participants
    next_batter: NextBatter | None = Field(alias="nextBatter")
    bridge: BridgeEvidence | None
    responsibility: ResponsibilityEvidence


class PlayT1Input(_WireFrozen):
    """未対応resultも同一TS核で非成功にする正規化済み一球。"""

    event_kind: str = Field(alias="eventKind")
    result_id: str = Field(alias="resultId")
    pitch_event_kind: str = Field(alias="pitchEventKind")
    before: TerminalSnapshot


class PlayPrefixRequest(_WireFrozen):
    """全履歴を受け付けず、真正sourceと混同しない新閉ABI。"""

    version: Literal["2"]
    prefix_ref: PlayPrefixRef = Field(alias="prefixRef")
    rules: SavedRuleWire
    t1: PlayT1Input
    source: PlayPrefixSource
    play_identity: PlayIdentity = Field(alias="playIdentity")
    next_checkpoint: Checkpoint = Field(alias="nextCheckpoint")


class _CountEffects(_Frozen):
    """既37または受理済み終端2操作の効果外形だけを受け取る。"""

    strikes: _Reset | UnchangedCount | _OneDelta
    balls: _Reset | UnchangedCount | _OneDelta


class PlayT1(_WireFrozen):
    """今回のT1全値。Pythonは結果/カウント/差分を計算しない。"""

    count_effect: _CountEffects = Field(alias="countEffect")
    plate_appearance_ended: bool = Field(alias="plateAppearanceEnded")
    batter_destination: _Reach | BatterDestination = Field(alias="batterDestination")
    runner_default_advance: _RunnerHolds = Field(alias="runnerDefaultAdvance")
    out_effect: _ZeroOut = Field(alias="outEffect")
    stat_flags: _WalkFlags | _HitByPitchFlags | _OrdinaryFlags = Field(
        alias="statFlags"
    )
    after: TerminalSnapshot


class PlayPrefixValue(_WireFrozen):
    """数学T1/T2と今回1entry、実source由来のrunner識別子だけを保持する。"""

    t1: PlayT1
    t2: PlayT2
    new_history_entry: TerminalHistoryEntry = Field(alias="newHistoryEntry")
    previous_prefix_ref: PlayPrefixRef = Field(alias="previousPrefixRef")
    next_prefix_ref: PlayPrefixRef = Field(alias="nextPrefixRef")
    runners: Annotated[tuple[RunnerSnapshot, ...], Field(max_length=3)]
    participants: Participants
    play_identity: PlayIdentity = Field(alias="playIdentity")
    source_position: SourcePosition = Field(alias="sourcePosition")
    execution_artifact_sha256: Digest = Field(alias="executionArtifactSha256")


class PlayPrefixSuccess(_Envelope):
    """保存/ACK/記録権ではない数学成功。"""

    ok: Literal[True]
    value: PlayPrefixValue


class _Error(_WireFrozen):
    """v2の閉エラー語彙。"""

    code: Literal[
        "INVALID_JSON",
        "INVALID_REQUEST",
        "INVALID_DECIMAL_INTEGER",
        "UNSUPPORTED_T1_SCOPE",
        "T2_NOT_EVALUATED",
        "PREFIX_SOURCE_MISMATCH",
    ]


class PlayPrefixFailure(_Envelope):
    """参照不一致・lock・未評価を成功へ補完しない。"""

    ok: Literal[False]
    error: _Error


PlayPrefixResponse: TypeAlias = PlayPrefixSuccess | PlayPrefixFailure
_RESPONSE = TypeAdapter(PlayPrefixResponse)


class PlayPrefixProtocolError(RuntimeError):
    """閉wire/実artifact bindingの破損。"""


def decode_play_prefix_response(raw: str) -> PlayPrefixResponse:
    """重複・非有限・黙った正規化/余剰/欠落を拒否する。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        result = _RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        if json.dumps(wire, sort_keys=True) != json.dumps(
            result.model_dump(mode="json", by_alias=True, exclude_unset=True),
            sort_keys=True,
        ):
            raise ValueError("wire型/値の不一致")
        return result
    except (ValueError, TypeError, ValidationError):
        raise PlayPrefixProtocolError(
            "play-prefix v2応答が固定ABIに適合しません"
        ) from None


def evaluate_play_prefix_continuation(request: PlayPrefixRequest) -> PlayPrefixResponse:
    """固定実artifactへ一回だけ渡す。source資格や保存成功は生成しない。"""
    if type(request) is not PlayPrefixRequest:
        raise TypeError("PlayPrefixRequestの実型が必要です")
    _check_frozen_members(request)
    validated = PlayPrefixRequest.model_validate_json(
        request.model_dump_json(by_alias=True, exclude_unset=True),
        by_alias=True,
        by_name=False,
    )
    with open_domain_host() as host:
        if validated.source.execution_artifact_sha256 != host.artifact_sha256:
            raise PlayPrefixProtocolError(
                "実loaded artifactとexecution hashが一致しません"
            )
        return decode_play_prefix_response(
            host.call(
                "derivePlayPrefixWithContinuation",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
