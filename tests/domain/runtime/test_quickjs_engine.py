"""quickjs-ng 0.17.0.1 の境界・拒否経路・資源上限を固定する。"""

from __future__ import annotations

import importlib.metadata
import platform
from typing import Protocol

import pytest
from _runtime_support import ARTIFACT, BIGINT_VALUES

quickjs = pytest.importorskip("quickjs")


class _QuickJsContext(Protocol):
    """往復試験で使用する quickjs-ng コンテキストの最小 API。"""

    def set(self, name: str, value: str) -> None:
        """ゲストへ文字列を渡す。"""
        ...

    def eval(self, source: str) -> object:
        """ゲストの式を評価する。"""
        ...


def _loaded_context() -> _QuickJsContext:
    """合成 artifact を読み込んだ独立コンテキストを返す。"""
    context = quickjs.Context()
    context.eval(ARTIFACT.read_text(encoding="utf-8"))
    return context


@pytest.mark.parametrize("value", BIGINT_VALUES)
def test_decimal_string_bigint_round_trip(value: str) -> None:
    context = _loaded_context()
    context.set("requestJson", f'{{"operation":"echo","value":"{value}"}}')
    assert context.eval("PitchlogSynthetic.run(requestJson)") == f'{{"value":"{value}"}}'


@pytest.mark.parametrize(
    ("value", "observed"),
    [
        (0, "0"),
        (-1, "-1"),
        (2147483648, "-2147483648"),
        (9007199254740993, "1"),
        (18446744073709551621, "18446744073709552000"),
        (-18446744073709551621, "-18446744073709552000"),
    ],
)
def test_direct_python_int_binding_is_number_and_can_change_value(
    value: int, observed: str
) -> None:
    context = quickjs.Context()
    context.set("bound", value)
    assert context.eval("typeof bound") == "number"
    assert context.eval("String(bound)") == observed


def test_eval_deletion_does_not_block_function_constructors() -> None:
    context = quickjs.Context()
    assert context.eval('eval("2")') == 2
    assert context.eval('new Function("return 2")()') == 2
    assert context.eval('Function.prototype.constructor("return 2")()') == 2
    context.eval("delete globalThis.eval")
    with pytest.raises(quickjs.JSException, match="eval is not defined"):
        context.eval('eval("2")')
    assert context.eval('new Function("return 2")()') == 2
    assert context.eval('Function.prototype.constructor("return 2")()') == 2
    ignored_option = quickjs.Context(disable_eval=True)
    assert ignored_option.eval('eval("2")') == 2


def test_dynamic_import_has_no_module_loader_but_is_not_syntax_rejected() -> None:
    context = quickjs.Context()
    context.eval(
        'globalThis.importState = "pending"; '
        'import("data:text/javascript,export default 2").then('
        '() => { importState = "fulfilled"; }, '
        'error => { importState = String(error); })'
    )
    for _ in range(3):
        if not context.execute_pending_job():
            break
    assert context.eval("importState").startswith("ReferenceError: could not load module")


def test_memory_limit_fails_closed() -> None:
    context = quickjs.Context()
    context.set_memory_limit(1024 * 1024)
    with pytest.raises(quickjs.JSException, match="out of memory"):
        context.eval('new Array(1000000).fill("x")')


def test_time_limit_fails_closed() -> None:
    context = quickjs.Context()
    context.set_time_limit(0.01)
    with pytest.raises(quickjs.JSException, match="interrupted"):
        context.eval("while (true) {}")


def test_stack_limit_fails_closed() -> None:
    context = quickjs.Context()
    context.set_max_stack_size(64 * 1024)
    with pytest.raises(quickjs.StackOverflow, match="Maximum call stack size exceeded"):
        context.eval("(function recurse() { return recurse(); })()")


def test_installed_wheel_targets_current_linux_platform() -> None:
    distribution = importlib.metadata.distribution("quickjs-ng")
    assert distribution.version == "0.17.0.1"
    assert platform.system() == "Linux"
    architecture = platform.machine()
    assert architecture in {"aarch64", "x86_64"}
    wheel_metadata = distribution.read_text("WHEEL")
    assert wheel_metadata is not None
    assert f"manylinux2014_{architecture}" in wheel_metadata
    assert "cp310-abi3" in wheel_metadata
