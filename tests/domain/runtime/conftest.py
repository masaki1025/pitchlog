"""合成 artifact と常駐 Node の共通試験データを用意する。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from _runtime_support import BIGINT_VALUES, NODE, NodeHost, json_bytes


@pytest.fixture(scope="module")
def cases() -> tuple[tuple[bytes, bytes], ...]:
    """入力と独立に決めた期待出力の組を返す。"""
    rows = [
        {"key": "b", "value": "first"},
        {"key": "a", "value": "second"},
        {"key": "b", "value": "third"},
        {"key": "a", "value": "fourth"},
    ]
    expected_rows = [rows[1], rows[3], rows[0], rows[2]]
    values: list[tuple[dict[str, object], dict[str, object]]] = [
        ({"operation": "echo", "value": value}, {"value": value}) for value in BIGINT_VALUES
    ]
    values.extend(
        [
            (
                {"operation": "arithmetic", "operator": "add", "left": "-1", "right": "2147483648"},
                {"value": "2147483647"},
            ),
            (
                {
                    "operation": "arithmetic",
                    "operator": "subtract",
                    "left": "-18446744073709551621",
                    "right": "1",
                },
                {"value": "-18446744073709551622"},
            ),
            (
                {
                    "operation": "arithmetic",
                    "operator": "multiply",
                    "left": "9007199254740993",
                    "right": "-2",
                },
                {"value": "-18014398509481986"},
            ),
            (
                {"operation": "arithmetic", "operator": "divide", "left": "-7", "right": "3"},
                {"value": "-2"},
            ),
            (
                {"operation": "arithmetic", "operator": "divide", "left": "7", "right": "-3"},
                {"value": "-2"},
            ),
            (
                {"operation": "arithmetic", "operator": "divide", "left": "1", "right": "0"},
                {"error": "zero_divisor"},
            ),
            ({"operation": "sort", "rows": rows}, {"rows": expected_rows}),
            ({"operation": "error"}, {"error": "synthetic_error"}),
        ]
    )
    return tuple((json_bytes(request), json_bytes(expected)) for request, expected in values)


@pytest.fixture
def node_host() -> Iterator[NodeHost]:
    """Node が存在する場合だけ試験用の常駐ホストを渡す。"""
    if NODE is None:
        pytest.skip("node が見つからない")
    host = NodeHost()
    try:
        yield host
    finally:
        host.close()
