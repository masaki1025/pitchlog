"""v2計算の閉V7/差分V8とwire-head metadata seal。数学や資格を生成しない。"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from pitchlog.domainrt.first_ball_projection import _canonical_json, _canonical_sha256
from pitchlog.domainrt.first_pitch import _Frozen
from pitchlog.domainrt.first_pitch_continuation import _check_frozen_members
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    BattedForceOut,
    CanonicalUuid,
    Digest,
    LineupPrefixRequest,
    LineupPrefixSuccess,
    NonplayLineupPrefixRequest,
    NonplayLineupPrefixSuccess,
    RbiRulingByRunner,
    RunnerEventT1Input,
    RunnerObservation,
    verify_lineup_wire_seal,
)
from pitchlog.domainrt.play_prefix_continuation import (
    PlayPrefixRequest,
    PlayPrefixSuccess,
)
from pitchlog.domainrt.terminal_pitch import TerminalHistoryEntry
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.nonpitch_payload import IntentionalWalkObservations
from pitchlog.sync.ordinary_pitch_payload import (
    OrdinaryPitchParticipants,
    _raw_json,
)


class TerminalPitchPayloadError(ValueError):
    """原入力や資格を例外へ混ぜない固定の閉境界違反。"""

    def __init__(self) -> None:
        """不一致を補修しない。"""
        super().__init__("v2投球payload/metadataが実評価と一致しません")


class TerminalPitchCalculation(_Frozen):
    """実artifact一回の全request/response。保存資格とは別。"""

    format_version: Literal["play-prefix-calculation-v2"] = Field(alias="formatVersion")
    artifact_sha256: Annotated[str, AfterValidator(_canonical_sha256)] = Field(
        alias="artifactSha256"
    )
    request: PlayPrefixRequest
    response: PlayPrefixSuccess


class TerminalPitchPlayPayload(_Frozen):
    """既V7と区別した閉variant。参加者は今回before側。"""

    format_version: Literal["play-prefix-play-v2"] = Field(alias="formatVersion")
    observations: FirstBallObservations
    participants: OrdinaryPitchParticipants
    calculation: TerminalPitchCalculation


def _dump(value):
    """省略差分をnullへ補完せず全wire値を保持する。"""
    return value.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _checked(value, model):
    """強制変更/異なる実型/余剰memberをJSON再検証でも拒否する。"""
    if type(value) is not model:
        raise TerminalPitchPayloadError
    _check_frozen_members(value)
    result = model.model_validate_json(_canonical_json(_dump(value)))
    if _canonical_json(_dump(result)) != _canonical_json(_dump(value)):
        raise TerminalPitchPayloadError
    return result


def play_prefix_wire_head(
    request: PlayPrefixRequest, response: PlayPrefixSuccess
) -> dict:
    """自己echo二欄以外を落とさないexact Wを構成する。"""
    request = _checked(request, PlayPrefixRequest)
    response = _checked(response, PlayPrefixSuccess)
    q, r = _dump(request), _dump(response)["value"]
    ref, source = r["nextPrefixRef"], q["source"]
    if (
        r["previousPrefixRef"] != q["prefixRef"]
        or r["playIdentity"] != q["playIdentity"]
        or ref["checkpoint"]["id"] != q["nextCheckpoint"]["id"]
        or ref["checkpoint"]["revision"] != q["nextCheckpoint"]["revision"]
        or source["executionArtifactSha256"] != r["executionArtifactSha256"]
    ):
        raise TerminalPitchPayloadError
    return {
        "formatVersion": "play-prefix-wire-head-v2",
        "version": ref["version"],
        "scope": ref["scope"],
        "tenantId": ref["tenantId"],
        "gameId": ref["gameId"],
        "generation": ref["generation"],
        "length": ref["length"],
        "checkpointId": ref["checkpoint"]["id"],
        "checkpointRevision": ref["checkpoint"]["revision"],
        "historyVersion": ref["historyVersion"],
        "origin": ref["origin"],
        "previousPrefixRef": q["prefixRef"],
        "rules": q["rules"],
        "rulesDigest": source["rulesDigest"],
        "layoutDigest": source["layoutDigest"],
        "priorArtifactSha256": source["priorArtifactSha256"],
        "executionArtifactSha256": source["executionArtifactSha256"],
        "sourcePosition": source["position"],
        "playIdentity": q["playIdentity"],
        "responsibility": source["responsibility"],
        "before": q["t1"]["before"],
        "T1": r["t1"],
        "T2": r["t2"],
        "newHistoryEntry": r["newHistoryEntry"],
        "runners": r["runners"],
        "participants": r["participants"],
    }


def play_prefix_wire_digest(
    request: PlayPrefixRequest, response: PlayPrefixSuccess
) -> str:
    """実出力と真正sourceからwire-headだけのhashを算出する。"""
    return hashlib.sha256(
        _canonical_json(play_prefix_wire_head(request, response)).encode("utf-8")
    ).hexdigest()


def seal_play_prefix_metadata(
    request: PlayPrefixRequest, response: PlayPrefixSuccess
) -> tuple[PlayPrefixRequest, PlayPrefixSuccess]:
    """一回数学後の自己echo二箇所だけを機械追随する。"""
    digest = play_prefix_wire_digest(request, response)
    q, r = _dump(request), _dump(response)
    q["nextCheckpoint"]["digest"] = digest
    r["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
    return (
        PlayPrefixRequest.model_validate_json(_canonical_json(q)),
        PlayPrefixSuccess.model_validate_json(_canonical_json(r)),
    )


def verify_play_prefix_seal(calculation: TerminalPitchCalculation) -> None:
    """未信頼提案が実wire-head hashと一致するまで保存準備を許さない。"""
    calc = _checked(calculation, TerminalPitchCalculation)
    digest = play_prefix_wire_digest(calc.request, calc.response)
    if (
        calc.artifact_sha256 != calc.request.source.execution_artifact_sha256
        or calc.request.next_checkpoint.digest != digest
        or calc.response.value.next_prefix_ref.checkpoint.digest != digest
    ):
        raise TerminalPitchPayloadError


def format_terminal_pitch_payload(
    observations: FirstBallObservations,
    participants: OrdinaryPitchParticipants,
    calculation: TerminalPitchCalculation,
) -> tuple[str, str]:
    """V7のみ計算封筒、V8は取消用difference全値を写す。"""
    try:
        verify_play_prefix_seal(calculation)
        payload = TerminalPitchPlayPayload.model_validate_json(
            _canonical_json(
                {
                    "formatVersion": "play-prefix-play-v2",
                    "observations": _dump(
                        _checked(observations, FirstBallObservations)
                    ),
                    "participants": _dump(
                        _checked(participants, OrdinaryPitchParticipants)
                    ),
                    "calculation": _dump(
                        _checked(calculation, TerminalPitchCalculation)
                    ),
                }
            )
        )
        return _canonical_json(_dump(payload)), _canonical_json(
            _dump(calculation.response.value.new_history_entry.difference)
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise TerminalPitchPayloadError from None


def read_terminal_pitch_payload(
    v7_json: str,
    v8_json: str,
    *,
    expected_calculation: TerminalPitchCalculation,
    expected_participants: OrdinaryPitchParticipants,
) -> TerminalPitchPlayPayload:
    """独立実計算/実参加者/差分V8へ全値一致する場合だけ受け取る。"""
    try:
        calc = _checked(expected_calculation, TerminalPitchCalculation)
        people = _checked(expected_participants, OrdinaryPitchParticipants)
        verify_play_prefix_seal(calc)
        payload = TerminalPitchPlayPayload.model_validate_json(v7_json)
        if (
            _canonical_json(_raw_json(v7_json)) != _canonical_json(_dump(payload))
            or payload.calculation != calc
            or payload.participants != people
            or people.batting_order != calc.request.t1.before.state_fields.batting_order
        ):
            raise TerminalPitchPayloadError
        entry = TerminalHistoryEntry.model_validate_json(
            _canonical_json(
                {"kind": "confirmed-play", "difference": _raw_json(v8_json)}
            )
        )
        if (
            _canonical_json(_raw_json(v8_json))
            != _canonical_json(_dump(entry.difference))
            or entry.difference != calc.response.value.new_history_entry.difference
        ):
            raise TerminalPitchPayloadError
        return payload
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise TerminalPitchPayloadError from None


class LineupPitchCalculation(_Frozen):
    """旧v2計算封筒を広げないv3 variant。"""

    format_version: Literal["play-prefix-calculation-v3"] = Field(alias="formatVersion")
    artifact_sha256: Digest = Field(alias="artifactSha256")
    request: LineupPrefixRequest
    response: LineupPrefixSuccess


class NonplayPitchCalculation(_Frozen):
    """非play原本からの通常投球。数学提案と保存CPの発行を区別する。"""

    format_version: Literal["nonplay-prefix-calculation-v1"] = Field(
        alias="formatVersion"
    )
    artifact_sha256: Digest = Field(alias="artifactSha256")
    request: NonplayLineupPrefixRequest
    response: NonplayLineupPrefixSuccess

    @model_validator(mode="after")
    def _normal_only(self):
        """閉normal profileで未提供の打球/非投球を暗黙有効化しない。"""
        if type(self.request.t1) is RunnerEventT1Input:
            return self
        if (
            self.request.t1.result_id != "batting-result.ball"
            or self.request.t1.pitch_event_kind != "pitch-event"
            or self.response.value.t1.plate_appearance_ended is not False
        ):
            raise ValueError("非play後normal profile外")
        return self


class _NoErrorScoring(_Frozen):
    """失策なしの明示採用観測。件数や野手を結果から推測しない。"""

    kind: Literal["no-error"]
    error_count: Literal["0"] = Field(alias="errorCount")
    fielders: tuple[()]


class _RecordedError(_Frozen):
    """公式失策1件の原野手と数値プリミティブ件数。"""

    fielder: _OfficialBatter
    count: Literal[1]

    @field_validator("count", mode="before")
    @classmethod
    def _primitive_one(cls, value: object) -> object:
        """bool・toJSON・数値wrapperを1件へ暗黙変換しない。"""
        if type(value) is not int or value != 1:
            raise ValueError("公式失策件数は数値プリミティブ1のみ")
        return value


class _RecordedErrorScoring(_Frozen):
    """正本の失策1件だけ。複数件は未接続として閉じる。"""

    kind: Literal["error-recorded"]
    errors: tuple[_RecordedError] = Field(min_length=1, max_length=1)


def _official_error_fielder_in_roster(
    roster: InitialRosterProjection, team_id: str, fielder_id: str
) -> bool:
    """今回の実守備側で野手役を持つ公式選手だけを返す。"""
    if type(roster) is not InitialRosterProjection:
        return False
    return any(
        team.team_id == team_id
        and any(
            entry.player.player_id == fielder_id
            and any(role.kind == "fielding" for role in entry.roles)
            for entry in team.participants
        )
        for team in roster.teams
    )


class _NoInterference(_Frozen):
    """今回妨害裁定が不要であるという記録者の明示観測。"""

    kind: Literal["not-required"]


class _NoRunnerOverride(_Frozen):
    """走者上書きを行わなかった明示観測。空値の既定補完はしない。"""

    kind: Literal["not-applied"]
    overrides: tuple[()]


class _RunnerAdvanceOverride(_Frozen):
    """記録者が確定した1走者の実到達塁。"""

    runner_base: Literal["1", "2", "3"] = Field(alias="runnerBase")
    destination: Literal["1", "2", "3", "4"]


class _AppliedRunnerOverrides(_Frozen):
    """空配列を未確認として受理しない明示override。"""

    kind: Literal["applied"]
    overrides: tuple[_RunnerAdvanceOverride, ...] = Field(min_length=1, max_length=3)


class _NoThirdOut(_Frozen):
    """今回第三アウトがない明示観測。"""

    kind: Literal["none"]


class _OfficialBatter(_Frozen):
    """当該プレイの真正打者を保存する公式参照。"""

    kind: Literal["official"]
    player_id: CanonicalUuid


class _BatterBeforeFirst(_Frozen):
    """第3アウトとなる打者走者の一塁到達前を明示する。"""

    kind: Literal["batter-before-first"]
    batter: _OfficialBatter


class _NoThirdOutTiming(_Frozen):
    """第三アウトがない場合の空観測。未知走者/観測値は拒否する。"""


class _BattedBall(_Frozen):
    """記録された打球情報だけを保持し、未観測値や野手を推測しない。"""

    type_key: Annotated[str, Field(min_length=1)] | None = Field(alias="typeKey")
    strength_key: Annotated[str, Field(min_length=1)] | None = Field(
        alias="strengthKey"
    )
    hit_x: str | None = Field(alias="hitX")
    hit_y: str | None = Field(alias="hitY")
    raw_fielder_position: Annotated[str, Field(min_length=1)] | None = Field(
        alias="rawFielderPosition"
    )
    resolved_fielder_id: str | None = Field(alias="resolvedFielderId")

    @model_validator(mode="after")
    def _closed_observed_coordinates(self):
        """有限十進原値/UUID表現だけを検査し、座標/所属の計算はしない。"""
        import re
        from uuid import UUID

        for value in (self.hit_x, self.hit_y):
            if (
                value is not None
                and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value, re.ASCII)
                is None
            ):
                raise ValueError("打球座標の有限十進表現が不正")
        if (
            self.resolved_fielder_id is not None
            and str(UUID(self.resolved_fielder_id)) != self.resolved_fielder_id
        ):
            raise ValueError("打球野手のUUID表現が不正")
        return self


class BattedHitPlayObservations(FirstBallObservations):
    """既投球観測と独立した打球/裁定の全明示値。数学タグだけで代用しない。"""

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
    batted_ball: _BattedBall = Field(alias="battedBall")
    official_scoring_payload: _NoErrorScoring | _RecordedErrorScoring = Field(
        alias="officialScoringPayload"
    )
    interference_ruling: _NoInterference = Field(alias="interferenceRuling")
    runner_advance_overrides: _NoRunnerOverride | _AppliedRunnerOverrides = Field(
        alias="runnerAdvanceOverridesByRunner"
    )
    third_out_observation: _NoThirdOut | _BatterBeforeFirst = Field(
        alias="thirdOutObservation"
    )
    third_out_timing_by_runner: _NoThirdOutTiming = Field(
        alias="thirdOutTimingByRunner"
    )
    out_runner: BattedForceOut | None = Field(default=None, alias="outRunner")
    rbi_ruling_by_runner: RbiRulingByRunner | None = Field(
        default=None, alias="rbiRulingByRunner"
    )

    @model_serializer(mode="wrap")
    def _serialize_closed_variant(self, handler):
        """旧V7には新しい任意memberを出さず、併殺だけ原観測を出す。"""
        value = handler(self)
        if self.out_runner is None:
            value.pop("outRunner", None)
            value.pop("out_runner", None)
        if self.rbi_ruling_by_runner is None:
            value.pop("rbiRulingByRunner", None)
            value.pop("rbi_ruling_by_runner", None)
        return value

    @model_validator(mode="after")
    def _closed_out_runner(self):
        """既V7へ明示nullを混ぜず、併殺だけ走者アウトを保存する。"""
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


class RunnerPitchPlayObservations(FirstBallObservations):
    """実投球観測と正式perPitchを持つ明示走者操作。"""

    runner_observation: RunnerObservation = Field(alias="runnerObservation")


class RunnerNonpitchPlayObservations(_Frozen):
    """投球を行わない操作。球種/コースを仮値で補わない。"""

    kind: Literal["non-pitch-event"]
    runner_observation: RunnerObservation = Field(alias="runnerObservation")


class LineupPitchPlayPayload(_Frozen):
    """V7のbefore参加者/実観測と実一回計算。V8は差分のまま。"""

    format_version: Literal["play-prefix-play-v3"] = Field(alias="formatVersion")
    observations: (
        FirstBallObservations
        | BattedHitPlayObservations
        | IntentionalWalkObservations
        | RunnerPitchPlayObservations
        | RunnerNonpitchPlayObservations
    )
    participants: OrdinaryPitchParticipants
    calculation: LineupPitchCalculation | NonplayPitchCalculation = Field(
        discriminator="format_version"
    )

    @model_validator(mode="after")
    def _closed_nonplay_observation(self):
        """通常観測を別profileの打球裁定で代用しない。"""
        if type(self.calculation) is NonplayPitchCalculation and type(
            self.observations
        ) not in {
            FirstBallObservations,
            RunnerPitchPlayObservations,
            RunnerNonpitchPlayObservations,
        }:
            raise ValueError("非play後normal観測以外")
        return self


def read_lineup_pitch_payload(
    raw_v7,
    raw_v8,
    *,
    expected_calculation,
    require_current_rbi: bool = False,
    current_roster: InitialRosterProjection | None = None,
):
    """実独立評価とV7/V8/参加者を全比較し、欠落/alias/型の変化を拒否する。"""
    try:
        payload = LineupPitchPlayPayload.model_validate_json(raw_v7)
        if _canonical_json(_raw_json(raw_v7)) != _canonical_json(_dump(payload)):
            raise ValueError
        if type(payload) is not LineupPitchPlayPayload or type(
            expected_calculation
        ) not in {LineupPitchCalculation, NonplayPitchCalculation}:
            raise ValueError
        if _canonical_json(_dump(payload.calculation)) != _canonical_json(
            _dump(expected_calculation)
        ):
            raise ValueError
        request = payload.calculation.request
        response = payload.calculation.response
        from pitchlog.domainrt.lineup_prefix_source import (
            require_batted_hit_observations,
        )

        if type(request.t1) is RunnerEventT1Input:
            if type(payload.observations) not in {
                RunnerPitchPlayObservations,
                RunnerNonpitchPlayObservations,
            }:
                raise ValueError
            if not isinstance(
                payload.observations,
                (RunnerPitchPlayObservations, RunnerNonpitchPlayObservations),
            ):
                raise ValueError
            observation = payload.observations.runner_observation
            if observation != request.t1.runner_observation:
                raise ValueError
            if (request.t1.pitch_event_kind == "pitch-event") != (
                type(payload.observations) is RunnerPitchPlayObservations
            ):
                raise ValueError
        elif type(payload.observations) is IntentionalWalkObservations:
            from pitchlog.sync.nonpitch_payload import (
                require_intentional_walk_observation,
            )

            if type(payload.calculation) is not LineupPitchCalculation:
                raise ValueError
            require_intentional_walk_observation(request.t1, payload.observations)
        else:
            require_batted_hit_observations(
                request.t1,
                payload.observations,
                require_current_rbi=require_current_rbi,
                actual_scoring=getattr(response.value, "runner_score_effects", None),
                actual_score_changed=(
                    request.t1.before.state_fields.score
                    != response.value.t1.after.state_fields.score
                ),
            )
            if (
                type(payload.observations) is BattedHitPlayObservations
                and type(payload.observations.official_scoring_payload)
                is _RecordedErrorScoring
            ):
                if type(payload.calculation) is not LineupPitchCalculation:
                    raise ValueError
                request = payload.calculation.request
                side = request.source.lineup.home
                if request.t1.before.state_fields.half == "bottom":
                    side = request.source.lineup.away
                fielder = payload.observations.official_scoring_payload.errors[
                    0
                ].fielder.player_id
                if fielder not in {
                    *side.batting_order.model_dump(mode="json", by_alias=True).values(),
                    side.pitcher_id,
                    side.catcher_id,
                }:
                    raise ValueError
                if current_roster is not None and not _official_error_fielder_in_roster(
                    current_roster, side.team_id, fielder
                ):
                    raise ValueError
        if (
            payload.calculation.artifact_sha256
            != response.value.execution_artifact_sha256
        ):
            raise ValueError
        if type(payload.calculation) is NonplayPitchCalculation:
            request = payload.calculation.request
            response = payload.calculation.response
            if (
                (
                    type(request.t1) is not RunnerEventT1Input
                    and (
                        type(payload.observations) is not FirstBallObservations
                        or request.t1.result_id != "batting-result.ball"
                    )
                )
                or request.prefix_ref != request.source.checkpoint.ref
                or response.value.previous_prefix_ref != request.prefix_ref
                or response.value.next_prefix_ref != request.next_checkpoint
                or response.value.play_identity != request.play_identity
                or response.value.source_position != request.source_position
                or payload.calculation.artifact_sha256
                != request.source.checkpoint.content.execution_artifact_sha256
            ):
                raise ValueError
        elif type(payload.calculation) is LineupPitchCalculation:
            verify_lineup_wire_seal(
                payload.calculation.request, payload.calculation.response
            )
        else:
            raise ValueError
        if _canonical_json(_dump(payload.participants)) != _canonical_json(
            _dump(response.value.before_participants)
        ):
            raise ValueError
        if type(payload.observations) is BattedHitPlayObservations:
            third = payload.observations.third_out_observation
            if third.kind == "batter-before-first" and (
                type(third) is not _BatterBeforeFirst
                or third.batter.player_id != payload.participants.batter_id
            ):
                raise ValueError
            if payload.observations.result_id == "batting-result.double-play":
                out = payload.observations.out_runner
                if type(payload.calculation) is not LineupPitchCalculation:
                    raise ValueError
                runners = payload.calculation.request.source.runners
                if (
                    out is None
                    or len(runners) != 1
                    or runners[0].base != "1"
                    or out.runner_id != runners[0].runner_id
                    or out.runner_id == payload.participants.batter_id
                ):
                    raise ValueError
        parsed = _raw_json(raw_v8)
        if _canonical_json(parsed) != _canonical_json(
            response.value.new_history_entry.difference.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            )
        ):
            raise ValueError
        return payload
    except (ValueError, TypeError):
        raise TerminalPitchPayloadError from None


def format_batted_hit_prefix_payload(
    observations: BattedHitPlayObservations,
    calculation: LineupPitchCalculation,
) -> tuple[str, str]:
    """唯一の実計算と観測からV7/V8を形成する。保存資格や成功ACKは発行しない。"""
    try:
        observed = _checked(observations, BattedHitPlayObservations)
        calc = _checked(calculation, LineupPitchCalculation)
        raw_v7 = _canonical_json(
            {
                "formatVersion": "play-prefix-play-v3",
                "observations": _dump(observed),
                "participants": _dump(calc.response.value.before_participants),
                "calculation": _dump(calc),
            }
        )
        raw_v8 = _canonical_json(
            _dump(calc.response.value.new_history_entry.difference)
        )
        read_lineup_pitch_payload(raw_v7, raw_v8, expected_calculation=calc)
        return raw_v7, raw_v8
    except (AttributeError, TypeError, ValueError):
        raise TerminalPitchPayloadError from None
