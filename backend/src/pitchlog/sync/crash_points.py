"""同期適用の名前付き故障注入点を定義する。

通常の製品実行では何もしない。試験は一つの実行文脈にだけ hook を設置し、
各 T 要素の保存境界で例外を送出して原子性を観測できる。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

type CrashPoint = Literal[
    "before_transaction",
    "after_transaction",
    "after_t1_ledger",
    "after_t2_event",
    "after_t3_prefix",
    "after_t4_projection",
    "after_t5_order",
    "after_t6_result",
    "before_t6_mapping",
    "after_t6_mapping",
    "after_d1_intents",
    "after_t7_intents",
    "after_t8_ledger",
    "after_t8_original",
    "after_t9_ledger",
    "after_t9_original",
]

_CRASH_HOOK: ContextVar[Callable[[CrashPoint], None] | None] = ContextVar(
    "sync_crash_hook", default=None
)


def reach(point: CrashPoint) -> None:
    """試験が設置した hook だけを呼ぶ。"""
    hook = _CRASH_HOOK.get()
    if hook is not None:
        hook(point)


@contextmanager
def testing_crash_hook(hook: Callable[[CrashPoint], None]) -> Iterator[None]:
    """試験の実行文脈に限って故障 hook を設置し、終了時に戻す。"""
    token = _CRASH_HOOK.set(hook)
    try:
        yield
    finally:
        _CRASH_HOOK.reset(token)
