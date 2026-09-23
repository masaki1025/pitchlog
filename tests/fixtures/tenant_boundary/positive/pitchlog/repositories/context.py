"""TenantContext の将来シンボル契約を表す正例。"""

from uuid import UUID


class TenantContext:
    """リポジトリへ渡す不変なテナント文脈を表す。"""

    def __init__(self, tenant_id: UUID) -> None:
        """テナント ID を保持する。"""
        self.tenant_id = tenant_id
