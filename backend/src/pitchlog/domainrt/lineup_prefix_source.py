"""実readerが供給する原本を同artifactで再生するv3 source検証。DB資格は発行しない。"""

from __future__ import annotations

import hashlib
import json

from pydantic import Field, ValidationError

from pitchlog.domainrt.first_pitch import _Frozen, _invalid_constant, _unique_object
from pitchlog.domainrt.first_pitch_continuation import (
    SavedRuleWire,
    _check_frozen_members,
)
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    CanonicalUuid,
    Digest,
    Lineup,
    LineupPrefixProtocolError,
    LineupPrefixRequest,
    LineupPrefixResponse,
    LineupPrefixSuccess,
    Source,
    SourcePosition,
    decode_lineup_prefix_response,
    verify_lineup_wire_seal,
)
from pitchlog.domainrt.play_prefix_continuation import PlayIdentity
from pitchlog.domainrt.terminal_pitch import TerminalSnapshot


class StartedLineupEvidence(_Frozen):
    """ロック下readerの実開始原本。未信頼request.sourceから組み立てない。"""

    tenant_id: CanonicalUuid
    game_id: CanonicalUuid
    generation: str
    started_event_id: CanonicalUuid
    prior_artifact_sha256: Digest
    roster: InitialRosterProjection
    snapshot: TerminalSnapshot
    rules: SavedRuleWire


class PersistedLineupPlay(_Frozen):
    """実event/ledger/PlayRow/history照合済みの原本。取得/認可はstep4責任。"""

    identity: PlayIdentity
    position_after: SourcePosition
    request: LineupPrefixRequest
    response: LineupPrefixSuccess


class LineupSourceEvidence(_Frozen):
    """実順序で読まれたprefix。任意v2移植/非play/取消/交代は別未対応。"""

    started: StartedLineupEvidence
    plays: tuple[PersistedLineupPlay, ...]
    position: SourcePosition
    complete: bool
    invalid_event_count: int = Field(ge=0)
    non_play_event_count: int = Field(ge=0)
    pa_change_count: int = Field(ge=0)


