"""実取消host/bridgeと実型Sessionを使い、SQL応答doubleの一回受領を対向検査する。"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
import test_nonplay_prefix as source_fixtures
from sqlalchemy.orm import Session
from test_nonplay_prefix import wire_event
from test_undo_execution import prepared

from pitchlog.authz import stats_primitive_sql, stats_undo_sql
from pitchlog.domaingen.core import (
    _canonical_hash,
    generate_native_primitive_sql_bundle,
)
from pitchlog.repositories import nonplay_prefix as reader
from pitchlog.repositories import transaction as tx
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
from pitchlog.sync import nonplay_prefix_bridge as bridge
from pitchlog.sync import stats_native_flush as api
from pitchlog.sync import undo_execution as execution
from pitchlog.sync.control_provider import writer_binding
from pitchlog.sync.idempotency import _json_value, event_source

ROOT = Path(__file__).parents[2]


def native_profile(root):
    """未採用manifestへ書かず、別テストcopy用の独立束縛値だけを導出する。"""
    import hashlib

    common = json.loads((root / "backend/domain/play-export.model.json").read_text())
    consumer = json.loads((root / "backend/domain/stats.model.json").read_text())
    path = "backend/domain/play-export-undo-selection.model.json"
    raw = (root / path).read_bytes()
    profile = json.loads(raw)
    return {
        "version": 1,
        "profilePath": path,
        "profileFileSha256": hashlib.sha256(raw).hexdigest(),
        "profileSha256": _canonical_hash(profile),
        "generatedFiles": {
            key: hashlib.sha256(value.encode()).hexdigest()
            for key, value in generate_native_primitive_sql_bundle(
                common, consumer, profile
            ).items()
        },
    }


@pytest.fixture
def verified_native_root(tmp_path, monkeypatch):
    """真正全入力を独立copyへ複製し、root未採用profileを候補としてだけ供給する。"""
    import shutil

    # 部分mockの成功ではなく、既_verified_inputs全旧hash検証も通る実体copy。
    for directory in (
        "backend/domain",
        "backend/src/pitchlog/exports/generated",
        "backend/src/pitchlog/stats/generated",
        "frontend/src/lib/generated",
        "docs/features/mvp-stats-primitives",
    ):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    path = tmp_path / "backend/domain/stats-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["nativeCanonicalSelection"] = native_profile(tmp_path)
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(stats_primitive_sql, "_ROOT", tmp_path)
    monkeypatch.setattr(stats_undo_sql, "_ROOT", tmp_path)
    return tmp_path


def receipt_value(rig, state, preparation):
    """明示SQLdoubleの閉期待。実PG受領証や数学期待の採取とは区別する。"""
    return {
        "formatVersion": "undo-native-stats-receipt-v1",
        "profileSha256": api._undo_selector_hash(),
        "modelSha256": SOURCE_MODEL_HASH,
        "tenantId": str(rig.handle._context.tenant_id),
        "gameId": rig.event.game_id,
        "attemptId": str(rig.lease.attempt_id),
        "phaseId": str(rig.lease.phase_id),
        "undoEventId": str(state.event_id),
        "targetEventId": preparation["target"]["source"]["eventId"],
        "frameId": str(state.frame_id),
        "frameDigest": preparation["frame_digest"],
        "artifactSha256": state.artifact,
        "sourceFingerprint": preparation["source_fingerprint"],
        "transactionId": "12345",
        "internalGeneration": "1",
        "checkpointDigest": preparation["after_source"]["checkpoint"]["ref"]["digest"],
        "oldFactVersionId": str(UUID(int=901)),
        "factVersionId": str(UUID(int=902)),
        "oldRevision": "2",
        "revision": "3",
        "sourceCount": "1",
        "beforeSourceSetSha256": "a" * 64,
        "sourceSetSha256": "b" * 64,
    }


@pytest.fixture
def base_rig(monkeypatch):
    """旧fixture本体を同じmonkeypatch寿命で使い、元test値を保持する。"""
    yield from cast(Any, source_fixtures.rig).__wrapped__(monkeypatch)


@pytest.fixture
def undo_stats_rig(base_rig, monkeypatch):
    """認可/SQLはdouble、実Session/topTX/LiveBinding型と唯一hostは本体を使用する。"""
    r = base_rig
    session = Session()
    session.begin()
    runtime = (session, r.runtime[1])
    monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, r.handle._state_key, runtime)
    r.runtime, r.session = runtime, session
    bound = object.__new__(writer_binding._LiveWriterBinding)
    bound._handle, bound._owner, bound._used = (
        r.handle,
        r.handle._writer_lifetime(),
        False,
    )
    bound._phase_snapshot = json.dumps(
        {"phase": {"internal_generation": 1, "wire_d4": r.event.d4}}
    )
    r.lease._phase_snapshot = bound._phase_snapshot
    bound._lease = r.lease
    bound._identity = writer_binding.WriterIdentity(
        "1",
        "1",
        datetime(2026, 11, 6, tzinfo=timezone.utc),
        123,
        datetime(2026, 11, 6, tzinfo=timezone.utc),
        "12345",
    )
    r.source.bound = bound
    r.bound = bound
    monkeypatch.setitem(writer_binding._LIVE_BINDINGS, r.handle._state_key, bound)
    monkeypatch.setattr(
        writer_binding._LiveWriterBinding, "assert_current", lambda self: None
    )
    original = type(r.handle).run_function
    r.receipt_mutation = None
    r.old_body = False

    def run(handle, token):
        result = original(handle, token)
        if type(token) is reader._ConsumeNonplayUndo and r.response_override is None:
            if r.old_body:
                return result
            state = execution._EXECUTIONS[handle._state_key]
            value = receipt_value(r, state, json.loads(token.request_json))
            if r.receipt_mutation:
                r.receipt_mutation(value)
            return TenantOperationResult(((json.dumps(value),),))
        return result

    monkeypatch.setattr(type(r.handle), "run_function", run)
    try:
        yield r
    finally:
        session.close()


def project(r, state):
    """元DTOを再利用せず本体が照合する別projected identityで実bridgeへ進む。"""
    r.source.write_started = True
    projected = wire_event(_json_value(event_source(r.event)))
    with execution._bind_undo_projection(r.handle, r.writer, r.event, projected):
        bridge.project_nonplay_undo(r.handle, projected, r.writer)
    assert state.projected is None and state.completed_projected is projected
    return projected


def test_actual_host_bridge_receipt_and_after_with_one_use_flush(undo_stats_rig):
    """with後phaseprojected/同実参照だけが一度受領し、終了時資格を失効する。"""
    r = undo_stats_rig
    with prepared(r) as state:
        projected = project(r, state)
        result = api._flush_native_undo_stats(
            r.handle, r.writer, r.event, projected, generation=1
        )
        assert result["sourceCount"] == "1" and result["revision"] == "3"
        with pytest.raises(api.StatsNativeFlushError):
            api._flush_native_undo_stats(
                r.handle, r.writer, r.event, projected, generation=1
            )
    assert state.stats_receipt is None and state.completed_projected is None
    with pytest.raises(api.StatsNativeFlushError):
        api._flush_native_undo_stats(
            r.handle, r.writer, r.event, projected, generation=1
        )


@pytest.mark.parametrize(
    "mutation",
    ["phase", "projected", "runtime", "nonce", "source", "frame", "generation"],
)
def test_real_lifetime_or_identity_change_never_accepts_receipt(
    undo_stats_rig, monkeypatch, mutation
):
    """同値clone/ready/別source/TX/nonceの権限昇格を拒否する。"""
    r = undo_stats_rig
    with prepared(r) as state:
        projected = project(r, state)
        generation = 1
        saved_source = state.source
        with monkeypatch.context() as patch:
            if mutation == "phase":
                state.phase = "ready"
            elif mutation == "projected":
                projected = wire_event(_json_value(event_source(r.event)))
            elif mutation == "runtime":
                patch.setitem(
                    tx._TRANSACTION_RUNTIMES, r.handle._state_key, (r.session, object())
                )
            elif mutation == "nonce":
                patch.setattr(r.lease, "nonce", b"z" * 32)
            elif mutation == "source":
                state.source = copy.copy(r.source)
            elif mutation == "frame":
                state.frame_id = UUID(int=111)
            else:
                generation = 2
            try:
                with pytest.raises(RuntimeError):
                    api._flush_native_undo_stats(
                        r.handle, r.writer, r.event, projected, generation=generation
                    )
            finally:
                state.source = saved_source


@pytest.mark.parametrize("key", sorted(api._UNDO_RECEIPT_KEYS))
def test_every_receipt_column_is_closed_and_bound(undo_stats_rig, key):
    """全列欠落を実bridgeが拒否し、旧bool SQLbodyも成功にしない。"""
    r = undo_stats_rig
    r.receipt_mutation = lambda value: value.pop(key)
    with prepared(r) as state, pytest.raises(api.StatsNativeFlushError):
        project(r, state)


def test_old_bool_consume_body_fails_closed(undo_stats_rig):
    """旧登録/bodyの戻り値を新S成立と解釈しない。"""
    r = undo_stats_rig
    r.old_body = True
    with prepared(r) as state, pytest.raises(api.StatsNativeFlushError):
        project(r, state)


def test_receipt_constructor_and_free_raw_cannot_issue():
    """閉JSONとprivate型の自由constructorだけでは実scope資格を作らない。"""
    with pytest.raises(api.StatsNativeFlushError):
        api._UndoStatsReceipt()
    for value in (True, 1, "{}", "x" * 4097, '{"x":1,"x":2}'):
        with pytest.raises(api.StatsNativeFlushError):
            api._decode_undo_stats_receipt(value)


def test_generated_helper_invalidates_and_clones_only_same_s(verified_native_root):
    """数学/credit計算を持たず、唯一生成membershipと同TX versionだけを使う。"""
    body = stats_undo_sql.candidate_function_body()
    for part in (
        "SECURITY INVOKER",
        "current_user<>'pitchlog_sync_right_fn_owner'",
        "stamp.state<>'consumed'",
        "FOR UPDATE",
        "UPDATE sync_fence.stats_fact_versions SET is_current=false",
        "prior.revision+1",
        "INSERT INTO sync_fence.stats_primitive_sources",
        "INSERT INTO sync_fence.stats_primitive_facts",
        "restore-undo-event",
        "canonical_undos AS",
    ):
        assert part in body
    assert (
        "DELETE FROM" not in body
        and "COMMIT" not in body
        and "EXCEPTION WHEN" not in body
    )
    assert "SUM(" not in body and "p_expected" not in body
    assert "original.metric_states" in body and "original.amount" in body


def test_missing_native_profile_and_any_changed_binding_are_unavailable(
    verified_native_root,
):
    """旧T5/profileは不変でも新selector封印が無ければnative関数を出さない。"""
    path = verified_native_root / "backend/domain/stats-manifest.json"
    manifest = json.loads(path.read_text())
    for key in tuple(manifest["nativeCanonicalSelection"]):
        changed = copy.deepcopy(manifest)
        del changed["nativeCanonicalSelection"][key]
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            stats_primitive_sql._verified_inputs(verified_native_root)
    path.write_text(json.dumps(manifest))
    assert (
        stats_primitive_sql._verified_inputs(verified_native_root)[2]
        == SOURCE_MODEL_HASH
    )


def decoder_receipt():
    """decoder肯定の有限text。自由JSONで資格が発行されるという主張ではない。"""
    value = {key: "a" * 64 for key in api._UNDO_RECEIPT_KEYS}
    for index, key in enumerate(
        (
            "tenantId",
            "gameId",
            "attemptId",
            "phaseId",
            "undoEventId",
            "targetEventId",
            "frameId",
            "oldFactVersionId",
            "factVersionId",
        ),
        1,
    ):
        value[key] = str(UUID(int=index))
    value.update(
        formatVersion="undo-native-stats-receipt-v1",
        profileSha256=api._undo_selector_hash(),
        modelSha256=SOURCE_MODEL_HASH,
        oldRevision="2",
        revision="3",
        sourceCount="1",
        transactionId="12345",
        internalGeneration="1",
    )
    return json.dumps(value)


@pytest.mark.parametrize(
    "mutation",
    ["clone", "raw", "preparation", "scope-clone", "anchor", "pointer", "used-reset"],
)
def test_issued_registry_rejects_equal_looking_or_mutated_receipt(
    undo_stats_rig, mutation
):
    """非作者のclone/raw反例と独立anchor/一回状態の改変を拒否する。"""
    from dataclasses import fields

    r = undo_stats_rig
    with prepared(r) as state:
        projected = project(r, state)
        original = state.stats_receipt
        issued = api._UNDO_STATS_ISSUED[id(state)]
        assert issued.receipt is original and issued.used is False
        with pytest.raises(AttributeError):
            object.__setattr__(issued, "raw", "changed")
        if mutation == "clone":
            clone = object.__new__(type(original))
            for field in fields(original):
                object.__setattr__(clone, field.name, getattr(original, field.name))
            state.stats_receipt = clone
        elif mutation == "raw":
            value = json.loads(original.raw)
            value["sourceCount"] = "999"
            object.__setattr__(original, "raw", json.dumps(value))
        elif mutation == "preparation":
            object.__setattr__(
                original, "preparation_json", original.preparation_json + " "
            )
        elif mutation == "scope-clone":
            clone = object.__new__(type(original.scope))
            for field in fields(original.scope):
                object.__setattr__(
                    clone, field.name, getattr(original.scope, field.name)
                )
            object.__setattr__(original, "scope", clone)
        elif mutation == "anchor":
            state.anchor = tuple(list(state.anchor))
        elif mutation == "pointer":
            state.stats_receipt = None
        else:
            api._flush_native_undo_stats(
                r.handle, r.writer, r.event, projected, generation=1
            )
            state.stats_flushed = False
        with pytest.raises(api.StatsNativeFlushError):
            api._flush_native_undo_stats(
                r.handle, r.writer, r.event, projected, generation=1
            )
    assert id(state) not in api._UNDO_STATS_ISSUED


@pytest.mark.parametrize("when", [1, 2])
def test_receipt_rechecked_after_each_live_scope_probe(
    undo_stats_rig, monkeypatch, when
):
    """資格照合の途中でも独立raw anchorを再照合し、成功へすり抜けさせない。"""
    r = undo_stats_rig
    with prepared(r) as state:
        projected = project(r, state)
        original_assert = api._assert_scope
        calls = []

        def assert_scope(scope, *args):
            original_assert(scope, *args)
            calls.append(True)
            if len(calls) == when:
                value = json.loads(state.stats_receipt.raw)
                value["sourceCount"] = "999"
                object.__setattr__(state.stats_receipt, "raw", json.dumps(value))

        monkeypatch.setattr(api, "_assert_scope", assert_scope)
        with pytest.raises(api.StatsNativeFlushError):
            api._flush_native_undo_stats(
                r.handle, r.writer, r.event, projected, generation=1
            )
    assert id(state) not in api._UNDO_STATS_ISSUED


def test_undo_clone_reuses_exact_existing_credit_guard(verified_native_root):
    """clone前の旧版全creditとclone後の新版を同じ既存read guardで検証する。"""
    read_guard = stats_primitive_sql._credit_integrity_guard("read")
    before = stats_primitive_sql._credit_integrity_guard("undo-prior")
    after = stats_primitive_sql._credit_integrity_guard("undo-current")
    assert (
        before.replace("p_tenant_id", "tenant").replace("prior.id", "p_fact_version_id")
        == read_guard
    )
    assert (
        after.replace("p_tenant_id", "tenant").replace("new_id", "p_fact_version_id")
        == read_guard
    )
    assert "s.evaluation_sha256 IS DISTINCT FROM" in read_guard
    assert "expected_credits EXCEPT SELECT * FROM actual_credits" in read_guard
    assert "actual_credits EXCEPT SELECT * FROM expected_credits" in read_guard
    assert "c.ordinality-1" in read_guard
    assert "COUNT(*)>0" not in read_guard
    normal = stats_primitive_sql.candidate_function_bodies()
    assert read_guard in normal["open_primitive_snapshot"]
    assert read_guard in normal["save_primitive_source"]
    assert "open_primitive_snapshot(" in normal["read_play_export_primitives"]
    body = stats_undo_sql.candidate_function_body()
    assert body.count(before) == body.count(after) == 1
    assert body.index(before) < body.index("SET is_current=false")
    assert body.index("INSERT INTO sync_fence.stats_primitive_facts") < body.index(
        after
    )
    assert body.index(after) < body.index("RETURN QUERY")
    for value in ("read;SELECT 1", "undo-other", True, None):
        with pytest.raises(ValueError):
            stats_primitive_sql._credit_integrity_guard(cast(Any, value))
