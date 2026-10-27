"""公開入口の DI5・ACK 合成・段階順を DB 不要で検査する。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, cast
from uuid import uuid4

import pytest

from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import apply, crash_points
from pitchlog.sync.idempotency import D5Candidate, operation_fingerprint
from pitchlog.sync.model import AckResult, RejectedChangeResult, SyncEvent, SyncRequest
from pitchlog.sync.ports import (
    ContentValidationPort,
    ProjectionPort,
    RecordingRightsPort,
)
from pitchlog.sync.prefix_path import P1ContentRejection, P1Result
from pitchlog.sync.rejection import RejectionResult
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    RecordingGenerationReadToken,
)


def _request(*d1_values: int) -> SyncRequest:
    """送信順と D1 順を分けられる S-1 の要求を作る。"""
    game = str(uuid4())
    events = tuple(
        SyncEvent(str(uuid4()), game, d1, "1", v5="game_end_declaration", v6=10, v7={})
        for d1 in d1_values
    )
    return SyncRequest("P1", game, events, d4="1", v12="proof")


def _ports() -> tuple[RecordingRightsPort, ProjectionPort, ContentValidationPort]:
    """下位経路を差し替える試験用の不透明なポートを返す。"""
    return (
        cast(RecordingRightsPort, object()),
        cast(ProjectionPort, object()),
        cast(ContentValidationPort, object()),
    )


def test_gap_overrides_preclassified_later_b3b(monkeypatch: pytest.MonkeyPatch) -> None:
    """D3=4・D1=5 欠落なら、6 と既存異内容の 7 は共に未処理。"""
    request = _request(7, 6)
    calls: list[str] = []
    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)

    def preflight(*_args: object) -> apply._BatchPreflight:
        calls.append("classify-all")
        return apply._BatchPreflight(
            4, (D5Candidate("conflict", "B3b"), D5Candidate("unused")), True, 1
        )

    def one_event(*args: object) -> P1Result:
        event = cast(SyncEvent, args[2])
        calls.append(f"apply-{event.d1}")
        return P1Result(None, 5, True)

    monkeypatch.setattr(apply, "_preflight_d1", preflight)
    monkeypatch.setattr(apply, "_run_d1_event", one_event)
    result = apply.apply_sync_request(cast(TenantContext, object()), request, *_ports())
    assert isinstance(result, AckResult)
    assert (result.boundary, result.d3, result.b3_branch) == ("B2", 4, None)
    assert [(row.d1, row.state) for row in result.a5] == [
        (6, "未処理"),
        (7, "未処理"),
    ]
    # ⑥ の欠落は入口が判定し、欠落より後ろは経路へ渡さない(SP 6-2 の ⑥)。
    assert calls == ["classify-all"]


def test_gap_overrides_later_existing_candidate_without_unused_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D3=4 で既存異内容の 7 だけなら、5 の欠落で B2・7 は未処理(B3b にしない)。"""
    request = _request(7)
    calls: list[str] = []
    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)
    monkeypatch.setattr(
        apply,
        "_preflight_d1",
        lambda *_: apply._BatchPreflight(4, (D5Candidate("conflict", "B3b"),), True, 1),
    )

    def one_event(*args: object) -> P1Result:
        calls.append("apply")
        return P1Result("B3b", 4, False)

    monkeypatch.setattr(apply, "_run_d1_event", one_event)
    result = apply.apply_sync_request(cast(TenantContext, object()), request, *_ports())
    assert isinstance(result, AckResult)
    assert (result.boundary, result.d3, result.b3_branch) == ("B2", 4, None)
    assert [(row.d1, row.state) for row in result.a5] == [(7, "未処理")]
    assert calls == []


