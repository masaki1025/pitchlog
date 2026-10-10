"""提示値から検証済みのテナント文脈を要求する。"""

from typing import Annotated

from fastapi import Depends, Request

from pitchlog.api.request_presentation import RequestGateError, require_presented_token
from pitchlog.repositories.context import TenantContext


def require_tenant_access(
    request: Request, value: Annotated[str, Depends(require_presented_token)]
) -> TenantContext:
    """要求の提示値を照合して製品の入口に文脈を渡す。"""
    from pitchlog.repositories.tenant_context_issuance import (
        issue_tenant_context_from_presented_token,
    )

    context = issue_tenant_context_from_presented_token(
        value, request.app.state.token_presentation
    )
    if context is None:
        raise RequestGateError("credential")
    return context
