"""binding 前の D5 先行分類（DI1/DI2/DI3）の閉入力を固定する。

実DB・実writer・実権利の成立はここで主張しない。外形の拒否だけを見る。
"""

from typing import cast
from uuid import uuid4

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.sync.apply import _replay_e1_without_binding
from pitchlog.sync.model import SyncEvent, SyncRequest
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
