"""TenantContext.__new__ を直接呼ぶ条件 5 の負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def forge():
    """通常の constructor 呼び出しを通さず instance を確保する。"""
    return TenantContext.__new__(TenantContext)
