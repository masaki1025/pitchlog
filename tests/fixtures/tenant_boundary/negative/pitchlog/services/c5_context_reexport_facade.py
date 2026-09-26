"""façade の別名 Context を通じて TenantContext を構築する負例。"""

from pitchlog.services.c5_context_in_default_arg import (
    TenantContext as Context,
)

tenant_id = "other-tenant"


def run() -> object:
    """再輸出名から TenantContext を不正に構築する。"""
    return Context(tenant_id)
