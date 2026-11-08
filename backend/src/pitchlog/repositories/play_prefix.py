"""v2の実source readerとstorage anchor/wire headの別表現。資格はJSONから発行しない。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import model_validator

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.first_pitch import _Frozen, _invalid_constant, _unique_object
from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    T2,
    Lineup,
    Origin,
    PaStart,
    PrefixRef,
    Runner,
)
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    Participants as LineupParticipants,
)
from pitchlog.domainrt.play_prefix_continuation import (
    BridgeEvidence,
    Participants,
    PaStartSource,
    PlayPrefixRef,
    PlayPrefixSource,
    PlayT2,
    RunnerSnapshot,
)
from pitchlog.domainrt.strikeout_pitch import StrikeoutSnapshot
from pitchlog.domainrt.terminal_pitch import TerminalSnapshot
from pitchlog.repositories.ordinary_prefix import (
    Digest,
    Nonnegative,
    OrdinaryPrefixError,
    Positive,
    PrefixSource,
    _locked_prefix_context,
    read_confirmed_ordinary_prefix,
)
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixCheckpointLockToken


class StorageAnchor(_Frozen):
    """不変private row ID/履歴epoch。wire headと同名に読み替えない。"""

    id: str
    history_epoch: Positive


class ProjectionSnapshot(_Frozen):
    """全物理列はmapper/DB stampでも独立検査する。"""

    play_row: dict[str, object]
    play_runners: tuple[dict[str, object], ...]


class PlayPrefixDocument(_Frozen):
    """private version2。旧raw v1 documentとは別の閉型。"""

    version: Literal["2"]
    id: str
    revision: Positive
    history_version: Positive
    storage_anchor: StorageAnchor
    prefix_ref: PlayPrefixRef
    wire_d4: str
    internal_generation: Positive
    recovery_generation: Positive
    confirmed_watermark: Nonnegative
    applied_watermark: Nonnegative
    last_source: PrefixSource
    history_depth: Nonnegative
    after: TerminalSnapshot
    rules: SavedRuleWire
    t2: PlayT2
    runners: tuple[RunnerSnapshot, ...]
    participants: Participants
    pa_start_source: PaStartSource
    roster_digest: Digest
    content_digest: Digest
    artifact_sha256: Digest
    state: Literal["current", "invalidated"]
    bridge_origin: BridgeEvidence
    projection_snapshot: ProjectionSnapshot

    @model_validator(mode="after")
    def _binding(self):
        """物理anchor/epochと論理headの全相関を検査する。"""
        if (
            str(UUID(self.id)) != self.id
            or self.storage_anchor.id != self.id
            or self.history_version != self.storage_anchor.history_epoch
            or self.prefix_ref.checkpoint.revision != self.revision
            or self.wire_d4 != self.prefix_ref.generation
            or self.confirmed_watermark != self.applied_watermark
            or self.last_source.d1 != self.confirmed_watermark
            or self.last_source.tenant_id != self.prefix_ref.tenant_id
            or self.last_source.game_id != self.prefix_ref.game_id
            or self.last_source.generation != self.internal_generation
            or self.history_depth != self.prefix_ref.length
        ):
            raise ValueError("v2 checkpointの原本相関が不一致")
        raw = self.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if (
            source_fingerprint({k: v for k, v in raw.items() if k != "content_digest"})
            != self.content_digest
        ):
            raise ValueError("v2 private full digest不一致")
        from pitchlog.db.game_state.models import PlayRow, PlayRunner

        if set(self.projection_snapshot.play_row) != set(PlayRow.__table__.c.keys()):
            raise ValueError("41列不一致")
        if any(
            set(r) != set(PlayRunner.__table__.c.keys())
            for r in self.projection_snapshot.play_runners
        ):
            raise ValueError("runner10列不一致")
        return self


def read_play_prefix_document(raw: str) -> PlayPrefixDocument:
    """余剰/重複/非有限/黙った正規化を拒否する。"""
    try:
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        result = PlayPrefixDocument.model_validate_json(raw)
        if _canonical_json(wire) != _canonical_json(
            result.model_dump(mode="json", by_alias=True, exclude_unset=True)
        ):
            raise ValueError
        return result
    except (ValueError, TypeError, KeyError, AttributeError):
        raise OrdinaryPrefixError from None


def _require_legacy_compatibility(
    digest: str, execution_digest: str, *, source_format="ordinary-pitch-play-v1"
):
    """rootの有限witness登録がない旧artifactを自己申告で採用しない。"""
    from pathlib import Path

    try:
        root = Path(__file__).resolve().parents[4]
        data = json.loads(
            (
                root / "contracts/state-transition/play_prefix_v2_source_compat"
                "ibility_v1.json"
            ).read_text()
        )
        if source_format == "play-prefix-play-v3":
            _require_v3_compatibility(root, digest, execution_digest)
            return
        operations = ["deriveState", "deriveFirstPitchWithContinuation"]
        if source_format == "ordinary-pitch-play-v1":
            operations += ["deriveOrdinaryPitch", "deriveOrdinaryPitchWithContinuation"]
        elif source_format != "first-ball-play-v1":
            raise ValueError
        if data.get("version") != "1" or not any(
            r.get("priorArtifactSha256") == digest
            and r.get("executionArtifactSha256") == execution_digest
            and r.get("sourceFormat") == source_format
            and r.get("compatibleOperations") == operations
            and type(r.get("witnessSha256")) is str
            and re.fullmatch(r"[a-f0-9]{64}", r["witnessSha256"]) is not None
            for r in data["cases"]
        ):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise OrdinaryPrefixError from None


@dataclass(frozen=True, slots=True)
class ConfirmedPlayPrefix:
    """実同TXで読み取ったraw storage-beforeと数学source。"""

    checkpoint: object
    source: PlayPrefixSource
    roster: InitialRosterProjection
    bootstrap: bool
    next_play_number: int


def read_confirmed_play_prefix(handle, event, source, *, proposal, artifact_sha256):
    """自由recordではなく既実writer/sourceから全原本を照合する。"""
    from pitchlog.authz.terminal_pitch_product import require_registered_product
    from pitchlog.repositories.ordinary_prefix import read_checkpoint_document
    from pitchlog.repositories.ordinary_prefix_read import _function_one

    require_registered_product(artifact_sha256=artifact_sha256)
    run, live, tenant, game, generation, epoch, watermark, lease = (
        _locked_prefix_context(handle, event, source)
    )
    row = _function_one(
        handle,
        PlayPrefixCheckpointLockToken(
            lease.attempt_id,
            lease.phase_id,
            lease.nonce,
            lease.device_id,
            game,
            generation,
        ),
    )
    live()
    if row is not None and row.get("content", {}).get("version") == "2":
        doc = read_play_prefix_document(_canonical_json(row["content"]))
        return _verified_v2(
            handle,
            event,
            source,
            proposal,
            row,
            doc,
            tenant,
            generation,
            epoch,
            watermark,
            artifact_sha256,
        )
    if row is not None:
        _verify_source_evidence(row, bridge=True)
    prior_digest = artifact_sha256
    if row is not None:
        legacy = read_checkpoint_document(_canonical_json(row["content"]))
        prior_digest = legacy.artifact_sha256
    else:
        # first-ball原本のartifactは既readerが検証した実payloadから取得する。
        from pitchlog.repositories.recorded_snapshot import (
            RecordedCalculationCandidate,
            try_read_recorded_snapshot,
        )

        if watermark == 1:
            initial = try_read_recorded_snapshot(handle, game, play_prefix_compat=True)
            if type(initial) is not RecordedCalculationCandidate:
                raise OrdinaryPrefixError
            prior_digest = initial.payload.v7.calculation.artifact_sha256
    if watermark > 0:
        _require_legacy_compatibility(
            prior_digest,
            artifact_sha256,
            source_format="first-ball-play-v1"
            if row is None
            else "ordinary-pitch-play-v1",
        )
    legacy = read_confirmed_ordinary_prefix(
        handle, event, source, artifact_sha256=prior_digest, play_prefix_compat=True
    )
    doc = legacy.checkpoint
    q = proposal.model_dump(mode="json", by_alias=True, exclude_unset=True)
    raw = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if legacy.bootstrap:
        # 未保存anchorだけを元D5提案へ固定。保存済anchorは絶対に置換しない。
        raw["id"] = q["prefixRef"]["checkpoint"]["id"]
        raw["content_digest"] = source_fingerprint(
            {k: v for k, v in raw.items() if k != "content_digest"}
        )
        doc = read_checkpoint_document(_canonical_json(raw))
    if q["prefixRef"]["checkpoint"] != {
        "id": doc.id,
        "revision": doc.revision,
        "digest": doc.content_digest,
    }:
        raise OrdinaryPrefixError
    ref = {
        "version": "2",
        "scope": "play-prefix-v2",
        "tenantId": str(tenant),
        "gameId": str(game),
        "generation": event.d4,
        "length": doc.prefix_ref.length,
        "checkpoint": q["prefixRef"]["checkpoint"],
        "historyVersion": "1",
        "origin": doc.prefix_ref.model_dump(mode="json", by_alias=True),
    }
    last = (
        None
        if doc.last_source is None
        else {
            "eventId": doc.last_source.id,
            "d5": doc.last_source.d5,
            "playId": str(_last_play_id(run, game, doc.last_source.id)),
        }
    )
    bridge = {
        "kind": "started-initial" if watermark == 0 else "ordinary-only-confirmed",
        "v1Ref": ref["origin"],
        "ordinaryPlayCount": ref["length"],
        "allPlayCount": ref["length"],
        "historyDepth": doc.history_depth,
        "lastSource": last,
        "priorArtifactSha256": doc.artifact_sha256,
        "rulesDigest": source_fingerprint(
            doc.rules.model_dump(mode="json", by_alias=True)
        ),
        "layoutDigest": doc.roster_digest,
        "checkpoint": ref["checkpoint"],
    }
    from pitchlog.sync.ordinary_pitch_payload import select_ordinary_pitch_participants

    people = select_ordinary_pitch_participants(legacy.roster, doc.after)
    before = doc.after.model_dump(mode="json", by_alias=True)
    if before["stateFields"]["state.runners"] != "empty":
        raise OrdinaryPrefixError
    math_source = {
        "kind": "bridged-v1",
        "prefixRef": ref,
        "rules": doc.rules.model_dump(mode="json", by_alias=True),
        "after": before,
        "t2": None if doc.t2 is None else doc.t2.model_dump(mode="json", by_alias=True),
        "historyDepth": doc.history_depth,
        "playCount": ref["length"],
        "lastSource": last,
        "position": q["source"]["position"],
        "priorArtifactSha256": doc.artifact_sha256,
        "executionArtifactSha256": artifact_sha256,
        "rulesDigest": bridge["rulesDigest"],
        "layoutDigest": bridge["layoutDigest"],
        "runners": [],
        "participants": {
            k: v
            for k, v in people.model_dump(mode="json", by_alias=True).items()
            if k != "catcherId"
        },
        "nextBatter": _next_batter(
            legacy.roster, doc.after, proposal.t1.result_id, proposal
        ),
        "bridge": bridge,
        "responsibility": {
            "kind": "no-change",
            "paStartSource": {"kind": "started-game", "id": str(game)},
            "previousPitcherId": None,
            "strikesAtChange": None,
            "ballsAtChange": None,
        },
    }
    _check_position(proposal, event, watermark)
    return ConfirmedPlayPrefix(
        doc,
        PlayPrefixSource.model_validate_json(_canonical_json(math_source)),
        legacy.roster,
        legacy.bootstrap,
        legacy.next_play_number,
    )


def _last_play_id(run, game, event_id):
    from pitchlog.repositories.first_ball_operations import PLAY_ROW_COLUMNS, _one
    from pitchlog.sync.first_ball_tokens import FirstBallPlayRowReadToken

    row = _one(run(FirstBallPlayRowReadToken(game, UUID(event_id))), PLAY_ROW_COLUMNS)
    return row["id"]


def _check_position(proposal, event, watermark):
    if proposal.source.position.d1 != str(
        event.d1
    ) or proposal.source.position.applied_watermark != str(watermark):
        raise OrdinaryPrefixError
    if proposal.play_identity.d5 != event.d5:
        raise OrdinaryPrefixError


def _next_batter(roster, before, result_id, proposal):
    """提案された順の実playerを照合する。次打順自体はartifactが決める。"""
    if result_id not in ("batting-result.walk", "batting-result.hit-by-pitch"):
        return None
    candidate = proposal.source.next_batter
    if candidate is None:
        raise OrdinaryPrefixError
    from pitchlog.domainrt.first_pitch import StateSnapshot
    from pitchlog.sync.ordinary_pitch_payload import select_ordinary_pitch_participants

    raw = before.model_dump(mode="json", by_alias=True)
    raw["stateFields"]["state.battingOrder"] = candidate.batting_order
    raw["stateFields"]["state.runners"] = "empty"
    people = select_ordinary_pitch_participants(
        roster, StateSnapshot.model_validate_json(_canonical_json(raw))
    )
    if people.batter_id != candidate.batter_id:
        raise OrdinaryPrefixError
    return {"batterId": people.batter_id, "battingOrder": people.batting_order}


def _verified_v2(
    handle,
    event,
    source,
    proposal,
    row,
    doc,
    tenant,
    generation,
    epoch,
    watermark,
    artifact_sha256,
):
    """現pointと実event/ledger/全投影を同tenantで再結合する。"""
    from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
    from pitchlog.repositories.first_ball_operations import PLAY_ROW_COLUMNS, _one
    from pitchlog.sync.first_ball_tokens import FirstBallPlayRowReadToken
    from pitchlog.sync.terminal_pitch_payload import (
        TerminalPitchPlayPayload,
        verify_play_prefix_seal,
    )
    from pitchlog.sync.tokens import IdempotencyLedgerReadToken, OperationEventReadToken

    if any(
        row[k] != v
        for k, v in {
            "tenant_id": str(tenant),
            "game_id": event.game_id,
            "internal_generation": generation,
            "id": doc.id,
            "revision": int(doc.revision),
            "history_version": int(doc.history_version),
            "recovery_generation": epoch,
            "confirmed_watermark": watermark,
            "applied_watermark": watermark,
            "content_digest": doc.content_digest,
            "state": "current",
        }.items()
    ):
        raise OrdinaryPrefixError
    if (
        doc.prefix_ref.tenant_id != str(tenant)
        or doc.prefix_ref.game_id != event.game_id
        or doc.wire_d4 != event.d4
        or doc.internal_generation != str(generation)
        or doc.recovery_generation != str(epoch)
        or doc.confirmed_watermark != str(watermark)
    ):
        raise OrdinaryPrefixError
    _verify_source_evidence(row, bridge=False)
    if source_fingerprint(row["roster"]) != doc.roster_digest:
        raise OrdinaryPrefixError
    roster = InitialRosterProjection.model_validate_json(_canonical_json(row["roster"]))
    ev = _one(
        handle.run(
            OperationEventReadToken(
                UUID(event.game_id), generation, int(doc.last_source.d1)
            )
        ),
        tuple(OperationEvent.__table__.c.keys()),
    )
    ledger = _one(
        handle.run(IdempotencyLedgerReadToken(UUID(doc.last_source.d5))),
        tuple(IdempotencyLedger.__table__.c.keys()),
    )
    play = _one(
        handle.run(
            FirstBallPlayRowReadToken(UUID(event.game_id), UUID(doc.last_source.id))
        ),
        PLAY_ROW_COLUMNS,
    )
    if (
        ev["tenant_id"] != tenant
        or ev["game_id"] != UUID(event.game_id)
        or ev["id"] != UUID(doc.last_source.id)
        or ev["d5"] != UUID(doc.last_source.d5)
        or ev["ledger_kind"] != "accepted"
        or ev["event_kind"] != "play_input"
        or any(
            ev[k] is not None
            for k in (
                "replaced_at",
                "retired_at",
                "import_batch_id",
                "legacy_row_identifier",
            )
        )
        or ev["is_tombstone"]
        or ev["migration_unverified"]
        or ledger["tenant_id"] != tenant
        or ledger["kind"] != "accepted"
        or ledger["retired_at"] is not None
        or ledger["import_batch_id"] is not None
        or ledger["source_fingerprint"] != doc.last_source.source_fingerprint
    ):
        raise OrdinaryPrefixError
    from pitchlog.sync.idempotency import _json_value

    payload = TerminalPitchPlayPayload.model_validate_json(
        _canonical_json(_json_value(ev["payload"]))
    )
    verify_play_prefix_seal(payload.calculation)
    response = payload.calculation.response.value
    if (
        response.next_prefix_ref != doc.prefix_ref
        or response.t1.after != doc.after
        or response.t2 != doc.t2
        or response.runners != doc.runners
        or response.participants != doc.participants
        or payload.calculation.artifact_sha256 != doc.artifact_sha256
        or _json_value(ev["state_diff"])
        != response.new_history_entry.difference.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
    ):
        raise OrdinaryPrefixError
    actual = {k: str(v) if type(v) is UUID else v for k, v in play.items()}
    if actual != doc.projection_snapshot.play_row or row.get("last_play_row") != actual:
        raise OrdinaryPrefixError
    if row.get("last_play_runners") != list(doc.projection_snapshot.play_runners):
        raise OrdinaryPrefixError
    if (
        proposal.prefix_ref != doc.prefix_ref
        or proposal.t1.before != doc.after
        or proposal.rules != doc.rules
    ):
        raise OrdinaryPrefixError
    _check_position(proposal, event, watermark)
    people = doc.participants
    before = doc.after
    candidate = _next_batter(roster, before, proposal.t1.result_id, proposal)
    q = proposal.model_dump(mode="json", by_alias=True, exclude_unset=True)
    math_source = {
        "kind": "evaluated-prefix-v2",
        "prefixRef": doc.prefix_ref.model_dump(mode="json", by_alias=True),
        "rules": doc.rules.model_dump(mode="json", by_alias=True),
        "after": before.model_dump(mode="json", by_alias=True),
        "t2": doc.t2.model_dump(mode="json", by_alias=True),
        "historyDepth": doc.history_depth,
        "playCount": doc.prefix_ref.length,
        "lastSource": {
            "eventId": doc.last_source.id,
            "d5": doc.last_source.d5,
            "playId": str(play["id"]),
        },
        "position": q["source"]["position"],
        "priorArtifactSha256": doc.artifact_sha256,
        "executionArtifactSha256": artifact_sha256,
        "rulesDigest": source_fingerprint(
            doc.rules.model_dump(mode="json", by_alias=True)
        ),
        "layoutDigest": doc.roster_digest,
        "runners": [r.model_dump(mode="json", by_alias=True) for r in doc.runners],
        "participants": people.model_dump(mode="json", by_alias=True),
        "nextBatter": candidate,
        "bridge": None,
        "responsibility": {
            "kind": "no-change",
            "paStartSource": doc.pa_start_source.model_dump(mode="json", by_alias=True),
            "previousPitcherId": None,
            "strikesAtChange": None,
            "ballsAtChange": None,
        },
    }
    source.read(handle, event)
    play_number = play["play_number"]
    if type(play_number) is not int or not 0 < play_number < 2**63 - 1:
        raise OrdinaryPrefixError
    return ConfirmedPlayPrefix(
        doc,
        PlayPrefixSource.model_validate_json(_canonical_json(math_source)),
        roster,
        False,
        play_number + 1,
    )


def _verify_source_evidence(row, *, bridge):
    """SQL集約の実全play/履歴/非play証拠を確認し、JSON自己申告で補わない。"""
    e = row.get("source_evidence")
    expected_keys = {
        "all_play_count",
        "ordinary_play_count",
        "invalid_count",
        "non_play_count",
        "history_count",
        "pa_change_count",
    }
    if (
        type(e) is not dict
        or set(e) != expected_keys
        or any(type(v) is not int or v < 0 for v in e.values())
        or e["invalid_count"] != 0
        or e["pa_change_count"] != 0
        or e["all_play_count"] != int(row["content"]["prefix_ref"]["length"])
        or e["history_count"] != int(row["content"]["history_depth"])
    ):
        raise OrdinaryPrefixError
    if bridge and (
        e["non_play_count"] != 0 or e["ordinary_play_count"] != e["all_play_count"]
    ):
        raise OrdinaryPrefixError


class LineupPrefixDocument(_Frozen):
    """private version3。両cursor/実配置とwire/物理anchorを別々に保持する。"""

    version: Literal["3"]
    id: str
    revision: Positive
    history_version: Positive
    storage_anchor: StorageAnchor
    prefix_ref: PrefixRef
    wire_d4: str
    internal_generation: Positive
    recovery_generation: Positive
    confirmed_watermark: Nonnegative
    applied_watermark: Nonnegative
    last_source: PrefixSource | None
    history_depth: Nonnegative
    after: StrikeoutSnapshot
    rules: SavedRuleWire
    t2: T2 | None
    runners: tuple[Runner, ...]
    participants: LineupParticipants
    pa_start_source: PaStart
    lineup: Lineup
    roster_digest: Digest
    roster_source_digest: Digest
    source_origin: Origin
    previous_prefix_ref: PrefixRef | None
    content_digest: Digest
    artifact_sha256: Digest
    state: Literal["current", "invalidated"]
    projection_snapshot: ProjectionSnapshot | None

    @model_validator(mode="after")
    def _native_binding(self):
        """JSON全内容と位置だけを検査し、野球値は再計算しない。"""
        if (
            str(UUID(self.id)) != self.id
            or self.storage_anchor.id != self.id
            or self.history_version != self.storage_anchor.history_epoch
            or self.prefix_ref.checkpoint.revision != self.revision
            or self.wire_d4 != self.prefix_ref.generation
            or self.prefix_ref.origin != self.source_origin
            or self.confirmed_watermark != self.applied_watermark
            or self.prefix_ref.length != self.history_depth
        ):
            raise ValueError("v3 private位置が不一致")
        if self.last_source is None:
            if (
                self.confirmed_watermark != "0"
                or self.projection_snapshot is not None
                or self.t2 is not None
                or self.previous_prefix_ref is not None
            ):
                raise ValueError("v3初期原本が不一致")
        elif (
            self.last_source.d1 != self.confirmed_watermark
            or self.last_source.game_id != self.prefix_ref.game_id
            or self.last_source.tenant_id != self.prefix_ref.tenant_id
            or self.last_source.generation != self.internal_generation
            or self.projection_snapshot is None
            or self.previous_prefix_ref is None
        ):
            raise ValueError("v3 head原本が不一致")
        raw = self.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if (
            source_fingerprint({k: v for k, v in raw.items() if k != "content_digest"})
            != self.content_digest
        ):
            raise ValueError("v3 full content digest不一致")
        return self


def read_lineup_prefix_document(raw):
    """Private v3も余剰/重複/非有限/型変更を拒否する。"""
    try:
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        doc = LineupPrefixDocument.model_validate_json(raw)
        if _canonical_json(wire) != _canonical_json(
            doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
        ):
            raise ValueError
        return doc
    except (ValueError, TypeError, KeyError):
        raise OrdinaryPrefixError from None


@dataclass(frozen=True, slots=True)
class ConfirmedLineupPrefix:
    """取得済み実source。単体ではwrite frame/記録権を発行しない。"""

    checkpoint: LineupPrefixDocument
    source: object
    roster: InitialRosterProjection
    bootstrap: bool
    next_play_number: int
    previous_payload: object = None


def _lineup_started_origin(handle, game, generation):
    """旧deviceの現在状態は参照せず、実成功logical原本だけを読む。"""
    from pitchlog.repositories.ordinary_prefix_read import _function_one
    from pitchlog.sync.terminal_pitch_tokens import LineupStartedOriginReadToken

    origin = _function_one(handle, LineupStartedOriginReadToken(game, generation))
    if (
        type(origin) is not dict
        or set(origin) != {"start_request_id", "device_id"}
        or any(type(v) is not str or str(UUID(v)) != v for v in origin.values())
    ):
        raise OrdinaryPrefixError
    return origin["start_request_id"]


def _initial_lineup_document(initial, origin, d4, epoch, artifact_sha256, position):
    """初期logical refをactual start_request_idへ固定する。物理rowは作らない。"""
    from pitchlog.domainrt.lineup_prefix_source import initial_lineup_source

    source = initial_lineup_source(
        tenant_id=initial.tenant_id,
        game_id=initial.game_id,
        generation=d4,
        origin_id=origin,
        initial=initial.before,
        roster=initial.roster,
        rules=initial.rules,
        position=position,
        artifact_sha256=artifact_sha256,
    )
    doc = {
        "version": "3",
        "id": origin,
        "revision": "1",
        "history_version": "1",
        "storage_anchor": {"id": origin, "history_epoch": "1"},
        "prefix_ref": source.prefix_ref.model_dump(mode="json", by_alias=True),
        "wire_d4": d4,
        "internal_generation": str(initial.generation),
        "recovery_generation": str(epoch),
        "confirmed_watermark": "0",
        "applied_watermark": "0",
        "last_source": None,
        "history_depth": "0",
        "after": source.after.model_dump(mode="json", by_alias=True),
        "rules": source.rules.model_dump(mode="json", by_alias=True),
        "t2": None,
        "runners": [],
        "participants": source.participants.model_dump(mode="json", by_alias=True),
        "pa_start_source": source.responsibility.pa_start_source.model_dump(
            mode="json", by_alias=True
        ),
        "lineup": source.lineup.model_dump(mode="json", by_alias=True),
        "roster_digest": source.roster_digest,
        "roster_source_digest": source_fingerprint(
            initial.roster.model_dump(mode="json")
        ),
        "source_origin": source.prefix_ref.origin.model_dump(
            mode="json", by_alias=True
        ),
        "previous_prefix_ref": None,
        "artifact_sha256": artifact_sha256,
        "state": "current",
        "projection_snapshot": None,
    }
    doc["content_digest"] = source_fingerprint(doc)
    return read_lineup_prefix_document(_canonical_json(doc)), source


def _source_from_lineup_document(doc, position, artifact_sha256, last_identity):
    """Actual native headを写す。cursor/次投捕を再計算しない。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import Source

    kind = "evaluated-prefix-v3"
    if doc.t2.decision.lock_further_play_input or doc.t2.tiebreak_start_required:
        kind = "locked-prefix-v3"
    source = {
        "kind": kind,
        "prefixRef": doc.prefix_ref.model_dump(mode="json", by_alias=True),
        "rules": doc.rules.model_dump(mode="json", by_alias=True),
        "after": doc.after.model_dump(mode="json", by_alias=True),
        "t2": doc.t2.model_dump(mode="json", by_alias=True),
        "historyDepth": doc.history_depth,
        "playCount": doc.prefix_ref.length,
        "lastSource": last_identity.model_dump(mode="json", by_alias=True),
        "position": position.model_dump(mode="json", by_alias=True),
        "priorArtifactSha256": doc.artifact_sha256,
        "executionArtifactSha256": artifact_sha256,
        "rulesDigest": source_fingerprint(
            doc.rules.model_dump(mode="json", by_alias=True)
        ),
        "layoutDigest": doc.roster_digest,
        "rosterDigest": doc.roster_digest,
        "lineup": doc.lineup.model_dump(mode="json", by_alias=True),
        "runners": [r.model_dump(mode="json", by_alias=True) for r in doc.runners],
        "participants": doc.participants.model_dump(mode="json", by_alias=True),
        "responsibility": {
            "kind": "no-change",
            "paStartSource": doc.pa_start_source.model_dump(mode="json", by_alias=True),
            "previousPitcherId": None,
            "strikesAtChange": None,
            "ballsAtChange": None,
        },
        "provenance": {
            "kind": "confirmed-prefix",
            "checkpoint": doc.prefix_ref.checkpoint.model_dump(
                mode="json", by_alias=True
            ),
            "sourceIdentity": last_identity.model_dump(mode="json", by_alias=True),
            "historyDepth": doc.history_depth,
        },
    }
    return Source.model_validate_json(
        _canonical_json(source), by_alias=True, by_name=False
    )


