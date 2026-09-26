"""if-else 合流で TenantContext 起源を消す条件 5 の負例。"""

from external.helpers import safe  # ty: ignore
from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(flag, tenant_id):
    """分岐代入の可能な構築起源を保持する。"""
    if flag:
        factory = TenantContext
    else:
        factory = safe
    return factory(tenant_id)
