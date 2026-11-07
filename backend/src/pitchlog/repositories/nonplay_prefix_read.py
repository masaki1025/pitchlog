"""非play現在原本の有限readと通常writerの再読取。公開値は保存資格でない。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    NonplayCheckpoint,
    NonplaySource,
)
from pitchlog.repositories import transaction
from pitchlog.repositories.nonplay_prefix import NonplaySourceUnavailable, _check_source
from pitchlog.repositories.nonplay_prefix_read_operations import (
    NonplayActiveHistoryReadToken,
)
from pitchlog.repositories.ordinary_prefix_operations import OrdinaryCheckpointLockToken
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.idempotency import source_fingerprint


def _same(a, b):
    """JSONの型を含めて全値を比較する。"""
    return _canonical_json(a) == _canonical_json(b)


def checked_checkpoint(raw, *, tenant, game, generation, d3, artifact=None):
    """保存digest/3headを既閉Source規則へ照合する。資格の代替にはしない。"""
    try:
        cp = NonplayCheckpoint.model_validate_json(
            _canonical_json(raw), by_alias=True, by_name=False
        )
    except (ValueError, TypeError):
        raise NonplaySourceUnavailable("非play CP閉型が不一致") from None
    if not _same(cp.model_dump(mode="json", by_alias=True, exclude_unset=True), raw):
        raise NonplaySourceUnavailable("非play CP型が不一致")
    c = cp.content
    if (
        c.scope.tenant_id != str(tenant)
        or c.scope.game_id != str(game)
        or c.scope.generation != generation
        or c.d3 != str(d3)
        or cp.ref.digest != source_fingerprint(raw["content"])
        or c.d1_head is None
        or c.d1_head.source.game_id != str(game)
        or c.d1_head.source.generation != generation
        or c.d1_head.source.d1 != str(d3)
        or artifact is not None
        and c.execution_artifact_sha256 != artifact
    ):
        raise NonplaySourceUnavailable("非play CP保存原本が不一致")
    return cp


def _owner(handle):
    """真正同Session/top-level TXのidentityだけを保持する。"""
    if type(handle) is not transaction._TenantTransaction:
        raise NonplaySourceUnavailable("非play読取handleが不正")
    from pitchlog.repositories.context import TenantContext

    if (
        type(handle._context) is not TenantContext
        or handle._context.tenant_id != handle._bound_tenant_id
        or handle._context._integrity_proof != handle._bound_integrity_proof
        or not handle._context._has_valid_integrity_proof()
    ):
        raise NonplaySourceUnavailable("非play読取tenant発行証跡が不正")
    key = handle._state_key
    runtime = transaction._TRANSACTION_RUNTIMES.get(key)
    if runtime is None:
        raise NonplaySourceUnavailable("非play読取scopeが失効")
    session = runtime[0]
    tx = session.get_transaction()
    if tx is None or not tx.is_active or session.in_nested_transaction():
        raise NonplaySourceUnavailable("非play読取TXが不正")
    return key, runtime, session, tx


def _live(handle, owner):
    """clone/別handle/別TX/失効を各実境界の前後で拒否する。"""
    now = _owner(handle)
    if any(a is not b for a, b in zip(now, owner, strict=True)):
        raise NonplaySourceUnavailable("非play読取scopeの移植")


def _point(raw) -> tuple[int, int, UUID]:
    """cursorは実順序値3列、bool/非正準表現を拒否する。"""
    if (
        type(raw) is not list
        or len(raw) != 3
        or any(type(x) is not int or x <= 0 for x in raw[:2])
        or type(raw[2]) is not str
        or str(UUID(raw[2])) != raw[2]
    ):
        raise NonplaySourceUnavailable("非play cursorが不正")
    return raw[0], raw[1], UUID(raw[2])


def _frame(handle, item, live):
    """実SQLの秘密非供給profileだけを消費し、原wireを推測しない。"""
    if type(item) is not dict or set(item) != {
        "kind",
        "cursor",
        "frame",
        "event",
        "fingerprint",
        "wireD4",
        "physical",
    }:
        raise NonplaySourceUnavailable("非play公開保存証拠の形が不一致")
    from pitchlog.db.game_state.models import PlayRow
    from pitchlog.db.sync_protocol.models import OperationEvent
    from pitchlog.repositories.recorded_snapshot import (
        _evaluate_historical_first_ball_frame,
        _typed_historical_row,
    )
    from pitchlog.sync.undo_payload import _validate_value

    ev = _typed_historical_row(item["event"], OperationEvent.__table__)
    physical = item["physical"]
    if type(physical) is not dict or set(physical) != {"play_row", "play_runners"}:
        raise NonplaySourceUnavailable("非play全physicalが欠落")
    play = _typed_historical_row(physical["play_row"], PlayRow.__table__)
    if (
        ev["tenant_id"] != handle._bound_tenant_id
        or ev["event_kind"] != "play_input"
        or ev["ledger_kind"] != "accepted"
        or ev["is_tombstone"] is not False
        or ev["id"] != play["source_event_id"]
        or ev["game_id"] != play["game_id"]
        or play["tenant_id"] != ev["tenant_id"]
        or play["hidden_at"] is not None
    ):
        raise NonplaySourceUnavailable("非play対象原本が不一致")
    if item["kind"] == "legacy-first-ball-v1":

        def run(token):
            live()
            result = handle.run(token)
            live()
            return result

        value = _evaluate_historical_first_ball_frame(
            handle,
            ev=ev,
            admission={"wire_d4": item["wireD4"]},
            play=play,
            play_raw=physical["play_row"],
            runners_raw=physical["play_runners"],
            ledger={"source_fingerprint": item["fingerprint"]},
            source_event_id=ev["id"],
            generation=ev["generation"],
            d1=ev["d1"],
            tenant=ev["tenant_id"],
            game_id=ev["game_id"],
            live=live,
            run=run,
        )
        frame = json.loads(value.frame_json)
    elif item["kind"] == "accepted-ordinary-admission-v1":
        from pitchlog.repositories.nonplay_prefix import _stored_contexts

        frame = item["frame"]
        before, after = _stored_contexts(item["event"]["payload"])
        if not _same(frame["beforeContext"], before) or not _same(
            frame["afterContext"], after
        ):
            raise NonplaySourceUnavailable("非play保存payloadの全文脈が不一致")
    else:
        raise NonplaySourceUnavailable("未知の非play読取profile")
    _validate_value(frame, "ActiveFrame")
    src = frame["play"]["source"]
    if (
        src["eventId"] != str(ev["id"])
        or src["gameId"] != str(ev["game_id"])
        or src["generation"] != item["wireD4"]
        or src["d1"] != str(ev["d1"])
        or src["d5"] != str(ev["d5"])
        or src["fingerprint"] != item["fingerprint"]
        or frame["play"]["d2"] != str(ev["d2"])
        or frame["play"]["playId"] != str(play["id"])
        or frame["play"]["physicalPlayNumber"] != str(play["play_number"])
        or not _same(frame["historyEntry"]["difference"], item["event"]["state_diff"])
    ):
        raise NonplaySourceUnavailable("非play frame全識別が不一致")
    live()
    return frame


def _page_anchor(cp):
    """全pageを同CP/refと3水位へ束縛する。秘密の資格は含めない。"""
    rawcp = cp.model_dump(mode="json", by_alias=True, exclude_unset=True)
    anchor = {
        "checkpoint": rawcp["ref"],
        "scope": rawcp["content"]["scope"],
        "d3": cp.content.d3,
        "epoch": cp.content.storage_history_epoch,
        "historyVersion": cp.content.history_version,
    }
    return anchor


def _read_page_cursor(cursor, anchor):
    """旧NPとbootstrapで同じ閉cursorを使い、別anchorへ移植しない。"""
    point = (0, 0, UUID(int=0))
    if cursor is not None:
        if type(cursor) is not str or len(cursor) > 2048:
            raise NonplaySourceUnavailable("非play cursor型が不正")
        try:
            decoded = base64.urlsafe_b64decode(
                cursor + "=" * ((-len(cursor)) % 4)
            ).decode()
            if (
                base64.urlsafe_b64encode(decoded.encode()).decode().rstrip("=")
                != cursor
            ):
                raise ValueError
            from pitchlog.sync.undo_payload import _load

            packet = _load(decoded)
            if (
                type(packet) is not dict
                or set(packet) != {"anchor", "position"}
                or not _same(packet["anchor"], anchor)
            ):
                raise ValueError
            point = _point(packet["position"])
        except (ValueError, TypeError, KeyError):
            raise NonplaySourceUnavailable("非play cursor anchorが不一致") from None
    return point


def _make_page_cursor(anchor, point):
    """実在するpage境界だけを公開opaque cursorへ写す。"""
    encoded = _canonical_json(
        {"anchor": anchor, "position": [point[0], point[1], str(point[2])]}
    )
    return base64.urlsafe_b64encode(encoded.encode()).decode().rstrip("=")


def _read_active_page_bound(
    handle, cp, *, generation, limit=25, cursor=None, viewer=False
):
    """同CPの一page。全stack完成とは区別する。秘密を返さない。"""
    owner = _owner(handle)

    def live():
        _live(handle, owner)

    rawcp = cp.model_dump(mode="json", by_alias=True, exclude_unset=True)
    anchor = _page_anchor(cp)
    point = _read_page_cursor(cursor, anchor)
    if viewer:
        from pitchlog.repositories.transaction import require_viewer_read_scope
        from pitchlog.repositories.viewer_read import (
            ViewerNonplayActiveHistoryReadToken,
        )

        require_viewer_read_scope(handle)
        page_token = ViewerNonplayActiveHistoryReadToken
    else:
        page_token = NonplayActiveHistoryReadToken
    token = page_token(
        game_id=UUID(cp.content.scope.game_id),
        generation=generation,
        checkpoint_id=UUID(cp.ref.id),
        revision=int(cp.ref.revision),
        epoch=int(cp.content.storage_history_epoch),
        d3=int(cp.content.d3),
        logical_version=int(cp.content.history_version),
        after_order=point[0],
        after_d1=point[1],
        after_id=point[2],
        page_size=limit,
    )
    live()
    result = handle.run_function(token)
    live()
    if (
        type(result) is not TenantOperationResult
        or len(result.rows) != 1
        or len(result.rows[0]) != 1
        or type(result.rows[0][0]) is not str
    ):
        raise NonplaySourceUnavailable("非play page実応答が不正")
    from pitchlog.sync.undo_payload import _load

    packet = _load(result.rows[0][0])
    if (
        type(packet) is not dict
        or set(packet) != {"checkpoint", "total", "items"}
        or not _same(packet["checkpoint"], rawcp)
        or type(packet["total"]) is not int
        or packet["total"] != int(cp.content.active_depth)
        or type(packet["items"]) is not list
        or len(packet["items"]) > limit + 1
    ):
        raise NonplaySourceUnavailable("非play page版/件数が不一致")
    values = []
    seen = set()
    last = None
    for item in packet["items"]:
        p = _point(item["cursor"])
        if p in seen or (point[0] and p >= point) or last is not None and p >= last:
            raise NonplaySourceUnavailable("非play page順序が不一致")
        seen.add(p)
        last = p
        frame = _frame(handle, item, live)
        values.append((p, frame))
    more = len(values) > limit
    selected = values[:limit]
    next_cursor = None
    if more:
        next_cursor = _make_page_cursor(anchor, selected[-1][0])
    return {"items": [frame for _, frame in selected], "next_cursor": next_cursor}


def read_active_page(handle, cp, *, generation, limit=25, cursor=None, viewer=False):
    """配置/原本破損は内容拒否へ落とさず、秘密なしの不可用として閉じる。"""
    from jsonschema import ValidationError

    from pitchlog.domainrt.host import DomainRuntimeError
    from pitchlog.repositories.function_operations import FunctionOperationError
    from pitchlog.repositories.recorded_snapshot import (
        RecordedSnapshotCorrupt,
        RecordedSnapshotUnavailable,
    )
    from pitchlog.sync.undo_payload import UndoContractUnavailable

    try:
        return _read_active_page_bound(
            handle,
            cp,
            generation=generation,
            limit=limit,
            cursor=cursor,
            viewer=viewer,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        ValidationError,
        FunctionOperationError,
        RecordedSnapshotCorrupt,
        RecordedSnapshotUnavailable,
        DomainRuntimeError,
        UndoContractUnavailable,
    ):
        raise NonplaySourceUnavailable("非play実原本又は読取能力が不可用") from None


@dataclass(frozen=True, slots=True)
class NonplayCheckpointView:
    """実CPを旧v3へ変換しないread-only型付きview。"""

    document: NonplayCheckpoint
    internal_generation: int
    recovery_generation: int

    @property
    def rules(self):
        """native7A共通照合へ真正restored.rulesそのものを渡す。"""
        return self.document.content.restored.rules


@dataclass(frozen=True, slots=True, init=False)
class ConfirmedNonplayNormalPrefix:
    """実writer再読取に由来する原本。自由constructorでは資格を発行しない。"""

    checkpoint: NonplayCheckpointView
    source: NonplaySource
    next_play_number: int
    roster: object
    previous_payload: None = None

    def __new__(cls, *args, **kwargs):
        """caller構築を実原本資格へ昇格させない。"""
        raise NonplaySourceUnavailable("通常非play原本参照は自由生成できません")


def read_confirmed_nonplay_normal(handle, event, source, *, proposal, artifact_sha256):
    """既ordinary writer lock/nonce/同TXを先行し、全active原本を再読取する。"""
    from pitchlog.repositories.ordinary_prefix import _locked_prefix_context
    from pitchlog.repositories.ordinary_prefix_read import _function_one
    from pitchlog.sync.ordinary_pitch_execution import _EXECUTIONS, _Execution
    from pitchlog.sync.ordinary_pitch_execution import _live as execution_live

    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.phase != "preparing"
        or handle._state_key in _PREFIX_READS
        or state.handle is not handle
        or state.source is not source
        or state.event is not event
    ):
        raise NonplaySourceUnavailable("非play通常投球の実executionがない")
    execution_live(state)
    run, live, tenant, game, generation, epoch, watermark, lease = (
        _locked_prefix_context(handle, event, source)
    )
    if watermark != event.d1 - 1:
        raise NonplaySourceUnavailable("非play通常投球の真正D3が不一致")
    row = _function_one(
        handle,
        OrdinaryCheckpointLockToken(
            lease.attempt_id,
            lease.phase_id,
            lease.nonce,
            lease.device_id,
            UUID(event.game_id),
            generation,
        ),
    )
    execution_live(state)
    if type(row) is not dict or type(row.get("content")) is not dict:
        raise NonplaySourceUnavailable("非play通常投球のCP lockが不一致")
    stored = row
    cp = checked_checkpoint(
        stored["content"],
        tenant=handle._bound_tenant_id,
        game=event.game_id,
        generation=event.d4,
        d3=event.d1 - 1,
        artifact=artifact_sha256,
    )
    check_storage_row(
        stored,
        cp,
        tenant=tenant,
        game=game,
        generation=generation,
        epoch=epoch,
        d3=watermark,
    )
    frames = []
    cursor = None
    while True:
        page = read_active_page(
            handle, cp, generation=generation, limit=100, cursor=cursor
        )
        execution_live(state)
        frames.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    raw = {
        "formatVersion": "nonplay-prefix-source-v1",
        "checkpoint": cp.model_dump(mode="json", by_alias=True, exclude_unset=True),
        "activeStack": frames,
    }
    _check_source(raw)
    if (
        not _same(
            raw,
            proposal.source.model_dump(mode="json", by_alias=True, exclude_unset=True),
        )
        or proposal.prefix_ref != cp.ref
        or proposal.source_position.d1 != str(event.d1)
        or proposal.source_position.applied_watermark != cp.content.d3
        or proposal.play_identity.d5 != event.d5
        or proposal.rules != cp.content.restored.rules
        or proposal.t1.before != cp.content.restored.current
    ):
        raise NonplaySourceUnavailable("非play実原本と提案sourceが不一致")
    _read_nonplay_append_d2(handle, event, proposal, epoch=epoch)
    execution_live(state)
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection

    result = object.__new__(ConfirmedNonplayNormalPrefix)
    values = {
        "checkpoint": NonplayCheckpointView(
            cp, generation, int(stored["recovery_generation"])
        ),
        "source": NonplaySource.model_validate_json(_canonical_json(raw)),
        "next_play_number": int(cp.content.next_physical_play_number),
        "roster": InitialRosterProjection.model_validate_json(
            _canonical_json(stored["roster"])
        ),
        "previous_payload": None,
    }
    values["checkpoint"] = NonplayCheckpointView(
        values["source"].checkpoint, generation, int(stored["recovery_generation"])
    )
    for k, v in values.items():
        object.__setattr__(result, k, v)
    _PREFIX_READS[handle._state_key] = (
        result,
        state,
        _canonical_json(raw),
        _canonical_json(stored["roster"]),
        _owner(handle),
        _canonical_json(
            {
                "generation": generation,
                "epoch": int(stored["recovery_generation"]),
                "next": values["next_play_number"],
            }
        ),
        values["source"],
        values["checkpoint"],
        values["roster"],
    )
    return result


_PREFIX_READS = {}


def _assert_nonplay_normal_prefix(state):
    """同reader/handle/source/frame内に発行した実参照だけを使う。"""
    entry = _PREFIX_READS.get(state.handle._state_key)
    if entry is None or entry[0] is not state.prefix or entry[1] is not state:
        raise NonplaySourceUnavailable("非play通常原本参照の移植")
    prefix = state.prefix
    _live(state.handle, entry[4])
    if (
        type(prefix) is not ConfirmedNonplayNormalPrefix
        or prefix.source is not entry[6]
        or prefix.checkpoint is not entry[7]
        or prefix.roster is not entry[8]
        or _canonical_json(
            {
                "generation": prefix.checkpoint.internal_generation,
                "epoch": prefix.checkpoint.recovery_generation,
                "next": prefix.next_play_number,
            }
        )
        != entry[5]
        or _canonical_json(
            prefix.source.model_dump(mode="json", by_alias=True, exclude_unset=True)
        )
        != entry[2]
        or prefix.checkpoint.document is not prefix.source.checkpoint
        or prefix.next_play_number
        != int(prefix.source.checkpoint.content.next_physical_play_number)
        or type(prefix.next_play_number) is not int
        or _canonical_json(prefix.roster.model_dump(mode="json", by_alias=True))
        != entry[3]
    ):
        raise NonplaySourceUnavailable("非play通常原本参照の全値が不一致")


def _release_nonplay_normal_prefix(handle):
    """真正executionのfinallyで期限切れ参照を残さない。"""
    _PREFIX_READS.pop(handle._state_key, None)


def check_storage_row(row, cp, *, tenant, game, generation, epoch, d3):
    """実CP table全列/型とwireCPの全参照を照合する。形を資格へ変えない。"""
    from pitchlog.db.writer_binding.ordinary_models import OrdinaryPitchCheckpoint
    from pitchlog.repositories.recorded_snapshot import _typed_historical_row

    columns = set(OrdinaryPitchCheckpoint.__table__.c.keys())
    if (
        type(row) is not dict
        or set(row) != columns | {"last_play_row"}
        or row["last_play_row"] is not None
    ):
        raise NonplaySourceUnavailable("非play CP全物理列が不一致")
    _typed_historical_row(
        {k: row[k] for k in columns}, OrdinaryPitchCheckpoint.__table__
    )
    expected = {
        "tenant_id": str(tenant),
        "game_id": str(game),
        "internal_generation": generation,
        "id": cp.ref.id,
        "revision": int(cp.ref.revision),
        "history_version": int(cp.content.storage_history_epoch),
        "recovery_generation": epoch,
        "confirmed_watermark": d3,
        "applied_watermark": d3,
        "state": "current",
        "content_digest": cp.ref.digest,
    }
    if (
        any(type(row.get(k)) is not type(v) or row[k] != v for k, v in expected.items())
        or row["saved_at"] is None
    ):
        raise NonplaySourceUnavailable("非play CP物理anchorが不一致")


def _read_nonplay_append_d2(handle, event, proposal, *, epoch):
    """実末尾を確認して既allocatorのappend枝へ渡す。過去位置再採番は行わない。"""
    owner = _owner(handle)
    # E1の真正D2 allocatorを再使用。active空でも過去物理番号を失わない。
    from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken
    from pitchlog.repositories.ordinary_prefix_read import _function_one

    summary = _function_one(handle, OrdinaryOrderSummaryToken(UUID(event.game_id)))
    if (
        type(summary) is not dict
        or set(summary) != {"tail", "duplicate", "recovery_generation"}
        or summary["duplicate"] is not False
        or type(summary["recovery_generation"]) is not int
        or summary["recovery_generation"] != epoch
    ):
        raise NonplaySourceUnavailable("非play実D2 allocatorの原本が不一致")
    tail = summary["tail"]
    if (
        type(tail) is not dict
        or tail.get("tenant_id") != str(handle._bound_tenant_id)
        or tail.get("game_id") != event.game_id
        or type(tail.get("d2")) is not int
        or type(event.v6) is not int
        or event.v6 <= tail["d2"]
        or proposal.source_position.d2 != str(event.v6)
    ):
        raise NonplaySourceUnavailable("非play実D2 allocatorと提案が不一致")
    # 過去位置の再採番へは入らず、既唯一allocatorの実append結果だけを使う。
    from pitchlog.sync.ordering import _assign_ordinary_append_d2

    try:
        assigned = _assign_ordinary_append_d2(handle, UUID(event.game_id), event.v6)
    except RuntimeError:
        raise NonplaySourceUnavailable("非play既allocatorの実原本が不一致") from None
    if type(assigned) is not int or proposal.source_position.d2 != str(assigned):
        raise NonplaySourceUnavailable("非play実D2 allocatorの結果が不一致")
    _live(handle, owner)
    return assigned


def _read_legacy_undo_source(handle, doc, stored, artifact_sha256):
    """各100+1原本を同TXで全検証し、writerと唯一のmapperから同refを得る。"""
    from pitchlog.db.writer_binding.ordinary_models import OrdinaryPitchCheckpoint
    from pitchlog.repositories.nonplay_prefix import (
        _checkpoint_from_legacy,
        _require_nonplay_legacy_compatibility,
    )
    from pitchlog.repositories.recorded_snapshot import _typed_historical_row
    from pitchlog.sync.undo_payload import _load

    _require_nonplay_legacy_compatibility(doc.artifact_sha256, artifact_sha256)
    owner = _owner(handle)

    def live():
        _live(handle, owner)

    rawcp = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
    columns = set(OrdinaryPitchCheckpoint.__table__.c.keys())
    expected_row = {k: stored[k] for k in columns}
    _typed_historical_row(expected_row, OrdinaryPitchCheckpoint.__table__)
    position = (0, 0, UUID(int=0))
    all_values = []
    envelope = None
    while True:
        token = NonplayActiveHistoryReadToken(
            game_id=UUID(doc.prefix_ref.game_id),
            generation=int(doc.internal_generation),
            checkpoint_id=UUID(doc.id),
            revision=int(doc.revision),
            epoch=int(doc.history_version),
            d3=int(doc.confirmed_watermark),
            logical_version=int(doc.prefix_ref.history_version),
            after_order=position[0],
            after_d1=position[1],
            after_id=position[2],
            page_size=100,
        )
        live()
        result = handle.run_function(token)
        live()
        if (
            type(result) is not TenantOperationResult
            or len(result.rows) != 1
            or len(result.rows[0]) != 1
            or type(result.rows[0][0]) is not str
        ):
            raise NonplaySourceUnavailable("取消bootstrapの実page応答が不一致")
        packet = _load(result.rows[0][0])
        if (
            type(packet) is not dict
            or set(packet)
            != {"checkpoint", "total", "items", "storage", "generationChain"}
            or not _same(packet["checkpoint"], rawcp)
            or type(packet["total"]) is not int
            or packet["total"] != int(doc.history_depth)
            or type(packet["items"]) is not list
            or not 1 <= len(packet["items"]) <= 101
            or type(packet["storage"]) is not dict
            or set(packet["storage"]) != {"row", "nextPhysicalPlayNumber"}
            or not _same(packet["storage"]["row"], expected_row)
        ):
            raise NonplaySourceUnavailable("取消bootstrapのCP/物理版/pageが不一致")
        binding = {
            "storage": packet["storage"],
            "generationChain": packet["generationChain"],
        }
        if envelope is None:
            envelope = binding
        elif not _same(envelope, binding):
            raise NonplaySourceUnavailable("取消bootstrapのpage間anchorが変化")
        values = []
        previous = position if position[0] else None
        for item in packet["items"]:
            point = _point(item["cursor"])
            if previous is not None and point >= previous:
                raise NonplaySourceUnavailable("取消bootstrapのpage順序が不一致")
            previous = point
            values.append((point, _frame(handle, item, live)))
        all_values.extend(values[:100])
        if len(all_values) > int(doc.history_depth):
            raise NonplaySourceUnavailable("取消bootstrapの履歴件数が過剰")
        if len(values) <= 100:
            break
        position = values[99][0]
    if envelope is None:
        raise NonplaySourceUnavailable("取消bootstrapの保存原本が欠落")
    chain = envelope["generationChain"]
    if (
        type(chain) is not list
        or any(type(x) is not str for x in chain)
        or not chain
        or len(set(chain)) != len(chain)
        or chain[-1] != doc.wire_d4
        or any(v[1]["play"]["source"]["generation"] not in chain for v in all_values)
    ):
        raise NonplaySourceUnavailable("取消bootstrapの実世代連結が不一致")
    stack = [frame for _, frame in all_values]
    cp = _checkpoint_from_legacy(doc, stack, envelope["storage"], artifact_sha256)
    _check_source(
        {
            "formatVersion": "nonplay-prefix-source-v1",
            "checkpoint": cp,
            "activeStack": stack,
        }
    )
    checked = checked_checkpoint(
        cp,
        tenant=handle._bound_tenant_id,
        game=doc.prefix_ref.game_id,
        generation=doc.wire_d4,
        d3=int(doc.confirmed_watermark),
        artifact=artifact_sha256,
    )
    live()
    return checked, all_values


def _read_undo_snapshot(handle, game_id):
    """既readと同じ実試合/世代lockとpoint原本だけを取得する。履歴は新能力で読む。"""
    from pitchlog.db.game_state.models import Game
    from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken
    from pitchlog.repositories.ordinary_prefix_operations import (
        OrdinaryCheckpointReadToken,
    )
    from pitchlog.repositories.ordinary_prefix_read import _function_one
    from pitchlog.repositories.started_read import (
        StartedReadNotVisible,
        StartedReadRecorded,
    )
    from pitchlog.repositories.started_snapshot import _one, _rows
    from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
    from pitchlog.sync.d4_reference import encode_d4_reference
    from pitchlog.sync.tokens import (
        GameLockToken,
        GameReadToken,
        RecordingGenerationLockToken,
        RecordingGenerationReadToken,
    )

    owner = _owner(handle)
    if type(game_id) is not UUID:
        raise NonplaySourceUnavailable("取消GETの試合ID型が不一致")

    def run(token):
        _live(handle, owner)
        result = handle.run(token)
        _live(handle, owner)
        return result

    columns = tuple(Game.__table__.c.keys())
    locked = _rows(run(GameLockToken(game_id)), columns)
    games = _rows(run(GameReadToken(game_id)), columns)
    if not locked and not games:
        return StartedReadNotVisible()
    if len(games) != 1 or locked != games:
        raise NonplaySourceUnavailable("取消GETの実試合lockが不一致")
    game = games[0]
    if game["tenant_id"] != handle._bound_tenant_id or game["id"] != game_id:
        raise NonplaySourceUnavailable("取消GETのtenant/gameが不一致")
    from pitchlog.repositories.game_lifecycle import _finished_lifecycle_read_allowed

    if (
        game["status"] != "in_progress"
        and not (
            game["status"] == "finished"
            and _finished_lifecycle_read_allowed(handle, game_id)
        )
    ) or any(
        game[k] is not None for k in ("trashed_at", "hidden_at", "import_batch_id")
    ):
        return StartedReadNotVisible()
    generation = _one(
        run(RecordingGenerationReadToken(game_id)), _GENERATION_READ_COLUMNS
    )
    number = generation["generation"]
    if type(number) is not int or not 0 < number < 2**63:
        raise NonplaySourceUnavailable("取消GETの世代型が不一致")
    again = _one(
        run(RecordingGenerationLockToken(game_id, number)), _GENERATION_READ_COLUMNS
    )
    watermark = generation["confirmed_watermark"]
    if (
        again != generation
        or generation["tenant_id"] != handle._bound_tenant_id
        or generation["game_id"] != game_id
        or generation["kind"] != "normal"
        or any(
            generation[k] is not None
            for k in ("revoked_at", "retired_at", "import_batch_id")
        )
        or type(watermark) is not int
        or watermark < 0
        or generation["applied_prefix"] != watermark
    ):
        raise NonplaySourceUnavailable("取消GETの真正世代/watermarkが不一致")
    summary = _function_one(handle, OrdinaryOrderSummaryToken(game_id))
    stored = _function_one(handle, OrdinaryCheckpointReadToken(game_id, number))
    _live(handle, owner)
    if (
        type(summary) is not dict
        or set(summary) != {"tail", "duplicate", "recovery_generation"}
        or summary["duplicate"] is not False
        or type(summary["recovery_generation"]) is not int
        or not 0 < summary["recovery_generation"] < 2**63
    ):
        raise NonplaySourceUnavailable("取消GETの実順序/epochが不一致")
    if stored is None or (
        type(stored) is dict and stored.get("kind") == "first-ball-save"
    ):
        return StartedReadRecorded()
    if (
        type(stored) is not dict
        or set(stored) != {"kind", "row"}
        or stored["kind"] != "checkpoint"
        or type(stored["row"]) is not dict
        or type(stored["row"].get("content")) is not dict
    ):
        raise NonplaySourceUnavailable("取消GETの保存CP形が不一致")
    if stored["row"]["content"].get("version") == "3":
        from pitchlog.authz.terminal_pitch_product import require_registered_product
        from pitchlog.db.writer_binding.ordinary_models import OrdinaryPitchCheckpoint
        from pitchlog.sync.terminal_pitch_tokens import PlayPrefixCheckpointReadToken

        require_registered_product(mode="play-prefix-play-v3")
        full = _function_one(handle, PlayPrefixCheckpointReadToken(game_id, number))
        _live(handle, owner)
        columns = OrdinaryPitchCheckpoint.__table__.c.keys()
        if (
            type(full) is not dict
            or set(full) != {"kind", "row"}
            or full["kind"] != "checkpoint"
            or type(full["row"]) is not dict
            or not _same(
                {k: stored["row"][k] for k in columns},
                {k: full["row"][k] for k in columns},
            )
        ):
            raise NonplaySourceUnavailable("取消GETのv3全head/CP原本が不一致")
        stored = full
    return {
        "game": game,
        "row": stored["row"],
        "generation": number,
        "epoch": summary["recovery_generation"],
        "d3": watermark,
        "d4": encode_d4_reference(handle._bound_tenant_id, game_id, number),
        "tail": summary["tail"],
    }


def _legacy_undo_metadata(handle, game_id, snapshot, doc):
    """旧v3のpoint/head/開始名簿の既helperを使い、旧公開history pageは流用しない。"""
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
    from pitchlog.domainrt.lineup_prefix_source import lineup_from_actual_roster
    from pitchlog.repositories.ordinary_prefix_read import (
        _evaluate_lineup_payload,
        _prefix_metadata,
    )
    from pitchlog.repositories.play_prefix import (
        _lineup_started_origin,
        _read_native_lineup_head,
    )
    from pitchlog.repositories.started_snapshot import _rows, _saved_lineup
    from pitchlog.repositories.started_snapshot_operations import (
        LINEUP_COLUMNS,
        StartedLineupsReadToken,
    )

    row, tail = snapshot["row"], snapshot["tail"]
    expected = {
        "tenant_id": str(handle._bound_tenant_id),
        "game_id": str(game_id),
        "internal_generation": snapshot["generation"],
        "id": doc.id,
        "revision": int(doc.revision),
        "history_version": int(doc.history_version),
        "recovery_generation": snapshot["epoch"],
        "confirmed_watermark": snapshot["d3"],
        "applied_watermark": snapshot["d3"],
        "content_digest": doc.content_digest,
        "state": "current",
    }
    if (
        any(type(row.get(k)) is not type(v) or row[k] != v for k, v in expected.items())
        or doc.wire_d4 != snapshot["d4"]
        or doc.prefix_ref.tenant_id != str(handle._bound_tenant_id)
        or doc.prefix_ref.game_id != str(game_id)
        or row.get("saved_at") is None
        or type(tail) is not dict
        or tail.get("tenant_id") != str(handle._bound_tenant_id)
        or tail.get("game_id") != str(game_id)
        or tail.get("generation") != snapshot["generation"]
        or type(tail.get("d1")) is not int
        or tail["d1"] != snapshot["d3"]
        or type(tail.get("d2")) is not int
        or not 0 <= tail["d2"] < 2**63 - 1000
        or source_fingerprint(row["roster"]) != doc.roster_source_digest
        or doc.source_origin.event_id
        != _lineup_started_origin(handle, game_id, snapshot["generation"])
    ):
        raise NonplaySourceUnavailable("取消GETのv3 CP/head/物理scopeが不一致")
    roster = InitialRosterProjection.model_validate_json(_canonical_json(row["roster"]))
    if lineup_from_actual_roster(roster) != doc.lineup:
        raise NonplaySourceUnavailable("取消GETの実開始名簿が不一致")
    payload, _ = _read_native_lineup_head(
        handle, game_id, handle._bound_tenant_id, row, doc
    )
    _evaluate_lineup_payload(
        payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )
    saved = _rows(handle.run(StartedLineupsReadToken(game_id)), LINEUP_COLUMNS)
    if len(saved) != 2 or any(
        x["tenant_id"] != handle._bound_tenant_id or x["game_id"] != game_id
        for x in saved
    ):
        raise NonplaySourceUnavailable("取消GETの保存済lineupが不一致")
    lineups = tuple(_saved_lineup(x) for x in saved)
    sides = tuple(
        next(x for x in lineups if x.team_id == snapshot["game"][key])
        for key in ("away_team_record_id", "home_team_record_id")
    )
    return _prefix_metadata(snapshot["game"], game_id, snapshot["d4"], sides, roster)


def read_undo_prefix(handle, game_id, *, limit=25, cursor=None):
    """初回取消前v3も正直なNP DTOへ写す。GETからwriter資格は発行しない。"""
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.repositories.ordinary_prefix_read import (
        OrdinaryPrefixView,
        read_lineup_prefix,
    )
    from pitchlog.repositories.play_prefix import read_lineup_prefix_document

    if type(limit) is not int or not 1 <= limit <= 100:
        raise NonplaySourceUnavailable("取消GET page上限が不一致")
    owner = _owner(handle)
    snapshot = _read_undo_snapshot(handle, game_id)
    _live(handle, owner)
    if type(snapshot) is not dict:
        return snapshot
    row = snapshot["row"]
    if row["content"].get("formatVersion") == "nonplay-prefix-checkpoint-v1":
        result = read_lineup_prefix(handle, game_id, limit=limit, cursor=cursor)
        _live(handle, owner)
        return result
    if row["content"].get("version") != "3":
        raise NonplaySourceUnavailable("取消GETの閉v3 profileが不一致")
    doc = read_lineup_prefix_document(_canonical_json(row["content"]))
    metadata = _legacy_undo_metadata(handle, game_id, snapshot, doc)
    _live(handle, owner)
    with open_domain_host() as host:
        cp, values = _read_legacy_undo_source(handle, doc, row, host.artifact_sha256)
    public_anchor = _page_anchor(cp)
    point = _read_page_cursor(cursor, public_anchor)
    start = 0
    if point[0]:
        matches = [i for i, (p, _) in enumerate(values) if p == point]
        if len(matches) != 1:
            raise NonplaySourceUnavailable("取消GET cursorの実境界が存在しない")
        start = matches[0] + 1
    selected = values[start : start + limit]
    next_cursor = (
        _make_page_cursor(public_anchor, selected[-1][0])
        if start + limit < len(values) and selected
        else None
    )
    _live(handle, owner)
    return OrdinaryPrefixView(
        metadata,
        {
            "profile": "nonplay-prefix-read-v1",
            "checkpoint": cp,
            "after": cp.content.restored.current,
            "next_position": {
                "d1": str(snapshot["d3"] + 1),
                "d2": str(snapshot["tail"]["d2"] + 1000),
            },
            "recovery_generation": str(snapshot["epoch"]),
            "last_saved_at": row["saved_at"],
            "page": {
                "items": [frame for _, frame in selected],
                "next_cursor": next_cursor,
            },
            "append_policy": {
                "version": "ordinary-append-v1",
                "first_d2": "1",
                "d2_gap": "1000",
                "max_d2": "9007199254740991",
            },
        },
    )
