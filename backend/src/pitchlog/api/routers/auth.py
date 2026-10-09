"""チームのログイン経路を提供する。"""

import ipaddress
from datetime import UTC, datetime

import anyio
from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from pitchlog.api.schemas.auth import LoginRequest, LoginResponse
from pitchlog.authz.team_login import get_login_connection, login_attempt

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

    value, expires_at = result
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
    return LoginResponse()
