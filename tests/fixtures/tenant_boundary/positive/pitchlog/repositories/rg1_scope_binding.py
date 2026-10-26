"""同Sessionの固定RG1識別SELECTだけの正例。"""

from sqlalchemy import Uuid, bindparam, func, select  # ty: ignore[unresolved-import]
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]


class rg1:
    """製品モジュールの登録symbolを表す。"""

    @staticmethod
    def _build_rg1_scope_binding_statement() -> Select[tuple[str]]:
        """tenantは実scopeからだけ注入する。"""
        tenant_id = bindparam("tenant_id", type_=Uuid())
        return select(func.rg1_control.scope_binding(tenant_id).label("binding"))
