"""関数内 import で TenantContext を構築する条件 5 の負例。"""


def build(tenant_id):
    """局所 import を保証外 callable と誤認させない。"""
    from pitchlog.repositories.context import TenantContext  # ty: ignore

    return TenantContext(tenant_id)
