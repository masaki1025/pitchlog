"""非play橋の実原本reader。固定関数未登録時は成功へ補完しない。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories import transaction
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync.first_ball_v5 import first_ball_database_kind
from pitchlog.sync.idempotency import operation_fingerprint, source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.undo_payload import _load, _validate_value
from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint


class NonplaySourceUnavailable(RuntimeError):
    """原本・資格の不明を内容拒否や初期値へ変換しない。"""


@dataclass(frozen=True, slots=True)
class _LockNonplayCheckpoint(TenantOperationToken):
    """nonce付きwriterだけが使う固定点読取。"""

    request_json: str

    @property
    def capability_id(self):
        """未登録の私有read能力を明示する。"""
        return "CAP:sync_nonplay:lock_checkpoint"


@dataclass(frozen=True, slots=True)
class _ReadNonplayHistoryPage(TenantOperationToken):
    """同CPの有限keysetページだけを読む。"""

    request_json: str

    @property
    def capability_id(self):
        """履歴を任意SQLへ開けない。"""
        return "CAP:sync_nonplay:read_history_page"


@dataclass(frozen=True, slots=True)
class _PrepareNonplayUndo(TenantOperationToken):
    """評価済みframeに同TXの独立印を要求する。"""

    request_json: str

    @property
    def capability_id(self):
        """私有prepare能力。"""
        return "CAP:sync_nonplay:prepare_undo"


@dataclass(frozen=True, slots=True)
class _ConsumeNonplayUndo(TenantOperationToken):
    """独立印と実原本を再確認して一回だけ投影する。"""

    request_json: str

    @property
    def capability_id(self):
        """私有consume能力。"""
        return "CAP:sync_nonplay:consume_undo"


_FUNCTIONS = MappingProxyType(
    {
        _LockNonplayCheckpoint: "lock_nonplay_checkpoint",
        _ReadNonplayHistoryPage: "read_nonplay_history_page",
        _PrepareNonplayUndo: "prepare_nonplay_undo",
        _ConsumeNonplayUndo: "consume_nonplay_undo",
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class QualifiedNonplayCall:
    """核が消費済み資格からだけ得る固定関数選択と全bind。"""

    operation: TenantOperationToken
    function_name: str
    parameters: object


_CALLS = {}
_READS = {}
_PAGE_ITEMS = {}


def _live(handle, source, event, lifetime, runtime):
    """既E1 issuer/同Session/topTX/nonceの現在性を再利用する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not runtime
        or transaction._SYNC_APPLY_ACTIVE.get() is not True
        or transaction._port_phase(handle) is not None
        or type(source) is not _E1CoreSource
        or source.scope is not handle
        or source.event is not event
        or type(event) is not SyncEvent
    ):
        raise NonplaySourceUnavailable("取消の実writer/sourceが不一致です")
    handle._assert_writer_lifetime(lifetime)
    observed = handle._writer_lifetime()
    if observed[0] is not lifetime[0] or observed[1] is not lifetime[1]:
        raise NonplaySourceUnavailable("取消のtop-level TX identityが不一致です")
    value = source.read(handle, event)
    handle._assert_writer_lifetime(lifetime)
    observed = handle._writer_lifetime()
    if observed[0] is not lifetime[0] or observed[1] is not lifetime[1]:
        raise NonplaySourceUnavailable("取消のtop-level TX identityが変更されました")
    return value


