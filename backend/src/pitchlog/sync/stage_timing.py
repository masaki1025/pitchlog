"""同期POSTの段階別サーバー計測（既定無効、秘密を出さない）。

``PITCHLOG_SYNC_STAGE_TIMING=1`` のときだけ、1要求の段階別所要を
``PITCHLOG_SYNC_STAGE_TIMING=`` で始まる1行JSONとして標準エラーへ出す。
応答には同じ集計を ``Server-Timing`` ヘッダとして付ける。

記録するのは固定の段階名・件数・マイクロ秒だけであり、cookie・端末資格・
V12・要求本文・tenant/game識別子・例外本文は保持も出力もしない。計測は
NFR-002 の5秒判定の代用ではなく、5秒判定は実時間のまま維持する。
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any

ENV_VARIABLE = "PITCHLOG_SYNC_STAGE_TIMING"
_LOG_PREFIX = ENV_VARIABLE + "="
_OTHER = "other"

# 出力できる段階名を固定する。要求由来の値を名前へ混ぜない。
_STAGE_NAMES = frozenset(
    {
        "assert_current",
        "auth",
        "body_parse",
        "binding_close",
        "commit",
        "config",
        "content_eval",
        "device_state",
        "device_verify",
        "fence_assert",
        "game_accessible",
        "host_call",
        "host_close",
        "host_open",
        "ledger_binding_open",
        "lease_check",
        "live_bind_check",
        "main_tx_close",
        "main_tx_open",
        "phase_check",
        "precommit_writer_check",
        "preflight_d5",
        "play_export",
        "play_export_identity",
        "play_export_project",
        "play_export_save",
        "play_export_substitutes",
        "projection",
        "replay",
        "response",
        "rg1_commit_check",
        "rg1_precheck",
        "route_body",
        "route_entry",
        "selected_source_derive",
        "session_close",
        "source_read",
        "stats_flush",
        "stats_prepare",
        "stats_read_writer_state",
        "stats_save_source",
        "stats_source",
        "stats_source_read_values",
        "tx_enter",
        "write_ledger",
        "writer_bind",
        "writer_identity",
        _OTHER,
    }
)

_CURRENT: ContextVar[SyncStageTimer | None] = ContextVar(
    "pitchlog_sync_stage_timer", default=None
)


@dataclass(slots=True)
class _Aggregate:
    """同一段階の反復を件数・合計・最大・初回位置へ集約する。"""

    count: int = 0
    total_us: int = 0
    max_us: int = 0
    first_start_us: int = 0
    details: dict[str, int] | None = None


class SyncStageTimer:
    """1要求分の段階計測だけを保持する。値・本文・secretを持たない。"""

    __slots__ = ("_start_ns", "_order", "_stages")

    def __init__(self) -> None:
        """要求受付時刻から計測を開始する。"""
        self._start_ns = perf_counter_ns()
        self._order: list[str] = []
        self._stages: dict[str, _Aggregate] = {}

    def record(
        self, name: str, start_ns: int, end_ns: int, detail: str | None = None
    ) -> None:
        """固定段階名の所要を加算する。未知の名前は``other``へ寄せる。"""
        stage_name = name if name in _STAGE_NAMES else _OTHER
        aggregate = self._stages.get(stage_name)
        if aggregate is None:
            aggregate = _Aggregate(first_start_us=(start_ns - self._start_ns) // 1000)
            self._stages[stage_name] = aggregate
            self._order.append(stage_name)
        duration_us = max(0, (end_ns - start_ns) // 1000)
        aggregate.count += 1
        aggregate.total_us += duration_us
        aggregate.max_us = max(aggregate.max_us, duration_us)
        if detail is not None:
            if aggregate.details is None:
                aggregate.details = {}
            aggregate.details[detail] = aggregate.details.get(detail, 0) + 1

    def elapsed_us(self) -> int:
        """要求受付から現在までの経過マイクロ秒を返す。"""
        return (perf_counter_ns() - self._start_ns) // 1000

    def stages(self) -> list[dict[str, object]]:
        """初回出現順の段階集計を返す。"""
        stages: list[dict[str, object]] = []
        for name in self._order:
            aggregate = self._stages[name]
            item: dict[str, object] = {
                "stage": name,
                "count": aggregate.count,
                "totalUs": aggregate.total_us,
                "maxUs": aggregate.max_us,
                "firstStartUs": aggregate.first_start_us,
            }
            if aggregate.details:
                item["callers"] = dict(aggregate.details)
            stages.append(item)
        return stages


def timing_enabled() -> bool:
    """環境変数で明示された場合だけ計測を有効にする。"""
    return os.environ.get(ENV_VARIABLE) == "1"


def start_sync_stage_timing() -> tuple[
    SyncStageTimer | None, Token[SyncStageTimer | None] | None
]:
    """要求の先頭で計測を開始し、現在のcontextへ束縛する。"""
    if not timing_enabled():
        return None, None
    timer = SyncStageTimer()
    timer.record("route_entry", timer._start_ns, timer._start_ns)
    return timer, _CURRENT.set(timer)


def finish_sync_stage_timing(token: Token[SyncStageTimer | None] | None) -> None:
    """要求の終端でcontext束縛を戻す。"""
    if token is not None:
        _CURRENT.reset(token)


@contextmanager
def stage(name: str, *, detail: str | None = None) -> Iterator[None]:
    """有効時だけ段階の所要を記録する。無効時は何もしない。"""
    timer = _CURRENT.get()
    if timer is None:
        yield
        return
    start_ns = perf_counter_ns()
    try:
        yield
    finally:
        timer.record(name, start_ns, perf_counter_ns(), detail)


def active() -> bool:
    """現在の要求で段階計測が有効かを返す。"""
    return _CURRENT.get() is not None


def begin_stage(name: str) -> tuple[str, int] | None:
    """関数全体など``with``で括れない範囲の開始を記録する。"""
    if _CURRENT.get() is None:
        return None
    return (name, perf_counter_ns())


def end_stage(begin: tuple[str, int] | None) -> None:
    """``begin_stage``に対応する終了を記録する。"""
    if begin is None:
        return
    timer = _CURRENT.get()
    if timer is None:
        return
    timer.record(begin[0], begin[1], perf_counter_ns())


def stage_timed_host_call(host: Any, operation: str, request_json: str) -> str:
    """host.callを``host_call``段階として測る。"""
    with stage("host_call"):
        return host.call(operation, request_json)


class TimedOpen(AbstractContextManager[Any]):
    """open関数の呼出だけを段階計測し、返却されたcontext managerへ委譲する。"""

    __slots__ = ("_close_name", "_manager", "_open_name", "_opener")

    def __init__(
        self,
        opener: Any,
        *,
        open_name: str = "host_open",
        close_name: str = "host_close",
    ) -> None:
        """呼出可能なopen関数と段階名を保持する。"""
        self._opener = opener
        self._open_name = open_name
        self._close_name = close_name
        self._manager: AbstractContextManager[Any] | None = None

    def __enter__(self) -> Any:
        """open呼出を測ってから、返却されたcontext managerへ入る。"""
        with stage(self._open_name):
            manager = self._opener()
        self._manager = manager
        return manager.__enter__()

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: Any,
    ) -> bool | None:
        """元のcontext managerの終了へ委譲する。"""
        manager = self._manager
        if manager is None:
            return None
        with stage(self._close_name):
            return manager.__exit__(exception_type, exception, traceback)


class TimedScope(AbstractContextManager[Any]):
    """既存context managerのenter/exitを別段階として包む。"""

    __slots__ = ("_close_name", "_manager", "_open_name")

    def __init__(
        self,
        manager: AbstractContextManager[Any],
        *,
        open_name: str,
        close_name: str,
    ) -> None:
        """元のcontext managerと段階名を保持する。"""
        self._manager = manager
        self._open_name = open_name
        self._close_name = close_name

    def __enter__(self) -> Any:
        """enterの所要を開始段階として記録する。"""
        with stage(self._open_name):
            return self._manager.__enter__()

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: Any,
    ) -> bool | None:
        """exitの所要を終了段階として記録する。"""
        with stage(self._close_name):
            return self._manager.__exit__(exception_type, exception, traceback)


def emit_sync_stage_timing(
    timer: SyncStageTimer, *, method: str, route: str, status: int
) -> None:
    """1要求分の段階集計を1行JSONとして標準エラーへ出す。"""
    payload = {
        "event": "sync_stage_timing",
        "method": method,
        "route": route,
        "status": status,
        "totalUs": timer.elapsed_us(),
        "stages": timer.stages(),
    }
    line = (
        _LOG_PREFIX
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    )
    sys.stderr.write(line)
    sys.stderr.flush()


def server_timing_value(timer: SyncStageTimer) -> str:
    """同じ集計を``Server-Timing``ヘッダ値へ写す。"""
    parts = [f"total;dur={timer.elapsed_us() / 1000:.1f}"]
    for item in timer.stages():
        name = str(item["stage"])
        count = int(item["count"])
        total_us = int(item["totalUs"])
        max_us = int(item["maxUs"])
        parts.append(
            f'{name};dur={total_us / 1000:.1f};'
            f'desc="count={count},max={max_us / 1000:.1f}ms"'
        )
    return ", ".join(parts)
