"""例外 handler type で TenantContext を構築する負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def handle(tenant_id):
    """handler type の評価から allowlist 外の構築へ到達する。"""
    try:
        raise
    except TenantContext(tenant_id):
        return None
