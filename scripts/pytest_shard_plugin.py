"""テスト ID を決定的に分割する pytest プラグイン。

CI の backend / harness は同じテスト集合を複数ジョブへ分割して実行する。
分割は「全件を各1回だけ実行する」ことが保証されなければ検査の質を落とすため、
node id の安定ソート順に対する剰余で決定的に割り当てる。実行時間ではなく件数で
均等化する初期実装であり、時間の偏りは実測後に別途調整する。

使い方(CI):
    PYTHONPATH=scripts pytest -p pytest_shard_plugin --shard-count 4 --shard-index 1 ...

`--shard-count` を省略した場合は分割せず全件を実行する。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# 分割前の総数。被覆検査がファイル経由で読むため、config の属性ではなく
# モジュール状態に持つ(型検査で Config の動的属性を増やさない)。
_COLLECTED_TOTALS: dict[int, int] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    """分割用のオプションを追加する。"""
    group = parser.getgroup("pytest_shard")
    group.addoption(
        "--shard-count",
        action="store",
        type=int,
        default=0,
        help="分割数。0 は分割しない",
    )
    group.addoption(
        "--shard-index",
        action="store",
        type=int,
        default=0,
        help="このプロセスが担当する 0 始まりの番号",
    )


def pytest_configure(config: pytest.Config) -> None:
    """分割指定の組合せを起動時に検証する。"""
    count = config.getoption("shard_count")
    index = config.getoption("shard_index")
    if type(count) is not int or count < 0:
        raise pytest.UsageError("--shard-count は 0 以上の整数が必要")
    if type(index) is not int or index < 0:
        raise pytest.UsageError("--shard-index は 0 以上の整数が必要")
    if count == 0 and index != 0:
        raise pytest.UsageError("--shard-count なしで --shard-index は指定できない")
    if count > 0 and index >= count:
        raise pytest.UsageError("--shard-index は --shard-count 未満が必要")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """収集順の剰余で、このシャードの項目だけを残す。

    収集順はファイル順・パラメータ順に依存し、乱数 UUID を含む node id でも
    順序は安定する。総数はヘッダへ出して被覆検査が照合できるようにする。
    """
    count = config.getoption("shard_count")
    if count == 0:
        return
    index = config.getoption("shard_index")
    total = len(items)
    items[:] = [item for position, item in enumerate(items) if position % count == index]
    _COLLECTED_TOTALS[id(config)] = total
    # -q ではヘッダが抑制されるため、被覆検査が総数を照合できるようファイルへ書く。
    target = os.environ.get("PITCHLOG_SHARD_TOTAL_FILE")
    if target:
        Path(target).write_text(str(total), encoding="utf-8")


def pytest_report_header(config: pytest.Config) -> str | None:
    """分割指定を実行ログへ残す。"""
    count = config.getoption("shard_count")
    if not count:
        return None
    index = config.getoption("shard_index")
    total = _COLLECTED_TOTALS.get(id(config), "?")
    return (
        f"pytest_shard: index={index} count={count} collected={total} selected={len(config.args)}"
    )
