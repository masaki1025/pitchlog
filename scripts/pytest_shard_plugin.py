"""テスト ID を実行時間の重みで決定的に分割する pytest プラグイン。

CI の backend / harness は同じテスト集合を複数ジョブへ分割して実行する。
分割は「全件を各1回だけ実行する」ことが保証されなければ検査の質を落とすため、
全シャードが同じ全件集合から同じ割当を計算する。割当は ``ci/pytest-shards.json``
の実行時間重みを使い、重いテストから順に最も空いているシャードへ置く。
重みに無い新しいテストも既定重みで必ず 1 つのシャードへ入る。

使い方(CI):
    PYTHONPATH=scripts pytest -p pytest_shard_plugin --shard-count 8 --shard-index 1 ...

`--shard-count` を省略した場合は分割せず全件を実行する。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pytest_shard_plan import (
    assign_shards,
    validated_default_weight,
    validated_weights,
)

# 分割前の総数。被覆検査がファイル経由で読むため、config の属性ではなく
# モジュール状態に持つ(型検査で Config の動的属性を増やさない)。
_COLLECTED_TOTALS: dict[int, int] = {}
CONFIG_RELATIVE_PATH = Path("ci") / "pytest-shards.json"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


def _suite_config(config: pytest.Config) -> dict[str, object] | None:
    """この pytest 実行に対応するスイート定義を返す。

    Args:
        config: pytest の設定。

    Returns:
        ルートが一致するスイート定義。設定や一致するスイートが無ければ ``None``。

    Raises:
        pytest.UsageError: 設定を読めない、または形が不正な場合。
    """
    path = REPOSITORY_ROOT / CONFIG_RELATIVE_PATH
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise pytest.UsageError(f"分割定義を読めない: {path}: {error}") from error
    if not isinstance(raw, dict):
        raise pytest.UsageError("分割定義のルートは JSON オブジェクトが必要")
    suites = raw.get("suites")
    if not isinstance(suites, dict):
        raise pytest.UsageError("分割定義の suites がオブジェクトではない")
    rootpath = Path(config.rootpath).resolve()
    for name, suite in suites.items():
        if not isinstance(name, str) or not isinstance(suite, dict):
            raise pytest.UsageError("分割定義のスイート行が不正")
        root_value = suite.get("root")
        if not isinstance(root_value, str) or not root_value:
            raise pytest.UsageError(f"{name}.root が文字列ではない")
        if (REPOSITORY_ROOT / root_value).resolve() == rootpath:
            return suite
    return None


def _load_assignment_settings(
    config: pytest.Config,
    count: int,
) -> tuple[dict[str, float], float]:
    """設定から重みと既定重みを読み、分割数との一致を検証する。

    Args:
        config: pytest の設定。
        count: コマンドラインで指定された分割数。

    Returns:
        正規化済みの重みと既定重み。

    Raises:
        pytest.UsageError: 分割数が設定と異なる、または重みが不正な場合。
    """
    suite = _suite_config(config)
    if suite is None:
        return {}, 1.0
    configured = suite.get("shards")
    if type(configured) is not int or configured < 1:
        raise pytest.UsageError("分割定義の shards が正の整数ではない")
    if configured != count:
        raise pytest.UsageError(
            f"--shard-count {count} が分割定義の shards {configured} と一致しない"
        )
    try:
        weights = validated_weights(suite.get("weights"))
        default_weight = validated_default_weight(suite.get("default_weight_seconds"))
    except ValueError as error:
        raise pytest.UsageError(str(error)) from error
    return weights, default_weight


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
    if count > 0:
        _load_assignment_settings(config, count)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """全件から重み付きでこのシャードの項目だけを残す。

    全シャードが同じ全件集合と同じ重みから同じ割当を計算するため、和集合は
    全件と一致し、各項目はちょうど 1 回だけ実行される。総数はヘッダへ出して
    被覆検査が照合できるようにする。
    """
    count = config.getoption("shard_count")
    if count == 0:
        return
    index = config.getoption("shard_index")
    weights, default_weight = _load_assignment_settings(config, count)
    total = len(items)
    assignments = assign_shards(
        [item.nodeid for item in items],
        count=count,
        weights=weights,
        default_weight=default_weight,
    )
    items[:] = [
        item
        for item, shard in zip(items, assignments, strict=True)
        if shard == index
    ]
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
