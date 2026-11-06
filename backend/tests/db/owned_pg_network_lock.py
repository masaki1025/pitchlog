"""隔離PGの生成から後始末までを画面試験のDockerネットワーク変更から守る。"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

LOCK_PATH = Path(
    "/home/ymdms/.cache/pitchlog/test-coordination/owned-pg-browser-network.lock"
)


@contextmanager
def owned_pg_browser_network_lock() -> Iterator[None]:
    """共通ロックを排他取得し、fixtureの作成・破棄全体を囲む。"""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
