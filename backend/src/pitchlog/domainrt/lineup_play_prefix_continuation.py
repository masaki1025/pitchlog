"""両cursor v3を固定単一artifactへ一回だけ渡す閉境界。"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal, Self, TypeAlias

from pydantic import (
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

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


class NoChangeResponsibility(_LineupWire):
    """真正PA開始以後に投手交代のない閉形。"""

    kind: Literal["no-change"]
    pa_start_source: PaStart = Field(alias="paStartSource")
    previous_pitcher_id: None = Field(alias="previousPitcherId")
    strikes_at_change: None = Field(alias="strikesAtChange")
    balls_at_change: None = Field(alias="ballsAtChange")


class ChangedResponsibility(_LineupWire):
    """打席途中の投手交代事実を全値で保持する。"""

    kind: Literal["changed-mid-plate-appearance"]
    pa_start_source: PaStart = Field(alias="paStartSource")
    previous_pitcher_id: CanonicalUuid = Field(alias="previousPitcherId")
    strikes_at_change: Literal["0", "1", "2"] = Field(alias="strikesAtChange")
    balls_at_change: Literal["0", "1", "2", "3"] = Field(alias="ballsAtChange")


Responsibility: TypeAlias = NoChangeResponsibility | ChangedResponsibility


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


class RunnerAdvanceOverride(_LineupWire):
    """記録者が確定した1走者の実到達塁。停止は写像へ含めない。"""

    runner_base: Literal["1", "2", "3"] = Field(alias="runnerBase")
    destination: Literal["1", "2", "3", "4"]


class AppliedRunnerAdvanceOverrides(_LineupWire):
    """空配列を未確認として受理しない明示override。"""

    kind: Literal["applied"]
    overrides: tuple[RunnerAdvanceOverride, ...] = Field(min_length=1, max_length=3)


class BattedForceOut(_LineupWire):
    """併殺の走者アウトを起点・実ID・原因で明示する。"""

    base: Literal["1"]
    runner_id: CanonicalUuid = Field(alias="runnerId")
    out_kind: Literal["force-out"] = Field(alias="outKind")


RbiRulingByRunner: TypeAlias = dict[
    Literal["1", "2", "3"],
    Literal["ordinary-play", "kept-running", "stopped-and-restarted"],
]


class BattedHitT1Input(_LineupWire):
    """安打と凡打死の明示観測を要求する打球入力。"""

    event_kind: Literal["batting-result"] = Field(alias="eventKind")
    result_id: Literal[
        "batting-result.single",
        "batting-result.double",
        "batting-result.triple",
        "batting-result.home-run",
        "batting-result.batted-out",
        "batting-result.batted-reach",
        "batting-result.error",
        "batting-result.fielders-choice",
        "batting-result.sacrifice-bunt",
        "batting-result.sacrifice-fly",
        "batting-result.sacrifice-bunt-error",
        "batting-result.double-play",
    ] = Field(alias="resultId")
    pitch_event_kind: Literal["pitch-event"] = Field(alias="pitchEventKind")
    before: StrikeoutSnapshot
    official_scoring_payload: Literal["no-error", "error-recorded"] = Field(
        alias="officialScoringPayload"
    )
    interference_ruling: Literal["not-required"] = Field(alias="interferenceRuling")
    runner_advance_overrides: Literal["not-applied"] | AppliedRunnerAdvanceOverrides = (
        Field(alias="runnerAdvanceOverrides")
    )
    third_out_observation: Literal["none", "batter-before-first"] = Field(
        alias="thirdOutObservation"
    )
    out_runner: BattedForceOut | None = Field(default=None, alias="outRunner")
    rbi_ruling_by_runner: RbiRulingByRunner | None = Field(
        default=None, alias="rbiRulingByRunner"
    )

    @model_validator(mode="after")
    def _closed_out_runner(self) -> Self:
        """旧形にnullを混ぜず、併殺だけ実走者アウトを要求する。"""
        if ("out_runner" in self.model_fields_set and self.out_runner is None) or (
            (self.result_id == "batting-result.double-play")
            != (self.out_runner is not None)
        ):
            raise ValueError("併殺走者アウトの原観測が不足")
        if (
            "rbi_ruling_by_runner" in self.model_fields_set
            and self.rbi_ruling_by_runner is None
        ):
            raise ValueError("RBI因果の明示nullは使えません")
        return self


class _RunnerOfficialRef(_LineupWire):
    """実在sourceへ後段で束縛する正式選手参照。"""

    kind: Literal["official"]
    player_id: CanonicalUuid


class _RunnerTemporaryRef(_LineupWire):
    """未解決temporaryをofficialへ補完しない。"""

    kind: Literal["temporary"]
    temporary_id: CanonicalUuid


RunnerPlayerRef: TypeAlias = _RunnerOfficialRef | _RunnerTemporaryRef
RunnerDestination: TypeAlias = Literal["first", "second", "third", "home"]


class _RunnerHold(_LineupWire):
    """明示された停止。"""

    kind: Literal["hold"]
    runner: RunnerPlayerRef


class _RunnerSafe(_LineupWire):
    """観測された到達塁。進塁計算はartifactだけが行う。"""

    kind: Literal["safe-advance"]
    runner: RunnerPlayerRef
    destination: RunnerDestination


class _RunnerOut(_LineupWire):
    """観測されたアウトの原因と企図塁。"""

    kind: Literal["out"]
    runner: RunnerPlayerRef
    attempted_base: RunnerDestination
    out_kind: Literal[
        "force-out",
        "pitcher-pickoff-out",
        "catcher-pickoff-out",
        "caught-stealing",
        "running-out",
    ]


RunnerOutcome: TypeAlias = _RunnerHold | _RunnerSafe | _RunnerOut


class RunnerOutcomeMap(_LineupWire):
    """正式partial map。省略を観測された停止へ補完しない。"""

    first: RunnerOutcome | None = None
    second: RunnerOutcome | None = None
    third: RunnerOutcome | None = None

    @model_validator(mode="after")
    def _no_explicit_null(self) -> Self:
        """省略と明示nullを区別する。"""
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("走者結果の明示nullは禁止です")
        return self


class _NotApplicableRunnerEvent(_LineupWire):
    """走者イベントを含まない明示タグ。"""

    kind: Literal["not-applicable"]


class _ExplicitRunnerEvent(_LineupWire):
    """正式runner-event payload。未知語彙を正規化しない。"""

    kind: Literal["runner-event"]
    event_kind: Literal[
        "strategy-category.steal",
        "pitcher-pickoff-destination.first",
        "pitcher-pickoff-destination.second",
        "pitcher-pickoff-destination.third",
        "catcher-pickoff-destination.first",
        "catcher-pickoff-destination.second",
        "catcher-pickoff-destination.third",
    ]
    by_runner: RunnerOutcomeMap


class _NotAppliedRunnerOverride(_LineupWire):
    """明示されたoverrideなし。"""

    kind: Literal["not-applied"]


class _ExplicitRunnerOverride(_LineupWire):
    """起点別実結果を持つ正式override。"""

    kind: Literal["overridden"]
    by_runner: RunnerOutcomeMap


class _RunnerNotRequired(_LineupWire):
    """不足観測ではなく非該当である明示タグ。"""

    kind: Literal["not-required"]


class _RunnerNoThird(_LineupWire):
    """第3アウトなし。"""

    kind: Literal["none"]


class _RunnerThirdOther(_LineupWire):
    """第3アウトの実対象。"""

    kind: Literal["other-third-out"]
    out_person: RunnerPlayerRef


class _RunnerThirdAppeal(_LineupWire):
    """アピールアウトの実対象。"""

    kind: Literal["missed-base-appeal"]
    runner: RunnerPlayerRef


class _RunnerThirdTiming(_LineupWire):
    """正式partial時機map。未観測をbeforeへ補完しない。"""

    first: Literal["home-before-third-out", "not-before-third-out"] | None = None
    second: Literal["home-before-third-out", "not-before-third-out"] | None = None
    third: Literal["home-before-third-out", "not-before-third-out"] | None = None
    batter: Literal["home-before-third-out", "not-before-third-out"] | None = None

    @model_validator(mode="after")
    def _no_explicit_null(self) -> Self:
        """省略だけを許し明示nullは拒否する。"""
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("第三アウト時機の明示nullは禁止です")
        return self


class _RunnerNoError(_LineupWire):
    """今回接続する既no-error形。誤記録を補修しない。"""

    kind: Literal["no-error"]


class _RunnerRbiNotRequired(_LineupWire):
    """RBI因果の追加観測を必要としない閉範囲。"""

    double_play_relay_error: Literal["not-required"] = Field(
        alias="doublePlayRelayError"
    )
    runner_continuity: _RunnerNotRequired = Field(alias="runnerContinuityByRunner")
    without_error: _RunnerNotRequired = Field(alias="wouldScoreWithoutErrorByRunner")
    cause_by_runner: _RunnerNotRequired
    restart_by_runner: _RunnerNotRequired


class RunnerPerPitch(_LineupWire):
    """既T1PerPitchPayloadV2の今回の閉部分集合。新意味を定義しない。"""

    kind: Literal["batting-result", "secondary-result", "runner-event"]
    pitch_event_kind: Literal["pitch-event", "non-pitch-event"] = Field(
        alias="pitchEventKind"
    )
    result_id: str = Field(alias="resultId")
    runner_event_payload: _NotApplicableRunnerEvent | _ExplicitRunnerEvent = Field(
        alias="runnerEventPayload"
    )
    runner_advance_overrides: _NotAppliedRunnerOverride | _ExplicitRunnerOverride = (
        Field(alias="runnerAdvanceOverridesByRunner")
    )
    third_out_observation: (
        _RunnerNotRequired | _RunnerNoThird | _RunnerThirdOther | _RunnerThirdAppeal
    ) = Field(alias="thirdOutObservation")
    third_out_timing: _RunnerThirdTiming = Field(alias="thirdOutTimingByRunner")
    interference_ruling: _RunnerNotRequired = Field(alias="interferenceRuling")
    official_scoring: _RunnerNoError = Field(alias="officialScoringPayload")
    rbi: _RunnerRbiNotRequired
    home_touch_order: _RunnerNotRequired = Field(alias="homeTouchOrder")


class RunnerObservation(_LineupWire):
    """元perPitchと実投球の主結果。V7原文と独立に照合する。"""

    per_pitch: RunnerPerPitch = Field(alias="perPitch")
    primary_result_id: str | None = Field(alias="primaryResultId")


class RunnerEventT1Input(_LineupWire):
    """既v3入力を一般緩和しない、明示runner観測付きvariant。"""

    event_kind: Literal["batting-result", "secondary-result", "runner-event"] = Field(
        alias="eventKind"
    )
    result_id: str = Field(alias="resultId")
    pitch_event_kind: Literal["pitch-event", "non-pitch-event"] = Field(
        alias="pitchEventKind"
    )
    before: StrikeoutSnapshot
    runner_observation: RunnerObservation = Field(alias="runnerObservation")

    @model_validator(mode="after")
    def _same_original_tags(self) -> Self:
        """外側タグを原観測と一致させ、値を書き換えない。"""
        p = self.runner_observation.per_pitch
        if (p.kind, p.result_id, p.pitch_event_kind) != (
            self.event_kind,
            self.result_id,
            self.pitch_event_kind,
        ):
            raise ValueError("走者観測と外側タグが不一致です")
        return self


class LineupPrefixRequest(_LineupWire):
    """旧ABIへ追加せず独立した閉要求。"""

    version: Literal["3"]
    prefix_ref: PrefixRef = Field(alias="prefixRef")
    rules: SavedRuleWire
    t1: T1Input | BattedHitT1Input | RunnerEventT1Input
    source: Source
    play_identity: PlayIdentity = Field(alias="playIdentity")
    next_checkpoint: Checkpoint = Field(alias="nextCheckpoint")


class _BattedReach(_LineupWire):
    """実T1が返した一/二/三塁到達。到達塁を結果から再計算しない。"""

    kind: Literal["reach"]
    base: Literal["1", "2", "3"]


class _BattedScore(_LineupWire):
    """本塁打で帰還した打者。baseを補わない。"""

    kind: Literal["score"]


class _LineupRunnerHold(_LineupWire):
    """移動を伴わない走者効果の閉形。"""

    modality: Literal["hold", "not-applicable"]
    destination: None


class _LineupRunnerMove(_LineupWire):
    """記録者が確定した明示進塁の閉形。"""

    modality: Literal["optional", "forced"]
    destination: Literal["1", "2", "3", "4"]


class _LineupRunnerAdvances(_LineupWire):
    """3塁分の実T1進塁計画。Pythonで再計算しない。"""

    first: _LineupRunnerHold | _LineupRunnerMove
    second: _LineupRunnerHold | _LineupRunnerMove
    third: _LineupRunnerHold | _LineupRunnerMove


class _FirstRunnerOut(_LineupWire):
    """SO-05の固定一死一塁行でアウトになった起点走者。"""

    runner: Literal["1"]


class _StrikeoutDoublePlayOut(_LineupWire):
    """打者と一塁走者の2アウトを閉形で保持する。"""

    count: Literal["2"]
    targets: tuple[Literal["batter"], _FirstRunnerOut]


class T1(_LineupWire):
    """一回核の全比較面。算式/結果lookupを持たない。"""

    count_effect: _CountEffects = Field(alias="countEffect")
    plate_appearance_ended: bool = Field(alias="plateAppearanceEnded")
    batter_destination: (
        _Out | _Reach | _BattedReach | _BattedScore | BatterDestination
    ) = Field(alias="batterDestination")
    runner_default_advance: _LineupRunnerAdvances = Field(alias="runnerDefaultAdvance")
    out_effect: _OneOut | _ZeroOut | _StrikeoutDoublePlayOut = Field(alias="outEffect")
    stat_flags: StatFlags = Field(alias="statFlags")
    after: StrikeoutSnapshot


class _RunnerOutTarget(_LineupWire):
    """実artifactが返したアウト起点塁。"""

    runner: Literal["1", "2", "3"]


class _RunnerOutEffect(_LineupWire):
    """一般走者アウトの閉形。算出済みcountを写す。"""

    count: Literal["0", "1", "2", "3"]
    targets: tuple[Literal["batter"] | _RunnerOutTarget, ...] = Field(max_length=3)


class _RunnerBatterNotApplicable(_LineupWire):
    """走者だけの操作に対する打者非該当。"""

    kind: Literal["not-applicable"]


class RunnerT1(_LineupWire):
    """明示runner入力に対応する実計算結果。旧T1型を緩和しない。"""

    count_effect: _CountEffects = Field(alias="countEffect")
    plate_appearance_ended: bool | Literal["not-applicable"] = Field(
        alias="plateAppearanceEnded"
    )
    batter_destination: (
        _Out
        | _Reach
        | _BattedReach
        | _BattedScore
        | BatterDestination
        | _RunnerBatterNotApplicable
    ) = Field(alias="batterDestination")
    runner_default_advance: _LineupRunnerAdvances = Field(alias="runnerDefaultAdvance")
    out_effect: _RunnerOutEffect = Field(alias="outEffect")
    stat_flags: StatFlags = Field(alias="statFlags")
    after: StrikeoutSnapshot


class RunnerScoreEffect(_LineupWire):
    """唯一核の本塁到達判定をT5へ写す根拠。Pythonで再計算しない。"""

    base: Literal["1", "2", "3"]
    valid_run: bool = Field(alias="validRun")
    rbi_credited: bool = Field(alias="rbiCredited")


class _ValueMetadata(_LineupWire):
    """全数学出力と実identityを保持する。"""

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
    def _require_new_cursor_head(self) -> Self:
        """v3新headのcursor面は必須。過去tail互換型を欠落許可へ流用しない。"""
        t1 = getattr(self, "t1")
        cursors = self.new_history_entry.difference.batting_order_by_side
        if cursors is None or (
            t1.plate_appearance_ended is True and not cursors.model_fields_set
        ):
            raise ValueError("v3新headのcursor差分が必要です")
        return self


class Value(_ValueMetadata):
    """旧v3の閉応答。runner根拠を省略して受理しない。"""

    t1: T1


class RunnerValue(_ValueMetadata):
    """明示runner操作だけの計算根拠付き閉応答。"""

    t1: RunnerT1
    runner_score_effects: tuple[RunnerScoreEffect, ...] = Field(
        alias="runnerScoreEffects", max_length=3
    )


class LineupPrefixSuccess(_Envelope):
    """数学成功。DB資格/ACK/Readyを生成しない。"""

    ok: Literal[True]
    value: Value | RunnerValue


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
    head = {
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

    if type(request.t1) is RunnerEventT1Input:
        if type(response.value) is not RunnerValue:
            raise LineupPrefixProtocolError("走者観測に実算入根拠がありません")
        head["runnerObservation"] = r["t1"]["runnerObservation"]
        head["runnerScoreEffects"] = v["runnerScoreEffects"]
    elif type(response.value) is RunnerValue:
        raise LineupPrefixProtocolError("旧入力に走者算入根拠を混在できません")
    return head


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


class NonplayScope(_LineupWire):
    """世代はopaque値として保持し、連結資格を自称しない。"""

    tenant_id: CanonicalUuid = Field(alias="tenantId")
    game_id: CanonicalUuid = Field(alias="gameId")
    generation: Annotated[str, Field(min_length=1, max_length=128)]


class NonplayEventSource(_LineupWire):
    """実eventの識別値。型成功だけでは原本資格にならない。"""

    event_id: CanonicalUuid = Field(alias="eventId")
    game_id: CanonicalUuid = Field(alias="gameId")
    generation: Annotated[str, Field(min_length=1, max_length=128)]
    d1: PositiveInteger
    d5: CanonicalUuid
    fingerprint: Annotated[
        str, Field(pattern=re.compile(r"^(?:wire-v1:)?[a-f0-9]{64}\Z"))
    ]
    event_kind: Literal[
        "play_input", "undo", "substitution", "game_end_declaration", "game_reopen"
    ] = Field(alias="eventKind")


class NonplayD1Head(_LineupWire):
    """最新受理headをprojection/activeと分離する。"""

    kind: Literal["accepted-event"]
    source: NonplayEventSource


class NonplayProjectionHead(_LineupWire):
    """保存projectionの実event参照。"""

    kind: Literal["d1-event"]
    source: NonplayEventSource


class NonplayActivePlay(_LineupWire):
    """論理D2と物理番号は独立した保存値である。"""

    source: NonplayEventSource
    play_id: CanonicalUuid = Field(alias="playId")
    d2: DecimalInteger
    physical_play_number: PositiveInteger = Field(alias="physicalPlayNumber")


class SubstitutionFielding(_LineupWire):
    """交代後の九守備枠。未配置はnullとして保持する。"""

    one: CanonicalUuid | None = Field(alias="1")
    two: CanonicalUuid | None = Field(alias="2")
    three: CanonicalUuid | None = Field(alias="3")
    four: CanonicalUuid | None = Field(alias="4")
    five: CanonicalUuid | None = Field(alias="5")
    six: CanonicalUuid | None = Field(alias="6")
    seven: CanonicalUuid | None = Field(alias="7")
    eight: CanonicalUuid | None = Field(alias="8")
    nine: CanonicalUuid | None = Field(alias="9")


class SubstitutionTeam(_LineupWire):
    """打順と守備の保存形。配置の計算はartifactだけが行う。"""

    team_id: CanonicalUuid = Field(alias="teamId")
    batting_order: LineupOrders = Field(alias="battingOrder")
    fielding: SubstitutionFielding
    dh_slot: Literal["1", "2", "3", "4", "5", "6", "7", "8", "9"] | None = Field(
        alias="dhSlot"
    )


class _UnchangedSubstitutionResponsibility(_LineupWire):
    """投手責任が変化していない形。"""

    kind: Literal["unchanged"]


class _ChangedSubstitutionResponsibility(_LineupWire):
    """途中交代時の責任事実。walk判定はartifact側へ委ねる。"""

    kind: Literal["changed-mid-plate-appearance"]
    previous_pitcher_id: CanonicalUuid = Field(alias="previousPitcherId")
    relief_pitcher_id: CanonicalUuid = Field(alias="reliefPitcherId")
    strikes_at_change: Literal["0", "1", "2"] = Field(alias="strikesAtChange")
    balls_at_change: Literal["0", "1", "2", "3"] = Field(alias="ballsAtChange")


class SubstitutionState(_LineupWire):
    """交代状態の閉保存形。"""

    attacking_side: Literal["away", "home"] = Field(alias="attackingSide")
    away: SubstitutionTeam
    home: SubstitutionTeam
    runners: tuple[Runner, ...]
    exited_player_ids: tuple[CanonicalUuid, ...] = Field(alias="exitedPlayerIds")
    responsibility: (
        _UnchangedSubstitutionResponsibility | _ChangedSubstitutionResponsibility
    )


class NonplaySubstitutionFrame(_LineupWire):
    """真正event照合前の交代frame閉形。"""

    source: NonplayEventSource
    after_play_id: CanonicalUuid | None = Field(alias="afterPlayId")
    before_context: NonplayRestoreContext = Field(alias="beforeContext")
    after_context: NonplayRestoreContext = Field(alias="afterContext")


class NonplayRestoreContext(_LineupWire):
    """採用Sourceの全復元文脈を不変保持する。"""

    current: StrikeoutSnapshot
    rules: SavedRuleWire
    rules_digest: Digest = Field(alias="rulesDigest")
    layout_digest: Digest = Field(alias="layoutDigest")
    roster_digest: Digest = Field(alias="rosterDigest")
    lineup: Lineup
    participants: Participants
    runners: tuple[Runner, ...]
    responsibility: Responsibility
    last_play_evaluation: T2 | None = Field(alias="lastPlayEvaluation")
    substitution_state: SubstitutionState | None = Field(
        default=None, alias="substitutionState"
    )

    @model_validator(mode="after")
    def _substitution_presence(self):
        """省略と明示nullを区別し、交代状態のnullを拒否する。"""
        if (
            "substitution_state" in self.model_fields_set
            and self.substitution_state is None
        ):
            raise ValueError("交代状態は省略又は閉objectが必要")
        return self


class LifecycleKernel(_LineupWire):
    """唯一kernelの全入出力。shapeは正式ABIを参照する。"""

    request: dict[str, Any]
    response: dict[str, Any]

    @field_validator("request", mode="before")
    @classmethod
    def _request(cls, value):
        from pitchlog.domainrt.game_lifecycle import LifecycleRequest

        return LifecycleRequest(json.dumps(value, ensure_ascii=False)).to_wire()

    @field_validator("response", mode="before")
    @classmethod
    def _response(cls, value):
        from pitchlog.domainrt.game_lifecycle import LifecycleResponse

        return LifecycleResponse(json.dumps(value, ensure_ascii=False)).to_wire()


class LifecycleControlBridge(_LineupWire):
    """全contextと実SQL証拠の参照。UUID型だけでは真正資格にならない。"""

    source: NonplayEventSource
    action: Literal["end", "reopen"]
    anchor_event_id: CanonicalUuid = Field(alias="anchorEventId")
    before_context: NonplayRestoreContext = Field(alias="beforeContext")
    after_context: NonplayRestoreContext = Field(alias="afterContext")
    kernel: LifecycleKernel
    frame_id: CanonicalUuid = Field(alias="frameId")
    checkpoint_before: Checkpoint = Field(alias="checkpointBefore")


class NonplayContent(_LineupWire):
    """空activeでもD3/履歴版/epoch/物理番号を保持する。"""

    scope: NonplayScope
    origin: Origin
    d3: DecimalInteger
    d1_head: NonplayD1Head | None = Field(alias="d1Head")
    projection_head: Origin | NonplayProjectionHead = Field(alias="projectionHead")
    active_head: NonplayActivePlay | None = Field(alias="activeHead")
    active_depth: DecimalInteger = Field(alias="activeDepth")
    history_version: DecimalInteger = Field(alias="historyVersion")
    storage_history_epoch: DecimalInteger = Field(alias="storageHistoryEpoch")
    next_physical_play_number: PositiveInteger = Field(alias="nextPhysicalPlayNumber")
    execution_artifact_sha256: Digest = Field(alias="executionArtifactSha256")
    restored: NonplayRestoreContext
    control_bridges: tuple[LifecycleControlBridge, ...] | None = Field(
        default=None, alias="controlBridges", exclude_if=lambda v: v is None
    )
    substitution_frames: tuple[NonplaySubstitutionFrame, ...] | None = Field(
        default=None, alias="substitutionFrames"
    )

    @model_validator(mode="after")
    def _substitution_frames_presence(self):
        """交代frameの明示nullを拒否する。"""
        if (
            "substitution_frames" in self.model_fields_set
            and self.substitution_frames is None
        ):
            raise ValueError("交代frameは省略又は配列が必要")
        return self


class NonplayCheckpoint(_LineupWire):
    """真正CP供給はruntimeの別要件。UUID/digestをこの層で発行しない。"""

    format_version: Literal["nonplay-prefix-checkpoint-v1"] = Field(
        alias="formatVersion"
    )
    ref: Checkpoint
    content: NonplayContent


class NonplayActiveFrame(_LineupWire):
    """全tailを保持して欠落や推測補完をしない。"""

    play: NonplayActivePlay
    history_entry: StrikeoutHistoryEntry = Field(alias="historyEntry")
    before_context: NonplayRestoreContext = Field(alias="beforeContext")
    after_context: NonplayRestoreContext = Field(alias="afterContext")


class NonplaySource(_LineupWire):
    """採用済nonplay Sourceの閉構造。"""

    format_version: Literal["nonplay-prefix-source-v1"] = Field(alias="formatVersion")
    checkpoint: NonplayCheckpoint
    active_stack: tuple[NonplayActiveFrame, ...] = Field(alias="activeStack")


class NonplayLineupPrefixRequest(_LineupWire):
    """取消後の実allocator位置を明示する独立variant。"""

    version: Literal["nonplay-continuation-v1"]
    prefix_ref: Checkpoint = Field(alias="prefixRef")
    rules: SavedRuleWire
    t1: T1Input | BattedHitT1Input | RunnerEventT1Input
    source: NonplaySource
    play_identity: PlayIdentity = Field(alias="playIdentity")
    next_checkpoint: Checkpoint = Field(alias="nextCheckpoint")
    source_position: SourcePosition = Field(alias="sourcePosition")


class _NonplayValueMetadata(_LineupWire):
    """全数学出力と実identityを保持する。"""

    t2: T2
    new_history_entry: StrikeoutHistoryEntry = Field(alias="newHistoryEntry")
    previous_prefix_ref: Checkpoint = Field(alias="previousPrefixRef")
    next_prefix_ref: Checkpoint = Field(alias="nextPrefixRef")
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
    def _require_new_cursor_head(self) -> Self:
        """v3新headのcursor面は必須。過去tail互換型を欠落許可へ流用しない。"""
        t1 = getattr(self, "t1")
        cursors = self.new_history_entry.difference.batting_order_by_side
        if cursors is None or (
            t1.plate_appearance_ended is True and not cursors.model_fields_set
        ):
            raise ValueError("v3新headのcursor差分が必要です")
        return self


class NonplayValue(_NonplayValueMetadata):
    """旧NP継続の閉応答。"""

    t1: T1


class RunnerNonplayValue(_NonplayValueMetadata):
    """runner操作後のNP継続結果。"""

    t1: RunnerT1
    runner_score_effects: tuple[RunnerScoreEffect, ...] = Field(
        alias="runnerScoreEffects", max_length=3
    )


class NonplayLineupPrefixSuccess(_Envelope):
    """新refは提案値であり保存成功/正式CP発行ではない。"""

    ok: Literal[True]
    value: NonplayValue | RunnerNonplayValue


NonplayLineupPrefixResponse: TypeAlias = (
    NonplayLineupPrefixSuccess | LineupPrefixFailure
)
_NONPLAY_RESPONSE = TypeAdapter(NonplayLineupPrefixResponse)


def decode_nonplay_lineup_prefix_request(raw: str) -> NonplayLineupPrefixRequest:
    """実wire入力を重複/非有限/型変更なしで読む。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        result = NonplayLineupPrefixRequest.model_validate_json(
            raw, by_alias=True, by_name=False
        )
        if json.dumps(wire, sort_keys=True) != json.dumps(
            result.model_dump(mode="json", by_alias=True, exclude_unset=True),
            sort_keys=True,
        ):
            raise ValueError("JSON型/全値の不一致")
        return result
    except (ValueError, TypeError, ValidationError):
        raise LineupPrefixProtocolError("nonplay要求が閉ABIに適合しません") from None


