"""公開入口の DI5・ACK 合成・段階順を DB 不要で検査する。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, cast
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
    from test_authz_tenant_context import make_tenant_context

    result = apply._preflight_d1(
        make_tenant_context(uuid4()), request, cast(RecordingRightsPort, Rights()), {}
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


@contextmanager
def _e1_private_flow_double(monkeypatch, mode="accepted", *, device_active=True):
    """私有registry/controllerのpure double。HTTP/実PG/本物資格ではない。"""
    import json
    from types import SimpleNamespace
    from uuid import UUID

    import test_sync_apply_source_binding as source_test

    from pitchlog.repositories import rg1
    from pitchlog.sync import prefix_path, rejection
    from pitchlog.sync import source_binding as source
    from pitchlog.sync.control_provider import binding_control, writer_binding
    from pitchlog.sync.control_provider.evidence import (
        AttemptBinding,
        AuthorityBinding,
        EventPhaseBinding,
    )

    receipt, request = source_test._receipt_double(source_test._raw())
    state = source._RECEIPTS[receipt]
    request = SyncRequest("P2", request.game_id, request.events, d4=request.d4)
    state.request = request
    state.request_json = source._request_json(request)
    phase = EventPhaseBinding(
        AttemptBinding(
            AuthorityBinding(UUID(int=1), UUID(int=2), UUID(int=3)),
            state.tenant_id,
            UUID(int=5),
            UUID(request.game_id),
            cast(str, request.d4),
            1,
            UUID(int=7),
            1,
            state.source.request_fingerprint,
            1,
        ),
        UUID(int=8),
        1,
        1,
        UUID(request.events[0].d5),
        state.source.event_fingerprints[0],
    )
    snapshot = json.dumps(
        {
            "tenant_id": str(state.tenant_id),
            "phase": binding_control._phase_wire(phase, UUID(int=10), 1),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    trace = []
    scope = SimpleNamespace(_context=state.context)
    bound = object.__new__(writer_binding._LiveWriterBinding)
    bound._used = False
    bound._owner = (object(),)
    bound._handle = scope
    bound._lease = cast(
        Any,
        SimpleNamespace(
            _phase_snapshot=snapshot,
            device_id=phase.attempt.device_id,
            game_id=phase.attempt.game_id,
        ),
    )
    bound._phase_snapshot = snapshot
    writer_binding._LIVE_BINDINGS[bound._owner[0]] = bound

    @contextmanager
    def open_scope(context):
        assert context is state.context
        trace.append("tx-open")
        try:
            yield scope
        except BaseException:
            trace.append("rollback")
            raise
        else:
            trace.append("commit")

    @contextmanager
    def gate(actual, rights):
        assert actual is scope
        trace.append("rg1-port")
        gated = SimpleNamespace(writer=object(), written=False)

        def mark():
            trace.append("mark-written")
            gated.written = True

        gated.mark_written = mark
        yield gated
        if gated.written:
            trace.append("rg1-commit")

    def preflight(*args, source):
        trace.append("d5-read")
        candidate = D5Candidate("unused")
        return apply._BatchPreflight(0, (candidate,), mode != "t8", 1)

    def reject(*args, **kwargs):
        trace.append("t8-t9")
        proof = kwargs["source"]
        proof.begin_write(scope, request.events[0])
        return RejectionResult(
            "B4" if mode == "t8" else "B3a",
            0,
            "退避" if mode == "t8" else "拒否",
            "synthetic",
        )

    def accepted(*args, **kwargs):
        trace.append("event")
        if mode == "t9":
            raise P1ContentRejection("synthetic")
        if mode == "replay":
            return P1Result(None, 1, True, True)
        kwargs["source"].begin_write(scope, request.events[0])
        if mode == "post-write-error":
            from pitchlog.sync.prefix_path import P1PreconditionError

            raise P1PreconditionError("synthetic after write", "recording_rights")
        return P1Result(None, 1, True)

    def read_device(*args):
        trace.append("device-read")
        return device_active

    def game_access(*args):
        trace.append("game-read")
        return True

    def bind(self, *args, **kwargs):
        trace.append("bind")
        return bound

    def verify(*args):
        trace.append("device-recheck")
        return True

    monkeypatch.setattr(apply, "tenant_transaction_scope", open_scope)
    monkeypatch.setattr(apply, "gated_e1_writer", gate)
    monkeypatch.setattr(apply, "_read_reference_device_state", read_device)
    monkeypatch.setattr(apply, "game_accessible", game_access)
    monkeypatch.setattr(rg1, "read_rg1_open", lambda scope: trace.append("rg1-core"))
    monkeypatch.setattr(binding_control.BindingControl, "bind_writer", bind)
    monkeypatch.setattr(
        writer_binding._LiveWriterBinding, "assert_current", lambda self: None
    )
    monkeypatch.setattr(writer_binding, "_recheck_bound_device", verify)
    monkeypatch.setattr(apply, "_preflight_in_scope", preflight)
    monkeypatch.setattr(prefix_path, "_apply_locked_in_scope", accepted)
    monkeypatch.setattr(rejection, "_apply_rejection_in_scope", reject)
    control = object.__new__(binding_control.BindingControl)
    args = (receipt, state.context, request)
    kwargs = {
        "phase": phase,
        "cookie": "synthetic-cookie",
        "reference_device": phase.attempt.device_id,
        "control": control,
        "rights": object(),
        "projection": object(),
        "validator": object(),
    }
    try:
        yield args, kwargs, trace, bound
    finally:
        writer_binding._LIVE_BINDINGS.pop(bound._owner[0], None)
        source._RECEIPTS.clear()
        source._SELECTIONS.clear()


@pytest.mark.parametrize("mode", ("accepted", "t8", "t9", "replay"))
def test_e1_private_flow_double_marks_written_exactly_once(monkeypatch, mode):
    """同gatedの⑧は受理/T8/T9各1回、再掲0回というdriver条件を固定する。"""
    with _e1_private_flow_double(monkeypatch, mode) as (args, kwargs, trace, bound):
        result = apply._apply_e1_f1(*args, **kwargs)
        assert isinstance(result, AckResult)
        count = 0 if mode == "replay" else 1
        assert trace.count("mark-written") == trace.count("rg1-commit") == count
        assert trace.count("tx-open") == trace.count("bind") == 1
        assert trace[-1] == "commit"
        assert (
            trace.index("device-read")
            < trace.index("game-read")
            < trace.index("bind")
            < trace.index("d5-read")
        )


def test_e1_device_false_before_game_or_binding(monkeypatch):
    """②の不成立では他の読み取り/lease/業務TXを開始しない。"""
    with _e1_private_flow_double(monkeypatch, device_active=False) as (
        args,
        kwargs,
        trace,
        bound,
    ):
        assert apply._apply_e1_f1(*args, **kwargs) == "B5"
        assert trace == ["device-read"]


@pytest.mark.parametrize("mismatch", ("device", "game", "both"))
def test_e1_bound_context_mismatch_rolls_back_before_recheck(monkeypatch, mismatch):
    """二段照合のa/b不一致は実DB再照合0、両不一致はB5先。"""
    from uuid import UUID

    with _e1_private_flow_double(monkeypatch) as (args, kwargs, trace, bound):
        if mismatch in ("device", "both"):
            kwargs["reference_device"] = UUID(int=90)
        if mismatch in ("game", "both"):
            bound._lease.game_id = UUID(int=91)
        expected = "B6" if mismatch == "game" else "B5"
        assert apply._apply_e1_f1(*args, **kwargs) == expected
        assert "device-recheck" not in trace and "d5-read" not in trace
        assert trace[-1] == "rollback"


def test_e1_after_write_exception_does_not_branch_to_t8(monkeypatch):
    """最初の書込marker後の権利例外は全体rollbackしT8へ分岐しない。"""
    from pitchlog.sync.prefix_path import P1PreconditionError

    with _e1_private_flow_double(monkeypatch, "post-write-error") as (
        args,
        kwargs,
        trace,
        bound,
    ):
        with pytest.raises(P1PreconditionError, match="synthetic after write"):
            apply._apply_e1_f1(*args, **kwargs)
        assert "t8-t9" not in trace
        assert trace[-1] == "rollback"
        assert "rg1-commit" not in trace
