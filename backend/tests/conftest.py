"""AnyIO テストの共通設定。"""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """非同期テストで使う AnyIO backend を返す。"""
    return "asyncio"
