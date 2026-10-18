"""AnyIO テストと一時ディレクトリ移送の共通設定。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 一時ディレクトリの移送はルートの conftest と同一実装を使う(単一実装)。
# backend からリポジトリ直下の scripts/ を import するため、ルートを sys.path へ加える。
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from scripts.pytest_tmp_bootstrap import activate, prune_stale  # noqa: E402

# basetemp は tempfile 経由で遅延計算されるため、conftest の読込み時に向け替える。
_ACTIVATION = activate()
prune_stale(_ACTIVATION)


@pytest.fixture(scope="session")
def tmp_bootstrap_base() -> Path | None:
    """移送先の基底(選ばれなかった場合は ``None``)。配線の検証用。"""
    return _ACTIVATION.base


@pytest.fixture
def anyio_backend() -> str:
    """非同期テストで使う AnyIO backend を返す。"""
    return "asyncio"
