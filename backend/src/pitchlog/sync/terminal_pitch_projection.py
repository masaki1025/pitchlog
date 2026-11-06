"""真正v2 frameの同TX親/runner/履歴投影。野球計算は実artifactだけが行う。"""

from __future__ import annotations

from uuid import UUID, uuid5

from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.first_ball_operations import _one
from pitchlog.repositories.play_prefix import read_play_prefix_document
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.ordinary_pitch_execution import (
    OrdinaryPitchExecutionError,
    _bind_ordinary_preparation,
    _consume_ordinary_pitch_frame,
    _live,
)
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.terminal_pitch_payload import verify_play_prefix_seal
from pitchlog.sync.terminal_pitch_tokens import (
    PlayPrefixCheckpointLockToken,
    PlayPrefixPlayRowInsertToken,
    PreparePlayPrefixProjectionToken,
    ProjectLineupPrefixToken,
    ProjectPlayPrefixToken,
)
from pitchlog.sync.tokens import OperationEventReadToken


def runner_physical_rows(before_runners, *, t1, tenant_id, play_id):
    """before各塁の実T1進塁結果を全10列へ写す。after占有は別保持する。"""
    slots = {"1": "first", "2": "second", "3": "third"}
    for runner in before_runners:
        effect = getattr(t1.runner_default_advance, slots[runner.base])
        if effect.modality == "not-applicable":
            raise OrdinaryPitchExecutionError
        if effect.modality == "hold" and effect.destination is not None:
            raise OrdinaryPitchExecutionError
        if effect.modality in {"optional", "forced"} and effect.destination not in {
            "1", "2", "3", "4"
        }:
            raise OrdinaryPitchExecutionError
    return [
        {
            "tenant_id": str(tenant_id),
            "id": str(uuid5(play_id, "play-prefix-runner:" + runner.base)),
            "play_id": str(play_id),
            "base": int(runner.base),
            "runner_id": runner.runner_id,
            "status": runner.status,
            "status_source": runner.status_source,
            "responsible_pitcher_id": runner.responsible_pitcher_id,
            "import_batch_id": None,
            "retired_at": None,
        }
        for runner in sorted(before_runners, key=lambda item: int(item.base))
    ]


def build_play_prefix_preparation(state, record, tenant_id):
    """実frame/原本から保存封筒を構成する。自由期待値や再計算を受けない。"""
    prefix, payload = state.prefix, state.payload
    if prefix is None or payload is None or state.frame_id is None:
        raise OrdinaryPitchExecutionError
    calc = payload.calculation
    verify_play_prefix_seal(calc)
    request, response = calc.request, calc.response.value
    identity = request.play_identity
    doc = prefix.checkpoint
    projected = state.projected
    if (
        projected is None
        or identity.event_id != str(record["id"])
        or identity.d5 != projected.d5
        or request.source.position.d1 != str(projected.d1)
        or request.source.position.d2 != str(projected.v6)
    ):
        raise OrdinaryPitchExecutionError
    view = state.source.read(state.handle, state.event)
    source = {
        "id": str(record["id"]),
        "tenant_id": str(tenant_id),
        "game_id": projected.game_id,
        "generation": doc.internal_generation,
        "d1": str(projected.d1),
        "d2": str(projected.v6),
        "d5": projected.d5,
        "source_fingerprint": view.event_fingerprint,
        "event_fingerprint": view.event_fingerprint,
    }
    row = pitch_physical_row(
        payload.observations,
        payload.participants,
        request.t1.result_id,
        tenant_id=tenant_id,
        game_id=UUID(projected.game_id),
        source_event_id=record["id"],
        row_id=UUID(identity.play_id),
        play_number=prefix.next_play_number,
    )
    runners = runner_physical_rows(
        request.source.runners,
        t1=response.t1,
        tenant_id=tenant_id,
        play_id=UUID(identity.play_id),
    )
    previous = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
    anchor = previous.get(
        "storage_anchor", {"id": doc.id, "history_epoch": doc.history_version}
    )
    bridge = previous.get("bridge_origin") or request.source.bridge.model_dump(
        mode="json", by_alias=True
    )
    pa_start = (
        {"kind": "confirmed-play", "id": identity.event_id}
        if response.t1.plate_appearance_ended
        else request.source.responsibility.pa_start_source.model_dump(
            mode="json", by_alias=True
        )
    )
    after = {
        "version": "2",
        "id": doc.id,
        "revision": response.next_prefix_ref.checkpoint.revision,
        "history_version": anchor["history_epoch"],
        "storage_anchor": anchor,
        "prefix_ref": response.next_prefix_ref.model_dump(mode="json", by_alias=True),
        "wire_d4": doc.wire_d4,
        "internal_generation": doc.internal_generation,
        "recovery_generation": doc.recovery_generation,
        "confirmed_watermark": str(projected.d1),
        "applied_watermark": str(projected.d1),
        "last_source": source,
        "history_depth": response.next_prefix_ref.length,
        "after": response.t1.after.model_dump(mode="json", by_alias=True),
        "rules": request.rules.model_dump(mode="json", by_alias=True),
        "t2": response.t2.model_dump(mode="json", by_alias=True),
        "runners": [r.model_dump(mode="json", by_alias=True) for r in response.runners],
        "participants": response.participants.model_dump(mode="json", by_alias=True),
        "pa_start_source": pa_start,
        "roster_digest": doc.roster_digest,
        "artifact_sha256": calc.artifact_sha256,
        "state": "current",
        "bridge_origin": bridge,
        "projection_snapshot": {"play_row": row, "play_runners": runners},
    }
    after["content_digest"] = source_fingerprint(after)
    next_doc = read_play_prefix_document(_canonical_json(after))
    prepared = {
        "checkpoint": previous,
        "next_checkpoint": next_doc.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
        "roster": prefix.roster.model_dump(mode="json", by_alias=True),
        "frame_id": str(state.frame_id),
        "artifact_sha256": calc.artifact_sha256,
        "source": source,
        "play_row": row,
        "history_entry": response.new_history_entry.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
    }
    prepared["frame_digest"] = source_fingerprint(
        {
            **prepared,
            "request": request.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "response": calc.response.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
        }
    )
    return prepared


