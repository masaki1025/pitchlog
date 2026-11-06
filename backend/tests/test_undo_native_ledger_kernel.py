"""取消native台帳の実既7Aへpure資格doubleを供給する。実DBではない。"""

from types import MappingProxyType
from uuid import UUID

import pytest
from test_native_ledger_insert import rig as rig

from pitchlog.sync import first_ball_execution as first
from pitchlog.sync import native_ledger_insert as api
from pitchlog.sync import ordinary_pitch_execution as ordinary
from pitchlog.sync import undo_execution as undo
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.model import SyncEvent


@pytest.fixture
def undo_rig(rig, monkeypatch):
    """実Session/bind/tokenを保持し、評価済みopaque状態だけを明示合成する。"""
    r = rig
    old = r.event
    payload = {"formatVersion": "native-undo-prefix-v1"}
    r.event = SyncEvent(
        old.d5,
        old.game_id,
        old.d1,
        old.d4,
        v5="undo",
        v7=payload,
        v10={"game": old.game_id, "d4": "1", "d1": 1},
    )
    r.source.event = r.event
    monkeypatch.delitem(first._EXECUTIONS, r.key, raising=False)
    monkeypatch.delitem(ordinary._EXECUTIONS, r.key, raising=False)
    state = undo._Execution(
        r.handle,
        r.writer,
        r.source,
        r.event,
        r.state.lifetime,
        r.state.runtime,
        phase="ready",
        anchor=tuple(object() for _ in range(7)),
        prefix=object(),
        payload=payload,
        frame=object.__new__(undo.UndoFrame),
        frame_id=UUID(int=97),
        event_id=UUID(int=98),
    )
    monkeypatch.setitem(undo._EXECUTIONS, r.key, state)
    r.undo_state, r.hook_calls = state, []

    def hook(handle, event, writer):
        assert handle is r.handle and event is r.event and writer is r.writer
        r.hook_calls.append(True)
        return state

    monkeypatch.setattr(undo, "_undo_native_ledger_state", hook)

    def classify(handle, d5, fingerprint, path):
        assert handle is r.handle
        assert (d5, fingerprint, path) == (r.token.d5, r.token.source_fingerprint, "P1")
        r.classified.append((d5, fingerprint, path))
        return r.candidates.pop(0)

    monkeypatch.setattr(api, "classify_d5", classify)
    return r


def call(r):
    """D2の無い取消をP1の既native入口へ渡す。"""
    return api._recheck_and_insert_native_result(
        r.handle, r.writer, r.event, r.token, "P1"
    )


def test_fresh_undo_rechecks_real_native_hook_and_inserts_once(undo_rig):
    """実固定INSERTと前後qualificationを通しStatsStateを借用しない。"""
    r = undo_rig
    assert call(r) is None
    assert len(r.calls) == 1 and len(r.hook_calls) == 3
    assert len(r.undo_state.anchor) == 7
    assert not hasattr(r.undo_state, "stats_source_reference")
    assert r.results[0].closed
    assert not r.controls


@pytest.mark.parametrize("stored_kind", ["accepted", "rejected", "evacuated"])
@pytest.mark.parametrize("kind", ["stored_result", "conflict"])
def test_stored_d5_skips_fresh_undo_hook_even_with_missing_frame(
    undo_rig, kind, stored_kind
):
    """DI2/DI3はfresh状態の破損より先、再sendで二重INSERTしない。"""
    r = undo_rig
    r.undo_state.frame = None
    candidate = D5Candidate(
        kind,
        stored=StoredResult(
            stored_kind,
            "same",
            {
                "state": {"accepted": "受理", "rejected": "拒否", "evacuated": "退避"}[
                    stored_kind
                ],
                "d3": 1,
                "temporary_id_mapping": MappingProxyType({}),
            },
            "stored rejection" if stored_kind == "rejected" else None,
        )
        if kind == "stored_result"
        else None,
        boundary="B3b" if kind == "conflict" else None,
    )
    r.candidates = [candidate]
    assert call(r) is candidate
    assert not r.hook_calls and not r.calls


@pytest.mark.parametrize(
    "fault",
    [
        "runtime",
        "writer",
        "frame",
        "event-id",
        "payload",
        "anchor",
        "prefix",
        "projected",
        "fingerprint",
    ],
)
def test_fresh_undo_forged_state_never_inserts(undo_rig, fault):
    """実hookの資格に加えてnative固定入口も同一性/全値を再確認する。"""
    r = undo_rig
    if fault == "runtime":
        r.undo_state.runtime = object()
    elif fault == "writer":
        r.undo_state.writer = object()
    elif fault == "frame":
        r.undo_state.frame = None
    elif fault == "event-id":
        r.undo_state.event_id = object()
    elif fault == "payload":
        r.undo_state.payload = {"formatVersion": "other"}
    elif fault == "anchor":
        r.undo_state.anchor = (object(),)
    elif fault == "prefix":
        r.undo_state.prefix = None
    elif fault == "projected":
        r.undo_state.projected = r.event
    else:
        from dataclasses import replace

        r.token = replace(r.token, source_fingerprint="changed")
    with pytest.raises(api.NativeLedgerInsertError):
        call(r)
    assert not r.calls


def test_race_after_insert_zero_classifies_without_second_fresh_state(undo_rig):
    """競合待機中の失効をDI3より先にfresh拒否しない。"""
    r = undo_rig
    race = D5Candidate("conflict", boundary="B3b")
    r.candidates = [D5Candidate("unused"), race]
    r.result = []
    r.after_execute = lambda: setattr(r.undo_state, "frame", None)
    assert call(r) is race
    assert len(r.hook_calls) == 2 and len(r.calls) == 1


def test_nonzero_insert_with_late_frame_loss_propagates_for_outer_rollback(undo_rig):
    """一行INSERT後の資格失効も成功化せず、局所commit/savepointを作らない。"""
    r = undo_rig
    r.after_execute = lambda: setattr(r.undo_state, "frame", None)
    with pytest.raises(api.NativeLedgerInsertError):
        call(r)
    assert len(r.calls) == 1 and r.results[0].closed
    assert not r.controls
