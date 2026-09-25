"""条件付き alias をクロージャへ渡す条件 5 の負例。"""

from external.helpers import safe  # ty: ignore
from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(flag, tenant_id):
    """クロージャ内まで可能な構築起源を保持する。"""
    factory = TenantContext if flag else safe

    def inner():
        return factory(tenant_id)

    return inner()