def apply_play_prefix_projection(handle, operation):
    """AFTER triggerによるrunner/印消費まで終わった親INSERTだけを成功とする。"""
    if type(operation) not in {ProjectPlayPrefixToken, ProjectLineupPrefixToken}:
        raise OrdinaryPitchExecutionError
    state = _consume_ordinary_pitch_frame(
        handle,
        operation.projected,
        operation.writer,
        mode="play-prefix-play-v3"
        if type(operation) is ProjectLineupPrefixToken
        else "play-prefix-play-v2",
    )
    if operation.game_id != UUID(state.event.game_id) or operation.d5 != UUID(
        state.event.d5
    ):
        raise OrdinaryPitchExecutionError
    doc = state.prefix.checkpoint
    record = _one(
        handle.run(
            OperationEventReadToken(
                operation.game_id, int(doc.internal_generation), operation.projected.d1
            )
        ),
        tuple(OperationEvent.__table__.c.keys()),
    )
    expected = {
        "tenant_id": handle._bound_tenant_id,
        "game_id": operation.game_id,
        "generation": int(doc.internal_generation),
        "d1": operation.projected.d1,
        "d2": operation.projected.v6,
        "d5": operation.d5,
        "ledger_kind": "accepted",
        "event_kind": "play_input",
        "is_tombstone": False,
        "replaced_at": None,
        "retired_at": None,
        "import_batch_id": None,
        "legacy_row_identifier": None,
        "migration_unverified": False,
    }
    if any(
        type(record[k]) is not type(v) or record[k] != v for k, v in expected.items()
    ):
        raise OrdinaryPitchExecutionError
    builder = (
        build_lineup_prefix_preparation
        if type(operation) is ProjectLineupPrefixToken
        else build_play_prefix_preparation
    )
    prepared = builder(state, record, handle._bound_tenant_id)
    lease = state.source.bound._lease
    token = PreparePlayPrefixProjectionToken(
        lease.attempt_id,
        lease.phase_id,
        lease.nonce,
        lease.device_id,
        operation.game_id,
        _canonical_json(prepared),
    )
    _live(state)
    with _bind_ordinary_preparation(state, token):
        result = handle.run_function(token)
    if type(result) is not TenantOperationResult or result.rows != ((True,),):
        raise OrdinaryPitchExecutionError
    result = handle.run(
        PlayPrefixPlayRowInsertToken(
            operation.game_id,
            int(doc.internal_generation),
            operation.projected.d1,
            operation.projected.v6,
            operation.d5,
            prepared["source"]["source_fingerprint"],
            _canonical_json(prepared["play_row"]),
        )
    )
    if type(result) is not TenantOperationResult or result.rows != ((1,),):
        raise OrdinaryPitchExecutionError
    from pitchlog.repositories.ordinary_prefix_read import _function_one

    saved = _function_one(
        handle,
        PlayPrefixCheckpointLockToken(
            lease.attempt_id,
            lease.phase_id,
            lease.nonce,
            lease.device_id,
            operation.game_id,
            int(doc.internal_generation),
        ),
    )
    nonplay = (
        prepared["next_checkpoint"].get("formatVersion") == "nonplay-normal-storage-v1"
    )
    if nonplay:
        from pitchlog.domainrt.lineup_play_prefix_continuation import NonplayCheckpoint
        from pitchlog.repositories.nonplay_prefix_read import read_active_page

        actual = prepared["next_checkpoint"]["checkpoint"]
        if saved is None or _canonical_json(saved.get("content")) != _canonical_json(
            actual
        ):
            raise OrdinaryPitchExecutionError
        page = read_active_page(
            handle,
            NonplayCheckpoint.model_validate_json(_canonical_json(actual)),
            generation=int(doc.internal_generation),
            limit=1,
        )
        if len(page["items"]) != 1 or page["items"][0]["play"]["source"][
            "eventId"
        ] != str(record["id"]):
            raise OrdinaryPitchExecutionError
    elif (
        saved is None
        or saved.get("content") != prepared["next_checkpoint"]
        or saved.get("last_play_row") != prepared["play_row"]
        or saved.get("last_play_runners")
        != prepared["next_checkpoint"]["projection_snapshot"]["play_runners"]
        or saved.get("saved_at") is None
    ):
        raise OrdinaryPitchExecutionError
    _live(state)
    state.phase = "projected"
    return TenantOperationResult(((True,),))


