"""提示値から検証済みのテナント文脈を要求する。"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request, Response

from pitchlog.api.request_presentation import RequestGateError, require_presented_token
from pitchlog.repositories.context import TenantContext


def require_tenant_access(
    request: Request,
    response: Response,
    value: Annotated[str, Depends(require_presented_token)],
) -> TenantContext:
    """要求の提示値を照合して製品の入口に文脈を渡す。"""
    from pitchlog.repositories.tenant_context_issuance import (
        issue_tenant_context_from_presented_token,
    )

    issued = issue_tenant_context_from_presented_token(
        value, request.app.state.token_presentation
    )
    if issued is None:
        raise RequestGateError("credential")
    context, expires_at = issued
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        key="__Host-pitchlog_token",
        value=value,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return context