def decode_nonplay_lineup_prefix_response(raw: str) -> NonplayLineupPrefixResponse:
    """JSON型を保存し、重複/非有限/余剰/alias/coercionを拒否する。"""
    try:
        if type(raw) is not str:
            raise ValueError("JSON文字列が必要")
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        result = _NONPLAY_RESPONSE.validate_json(raw, by_alias=True, by_name=False)
        if json.dumps(wire, sort_keys=True) != json.dumps(
            result.model_dump(mode="json", by_alias=True, exclude_unset=True),
            sort_keys=True,
        ):
            raise ValueError("JSON型/全値の不一致")
        return result
    except (ValueError, TypeError, ValidationError):
        raise LineupPrefixProtocolError("nonplay応答が閉ABIに適合しません") from None


def evaluate_nonplay_lineup_prefix_continuation(
    request: NonplayLineupPrefixRequest,
) -> NonplayLineupPrefixResponse:
    """実loaded source照合後、固定製品hostを一回だけ呼ぶ。"""
    if type(request) is not NonplayLineupPrefixRequest:
        raise TypeError("NonplayLineupPrefixRequestの実型が必要です")
    _check_frozen_members(request)
    validated = NonplayLineupPrefixRequest.model_validate_json(
        request.model_dump_json(by_alias=True, exclude_unset=True),
        by_alias=True,
        by_name=False,
    )
    with open_domain_host() as host:
        if (
            validated.source.checkpoint.content.execution_artifact_sha256
            != host.artifact_sha256
        ):
            raise LineupPrefixProtocolError(
                "実loaded artifactとexecution hashが一致しません"
            )
        return decode_nonplay_lineup_prefix_response(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                validated.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
