"""star import の起源を解決済みとして扱わせない負例。"""

from external.facade import *  # type: ignore  # noqa: F403


def run() -> object:
    """star import 由来で起源不明の名前を呼び出す。"""
    return Context("other-tenant")  # type: ignore  # noqa: F405
