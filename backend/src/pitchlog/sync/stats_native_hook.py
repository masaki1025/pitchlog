"""生存native frameと同TX原本を照合した一回だけの成績source参照。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from weakref import WeakKeyDictionary

from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
from pitchlog.repositories import transaction
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.control_provider.evidence import EventPhaseBinding
from pitchlog.sync.first_ball_execution import _same_wire_value
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.tokens import IdempotencyLedgerReadToken, OperationEventReadToken


class StatsNativeSourceError(RuntimeError):
    """原本・nonce・資格値を含めない成績source拒否。"""

    def __init__(self):
        """結果不明や失効を成功/欠測へ変換しない。"""
        super().__init__("成績native sourceの同一frameを確認できません")


class NativeStatsSourceReceipt:
    """私有registryのobjectidentityだけで利用できる短命参照。"""

    __slots__ = ("__weakref__",)

    def __new__(cls):
        """UUID/JSONや自由生成から資格を発行しない。"""
        raise StatsNativeSourceError


@dataclass(frozen=True, slots=True, repr=False)
class _NativeStatsSource:
    """照合済み値。値だけを再投入して保存資格へ昇格してはいけない。"""

    tenant_id: UUID
    game_id: UUID
    generation: int
    d1: int
    d2: int
    d5: UUID
    source_event_id: UUID
    event_fingerprint: str
    native_payload_json: str
    native_rule_sha256: str
    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes


@dataclass(slots=True, repr=False)
class _IssuedSource:
    handle: Any
    writer: Any
    event: SyncEvent
    projected: SyncEvent
    generation: int
    state_key: object
    execution: Any
    anchor: tuple[object, ...]
    source: object
    bound: object
    lease: object
    lifetime: tuple[object, object]
    phase: object
    nonce: bytes
    event_row: tuple[object, ...]
    ledger_row: tuple[object, ...]
    values: _NativeStatsSource
    used: bool = False


_RECEIPTS: WeakKeyDictionary[NativeStatsSourceReceipt, _IssuedSource] = (
    WeakKeyDictionary()
)


def _json(value: object) -> str:
    """既wire正規化から全値比較用の不変JSONへ写す。数学は計算しない。"""
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _execution(handle, writer, event, projected):
    """実登録Executionからだけgetterを選び、任意のmode指定を受けない。"""
    from pitchlog.sync import first_ball_execution as first
    from pitchlog.sync import ordinary_pitch_execution as ordinary

    if type(handle) is not transaction._TenantTransaction:
        raise StatsNativeSourceError
    key = handle._state_key
    if key is None or (key in first._EXECUTIONS) == (key in ordinary._EXECUTIONS):
        raise StatsNativeSourceError
    if key in first._EXECUTIONS:
        return first._read_first_ball_stats_source(handle, writer, event, projected)
    return ordinary._read_ordinary_stats_source(handle, writer, event, projected)


def _one_row(handle, token, model) -> tuple[object, ...]:
    """同handleの正式read token以外で原本を取得しない。"""
    result = handle.run(token)
    if (
        type(result) is not TenantOperationResult
        or type(result.rows) is not tuple
        or len(result.rows) != 1
        or type(result.rows[0]) is not tuple
        or len(result.rows[0]) != len(model.__table__.c)
    ):
        raise StatsNativeSourceError
    return result.rows[0]


def _read_values(handle, writer, event, projected, generation):
    """実frame/元V7V8/実ledger/保存規則を同TXで全照合する。"""
    state = _execution(handle, writer, event, projected)
    anchor = state.stats_source_reference
    if type(anchor) is not tuple or len(anchor) not in (8, 9):
        raise StatsNativeSourceError
    source = state.source
    bound = source.bound
    lease = bound._lease
    phase = source.phase
    view = source.read(handle, event)
    if (
        type(event) is not SyncEvent
        or type(projected) is not SyncEvent
        or type(generation) is not int
        or generation < 1
        or type(event.d1) is not int
        or event.d1 < 1
        or type(phase) is not EventPhaseBinding
        or type(lease.nonce) is not bytes
        or len(lease.nonce) != 32
        or lease.attempt_id != phase.attempt.attempt_id
        or lease.phase_id != phase.phase_id
        or lease.game_id != UUID(event.game_id)
        or phase.d1 != event.d1
        or phase.d5 != UUID(event.d5)
        or phase.attempt.tenant_id != handle._context.tenant_id
        or phase.attempt.game_id != UUID(event.game_id)
        or phase.attempt.internal_generation != generation
        or lease.device_id != phase.attempt.device_id
        or phase.event_fingerprint != view.event_fingerprint
        or json.loads(bound._phase_snapshot)["phase"]["internal_generation"]
        != generation
    ):
        raise StatsNativeSourceError
    payload = state.payload.v7 if hasattr(state.payload, "v7") else state.payload
    native = payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
    # firstだけ完全形、ordinary/v2/v3のdifferenceは既codecどおり省略を維持する。
    if native["formatVersion"] == "first-ball-play-v1":
        native = payload.model_dump(mode="json", by_alias=True)
    if _json(native) != _json(event.v7):
        raise StatsNativeSourceError
    if hasattr(state.payload, "v8") and _json(
        state.payload.v8.model_dump(mode="json", by_alias=True)
    ) != _json(event.v8):
        raise StatsNativeSourceError
    request = payload.calculation.request
    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        NonplayLineupPrefixRequest,
    )

    nonplay = type(request) is NonplayLineupPrefixRequest
    position = (
        request.source_position
        if nonplay
        else getattr(request.source, "position", None)
        if hasattr(request, "source")
        else None
    )
    rule = request.rules.model_dump(mode="json", by_alias=True)
    rule_hash = source_fingerprint(rule)
    if hasattr(state, "prefix"):
        if request.rules != state.prefix.checkpoint.rules:
            raise StatsNativeSourceError
        if native["formatVersion"] in ("play-prefix-play-v2", "play-prefix-play-v3"):
            rules_digest = (
                request.source.checkpoint.content.restored.rules_digest
                if nonplay
                else request.source.rules_digest
            )
            if rules_digest != rule_hash:
                raise StatsNativeSourceError
    event_row = _one_row(
        handle,
        OperationEventReadToken(UUID(event.game_id), generation, event.d1),
        OperationEvent,
    )
    saved = dict(zip(OperationEvent.__table__.c.keys(), event_row, strict=True))
    expected = {
        "tenant_id": handle._context.tenant_id,
        "game_id": UUID(event.game_id),
        "generation": generation,
        "d1": event.d1,
        "d2": projected.v6,
        "d5": UUID(event.d5),
        "ledger_kind": "accepted",
        "event_kind": "play_input",
        "is_tombstone": False,
        "replaced_at": None,
        "retired_at": None,
        "import_batch_id": None,
        "migration_unverified": False,
        "target_generation": None,
        "target_d1": None,
        "expected_version": None,
        "change_order": None,
        "legacy_row_identifier": None,
    }
    if (
        type(saved["id"]) is not UUID
        or any(not _same_wire_value(saved[k], value) for k, value in expected.items())
        or _json(saved["payload"]) != _json(event.v7)
        or _json(saved["state_diff"]) != _json(event.v8)
    ):
        raise StatsNativeSourceError
    if native["formatVersion"] in ("play-prefix-play-v2", "play-prefix-play-v3"):
        if position is None:
            raise StatsNativeSourceError
        if (
            request.play_identity.event_id != str(saved["id"])
            or request.play_identity.d5 != event.d5
            or position.d1 != str(event.d1)
            or position.d2 != str(projected.v6)
        ):
            raise StatsNativeSourceError
    ledger_row = _one_row(
        handle, IdempotencyLedgerReadToken(UUID(event.d5)), IdempotencyLedger
    )
    ledger = dict(zip(IdempotencyLedger.__table__.c.keys(), ledger_row, strict=True))
    if any(
        not _same_wire_value(ledger[k], value)
        for k, value in {
            "tenant_id": handle._context.tenant_id,
            "d5": UUID(event.d5),
            "kind": "accepted",
            "source_fingerprint": view.event_fingerprint,
            "reason": None,
            "retired_at": None,
            "import_batch_id": None,
        }.items()
    ) or not isinstance(ledger["result"], Mapping):
        raise StatsNativeSourceError
    result = ledger["result"]
    if (
        set(result) != {"state", "d3", "temporary_id_mapping"}
        or result["state"] != "受理"
        or type(result["d3"]) is not int
        or result["d3"] != event.d1
        or not isinstance(result["temporary_id_mapping"], Mapping)
        or result["temporary_id_mapping"]
    ):
        raise StatsNativeSourceError
    # readのawait/実行境界でruntime/sourceが失効していないか再確認する。
    if _execution(handle, writer, event, projected) is not state:
        raise StatsNativeSourceError
    values = _NativeStatsSource(
        handle._context.tenant_id,
        UUID(event.game_id),
        generation,
        event.d1,
        projected.v6,
        UUID(event.d5),
        saved["id"],
        view.event_fingerprint,
        _json(native),
        rule_hash,
        lease.attempt_id,
        lease.phase_id,
        lease.nonce,
    )
    return state, anchor, event_row, ledger_row, values


def _issue_native_stats_source(handle, writer, event, projected, *, generation):
    """after_d1_intents後の生存実行に一回だけsource参照を発行する。"""
    from pitchlog.sync import first_ball_execution as first
    from pitchlog.sync import ordinary_pitch_execution as ordinary

    try:
        if type(handle) is not transaction._TenantTransaction:
            raise StatsNativeSourceError
        key = handle._state_key
        states = [
            s
            for s in (first._EXECUTIONS.get(key), ordinary._EXECUTIONS.get(key))
            if s is not None
        ]
        if len(states) != 1:
            raise StatsNativeSourceError
        state = states[0]
        anchor = state.stats_source_reference
        if type(anchor) is not tuple or len(anchor) != 8:
            raise StatsNativeSourceError
        # read/結果照会が失敗しても同frameへ別資格を発行し直さない。
        marker = object()
        pending = (*anchor, marker)
        state.stats_source_reference = pending
        from pitchlog.sync.stage_timing import stage

        with stage("stats_source_read_values"):
            checked, seen, event_row, ledger_row, values = _read_values(
                handle,
                writer,
                event,
                projected,
                generation,
            )
        if checked is not state or seen is not pending:
            raise StatsNativeSourceError
        receipt = object.__new__(NativeStatsSourceReceipt)
        state.stats_source_reference = (*anchor, receipt)
        # valueからkey自身を保持しない。Execution終了後にweak registryを解放できる。
        _RECEIPTS[receipt] = _IssuedSource(
            handle,
            writer,
            event,
            projected,
            generation,
            handle._state_key,
            state,
            anchor,
            state.source,
            state.source.bound,
            state.source.bound._lease,
            handle._writer_lifetime(),
            state.source.phase,
            values.binding_nonce,
            event_row,
            ledger_row,
            values,
        )
        return receipt
    except (KeyError, TypeError, ValueError, AttributeError):
        raise StatsNativeSourceError from None


def _consume_native_stats_source(handle, receipt) -> _NativeStatsSource:
    """同handle/同frame/未改変原本の参照を一回消費し、T5はまだ評価しない。"""
    if type(receipt) is not NativeStatsSourceReceipt:
        raise StatsNativeSourceError
    issued = _RECEIPTS.get(receipt)
    if issued is None or issued.used:
        raise StatsNativeSourceError
    # 失敗も再利用せず、結果不明の別資格への置換を許さない。
    issued.used = True
    try:
        if (
            handle is not issued.handle
            or handle._state_key is not issued.state_key
            or type(issued.execution.stats_source_reference) is not tuple
            or len(issued.execution.stats_source_reference) != 9
            or issued.execution.stats_source_reference[-1] is not receipt
            or any(
                a is not b
                for a, b in zip(
                    issued.execution.stats_source_reference[:8],
                    issued.anchor,
                    strict=True,
                )
            )
            or issued.execution.source is not issued.source
            or issued.execution.source.bound is not issued.bound
            or issued.bound._lease is not issued.lease
            or issued.source.phase is not issued.phase
            or issued.lease.nonce != issued.nonce
        ):
            raise StatsNativeSourceError
        handle._assert_writer_lifetime(issued.lifetime)
        state, anchor, event_row, ledger_row, values = _read_values(
            handle,
            issued.writer,
            issued.event,
            issued.projected,
            issued.generation,
        )
        if (
            state is not issued.execution
            or len(anchor) != 9
            or anchor[-1] is not receipt
            or any(a is not b for a, b in zip(anchor[:8], issued.anchor, strict=True))
            or not _same_wire_value(event_row, issued.event_row)
            or not _same_wire_value(ledger_row, issued.ledger_row)
            or values != issued.values
        ):
            raise StatsNativeSourceError
        return values
    except (KeyError, TypeError, ValueError, AttributeError):
        raise StatsNativeSourceError from None
