"""公開入口の DI5・ACK 合成・段階順を DB 不要で検査する。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, cast
from uuid import UUID, uuid4

import pytest

from pitchlog.db.recording_rights.models import RecordingGeneration
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import apply, crash_points, ordering, prefix_path
from pitchlog.sync.idempotency import D5Candidate, operation_fingerprint
from pitchlog.sync.model import AckResult, RejectedChangeResult, SyncEvent, SyncRequest
from pitchlog.sync.ports import (
    ContentValidationPort,
    ProjectionPort,
    RecordingRightsPort,
)
from pitchlog.sync.prefix_path import (
    P1ContentRejection,
    P1Result,
    P1Target,
    PlayerRegistration,
)
from pitchlog.sync.rejection import RejectionResult
from pitchlog.sync.tokens import (
    RecordingGenerationByNumberReadToken,
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


@pytest.mark.parametrize("reverse", [False, True])
def test_b4_duplicate_d5_keeps_candidates_by_d1(
    monkeypatch: pytest.MonkeyPatch, reverse: bool
) -> None:
    """同じ D5 の再掲と異内容を入力順によらず区別し、未使用だけ退避する。"""
    request = _request(1, 2, 3)
    saved = request.events[0]
    conflict = SyncEvent(saved.d5, request.game_id, 2, "1", v5="undo", v7={})
    unused = request.events[2]
    events = (conflict, saved, unused) if reverse else (saved, conflict, unused)
    request = SyncRequest("P1", request.game_id, events, d4="1", v12="proof")
    kinds = {
        1: D5Candidate("stored_result"),
        2: D5Candidate("conflict", "B3b"),
        3: D5Candidate("unused"),
    }
    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)
    monkeypatch.setattr(
        apply,
        "_preflight_d1",
        lambda *_: apply._BatchPreflight(
            1, tuple(kinds[cast(int, event.d1)] for event in events), False, 1
        ),
    )
    calls: list[tuple[str, int]] = []

    def replay(*args: object) -> P1Result:
        event = cast(SyncEvent, args[2])
        assert event.d1 is not None
        calls.append(("replay", event.d1))
        return P1Result(None, 1, True, replayed=True)

    def escrow(*args: object) -> RejectionResult:
        event = cast(SyncEvent, args[2])
        assert event.d1 is not None
        calls.append(("escrow", event.d1))
        return RejectionResult("B4", 1, "退避")

    monkeypatch.setattr(apply, "_replay_existing", replay)
    monkeypatch.setattr(apply, "_escrow_without_right", escrow)
    result = apply.apply_sync_request(cast(TenantContext, object()), request, *_ports())
    assert isinstance(result, AckResult)
    assert (result.boundary, result.d3, result.b3_branch) == ("B4", 1, None)
    assert [(row.d1, row.state, row.reason) for row in result.a5] == [
        (1, "重複", None),
        (2, "未処理", None),
        (3, "退避", None),
    ]
    assert calls == [("replay", 1), ("escrow", 3)]


@pytest.mark.parametrize("reverse", [False, True])
def test_escrowed_duplicate_d5_retry_skips_rights_and_stops_at_b3b(
    monkeypatch: pytest.MonkeyPatch, reverse: bool
) -> None:
    """初回の退避で未使用 D5 が消えた再送は、⑤を通らず⑥で B3b になる。"""
    base = _request(1, 2, 3)
    saved = base.events[0]
    conflict = SyncEvent(saved.d5, base.game_id, 2, "1", v5="undo", v7={})
    unused = base.events[2]
    events = (conflict, saved, unused) if reverse else (saved, conflict, unused)
    request = SyncRequest("P1", base.game_id, events, d4="1", v12="old-proof")
    columns = tuple(RecordingGeneration.__table__.c.keys())

    def generation_row(d3: int, generation: int) -> tuple[int, ...]:
        values = {"confirmed_watermark": d3, "generation": generation}
        return tuple(values.get(column, 0) for column in columns)

    class Scope:
        """現世代と要求の旧世代の D3 を返す偽スコープ。"""

        def run(self, token: object) -> TenantOperationResult:
            """必要な記録権世代の読み取りだけを受ける。"""
            if isinstance(token, RecordingGenerationReadToken):
                return TenantOperationResult((generation_row(0, 2),))
            assert isinstance(token, RecordingGenerationByNumberReadToken)
            return TenantOperationResult((generation_row(1, 1),))

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        yield cast(_TenantTransaction, Scope())

    @contextmanager
    def fake_gate(_scope: object, _rights: object) -> Iterator[object]:
        yield type("Writer", (), {"writer": object()})()

    escrowed = False
    classified = 0

    def classify(
        _scope: object, incoming: SyncRequest, _fingerprints: tuple[str, ...]
    ) -> tuple[D5Candidate, ...]:
        nonlocal classified
        classified += 1
        by_d1 = {
            1: D5Candidate("stored_result"),
            2: D5Candidate("conflict", "B3b"),
            3: D5Candidate("stored_result" if escrowed else "unused"),
        }
        return tuple(by_d1[cast(int, event.d1)] for event in incoming.events)

    class Rights:
        """⑤ の呼び出し回数と判定を記録する。"""

        def __init__(self) -> None:
            self.calls = 0

        def holds_recording_right(self, *_args: object) -> bool:
            self.calls += 1
            return False

    rights = Rights()

    def replay(*_args: object) -> P1Result:
        return P1Result(None, 1, True, replayed=True)

    def escrow(*_args: object) -> RejectionResult:
        nonlocal escrowed
        escrowed = True
        return RejectionResult("B4", 1, "退避")

    def one_event(*args: object) -> P1Result:
        event = cast(SyncEvent, args[2])
        if event.d1 == 1:
            return replay()
        assert event.d1 == 2
        return P1Result("B3b", 1, False)

    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)
    monkeypatch.setattr(apply, "tenant_transaction_scope", fake_scope)
    monkeypatch.setattr(apply, "gated_writer", fake_gate)
    monkeypatch.setattr(apply, "classify_request_d5", classify)
    monkeypatch.setattr(apply.port_guard, "require_registered_port", lambda *_: None)
    monkeypatch.setattr(apply, "_replay_existing", replay)
    monkeypatch.setattr(apply, "_escrow_without_right", escrow)
    monkeypatch.setattr(apply, "_run_d1_event", one_event)

    first = apply.apply_sync_request(
        cast(TenantContext, object()),
        request,
        cast(RecordingRightsPort, rights),
        *_ports()[1:],
    )
    assert isinstance(first, AckResult)
    assert (first.boundary, first.d3, first.b3_branch) == ("B4", 1, None)
    assert [(row.d1, row.state) for row in first.a5] == [
        (1, "重複"),
        (2, "未処理"),
        (3, "退避"),
    ]
    resent = apply.apply_sync_request(
        cast(TenantContext, object()),
        request,
        cast(RecordingRightsPort, rights),
        *_ports()[1:],
    )
    assert isinstance(resent, AckResult)
    assert (resent.boundary, resent.d3, resent.b3_branch) == ("B3", 1, "B3b")
    assert [(row.d1, row.state) for row in resent.a5] == [
        (1, "重複"),
        (2, "拒否"),
        (3, "未処理"),
    ]
    assert classified == 2
    assert rights.calls == 1


def test_duplicate_d5_uses_each_d1_registration_and_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D5 が同じ 2 件にも別々の登録値と解決済み対象を渡す。"""
    request = _request(2, 1)
    shared_d5 = request.events[0].d5
    events = tuple(
        SyncEvent(shared_d5, request.game_id, d1, "1", v5="undo", v7={})
        for d1 in (2, 1)
    )
    request = SyncRequest("P1", request.game_id, events, d4="1", v12="proof")
    registrations = {
        d1: PlayerRegistration(uuid4(), uuid4(), f"登録{d1}", "active") for d1 in (1, 2)
    }
    targets = {d1: P1Target(uuid4(), 1, d1) for d1 in (1, 2)}
    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)
    monkeypatch.setattr(
        apply,
        "_preflight_d1",
        lambda *_: apply._BatchPreflight(
            0, (D5Candidate("unused"), D5Candidate("unused")), True, 1
        ),
    )
    seen: list[tuple[int, PlayerRegistration | None, P1Target | None]] = []

    def one_event(*args: object) -> P1Result:
        event = cast(SyncEvent, args[2])
        assert event.d1 is not None
        seen.append(
            (
                event.d1,
                cast(PlayerRegistration | None, args[6]),
                cast(P1Target | None, args[7]),
            )
        )
        return P1Result(None, event.d1, True)

    monkeypatch.setattr(apply, "_run_d1_event", one_event)
    result = apply.apply_sync_request(
        cast(TenantContext, object()),
        request,
        *_ports(),
        registrations=registrations,
        targets=targets,
    )
    assert isinstance(result, AckResult)
    assert [(d1, registration, target) for d1, registration, target in seen] == [
        (d1, registrations[d1], targets[d1]) for d1 in (1, 2)
    ]