def _canonical(value: object) -> str:
    """wire正準化。野球計算を含まない。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(value: object) -> str:
    """実原本の内容hash。wire-head/full private digestとは別。"""
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _dump(value: _Frozen) -> object:
    """readonlyモデルの全明示fieldを保存する。"""
    return value.model_dump(mode="json", by_alias=True, exclude_unset=True)


def lineup_from_actual_roster(roster: InitialRosterProjection) -> Lineup:
    """実rosterの既slot/positionを写す。active側/打順/半回を計算しない。"""
    if type(roster) is not InitialRosterProjection:
        raise TypeError("実InitialRosterProjectionが必要です")
    result: dict[str, object] = {}
    for team in roster.teams:
        order: dict[str, str] = {}
        pitchers: list[str] = []
        catchers: list[str] = []
        players: set[str] = set()
        for entry in team.participants:
            player_id = entry.player.player_id
            if player_id in players:
                raise LineupPrefixProtocolError("実配置に重複があります")
            players.add(player_id)
            if entry.batting_slot.kind == "slot":
                slot = entry.batting_slot.slot
                if slot in order:
                    raise LineupPrefixProtocolError("実打順に重複があります")
                order[slot] = player_id
            for role in entry.roles:
                if role.kind == "fielding" and role.position == "1":
                    pitchers.append(player_id)
                if role.kind == "fielding" and role.position == "2":
                    catchers.append(player_id)
        if len(pitchers) != 1 or len(catchers) != 1 or set(order) != set("123456789"):
            raise LineupPrefixProtocolError("実配置の9枠/投捕が不足しています")
        result[team.side] = {
            "teamId": team.team_id,
            "battingOrder": order,
            "pitcherId": pitchers[0],
            "catcherId": catchers[0],
        }
    return Lineup.model_validate_json(_canonical(result), by_alias=True, by_name=False)


def _bound(
    request: LineupPrefixRequest, started: StartedLineupEvidence, lineup: Lineup
) -> None:
    """scope/roster/rules/内容参照を全比較する。cursor算式は置かない。"""
    if (
        request.prefix_ref.tenant_id != started.tenant_id
        or request.prefix_ref.game_id != started.game_id
        or request.prefix_ref.generation != started.generation
        or request.prefix_ref.origin.event_id != started.started_event_id
        or _canonical(_dump(request.rules)) != _canonical(_dump(started.rules))
        or _canonical(_dump(request.source.lineup)) != _canonical(_dump(lineup))
    ):
        raise LineupPrefixProtocolError("実sourceとscope/規則/配置が一致しません")
    if (
        request.source.rules_digest != _fingerprint(_dump(started.rules))
        or request.source.roster_digest != _fingerprint(_dump(lineup))
        or request.source.layout_digest != _fingerprint(_dump(lineup))
    ):
        raise LineupPrefixProtocolError("実sourceの内容hashが一致しません")


def verify_and_evaluate_lineup_source(
    request: LineupPrefixRequest, evidence: LineupSourceEvidence
) -> LineupPrefixResponse:
    """真正取得済み原本を実hostで再生し、今回の一回評価を返す。

    このpure関数は原本の取得/認可/一回consume/SQLロック/署名能力を持たない。
    evidenceはstep4の専用readerが供給し、HTTP自己申告から構築してはならない。
    """
    if (
        type(request) is not LineupPrefixRequest
        or type(evidence) is not LineupSourceEvidence
    ):
        raise TypeError("固定request/evidence実型が必要です")
    _check_frozen_members(request)
    _check_frozen_members(evidence)
    request = LineupPrefixRequest.model_validate_json(
        request.model_dump_json(by_alias=True, exclude_unset=True),
        by_alias=True,
        by_name=False,
    )
    evidence = decode_lineup_source_evidence(
        evidence.model_dump_json(by_alias=True, exclude_unset=True)
    )
    if (
        not evidence.complete
        or evidence.invalid_event_count
        or evidence.non_play_event_count
        or evidence.pa_change_count
    ):
        raise LineupPrefixProtocolError("不完全/未対応sourceを資格へ補完できません")
    actual = lineup_from_actual_roster(evidence.started.roster)
    previous: LineupPrefixSuccess | None = None
    watermark = 0
    last_d2 = 0
    seen_events: set[str] = set()
    seen_d5: set[str] = set()
    seen_plays: set[str] = set()
    with open_domain_host() as host:
        for persisted in evidence.plays:
            prior = persisted.request
            _bound(prior, evidence.started, actual)
            if (
                persisted.identity != prior.play_identity
                or persisted.identity.event_id in seen_events
                or persisted.identity.d5 in seen_d5
                or persisted.identity.play_id in seen_plays
            ):
                raise LineupPrefixProtocolError("原本の重複/identityが一致しません")
            seen_events.add(persisted.identity.event_id)
            seen_d5.add(persisted.identity.d5)
            seen_plays.add(persisted.identity.play_id)
            actual_position = prior.source.position
            if (
                int(actual_position.d1) != watermark + 1
                or int(actual_position.applied_watermark) != watermark
                or int(actual_position.d2) <= last_d2
                or watermark == 0
                and actual_position.d2 != "1"
            ):
                raise LineupPrefixProtocolError("原本順序に欠落があります")
            # 実event位置と適用後水位。D2の間隔や野球値を推測しない。
            if persisted.position_after != SourcePosition(
                d1=actual_position.d1,
                d2=actual_position.d2,
                appliedWatermark=actual_position.d1,
            ):
                raise LineupPrefixProtocolError("原本のevent水位が一致しません")
            watermark = int(actual_position.d1)
            last_d2 = int(actual_position.d2)
            _previous_binding(prior, previous, evidence.started)
            if prior.source.execution_artifact_sha256 != host.artifact_sha256:
                raise LineupPrefixProtocolError("未知実行artifactの再生はできません")
            verify_lineup_wire_seal(prior, persisted.response)
            replayed = decode_lineup_prefix_response(
                host.call(
                    "deriveLineupPlayPrefixWithContinuation",
                    prior.model_dump_json(by_alias=True, exclude_unset=True),
                )
            )
            if not replayed.ok or _canonical(_dump(replayed.value)) != _canonical(
                _dump(persisted.response.value)
            ):
                raise LineupPrefixProtocolError(
                    "実artifact再生と保存全応答が一致しません"
                )
            _validate_runner_projection(prior, replayed)
            previous = replayed
        _bound(request, evidence.started, actual)
        _previous_binding(request, previous, evidence.started)
        if (
            int(request.source.position.d1) != watermark + 1
            or int(request.source.position.applied_watermark) != watermark
            or int(request.source.position.d2) <= last_d2
            or watermark == 0
            and request.source.position.d2 != "1"
            or evidence.position != request.source.position
            or request.play_identity.event_id in seen_events
            or request.play_identity.d5 in seen_d5
            or request.play_identity.play_id in seen_plays
            or request.source.execution_artifact_sha256 != host.artifact_sha256
        ):
            raise LineupPrefixProtocolError(
                "今回位置/identity/実artifactが一致しません"
            )
        response = decode_lineup_prefix_response(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                request.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
        if response.ok:
            verify_lineup_wire_seal(request, response)
            _validate_runner_projection(request, response)
        return response


def _validate_runner_projection(
    request: LineupPrefixRequest, response: LineupPrefixSuccess
) -> None:
    """after走者をbefore走者と実T1進塁計画だけから照合する。"""
    value = response.value
    t1 = value.t1
    before = request.t1.before.state_fields
    after = t1.after.state_fields
    if before.half != after.half or before.inning != after.inning:
        expected: dict[str, tuple[str, str]] = {}
    else:
        expected = {}
        slots = {"1": "first", "2": "second", "3": "third"}
        for runner in request.source.runners:
            effect = getattr(t1.runner_default_advance, slots[runner.base])
            # forced/optionalの意味は唯一artifactで決定済み。ここでは再計算しない。
            if effect.modality == "not-applicable":
                raise LineupPrefixProtocolError("在塁走者の進塁計画がありません")
            if effect.modality == "hold":
                if effect.destination is not None:
                    raise LineupPrefixProtocolError("停止走者へ到達塁があります")
                expected[runner.base] = (
                    runner.runner_id,
                    runner.responsible_pitcher_id,
                )
            elif effect.modality in {"optional", "forced"}:
                if int(effect.destination) <= int(runner.base):
                    raise LineupPrefixProtocolError("走者の到達塁が起点以前です")
                if effect.destination == "4":
                    continue
                if effect.destination not in {"1", "2", "3"}:
                    raise LineupPrefixProtocolError("走者の到達塁が不正です")
                if effect.destination in expected:
                    raise LineupPrefixProtocolError("走者の到達塁が重複します")
                expected[effect.destination] = (
                    runner.runner_id,
                    runner.responsible_pitcher_id,
                )
            else:
                raise LineupPrefixProtocolError("走者の進塁計画が不正です")
        if t1.plate_appearance_ended and t1.batter_destination.kind == "reach":
            base = t1.batter_destination.base
            if base in expected:
                raise LineupPrefixProtocolError("打者と走者の到達塁が重複します")
            expected[base] = (
                request.source.participants.batter_id,
                request.source.participants.pitcher_id,
            )
    actual = {
        runner.base: (runner.runner_id, runner.responsible_pitcher_id)
        for runner in value.runners
    }
    if actual != expected:
        raise LineupPrefixProtocolError("after走者が実T1進塁計画と一致しません")


def _previous_binding(
    request: LineupPrefixRequest,
    previous: LineupPrefixSuccess | None,
    started: StartedLineupEvidence,
) -> None:
    """今回beforeを実前応答へ全結合する。野球値を再計算しない。"""
    source = request.source
    if previous is None:
        before = source.after.model_dump(mode="json", by_alias=True)
        del before["battingOrderBySide"]
        if (
            source.kind != "started-initial-v3"
            or _canonical(before) != _canonical(_dump(started.snapshot))
            or source.prior_artifact_sha256 != started.prior_artifact_sha256
        ):
            raise LineupPrefixProtocolError("真正開始snapshotと一致しません")
        return
    value = previous.value
    if (
        source.kind != "evaluated-prefix-v3"
        or request.prefix_ref != value.next_prefix_ref
        or source.prior_artifact_sha256 != value.execution_artifact_sha256
        or source.last_source != value.play_identity
        or _canonical(_dump(source.after)) != _canonical(_dump(value.t1.after))
        or source.t2 != value.t2
        or source.runners != value.runners
        or source.participants != value.participants
        or source.responsibility != value.next_responsibility
    ):
        raise LineupPrefixProtocolError("実前prefix全値と一致しません")


def decode_lineup_source_evidence(raw: str) -> LineupSourceEvidence:
    """履歴の未指定fieldをnull補完せず、原本frameの型/全値を保持する。"""
    try:
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        value = LineupSourceEvidence.model_validate_json(
            raw, by_alias=True, by_name=False
        )
        if _canonical(wire) != _canonical(
            value.model_dump(mode="json", by_alias=True, exclude_unset=True)
        ):
            raise ValueError("原本の型/全値が変わった")
        return value
    except (ValueError, TypeError, ValidationError):
        raise LineupPrefixProtocolError("原本frameが閉境界に適合しません") from None


class NativeLineupEvidence(_Frozen):
    """private v3の直近原本。DB取得/tenant/epoch/全物理投影は専用reader責任。"""

    expected_source: Source
    roster: InitialRosterProjection
    previous_request: LineupPrefixRequest
    previous_response: LineupPrefixSuccess


def verify_native_lineup_source(request, evidence, host):
    """全履歴を再取得せず、実checkpoint headの直近一回を独立再生する。"""
    from pitchlog.domainrt.host import NodeDomainHost

    if (
        type(request) is not LineupPrefixRequest
        or type(evidence) is not NativeLineupEvidence
        or type(host) is not NodeDomainHost
    ):
        raise TypeError("固定実型/native evidence/実hostが必要です")
    _check_frozen_members(request)
    _check_frozen_members(evidence)
    actual = lineup_from_actual_roster(evidence.roster)
    if (
        request.source != evidence.expected_source
        or request.source.lineup != actual
        or request.t1.before != request.source.after
        or request.prefix_ref != request.source.prefix_ref
    ):
        raise LineupPrefixProtocolError("native source全値が一致しません")
    if (
        request.source.roster_digest != _fingerprint(_dump(actual))
        or request.source.layout_digest != _fingerprint(_dump(actual))
        or request.source.rules_digest != _fingerprint(_dump(request.rules))
    ):
        raise LineupPrefixProtocolError("native source内容参照が一致しません")
    prior = evidence.previous_request
    if (
        prior.source.execution_artifact_sha256 != host.artifact_sha256
        or request.source.execution_artifact_sha256 != host.artifact_sha256
    ):
        raise LineupPrefixProtocolError("未登録v3保存互換は利用できません")
    verify_lineup_wire_seal(prior, evidence.previous_response)
    replayed = decode_lineup_prefix_response(
        host.call(
            "deriveLineupPlayPrefixWithContinuation",
            prior.model_dump_json(by_alias=True, exclude_unset=True),
        )
    )
    if not replayed.ok or _canonical(_dump(replayed)) != _canonical(
        _dump(evidence.previous_response)
    ):
        raise LineupPrefixProtocolError("native headの独立全応答が一致しません")
    _validate_runner_projection(prior, replayed)
    value = replayed.value
    source = request.source
    if (
        source.prefix_ref != value.next_prefix_ref
        or source.last_source != value.play_identity
        or source.after != value.t1.after
        or source.t2 != value.t2
        or source.runners != value.runners
        or source.participants != value.participants
        or source.responsibility != value.next_responsibility
        or source.lineup != value.lineup
    ):
        raise LineupPrefixProtocolError("native checkpointと実headの全値が一致しません")


def initial_lineup_source(
    *,
    tenant_id,
    game_id,
    generation,
    origin_id,
    initial,
    roster,
    rules,
    position,
    artifact_sha256,
):
    """実startedだけの未信頼初期profileを構成し、初回実artifactの検証へ渡す。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import Source

    lineup = lineup_from_actual_roster(roster)
    lineup_wire = _dump(lineup)
    after = initial.model_dump(mode="json", by_alias=True)
    after["battingOrderBySide"] = {"away": "1", "home": "1"}
    ref = {
        "version": "3",
        "scope": "play-prefix-v3",
        "tenantId": str(tenant_id),
        "gameId": str(game_id),
        "generation": generation,
        "length": "0",
        "checkpoint": {"id": str(origin_id), "revision": "1", "digest": "0" * 64},
        "historyVersion": "0",
        "origin": {"kind": "started-game", "eventId": str(origin_id)},
    }
    source = {
        "kind": "started-initial-v3",
        "prefixRef": ref,
        "rules": _dump(rules),
        "after": after,
        "t2": None,
        "historyDepth": "0",
        "playCount": "0",
        "lastSource": None,
        "position": position.model_dump(mode="json", by_alias=True),
        "priorArtifactSha256": artifact_sha256,
        "executionArtifactSha256": artifact_sha256,
        "rulesDigest": _fingerprint(_dump(rules)),
        "layoutDigest": _fingerprint(lineup_wire),
        "rosterDigest": _fingerprint(lineup_wire),
        "lineup": lineup_wire,
        "runners": [],
        "participants": {
            "batterId": lineup.away.batting_order.one,
            "pitcherId": lineup.home.pitcher_id,
            "catcherId": lineup.home.catcher_id,
            "battingOrder": "1",
        },
        "responsibility": {
            "kind": "no-change",
            "paStartSource": {"kind": "started-game", "id": str(origin_id)},
            "previousPitcherId": None,
            "strikesAtChange": None,
            "ballsAtChange": None,
        },
        "provenance": {"kind": "started-game", "eventId": str(origin_id)},
    }
    header = {k: v for k, v in ref.items() if k != "checkpoint"}
    header["checkpoint"] = {"id": str(origin_id), "revision": "1"}
    head = {
        "formatVersion": "lineup-prefix-initial-wire-head-v1",
        "prefix": header,
        "rules": source["rules"],
        "rulesDigest": source["rulesDigest"],
        "layoutDigest": source["layoutDigest"],
        "rosterDigest": source["rosterDigest"],
        "lineup": source["lineup"],
        "before": after,
        "participants": source["participants"],
        "responsibility": source["responsibility"],
        "provenance": source["provenance"],
        "priorArtifactSha256": artifact_sha256,
        "executionArtifactSha256": artifact_sha256,
    }
    ref["checkpoint"]["digest"] = _fingerprint(head)
    return Source.model_validate_json(_canonical(source), by_alias=True, by_name=False)


