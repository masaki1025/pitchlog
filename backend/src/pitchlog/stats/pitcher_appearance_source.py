"""単一SQL entry投影の閉じた値境界。保存資格は発行しない。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast
from uuid import UUID


class PitcherAppearanceSourceUnavailable(ValueError):
    """原本/投影/型が不足または不一致で登板を供給できない。"""


_SHA = re.compile(r"[a-f0-9]{64}")
_FINGERPRINT = re.compile(r"(?:wire-v1:)?[a-f0-9]{64}")


@dataclass(frozen=True, slots=True)
class ProjectedPitcherEntry:
    """SQLで評価済みの値。これ自身はwriter/認可/同TX証明ではない。"""

    tenant_id: UUID
    game_id: UUID
    origin_kind: str
    source_id: UUID
    generation: int
    d1: int | None
    player_id: UUID
    defending_side: str
    inning: int
    half: str
    proof_kind: str
    artifact_sha256: str
    source_fingerprint: str


def decode_projected_entry(rows: object) -> ProjectedPitcherEntry | None:
    """1行完全形だけを受け、正当なentry無しと不正を区別する。"""
    if type(rows) is not tuple or len(rows) != 1:
        raise PitcherAppearanceSourceUnavailable("entry投影行数が不一致です")
    row = rows[0]
    if (
        type(row) is not tuple
        or len(row) != 14
        or type(row[0]) is not str
        or row[0] != "evaluated"
    ):
        raise PitcherAppearanceSourceUnavailable("entry投影が未供給です")
    (
        _,
        tenant,
        game,
        origin,
        source,
        generation,
        d1,
        player,
        side,
        inning,
        half,
        kind,
        artifact,
        fingerprint,
    ) = row
    if (
        any(type(value) is not UUID for value in (tenant, game, source))
        or type(origin) is not str
        or origin not in {"start", "play", "substitution", "reopen"}
        or type(generation) is not int
        or not 0 < generation < 2**63
        or type(artifact) is not str
        or _SHA.fullmatch(artifact) is None
        or type(fingerprint) is not str
        or _FINGERPRINT.fullmatch(fingerprint) is None
        or (origin == "start" and d1 is not None)
        or (origin != "start" and (type(d1) is not int or not 0 < d1 < 2**63))
    ):
        raise PitcherAppearanceSourceUnavailable("entryの原本identityが不一致です")
    entry = (player, side, inning, half, kind)
    if all(value is None for value in entry):
        if origin == "start":
            raise PitcherAppearanceSourceUnavailable("開始の守備投手が未供給です")
        return None
    if (
        any(value is None for value in entry)
        or type(player) is not UUID
        or type(side) is not str
        or side not in {"home", "away"}
        or type(half) is not str
        or half not in {"top", "bottom"}
        or type(inning) is not int
        or not 0 < inning < 2**63
        or type(kind) is not str
        or kind not in {"defensive-half-entry", "pitcher-defensive-entry"}
        or (origin == "start" and (half != "top" or inning != 1))
        or (side, half) not in {("home", "top"), ("away", "bottom")}
        or (origin == "substitution") != (kind == "pitcher-defensive-entry")
    ):
        raise PitcherAppearanceSourceUnavailable("entryの出場identityが不一致です")
    return ProjectedPitcherEntry(
        cast(UUID, tenant),
        cast(UUID, game),
        origin,
        cast(UUID, source),
        generation,
        cast(int | None, d1),
        player,
        side,
        inning,
        half,
        kind,
        artifact,
        fingerprint,
    )


def _positive_decimal(value: object) -> int:
    """既kernelの正準整数を型へ写し、回の計算は行わない。"""
    if type(value) is not str or re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise PitcherAppearanceSourceUnavailable("entryの既状態座標が不一致です")
    result = int(value)
    if result >= 2**63:
        raise PitcherAppearanceSourceUnavailable("entryの既状態座標が範囲外です")
    return result


def _canonical_uuid(value: object) -> UUID:
    """原本のUUID文字列を黙って正規化しない。"""
    if type(value) is not str:
        raise PitcherAppearanceSourceUnavailable("entryの原本UUIDが不一致です")
    try:
        result = UUID(value)
    except ValueError:
        raise PitcherAppearanceSourceUnavailable(
            "entryの原本UUIDが不一致です"
        ) from None
    if str(result) != value:
        raise PitcherAppearanceSourceUnavailable("entryのUUIDが非正準です")
    return result


def _transition_values(**values: object) -> dict[str, object]:
    """私有source getterが既原本を写すための値だけを作る。資格ではない。"""
    result = dict.fromkeys(
        (
            "tenant_id",
            "game_id",
            "source_id",
            "origin_kind",
            "internal_generation",
            "d1",
            "before_inning",
            "before_half",
            "after_inning",
            "after_half",
            "after_home_pitcher_id",
            "after_away_pitcher_id",
            "before_home_pitcher_id",
            "before_away_pitcher_id",
            "changed_side",
            "half_completed",
            "end_condition_detected",
            "lock_further_play",
            "outcome",
            "x_mark",
            "released_end_condition",
            "half_started_before",
            "artifact_sha256",
            "source_fingerprint",
        )
    )
    if set(values) - result.keys():
        raise PitcherAppearanceSourceUnavailable("entry sourceのmemberが不一致です")
    result.update(values)
    return result


def capture_start_transition(scope: object) -> dict[str, object]:
    """初期権保存済みの真正同actorからだけ開始片側の原本を採る。"""
    import hashlib

    from pitchlog.domainrt.host import _product_artifact_paths, _verified_source
    from pitchlog.repositories.game_start import (
        InitialStartReceipt,
        _read_start_context,
    )
    from pitchlog.repositories.initial_recording_right import InitialRecordingRightScope

    if type(scope) is not InitialRecordingRightScope:
        raise PitcherAppearanceSourceUnavailable("開始entryに真正scopeが必要です")
    scope._check()
    if (
        scope._outcome != "committed"
        or type(scope._resolved_generation) is not int
        or not 0 < scope._resolved_generation < 2**63
        or scope._start_payload is None
        or type(scope._start_receipt) is not InitialStartReceipt
        or scope._start_receipt.owner != scope._owner
    ):
        raise PitcherAppearanceSourceUnavailable("開始entryの同TX原本がありません")
    context = _read_start_context(scope._transaction, scope._start_payload)
    if context["outcome"] != "committed":
        raise PitcherAppearanceSourceUnavailable("開始entryの保存が未成立です")
    pitchers = {}
    for side in ("home", "away"):
        players = [
            row["player_id"]
            for row in context[side]
            if row["fielding_position"] == {"kind": "fielding", "position": 1}
        ]
        if len(players) != 1:
            raise PitcherAppearanceSourceUnavailable("開始entryの投手原本が不一致です")
        pitchers[side] = _canonical_uuid(players[0])
    artifact = _verified_source(*_product_artifact_paths())
    scope._check()
    return _transition_values(
        tenant_id=scope._owner.tenant_id,
        game_id=scope._owner.game_id,
        source_id=scope._owner.attempt_id,
        origin_kind="start",
        internal_generation=scope._resolved_generation,
        d1=None,
        after_inning=1,
        after_half="top",
        after_home_pitcher_id=pitchers["home"],
        after_away_pitcher_id=pitchers["away"],
        artifact_sha256=hashlib.sha256(artifact.encode()).hexdigest(),
        source_fingerprint=scope._owner.request_digest.hex(),
    )


def capture_play_transition(scope, receipt, source) -> dict[str, object]:
    """真正native receiptと同writerの保存V7/T1/T2だけから値を写す。"""
    from pitchlog.exports.record_projection import _recorded_context
    from pitchlog.sync.play_export_identity import capture_recorded_play_identity
    from pitchlog.sync.stats_native_flush import _assert_scope, _WriterScope

    if type(scope) is not _WriterScope:
        raise PitcherAppearanceSourceUnavailable("play entryに真正writerが必要です")
    _assert_scope(scope, receipt, source)
    identity = capture_recorded_play_identity(scope, receipt, source)
    payload = identity.payload
    if payload.get("formatVersion") != "play-prefix-play-v3":
        raise PitcherAppearanceSourceUnavailable("entryの未対応保存profileです")
    before_lineup, _ = _recorded_context(identity)
    if before_lineup is None:
        raise PitcherAppearanceSourceUnavailable("entryの保存名簿が未供給です")
    try:
        before = payload["calculation"]["request"]["t1"]["before"]["stateFields"]
        value = payload["calculation"]["response"]["value"]
        after = value["t1"]["after"]["stateFields"]
        facts, decision = value["t2"]["facts"], value["t2"]["decision"]
        if (
            facts["beforeHalf"] != before["state.half"]
            or facts["afterHalf"] != after["state.half"]
            or facts["beforeInning"] != before["state.inning"]
            or facts["afterInning"] != after["state.inning"]
        ):
            raise PitcherAppearanceSourceUnavailable("entryの既T2座標が不一致です")
        result = _transition_values(
            tenant_id=source.tenant_id,
            game_id=source.game_id,
            source_id=source.source_event_id,
            origin_kind="play",
            internal_generation=source.generation,
            d1=source.d1,
            before_inning=_positive_decimal(before["state.inning"]),
            before_half=before["state.half"],
            after_inning=_positive_decimal(after["state.inning"]),
            after_half=after["state.half"],
            before_home_pitcher_id=_canonical_uuid(before_lineup["home"]["pitcherId"]),
            before_away_pitcher_id=_canonical_uuid(before_lineup["away"]["pitcherId"]),
            after_home_pitcher_id=_canonical_uuid(value["lineup"]["home"]["pitcherId"]),
            after_away_pitcher_id=_canonical_uuid(value["lineup"]["away"]["pitcherId"]),
            half_completed=facts["halfCompleted"],
            end_condition_detected=decision["endConditionDetected"],
            lock_further_play=decision["lockFurtherPlayInput"],
            outcome=decision["outcome"],
            x_mark=decision["xMark"],
            artifact_sha256=value["executionArtifactSha256"],
            source_fingerprint=source.event_fingerprint,
        )
    except (KeyError, TypeError):
        raise PitcherAppearanceSourceUnavailable(
            "entryの既kernel出力が未供給です"
        ) from None
    _assert_scope(scope, receipt, source)
    return result


def capture_substitution_transition(handle, writer, event) -> dict[str, object]:
    """同一実Execution/consume済み保存印の交代だけをentry入力へ写す。"""
    from pitchlog.domainrt.first_ball_projection import _canonical_json
    from pitchlog.repositories import transaction
    from pitchlog.sync import substitution_execution as execution

    if type(handle) is not transaction._TenantTransaction:
        raise PitcherAppearanceSourceUnavailable("交代entryに真正handleが必要です")
    state = execution._EXECUTIONS.get(handle._state_key)
    if (
        state is None
        or state.phase != "consumed"
        or state.projected is not event
        or state.writer is not writer
        or state.anchor is None
    ):
        raise PitcherAppearanceSourceUnavailable("交代entryの同TX保存印がありません")
    execution._live(state)
    if state.anchor[4:] != (
        _canonical_json(state.before),
        _canonical_json(state.after),
        _canonical_json(state.transition),
    ):
        raise PitcherAppearanceSourceUnavailable(
            "交代entryの実評価原本が変更されました"
        )
    try:
        before = state.before["checkpoint"]["content"]["restored"]
        after = state.after["checkpoint"]["content"]["restored"]
        before_fields = before["current"]["stateFields"]
        after_fields = after["current"]["stateFields"]
        selected = state.source.read(handle, state.event)
        result = _transition_values(
            tenant_id=state.source.phase.attempt.tenant_id,
            game_id=state.source.phase.attempt.game_id,
            source_id=_canonical_uuid(state.payload.to_wire()["eventId"]),
            origin_kind="substitution",
            internal_generation=state.source.phase.attempt.internal_generation,
            d1=state.event.d1,
            before_inning=_positive_decimal(before_fields["state.inning"]),
            before_half=before_fields["state.half"],
            after_inning=_positive_decimal(after_fields["state.inning"]),
            after_half=after_fields["state.half"],
            before_home_pitcher_id=_canonical_uuid(
                before["lineup"]["home"]["pitcherId"]
            ),
            before_away_pitcher_id=_canonical_uuid(
                before["lineup"]["away"]["pitcherId"]
            ),
            after_home_pitcher_id=_canonical_uuid(after["lineup"]["home"]["pitcherId"]),
            after_away_pitcher_id=_canonical_uuid(after["lineup"]["away"]["pitcherId"]),
            changed_side=state.payload.to_wire()["operation"]["side"],
            artifact_sha256=state.artifact,
            source_fingerprint=selected.event_fingerprint,
        )
    except (KeyError, TypeError):
        raise PitcherAppearanceSourceUnavailable(
            "交代entryの原本contextが不一致です"
        ) from None
    execution._live(state)
    return result
