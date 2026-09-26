"""終端文より後で TenantContext を構築する負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def terminate_then_construct(tenant_id):
    """return 後も scanner と flow の被覆対象にする。"""
    return None
    TenantContext(tenant_id)
