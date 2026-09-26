"""TenantContext.__init__ を直接呼ぶ条件 5 の負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def forge(target, tenant_id):
    """既存 object へ constructor の初期化処理だけを適用する。"""
    TenantContext.__init__(target, tenant_id)
    return target