def require_batted_hit_observations(t1, observations) -> None:
    """原本V7の全打球観測と数学入力のタグを照合する。DB資格は発行しない。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        AppliedRunnerAdvanceOverrides,
        BattedHitT1Input,
    )
    from pitchlog.sync.first_ball_payload import FirstBallObservations
    from pitchlog.sync.terminal_pitch_payload import BattedHitPlayObservations

    if type(t1) is not BattedHitT1Input:
        if type(observations) is not FirstBallObservations:
            raise ValueError("旧投球へ打球観測を混在できません")
        return
    if type(observations) is not BattedHitPlayObservations:
        raise ValueError("安打には記録者の全明示観測が必要です")
    _check_frozen_members(t1)
    _check_frozen_members(observations)
    checked = BattedHitPlayObservations.model_validate_json(
        _canonical(_dump(observations))
    )
    if t1.before.state_fields.runners != "empty":
        if type(t1.runner_advance_overrides) is not AppliedRunnerAdvanceOverrides:
            raise ValueError("走者あり安打には明示進塁が必要です")
    elif t1.runner_advance_overrides != "not-applied":
        raise ValueError("無走者安打に進塁指定を混在できません")
    observation_override = checked.runner_advance_overrides
    if observation_override.kind == "not-applied":
        override_matches = t1.runner_advance_overrides == "not-applied"
    else:
        override_matches = type(
            t1.runner_advance_overrides
        ) is AppliedRunnerAdvanceOverrides and _canonical(
            _dump(t1.runner_advance_overrides)
        ) == _canonical(_dump(observation_override))
    if (
        _canonical(_dump(checked)) != _canonical(_dump(observations))
        or t1.result_id != checked.result_id
        or t1.official_scoring_payload != checked.official_scoring_payload.kind
        or t1.interference_ruling != checked.interference_ruling.kind
        or not override_matches
        or t1.third_out_observation != checked.third_out_observation.kind
    ):
        raise ValueError("記録者の観測と今回安打計算が一致しません")
