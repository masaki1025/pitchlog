"""一時ディレクトリ移送(backend 配線)の検証。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_tmp_path_is_under_bootstrap_base(
    tmp_bootstrap_base: Path | None, tmp_path: Path
) -> None:
    """テスト実行時の basetemp が移送先の配下に作られる。"""
    if tmp_bootstrap_base is None:
        pytest.skip("移送先が選ばれなかった(書込み不能時はシステム既定へ退避する仕様)")
    assert tempfile.gettempdir() == str(tmp_bootstrap_base)
    assert str(tmp_path).startswith(str(tmp_bootstrap_base))
