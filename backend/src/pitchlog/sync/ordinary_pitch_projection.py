"""実ordinary frameからだけ同TXのDB準備/PlayRow/checkpoint投影を行う核。"""

from __future__ import annotations

from uuid import UUID, uuid4

from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.first_ball_operations import _one
from pitchlog.repositories.ordinary_pitch_qualification import (
    PrepareOrdinaryProjectionToken,
)
from pitchlog.repositories.ordinary_prefix import read_checkpoint_document
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.ordinary_pitch_execution import (
    OrdinaryPitchExecutionError,
    _bind_ordinary_preparation,
    _consume_ordinary_pitch_frame,
    _live,
)
from pitchlog.sync.ordinary_pitch_physical import ordinary_pitch_physical_row
from pitchlog.sync.ordinary_pitch_tokens import (
    OrdinaryPlayRowInsertToken,
    ProjectOrdinaryPitchToken,
)
from pitchlog.sync.tokens import OperationEventReadToken


def apply_ordinary_pitch_projection(handle, operation):
    """自由record/成功boolを受けず、実frame消費から有限SQLだけを実行する。"""
    if type(operation) is not ProjectOrdinaryPitchToken:
        raise OrdinaryPitchExecutionError
    state = _consume_ordinary_pitch_frame(handle, operation.projected, operation.writer)
    if operation.game_id != UUID(state.event.game_id) or operation.d5 != UUID(
        state.event.d5
    ):
        raise OrdinaryPitchExecutionError
    _live(state)
    prefix, payload = state.prefix, state.payload
    if prefix is None or payload is None or state.frame_id is None:
        raise OrdinaryPitchExecutionError
    doc = prefix.checkpoint
    generation = int(doc.internal_generation)
    projected = operation.projected
    record = _one(
        handle.run(
            OperationEventReadToken(operation.game_id, generation, projected.d1)
        ),
        tuple(OperationEvent.__table__.c.keys()),
    )
    expected = {
        "tenant_id": handle._bound_tenant_id,
        "game_id": operation.game_id,
        "generation": generation,
        "d1": projected.d1,
        "d2": projected.v6,
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
    if type(record["id"]) is not UUID:
        raise OrdinaryPitchExecutionError
    view = state.source.read(handle, state.event)
    source = {
        "id": str(record["id"]),
        "tenant_id": str(handle._bound_tenant_id),
        "game_id": str(operation.game_id),
        "generation": str(generation),
        "d1": str(record["d1"]),
        "d2": str(record["d2"]),
        "d5": str(operation.d5),
        "source_fingerprint": view.event_fingerprint,
        "event_fingerprint": view.event_fingerprint,
    }
    calc = payload.calculation
    response = calc.response.value
    previous = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
    after = {
        **previous,
        "revision": str(int(doc.revision) + 1),
        "prefix_ref": response.next_prefix_ref.model_dump(mode="json", by_alias=True),
        "confirmed_watermark": str(projected.d1),
        "applied_watermark": str(projected.d1),
        "last_source": source,
        "history_depth": str(int(doc.history_depth) + 1),
        "after": response.t1.after.model_dump(mode="json", by_alias=True),
        "t2": response.t2.model_dump(mode="json", by_alias=True, exclude_unset=True),
    }
    after["content_digest"] = source_fingerprint(
        {k: v for k, v in after.items() if k != "content_digest"}
    )
    # 数学を再計算せず、次checkpointの全構造/相関/digestを確認する。
    next_document = read_checkpoint_document(_canonical_json(after))
    row = ordinary_pitch_physical_row(
        payload,
        tenant_id=handle._bound_tenant_id,
        game_id=operation.game_id,
        source_event_id=record["id"],
        row_id=uuid4(),
        play_number=prefix.next_play_number,
    )
    prepared = {
        "checkpoint": previous,
        "next_checkpoint": next_document.model_dump(
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
    # source/前後checkpoint/評価/最終行を一つの封筒へ束縛する。自由hashを受けない。
    prepared["frame_digest"] = source_fingerprint(
        {
            **prepared,
            "request": calc.request.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "response": calc.response.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
        }
    )
    lease = state.source.bound._lease
    _live(state)
    token = PrepareOrdinaryProjectionToken(
        lease.attempt_id,
        lease.phase_id,
        lease.nonce,
        lease.device_id,
        operation.game_id,
        _canonical_json(prepared),
    )
    with _bind_ordinary_preparation(state, token):
        admitted = handle.run_function(token)
    if type(admitted) is not TenantOperationResult or admitted.rows != ((True,),):
        raise OrdinaryPitchExecutionError
    _live(state)
    result = handle.run(
        OrdinaryPlayRowInsertToken(
            operation.game_id,
            generation,
            projected.d1,
            projected.v6,
            operation.d5,
            view.event_fingerprint,
            _canonical_json(row),
        )
    )
    if type(result) is not TenantOperationResult or result.rows != ((1,),):
        raise OrdinaryPitchExecutionError
    _live(state)
    state.phase = "projected"
    return TenantOperationResult(((True,),))
