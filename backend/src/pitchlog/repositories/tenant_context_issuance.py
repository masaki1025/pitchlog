"""製品の入口へ渡すテナント文脈を提示値から発行する。"""

from datetime import datetime

from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import verify_tenant_id
from pitchlog.db.engine import create_database_engine
from pitchlog.repositories.context import _ISSUANCE_CAPABILITY, TenantContext

__all__ = ("issue_tenant_context_from_presented_token",)


def issue_tenant_context_from_presented_token(
    value: str, presentation: TokenPresentation
) -> tuple[TenantContext, datetime] | None:
    """照合済みの提示値からだけテナント文脈を発行する。

    Args:
        value: Cookie から得た不透明な提示値。
        presentation: アプリ起動時に設定した署名器。

    Returns:
        照合に成功した文脈と延長後の期限。拒否した場合は None。
    """
    if type(value) is not str:
        return None
    engine = create_database_engine()
    try:
        verified = verify_tenant_id(value, presentation, engine)
    finally:
        engine.dispose()
    if verified is None:
        return None
    tenant_id, expires_at = verified
    return TenantContext(tenant_id, _ISSUANCE_CAPABILITY), expires_at
