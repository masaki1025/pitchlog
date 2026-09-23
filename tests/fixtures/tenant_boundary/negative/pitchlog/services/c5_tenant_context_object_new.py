"""object.__new__ による TenantContext allowlist 迂回の負例。"""

from pitchlog.repositories.context import TenantContext  # ty: ignore


def bypass() -> TenantContext:
    """コンストラクタを通らず TenantContext を生成する。"""
    return object.__new__(TenantContext)
