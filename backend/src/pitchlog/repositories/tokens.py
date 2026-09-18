"""閉じたリポジトリ操作 token と不変な実行結果を定義する。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

__all__ = ("TenantOperationResult", "TenantOperationToken")

type ImmutableScalar = (
    None | bool | int | float | str | bytes | UUID | Decimal | date | datetime | time
)
type ImmutableValue = (
    ImmutableScalar
    | tuple[ImmutableValue, ...]
    | frozenset[ImmutableValue]
)


class TenantOperationToken(ABC):
    """生成済み operation registry が認識する token の基底型。"""

    __slots__ = ()

    @property
    @abstractmethod
    def capability_id(self) -> str:
        """生成元 capability の閉じた識別子を返す。"""


@dataclass(frozen=True, slots=True)
class TenantOperationResult:
    """トランザクション内で完全実体化した不変な行集合。"""

    rows: tuple[tuple[ImmutableValue, ...], ...]
