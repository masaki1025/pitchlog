"""辞書内包表記の generator 条件で TenantContext を構築する負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def build(values, tenant_id):
    """辞書内包表記の条件から allowlist 外の構築へ到達する。"""
    return {
        value: value
        for value in values
        if TenantContext(tenant_id)
    }