def read_confirmed_lineup_prefix(handle, event, source, *, proposal, artifact_sha256):
    """既live writer/lock下でactual zero又はnative CPへ結合し、旧v2を補完しない。"""
    from pitchlog.authz.terminal_pitch_product import require_registered_product
    from pitchlog.domainrt.lineup_play_prefix_continuation import SourcePosition
    from pitchlog.repositories.ordinary_prefix_read import _function_one
    from pitchlog.repositories.started_snapshot import read_initial_started_snapshot

    require_registered_product(
        artifact_sha256=artifact_sha256, mode="play-prefix-play-v3"
    )
    run, live, tenant, game, generation, epoch, watermark, lease = (
        _locked_prefix_context(handle, event, source)
    )
    row = _function_one(
        handle,
        PlayPrefixCheckpointLockToken(
            lease.attempt_id,
            lease.phase_id,
            lease.nonce,
            lease.device_id,
            game,
            generation,
        ),
    )
    live()
    origin = _lineup_started_origin(handle, game, generation)
    live()
    position = SourcePosition(
        d1=str(event.d1),
        d2=proposal.source.position.d2,
        appliedWatermark=str(watermark),
    )
    if event.d1 != watermark + 1 or proposal.play_identity.d5 != event.d5:
        raise OrdinaryPrefixError
    if row is None:
        if watermark != 0:
            raise OrdinaryPrefixError
        initial = read_initial_started_snapshot(handle, game)
        doc, actual_source = _initial_lineup_document(
            initial, origin, event.d4, epoch, artifact_sha256, position
        )
        live()
        if (
            proposal.source != actual_source
            or proposal.prefix_ref != doc.prefix_ref
            or proposal.t1.before != doc.after
            or proposal.rules != doc.rules
        ):
            raise OrdinaryPrefixError
        return ConfirmedLineupPrefix(doc, actual_source, initial.roster, True, 1)
    if row.get("content", {}).get("version") != "3":
        raise OrdinaryPrefixError
    doc = read_lineup_prefix_document(_canonical_json(row["content"]))
    _check_native_lineup_row(
        row,
        doc,
        tenant=tenant,
        game=game,
        generation=generation,
        epoch=epoch,
        watermark=watermark,
    )
    if (
        doc.source_origin.event_id != origin
        or doc.prefix_ref.generation != event.d4
        or doc.internal_generation != str(generation)
        or doc.recovery_generation != str(epoch)
        or doc.confirmed_watermark != str(watermark)
    ):
        raise OrdinaryPrefixError
    roster = InitialRosterProjection.model_validate_json(_canonical_json(row["roster"]))
    if source_fingerprint(row["roster"]) != doc.roster_source_digest:
        raise OrdinaryPrefixError
    from pitchlog.repositories.past_correction_current import (
        PastCorrectionCurrentUnavailable,
        verify_p3_current_packet,
    )
    from pitchlog.repositories.past_correction_current_paged import (
        read_verified_p3_paged_current,
    )
    from pitchlog.repositories.past_correction_right import _ReadP3CurrentToken

    try:
        paged = read_verified_p3_paged_current(
            handle, game, generation, selected_after_d1=0, selected_limit=25
        )
    except PastCorrectionCurrentUnavailable:
        raise OrdinaryPrefixError from None
    p3_packet = (
        None
        if paged is not None
        else _function_one(handle, _ReadP3CurrentToken(game, generation))
    )
    if paged is None and (
        p3_packet is None or p3_packet.get("kind") not in {"none", "p3-current"}
    ):
        raise OrdinaryPrefixError
    if paged is not None or (
        p3_packet is not None and p3_packet["kind"] == "p3-current"
    ):
        _verify_source_evidence(row, bridge=False)
        if row["source_evidence"]["non_play_count"] != 0:
            raise OrdinaryPrefixError
        try:
            if paged is None:
                verified = verify_p3_current_packet(
                    p3_packet, tenant=tenant, game=game, generation=generation
                )
                payload = verified.payloads[-1]
                last_play = verified.items[-1]["play_row"]
            else:
                verified = paged
                payload = paged.last_payload
                last_play = paged.last_item["play_row"]
        except PastCorrectionCurrentUnavailable:
            raise OrdinaryPrefixError from None
        if verified.checkpoint != doc:
            raise OrdinaryPrefixError
        if type(last_play) is not dict:
            raise OrdinaryPrefixError
        play_number = last_play.get("play_number")
        if type(play_number) is not int or play_number < 1:
            raise OrdinaryPrefixError
    else:
        payload, play_number = _read_native_lineup_head(handle, game, tenant, row, doc)
    actual_source = _source_from_lineup_document(
        doc, position, artifact_sha256, payload.calculation.request.play_identity
    )
    live()
    if (
        proposal.source != actual_source
        or proposal.prefix_ref != doc.prefix_ref
        or proposal.t1.before != doc.after
        or proposal.rules != doc.rules
    ):
        raise OrdinaryPrefixError
    return ConfirmedLineupPrefix(
        doc, actual_source, roster, False, play_number + 1, payload
    )