def test_duplicate_d5_rejects_legacy_d5_keyed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧 D5 キーは黙って別の D1 に適用せず、入口で拒む。"""
    request = _request(1, 2)
    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)
    registration = PlayerRegistration(uuid4(), uuid4(), "登録", "active")
    with pytest.raises(TypeError, match="D1 をキー"):
        apply.apply_sync_request(
            cast(TenantContext, object()),
            request,
            *_ports(),
            registrations=cast(
                dict[int, PlayerRegistration], {request.events[0].d5: registration}
            ),
        )
    target = P1Target(uuid4(), 1, 1)
    with pytest.raises(TypeError, match="D1 をキー"):
        apply.apply_sync_request(
            cast(TenantContext, object()),
            request,
            *_ports(),
            targets=cast(dict[int, P1Target], {request.events[0].d5: target}),
        )


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


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("reference_type", "選手参照は UUID 文字列が必要"),
        ("reference_parse", "選手参照は UUID 文字列が必要"),
        ("reference_canonical", "選手参照は正規 UUID が必要"),
        ("reference_field", "V5 で定義されない選手参照位置"),
        ("v6_range", "P2 の V6 は非負の bigint が必要"),
    ],
)
def test_d5_content_sites_route_b3a_to_t9(
    monkeypatch: pytest.MonkeyPatch, case: str, reason: str
) -> None:
    """D-5 の内容だけで決まる各例外を T9 の理由と B3a へ渡す。"""
    request = _request(1)
    event = request.events[0]

    def reject(*_args: object, **_kwargs: object) -> P1Result:
        """実際の内容検査を起動し、各 raise 文を通す。"""
        if case == "v6_range":
            ordering._assign_d2(
                cast(_TenantTransaction, object()), UUID(event.game_id), 2**63
            )
        else:
            payload: dict[str, object]
            if case == "reference_type":
                payload = {"player_id": 1}
            elif case == "reference_parse":
                payload = {"player_id": "invalid-uuid"}
            elif case == "reference_canonical":
                payload = {"player_id": str(uuid4()).upper()}
            else:
                payload = {"batter_id": str(uuid4())}
            prefix_path._resolve_payload(
                cast(_TenantTransaction, object()),
                payload,
                "game_end_declaration",
                {},
                {},
            )
        raise AssertionError("内容拒否に到達しなかった")

    with pytest.raises(P1ContentRejection, match=reason):
        reject()
    saved: list[tuple[SyncEvent, str | None, str]] = []

    def save(*args: object, **kwargs: object) -> RejectionResult:
        """T9 の保存呼び出しに原本・理由・区分が届くことを確かめる。"""
        saved.append(
            (
                cast(SyncEvent, args[1]),
                cast(str | None, kwargs["reason"]),
                cast(str, kwargs["cause"]),
            )
        )
        return RejectionResult("B3a", 0, "拒否", reason)

    monkeypatch.setattr(apply, "apply_p1_event", reject)
    monkeypatch.setattr(apply, "apply_rejection_or_escrow", save)
    result = apply._run_d1_event(
        cast(TenantContext, object()), request, event, *_ports(), None, None
    )
    assert result == RejectionResult("B3a", 0, "拒否", reason)
    assert saved == [(event, reason, "content_rejection")]


def test_other_precondition_and_unknown_runtime_do_not_start_t9(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """永続状態依存と原因不明の失敗は T9 へ変換しない。"""
    request = _request(1)
    event = request.events[0]
    calls: list[str] = []

    def save(*_args: object, **_kwargs: object) -> RejectionResult:
        """誤って拒否原本を保存した場合に失敗させる。"""
        calls.append("T9")
        raise AssertionError("T9 を開始してはいけない")

    monkeypatch.setattr(apply, "apply_rejection_or_escrow", save)
    for failure in (
        apply.P1PreconditionError("永続状態に依存", "other"),
        RuntimeError("原因不明"),
    ):

        def fail(*_args: object, **_kwargs: object) -> P1Result:
            """B7 側に残す例外を局所経路から返す。"""
            raise failure

        monkeypatch.setattr(apply, "apply_p1_event", fail)
        with pytest.raises(type(failure), match=str(failure)):
            apply._run_d1_event(
                cast(TenantContext, object()), request, event, *_ports(), None, None
            )
    assert calls == []


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
    """④の指紋は同じ D5 の各 D1 の登録値を使い、⑤より先に作る。"""
    request = _request(2, 1)
    first = request.events[0]
    second = SyncEvent(
        first.d5, request.game_id, 1, "1", v5="game_end_declaration", v6=10, v7={}
    )
    request = SyncRequest("P1", request.game_id, (first, second), d4="1", v12="proof")
    registrations = {
        d1: PlayerRegistration(uuid4(), uuid4(), f"登録{d1}", "active") for d1 in (1, 2)
    }
    observed: list[str] = []
    columns = tuple(RecordingGeneration.__table__.c.keys())
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
            operation_fingerprint(event, "P1", registrations[cast(int, event.d1)])
            for event in request.events
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
        cast(TenantContext, object()),
        request,
        cast(RecordingRightsPort, Rights()),
        registrations,
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