def test_reversing_d1_walk_fails_gap_oracle(monkeypatch: pytest.MonkeyPatch) -> None:
    """D1 昇順の走査を送信順へ変異させると、B2 のオラクルが落ちる。"""
    request = _request(7, 6)
    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)
    monkeypatch.setattr(
        apply,
        "_preflight_d1",
        lambda *_: apply._BatchPreflight(
            4, (D5Candidate("conflict", "B3b"), D5Candidate("unused")), True, 1
        ),
    )

    def first_event(*args: object) -> P1Result:
        return P1Result(None, 5, True)

    monkeypatch.setattr(apply, "_run_d1_event", first_event)
    # sorted を送信順のまま返す変異。D1 昇順の A5 のオラクルが赤になる。
    monkeypatch.setattr(apply, "sorted", lambda items, key: list(items), raising=False)
    result = apply.apply_sync_request(cast(TenantContext, object()), request, *_ports())
    assert isinstance(result, AckResult)
    with pytest.raises(AssertionError):
        assert [row.d1 for row in result.a5] == [6, 7], "D1 昇順"


def test_first_b3b_stops_before_later_unused(monkeypatch: pytest.MonkeyPatch) -> None:
    """最初の拒否位置の後は未使用候補も外部では未処理にする。"""
    request = _request(2, 1)
    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)
    monkeypatch.setattr(
        apply,
        "_preflight_d1",
        lambda *_: apply._BatchPreflight(
            0, (D5Candidate("unused"), D5Candidate("conflict", "B3b")), True, 1
        ),
    )
    calls: list[int] = []

    def one_event(*args: object) -> P1Result:
        event = cast(SyncEvent, args[2])
        assert event.d1 is not None
        calls.append(event.d1)
        return P1Result("B3b", 0, False)

    monkeypatch.setattr(apply, "_run_d1_event", one_event)
    result = apply.apply_sync_request(cast(TenantContext, object()), request, *_ports())
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch) == ("B3", "B3b")
    assert result.reason == "同じ D5 の内容が異なる"
    assert [(row.d1, row.state) for row in result.a5] == [
        (1, "拒否"),
        (2, "未処理"),
    ]
    assert calls == [1]


def test_auth_before_rg1_and_d5_has_no_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    """他テナントと不存在の両方で、後段を読まず B6 だけを返す。"""
    request = _request(6)
    monkeypatch.setattr(apply, "game_accessible", lambda *_: False)

    def forbidden(*_args: object) -> None:
        raise AssertionError("③より後の段階へ進んだ")

    monkeypatch.setattr(apply, "_preflight_d1", forbidden)
    assert (
        apply.apply_sync_request(cast(TenantContext, object()), request, *_ports())
        == "B6"
    )


def test_p3_delegates_without_d1_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    """P3 の独立結果は D1 の ACK へ写さない。"""
    game = str(uuid4())
    event = SyncEvent(str(uuid4()), game, v5="play_change", v7={})
    request = SyncRequest("P3", game, (event,), recovery_generation="current")
    expected = RejectedChangeResult("B12", event.d5)
    monkeypatch.setattr(apply, "apply_p3_change", lambda *_: expected)
    assert (
        apply.apply_sync_request(cast(TenantContext, object()), request, *_ports())
        is expected
    )


