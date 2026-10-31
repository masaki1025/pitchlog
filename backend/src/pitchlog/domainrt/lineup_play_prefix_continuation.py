"""両cursor v3を固定単一artifactへ一回だけ渡す閉境界。"""

from __future__ import annotations

import json
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from pitchlog.domainrt.first_pitch import (
    BatterDestination,
    DecimalInteger,
    StatFlags,
    _Envelope,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.first_pitch_continuation import (
    SavedRuleWire,
    _check_frozen_members,
)
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.ordinary_pitch_continuation import _RunnerHolds
from pitchlog.domainrt.play_prefix_continuation import (
    CanonicalUuid,
    Checkpoint,
    Digest,
    PlayIdentity,
    SourcePosition,
    _CountEffects,
)
from pitchlog.domainrt.strikeout_pitch import (
    Order,
    StrikeoutHistoryEntry,
    StrikeoutSnapshot,
    _OneOut,
    _Out,
)
from pitchlog.domainrt.terminal_pitch import PositiveInteger, _Reach, _ZeroOut


class _LineupWire(_Frozen):
    """v3だけの型保存wire。nested bool/intと履歴の省略/nullを区別する。"""

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        extra: Literal["allow", "ignore", "forbid"] | None = None,
        context: object | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """旧共有helperを変更せず、v3の全JSON型を再帰的に保存する。"""
        wire = json.loads(
            json_data,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        result = super().model_validate_json(
            json_data,
            strict=strict,
            extra=extra,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )
        if json.dumps(wire, sort_keys=True) != json.dumps(
            result.model_dump(mode="json", by_alias=True, exclude_unset=True),
            sort_keys=True,
        ):
            raise ValueError("v3 wireのJSON型/全値が変わった")
        return result


class LineupOrders(_LineupWire):
    """9枠とIDの写像。算式を持たず全枠を保持する。"""

    one: CanonicalUuid = Field(alias="1")
    two: CanonicalUuid = Field(alias="2")
    three: CanonicalUuid = Field(alias="3")
    four: CanonicalUuid = Field(alias="4")
    five: CanonicalUuid = Field(alias="5")
    six: CanonicalUuid = Field(alias="6")
    seven: CanonicalUuid = Field(alias="7")
    eight: CanonicalUuid = Field(alias="8")
    nine: CanonicalUuid = Field(alias="9")


class LineupTeam(_LineupWire):
    """実rosterから投捕を含めて供給する固定配置。"""

    team_id: CanonicalUuid = Field(alias="teamId")
    batting_order: LineupOrders = Field(alias="battingOrder")
    pitcher_id: CanonicalUuid = Field(alias="pitcherId")
    catcher_id: CanonicalUuid = Field(alias="catcherId")


class Lineup(_LineupWire):
    """両チームを一緒に拘束し、active側をPythonで計算しない。"""

    away: LineupTeam
    home: LineupTeam


class Participants(_LineupWire):
    """before/afterの投捕・打者。"""

    batter_id: CanonicalUuid = Field(alias="batterId")
    pitcher_id: CanonicalUuid = Field(alias="pitcherId")
    catcher_id: CanonicalUuid = Field(alias="catcherId")
    batting_order: Order = Field(alias="battingOrder")


class Origin(_LineupWire):
    """真正開始eventへの参照。任意v2 bridgeへ補完しない。"""

    kind: Literal["started-game"]
    event_id: CanonicalUuid = Field(alias="eventId")


class PrefixRef(_LineupWire):
    """v3長は全play長。旧v2参照を再解釈しない。"""

    version: Literal["3"]
    scope: Literal["play-prefix-v3"]
    tenant_id: CanonicalUuid = Field(alias="tenantId")
    game_id: CanonicalUuid = Field(alias="gameId")
    generation: Annotated[str, Field(min_length=1, max_length=128)]
    length: DecimalInteger
    checkpoint: Checkpoint
    history_version: DecimalInteger = Field(alias="historyVersion")
    origin: Origin


class BoundaryFacts(_LineupWire):
    """artifactの実遷移事実。Pythonで算出/補完しない。"""

    before_inning: PositiveInteger = Field(alias="beforeInning")
    before_half: Literal["top", "bottom"] = Field(alias="beforeHalf")
    before_outs: Literal["0", "1", "2"] = Field(alias="beforeOuts")
    after_inning: PositiveInteger = Field(alias="afterInning")
    after_half: Literal["top", "bottom"] = Field(alias="afterHalf")
    after_outs: Literal["0", "1", "2"] = Field(alias="afterOuts")
    half_completed: bool = Field(alias="halfCompleted")
    outs_unchanged: bool = Field(alias="outsUnchanged")
    score_unchanged: bool = Field(alias="scoreUnchanged")
    prior_open: Literal[True] = Field(alias="priorOpen")


class _OpenDecision(_LineupWire):
    """schemaの非検知3variant。野球条件を再計算しない。"""

    outcome: Literal["no-end", "extra-continue", "tiebreak-continue"]
    end_condition_detected: Literal[False] = Field(alias="endConditionDetected")
    lock_further_play_input: Literal[False] = Field(alias="lockFurtherPlayInput")
    prompt_end_declaration: Literal[False] = Field(alias="promptEndDeclaration")
    automatically_ends_game: Literal[False] = Field(alias="automaticallyEndsGame")
    x_mark: Literal["recorded-score"] = Field(alias="xMark")


class _DetectedDecision(_LineupWire):
    """schemaで検知済みの3flagsと未宣言終了falseを拘束する。"""

    end_condition_detected: Literal[True] = Field(alias="endConditionDetected")
    lock_further_play_input: Literal[True] = Field(alias="lockFurtherPlayInput")
    prompt_end_declaration: Literal[True] = Field(alias="promptEndDeclaration")
    automatically_ends_game: Literal[False] = Field(alias="automaticallyEndsGame")


class _NormalDecision(_DetectedDecision):
    """通常終了のX表示は規範schemaの2variantだけ。"""

    outcome: Literal["normal-end"]
    x_mark: Literal["recorded-score", "x-mark"] = Field(alias="xMark")


class _ColdDecision(_DetectedDecision):
    """表完了/完了裏の既cold表示2variantだけを保持する。"""

    outcome: Literal["cold-end"]
    x_mark: Literal["recorded-score", "x-mark"] = Field(alias="xMark")


class _RecordedDecision(_DetectedDecision):
    """有限引分け/サヨナラは開始済み裏の得点を保持する。"""

    outcome: Literal["limit-draw", "walk-off"]
    x_mark: Literal["recorded-score"] = Field(alias="xMark")


Decision: TypeAlias = (
    _OpenDecision | _NormalDecision | _ColdDecision | _RecordedDecision
)


class T2(_LineupWire):
    """評価済み事実/decisionを全値で受け取る。"""

    kind: Literal["evaluated-end-condition"]
    scope: Literal["play-prefix-v3"]
    evaluation_point: Literal["post-play"]
    facts: BoundaryFacts
    decision: Decision
    tiebreak_start_required: bool = Field(alias="tiebreakStartRequired")


class PaStart(_LineupWire):
    """元PAのeventId。playIdへ代替しない。"""

    kind: Literal["started-game", "confirmed-play"]
    id: CanonicalUuid


class Responsibility(_LineupWire):
    """本実保存単位は真正PA開始以後の投手交代なし。"""

    kind: Literal["no-change"]
    pa_start_source: PaStart = Field(alias="paStartSource")
    previous_pitcher_id: None = Field(alias="previousPitcherId")
    strikes_at_change: None = Field(alias="strikesAtChange")
    balls_at_change: None = Field(alias="ballsAtChange")


class StartedProvenance(_LineupWire):
    """実開始の原本参照。自己申告を真正資格にはしない。"""

    kind: Literal["started-game"]
    event_id: CanonicalUuid = Field(alias="eventId")


class ConfirmedProvenance(_LineupWire):
    """checkpoint/元D5/実eventをまとめて照合する。"""

    kind: Literal["confirmed-prefix"]
    checkpoint: Checkpoint
    source_identity: PlayIdentity = Field(alias="sourceIdentity")
    history_depth: DecimalInteger = Field(alias="historyDepth")


class Runner(_LineupWire):
    """after占有。物理PlayRunnerのbefore結果とは別。"""

    runner_id: CanonicalUuid = Field(alias="runnerId")
    responsible_pitcher_id: CanonicalUuid = Field(alias="responsiblePitcherId")
    base: Literal["1", "2", "3"]
    status: Literal["継続"]
    status_source: Literal["auto"] = Field(alias="statusSource")


class Source(_LineupWire):
    """未信頼数学提案。真正source供給は別検証を必須にする。"""

    kind: Literal["started-initial-v3", "evaluated-prefix-v3", "locked-prefix-v3"]
    prefix_ref: PrefixRef = Field(alias="prefixRef")
    rules: SavedRuleWire
    after: StrikeoutSnapshot
    t2: T2 | None
    history_depth: DecimalInteger = Field(alias="historyDepth")
    play_count: DecimalInteger = Field(alias="playCount")
    last_source: PlayIdentity | None = Field(alias="lastSource")
    position: SourcePosition
    prior_artifact_sha256: Digest = Field(alias="priorArtifactSha256")
    execution_artifact_sha256: Digest = Field(alias="executionArtifactSha256")
    rules_digest: Digest = Field(alias="rulesDigest")
    layout_digest: Digest = Field(alias="layoutDigest")
    roster_digest: Digest = Field(alias="rosterDigest")
    lineup: Lineup
    runners: tuple[Runner, ...] = Field(max_length=3)
    participants: Participants
    responsibility: Responsibility
    provenance: StartedProvenance | ConfirmedProvenance


class T1Input(_LineupWire):
    """scope外文字列も数学で非成功にする。"""

    event_kind: str = Field(alias="eventKind")
    result_id: str = Field(alias="resultId")
    pitch_event_kind: str = Field(alias="pitchEventKind")
    before: StrikeoutSnapshot


class LineupPrefixRequest(_LineupWire):
    """旧ABIへ追加せず独立した閉要求。"""

    version: Literal["3"]
    prefix_ref: PrefixRef = Field(alias="prefixRef")
    rules: SavedRuleWire
    t1: T1Input
    source: Source
    play_identity: PlayIdentity = Field(alias="playIdentity")
    next_checkpoint: Checkpoint = Field(alias="nextCheckpoint")


class T1(_LineupWire):
    """一回核の全比較面。算式/結果lookupを持たない。"""

    count_effect: _CountEffects = Field(alias="countEffect")
    plate_appearance_ended: bool = Field(alias="plateAppearanceEnded")
    batter_destination: _Out | _Reach | BatterDestination = Field(
        alias="batterDestination"
    )
    runner_default_advance: _RunnerHolds = Field(alias="runnerDefaultAdvance")
    out_effect: _OneOut | _ZeroOut = Field(alias="outEffect")
    stat_flags: StatFlags = Field(alias="statFlags")
    after: StrikeoutSnapshot


class Value(_LineupWire):
    """全数学出力と実identityを保持する。"""

    t1: T1
    t2: T2
    new_history_entry: StrikeoutHistoryEntry = Field(alias="newHistoryEntry")
    previous_prefix_ref: PrefixRef = Field(alias="previousPrefixRef")
    next_prefix_ref: PrefixRef = Field(alias="nextPrefixRef")
    runners: tuple[Runner, ...] = Field(max_length=3)
    before_participants: Participants = Field(alias="beforeParticipants")
    participants: Participants
    lineup: Lineup
    roster_digest: Digest = Field(alias="rosterDigest")
    responsibility: Responsibility
    next_responsibility: Responsibility = Field(alias="nextResponsibility")
    play_identity: PlayIdentity = Field(alias="playIdentity")
    source_position: SourcePosition = Field(alias="sourcePosition")
    execution_artifact_sha256: Digest = Field(alias="executionArtifactSha256")

    @model_validator(mode="after")
    def _require_new_cursor_head(self) -> Value:
        """v3新headのcursor面は必須。過去tail互換型を欠落許可へ流用しない。"""
        cursors = self.new_history_entry.difference.batting_order_by_side
        if cursors is None or (
            self.t1.plate_appearance_ended and not cursors.model_fields_set
        ):
            raise ValueError("v3新headのcursor差分が必要です")
        return self


class LineupPrefixSuccess(_Envelope):
    """数学成功。DB資格/ACK/Readyを生成しない。"""

    ok: Literal[True]
    value: Value


class Error(_LineupWire):
    """v3契約の閉エラー。"""

    code: Literal[
        "INVALID_JSON",
        "INVALID_REQUEST",
        "INVALID_DECIMAL_INTEGER",
        "UNSUPPORTED_T1_SCOPE",
        "T2_NOT_EVALUATED",
        "PREFIX_SOURCE_MISMATCH",
    ]


class LineupPrefixFailure(_Envelope):
    """拒否を未対応成功へ昇格しない。"""

    ok: Literal[False]
    error: Error


LineupPrefixResponse: TypeAlias = LineupPrefixSuccess | LineupPrefixFailure
_RESPONSE = TypeAdapter(LineupPrefixResponse)


class LineupPrefixProtocolError(RuntimeError):
    """固定ABI/実loaded artifactの不一致。"""


def decode_lineup_prefix_response(raw: str) -> LineupPrefixResponse:
    """JSON型を保存し、重複/非有限/余剰/alias/coercionを拒否する。"""
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
            raise ValueError("JSON型/全値の不一致")
        return result
    except (ValueError, TypeError, ValidationError):
        raise LineupPrefixProtocolError("v3応答が閉ABIに適合しません") from None


def evaluate_lineup_prefix_continuation(
    request: LineupPrefixRequest,
) -> LineupPrefixResponse:
    """実loaded source照合後、固定製品hostを一回だけ呼ぶ。"""
    if type(request) is not LineupPrefixRequest:
        raise TypeError("LineupPrefixRequestの実型が必要です")
    _check_frozen_members(request)
    validated = LineupPrefixRequest.model_validate_json(
        request.model_dump_json(by_alias=True, exclude_unset=True),
        by_alias=True,
        by_name=False,
    )
    with open_domain_host() as host:
        if validated.source.execution_artifact_sha256 != host.artifact_sha256:
            raise LineupPrefixProtocolError(
                "実loaded artifactとexecution hashが一致しません"
            )
        return decode_lineup_prefix_response(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )


def decode_lineup_prefix_request(raw: str) -> LineupPrefixRequest:
    """実wire入力を重複/非有限/型変更なしで読む。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        result = LineupPrefixRequest.model_validate_json(
            raw, by_alias=True, by_name=False
        )
        if json.dumps(wire, sort_keys=True) != json.dumps(
            result.model_dump(mode="json", by_alias=True, exclude_unset=True),
            sort_keys=True,
        ):
            raise ValueError("JSON型/全値の不一致")
        return result
    except (ValueError, TypeError, ValidationError):
        raise LineupPrefixProtocolError("v3要求が閉ABIに適合しません") from None


def lineup_wire_head(
    request: LineupPrefixRequest, response: LineupPrefixSuccess
) -> dict[str, object]:
    """実after計算後のwire-head選択field32を固定する。自己echo2以外は落とさない。"""
    if (
        type(request) is not LineupPrefixRequest
        or type(response) is not LineupPrefixSuccess
    ):
        raise TypeError("固定要求/成功応答の実型が必要です")
    r = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    v = response.value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    n = v["nextPrefixRef"]
    s = r["source"]
    return {
        "formatVersion": "play-prefix-wire-head-v3",
        "version": n["version"],
        "scope": n["scope"],
        "tenantId": n["tenantId"],
        "gameId": n["gameId"],
        "generation": n["generation"],
        "length": n["length"],
        "checkpointId": n["checkpoint"]["id"],
        "checkpointRevision": n["checkpoint"]["revision"],
        "historyVersion": n["historyVersion"],
        "origin": n["origin"],
        "previousPrefixRef": v["previousPrefixRef"],
        "rules": r["rules"],
        "rulesDigest": s["rulesDigest"],
        "layoutDigest": s["layoutDigest"],
        "rosterDigest": v["rosterDigest"],
        "lineup": v["lineup"],
        "priorArtifactSha256": s["priorArtifactSha256"],
        "executionArtifactSha256": v["executionArtifactSha256"],
        "sourcePosition": v["sourcePosition"],
        "source": s,
        "sourceProvenance": s["provenance"],
        "playIdentity": v["playIdentity"],
        "responsibility": v["responsibility"],
        "nextResponsibility": v["nextResponsibility"],
        "before": r["t1"]["before"],
        "T1": v["t1"],
        "T2": v["t2"],
        "newHistoryEntry": v["newHistoryEntry"],
        "runners": v["runners"],
        "beforeParticipants": v["beforeParticipants"],
        "participants": v["participants"],
    }


def lineup_wire_digest(
    request: LineupPrefixRequest, response: LineupPrefixSuccess
) -> str:
    """wire内容をUTF8でhashする。private full content_digestとは別。"""
    import hashlib

    wire = json.dumps(
        lineup_wire_head(request, response),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(wire.encode()).hexdigest()


def verify_lineup_wire_seal(
    request: LineupPrefixRequest, response: LineupPrefixSuccess
) -> None:
    """未信頼digest提案を実出力の正準wireと照合し、不一致を拒否する。"""
    if (
        response.value.previous_prefix_ref != request.prefix_ref
        or response.value.next_prefix_ref.checkpoint != request.next_checkpoint
        or response.value.play_identity != request.play_identity
        or response.value.source_position != request.source.position
        or response.value.execution_artifact_sha256
        != request.source.execution_artifact_sha256
        or request.next_checkpoint.digest != lineup_wire_digest(request, response)
    ):
        raise LineupPrefixProtocolError("v3 wire-head内容とdigestが一致しません")


def seal_lineup_wire(
    request: LineupPrefixRequest, response: LineupPrefixSuccess
) -> tuple[LineupPrefixRequest, LineupPrefixSuccess]:
    """実一回出力の自己echo2だけを追随し、数学値や履歴は再計算しない。"""
    digest = lineup_wire_digest(request, response)
    raw_request = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    raw_response = response.model_dump(mode="json", by_alias=True, exclude_unset=True)
    raw_request["nextCheckpoint"]["digest"] = digest
    raw_response["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
    sealed_request = decode_lineup_prefix_request(json.dumps(raw_request))
    sealed_response = decode_lineup_prefix_response(json.dumps(raw_response))
    if not sealed_response.ok:
        raise LineupPrefixProtocolError("v3成功出力が必要です")
    verify_lineup_wire_seal(sealed_request, sealed_response)
    return sealed_request, sealed_response
