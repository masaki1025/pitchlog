"""match 合流で TenantContext 起源を消す条件 5 の負例。"""

from external.helpers import safe  # ty: ignore
from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(flag, tenant_id):
    """match 各分岐の可能な構築起源を保持する。"""
    match flag:
        case True:
            factory = TenantContext
        case _:
            factory = safe
    return factory(tenant_id)
