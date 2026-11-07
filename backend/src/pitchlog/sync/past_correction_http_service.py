"""P3の既対象読取とopaque参照のbinding形成をtransportから分離する。"""

from typing import cast
from uuid import UUID

from pitchlog.db.sync_protocol.models import EventSlot
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixView,
    _function_one,
    read_lineup_prefix,
)
from pitchlog.repositories.past_correction_current import (
    PastCorrectionCurrentUnavailable,
    verify_p3_current_packet,
)
from pitchlog.repositories.past_correction_current_paged import (
    read_verified_p3_paged_current,
)
from pitchlog.repositories.past_correction_right import _ReadP3CurrentToken
from pitchlog.repositories.past_correction_source import (
    PastCorrectionSourceUnavailable,
    read_past_correction_v3_source_snapshot,
    read_past_correction_watermark,
    visit_past_correction_v3_source_pages,
)
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.sync.control_provider.binding_client import BindingClientConfiguration
from pitchlog.sync.control_provider.evidence import AttemptBinding, AuthorityBinding
from pitchlog.sync.http_recording_key import _decode_recording_key
from pitchlog.sync.idempotency import _json_value
from pitchlog.sync.model import AcceptedChangeResult, RejectedChangeResult
from pitchlog.sync.tokens import EventSlotReadToken


def read_change_target_snapshot(
    game_id: UUID, d1: int, context: TenantContext
) -> dict[str, object]:
    """既同TXの真正対象原本を全条件一致時だけ返す。"""
    with tenant_transaction_scope(context) as scope:
        generation, watermark = read_past_correction_watermark(scope, game_id)
        if d1 < 1 or d1 > watermark:
            raise PastCorrectionSourceUnavailable("P3対象水位が不正")
        if watermark > 25:
            target_rows = []

            def capture(page, _checkpoint):
                """全頁照合中に要求対象一件だけを保持する。"""
                target_rows.extend((row for row in page if row.d1 == d1))

            proof = visit_past_correction_v3_source_pages(scope, game_id, d1, capture)
            if (
                proof.internal_generation != generation
                or proof.watermark != watermark
                or len(target_rows) != 1
            ):
                raise PastCorrectionSourceUnavailable("P3対象頁が不一致")
            checkpoint = proof.checkpoint
            saved = target_rows[0]
            current_ref = checkpoint.prefix_ref
        else:
            snapshot = read_past_correction_v3_source_snapshot(scope, game_id, d1)
            if (
                snapshot.internal_generation != generation
                or len(snapshot.rows) != watermark
                or snapshot.checkpoint is None
            ):
                raise PastCorrectionSourceUnavailable("P3対象のCPがありません")
            checkpoint = snapshot.checkpoint
            saved = snapshot.rows[d1 - 1]
            current_ref = snapshot.rows[-1].calculation.response.value.next_prefix_ref
        rows = scope.run(EventSlotReadToken(game_id, generation, d1)).rows
        columns = tuple(EventSlot.__table__.c.keys())
        if len(rows) != 1 or len(rows[0]) != len(columns):
            raise PastCorrectionSourceUnavailable("P3対象版がありません")
        slot = dict(zip(columns, rows[0], strict=True))
        if (
            slot["tenant_id"] != context.tenant_id
            or slot["game_id"] != game_id
            or slot["generation"] != generation
            or (slot["d1"] != d1)
            or (type(slot["confirmed_version"]) is not int)
            or (slot["confirmed_version"] != 1)
            or (saved.play_row is None)
            or (saved.play_row.get("source_event_id") != str(saved.source_event_id))
            or (
                saved.play_row.get("id")
                != saved.calculation.request.play_identity.play_id
            )
            or (
                checkpoint.wire_d4
                != saved.calculation.response.value.next_prefix_ref.generation
            )
        ):
            raise PastCorrectionSourceUnavailable("P3対象版と原本が不一致")
        return {
            "target_reference": {
                "game": str(game_id),
                "d4": checkpoint.wire_d4,
                "d1": d1,
            },
            "expected_version": slot["confirmed_version"],
            "expected_prefix_ref": current_ref.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "target_event_id": str(saved.source_event_id),
            "target_play_id": saved.play_row["id"],
            "original_result_id": saved.calculation.request.t1.result_id,
        }


