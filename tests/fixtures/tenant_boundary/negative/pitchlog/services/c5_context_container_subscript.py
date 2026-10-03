"""コンテナと添字で TenantContext 起源を隠す条件 5 の負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(tenant_id):
    """コンテナ要素の構築起源を添字参照へ伝播する。"""
    factory = [TenantContext][0]
    return factory(tenant_id)
