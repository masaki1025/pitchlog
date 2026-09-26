"""デフォルト引数で TenantContext を構築する負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore

tenant_id = "other-tenant"


def run(context=TenantContext(tenant_id)):
    """関数定義時に allowlist 外で TenantContext を構築する。"""
    return context
