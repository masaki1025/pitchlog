"""ルート pytest から凍結基準台帳の共通読取実装を利用する。"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
READER_SCRIPT = REPOSITORY_ROOT / "scripts/check_frozen_baselines.py"


@lru_cache(maxsize=1)
def _load_reader() -> Callable[[Path, str], str]:
    """検査器から台帳末尾の読取関数を取得する。"""
    module_name = "frozen_baseline_reader_script"
    spec = importlib.util.spec_from_file_location(module_name, READER_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"凍結基準検査器を読み込めない: {READER_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    reader = getattr(module, "load_frozen_baseline_commit", None)
    if not callable(reader):
        raise RuntimeError("凍結基準検査器に共通読取関数がない")
    return cast(Callable[[Path, str], str], reader)


@lru_cache(maxsize=1)
def _load_target_reader() -> Callable[[Path, str], tuple[Any, str]]:
    """検査器から対象起点の宣言・基準読取関数を取得する。"""
    _load_reader()
    module = sys.modules["frozen_baseline_reader_script"]
    reader = getattr(module, "load_frozen_baseline_for_target", None)
    if not callable(reader):
        raise RuntimeError("凍結基準検査器に対象起点の共通読取関数がない")
    return cast(Callable[[Path, str], tuple[Any, str]], reader)


def load_frozen_baseline_commit(root: Path, series: str) -> str:
    """指定した commit 型系列の末尾から現行基準を読む。

    Args:
        root: リポジトリルート。
        series: 読み出す系列名。

    Returns:
        系列末尾の40桁commit。
    """
    return _load_reader()(root, series)


def load_frozen_baseline_for_target(root: Path, target: str) -> tuple[Any, str]:
    """凍結対象から宣言と末尾基準を導出する。"""
    return _load_target_reader()(root, target)
