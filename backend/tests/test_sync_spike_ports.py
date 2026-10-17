"""spike スタブポートの実行時登録と復元を検査する。

spike の `install()` は製品の `PORT_IMPLEMENTATIONS` 定数を実行時に書き換える
（テストの monkeypatch と同じ権限の明示的操作）。この試験は「登録できる」こと
と、返された callable で「戻せる」ことを検査して、書き換えが恒久的に残らない
ことを担保する。製品の初期値（空の frozenset()）は monkeypatch の退避先として
常に守る。
"""

from __future__ import annotations

import pytest

from pitchlog.sync import port_guard, ports, spike_ports

_EMPTY: frozenset[tuple[str, str]] = frozenset()
_SPIKE_CLASSES = (
    spike_ports.SpikeRights,
    spike_ports.SpikeProjection,
    spike_ports.SpikeValidator,
)


def _spike_registrations() -> frozenset[tuple[str, str]]:
    """Spike スタブ 3 クラスの登録キーの組を作る。"""
    return frozenset((cls.__module__, cls.__name__) for cls in _SPIKE_CLASSES)


def test_install_registers_stub_classes_and_returned_callable_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """install() で登録し、返された callable で製品の空表へ戻る。"""
    monkeypatch.setattr(ports, "PORT_IMPLEMENTATIONS", _EMPTY)
    assert ports.PORT_IMPLEMENTATIONS == _EMPTY

    restore = spike_ports.install(ports)
    try:
        assert ports.PORT_IMPLEMENTATIONS == _spike_registrations()
    finally:
        restore()
    assert ports.PORT_IMPLEMENTATIONS == _EMPTY  # 恒久的な書き換えは残らない


def test_installed_spike_ports_pass_the_port_source_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登録中の spike スタブモジュールはポート検査を静的に通る。"""
    monkeypatch.setattr(ports, "PORT_IMPLEMENTATIONS", _EMPTY)
    restore = spike_ports.install(ports)
    try:
        port_guard.validate_port_modules()
    finally:
        restore()
    port_guard.validate_port_modules()
    assert ports.PORT_IMPLEMENTATIONS == _EMPTY
