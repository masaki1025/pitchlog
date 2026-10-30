"""T9・T8 の分類、保存済み結果、ロック順を DB なしで検査する。"""

from __future__ import annotations

from types import MappingProxyType
from typing import cast
from uuid import UUID

import pytest

from pitchlog.repositories.tokens import (
    ImmutableValue,
    TenantOperationResult,
    TenantOperationToken,
)
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.prefix_path import (
    P1ContentRejection,
    P1PreconditionCategory,
    P1PreconditionError,
    _lock_game_generation,
)
from pitchlog.sync.prefix_path import (
    _candidate_result as _p1_candidate_result,
)
from pitchlog.sync.rejection import _candidate_result, content_reason_for_precondition
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    GameLockToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
)


def _stored(kind: str, state: str, d3: int, reason: str | None) -> D5Candidate:
    """台帳から実体化された確定結果を作る。"""
    return D5Candidate(
        "stored_result",
        stored=StoredResult(
            kind,
            "fingerprint",
            MappingProxyType({"state": state, "d3": d3}),
            reason,
        ),
    )


def test_b3a_replay_keeps_the_original_reason_and_d3() -> None:
    """現在の D3 ではなく T9 に保存した結果を再掲する。"""
    result = _candidate_result(_stored("rejected", "拒否", 4, "内容が不正"), 9)
    assert result is not None
    actual = (result.boundary, result.state, result.d3, result.reason, result.replayed)
    assert actual == (
        "B3a",
        "拒否",
        4,
        "内容が不正",
        True,
    )


def test_b4_replay_does_not_need_current_rights() -> None:
    """退避の再掲は記録権ポートへ進む前の純分類で決まる。"""
    result = _candidate_result(_stored("evacuated", "退避", 2, None), 11)
    assert result is not None
    assert (result.boundary, result.state, result.d3, result.replayed) == (
        "B4",
        "退避",
        2,
        True,
    )


@pytest.mark.parametrize(
    ("kind", "state", "boundary", "reason"),
    [
        ("rejected", "拒否", "B3a", "元の理由"),
        ("evacuated", "退避", "B4", None),
    ],
)
def test_common_p1_path_replays_saved_rejection_or_escrow(
    kind: str, state: str, boundary: str, reason: str | None
) -> None:
    """P1/P2 共通の D5 分類からも現在の記録権に進まず再掲する。"""
    result = _p1_candidate_result(_stored(kind, state, 3, reason), 8)
    assert result is not None
    assert (result.boundary, result.d3, result.a5, result.reason, result.replayed) == (
        boundary,
        3,
        state,
        reason,
        True,
    )


def test_b3b_is_not_a_new_t9_result() -> None:
    """異内容 D5 は先着を変えず、B3b 候補だけにする。"""
    result = _candidate_result(D5Candidate("conflict", boundary="B3b"), 3)
    assert result is not None
    assert (result.boundary, result.replayed) == ("B3b", False)


@pytest.mark.parametrize("category", ["recording_rights", "other"])
def test_only_w2_violation_maps_to_t9(category: str) -> None:
    """記録権や一般の前提違反を内容拒否として消費しない。"""
    error = P1PreconditionError("失敗", cast(P1PreconditionCategory, category))
    with pytest.raises(ValueError, match="内容拒否以外"):
        content_reason_for_precondition(error)


def test_w2_violation_maps_to_b3a_reason() -> None:
    """拒否原本または V10 の対象不一致を T9 の理由へ渡す。"""
    error = P1PreconditionError("V10 不一致", "w2_violation")
    assert content_reason_for_precondition(error) == "V10 不一致"


def test_validation_failure_maps_to_b3a_reason() -> None:
    """内容検証ポートの拒否理由も T9 へ渡す。"""
    error = P1ContentRejection("禁止された内容")
    assert content_reason_for_precondition(error) == "禁止された内容"


class _LockSpy:
    """R-16 の token 発行順と行列を記録する合成 scope。"""

    def __init__(self) -> None:
        """空の token 列を持つ。"""
        self.calls: list[type[TenantOperationToken]] = []

    def run(self, token: TenantOperationToken) -> TenantOperationResult:
        """試合行と世代行を返し、発行順を記録する。"""
        self.calls.append(type(token))
        if isinstance(token, GameLockToken):
            return TenantOperationResult(((UUID(int=1),),))
        columns = RECORDING_GENERATION_READ_COLUMNS
        cells: list[ImmutableValue] = [None] * len(columns)
        cells[columns.index("generation")] = 1
        cells[columns.index("confirmed_watermark")] = 4
        return TenantOperationResult((tuple(cells),))


def test_rejection_path_locks_game_before_generation() -> None:
    """P5・P4 が共有する局所ロック入口で試合行を先に取る。"""
    spy = _LockSpy()
    assert _lock_game_generation(cast(_TenantTransaction, spy), UUID(int=1)) == (1, 4)
    assert spy.calls == [
        GameLockToken,
        RecordingGenerationReadToken,
        RecordingGenerationLockToken,
    ]


@pytest.mark.parametrize("kind", ("rejected", "evacuated"))
def test_e1_rejection_pure_producer_keeps_raw_envelope_and_event_hash(
    monkeypatch, kind
):
    """閉doubleでT8/T9原本形式を検査する。実binding/実DB成功ではない。"""
    import json
    from typing import Any, cast

    from pitchlog.repositories.tokens import TenantOperationResult
    from pitchlog.sync import rejection
    from pitchlog.sync.model import SyncEvent
    from pitchlog.sync.source_binding import SelectedEventSourceValue, _E1CoreSource
    from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint
    from pitchlog.sync.wire_original import encode_wire_original

    raw = {
        "game_id": "10000000-0000-0000-0000-000000000001",
        "d4": "opaque-epoch",
        "d1": 1,
        "d5": "20000000-0000-0000-0000-000000000001",
        "event_kind": "1",
        "payload": {"observed": None},
        "registration": False,
        "future_unknown": [1, 1.0, -0.0],
    }
    wire = freeze_wire_event(raw)
    digest = wire_event_fingerprint(wire)
    original = encode_wire_original(wire)
    event = SyncEvent(
        raw["d5"], raw["game_id"], 1, raw["d4"], v5="1", v7=raw["payload"]
    )
    selected = SelectedEventSourceValue(
        "e1", 1, digest, "wire-request-v1:raw", wire, original
    )
    source = object.__new__(_E1CoreSource)
    observed = []

    def read(self, scope, actual):
        assert actual is event
        observed.append("read")
        return selected

    def begin(self, scope, actual):
        assert actual is event
        observed.append("begin")

    def ledger(scope, token, path):
        assert token.source_fingerprint == digest
        observed.append("ledger")
        return None

    class Scope:
        def run(self, token):
            observed.append("original")
            assert json.loads(token.payload_json) == json.loads(original)
            return TenantOperationResult(())

    monkeypatch.setattr(_E1CoreSource, "read", read)
    monkeypatch.setattr(_E1CoreSource, "begin_write", begin)
    monkeypatch.setattr(rejection, "recheck_and_insert_result", ledger)
    result = rejection._commit_result_in_scope(
        cast(Any, Scope()),
        event,
        digest,
        0,
        source=source,
        path="P2",
        kind=kind,
        reason="synthetic" if kind == "rejected" else None,
        old_generation=1 if kind == "evacuated" else None,
    )
    assert result.state == ("拒否" if kind == "rejected" else "退避")
    assert observed == ["read", "begin", "ledger", "original"]
