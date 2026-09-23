"""発行証跡の導出関数を直接参照する負例。"""

from pitchlog.repositories.context import _tenant_context_proof  # ty: ignore


def forge_proof(tenant_id):
    """許可シンボル外から発行証跡を作る。"""
    return _tenant_context_proof(tenant_id)
