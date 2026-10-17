"""P3 の変更イベントを対象版と無効化意図とともに確定する。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pitchlog.db.game_state.models import Game
from pitchlog.db.sync_protocol.event_kinds import CHANGE_EVENT_KIND_LITERALS
from pitchlog.db.sync_protocol.models import EventSlot
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import (
    _sync_apply_active,
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync import port_guard
from pitchlog.sync.crash_points import reach
from pitchlog.sync.gate import RG1Blocked, game_accessible, gated_writer
from pitchlog.sync.idempotency import (
    D5Candidate,
    _json_value,
    classify_d5,
    operation_fingerprint,
    recheck_and_insert_result,
)
from pitchlog.sync.invalidation import record_p3_intents
from pitchlog.sync.model import (
    ABSENT,
    AcceptedChangeResult,
    ChangeResult,
    RejectedChangeResult,
    SyncEvent,
    SyncRequest,
)
from pitchlog.sync.ports import (
    ContentValidationPort,
    PortWriter,
    ProjectionPort,
    RecordingRightsPort,
    _issue_port_writer,
)
from pitchlog.sync.prefix_path import _cell, _lock_game_generation, _one_row
from pitchlog.sync.tokens import (
    EventSlotReadToken,
    EventSlotVersionUpdateToken,
    GameReadToken,
    IdempotencyLedgerInsertToken,
    OperationEventInsertToken,
)

_GAME_COLUMNS = tuple(Game.__table__.c.keys())
_SLOT_COLUMNS = tuple(EventSlot.__table__.c.keys())
_MAX_BIGINT = 2**63 - 1


class _D5Race(RuntimeError):
    """先着台帳を見た後、ポートの副作用をロールバックする。"""

    def __init__(self, result: ChangeResult) -> None:
        """ロールバック後へ確定済みの結果を運ぶ。"""
        self.result = result


class _NoWriteResult(RuntimeError):
    """ポートが書いた場合も拒否結果より前に取引全体を戻す。"""

    def __init__(self, result: RejectedChangeResult) -> None:
        """拒否結果をロールバック後へ運ぶ。"""
        self.result = result


def _target(event: SyncEvent) -> tuple[UUID, int, int]:
    """P3 の V10 を試合・世代・D1 の三つ組へ検証する。"""
    value = event.v10
    if not isinstance(value, Mapping) or set(value) != {"game", "d4", "d1"}:
        raise ValueError("V10 の対象参照が不正")
    game, generation, d1 = value["game"], value["d4"], value["d1"]
    if type(generation) is str and generation.isdecimal():
        parsed = int(generation)
        generation = parsed if str(parsed) == generation else generation
    if (
        game != event.game_id
        or type(generation) is not int
        or not 0 < generation <= _MAX_BIGINT
        or type(d1) is not int
        or not 0 < d1 <= _MAX_BIGINT
    ):
        raise ValueError("V10 の対象参照が不正")
    return UUID(event.game_id), generation, d1


def _accepted_from_candidate(candidate: D5Candidate, d5: str) -> ChangeResult | None:
    """I2/I3 の再掲または D5 衝突を新たな書き込みなしで返す。"""
    if candidate.kind == "unused":
        return None
    if candidate.kind == "conflict":
        return RejectedChangeResult("B13", d5, "同じ D5 の内容が異なる")
    stored = candidate.stored
    if stored is None or stored.kind != "accepted":
        return RejectedChangeResult("B13", d5, "D5 は別の結果に使用済み")
    value = stored.result
    reference = value.get("target_reference")
    version = value.get("expected_version")
    content = value.get("confirmed_content")
    accepted_at = value.get("accepted_at")
    if (
        not isinstance(reference, Mapping)
        or type(version) is not int
        or not isinstance(content, Mapping)
        or type(accepted_at) is not str
    ):
        raise RuntimeError("P3 の保存済み結果の形が不正")
    return AcceptedChangeResult(reference, version, d5, content, accepted_at)


def _apply_locked(
    scope: _TenantTransaction,
    request: SyncRequest,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    writer: PortWriter | None = None,
) -> ChangeResult:
    """③〜⑨を順に判定し、未使用 D5 だけを一取引で確定する。"""
    event = request.events[0]
    game_id = UUID(request.game_id)
    locked = _lock_game_generation(scope, game_id)
    if locked is None:
        raise RuntimeError("認可後に試合行が消失した")
    generation, _ = locked
    game_row = _one_row(scope.run(GameReadToken(game_id)), "games")
    status = _cell(game_row, _GAME_COLUMNS, "status")

    for port in (rights, projection, validator):
        port_guard.require_registered_port(port)
    own_writer = writer is None
    if writer is None:
        writer = _issue_port_writer(scope.run)
    try:
        supplied = request.recovery_generation
        if type(supplied) is not str or not rights.is_recovery_generation_current(
            event.game_id, supplied, writer
        ):
            raise _NoWriteResult(
                RejectedChangeResult(
                    "B9",
                    event.d5,
                    "要求作成時の復旧世代が旧世代",
                    b9_cause="旧復旧世代",
                )
            )

        fingerprint = operation_fingerprint(event, "P3", None)
        candidate = classify_d5(scope, UUID(event.d5), fingerprint, "P3")
        previous = _accepted_from_candidate(candidate, event.d5)
        if previous is not None:
            raise _D5Race(previous)

        if status not in ("in_progress", "finished"):
            raise _NoWriteResult(
                RejectedChangeResult(
                    "B14", event.d5, "変更対象の試合が進行中・終了後ではない"
                )
            )

        if status == "in_progress" and (
            request.v12 is ABSENT
            or not rights.holds_recording_right(
                event.game_id, str(generation), request.v12, writer
            )
        ):
            raise _NoWriteResult(
                RejectedChangeResult(
                    "B9", event.d5, "現在の記録権証明がない", b9_cause="記録権不保持"
                )
            )
        if type(event.v5) is not str or event.v5 not in CHANGE_EVENT_KIND_LITERALS:
            raise _NoWriteResult(
                RejectedChangeResult("B14", event.d5, "P3 のイベント種別が不正")
            )
        if not isinstance(event.v7, Mapping):
            raise _NoWriteResult(
                RejectedChangeResult("B14", event.d5, "P3 の内容は JSON object が必要")
            )
        try:
            target = _target(event)
        except ValueError:
            raise _NoWriteResult(
                RejectedChangeResult("B14", event.d5, "V10 の対象参照が不正")
            ) from None
        if type(event.v11) is not int or not 0 < event.v11 < _MAX_BIGINT:
            raise _NoWriteResult(
                RejectedChangeResult("B14", event.d5, "V11 の期待版が不正")
            )
        valid, reason = validator.validate(event, writer)
        if not valid:
            raise _NoWriteResult(
                RejectedChangeResult(
                    "B14", event.d5, reason or "変更内容を受理できない"
                )
            )

        slot_rows = scope.run(EventSlotReadToken(*target)).rows
        if not slot_rows:
            raise _NoWriteResult(
                RejectedChangeResult("B14", event.d5, "変更対象が存在しない")
            )
        if len(slot_rows) != 1:
            raise RuntimeError("event_slots の対象行が一件ではない")
        slot = slot_rows[0]
        current_version = _cell(slot, _SLOT_COLUMNS, "confirmed_version")
        if type(current_version) is not int:
            raise RuntimeError("対象の確定版の型が不正")
        if current_version != event.v11:
            raise _NoWriteResult(
                RejectedChangeResult(
                    "B8",
                    event.d5,
                    f"現在版: {current_version}",
                    current_version=current_version,
                )
            )

        accepted_at = datetime.now(UTC).isoformat()
        reference = {
            "試合": event.game_id,
            "対象の D4": target[1],
            "対象の D1": target[2],
        }
        result = AcceptedChangeResult(
            reference, event.v11, event.d5, event.v7, accepted_at
        )
        result_json = json.dumps(
            {
                "target_reference": reference,
                "expected_version": event.v11,
                "d5": event.d5,
                "confirmed_content": _json_value(event.v7),
                "accepted_at": accepted_at,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        raced = recheck_and_insert_result(
            scope,
            IdempotencyLedgerInsertToken(
                UUID(event.d5), "accepted", fingerprint, result_json
            ),
            "P3",
        )
        if raced is not None:
            outcome = _accepted_from_candidate(raced, event.d5)
            if outcome is None:
                raise RuntimeError("D5 再照合が未使用に戻った")
            raise _D5Race(outcome)
        reach("after_t1_ledger")
        reach("after_t6_result")

        updated = scope.run(
            EventSlotVersionUpdateToken(*target, event.v11, event.v11 + 1)
        )
        if updated.rows != ((1,),):
            raise RuntimeError("試合行ロック下で対象版の CAS が失敗")
        payload_json = json.dumps(
            _json_value(event.v7), ensure_ascii=False, sort_keys=True
        )
        scope.run(
            OperationEventInsertToken(
                uuid4(),
                game_id,
                UUID(event.d5),
                event.v5,
                payload_json,
                target_generation=target[1],
                target_d1=target[2],
                expected_version=event.v11,
            )
        )
        reach("after_t2_event")
        projection.apply(event, writer)
        reach("after_t4_projection")
        record_p3_intents(scope, game_id, target[1], target[2], event.v11 + 1)
        reach("after_t7_intents")
        return result
    finally:
        if own_writer:
            writer._close()


def apply_p3_change(
    context: TenantContext,
    request: SyncRequest,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
) -> ChangeResult:
    """P3 一件を適用する。認証は公開入口が所有する。"""
    if request.path != "P3" or len(request.events) != 1:
        raise ValueError("P3 の要求 1 件が必要")
    if not game_accessible(context, UUID(request.game_id), tenant_transaction_scope):
        return RejectedChangeResult("B12", request.events[0].d5)
    try:
        with tenant_transaction_scope(context) as scope:
            with _sync_apply_active():
                with gated_writer(scope, rights) as gated:
                    result = _apply_locked(
                        scope, request, rights, projection, validator, gated.writer
                    )
                    if isinstance(result, AcceptedChangeResult):
                        gated.mark_written()
                    return result
    except _D5Race as race:
        return race.result
    except _NoWriteResult as rejected:
        return rejected.result
    except RG1Blocked:
        return RejectedChangeResult("B10", request.events[0].d5, "復元調整中")
