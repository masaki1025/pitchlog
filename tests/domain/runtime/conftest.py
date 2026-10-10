"""合成 artifact と常駐 Node の共通試験データを用意する。"""

from __future__ import annotations

import json
import select
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
ARTIFACT = FIXTURES / "synthetic_artifact.js"
NODE_HOST = FIXTURES / "node_host.mjs"
NODE = shutil.which("node")

BIGINT_VALUES = (
    "0",
    "-1",
    "2147483648",
    "9007199254740993",
    "18446744073709551621",
    "-18446744073709551621",
)


def json_bytes(value: object) -> bytes:
    """JSON 文字列境界に使う空白なし UTF-8 を返す。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


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
    values = [
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


class NodeHost:
    """試験専用の改行区切り JSON ホストを管理する。"""

    def __init__(self) -> None:
        """同一 artifact を読む Node を一度だけ起動する。"""
        assert NODE is not None
        self.process = subprocess.Popen(
            [NODE, "--disallow-code-generation-from-strings", str(NODE_HOST), str(ARTIFACT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def request(self, payload: bytes) -> bytes:
        """一要求を送り、一応答をバイト列で受け取る。"""
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(payload + b"\n")
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], 3)
        assert ready, "Node ホストが 3 秒以内に応答しない"
        response = self.process.stdout.readline()
        assert response.endswith(b"\n"), "Node ホストが改行区切り応答を返さない"
        return response[:-1]

    def close(self) -> None:
        """試験後に常駐プロセスを終了する。"""
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


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