def build_lineup_prefix_preparation(state, record, tenant_id):
    """v3実frameのbefore物理行とafter両cursorを別の保存面へ写す。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        verify_lineup_wire_seal,
    )
    from pitchlog.repositories.play_prefix import read_lineup_prefix_document
    from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload

    if (
        state.prefix is None
        or type(state.payload) is not LineupPitchPlayPayload
        or state.frame_id is None
    ):
        raise OrdinaryPitchExecutionError
    calc = state.payload.calculation
    from pitchlog.sync.terminal_pitch_payload import NonplayPitchCalculation

    if type(calc) is NonplayPitchCalculation:
        return build_nonplay_normal_preparation(state, record, tenant_id)
    request, response = calc.request, calc.response.value
    verify_lineup_wire_seal(request, calc.response)
    doc = state.prefix.checkpoint
    projected = state.projected
    identity = request.play_identity
    if (
        projected is None
        or identity.event_id != str(record["id"])
        or identity.d5 != projected.d5
        or request.source.position.d1 != str(projected.d1)
        or request.source.position.d2 != str(projected.v6)
    ):
        raise OrdinaryPitchExecutionError
    view = state.source.read(state.handle, state.event)
    source = {
        "id": str(record["id"]),
        "tenant_id": str(tenant_id),
        "game_id": projected.game_id,
        "generation": doc.internal_generation,
        "d1": str(projected.d1),
        "d2": str(projected.v6),
        "d5": projected.d5,
        "source_fingerprint": view.event_fingerprint,
        "event_fingerprint": view.event_fingerprint,
    }
    row = pitch_physical_row(
        state.payload.observations,
        state.payload.participants,
        request.t1.result_id,
        tenant_id=tenant_id,
        game_id=UUID(projected.game_id),
        source_event_id=record["id"],
        row_id=UUID(identity.play_id),
        play_number=state.prefix.next_play_number,
    )
    runners = runner_physical_rows(
        request.source.runners,
        t1=response.t1,
        tenant_id=tenant_id,
        play_id=UUID(identity.play_id),
    )
    previous = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
    after = {
        **previous,
        "revision": response.next_prefix_ref.checkpoint.revision,
        "prefix_ref": response.next_prefix_ref.model_dump(mode="json", by_alias=True),
        "confirmed_watermark": str(projected.d1),
        "applied_watermark": str(projected.d1),
        "last_source": source,
        "history_depth": response.next_prefix_ref.length,
        "after": response.t1.after.model_dump(mode="json", by_alias=True),
        "t2": response.t2.model_dump(mode="json", by_alias=True),
        "runners": [r.model_dump(mode="json", by_alias=True) for r in response.runners],
        "participants": response.participants.model_dump(mode="json", by_alias=True),
        "pa_start_source": response.next_responsibility.pa_start_source.model_dump(
            mode="json", by_alias=True
        ),
        "lineup": response.lineup.model_dump(mode="json", by_alias=True),
        "roster_digest": response.roster_digest,
        "previous_prefix_ref": response.previous_prefix_ref.model_dump(
            mode="json", by_alias=True
        ),
        "artifact_sha256": calc.artifact_sha256,
        "projection_snapshot": {"play_row": row, "play_runners": runners},
    }
    del after["content_digest"]
    after["content_digest"] = source_fingerprint(after)
    next_doc = read_lineup_prefix_document(_canonical_json(after))
    prepared = {
        "checkpoint": previous,
        "next_checkpoint": next_doc.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
        "roster": state.prefix.roster.model_dump(mode="json", by_alias=True),
        "frame_id": str(state.frame_id),
        "artifact_sha256": calc.artifact_sha256,
        "source": source,
        "play_row": row,
        "history_entry": response.new_history_entry.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
    }
    prepared["frame_digest"] = source_fingerprint(
        {
            **prepared,
            "request": request.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "response": calc.response.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
        }
    )
    return prepared


def build_nonplay_normal_preparation(state, record, tenant_id):
    """実非playCPに通常球をappend。logical echoは保存ID/digestに転用しない。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import NonplayCheckpoint
    from pitchlog.repositories.nonplay_prefix_read import ConfirmedNonplayNormalPrefix
    from pitchlog.sync.terminal_pitch_payload import NonplayPitchCalculation

    if (
        type(state.prefix) is not ConfirmedNonplayNormalPrefix
        or type(state.payload.calculation) is not NonplayPitchCalculation
        or state.frame_id is None
    ):
        raise OrdinaryPitchExecutionError
    calc = state.payload.calculation
    q = calc.request
    r = calc.response.value
    cp = state.prefix.checkpoint.document
    event = state.projected
    if (
        event is None
        or q.source.checkpoint != cp
        or q.play_identity.event_id != str(record["id"])
        or q.play_identity.d5 != event.d5
        or q.source_position.d1 != str(event.d1)
        or q.source_position.d2 != str(event.v6)
    ):
        raise OrdinaryPitchExecutionError
    view = state.source.read(state.handle, state.event)
    identity = {
        "eventId": str(record["id"]),
        "gameId": event.game_id,
        "generation": event.d4,
        "d1": str(event.d1),
        "d5": event.d5,
        "fingerprint": view.event_fingerprint,
        "eventKind": "play_input",
    }
    row = pitch_physical_row(
        state.payload.observations,
        state.payload.participants,
        q.t1.result_id,
        tenant_id=tenant_id,
        game_id=UUID(event.game_id),
        source_event_id=record["id"],
        row_id=UUID(q.play_identity.play_id),
        play_number=state.prefix.next_play_number,
    )
    before = cp.content.restored
    runners = runner_physical_rows(
        before.runners,
        t1=r.t1,
        tenant_id=tenant_id,
        play_id=UUID(q.play_identity.play_id),
    )
    raw = cp.model_dump(mode="json", by_alias=True)
    old = raw["content"]
    value = r.model_dump(mode="json", by_alias=True, exclude_unset=True)
    restored = {
        "current": value["t1"]["after"],
        **{k: old["restored"][k] for k in ("rules", "rulesDigest", "layoutDigest")},
        **{k: value[k] for k in ("rosterDigest", "lineup", "participants", "runners")},
        "responsibility": value["nextResponsibility"],
        "lastPlayEvaluation": value["t2"],
    }
    head = {
        "source": identity,
        "playId": q.play_identity.play_id,
        "d2": str(event.v6),
        "physicalPlayNumber": str(state.prefix.next_play_number),
    }
    content = {
        **old,
        "d3": str(event.d1),
        "d1Head": {"kind": "accepted-event", "source": identity},
        "projectionHead": {"kind": "d1-event", "source": identity},
        "activeHead": head,
        "activeDepth": str(int(old["activeDepth"]) + 1),
        "historyVersion": str(int(old["historyVersion"]) + 1),
        "nextPhysicalPlayNumber": str(state.prefix.next_play_number + 1),
        "restored": restored,
    }
    actual = {
        "formatVersion": raw["formatVersion"],
        "ref": {
            "id": cp.ref.id,
            "revision": str(int(cp.ref.revision) + 1),
            "digest": source_fingerprint(content),
        },
        "content": content,
    }
    NonplayCheckpoint.model_validate_json(_canonical_json(actual))
    source = {
        "id": str(record["id"]),
        "tenant_id": str(tenant_id),
        "game_id": event.game_id,
        "generation": str(state.prefix.checkpoint.internal_generation),
        "d1": str(event.d1),
        "d2": str(event.v6),
        "d5": event.d5,
        "source_fingerprint": view.event_fingerprint,
        "event_fingerprint": view.event_fingerprint,
    }
    prepared = {
        "checkpoint": raw,
        "next_checkpoint": {
            "formatVersion": "nonplay-normal-storage-v1",
            "checkpoint": actual,
            "projection_snapshot": {"play_row": row, "play_runners": runners},
        },
        "roster": state.prefix.roster.model_dump(mode="json", by_alias=True),
        "frame_id": str(state.frame_id),
        "artifact_sha256": calc.artifact_sha256,
        "source": source,
        "play_row": row,
        "history_entry": value["newHistoryEntry"],
    }
    prepared["frame_digest"] = source_fingerprint(
        {
            **prepared,
            "request": q.model_dump(mode="json", by_alias=True, exclude_unset=True),
            "response": calc.response.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
        }
    )
    return prepared
