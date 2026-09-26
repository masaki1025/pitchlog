"""IfExp 合流で TenantContext 起源を消す条件 5 の負例。"""

from external.helpers import safe  # ty: ignore
from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(flag, tenant_id):
    """安全 callable との合流後も構築起源を保持する。"""
    factory = TenantContext if flag else safe
    return factory(tenant_id)
