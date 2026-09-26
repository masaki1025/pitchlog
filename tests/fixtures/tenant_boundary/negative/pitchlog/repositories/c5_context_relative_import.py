"""相対 import した TenantContext を allowlist 外で構築する負例。"""

from .context import TenantContext  # ty: ignore

tenant_id = "other-tenant"


def run() -> TenantContext:
    """相対名から解決した TenantContext を不正に構築する。"""
    return TenantContext(tenant_id)
