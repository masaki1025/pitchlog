"""lambda のデフォルト引数で TenantContext を構築する負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def build_factory(tenant_id):
    """lambda 定義時に allowlist 外で TenantContext を構築する。"""
    return lambda context=TenantContext(tenant_id): context
