"""同期段階計測の既定無効・固定名・秘密非出力を固定する。"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager, contextmanager, redirect_stderr
from io import StringIO
from typing import Any, Iterator

import pytest

from pitchlog.sync import stage_timing as timing


def _start(monkeypatch: pytest.MonkeyPatch) -> Any:
    """計測を明示有効にし、後始末用tokenも返す。"""
    monkeypatch.setenv(timing.ENV_VARIABLE, "1")
    return timing.start_sync_stage_timing()


def test_timing_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数がない通常要求では何も記録しない。"""
    monkeypatch.delenv(timing.ENV_VARIABLE, raising=False)

    assert timing.timing_enabled() is False
    timer, token = timing.start_sync_stage_timing()
    assert timer is None
    assert token is None
    with timing.stage("auth"):
        pass
    assert timing.begin_stage("auth") is None


def test_records_only_fixed_stage_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """反復を件数へ集約し、未知の名前をotherへ寄せる。"""
    timer, token = _start(monkeypatch)
    assert timer is not None
    try:
        with timing.stage("auth"):
            pass
        with timing.stage("auth"):
            pass
        with timing.stage("unknown-user-value"):
            pass
        begin = timing.begin_stage("replay")
        timing.end_stage(begin)
        stages = {item["stage"]: item for item in timer.stages()}
    finally:
        timing.finish_sync_stage_timing(token)

    assert stages["auth"]["count"] == 2
    assert stages["auth"]["totalUs"] >= 0
    assert stages["replay"]["count"] == 1
    assert "unknown-user-value" not in stages
    assert stages["other"]["count"] == 1


def test_emits_one_line_without_request_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """出力は固定キーと段階集計だけで、要求本文や資格を含まない。"""
    timer, token = _start(monkeypatch)
    assert timer is not None
    stream = StringIO()
    try:
        with timing.stage("auth"):
            pass
        with redirect_stderr(stream):
            timing.emit_sync_stage_timing(
                timer, method="POST", route="sync_events", status=200
            )
    finally:
        timing.finish_sync_stage_timing(token)

    text = stream.getvalue()
    assert text.startswith(timing.ENV_VARIABLE + "=")
    assert text.count("\n") == 1
    payload = json.loads(text.split("=", 1)[1])
    assert set(payload) == {
        "event",
        "method",
        "route",
        "status",
        "totalUs",
        "stages",
    }
    assert payload["status"] == 200
    assert set(payload["stages"][0]) == {
        "stage",
        "count",
        "totalUs",
        "maxUs",
        "firstStartUs",
    }
    lowered = text.lower()
    for forbidden in ("cookie", "credential", "request_json", "tenant_id"):
        assert forbidden not in lowered


def test_server_timing_header_has_only_metric_durations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server-Timingは固定段階名とdur/descだけを返す。"""
    timer, token = _start(monkeypatch)
    assert timer is not None
    try:
        with timing.stage("auth"):
            pass
        value = timing.server_timing_value(timer)
    finally:
        timing.finish_sync_stage_timing(token)

    assert value.startswith("total;dur=")
    assert ", auth;dur=" in value
    assert 'desc="count=1,max=' in value
    for forbidden in ("cookie", "credential", "tenant", "game"):
        assert forbidden not in value.lower()


@contextmanager
def _manager(log: list[str]) -> Iterator[str]:
    """enter/exitの順序を記録する単純なcontext manager。"""
    log.append("enter")
    try:
        yield "value"
    finally:
        log.append("exit")


def test_timed_scope_keeps_original_context_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enter/exitを包み、元の戻り値と例外伝播を変えない。"""
    timer, token = _start(monkeypatch)
    assert timer is not None
    log: list[str] = []
    wrapped = timing.TimedScope(
        _manager(log), open_name="main_tx_open", close_name="main_tx_close"
    )
    assert isinstance(wrapped, AbstractContextManager)
    try:
        with wrapped as value:
            assert value == "value"
        stages = {item["stage"]: item["count"] for item in timer.stages()}
    finally:
        timing.finish_sync_stage_timing(token)

    assert log == ["enter", "exit"]
    assert stages["main_tx_open"] == 1
    assert stages["main_tx_close"] == 1
