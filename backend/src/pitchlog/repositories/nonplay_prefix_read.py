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
    if not _same(cp.model_dump(mode="json", by_alias=True), raw):
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


def _read_active_page_bound(handle, cp, *, generation, limit=25, cursor=None):
    """同CPの一page。全stack完成とは区別する。秘密を返さない。"""
    owner = _owner(handle)

    def live():
        _live(handle, owner)

    rawcp = cp.model_dump(mode="json", by_alias=True)
    anchor = {
        "checkpoint": rawcp["ref"],
        "scope": rawcp["content"]["scope"],
        "d3": cp.content.d3,
        "epoch": cp.content.storage_history_epoch,
        "historyVersion": cp.content.history_version,
    }
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
    token = NonplayActiveHistoryReadToken(
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
        p = selected[-1][0]
        encoded = _canonical_json(
            {"anchor": anchor, "position": [p[0], p[1], str(p[2])]}
        )
        next_cursor = base64.urlsafe_b64encode(encoded.encode()).decode().rstrip("=")
    return {"items": [frame for _, frame in selected], "next_cursor": next_cursor}


def read_active_page(handle, cp, *, generation, limit=25, cursor=None):
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
            handle, cp, generation=generation, limit=limit, cursor=cursor
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
        "checkpoint": cp.model_dump(mode="json", by_alias=True),
        "activeStack": frames,
    }
    _check_source(raw)
    if (
        not _same(raw, proposal.source.model_dump(mode="json", by_alias=True))
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
        or _canonical_json(prefix.source.model_dump(mode="json", by_alias=True))
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
