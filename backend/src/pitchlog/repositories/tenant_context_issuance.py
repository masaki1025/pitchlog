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


def _issue_initial_broker_context(
    cookie: object, expected_tenant_id: object, verifier_runtime: object
) -> tuple[TenantContext, datetime] | None:
    """私有verifierの実照合tenantだけを既module内で発行する。"""
    from uuid import UUID

    from pydantic import SecretStr

    from pitchlog.recording_rights.initial_grant_broker import (
        _broker_invalid,
        _verify_initial_cookie,
    )

    if type(cookie) is not SecretStr or type(expected_tenant_id) is not UUID:
        raise _broker_invalid()
    verified = _verify_initial_cookie(verifier_runtime, cookie)
    if verified is None or verified[0] != expected_tenant_id:
        return None
    tenant_id, expires_at = verified
    return TenantContext(tenant_id, _ISSUANCE_CAPABILITY), expires_at
