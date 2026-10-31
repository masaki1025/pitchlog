"""v2の実source readerとstorage anchor/wire headの別表現。資格はJSONから発行しない。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.first_pitch import _Frozen, _invalid_constant, _unique_object
from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.domainrt.play_prefix_continuation import (
    BridgeEvidence,
    Participants,
    PaStartSource,
    PlayPrefixRef,
    PlayPrefixSource,
    PlayT2,
    RunnerSnapshot,
)
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
