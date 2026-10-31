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
    expected_position = SourcePosition(d1="0", d2="0", appliedWatermark="0")
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
            if prior.source.position != expected_position:
                raise LineupPrefixProtocolError("原本順序に欠落があります")
            # 同期のevent順序だけを検査し、野球cursor/半回は計算しない。
            next_sequence = str(int(expected_position.d1) + 1)
            if any(
                value != next_sequence
                for value in persisted.position_after.model_dump(
                    mode="json", by_alias=True
                ).values()
            ):
                raise LineupPrefixProtocolError("原本のevent水位が一致しません")
            expected_position = persisted.position_after
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
            previous = replayed
        _bound(request, evidence.started, actual)
        _previous_binding(request, previous, evidence.started)
        if (
            request.source.position != expected_position
            or evidence.position != expected_position
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
        return response


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
