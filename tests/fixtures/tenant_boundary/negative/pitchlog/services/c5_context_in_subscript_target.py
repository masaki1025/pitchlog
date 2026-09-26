"""添字代入先で TenantContext を構築する負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def assign(target, tenant_id, value):
    """添字の評価から allowlist 外の構築へ到達する。"""
    target[TenantContext(tenant_id)] = value
