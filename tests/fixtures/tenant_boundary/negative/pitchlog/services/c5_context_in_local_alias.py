"""TenantContext の静的な局所 alias を呼ぶ条件 5 の負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(tenant_id):
    """静的に解決できる派生 alias を保証外 callable と誤認させない。"""
    constructor = TenantContext
    derived_constructor = constructor
    return derived_constructor(tenant_id)
