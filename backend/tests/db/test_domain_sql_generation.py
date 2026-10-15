"""合成 TS から生成した SQL を既存の DB fixture で照合する。"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import psycopg
import pytest

pytestmark = pytest.mark.requires_db

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend"
SCRIPTS = FRONTEND / "scripts/domain-sql"
ROWS: list[dict[str, str | bool]] = [
    {"amount": "-5", "active": True, "code": "a"},
    {"amount": "18446744073709551621", "active": True, "code": "b"},
    {"amount": "2", "active": False, "code": "c"},
    {"amount": "5", "active": True, "code": "d"},
]
INPUT = {"rows": ROWS, "bindings": {"threshold": "0"}}


def _node(script: Path, *arguments: str, payload: Mapping[str, object]) -> Any:
    """同じ合成 TS 正本の生成器または Node 実行器を呼ぶ。

    Args:
        script: 試験補助スクリプト。
        *arguments: スクリプトに渡す引数。
        payload: 合成行とバインド値。

    Returns:
        JSON 応答。
    """
    node = shutil.which("node")
    if node is None:
        pytest.fail("Node が見つからないため、合成 TS との一致を検証できない")
    result = subprocess.run(
        [node, "--experimental-strip-types", str(script), *arguments],
        input=json.dumps(payload),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=FRONTEND,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("mode", "rows"),
    [
        ("aggregate", ROWS),
        ("aggregate", []),
        ("classify", ROWS),
        ("classify", []),
    ],
)
def test_generated_sql_matches_node_on_postgres(
    mode: str,
    rows: list[dict[str, str | bool]],
    tested_role_connection: psycopg.Connection[Any],
) -> None:
    """集計と行分類を DB で実行し、合成 TS の Node 結果と突合する。

    Args:
        mode: 合成操作の種類。
        rows: 固定の合成行。
        tested_role_connection: 既存の被検査ロール接続 fixture。
    """
    source = SCRIPTS / "fixtures" / f"{mode}.ts"
    payload = {**INPUT, "rows": rows}
    generated = _node(SCRIPTS / "generate.mjs", str(source), mode, payload=payload)
    expected = _node(SCRIPTS / "fixture-runner.mjs", mode, payload=payload)

    try:
        with tested_role_connection.cursor() as cursor:
            cursor.execute(generated["sql"], generated["parameters"])
            if mode == "aggregate":
                result = cursor.fetchone()
                assert result is not None
                actual = {"count": str(result[0]), "sum": str(result[1])}
            else:
                actual = [value for (value,) in cursor.fetchall()]
    finally:
        tested_role_connection.rollback()

    assert actual == expected