def _read_native_lineup_head_bound(handle, game, tenant, row, doc):
    """直近event/ledger/物理41+10列/history1をpointで全照合する。"""
    from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
    from pitchlog.repositories.first_ball_operations import PLAY_ROW_COLUMNS, _one
    from pitchlog.sync.first_ball_tokens import FirstBallPlayRowReadToken
    from pitchlog.sync.idempotency import _json_value
    from pitchlog.sync.terminal_pitch_payload import (
        LineupPitchPlayPayload,
        read_lineup_pitch_payload,
    )
    from pitchlog.sync.tokens import IdempotencyLedgerReadToken, OperationEventReadToken

    _verify_source_evidence(row, bridge=False)
    if row["source_evidence"]["non_play_count"] != 0:
        raise OrdinaryPrefixError
    last = doc.last_source
    if last is None or doc.projection_snapshot is None:
        raise OrdinaryPrefixError
    event = _one(
        handle.run(
            OperationEventReadToken(game, int(doc.internal_generation), int(last.d1))
        ),
        tuple(OperationEvent.__table__.c.keys()),
    )
    ledger = _one(
        handle.run(IdempotencyLedgerReadToken(UUID(last.d5))),
        tuple(IdempotencyLedger.__table__.c.keys()),
    )
    play = _one(
        handle.run(FirstBallPlayRowReadToken(game, UUID(last.id))), PLAY_ROW_COLUMNS
    )
    if (
        event["tenant_id"] != tenant
        or event["game_id"] != game
        or event["id"] != UUID(last.id)
        or event["d5"] != UUID(last.d5)
        or event["d2"] != int(last.d2)
        or event["ledger_kind"] != "accepted"
        or event["event_kind"] != "play_input"
        or event["is_tombstone"]
        or event["migration_unverified"]
        or any(
            event[k] is not None
            for k in (
                "replaced_at",
                "retired_at",
                "import_batch_id",
                "legacy_row_identifier",
            )
        )
        or ledger["tenant_id"] != tenant
        or ledger["kind"] != "accepted"
        or ledger["source_fingerprint"] != last.source_fingerprint
        or ledger["retired_at"] is not None
        or ledger["import_batch_id"] is not None
    ):
        raise OrdinaryPrefixError
    payload = LineupPitchPlayPayload.model_validate_json(
        _canonical_json(_json_value(event["payload"]))
    )
    payload = read_lineup_pitch_payload(
        _canonical_json(_json_value(event["payload"])),
        _canonical_json(_json_value(event["state_diff"])),
        expected_calculation=payload.calculation,
    )
    from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
    from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

    request = payload.calculation.request
    value = payload.calculation.response.value
    expected_row = pitch_physical_row(
        payload.observations,
        payload.participants,
        request.t1.result_id,
        tenant_id=tenant,
        game_id=game,
        source_event_id=event["id"],
        row_id=UUID(request.play_identity.play_id),
        play_number=play["play_number"],
    )
    expected_runners = runner_physical_rows(
        request.source.runners,
        t1=value.t1,
        t1_input=request.t1,
        tenant_id=tenant,
        play_id=UUID(request.play_identity.play_id),
    )
    if (
        request.play_identity.event_id != last.id
        or request.play_identity.d5 != last.d5
        or request.source.position.d1 != last.d1
        or request.source.position.d2 != last.d2
        or request.prefix_ref.tenant_id != str(tenant)
        or request.prefix_ref.game_id != str(game)
        or request.rules != doc.rules
        or last.event_fingerprint != last.source_fingerprint
    ):
        raise OrdinaryPrefixError
    if (
        value.next_prefix_ref != doc.prefix_ref
        or value.previous_prefix_ref != doc.previous_prefix_ref
        or value.t1.after != doc.after
        or value.t2 != doc.t2
        or value.runners != doc.runners
        or value.participants != doc.participants
        or value.lineup != doc.lineup
        or value.next_responsibility.pa_start_source != doc.pa_start_source
        or value.roster_digest != doc.roster_digest
        or payload.calculation.artifact_sha256 != doc.artifact_sha256
    ):
        raise OrdinaryPrefixError
    actual = {k: str(v) if type(v) is UUID else v for k, v in play.items()}
    history = row.get("last_history")
    if (
        actual != expected_row
        or list(doc.projection_snapshot.play_runners) != expected_runners
        or actual != doc.projection_snapshot.play_row
        or row.get("last_play_row") != actual
        or row.get("last_play_runners") != list(doc.projection_snapshot.play_runners)
        or type(history) is not dict
        or history.get("tenant_id") != str(tenant)
        or history.get("game_id") != str(game)
        or history.get("internal_generation") != int(doc.internal_generation)
        or history.get("d1") != int(last.d1)
        or history.get("d2") != int(last.d2)
        or history.get("source_event_id") != last.id
        or history.get("entry")
        != value.new_history_entry.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        or history.get("history_version") != int(doc.history_version)
    ):
        raise OrdinaryPrefixError
    return payload, play["play_number"]