def test_content_rejection_routes_to_t9(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑦の恒久拒否を一度だけ T9 へ渡して B3a にする。"""
    request = _request(1)
    event = request.events[0]
    monkeypatch.setattr(
        apply,
        "apply_p1_event",
        lambda *_args, **_kw: (_ for _ in ()).throw(P1ContentRejection("内容不正")),
    )
    observed: list[tuple[str | None, str]] = []

    def save(*_args: object, **kwargs: object) -> RejectionResult:
        observed.append(
            (cast(str | None, kwargs["reason"]), cast(str, kwargs["cause"]))
        )
        return RejectionResult("B3a", 0, "拒否", "内容不正")

    monkeypatch.setattr(apply, "apply_rejection_or_escrow", save)
    result = apply._run_d1_event(
        cast(TenantContext, object()), request, event, *_ports(), None, None
    )
    assert result == RejectionResult("B3a", 0, "拒否", "内容不正")
    assert observed == [("内容不正", "content_rejection")]


def test_w2_violation_routes_to_t9_with_distinct_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """拒否原本との不一致を B3a/T9 へ渡し、他の前提違反と混ぜない。"""
    request = _request(1)
    event = request.events[0]

    def reject(*_args: object, **_kwargs: object) -> P1Result:
        raise apply.P1PreconditionError("拒否原本の対象不一致", "w2_violation")

    observed: list[tuple[str | None, str]] = []

    def save(*_args: object, **kwargs: object) -> RejectionResult:
        observed.append(
            (cast(str | None, kwargs["reason"]), cast(str, kwargs["cause"]))
        )
        return RejectionResult("B3a", 0, "拒否", "拒否原本の対象不一致")

    monkeypatch.setattr(apply, "apply_p1_event", reject)
    monkeypatch.setattr(apply, "apply_rejection_or_escrow", save)
    result = apply._run_d1_event(
        cast(TenantContext, object()), request, event, *_ports(), None, None
    )
    assert result.boundary == "B3a"
    assert observed == [("拒否原本の対象不一致", "w2_violation")]


def test_preflight_classifies_with_operation_fingerprint_before_rights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全件の④は同じ内容同一性を使い、⑤より先に終わる。"""
    request = _request(2, 1)
    observed: list[str] = []
    columns = RECORDING_GENERATION_READ_COLUMNS
    # 要求の D4 = 1 と同じ現世代の行(旧 D4 の要求ではないので要求世代の read は無い)。
    values = {"confirmed_watermark": 4, "generation": 1}
    row = tuple(values.get(name, 0) for name in columns)

    class Scope:
        """記録権世代 read だけを実体化する。"""

        def run(self, token: object) -> TenantOperationResult:
            """登録済み read token を観測する。"""
            assert isinstance(token, RecordingGenerationReadToken)
            observed.append("read-d3")
            return TenantOperationResult((row,))

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        yield cast(_TenantTransaction, Scope())

    @contextmanager
    def fake_gate(_scope: object, _rights: object) -> Iterator[object]:
        observed.append("rg1")
        yield type("Writer", (), {"writer": object()})()

    def classify(
        _scope: object, _request: SyncRequest, fingerprints: tuple[str, ...]
    ) -> tuple[D5Candidate, ...]:
        observed.append("classify-all")
        assert fingerprints == tuple(
            operation_fingerprint(event, "P1", None) for event in request.events
        )
        return D5Candidate("unused"), D5Candidate("conflict", "B3b")

    class Rights:
        """⑤が④の後に呼ばれたかだけを観測する。"""

        def holds_recording_right(self, *_args: object) -> bool:
            observed.append("rights")
            return True

    monkeypatch.setattr(apply, "tenant_transaction_scope", fake_scope)
    monkeypatch.setattr(apply, "gated_writer", fake_gate)
    monkeypatch.setattr(apply, "classify_request_d5", classify)
    monkeypatch.setattr(apply.port_guard, "require_registered_port", lambda *_: None)
    result = apply._preflight_d1(
        cast(TenantContext, object()), request, cast(RecordingRightsPort, Rights()), {}
    )
    assert result.d3 == 4 and result.has_recording_right
    assert observed == ["rg1", "classify-all", "read-d3", "rights"]


@pytest.mark.parametrize(
    "point", ["after_t1_ledger", "after_t8_ledger", "after_t9_original"]
)
def test_named_crash_hook_is_scoped_and_raises(point: crash_points.CrashPoint) -> None:
    """注入点の例外は伝播し、試験文脈を出れば製品動作に戻る。"""

    def crash(name: crash_points.CrashPoint) -> None:
        if name == point:
            raise RuntimeError("電源断")

    with crash_points.testing_crash_hook(crash):
        with pytest.raises(RuntimeError, match="電源断"):
            crash_points.reach(point)
    crash_points.reach(point)