def read_change_confirmation_snapshot(
    game_id: UUID, d1: int, context: TenantContext
) -> dict[str, object]:
    """既同TXの真正対象原本を全条件一致時だけ返す。"""
    with tenant_transaction_scope(context) as scope:
        current = read_lineup_prefix(scope, game_id, limit=25)
        if type(current) is not OrdinaryPrefixView:
            raise PastCorrectionCurrentUnavailable("現v3がありません")
        generation = _decode_recording_key(
            current.metadata.current_d4, context.tenant_id, game_id
        )
        paged = read_verified_p3_paged_current(
            scope, game_id, generation, selected_after_d1=d1 - 1, selected_limit=1
        )
        if paged is None:
            packet = _function_one(scope, _ReadP3CurrentToken(game_id, generation))
            verified = verify_p3_current_packet(
                packet, tenant=context.tenant_id, game=game_id, generation=generation
            )
            if d1 > len(verified.items):
                raise PastCorrectionCurrentUnavailable("P3対象水位が不一致")
            target_item = verified.items[d1 - 1]
        else:
            verified = paged
            target_item = paged.target_item
        page = current.projection.get("page")
        if (
            verified.target_d1 != d1
            or verified.checkpoint.prefix_ref != current.projection.get("prefix_ref")
            or verified.checkpoint.after != current.projection.get("after")
            or (type(page) is not dict)
            or (paged is None and page.get("next_cursor") is not None)
        ):
            raise PastCorrectionCurrentUnavailable("P3現readとの照合が不一致")
        rows = scope.run(EventSlotReadToken(game_id, generation, d1)).rows
        columns = tuple(EventSlot.__table__.c.keys())
        if len(rows) != 1 or len(rows[0]) != len(columns):
            raise PastCorrectionCurrentUnavailable("P3対象slotがありません")
        slot = dict(zip(columns, rows[0], strict=True))
        target = target_item["play_row"]
        if (
            slot["tenant_id"] != context.tenant_id
            or slot["game_id"] != game_id
            or slot["generation"] != generation
            or (slot["d1"] != d1)
            or (type(slot["confirmed_version"]) is not int)
            or (slot["confirmed_version"] != 2)
            or (type(target) is not dict)
            or (target.get("source_event_id") != str(verified.change_event_id))
            or (target.get("id") != target_item["effective_play_row_id"])
        ):
            raise PastCorrectionCurrentUnavailable("P3対象版が不一致")
        play = cast(dict[str, object], target)
        return {
            "target_reference": {
                "game": str(game_id),
                "d4": current.metadata.current_d4,
                "d1": d1,
            },
            "confirmed_version": slot["confirmed_version"],
            "d5": str(verified.d5),
            "source_event_id": str(verified.change_event_id),
            "target_play_id": play["id"],
            "stats_version_id": str(verified.stats_version_id),
            "current_prefix_ref": verified.checkpoint.prefix_ref.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "current_after": verified.checkpoint.after.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
        }


def change_attempt_binding(
    configuration: BindingClientConfiguration,
    tenant: UUID,
    device: UUID,
    game: UUID,
    wire_d4: str,
    attempt: UUID,
    request_fingerprint: str,
) -> AttemptBinding:
    """既参照codecの内部位置を、そのまま同じ真正要求のbindingへ渡す。"""
    internal_generation = _decode_recording_key(wire_d4, tenant, game)
    return AttemptBinding(
        AuthorityBinding(
            configuration.control_instance,
            configuration.business_instance,
            configuration.restore_epoch,
        ),
        tenant,
        device,
        game,
        wire_d4,
        internal_generation,
        attempt,
        1,
        request_fingerprint,
        1,
    )


def p3_response_body(
    result: AcceptedChangeResult | RejectedChangeResult,
) -> dict[str, object]:
    """保存済みI6と拒否を別形にし、例外や資格を応答へ写さない。"""
    if type(result) is AcceptedChangeResult:
        return {
            "boundary": result.boundary,
            "target_reference": _json_value(result.target_reference),
            "expected_version": result.expected_version,
            "d5": result.d5,
            "confirmed_content": _json_value(result.confirmed_content),
            "accepted_at": result.accepted_at,
        }
    if type(result) is RejectedChangeResult:
        return {"boundary": result.boundary, "d5": result.d5, "reason": result.reason}
    raise TypeError("P3結果型が不一致")