@contextmanager
def _call_scope(handle, source, event, operation):
    """呼出区間とexacttoken/全値を結びSQL直実行の偽造を閉じる。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(operation) not in _FUNCTIONS
    ):
        raise NonplaySourceUnavailable("取消の固定関数型が不一致です")
    key = handle._state_key
    if key in _CALLS:
        raise NonplaySourceUnavailable("取消関数資格の再入です")
    lifetime = handle._writer_lifetime()
    runtime = transaction._TRANSACTION_RUNTIMES.get(key)
    _live(handle, source, event, lifetime, runtime)
    if type(operation) in {_PrepareNonplayUndo, _ConsumeNonplayUndo}:
        from pitchlog.sync.nonplay_prefix_bridge import _assert_undo_write_call

        _assert_undo_write_call(handle, operation)
    lease = source.bound._lease
    parameters = {
        "tenant_id": handle._bound_tenant_id,
        "attempt_id": lease.attempt_id,
        "phase_id": lease.phase_id,
        "binding_nonce": lease.nonce,
        "device_id": lease.device_id,
        "game_id": UUID(event.game_id),
        "request_json": operation.request_json,
    }
    if (
        any(
            type(parameters[name]) is not UUID
            for name in ("tenant_id", "attempt_id", "phase_id", "device_id", "game_id")
        )
        or type(parameters["binding_nonce"]) is not bytes
        or len(parameters["binding_nonce"]) != 32
    ):
        raise NonplaySourceUnavailable("取消の型付き実bindが不一致です")
    snapshot = (
        operation,
        operation.request_json,
        parameters,
        source,
        event,
        lifetime,
        runtime,
    )
    state = [snapshot, False]
    _CALLS[key] = state
    try:
        yield
        _live(handle, source, event, lifetime, runtime)
        if state[1] is not True:
            raise NonplaySourceUnavailable("取消の固定関数が資格を消費していません")
    finally:
        if _CALLS.get(key) is state:
            del _CALLS[key]


def _qualified_nonplay_call(handle, operation):
    """Root dispatcherがSQL0の前に一回消費する唯一getter。"""
    if type(handle) is not transaction._TenantTransaction:
        raise NonplaySourceUnavailable("取消の実handleが必要です")
    state = _CALLS.get(handle._state_key)
    if state is None or state[1] is not False:
        raise NonplaySourceUnavailable("取消の関数資格が未発行又は消費済みです")
    token, raw, params, source, event, lifetime, runtime = state[0]
    _live(handle, source, event, lifetime, runtime)
    if (
        operation is not token
        or type(operation) not in _FUNCTIONS
        or type(operation.request_json) is not str
        or operation.request_json != raw
    ):
        raise NonplaySourceUnavailable("取消のtoken identity/値が不一致です")
    lease = source.bound._lease
    actual_parameters = {
        "tenant_id": handle._bound_tenant_id,
        "attempt_id": lease.attempt_id,
        "phase_id": lease.phase_id,
        "binding_nonce": lease.nonce,
        "device_id": lease.device_id,
        "game_id": UUID(event.game_id),
        "request_json": operation.request_json,
    }
    if any(
        type(value) is not type(params[name]) or value != params[name]
        for name, value in actual_parameters.items()
    ):
        raise NonplaySourceUnavailable("取消の実bind全値/型が変更されました")
    if (
        params["binding_nonce"] != lease.nonce
        or params["attempt_id"] != lease.attempt_id
        or params["phase_id"] != lease.phase_id
        or params["device_id"] != lease.device_id
        or params["game_id"] != UUID(event.game_id)
    ):
        raise NonplaySourceUnavailable("取消の実leaseが差し替わりました")
    if type(operation) in {_PrepareNonplayUndo, _ConsumeNonplayUndo}:
        from pitchlog.sync.nonplay_prefix_bridge import _consume_undo_write_call

        _consume_undo_write_call(handle, operation)
    state[1] = True
    return QualifiedNonplayCall(
        operation, _FUNCTIONS[type(operation)], MappingProxyType(dict(params))
    )


def _run(handle, source, event, token):
    """既同Session実行器へ渡す。未登録はそのまま技術故障となる。"""
    with _call_scope(handle, source, event, token):
        result = handle.run_function(token)
        if type(result) is not TenantOperationResult or type(result.rows) is not tuple:
            raise NonplaySourceUnavailable("取消の固定関数応答型が不一致です")
        return result.rows


class ConfirmedNonplayPrefix:
    """reader寿命に登録した実参照。自由constructor/cloneは資格でない。"""

    __slots__ = ()

    def __new__(cls):
        """読取関数だけが発行する。"""
        raise NonplaySourceUnavailable("取消原本参照は自由生成できません")


def _read_prefix(prefix, handle, source, event):
    """全値をコピー返却し、実identityと同scopeを繰返し検査する。"""
    state = _READS.get(prefix)
    if state is None:
        raise NonplaySourceUnavailable("取消原本参照が失効しています")
    actual_handle, actual_source, actual_event, lifetime, runtime, raw, evidence = state
    if (
        handle is not actual_handle
        or source is not actual_source
        or event is not actual_event
    ):
        raise NonplaySourceUnavailable("取消原本参照の移植です")
    _live(handle, source, event, lifetime, runtime)
    return _load(raw), _load(evidence)


def _check_source(value):
    """原本全形とhead/depth/位置の相関。野球逆計算はしない。"""
    _validate_value(value, "Source")
    cp = value["checkpoint"]
    c = cp["content"]
    stack = value["activeStack"]
    if (
        cp["ref"]["digest"] != source_fingerprint(c)
        or c["activeDepth"] != str(len(stack))
        or _canonical_json(c["activeHead"])
        != _canonical_json(stack[0]["play"] if stack else None)
        or (c["d3"] == "0") != (c["d1Head"] is None)
    ):
        raise NonplaySourceUnavailable("取消CPの全値相関が不一致です")
    identities = set()
    for index, frame in enumerate(stack):
        play = frame["play"]
        src = play["source"]
        identity = (src["generation"], src["d1"], src["eventId"], play["playId"])
        if (
            src["eventKind"] != "play_input"
            or identity in identities
            or src["gameId"] != c["scope"]["gameId"]
            or int(play["physicalPlayNumber"]) >= int(c["nextPhysicalPlayNumber"])
        ):
            raise NonplaySourceUnavailable("取消active原本が重複又は別種別です")
        identities.add(identity)
        if index == 0 and _canonical_json(frame["afterContext"]) != _canonical_json(
            c["restored"]
        ):
            raise NonplaySourceUnavailable("取消head/current文脈が不一致です")
        if index + 1 < len(stack) and _canonical_json(
            frame["beforeContext"]
        ) != _canonical_json(stack[index + 1]["afterContext"]):
            raise NonplaySourceUnavailable("取消tail文脈が不一致です")
    if c["d1Head"] is not None:
        head = c["d1Head"]["source"]
        if head["d1"] != c["d3"] or head["generation"] != c["scope"]["generation"]:
            raise NonplaySourceUnavailable("取消D3原本が不一致です")
    if (
        c["projectionHead"]["kind"] == "started-game"
        and c["projectionHead"]["eventId"] != c["origin"]["eventId"]
    ):
        raise NonplaySourceUnavailable("取消開始原本が不一致です")
    if (
        c["projectionHead"]["kind"] == "d1-event"
        and c["projectionHead"]["source"]["gameId"] != c["scope"]["gameId"]
    ):
        raise NonplaySourceUnavailable("取消投影原本の試合が不一致です")
    return value


@contextmanager
def read_confirmed_nonplay_prefix(handle, event, source, *, artifact_sha256):
    """実固定関数でpoint-lockと有限pageを読取り寿命に登録する。"""
    lifetime = handle._writer_lifetime()
    runtime = transaction._TRANSACTION_RUNTIMES.get(handle._state_key)
    _live(handle, source, event, lifetime, runtime)
    if source.write_started:
        raise NonplaySourceUnavailable("取消原本読取は最初の書込より前です")
    rows = _run(
        handle,
        source,
        event,
        _LockNonplayCheckpoint(_canonical_json({"artifactSha256": artifact_sha256})),
    )
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not str:
        raise NonplaySourceUnavailable("取消CPを一点読取できません")
    envelope = _load(rows[0][0])
    if type(envelope) is not dict or set(envelope) != {
        "checkpoint",
        "storage",
        "generationChain",
    }:
        raise NonplaySourceUnavailable("取消原本envelopeが不一致です")
    content: dict[str, Any]
    cp = envelope["checkpoint"]
    legacy = cp.get("version") == "3"
    if legacy:
        from pitchlog.repositories.play_prefix import read_lineup_prefix_document

        legacy_doc = read_lineup_prefix_document(_canonical_json(cp))
        _require_nonplay_legacy_compatibility(
            legacy_doc.artifact_sha256, artifact_sha256
        )
        content = {
            "scope": {
                "tenantId": legacy_doc.prefix_ref.tenant_id,
                "gameId": legacy_doc.prefix_ref.game_id,
                "generation": legacy_doc.wire_d4,
            },
            "executionArtifactSha256": artifact_sha256,
            "d3": legacy_doc.confirmed_watermark,
        }
        storage_ref = {
            "id": legacy_doc.id,
            "revision": legacy_doc.revision,
            "digest": legacy_doc.content_digest,
        }
    else:
        content = cp["content"]
        storage_ref = cp["ref"]
    if (
        content["scope"]["tenantId"] != str(handle._bound_tenant_id)
        or content["scope"]["gameId"] != event.game_id
        or content["scope"]["generation"] != event.d4
        or content["executionArtifactSha256"] != artifact_sha256
        or event.d1 != int(content["d3"]) + 1
    ):
        raise NonplaySourceUnavailable("取消CPのtenant/game/世代/連番が不一致です")
    stack = []
    cursor = None
    seen = set()
    while True:
        request = {"checkpoint": storage_ref, "cursor": cursor, "limit": 100}
        page_rows = _run(
            handle, source, event, _ReadNonplayHistoryPage(_canonical_json(request))
        )
        if len(page_rows) > 100:
            raise NonplaySourceUnavailable("取消pageが有限上限を超えました")
        if not page_rows:
            break
        for row in page_rows:
            if len(row) != 1 or type(row[0]) is not str:
                raise NonplaySourceUnavailable("取消page応答形が不一致です")
            item = _load(row[0])
            stored_profile = False
            if type(item) is dict and item.get("kind") in {
                "legacy-first-ball-v1",
                "accepted-ordinary-admission-v1",
            }:
                key = handle._state_key
                _PAGE_ITEMS[key] = (
                    item,
                    row[0],
                    handle,
                    event,
                    source,
                    lifetime,
                    runtime,
                )
                try:
                    if item["kind"] == "legacy-first-ball-v1":
                        item = _legacy_first_ball_item(
                            handle, event, source, item, lifetime, runtime
                        )
                    else:
                        item = _stored_ordinary_item(
                            handle, event, source, item, lifetime, runtime
                        )
                    stored_profile = True
                finally:
                    _PAGE_ITEMS.pop(key, None)
            if type(item) is not dict or set(item) != {
                "frame",
                "cursor",
                "original",
                "storedFingerprint",
                "physical",
                "expectedPhysical",
            }:
                raise NonplaySourceUnavailable("取消page原本形が不一致です")
            position = item["cursor"]
            if (
                type(position) is not list
                or len(position) != 3
                or any(type(n) is not int or n <= 0 for n in position[:2])
                or type(position[2]) is not str
                or str(UUID(position[2])) != position[2]
                or (cursor is not None and tuple(position) >= tuple(cursor))
            ):
                raise NonplaySourceUnavailable("取消page順序が不一致です")
            raw_cursor = _canonical_json(position)
            if raw_cursor in seen or _canonical_json(
                item["physical"]
            ) != _canonical_json(item["expectedPhysical"]):
                raise NonplaySourceUnavailable("取消page cursor/全physicalが不一致です")
            seen.add(raw_cursor)
            frame = item["frame"]
            src = frame["play"]["source"]
            if src["fingerprint"] != item["storedFingerprint"] or _canonical_json(
                item["original"].get("state_diff")
            ) != _canonical_json(frame["historyEntry"]["difference"]):
                raise NonplaySourceUnavailable("取消履歴と保存済原本が不一致です")
            # 保存証拠profileは原wireと同一視せず、保存済指紋そのものを参照する。
            raw = item["original"]
            if stored_profile:
                fingerprint = item["storedFingerprint"]
            elif item["storedFingerprint"].startswith("wire-v1:"):
                fingerprint = wire_event_fingerprint(freeze_wire_event(raw))
            else:
                # 旧native P2だけの既DTO指紋。raw単独hashへ付替えない。
                if set(raw) != {
                    "d5",
                    "game_id",
                    "d1",
                    "d4",
                    "event_kind",
                    "d2",
                    "payload",
                    "state_diff",
                }:
                    raise NonplaySourceUnavailable("旧native原本の全項目が不一致です")
                historical = SyncEvent(
                    raw["d5"],
                    raw["game_id"],
                    raw["d1"],
                    raw["d4"],
                    raw["event_kind"],
                    v6=raw["d2"],
                    v7=raw["payload"],
                    v8=raw["state_diff"],
                )
                fingerprint = operation_fingerprint(historical, "P2", None)
            if fingerprint != item["storedFingerprint"]:
                raise NonplaySourceUnavailable("取消の原wire指紋が不一致です")
            if any(
                (type(raw.get(key)) is not type(expected) or raw.get(key) != expected)
                for key, expected in (
                    ("game_id", src["gameId"]),
                    ("d4", src["generation"]),
                    ("d1", int(src["d1"])),
                    ("d5", src["d5"]),
                )
            ):
                raise NonplaySourceUnavailable("取消原本の全識別が不一致です")
            raw_kind = raw.get("event_kind")
            database_kind = (
                first_ball_database_kind(raw_kind) if raw_kind == "1" else raw_kind
            )
            if type(database_kind) is not str or database_kind != "play_input":
                raise NonplaySourceUnavailable("歴史原本の種別が不一致です")
            stack.append(frame)
            cursor = item["cursor"]
        _live(handle, source, event, lifetime, runtime)
    if legacy:
        cp = _checkpoint_from_legacy(
            legacy_doc, stack, envelope["storage"], artifact_sha256
        )
        envelope["checkpoint"] = cp
    value = _check_source(
        {
            "formatVersion": "nonplay-prefix-source-v1",
            "checkpoint": cp,
            "activeStack": stack,
        }
    )
    if (
        value["checkpoint"]["content"]["nextPhysicalPlayNumber"]
        != envelope["storage"]["nextPhysicalPlayNumber"]
    ):
        raise NonplaySourceUnavailable("取消の次物理番号が実maxと不一致です")
    chain = envelope["generationChain"]
    if (
        type(chain) is not list
        or not chain
        or len(set(chain)) != len(chain)
        or chain[-1] != event.d4
    ):
        raise NonplaySourceUnavailable("取消の実世代連結が不一致です")
    if any(frame["play"]["source"]["generation"] not in chain for frame in stack):
        raise NonplaySourceUnavailable("取消active対象が実世代連結にありません")
    prefix = object.__new__(ConfirmedNonplayPrefix)
    _READS[prefix] = (
        handle,
        source,
        event,
        lifetime,
        runtime,
        _canonical_json(value),
        _canonical_json(envelope),
    )
    try:
        yield prefix
        _read_prefix(prefix, handle, source, event)
    finally:
        _READS.pop(prefix, None)


def _checkpoint_from_legacy(doc, stack, storage, artifact):
    """検証済みv3原本を新版へ写す。状態/打順/走者を再計算しない。"""
    if type(storage) is not dict or set(storage) != {"row", "nextPhysicalPlayNumber"}:
        raise NonplaySourceUnavailable("取消bootstrapの物理原本が不一致です")
    row = storage["row"]
    if (
        row["id"] != doc.id
        or row["revision"] != int(doc.revision)
        or row["content_digest"] != doc.content_digest
        or _canonical_json(row["content"])
        != _canonical_json(
            doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
        )
        or len(stack) != int(doc.history_depth)
        or not stack
    ):
        raise NonplaySourceUnavailable("取消bootstrapの全CP原本が不一致です")
    head = stack[0]["play"]["source"]
    last = doc.last_source
    if (
        last is None
        or head["eventId"] != last.id
        or head["d5"] != last.d5
        or head["fingerprint"] != last.source_fingerprint
    ):
        raise NonplaySourceUnavailable("取消bootstrapのactive headが不一致です")

    def wire(model):
        """既modelの全memberを写す。"""
        return model.model_dump(mode="json", by_alias=True, exclude_unset=True)

    restored = {
        "current": wire(doc.after),
        "rules": wire(doc.rules),
        "rulesDigest": source_fingerprint(wire(doc.rules)),
        "layoutDigest": doc.roster_digest,
        "rosterDigest": doc.roster_digest,
        "lineup": wire(doc.lineup),
        "participants": wire(doc.participants),
        "runners": [wire(r) for r in doc.runners],
        "responsibility": {
            "kind": "no-change",
            "paStartSource": wire(doc.pa_start_source),
            "previousPitcherId": None,
            "strikesAtChange": None,
            "ballsAtChange": None,
        },
        "lastPlayEvaluation": wire(doc.t2) if doc.t2 is not None else None,
    }
    c = {
        "scope": {
            "tenantId": doc.prefix_ref.tenant_id,
            "gameId": doc.prefix_ref.game_id,
            "generation": doc.wire_d4,
        },
        "origin": wire(doc.source_origin),
        "d3": doc.confirmed_watermark,
        "d1Head": {"kind": "accepted-event", "source": head},
        "projectionHead": {"kind": "d1-event", "source": head},
        "activeHead": stack[0]["play"],
        "activeDepth": doc.history_depth,
        "historyVersion": doc.prefix_ref.history_version,
        "storageHistoryEpoch": doc.storage_anchor.history_epoch,
        "nextPhysicalPlayNumber": storage["nextPhysicalPlayNumber"],
        "executionArtifactSha256": artifact,
        "restored": restored,
    }
    return {
        "formatVersion": "nonplay-prefix-checkpoint-v1",
        "ref": {
            "id": doc.id,
            "revision": doc.revision,
            "digest": source_fingerprint(c),
        },
        "content": c,
    }


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalFirstBallEvidence:
    """閉history関数から得た原本snapshot。単体で保存資格ではない。"""

    source_event_id: UUID
    generation: int
    d1: int
    event_json: str
    ledger_json: str
    slot_json: str
    admission_json: str
    play_json: str
    runners_json: str


_HISTORICAL_LOANS = {}


def _read_historical_first_ball_evidence(
    handle, event, source, *, source_event_id, generation, d1
):
    """Root hook呼出区間に登録した実pointだけを一回貸与する。"""
    if type(handle) is not transaction._TenantTransaction:
        raise NonplaySourceUnavailable("歴史原本の実handleが必要です")
    loan = _HISTORICAL_LOANS.get(handle._state_key)
    if (
        loan is None
        or loan[0] is not handle
        or loan[1] is not event
        or loan[2] is not source
        or loan[6] is not False
    ):
        raise NonplaySourceUnavailable("歴史原本貸与が未発行又は消費済みです")
    _handle, _event, _source, lifetime, runtime, evidence, _used = loan
    _live(handle, source, event, lifetime, runtime)
    if (
        type(source_event_id) is not UUID
        or type(generation) is not int
        or type(d1) is not int
        or source_event_id != evidence.source_event_id
        or generation != evidence.generation
        or d1 != evidence.d1
    ):
        raise NonplaySourceUnavailable("歴史原本の対象移植です")
    loan[6] = True
    return evidence


def _legacy_first_ball_item(handle, event, source, item, lifetime, runtime):
    """未供給hook/自由JSONで完全文脈を捏造せず閉じる。"""
    from pitchlog.repositories import recorded_snapshot

    current = _PAGE_ITEMS.get(handle._state_key)
    if (
        current is None
        or current[0] is not item
        or current[2] is not handle
        or current[3] is not event
        or current[4] is not source
        or current[5] != lifetime
        or current[6] is not runtime
        or _canonical_json(item) != _canonical_json(_load(current[1]))
    ):
        raise NonplaySourceUnavailable("歴史初球itemは実page読取だけが登録できます")
    keys = {
        "kind",
        "cursor",
        "event",
        "ledger",
        "slot",
        "admission",
        "play",
        "runners",
        "qualified",
        "xmins",
    }
    if (
        type(item) is not dict
        or set(item) != keys
        or item["kind"] != "legacy-first-ball-v1"
    ):
        raise NonplaySourceUnavailable("歴史初球の原本形が不一致です")
    _check_saved_evidence(handle, event, source, item, lifetime, runtime, first=True)
    raw_event = item["event"]
    if type(raw_event) is not dict or any(
        type(raw_event.get(k)) is not int or raw_event[k] <= 0
        for k in ("generation", "d1")
    ):
        raise NonplaySourceUnavailable("歴史初球の原本位置が不一致です")
    evidence = HistoricalFirstBallEvidence(
        UUID(raw_event["id"]),
        raw_event["generation"],
        raw_event["d1"],
        _canonical_json(raw_event),
        _canonical_json(item["ledger"]),
        _canonical_json(item["slot"]),
        _canonical_json(item["admission"]),
        _canonical_json(item["play"]),
        _canonical_json(item["runners"]),
    )
    hook = getattr(recorded_snapshot, "_read_nonplay_first_ball_frame", None)
    expected_type = getattr(recorded_snapshot, "HistoricalFirstBallFrame", None)
    if hook is None or expected_type is None:
        raise NonplaySourceUnavailable("歴史初球の真正bootstrap hookは未供給です")
    key = handle._state_key
    if key in _HISTORICAL_LOANS:
        raise NonplaySourceUnavailable("歴史原本貸与の再入です")
    loan = [handle, event, source, lifetime, runtime, evidence, False]
    _HISTORICAL_LOANS[key] = loan
    try:
        value = hook(
            handle,
            event,
            source,
            source_event_id=evidence.source_event_id,
            generation=evidence.generation,
            d1=evidence.d1,
        )
        _live(handle, source, event, lifetime, runtime)
        if loan[6] is not True or type(value) is not expected_type:
            raise NonplaySourceUnavailable("歴史初球の実読取が不一致です")
        if (
            type(value.source_event_id) is not UUID
            or value.source_event_id != evidence.source_event_id
            or type(value.generation) is not int
            or value.generation != evidence.generation
            or type(value.d1) is not int
            or value.d1 != evidence.d1
        ):
            raise NonplaySourceUnavailable("歴史初球戻り値の対象移植です")
        if any(
            type(getattr(value, name)) is not str
            for name in (
                "frame_json",
                "semantic_event_json",
                "stored_fingerprint",
                "physical_json",
                "expected_physical_json",
            )
        ):
            raise NonplaySourceUnavailable("歴史初球戻り値のJSON型が不一致です")
        semantic = _semantic_event(item["event"], item["admission"])
        physical = {"play_row": item["play"], "play_runners": item["runners"]}
        if (
            value.stored_fingerprint != item["ledger"]["source_fingerprint"]
            or _canonical_json(_load(value.physical_json)) != _canonical_json(physical)
            or _canonical_json(_load(value.semantic_event_json))
            != _canonical_json(semantic)
        ):
            raise NonplaySourceUnavailable("歴史初球の保存意味列が不一致です")
        return {
            "frame": _load(value.frame_json),
            "cursor": item["cursor"],
            "original": semantic,
            "storedFingerprint": value.stored_fingerprint,
            "physical": _load(value.physical_json),
            "expectedPhysical": _load(value.expected_physical_json),
        }
    finally:
        if _HISTORICAL_LOANS.get(key) is loan:
            del _HISTORICAL_LOANS[key]


def _semantic_event(operation, admission):
    """DB意味列だけを表す。原wireの再生成/再hashには使用しない。"""
    return {
        "d5": operation["d5"],
        "game_id": operation["game_id"],
        "d1": operation["d1"],
        "d4": admission["wire_d4"],
        "event_kind": operation["event_kind"],
        "d2": operation["d2"],
        "payload": operation["payload"],
        "state_diff": operation["state_diff"],
    }


def _check_saved_evidence(handle, event, source, item, lifetime, runtime, *, first):
    """固定CTEの同scope貸与と、全保存列・消費印・同原取引を検査する。"""
    from datetime import datetime

    from sqlalchemy import (
        BigInteger,
        Boolean,
        DateTime,
        Integer,
        LargeBinary,
        String,
        Uuid,
    )
    from sqlalchemy.dialects.postgresql import JSONB

    from pitchlog.db.game_state.models import PlayRow, PlayRunner
    from pitchlog.db.sync_protocol.models import (
        EventSlot,
        IdempotencyLedger,
        OperationEvent,
    )
    from pitchlog.db.writer_binding.ordinary_models import OrdinaryPitchWriteAdmission
    from pitchlog.sync.control_provider.writer_binding_models import (
        FirstBallWriteAdmission,
    )

    _live(handle, source, event, lifetime, runtime)
    loan = _PAGE_ITEMS.get(handle._state_key)
    if (
        loan is None
        or loan[0] is not item
        or loan[2] is not handle
        or loan[3] is not event
        or loan[4] is not source
        or loan[6] is not runtime
        or _canonical_json(item) != _canonical_json(_load(loan[1]))
    ):
        raise NonplaySourceUnavailable("保存証拠は実pageの同scopeだけが貸与できます")
    physical = (
        {"play_row": item.get("play"), "play_runners": item.get("runners")}
        if first
        else item.get("physical")
    )
    if (
        type(physical) is not dict
        or set(physical) != {"play_row", "play_runners"}
        or type(physical["play_runners"]) is not list
    ):
        raise NonplaySourceUnavailable("保存証拠の物理全形が不一致です")
    rows = [
        (item.get("event"), OperationEvent),
        (item.get("ledger"), IdempotencyLedger),
        (item.get("slot"), EventSlot),
        (
            item.get("admission"),
            FirstBallWriteAdmission if first else OrdinaryPitchWriteAdmission,
        ),
        (physical["play_row"], PlayRow),
    ]
    rows.extend((runner, PlayRunner) for runner in physical["play_runners"])
    for row, model in rows:
        if type(row) is not dict or set(row) != set(model.__table__.c.keys()):
            raise NonplaySourceUnavailable("保存証拠の全列が不一致です")
        for column in model.__table__.c:
            value = row[column.name]
            if value is None:
                if column.nullable:
                    continue
                raise NonplaySourceUnavailable("保存証拠の非null列が欠落しています")
            if isinstance(column.type, (BigInteger, Integer)):
                ok = type(value) is int
            elif isinstance(column.type, Boolean):
                ok = type(value) is bool
            elif isinstance(column.type, (String, Uuid)):
                ok = type(value) is str
                if ok and isinstance(column.type, Uuid):
                    ok = str(UUID(value)) == value
            elif isinstance(column.type, DateTime):
                try:
                    ok = (
                        type(value) is str
                        and datetime.fromisoformat(value).tzinfo is not None
                    )
                except ValueError:
                    ok = False
            elif isinstance(column.type, LargeBinary):
                try:
                    ok = (
                        type(value) is str
                        and value.startswith("\\x")
                        and bytes.fromhex(value[2:]).hex() == value[2:]
                        and len(bytes.fromhex(value[2:])) == 32
                    )
                except ValueError:
                    ok = False
            elif isinstance(column.type, JSONB):
                ok = type(value) in {dict, list, str, int, float, bool}
            else:
                ok = False
            if not ok:
                raise NonplaySourceUnavailable("保存証拠の列型が不一致です")
    ev, ledger, slot, admission = (
        item[n] for n in ("event", "ledger", "slot", "admission")
    )
    expected = {"tenant_id": str(handle._bound_tenant_id), "game_id": event.game_id}
    if any(
        row[k] != value
        for row in (ev, slot, admission)
        for k, value in expected.items()
    ):
        raise NonplaySourceUnavailable("保存証拠のtenant/gameが不一致です")
    if (
        item.get("qualified") is not True
        or ev["ledger_kind"] != "accepted"
        or ev["event_kind"] != "play_input"
        or ev["is_tombstone"] is not False
        or any(
            ev[k] is not None
            for k in (
                "replaced_at",
                "retired_at",
                "import_batch_id",
                "legacy_row_identifier",
            )
        )
        or ev["migration_unverified"] is not False
        or ledger["tenant_id"] != ev["tenant_id"]
        or ledger["d5"] != ev["d5"]
        or ledger["kind"] != "accepted"
        or ledger["retired_at"] is not None
        or ledger["import_batch_id"] is not None
        or admission["state"] != "consumed"
        or admission["consumed_at"] is None
        or admission["source_event_id"] != ev["id"]
        or admission["d5"] != ev["d5"]
        or admission["internal_generation"] != ev["generation"]
        or admission["event_fingerprint"] != ledger["source_fingerprint"]
        or slot["generation"] != ev["generation"]
        or slot["d1"] != ev["d1"]
        or slot["confirmed_version"] != 1
    ):
        raise NonplaySourceUnavailable("保存証拠のaccepted/consumed対応が不一致です")
    xmins = item.get("xmins")
    txid = admission["transaction_id"]
    if (
        type(txid) is not str
        or not txid.isascii()
        or not txid.isdecimal()
        or str(int(txid)) != txid
        or int(txid) <= 0
        or type(xmins) is not dict
        or set(xmins) != {"event", "ledger", "admission", "play", "slot"}
        or any(
            type(v) is not str or v != str(int(txid) % 4294967296)
            for v in xmins.values()
        )
    ):
        raise NonplaySourceUnavailable("保存証拠の原top-level取引が不一致です")
    play = item["play"] if first else item["physical"]["play_row"]
    if (
        type(play) is not dict
        or play.get("id") != admission["play_row_id"]
        or play.get("source_event_id") != ev["id"]
        or any(play.get(k) != value for k, value in expected.items())
        or play.get("hidden_at") is not None
        or play.get("import_batch_id") is not None
        or play.get("legacy_row_identifier") is not None
        or play.get("migration_unverified") is not False
    ):
        raise NonplaySourceUnavailable("保存証拠の全物理対象が不一致です")
    if any(
        r["tenant_id"] != ev["tenant_id"] or r["play_id"] != play["id"]
        for r in physical["play_runners"]
    ):
        raise NonplaySourceUnavailable("保存証拠の走者参照が不一致です")
    if not first:
        if (
            admission["source_d1"] != ev["d1"]
            or admission["source_d2"] != ev["d2"]
            or _canonical_json(admission["history_entry"])
            != _canonical_json(item["frame"]["historyEntry"])
            or _canonical_json(
                admission["next_checkpoint_content"]["projection_snapshot"]
            )
            != _canonical_json(item["physical"])
        ):
            raise NonplaySourceUnavailable("保存証拠の履歴/全投影が不一致です")
        before, after = _stored_contexts(ev["payload"])
        if (
            _canonical_json(before) != _canonical_json(item["frame"]["beforeContext"])
            or _canonical_json(after) != _canonical_json(item["frame"]["afterContext"])
            or item["frame"]["play"]["playId"] != play["id"]
            or item["frame"]["play"]["source"]["eventId"] != ev["id"]
            or item["frame"]["play"]["d2"] != str(ev["d2"])
            or item["frame"]["play"]["physicalPlayNumber"] != str(play["play_number"])
        ):
            raise NonplaySourceUnavailable("保存証拠の全frameが不一致です")
    return ev, ledger, admission


def _stored_contexts(payload):
    """保存済みcalculationの全fieldを射影する。数学の再計算は行わない。"""
    try:
        source = payload["calculation"]["request"]["source"]
        value = payload["calculation"]["response"]["value"]
        before = {
            key: source[key]
            for key in (
                "rules",
                "rulesDigest",
                "layoutDigest",
                "rosterDigest",
                "lineup",
                "participants",
                "runners",
                "responsibility",
            )
        }
        before.update(current=source["after"], lastPlayEvaluation=source["t2"])
        after = {key: before[key] for key in ("rules", "rulesDigest", "layoutDigest")}
        after.update(
            {
                key: value[key]
                for key in ("rosterDigest", "lineup", "participants", "runners")
            }
        )
        after.update(
            current=value["t1"]["after"],
            responsibility=value["nextResponsibility"],
            lastPlayEvaluation=value["t2"],
        )
        return before, after
    except (KeyError, TypeError) as exc:
        raise NonplaySourceUnavailable(
            "保存済みcalculationの全fieldが必要です"
        ) from exc


def _stored_ordinary_item(handle, event, source, item, lifetime, runtime):
    """原wire再hashをせず、真正消費済保存証拠profileを閉射影する。"""
    if set(item) != {
        "kind",
        "frame",
        "cursor",
        "storedEvent",
        "storedFingerprint",
        "physical",
        "expectedPhysical",
        "event",
        "ledger",
        "slot",
        "admission",
        "qualified",
        "xmins",
    }:
        raise NonplaySourceUnavailable("保存証拠profileの閉形が不一致です")
    ev, ledger, admission = _check_saved_evidence(
        handle, event, source, item, lifetime, runtime, first=False
    )
    semantic = _semantic_event(ev, admission)
    if (
        _canonical_json(item["storedEvent"]) != _canonical_json(semantic)
        or item["storedFingerprint"] != ledger["source_fingerprint"]
    ):
        raise NonplaySourceUnavailable("保存証拠の意味列/指紋が不一致です")
    return {
        "frame": item["frame"],
        "cursor": item["cursor"],
        "original": semantic,
        "storedFingerprint": ledger["source_fingerprint"],
        "physical": item["physical"],
        "expectedPhysical": item["expectedPhysical"],
    }


def _require_nonplay_legacy_compatibility(prior, execution):
    """真正旧v3をcurrentへ投影する前に、共有の有限互換資格を必須確認する。"""
    from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
    from pitchlog.repositories.play_prefix import _require_legacy_compatibility

    try:
        _require_legacy_compatibility(
            prior, execution, source_format="play-prefix-play-v3"
        )
    except OrdinaryPrefixError:
        raise NonplaySourceUnavailable(
            "旧v3の有限artifact互換資格が確認できません"
        ) from None
