"""TenantContext の将来シンボル契約を表す正例。"""

from typing import final
from uuid import UUID


@final
class TenantContextIssuanceCapability:
    """TenantContext の構築に必要な発行能力を表す。"""

    __slots__ = ()


class TenantContext:
    """リポジトリへ渡す不変なテナント文脈を表す。"""

    def __init__(
        self, tenant_id: UUID, issuance_capability: TenantContextIssuanceCapability
    ) -> None:
        """テナント ID を保持する。"""
        self.tenant_id = tenant_id
