"""try-except 合流で TenantContext 起源を消す条件 5 の負例。"""

from external.helpers import safe  # ty: ignore
from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(tenant_id):
    """正常系と例外系の可能な構築起源を保持する。"""
    try:
        factory = TenantContext
    except RuntimeError:
        factory = safe
    return factory(tenant_id)
