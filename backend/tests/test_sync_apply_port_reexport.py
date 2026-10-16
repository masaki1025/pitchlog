"""Pitchlog 内の再輸出を模した、静的検査用の合成モジュール。"""

import typing as exported_typing
from collections import abc as exported_collections_abc
from typing import Protocol as ExportedProtocol


class Holder:
    """再輸出される module object を属性に保持する。"""

    module = exported_typing


exported_nested = Holder.module

__all__ = (
    "exported_typing",
    "exported_collections_abc",
    "exported_nested",
    "ExportedProtocol",
)