def _read_native_lineup_head(handle, game, tenant, row, doc):
    """保存原本破損を要求内容の恒久拒否へ混同しない。"""
    try:
        return _read_native_lineup_head_bound(handle, game, tenant, row, doc)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise OrdinaryPrefixError from None


def _check_native_lineup_row(row, doc, *, tenant, game, generation, epoch, watermark):
    """CP外側の実列を内容全hashと結合し、ready前にも別版/別scopeを拒否する。"""
    expected = {
        "tenant_id": str(tenant),
        "game_id": str(game),
        "internal_generation": generation,
        "id": doc.id,
        "revision": int(doc.revision),
        "history_version": int(doc.history_version),
        "recovery_generation": epoch,
        "confirmed_watermark": watermark,
        "applied_watermark": watermark,
        "content_digest": doc.content_digest,
        "state": "current",
    }
    if (
        type(row) is not dict
        or any(
            type(row.get(key)) is not type(value) or row[key] != value
            for key, value in expected.items()
        )
        or row.get("saved_at") is None
    ):
        raise OrdinaryPrefixError


def _require_v3_compatibility(root, prior, execution):
    """既2形式から分離し、実artifact/旧anchor/固定witnessと有限2pairを確認する。"""
    import hashlib

    base = root / "contracts/state-transition"
    registry_raw = (base / "play_prefix_v2_source_compatibility_v1.json").read_bytes()
    registry = json.loads(
        registry_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    raw = (base / "nonplay_v3_compatibility_witness_v1.json").read_bytes()
    anchor = (base / "batted_current_identity_witness_v1.json").read_bytes()
    artifact = (root / "frontend/public/domain/pitchlog-domain.js").read_bytes()
    current = hashlib.sha256(artifact).hexdigest()
    declaration = json.loads(
        (root / "frontend/public/domain/pitchlog-domain.json").read_bytes(),
        object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    if declaration.get("sha256") != current or execution != current:
        raise ValueError
    if current == "0e260cd916e4cd4da189132a52adb3e065f261d477bc65f5352bb121e8b45f15":
        _require_v3_compatibility_v6(root, prior, current, raw, anchor)
        return
    if current == "71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff":
        _require_v3_compatibility_v5(root, prior, current, raw, anchor)
        return
    if current == "0db3c87d156e290b71d13a31baa5dc5f240ea38a0a84b660428d7dc687b72fff":
        _require_v3_compatibility_v4(root, prior, current, raw, anchor)
        return
    if current == "ab8e9de1e9a2b602b998b485cb44133ab7cd703309a1e5d72e2c5b8ceca2ff8c":
        _require_v3_compatibility_v3(root, prior, current, raw, anchor)
        return
    if current != "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1":
        _require_v3_compatibility_v2(root, prior, current, raw, anchor)
        return
    legacy, original_registry_sha = _validated_v3_witness(raw, anchor, current)
    rows = registry["cases"]
    legacy_anchor = json.loads(
        anchor, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    if (
        set(registry) != {"version", "cases"}
        or registry["version"] != "1"
        or type(rows) is not list
        or hashlib.sha256(
            json.dumps(rows[:55], ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        != legacy_anchor["oldRegistryCasesSha256"]
    ):
        raise ValueError
    old_ops = ["deriveState", "deriveFirstPitchWithContinuation"]
    old_rows = [
        {
            "priorArtifactSha256": legacy,
            "executionArtifactSha256": legacy,
            "sourceFormat": f,
            "compatibleOperations": ops,
            "witnessSha256": hashlib.sha256(anchor).hexdigest(),
        }
        for f, ops in (
            ("first-ball-play-v1", old_ops),
            (
                "ordinary-pitch-play-v1",
                old_ops
                + ["deriveOrdinaryPitch", "deriveOrdinaryPitchWithContinuation"],
            ),
        )
    ]
    if _canonical_json(rows[55:57]) != _canonical_json(old_rows):
        raise ValueError
    original = {k: v for k, v in registry.items() if k != "cases"}
    original["cases"] = rows[:57]
    original_raw = (json.dumps(original, ensure_ascii=False, indent=2) + "\n").encode()
    if hashlib.sha256(original_raw).hexdigest() != original_registry_sha:
        raise ValueError
    operations = ["deriveLineupPlayPrefixWithContinuation"]
    witness_sha = hashlib.sha256(raw).hexdigest()
    expected = [
        {
            "priorArtifactSha256": p,
            "executionArtifactSha256": current,
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": operations,
            "witnessSha256": witness_sha,
        }
        for p in (legacy, current)
    ]
    four_ops = ["deriveState", "deriveFirstPitchWithContinuation"]
    joined = [
        {
            "priorArtifactSha256": p,
            "executionArtifactSha256": current,
            "sourceFormat": fmt,
            "compatibleOperations": ops,
            "witnessSha256": witness_sha,
        }
        for p in (current, legacy)
        for fmt, ops in (
            ("first-ball-play-v1", four_ops),
            (
                "ordinary-pitch-play-v1",
                four_ops
                + ["deriveOrdinaryPitch", "deriveOrdinaryPitchWithContinuation"],
            ),
        )
    ]
    if _canonical_json(rows[57:]) != _canonical_json(expected + joined):
        raise ValueError
    selected = [r for r in rows if r.get("sourceFormat") == "play-prefix-play-v3"]
    if _canonical_json(selected) != _canonical_json(expected) or (
        prior,
        execution,
    ) not in {(legacy, current), (current, current)}:
        raise ValueError


def _require_v3_compatibility_v2(root, prior, current, old_raw, anchor_raw):
    """旧witnessを固定したまま、新bundleとの53件だけを別版で資格化する。"""
    import hashlib

    from pitchlog.authz.terminal_pitch_product import require_registered_product

    base = root / "contracts/state-transition"
    old = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    if (
        hashlib.sha256(old_raw).hexdigest()
        != "cd21ba1138c37820a6b80e8f3c506a462d961a8a745c537012cb72ca876c6df4"
        or prior not in {old, current}
    ):
        raise ValueError
    _validated_v3_witness(old_raw, anchor_raw, old)
    raw = (base / "nonplay_v3_compatibility_witness_v2.json").read_bytes()
    witness_sha = hashlib.sha256(raw).hexdigest()
    if (
        witness_sha
        != "4e92d746007a2fa467512d638a7d4b72d54b8548e202a616306175b977d4a6bb"
    ):
        raise ValueError
    registry_raw = (base / "play_prefix_v3_source_compatibility_v2.json").read_bytes()
    _validated_v3_witness_v2(raw, registry_raw, old_raw, current)
    require_registered_product(artifact_sha256=current, mode="play-prefix-play-v3")


def _require_v3_compatibility_v6(root, prior, current, old_raw, anchor_raw):
    """旧5段の固定証明に新53件を連結し、有限6pairだけを許可する。"""
    import hashlib

    from pitchlog.authz.terminal_pitch_product import require_registered_product

    base = root / "contracts/state-transition"
    legacy = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    second = "4e7d4c8d8d010f1cebb5825272a1f7627fe779e62f0135540c7d79acdce90309"
    previous = "ab8e9de1e9a2b602b998b485cb44133ab7cd703309a1e5d72e2c5b8ceca2ff8c"
    fourth = "0db3c87d156e290b71d13a31baa5dc5f240ea38a0a84b660428d7dc687b72fff"
    fifth = "71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff"
    expected = "0e260cd916e4cd4da189132a52adb3e065f261d477bc65f5352bb121e8b45f15"
    if (
        current != expected
        or prior not in {legacy, second, previous, fourth, fifth, expected}
        or hashlib.sha256(old_raw).hexdigest()
        != "cd21ba1138c37820a6b80e8f3c506a462d961a8a745c537012cb72ca876c6df4"
    ):
        raise ValueError
    legacy_registry = (
        base / "play_prefix_v2_source_compatibility_v1.json"
    ).read_bytes()
    if hashlib.sha256(legacy_registry).hexdigest() != (
        "14cb5d22aa51b87676419f044babc43a2f9eb5e34795db617bf7b32369daccab"
    ):
        raise ValueError
    _validated_v3_witness(old_raw, anchor_raw, legacy)
    second_raw = (base / "nonplay_v3_compatibility_witness_v2.json").read_bytes()
    second_registry = (
        base / "play_prefix_v3_source_compatibility_v2.json"
    ).read_bytes()
    if (
        hashlib.sha256(second_raw).hexdigest()
        != "4e92d746007a2fa467512d638a7d4b72d54b8548e202a616306175b977d4a6bb"
        or hashlib.sha256(second_registry).hexdigest()
        != "d418deb4ece88392d19692143fe631dbc3655eae3e57fc3e197f9de27aed5f3b"
    ):
        raise ValueError
    _validated_v3_witness_v2(second_raw, second_registry, old_raw, second)
    previous_raw = (base / "nonplay_v3_compatibility_witness_v3.json").read_bytes()
    previous_registry = (
        base / "play_prefix_v3_source_compatibility_v3.json"
    ).read_bytes()
    if (
        hashlib.sha256(previous_raw).hexdigest()
        != "7cdc5c0b8e3b2481af8c33c1e437562c727ac9769110138d5aeabb403223d051"
        or hashlib.sha256(previous_registry).hexdigest()
        != "333699a12b90df9f8cfbeaa5b3b533f1a1675c9b03ca9e233fd22b0093827665"
    ):
        raise ValueError
    _validated_v3_witness_v3(
        previous_raw, previous_registry, second_raw, old_raw, previous
    )
    raw = (base / "nonplay_v3_compatibility_witness_v4.json").read_bytes()
    registry_raw = (base / "play_prefix_v3_source_compatibility_v4.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "ab055224a3279da42606d5dfcf42caefd8fae5a3df814e0a481acf549ad2791b"
        or hashlib.sha256(registry_raw).hexdigest()
        != "20838d15aa2150e67e1049d54567240571fc770e8d4324ad2caace2f389c6f41"
    ):
        raise ValueError
    _validated_v3_witness_v4(raw, registry_raw, previous_raw, fourth)
    fourth_raw = raw
    raw = (base / "nonplay_v3_compatibility_witness_v5.json").read_bytes()
    registry_raw = (base / "play_prefix_v3_source_compatibility_v5.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "981572b187097ac52435bb143cb718aa993c9ffec9692e9332b79894f2621955"
        or hashlib.sha256(registry_raw).hexdigest()
        != "fc55be98546bba6e4e6fdba53cbf0f8fa327550fae957eacb3e2cbd30aa00ab2"
    ):
        raise ValueError
    _validated_v3_witness_v5(raw, registry_raw, fourth_raw, fifth)
    fifth_raw = raw
    raw = (base / "nonplay_v3_compatibility_witness_v6.json").read_bytes()
    registry_raw = (base / "play_prefix_v3_source_compatibility_v6.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "d3407e02873e918eb7ced918c1a815f362c3062b6ac8ce8ee55e1d809d90bc54"
        or hashlib.sha256(registry_raw).hexdigest()
        != "94b40efd8f46f4630b07445ef8a12c687ff69815e20ae006b168c65a1aa6f58d"
    ):
        raise ValueError
    _validated_v3_witness_v6(raw, registry_raw, fifth_raw, current)
    require_registered_product(artifact_sha256=current, mode="play-prefix-play-v3")


def _require_v3_compatibility_v5(root, prior, current, old_raw, anchor_raw):
    """旧4段の固定証明に新53件を連結し、有限5pairだけを許可する。"""
    import hashlib

    from pitchlog.authz.terminal_pitch_product import require_registered_product

    base = root / "contracts/state-transition"
    legacy = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    second = "4e7d4c8d8d010f1cebb5825272a1f7627fe779e62f0135540c7d79acdce90309"
    previous = "ab8e9de1e9a2b602b998b485cb44133ab7cd703309a1e5d72e2c5b8ceca2ff8c"
    fourth = "0db3c87d156e290b71d13a31baa5dc5f240ea38a0a84b660428d7dc687b72fff"
    expected = "71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff"
    if (
        current != expected
        or prior not in {legacy, second, previous, fourth, expected}
        or hashlib.sha256(old_raw).hexdigest()
        != "cd21ba1138c37820a6b80e8f3c506a462d961a8a745c537012cb72ca876c6df4"
    ):
        raise ValueError
    legacy_registry = (
        base / "play_prefix_v2_source_compatibility_v1.json"
    ).read_bytes()
    if hashlib.sha256(legacy_registry).hexdigest() != (
        "14cb5d22aa51b87676419f044babc43a2f9eb5e34795db617bf7b32369daccab"
    ):
        raise ValueError
    _validated_v3_witness(old_raw, anchor_raw, legacy)
    second_raw = (base / "nonplay_v3_compatibility_witness_v2.json").read_bytes()
    second_registry = (
        base / "play_prefix_v3_source_compatibility_v2.json"
    ).read_bytes()
    if (
        hashlib.sha256(second_raw).hexdigest()
        != "4e92d746007a2fa467512d638a7d4b72d54b8548e202a616306175b977d4a6bb"
        or hashlib.sha256(second_registry).hexdigest()
        != "d418deb4ece88392d19692143fe631dbc3655eae3e57fc3e197f9de27aed5f3b"
    ):
        raise ValueError
    _validated_v3_witness_v2(second_raw, second_registry, old_raw, second)
    previous_raw = (base / "nonplay_v3_compatibility_witness_v3.json").read_bytes()
    previous_registry = (
        base / "play_prefix_v3_source_compatibility_v3.json"
    ).read_bytes()
    if (
        hashlib.sha256(previous_raw).hexdigest()
        != "7cdc5c0b8e3b2481af8c33c1e437562c727ac9769110138d5aeabb403223d051"
        or hashlib.sha256(previous_registry).hexdigest()
        != "333699a12b90df9f8cfbeaa5b3b533f1a1675c9b03ca9e233fd22b0093827665"
    ):
        raise ValueError
    _validated_v3_witness_v3(
        previous_raw, previous_registry, second_raw, old_raw, previous
    )
    raw = (base / "nonplay_v3_compatibility_witness_v4.json").read_bytes()
    registry_raw = (base / "play_prefix_v3_source_compatibility_v4.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "ab055224a3279da42606d5dfcf42caefd8fae5a3df814e0a481acf549ad2791b"
        or hashlib.sha256(registry_raw).hexdigest()
        != "20838d15aa2150e67e1049d54567240571fc770e8d4324ad2caace2f389c6f41"
    ):
        raise ValueError
    _validated_v3_witness_v4(raw, registry_raw, previous_raw, fourth)
    fourth_raw = raw
    raw = (base / "nonplay_v3_compatibility_witness_v5.json").read_bytes()
    registry_raw = (base / "play_prefix_v3_source_compatibility_v5.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "981572b187097ac52435bb143cb718aa993c9ffec9692e9332b79894f2621955"
        or hashlib.sha256(registry_raw).hexdigest()
        != "fc55be98546bba6e4e6fdba53cbf0f8fa327550fae957eacb3e2cbd30aa00ab2"
    ):
        raise ValueError
    _validated_v3_witness_v5(raw, registry_raw, fourth_raw, current)
    require_registered_product(artifact_sha256=current, mode="play-prefix-play-v3")


def _require_v3_compatibility_v4(root, prior, current, old_raw, anchor_raw):
    """旧3段の固定証明に新53件を連結し、有限4pairだけを許可する。"""
    import hashlib

    from pitchlog.authz.terminal_pitch_product import require_registered_product

    base = root / "contracts/state-transition"
    legacy = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    second = "4e7d4c8d8d010f1cebb5825272a1f7627fe779e62f0135540c7d79acdce90309"
    previous = "ab8e9de1e9a2b602b998b485cb44133ab7cd703309a1e5d72e2c5b8ceca2ff8c"
    expected = "0db3c87d156e290b71d13a31baa5dc5f240ea38a0a84b660428d7dc687b72fff"
    if (
        current != expected
        or prior not in {legacy, second, previous, expected}
        or hashlib.sha256(old_raw).hexdigest()
        != "cd21ba1138c37820a6b80e8f3c506a462d961a8a745c537012cb72ca876c6df4"
    ):
        raise ValueError
    legacy_registry = (
        base / "play_prefix_v2_source_compatibility_v1.json"
    ).read_bytes()
    if hashlib.sha256(legacy_registry).hexdigest() != (
        "14cb5d22aa51b87676419f044babc43a2f9eb5e34795db617bf7b32369daccab"
    ):
        raise ValueError
    _validated_v3_witness(old_raw, anchor_raw, legacy)
    second_raw = (base / "nonplay_v3_compatibility_witness_v2.json").read_bytes()
    second_registry = (
        base / "play_prefix_v3_source_compatibility_v2.json"
    ).read_bytes()
    if (
        hashlib.sha256(second_raw).hexdigest()
        != "4e92d746007a2fa467512d638a7d4b72d54b8548e202a616306175b977d4a6bb"
        or hashlib.sha256(second_registry).hexdigest()
        != "d418deb4ece88392d19692143fe631dbc3655eae3e57fc3e197f9de27aed5f3b"
    ):
        raise ValueError
    _validated_v3_witness_v2(second_raw, second_registry, old_raw, second)
    previous_raw = (base / "nonplay_v3_compatibility_witness_v3.json").read_bytes()
    previous_registry = (
        base / "play_prefix_v3_source_compatibility_v3.json"
    ).read_bytes()
    if (
        hashlib.sha256(previous_raw).hexdigest()
        != "7cdc5c0b8e3b2481af8c33c1e437562c727ac9769110138d5aeabb403223d051"
        or hashlib.sha256(previous_registry).hexdigest()
        != "333699a12b90df9f8cfbeaa5b3b533f1a1675c9b03ca9e233fd22b0093827665"
    ):
        raise ValueError
    _validated_v3_witness_v3(
        previous_raw, previous_registry, second_raw, old_raw, previous
    )
    raw = (base / "nonplay_v3_compatibility_witness_v4.json").read_bytes()
    registry_raw = (base / "play_prefix_v3_source_compatibility_v4.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "ab055224a3279da42606d5dfcf42caefd8fae5a3df814e0a481acf549ad2791b"
        or hashlib.sha256(registry_raw).hexdigest()
        != "20838d15aa2150e67e1049d54567240571fc770e8d4324ad2caace2f389c6f41"
    ):
        raise ValueError
    _validated_v3_witness_v4(raw, registry_raw, previous_raw, current)
    require_registered_product(artifact_sha256=current, mode="play-prefix-play-v3")


def _require_v3_compatibility_v3(root, prior, current, old_raw, anchor_raw):
    """固定旧2段を検査し、新artifactへの有限53件だけを資格化する。"""
    import hashlib

    from pitchlog.authz.terminal_pitch_product import require_registered_product

    base = root / "contracts/state-transition"
    legacy = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    previous = "4e7d4c8d8d010f1cebb5825272a1f7627fe779e62f0135540c7d79acdce90309"
    expected_current = (
        "ab8e9de1e9a2b602b998b485cb44133ab7cd703309a1e5d72e2c5b8ceca2ff8c"
    )
    if (
        current != expected_current
        or prior not in {legacy, previous, expected_current}
        or hashlib.sha256(old_raw).hexdigest()
        != "cd21ba1138c37820a6b80e8f3c506a462d961a8a745c537012cb72ca876c6df4"
    ):
        raise ValueError
    legacy_registry = (
        base / "play_prefix_v2_source_compatibility_v1.json"
    ).read_bytes()
    if (
        hashlib.sha256(legacy_registry).hexdigest()
        != "14cb5d22aa51b87676419f044babc43a2f9eb5e34795db617bf7b32369daccab"
    ):
        raise ValueError
    _validated_v3_witness(old_raw, anchor_raw, legacy)
    previous_raw = (base / "nonplay_v3_compatibility_witness_v2.json").read_bytes()
    previous_registry = (
        base / "play_prefix_v3_source_compatibility_v2.json"
    ).read_bytes()
    if (
        hashlib.sha256(previous_raw).hexdigest()
        != "4e92d746007a2fa467512d638a7d4b72d54b8548e202a616306175b977d4a6bb"
        or hashlib.sha256(previous_registry).hexdigest()
        != "d418deb4ece88392d19692143fe631dbc3655eae3e57fc3e197f9de27aed5f3b"
    ):
        raise ValueError
    _validated_v3_witness_v2(previous_raw, previous_registry, old_raw, previous)
    raw = (base / "nonplay_v3_compatibility_witness_v3.json").read_bytes()
    registry_raw = (base / "play_prefix_v3_source_compatibility_v3.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "7cdc5c0b8e3b2481af8c33c1e437562c727ac9769110138d5aeabb403223d051"
        or hashlib.sha256(registry_raw).hexdigest()
        != "333699a12b90df9f8cfbeaa5b3b533f1a1675c9b03ca9e233fd22b0093827665"
    ):
        raise ValueError
    _validated_v3_witness_v3(raw, registry_raw, previous_raw, old_raw, current)
    require_registered_product(artifact_sha256=current, mode="play-prefix-play-v3")


@lru_cache(maxsize=4)
def _validated_v3_witness_v6(raw, registry_raw, previous_raw, current):
    """旧固定53例と現53例を識別値・自己echo以外の全値で結ぶ。"""
    import copy
    import hashlib

    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        LineupPrefixRequest,
        LineupPrefixSuccess,
        decode_lineup_prefix_response,
        lineup_wire_digest,
    )

    third = "ab8e9de1e9a2b602b998b485cb44133ab7cd703309a1e5d72e2c5b8ceca2ff8c"
    fourth = "0db3c87d156e290b71d13a31baa5dc5f240ea38a0a84b660428d7dc687b72fff"
    previous = "71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff"
    legacy = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    second = "4e7d4c8d8d010f1cebb5825272a1f7627fe779e62f0135540c7d79acdce90309"
    data = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    registry = json.loads(
        registry_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    historical = json.loads(
        previous_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    if raw != (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode():
        raise ValueError
    if (
        registry_raw
        != (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode()
    ):
        raise ValueError
    witness_sha = hashlib.sha256(raw).hexdigest()
    expected_rows = [
        {
            "priorArtifactSha256": prior,
            "executionArtifactSha256": current,
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
            "witnessSha256": witness_sha,
        }
        for prior in (legacy, second, third, fourth, previous, current)
    ]
    if _canonical_json(registry) != _canonical_json(
        {
            "version": "6",
            "sourceFormat": "play-prefix-play-v3",
            "historicalWitnessSha256": hashlib.sha256(previous_raw).hexdigest(),
            "chainWitnessSha256": historical["chainWitnessSha256"],
            "currentWitnessSha256": witness_sha,
            "cases": expected_rows,
        }
    ):
        raise ValueError
    if set(data) != {
        "version",
        "sourceFormat",
        "compatibleOperations",
        "historicalArtifactCommit",
        "historicalArtifactSha256",
        "historicalWitnessSha256",
        "chainArtifactSha256",
        "chainWitnessSha256",
        "executionArtifactSha256",
        "normalization",
        "scope",
        "samplesSha256",
        "samples",
    }:
        raise ValueError
    if _canonical_json(
        {key: data[key] for key in data if key != "samples"}
    ) != _canonical_json(
        {
            "version": "6",
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
            "historicalArtifactCommit": "d074b72ba01cc4d05af29e7b534189c496c5c49c",
            "historicalArtifactSha256": previous,
            "historicalWitnessSha256": hashlib.sha256(previous_raw).hexdigest(),
            "chainArtifactSha256": legacy,
            "chainWitnessSha256": historical["chainWitnessSha256"],
            "executionArtifactSha256": current,
            "normalization": {
                "requestPointers": [
                    "/source/executionArtifactSha256",
                    "/nextCheckpoint/digest",
                ],
                "responsePointers": [
                    "/value/executionArtifactSha256",
                    "/value/nextPrefixRef/checkpoint/digest",
                ],
                "allOtherValuesUnchanged": True,
            },
            "scope": {
                "caseCount": 53,
                "operationCount": 1,
                "HTTPorDB": False,
                "P6Blind": False,
            },
            "samplesSha256": data["samplesSha256"],
        }
    ):
        raise ValueError
    samples = data["samples"]
    before_samples = historical["samples"]
    if (
        type(samples) is not list
        or len(samples) != 53
        or len(before_samples) != 53
        or hashlib.sha256(
            json.dumps(
                samples, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        != data["samplesSha256"]
    ):
        raise ValueError
    for before, sample in zip(before_samples, samples, strict=True):
        if (
            type(sample) is not dict
            or type(before) is not dict
            or set(sample)
            != {
                "sourcePath",
                "caseId",
                "priorRequest",
                "priorExpected",
                "priorActual",
                "currentRequest",
                "currentExpected",
                "currentActual",
            }
        ):
            raise ValueError
        sample = cast("dict[str, Any]", sample)
        before = cast("dict[str, Any]", before)
        if any(
            _canonical_json(sample[key]) != _canonical_json(before[old_key])
            for key, old_key in (
                ("sourcePath", "sourcePath"),
                ("caseId", "caseId"),
                ("priorRequest", "currentRequest"),
                ("priorExpected", "currentExpected"),
                ("priorActual", "currentActual"),
            )
        ) or _canonical_json(sample["currentActual"]) != _canonical_json(
            sample["currentExpected"]
        ):
            raise ValueError
        request = copy.deepcopy(sample["priorRequest"])
        expected = copy.deepcopy(sample["priorExpected"])
        if (
            request["source"]["executionArtifactSha256"] != previous
            or expected["value"]["executionArtifactSha256"] != previous
        ):
            raise ValueError
        request["source"]["executionArtifactSha256"] = current
        expected["value"]["executionArtifactSha256"] = current
        response = decode_lineup_prefix_response(_canonical_json(expected))
        if type(response) is not LineupPrefixSuccess:
            raise ValueError
        digest = lineup_wire_digest(
            LineupPrefixRequest.model_validate_json(_canonical_json(request)), response
        )
        request["nextCheckpoint"]["digest"] = digest
        expected["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
        if _canonical_json(request) != _canonical_json(
            sample["currentRequest"]
        ) or _canonical_json(expected) != _canonical_json(sample["currentExpected"]):
            raise ValueError


@lru_cache(maxsize=4)
def _validated_v3_witness_v5(raw, registry_raw, previous_raw, current):
    """旧固定53例と現53例を識別値・自己echo以外の全値で結ぶ。"""
    import copy
    import hashlib

    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        LineupPrefixRequest,
        LineupPrefixSuccess,
        decode_lineup_prefix_response,
        lineup_wire_digest,
    )

    third = "ab8e9de1e9a2b602b998b485cb44133ab7cd703309a1e5d72e2c5b8ceca2ff8c"
    previous = "0db3c87d156e290b71d13a31baa5dc5f240ea38a0a84b660428d7dc687b72fff"
    legacy = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    second = "4e7d4c8d8d010f1cebb5825272a1f7627fe779e62f0135540c7d79acdce90309"
    data = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    registry = json.loads(
        registry_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    historical = json.loads(
        previous_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    if raw != (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode():
        raise ValueError
    if (
        registry_raw
        != (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode()
    ):
        raise ValueError
    witness_sha = hashlib.sha256(raw).hexdigest()
    expected_rows = [
        {
            "priorArtifactSha256": prior,
            "executionArtifactSha256": current,
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
            "witnessSha256": witness_sha,
        }
        for prior in (legacy, second, third, previous, current)
    ]
    if _canonical_json(registry) != _canonical_json(
        {
            "version": "5",
            "sourceFormat": "play-prefix-play-v3",
            "historicalWitnessSha256": hashlib.sha256(previous_raw).hexdigest(),
            "chainWitnessSha256": historical["chainWitnessSha256"],
            "currentWitnessSha256": witness_sha,
            "cases": expected_rows,
        }
    ):
        raise ValueError
    if set(data) != {
        "version",
        "sourceFormat",
        "compatibleOperations",
        "historicalArtifactCommit",
        "historicalArtifactSha256",
        "historicalWitnessSha256",
        "chainArtifactSha256",
        "chainWitnessSha256",
        "executionArtifactSha256",
        "normalization",
        "scope",
        "samplesSha256",
        "samples",
    }:
        raise ValueError
    if _canonical_json(
        {key: data[key] for key in data if key != "samples"}
    ) != _canonical_json(
        {
            "version": "5",
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
            "historicalArtifactCommit": "bb0b08dc3c04d0f06eb010291600511ac6eb9476",
            "historicalArtifactSha256": previous,
            "historicalWitnessSha256": hashlib.sha256(previous_raw).hexdigest(),
            "chainArtifactSha256": legacy,
            "chainWitnessSha256": historical["chainWitnessSha256"],
            "executionArtifactSha256": current,
            "normalization": {
                "requestPointers": [
                    "/source/executionArtifactSha256",
                    "/nextCheckpoint/digest",
                ],
                "responsePointers": [
                    "/value/executionArtifactSha256",
                    "/value/nextPrefixRef/checkpoint/digest",
                ],
                "allOtherValuesUnchanged": True,
            },
            "scope": {
                "caseCount": 53,
                "operationCount": 1,
                "HTTPorDB": False,
                "P6Blind": False,
            },
            "samplesSha256": data["samplesSha256"],
        }
    ):
        raise ValueError
    samples = data["samples"]
    before_samples = historical["samples"]
    if (
        type(samples) is not list
        or len(samples) != 53
        or len(before_samples) != 53
        or hashlib.sha256(
            json.dumps(
                samples, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        != data["samplesSha256"]
    ):
        raise ValueError
    for before, sample in zip(before_samples, samples, strict=True):
        if (
            type(sample) is not dict
            or type(before) is not dict
            or set(sample)
            != {
                "sourcePath",
                "caseId",
                "priorRequest",
                "priorExpected",
                "priorActual",
                "currentRequest",
                "currentExpected",
                "currentActual",
            }
        ):
            raise ValueError
        sample = cast("dict[str, Any]", sample)
        before = cast("dict[str, Any]", before)
        if any(
            _canonical_json(sample[key]) != _canonical_json(before[old_key])
            for key, old_key in (
                ("sourcePath", "sourcePath"),
                ("caseId", "caseId"),
                ("priorRequest", "currentRequest"),
                ("priorExpected", "currentExpected"),
                ("priorActual", "currentActual"),
            )
        ) or _canonical_json(sample["currentActual"]) != _canonical_json(
            sample["currentExpected"]
        ):
            raise ValueError
        request = copy.deepcopy(sample["priorRequest"])
        expected = copy.deepcopy(sample["priorExpected"])
        if (
            request["source"]["executionArtifactSha256"] != previous
            or expected["value"]["executionArtifactSha256"] != previous
        ):
            raise ValueError
        request["source"]["executionArtifactSha256"] = current
        expected["value"]["executionArtifactSha256"] = current
        response = decode_lineup_prefix_response(_canonical_json(expected))
        if type(response) is not LineupPrefixSuccess:
            raise ValueError
        digest = lineup_wire_digest(
            LineupPrefixRequest.model_validate_json(_canonical_json(request)), response
        )
        request["nextCheckpoint"]["digest"] = digest
        expected["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
        if _canonical_json(request) != _canonical_json(
            sample["currentRequest"]
        ) or _canonical_json(expected) != _canonical_json(sample["currentExpected"]):
            raise ValueError


@lru_cache(maxsize=4)
def _validated_v3_witness_v4(raw, registry_raw, previous_raw, current):
    """旧固定53例と現53例を識別値・自己echo以外の全値で結ぶ。"""
    import copy
    import hashlib

    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        LineupPrefixRequest,
        LineupPrefixSuccess,
        decode_lineup_prefix_response,
        lineup_wire_digest,
    )

    previous = "ab8e9de1e9a2b602b998b485cb44133ab7cd703309a1e5d72e2c5b8ceca2ff8c"
    legacy = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    second = "4e7d4c8d8d010f1cebb5825272a1f7627fe779e62f0135540c7d79acdce90309"
    data = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    registry = json.loads(
        registry_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    historical = json.loads(
        previous_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    if raw != (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode():
        raise ValueError
    if (
        registry_raw
        != (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode()
    ):
        raise ValueError
    witness_sha = hashlib.sha256(raw).hexdigest()
    expected_rows = [
        {
            "priorArtifactSha256": prior,
            "executionArtifactSha256": current,
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
            "witnessSha256": witness_sha,
        }
        for prior in (legacy, second, previous, current)
    ]
    if _canonical_json(registry) != _canonical_json(
        {
            "version": "4",
            "sourceFormat": "play-prefix-play-v3",
            "historicalWitnessSha256": hashlib.sha256(previous_raw).hexdigest(),
            "chainWitnessSha256": historical["chainWitnessSha256"],
            "currentWitnessSha256": witness_sha,
            "cases": expected_rows,
        }
    ):
        raise ValueError
    if set(data) != {
        "version",
        "sourceFormat",
        "compatibleOperations",
        "historicalArtifactCommit",
        "historicalArtifactSha256",
        "historicalWitnessSha256",
        "chainArtifactSha256",
        "chainWitnessSha256",
        "executionArtifactSha256",
        "normalization",
        "scope",
        "samplesSha256",
        "samples",
    }:
        raise ValueError
    if _canonical_json(
        {key: data[key] for key in data if key != "samples"}
    ) != _canonical_json(
        {
            "version": "4",
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
            "historicalArtifactCommit": "1bfad343fa365f3902d1a02b38a5f1b1a5cf8139",
            "historicalArtifactSha256": previous,
            "historicalWitnessSha256": hashlib.sha256(previous_raw).hexdigest(),
            "chainArtifactSha256": legacy,
            "chainWitnessSha256": historical["chainWitnessSha256"],
            "executionArtifactSha256": current,
            "normalization": {
                "requestPointers": [
                    "/source/executionArtifactSha256",
                    "/nextCheckpoint/digest",
                ],
                "responsePointers": [
                    "/value/executionArtifactSha256",
                    "/value/nextPrefixRef/checkpoint/digest",
                ],
                "allOtherValuesUnchanged": True,
            },
            "scope": {
                "caseCount": 53,
                "operationCount": 1,
                "HTTPorDB": False,
                "P6Blind": False,
            },
            "samplesSha256": data["samplesSha256"],
        }
    ):
        raise ValueError
    samples = data["samples"]
    before_samples = historical["samples"]
    if (
        type(samples) is not list
        or len(samples) != 53
        or len(before_samples) != 53
        or hashlib.sha256(
            json.dumps(
                samples, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        != data["samplesSha256"]
    ):
        raise ValueError
    for before, sample in zip(before_samples, samples, strict=True):
        if (
            type(sample) is not dict
            or type(before) is not dict
            or set(sample)
            != {
                "sourcePath",
                "caseId",
                "priorRequest",
                "priorExpected",
                "priorActual",
                "currentRequest",
                "currentExpected",
                "currentActual",
            }
        ):
            raise ValueError
        sample = cast("dict[str, Any]", sample)
        before = cast("dict[str, Any]", before)
        if any(
            _canonical_json(sample[key]) != _canonical_json(before[old_key])
            for key, old_key in (
                ("sourcePath", "sourcePath"),
                ("caseId", "caseId"),
                ("priorRequest", "currentRequest"),
                ("priorExpected", "currentExpected"),
                ("priorActual", "currentActual"),
            )
        ) or _canonical_json(sample["currentActual"]) != _canonical_json(
            sample["currentExpected"]
        ):
            raise ValueError
        request = copy.deepcopy(sample["priorRequest"])
        expected = copy.deepcopy(sample["priorExpected"])
        if (
            request["source"]["executionArtifactSha256"] != previous
            or expected["value"]["executionArtifactSha256"] != previous
        ):
            raise ValueError
        request["source"]["executionArtifactSha256"] = current
        expected["value"]["executionArtifactSha256"] = current
        response = decode_lineup_prefix_response(_canonical_json(expected))
        if type(response) is not LineupPrefixSuccess:
            raise ValueError
        digest = lineup_wire_digest(
            LineupPrefixRequest.model_validate_json(_canonical_json(request)), response
        )
        request["nextCheckpoint"]["digest"] = digest
        expected["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
        if _canonical_json(request) != _canonical_json(
            sample["currentRequest"]
        ) or _canonical_json(expected) != _canonical_json(sample["currentExpected"]):
            raise ValueError


@lru_cache(maxsize=4)
def _validated_v3_witness_v3(raw, registry_raw, previous_raw, old_raw, current):
    """旧2段の原本に結び、新53件の自己echo2箇所以外の変更を拒否する。"""
    import copy
    import hashlib

    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        LineupPrefixRequest,
        LineupPrefixSuccess,
        decode_lineup_prefix_response,
        lineup_wire_digest,
    )

    legacy = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    previous = "4e7d4c8d8d010f1cebb5825272a1f7627fe779e62f0135540c7d79acdce90309"
    data = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    registry = json.loads(
        registry_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    old_witness = json.loads(
        previous_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    if raw != (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode():
        raise ValueError
    if (
        registry_raw
        != (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode()
    ):
        raise ValueError
    witness_sha = hashlib.sha256(raw).hexdigest()
    expected_rows = [
        {
            "priorArtifactSha256": p,
            "executionArtifactSha256": current,
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
            "witnessSha256": witness_sha,
        }
        for p in (legacy, previous, current)
    ]
    if _canonical_json(registry) != _canonical_json(
        {
            "version": "3",
            "sourceFormat": "play-prefix-play-v3",
            "historicalWitnessSha256": hashlib.sha256(previous_raw).hexdigest(),
            "chainWitnessSha256": hashlib.sha256(old_raw).hexdigest(),
            "currentWitnessSha256": witness_sha,
            "cases": expected_rows,
        }
    ):
        raise ValueError
    if set(data) != {
        "version",
        "sourceFormat",
        "compatibleOperations",
        "historicalArtifactCommit",
        "historicalArtifactSha256",
        "historicalWitnessSha256",
        "chainArtifactSha256",
        "chainWitnessSha256",
        "executionArtifactSha256",
        "normalization",
        "scope",
        "samplesSha256",
        "samples",
    }:
        raise ValueError
    if _canonical_json({key: data[key] for key in data if key != "samples"}) != (
        _canonical_json(
            {
                "version": "3",
                "sourceFormat": "play-prefix-play-v3",
                "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
                "historicalArtifactCommit": "71e3eebe436349f8a9ee3869132e785bfd5baa07",
                "historicalArtifactSha256": previous,
                "historicalWitnessSha256": hashlib.sha256(previous_raw).hexdigest(),
                "chainArtifactSha256": legacy,
                "chainWitnessSha256": hashlib.sha256(old_raw).hexdigest(),
                "executionArtifactSha256": current,
                "normalization": {
                    "requestPointers": [
                        "/source/executionArtifactSha256",
                        "/nextCheckpoint/digest",
                    ],
                    "responsePointers": [
                        "/value/executionArtifactSha256",
                        "/value/nextPrefixRef/checkpoint/digest",
                    ],
                    "allOtherValuesUnchanged": True,
                },
                "scope": {
                    "caseCount": 53,
                    "operationCount": 1,
                    "HTTPorDB": False,
                    "P6Blind": False,
                },
                "samplesSha256": data["samplesSha256"],
            }
        )
    ):
        raise ValueError
    samples = data["samples"]
    before_samples = old_witness["samples"]
    if (
        type(samples) is not list
        or len(samples) != 53
        or len(before_samples) != 53
        or hashlib.sha256(
            json.dumps(
                samples, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        != data["samplesSha256"]
    ):
        raise ValueError
    for before, sample in zip(before_samples, samples, strict=True):
        if (
            type(sample) is not dict
            or type(before) is not dict
            or set(sample)
            != {
                "sourcePath",
                "caseId",
                "priorRequest",
                "priorExpected",
                "priorActual",
                "currentRequest",
                "currentExpected",
                "currentActual",
            }
        ):
            raise ValueError
        sample = cast("dict[str, Any]", sample)
        before = cast("dict[str, Any]", before)
        if any(
            _canonical_json(sample[key]) != _canonical_json(before[old_key])
            for key, old_key in (
                ("sourcePath", "sourcePath"),
                ("caseId", "caseId"),
                ("priorRequest", "currentRequest"),
                ("priorExpected", "currentExpected"),
                ("priorActual", "currentActual"),
            )
        ) or _canonical_json(sample["currentActual"]) != _canonical_json(
            sample["currentExpected"]
        ):
            raise ValueError
        request = copy.deepcopy(sample["priorRequest"])
        expected = copy.deepcopy(sample["priorExpected"])
        if (
            request["source"]["executionArtifactSha256"] != previous
            or expected["value"]["executionArtifactSha256"] != previous
        ):
            raise ValueError
        request["source"]["executionArtifactSha256"] = current
        expected["value"]["executionArtifactSha256"] = current
        response = decode_lineup_prefix_response(_canonical_json(expected))
        if type(response) is not LineupPrefixSuccess:
            raise ValueError
        digest = lineup_wire_digest(
            LineupPrefixRequest.model_validate_json(_canonical_json(request)),
            response,
        )
        request["nextCheckpoint"]["digest"] = digest
        expected["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
        if _canonical_json(request) != _canonical_json(
            sample["currentRequest"]
        ) or _canonical_json(expected) != _canonical_json(sample["currentExpected"]):
            raise ValueError


@lru_cache(maxsize=4)
def _validated_v3_witness_v2(raw, registry_raw, old_raw, current):
    """旧53原本との全値一致と識別値/digestだけの正規化を閉検査する。"""
    import copy
    import hashlib

    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        LineupPrefixRequest,
        LineupPrefixSuccess,
        decode_lineup_prefix_response,
        lineup_wire_digest,
    )

    old = "4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1"
    data = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    registry = json.loads(
        registry_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    old_witness = json.loads(
        old_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    if raw != (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode():
        raise ValueError
    if (
        registry_raw
        != (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode()
    ):
        raise ValueError
    witness_sha = hashlib.sha256(raw).hexdigest()
    expected_rows = [
        {
            "priorArtifactSha256": p,
            "executionArtifactSha256": current,
            "sourceFormat": "play-prefix-play-v3",
            "compatibleOperations": ["deriveLineupPlayPrefixWithContinuation"],
            "witnessSha256": witness_sha,
        }
        for p in (old, current)
    ]
    if registry != {
        "version": "2",
        "sourceFormat": "play-prefix-play-v3",
        "historicalWitnessSha256": hashlib.sha256(old_raw).hexdigest(),
        "currentWitnessSha256": witness_sha,
        "cases": expected_rows,
    }:
        raise ValueError
    if set(data) != {
        "version",
        "sourceFormat",
        "compatibleOperations",
        "historicalArtifactCommit",
        "historicalArtifactSha256",
        "historicalWitnessSha256",
        "executionArtifactSha256",
        "normalization",
        "scope",
        "samplesSha256",
        "samples",
    }:
        raise ValueError
    if any(
        (
            data["version"] != "2",
            data["sourceFormat"] != "play-prefix-play-v3",
            data["compatibleOperations"] != ["deriveLineupPlayPrefixWithContinuation"],
            data["historicalArtifactCommit"]
            != "177de16a31df723c69595bc659839f46b3fc71ac",
            data["historicalArtifactSha256"] != old,
            data["historicalWitnessSha256"] != hashlib.sha256(old_raw).hexdigest(),
            data["executionArtifactSha256"] != current,
            data["normalization"]
            != {
                "requestPointers": [
                    "/source/executionArtifactSha256",
                    "/nextCheckpoint/digest",
                ],
                "responsePointers": [
                    "/value/executionArtifactSha256",
                    "/value/nextPrefixRef/checkpoint/digest",
                ],
                "allOtherValuesUnchanged": True,
            },
            data["scope"]
            != {
                "caseCount": 53,
                "operationCount": 1,
                "HTTPorDB": False,
                "P6Blind": False,
            },
        )
    ):
        raise ValueError
    samples = data["samples"]
    if (
        type(samples) is not list
        or len(samples) != 53
        or len(old_witness["samples"]) != 53
        or hashlib.sha256(
            json.dumps(
                samples, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        != data["samplesSha256"]
    ):
        raise ValueError
    for before, sample in zip(old_witness["samples"], samples, strict=True):
        if not isinstance(sample, dict) or type(sample) is not dict:
            raise ValueError
        if (
            set(sample)
            != {
                "sourcePath",
                "caseId",
                "priorRequest",
                "priorExpected",
                "priorActual",
                "currentRequest",
                "currentExpected",
                "currentActual",
            }
            or sample["sourcePath"] != before["sourcePath"]
            or sample["caseId"] != before["caseId"]
            or sample["priorRequest"] != before["currentRequest"]
            or sample["priorExpected"] != before["currentExpected"]
            or sample["priorActual"] != before["currentActual"]
            or sample["currentActual"] != sample["currentExpected"]
        ):
            raise ValueError
        request = copy.deepcopy(sample["priorRequest"])
        expected = copy.deepcopy(sample["priorExpected"])
        if (
            request["source"]["executionArtifactSha256"] != old
            or expected["value"]["executionArtifactSha256"] != old
        ):
            raise ValueError
        request["source"]["executionArtifactSha256"] = current
        expected["value"]["executionArtifactSha256"] = current
        response = decode_lineup_prefix_response(_canonical_json(expected))
        if type(response) is not LineupPrefixSuccess:
            raise ValueError
        digest = lineup_wire_digest(
            LineupPrefixRequest.model_validate_json(_canonical_json(request)),
            response,
        )
        request["nextCheckpoint"]["digest"] = digest
        expected["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
        if request != sample["currentRequest"] or expected != sample["currentExpected"]:
            raise ValueError


@lru_cache(maxsize=4)
def _validated_v3_witness(raw, anchor_raw, current):
    """固定証拠の全bytesを検査し、宣言metadata/全応答の閉比較を行う。"""
    import copy
    import hashlib

    data = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    anchor = json.loads(
        anchor_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    legacy = anchor["executionArtifactSha256"]
    if raw != (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode():
        raise ValueError
    if set(data) != {
        "version",
        "sourceFormat",
        "compatibleOperations",
        "historicalContext",
        "executionArtifactSha256",
        "priorArtifacts",
        "normativeSources",
        "normalization",
        "scope",
        "separateFourOperationEvidence",
        "fourOperationJoinEvidence",
        "samplesSha256",
        "samples",
    }:
        raise ValueError
    if (
        type(legacy) is not str
        or re.fullmatch(r"[a-f0-9]{64}", legacy) is None
        or data["version"] != "1"
        or data["sourceFormat"] != "play-prefix-play-v3"
        or data["compatibleOperations"] != ["deriveLineupPlayPrefixWithContinuation"]
        or data["executionArtifactSha256"] != current
        or data["priorArtifacts"] != [legacy, current]
    ):
        raise ValueError
    historical = data["historicalContext"]
    if (
        _canonical_json(
            {
                k: v
                for k, v in historical.items()
                if k not in {"revision", "registrySha256"}
            }
        )
        != _canonical_json(
            {
                "artifactPath": "frontend/public/domain/pitchlog-domain.js",
                "artifactSha256": legacy,
                "registryCaseCount": 57,
                "legacyWitnessPath": (
                    "contracts/state-transition/batted_current_identity_witness_v1.json"
                ),
                "legacyWitnessSha256": hashlib.sha256(anchor_raw).hexdigest(),
            }
        )
        or type(historical["revision"]) is not str
        or re.fullmatch(r"[a-f0-9]{40}", historical["revision"]) is None
        or type(historical["registrySha256"]) is not str
        or re.fullmatch(r"[a-f0-9]{64}", historical["registrySha256"]) is None
    ):
        raise ValueError
    if _canonical_json(data["scope"]) != _canonical_json(
        {
            "caseCount": 53,
            "operationCount": 1,
            "HTTPorDB": False,
            "wholeDomainCompatibility": False,
            "P6Blind": False,
        }
    ):
        raise ValueError
    normalization = {
        "requestPointers": [
            "/source/executionArtifactSha256",
            "/nextCheckpoint/digest",
        ],
        "responsePointers": [
            "/value/executionArtifactSha256",
            "/value/nextPrefixRef/checkpoint/digest",
        ],
        "allOtherValuesUnchanged": True,
        "sealHelper": "lineup_wire_digest/verify_lineup_wire_seal",
    }
    if _canonical_json(data["normalization"]) != _canonical_json(normalization):
        raise ValueError
    separate = data["separateFourOperationEvidence"]
    if (
        set(separate)
        != {"sha256", "caseCount", "notV3Evidence", "notAllPublicOperations"}
        or type(separate["caseCount"]) is not int
        or separate["caseCount"] != 1878
        or separate["notV3Evidence"] is not True
        or separate["notAllPublicOperations"] is not True
        or type(separate["sha256"]) is not str
        or re.fullmatch(r"[a-f0-9]{64}", separate["sha256"]) is None
    ):
        raise ValueError
    sources = data["normativeSources"]
    if (
        type(sources) is not list
        or len(sources) != 2
        or [(r["path"], r["caseCount"]) for r in sources]
        != [
            ("contracts/state-transition/lineup_play_prefix_cases_v1.json", 34),
            ("contracts/state-transition/batted_hit_prefix_cases_v1.json", 19),
        ]
        or any(
            set(r) != {"path", "revision", "sha256", "caseCount"}
            or type(r["caseCount"]) is not int
            or r["revision"] != historical["revision"]
            or type(r["sha256"]) is not str
            or re.fullmatch(r"[a-f0-9]{64}", r["sha256"]) is None
            for r in sources
        )
    ):
        raise ValueError
    samples = data["samples"]
    if (
        type(samples) is not list
        or len(samples) != 53
        or hashlib.sha256(_canonical_json(samples).encode()).hexdigest()
        != data["samplesSha256"]
        or len({(s["sourcePath"], s["caseId"]) for s in samples}) != 53
    ):
        raise ValueError
    if [sum(s["sourcePath"] == r["path"] for s in samples) for r in sources] != [
        34,
        19,
    ]:
        raise ValueError
    for sample in samples:
        if (
            set(sample)
            != {
                "sourcePath",
                "caseId",
                "originalRequest",
                "oldExpected",
                "currentRequest",
                "currentExpected",
                "oldActual",
                "currentActual",
                "selfActual",
            }
            or type(sample["caseId"]) is not str
            or not sample["caseId"]
        ):
            raise ValueError
        if (
            _canonical_json(sample["oldActual"])
            != _canonical_json(sample["oldExpected"])
            or _canonical_json(sample["currentActual"])
            != _canonical_json(sample["currentExpected"])
            or _canonical_json(sample["selfActual"])
            != _canonical_json(sample["currentExpected"])
        ):
            raise ValueError
        before = copy.deepcopy(sample["originalRequest"])
        after = copy.deepcopy(sample["currentRequest"])
        if (
            before["source"]["executionArtifactSha256"] != legacy
            or after["source"]["executionArtifactSha256"] != current
        ):
            raise ValueError
        before["source"]["executionArtifactSha256"] = after["source"][
            "executionArtifactSha256"
        ] = "SELF"
        before["nextCheckpoint"]["digest"] = after["nextCheckpoint"]["digest"] = "SELF"
        if _canonical_json(before) != _canonical_json(after):
            raise ValueError
        before = copy.deepcopy(sample["oldExpected"])
        after = copy.deepcopy(sample["currentExpected"])
        if (
            before["value"]["executionArtifactSha256"] != legacy
            or after["value"]["executionArtifactSha256"] != current
        ):
            raise ValueError
        before["value"]["executionArtifactSha256"] = after["value"][
            "executionArtifactSha256"
        ] = "SELF"
        before["value"]["nextPrefixRef"]["checkpoint"]["digest"] = after["value"][
            "nextPrefixRef"
        ]["checkpoint"]["digest"] = "SELF"
        if _canonical_json(before) != _canonical_json(after):
            raise ValueError
    if (
        data["fourOperationJoinEvidence"]["rawInputSha256"]
        != data["separateFourOperationEvidence"]["sha256"]
    ):
        raise ValueError
    _validate_four_operation_join(data["fourOperationJoinEvidence"], legacy, current)
    return legacy, historical["registrySha256"]


def _validate_four_operation_join(join, legacy, current):
    """v3証明と分離した旧51d/currentの正確な4操作join根拠だけを検査する。"""
    from typing import cast

    if (
        set(join)
        != {
            "rawInputSha256",
            "comparisonArtifactSha256",
            "executionArtifactSha256",
            "fullCaseCount",
            "groups",
            "measurementSha256",
            "normalizationPointers",
            "scope",
        }
        or join["comparisonArtifactSha256"] != legacy
        or join["executionArtifactSha256"] != current
        or type(join["fullCaseCount"]) is not int
        or join["fullCaseCount"] != 1878
        or join["normalizationPointers"] != []
    ):
        raise ValueError
    for key in ("rawInputSha256", "measurementSha256"):
        if (
            type(join[key]) is not str
            or re.fullmatch(r"[a-f0-9]{64}", join[key]) is None
        ):
            raise ValueError
    expected_scope = {
        "sourceFormats": ["first-ball-play-v1", "ordinary-pitch-play-v1"],
        "onlyFourOperations": True,
        "notV3Evidence": True,
        "notAllPublicOperations": True,
        "HTTPorDB": False,
        "P6Blind": False,
    }
    if _canonical_json(join["scope"]) != _canonical_json(expected_scope):
        raise ValueError
    groups = join["groups"]
    if type(groups) is not list or len(groups) != 2:
        raise ValueError
    operations = ["deriveState", "deriveFirstPitchWithContinuation"]
    for raw_group, fmt, count, ops in zip(
        groups,
        ["first-ball-play-v1", "ordinary-pitch-play-v1"],
        [24, 1854],
        [
            operations,
            operations + ["deriveOrdinaryPitch", "deriveOrdinaryPitchWithContinuation"],
        ],
        strict=True,
    ):
        if type(raw_group) is not dict or any(type(k) is not str for k in raw_group):
            raise ValueError
        group = cast(dict[str, object], raw_group)
        if (
            set(group)
            != {
                "sourceFormat",
                "caseCount",
                "operations",
                "priorFullResponsesSha256",
                "currentFullResponsesSha256",
                "selfFullResponsesSha256",
            }
            or group["sourceFormat"] != fmt
            or type(group["caseCount"]) is not int
            or group["caseCount"] != count
            or group["operations"] != ops
        ):
            raise ValueError
        a, b, c = (
            group[k]
            for k in (
                "priorFullResponsesSha256",
                "currentFullResponsesSha256",
                "selfFullResponsesSha256",
            )
        )
        if (
            type(a) is not str
            or re.fullmatch(r"[a-f0-9]{64}", a) is None
            or a != b
            or a != c
        ):
            raise ValueError
