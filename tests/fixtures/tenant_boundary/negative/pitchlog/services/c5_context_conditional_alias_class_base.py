"""条件付き alias を関数内 class の基底に使う条件 5 の負例。"""

from external.helpers import safe  # ty: ignore
from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(flag, tenant_id):
    """関数内 class の基底まで可能な構築起源を保持する。"""
    base = TenantContext if flag else safe

    class Derived(base):
        pass

    return Derived(tenant_id)
