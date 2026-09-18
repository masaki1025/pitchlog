"""リポジトリへ渡すテナント文脈を定義する。"""

from dataclasses import dataclass
from typing import final
from uuid import UUID


@final
@dataclass(frozen=True, slots=True, init=False)
class TenantContext:
    """呼び出し側が渡したテナント ID を信じて束縛する値オブジェクト。

    この型は値の真正性を検査しない。テナント ID が認証済み主体のもので
    あることは API 層（TSK-217 / U-A1）の責務である。
    """

    tenant_id: UUID

    def __init__(self, tenant_id: UUID) -> None:
        """テナント ID を保持する。

        Args:
            tenant_id: 呼び出し側が認証済み主体から導出するテナント ID。
        """
        object.__setattr__(self, "tenant_id", tenant_id)
