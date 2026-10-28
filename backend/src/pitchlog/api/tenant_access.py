"""提示値から検証済みのテナント文脈を要求する。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool
from starlette.types import Receive, Scope, Send

from pitchlog.api.request_presentation import RequestGateError, require_presented_token
from pitchlog.repositories.context import TenantContext

_MATCH_STATE = "pitchlog_tenant_match"
_MATCH_ROUTE_STATE = "pitchlog_tenant_match_route"
_EXPECTED_HEADER = "X-Pitchlog-Expected-Tenant"
_CHALLENGE_HEADER = "X-Pitchlog-Tenant-Challenge"
_ACK_HEADER = b"x-pitchlog-tenant-match"
_CHALLENGE_RESPONSE_HEADER = b"x-pitchlog-tenant-challenge"
_MATCH_OPERATIONS = frozenset(
    {
        "preparing_game_list",
        "preparing_game_detail",
        "started_game_detail",
        "initial_device_enroll",
        "initial_game_start",
        "initial_game_start_resolve",
        "roster_self_team_read",
        "roster_team_list",
        "roster_team_create",
        "roster_team_update",
        "roster_player_list",
        "roster_player_create",
        "roster_player_read",
        "roster_player_update",
    }
)


@dataclass(frozen=True, slots=True)
class _TenantMatch:
    """同じ要求内で照合済み文脈と公開challengeだけを保持する。"""

    context: TenantContext
    challenge: str


def _canonical_header(request: Request, name: str) -> str:
    """単一のcanonical UUIDを要求し、拒否に入力値を含めない。"""
    values = request.headers.getlist(name)
    if len(values) != 1:
        raise HTTPException(status_code=404)
    value = values[0]
    try:
        if str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise HTTPException(status_code=404)


class TenantMatchedRoute(APIRoute):
    """指定経路で本文検証より先に認証とtenant照合を行う。"""

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        """本文を解釈する標準ASGI経路へ照合済み要求だけを渡す。"""
        if self.operation_id in _MATCH_OPERATIONS and (
            self.methods is None or scope["method"] in self.methods
        ):
            request = Request(scope, receive)
            request.scope.setdefault("state", {})[_MATCH_ROUTE_STATE] = True
            value = await require_presented_token(request)
            context = await run_in_threadpool(
                require_tenant_access, request, Response(), value
            )
            expected = _canonical_header(request, _EXPECTED_HEADER)
            challenge = _canonical_header(request, _CHALLENGE_HEADER)
            if expected != str(context.tenant_id):
                raise HTTPException(status_code=404)
            request.scope["state"][_MATCH_STATE] = _TenantMatch(context, challenge)
        await super().handle(scope, receive, send)


def tenant_match_response_headers(
    scope: Scope, status: int, headers: list[tuple[bytes, bytes]]
) -> list[tuple[bytes, bytes]]:
    """対象応答を保存禁止にし、照合済み成功だけへ証跡を付ける。"""
    state = scope.get("state", {})
    if state.get(_MATCH_ROUTE_STATE) is not True:
        return headers
    result = [
        (name, value)
        for name, value in headers
        if name.lower()
        not in {b"cache-control", _ACK_HEADER, _CHALLENGE_RESPONSE_HEADER}
    ]
    result.append((b"cache-control", b"no-store"))
    matched = state.get(_MATCH_STATE)
    if 200 <= status < 300 and isinstance(matched, _TenantMatch):
        result.extend(
            [
                (_ACK_HEADER, b"1"),
                (_CHALLENGE_RESPONSE_HEADER, matched.challenge.encode("ascii")),
            ]
        )
    return result


def require_tenant_access(
    request: Request,
    response: Response,
    value: Annotated[str, Depends(require_presented_token)],
) -> TenantContext:
    """要求の提示値を照合して製品の入口に文脈を渡す。"""
    matched = request.scope.get("state", {}).get(_MATCH_STATE)
    if isinstance(matched, _TenantMatch):
        return matched.context
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
    request.state.renewed_cookie = response.headers["set-cookie"]
    return context
