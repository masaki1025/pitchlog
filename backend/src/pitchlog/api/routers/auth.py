"""チームのログイン経路を提供する。"""

import ipaddress
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from pitchlog.api.request_presentation import RequestGateError, require_presented_token
from pitchlog.api.schemas.auth import (
    AuthSessionResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    PasswordChangeRequest,
    PasswordChangeResponse,
)
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.authz.password_change import change_password_token
from pitchlog.authz.team_login import get_login_connection, login_attempt
from pitchlog.authz.verified_tenant import logout_token, verify_tenant_id
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tenant_profile import TenantProfileReadToken
from pitchlog.repositories.transaction import tenant_transaction_scope

router = APIRouter(tags=["認証"])
_COOKIE_NAME = "__Host-pitchlog_token"


def _source(request: Request) -> str:
    """接続元を IPv4 アドレスまたは IPv6 の /64 へ正規化する。"""
    client = request.client
    if client is None:
        return "unknown"
    try:
        address = ipaddress.ip_address(client.host)
    except ValueError:
        return "unknown"
    if isinstance(address, ipaddress.IPv6Address):
        address = ipaddress.ip_network(f"{address}/64", strict=False).network_address
    return str(address)


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    operation_id="auth_login_create",
    summary="チームにログインする",
)
async def login(
    payload: LoginRequest, request: Request, response: Response
) -> LoginResponse:
    """認証結果に応じて Cookie を発行するか固定の失敗応答を返す。"""
    # 接続資源の遅延取得と cost 12 の照合だけを、実際の仕事としてスレッドへ出す。
    # 失敗後の待ちは接続もワーカーも占有しない非同期タイマーで消費する。
    result = await run_in_threadpool(
        lambda: login_attempt(
            payload.team_name,
            payload.password,
            _source(request),
            request.app.state.token_presentation,
            get_login_connection(),
        )
    )
    if isinstance(result, int):
        if result > 0:
            await anyio.sleep(result / 1000)
        raise HTTPException(status_code=401)

    value, _issued_expires_at = result
    # 発行済み提示値を既存の署名・DB境界で照合し、入力名からIDを推測しない。
    try:
        verified = await run_in_threadpool(
            lambda: verify_tenant_id(
                value, request.app.state.token_presentation, get_login_connection()
            )
        )
    except (RuntimeError, TypeError, ValueError):
        verified = None
    if verified is None:
        # 先行するtoken発行transactionまで全取消になったとは主張しない。
        raise HTTPException(status_code=503)
    tenant_id, expires_at = verified
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        key=_COOKIE_NAME,
        value=value,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return LoginResponse(tenant_id=tenant_id)


@router.get(
    "/auth/session",
    response_model=AuthSessionResponse,
    operation_id="auth_session_read",
    summary="ログイン状態を確認する",
)
def read_session(
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> AuthSessionResponse:
    """Cookieから検証したテナントの識別子と正規表示名だけを返す。"""
    with tenant_transaction_scope(context) as scope:
        rows = scope.run(TenantProfileReadToken()).rows
    if not rows:
        raise RequestGateError("credential")
    if len(rows) != 1 or len(rows[0]) != 2:
        raise RuntimeError("テナント情報の読み取り結果が不正")
    tenant_id, team_name = rows[0]
    if (
        type(tenant_id) is not UUID
        or tenant_id != context.tenant_id
        or type(team_name) is not str
        or not team_name
    ):
        raise RuntimeError("テナント情報の読み取り結果が不正")
    return AuthSessionResponse(tenant_id=tenant_id, team_name=team_name)


@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    operation_id="auth_logout_create",
    summary="ログアウトする",
)
async def logout(request: Request, response: Response) -> LogoutResponse:
    """提示値を失効させ、端末の Cookie を消す。"""
    value = await require_presented_token(request)
    await run_in_threadpool(
        lambda: logout_token(
            value, request.app.state.token_presentation, get_login_connection()
        )
    )
    response.delete_cookie(
        key=_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict"
    )
    return LogoutResponse()


@router.patch(
    "/auth/password",
    response_model=PasswordChangeResponse,
    operation_id="auth_password_update",
    summary="パスワードを変更する",
)
async def change_password(
    payload: PasswordChangeRequest, request: Request, response: Response
) -> PasswordChangeResponse:
    """現行パスワードで変更し、実行端末も再ログインを要求する。"""
    value = await require_presented_token(request)
    changed = await run_in_threadpool(
        lambda: change_password_token(
            value,
            payload.current_password,
            payload.new_password,
            request.app.state.token_presentation,
            get_login_connection(),
        )
    )
    if not changed:
        raise RequestGateError("credential")
    response.delete_cookie(
        key=_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict"
    )
    return PasswordChangeResponse()
