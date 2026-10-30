"""binding 前の D5 先行分類（DI1/DI2/DI3）の閉入力を固定する。

実DB・実writer・実権利の成立はここで主張しない。外形の拒否だけを見る。
"""

from types import MappingProxyType
from typing import cast
from uuid import uuid4

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.sync.apply import _replay_e1_without_binding
from pitchlog.sync.model import AckResult, SyncEvent, SyncRequest
from pitchlog.sync.source_binding import SourceBindingError

_D4 = "d4.1.example"


def _digest() -> str:
    """wire-v1形式の閉じた指紋。"""
    return "wire-v1:" + "a" * 64


def _p2(*, count: int = 1, d1: int = 1) -> SyncRequest:
    """S-1外形に合うP2要求を作る（D1は重複させない）。"""
    game = str(uuid4())
    return SyncRequest(
        "P2",
        game,
        tuple(
            SyncEvent(
                d5=str(uuid4()),
                game_id=game,
                d1=d1 + index,
                d4=_D4,
                v5="1",
                v7={},
                v8={},
            )
            for index in range(count)
        ),
        d4=_D4,
    )


def _p3() -> SyncRequest:
    """P3外形の要求を作る（再掲の対象外であることを確かめる）。"""
    game = str(uuid4())
    return SyncRequest(
        "P3",
        game,
        (SyncEvent(d5=str(uuid4()), game_id=game),),
        recovery_generation=_D4,
    )


def test_missing_integrity_proof_is_rejected() -> None:
    """実認証の証跡が無い文脈を再掲へ使わない。"""
    forged = object.__new__(type(make_tenant_context(uuid4())))
    with pytest.raises(SourceBindingError):
        _replay_e1_without_binding(forged, _p2(), (_digest(),))


@pytest.mark.parametrize(
    "fingerprints",
    [(), (_digest(), _digest()), (_digest(), ""), (_digest(), 1), "x"],
)
def test_mismatched_fingerprints_are_rejected(fingerprints: object) -> None:
    """要求と指紋の件数・型が違う入力を再掲へ流さない。"""
    with pytest.raises(SourceBindingError):
        _replay_e1_without_binding(
            make_tenant_context(uuid4()),
            _p2(),
            cast(tuple[str, ...], fingerprints),  # 意図的不正入力を補修せず渡す。
        )


def test_multi_event_and_p3_are_left_to_the_existing_out_of_scope() -> None:
    """単球F1の範囲外は再掲で判定せず、既存の範囲外拒否へ戻す。"""
    context = make_tenant_context(uuid4())
    assert (
        _replay_e1_without_binding(context, _p2(count=2), (_digest(), _digest()))
        is None
    )
    assert _replay_e1_without_binding(context, _p3(), (_digest(),)) is None


@pytest.mark.parametrize("d1,current_d3", [(1, 1), (2, 2), (99, 99), (1, 3), (2, 3)])
@pytest.mark.parametrize("kind", ["unused", "stored_result", "conflict"])
def test_positive_d1_classifies_saved_d5_before_any_binding(
    monkeypatch, d1, current_d3, kind
):
    """通常後続単球も同じD5分類を再利用し、未使用だけ通常段へ戻す。"""
    from contextlib import contextmanager

    from pitchlog.repositories import rg1
    from pitchlog.repositories.tokens import TenantOperationResult
    from pitchlog.sync import apply, idempotency
    from pitchlog.sync.idempotency import D5Candidate, StoredResult
    from pitchlog.sync.tokens import (
        RECORDING_GENERATION_READ_COLUMNS,
        RecordingGenerationReadToken,
    )

    request = _p2(d1=d1)
    context = make_tenant_context(uuid4())
    seen = []

    class Scope:
        """D3一点のみ合成し、writer関数は提供しない。"""

        def run(self, token):
            """実原本照会の代替合成。実DB成立とは別。"""
            assert type(token) is RecordingGenerationReadToken
            seen.append("D3")
            values = {"confirmed_watermark": current_d3}
            return TenantOperationResult(
                (tuple(values.get(key) for key in RECORDING_GENERATION_READ_COLUMNS),)
            )

    @contextmanager
    def scope(context):
        yield Scope()

    def classify(handle, d5, fingerprint, path):
        seen.append("D5")
        assert (
            str(d5) == request.events[0].d5
            and fingerprint == _digest()
            and path == "P2"
        )
        if kind == "stored_result":
            return D5Candidate(
                kind,
                stored=StoredResult(
                    "accepted",
                    _digest(),
                    {
                        "state": "受理",
                        "d3": d1,
                        "temporary_id_mapping": MappingProxyType({}),
                    },
                    None,
                ),
            )
        return D5Candidate(kind, "B3b" if kind == "conflict" else None)

    monkeypatch.setattr(apply, "game_accessible", lambda *args: True)
    monkeypatch.setattr(apply, "tenant_transaction_scope", scope)
    monkeypatch.setattr(rg1, "read_rg1_open", lambda scope: seen.append("RG1"))
    monkeypatch.setattr(idempotency, "classify_d5", classify)
    result = _replay_e1_without_binding(context, request, (_digest(),))
    assert seen == ["RG1", "D3", "D5"]
    if kind == "unused":
        assert result is None
    else:
        assert isinstance(result, AckResult)
        assert result.d3 == current_d3
        assert result.a5[0].d1 == d1
        assert result.a5[0].state == ("重複" if kind == "stored_result" else "拒否")
