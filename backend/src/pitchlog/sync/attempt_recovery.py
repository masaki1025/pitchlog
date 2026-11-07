"""応答不明E-1の旧試行を実端末・同fenceで照会する。"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from typing import Literal
from uuid import UUID

from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.rg1 import RG1Unavailable, read_rg1_open
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.sync.apply import _verify_replay_device
from pitchlog.sync.control_provider.binding_control import BindingControl
from pitchlog.sync.gate import game_accessible
from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import SyncRequest
from pitchlog.sync.source_binding import _e1_receipt_scope, receipt_body_fingerprint
from pitchlog.sync.stop_contract import AttemptIdentity
from pitchlog.sync.wire_source import WireSourceValue

type RecoveryResult = Literal["B5", "B6", "B7", "retry_allowed", "unresolved"]


def recover_sync_attempt(
    context: TenantContext,
    request: SyncRequest,
    source: WireSourceValue,
    *,
    attempt_id: UUID,
    device_id: UUID,
    credential_digest: bytes,
    cookie: str,
    control: BindingControl,
) -> RecoveryResult:
    """元本文の試行を実認証/端末照合後に耐久遮断する。

    Args:
        context: 実HTTPから発行されたテナント文脈。
        request: 元E-1本文のS-1解析値。
        source: 同じ元wireの凍結値。
        attempt_id: 送信前バリアの旧attempt ID。
        device_id: 提示された端末ID。
        credential_digest: 実端末資格のdigest。
        cookie: 実認証済みの提示Cookie。
        control: 既専用peerへの実制御入口。

    Returns:
        既認可境界またはACKではない閉じた照会結果。
    """
    if (
        type(context) is not TenantContext
        or not context._has_valid_integrity_proof()
        or type(request) is not SyncRequest
        or type(source) is not WireSourceValue
        or type(attempt_id) is not UUID
        or type(device_id) is not UUID
        or type(credential_digest) is not bytes
        or len(credential_digest) != 32
        or type(cookie) is not str
        or not cookie
        or type(control) is not BindingControl
        or request.path not in ("P1", "P2", "P3")
        or len(request.events) != 1
        or source.game_id != request.game_id
        or len(source.events) != 1
        or len(source.event_fingerprints) != 1
        or source.codec_version != 1
    ):
        raise ValueError("旧試行照会の元要求が不正")
    event = request.events[0]
    p3 = request.path == "P3"
    target = event.v10 if p3 else None
    target_d4 = target.get("d4") if isinstance(target, Mapping) else None
    if (
        source.d1less is not p3
        or (source.d4 != target_d4 if p3 else source.d4 != request.d4)
        or (event.d4 is not None if p3 else event.d4 != request.d4)
        or event.game_id != request.game_id
        or source.events[0].wire_event.get("d5") != event.d5
        or source.events[0].wire_event.get("d1") != event.d1
    ):
        raise ValueError("旧試行照会の原wireが不一致")
    identity = AttemptIdentity(
        str(attempt_id),
        request.game_id,
        source.d4,
        source.codec_version,
        source.request_fingerprint,
    )
    entry_token = object()
    with _e1_receipt_scope(
        context=context, request=request, source=source, entry_token=entry_token
    ) as receipt:
        body_fingerprint = receipt_body_fingerprint(receipt, entry_token)
    game_id = UUID(request.game_id)
    # 実端末状態と自テナント試合の照合を、broker照会終了まで同一scopeに保持する。
    with tenant_transaction_scope(context) as scope:
        if not _verify_replay_device(scope, device_id, credential_digest):
            return "B5"
        if not game_accessible(context, game_id, lambda _: nullcontext(scope)):
            return "B6"
        try:
            read_rg1_open(scope)
        except RG1Unavailable:
            return "B7"
        return control.recover_attempt(
            context,
            identity,
            device_id,
            UUID(event.d5),
            source.event_fingerprints[0],
            cookie=cookie,
            body_fingerprint=body_fingerprint,
            **(
                {
                    "phase_kind": "d1less",
                    "d5_fingerprint": operation_fingerprint(event, "P3", None),
                }
                if p3
                else {}
            ),
        )
