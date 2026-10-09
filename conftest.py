"""ルートの pytest 設定を異なる Python 環境でも受理させる。"""

from __future__ import annotations

import importlib.util

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """xdist が無い環境に限り並列化オプションを受理する。

    TSK-501 の harness 並列化でルートの pyproject.toml に設定した
    ``addopts = "-n auto --dist worksteal"`` を、backend の venv から
    scripts/check_authz_catalog.py 経由で起動する pytest 収集でも受理させる。
    ``--dist worksteal`` は小さな大量ケースと重いケースの分配の尾を短くする。
    xdist がある環境では互換オプションを登録しない。

    Args:
        parser: オプションを登録する pytest パーサー。
    """
    # xdist がある環境では本来の -n / --numprocesses と --dist に処理を任せる。
    if importlib.util.find_spec("xdist") is not None:
        return
    # pytest が予約する小文字の短縮オプションは、xdist と同じ登録方法を使う。
    group = parser.getgroup("xdist-compat")
    group._addoption(
        "-n",
        "--numprocesses",
        action="store",
        dest="_unused_numprocesses",
        metavar="NUMPROCESSES",
        help="xdist が無い環境でルートの並列化設定を受理する互換オプション",
    )
    # --dist worksteal は長短混在ケースの分配の尾を減らす設定として受理する。
    group._addoption(
        "--dist",
        action="store",
        dest="_unused_dist",
        metavar="DIST",
        help="xdist が無い環境でルートの分配設定を受理する互換オプション",
    )
