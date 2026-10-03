"""注釈付き代入の annotation で TenantContext を構築する負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def annotate(tenant_id):
    """annotation の評価から allowlist 外の構築へ到達する。"""
    context: TenantContext(tenant_id) = None  # ty: ignore
    return context
