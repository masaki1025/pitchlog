"""class base で TenantContext を構築する負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore

tenant_id = "other-tenant"


class ForgedContext(TenantContext(tenant_id)):
    """allowlist 外で構築した値を基底として使う。"""
