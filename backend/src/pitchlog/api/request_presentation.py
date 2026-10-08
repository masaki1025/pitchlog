"""要求から提示値を取り出し、状態変更要求の CSRF 条件を確認する。"""

import ipaddress
import os
import re
from typing import Literal

from fastapi import Request

_COOKIE_NAME = "__Host-pitchlog_token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_REQUEST_HEADER = "X-Pitchlog-Request"
_ALLOWED_ORIGINS_VARIABLE = "PITCHLOG_ALLOWED_ORIGINS"
_DNS_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_ORIGIN_PATTERN = re.compile(
    rf"(?P<scheme>https?)://(?:"
    rf"(?P<dns>{_DNS_LABEL}(?:\.{_DNS_LABEL})*)"
    rf"|\[(?P<ipv6>[0-9A-Fa-f:.]+)\])"
    rf"(?::(?P<port>[1-9][0-9]{{0,4}}))?",
    flags=re.ASCII | re.IGNORECASE,
)


def _serialize_allowed_origin(value: str) -> str | None:
    """有効な設定値をオリジンの ASCII シリアライズ形へ変換する。

    Args:
        value: 設定に含まれる候補。

    Returns:
        シリアライズしたオリジン。不正な設定値なら None。
    """
    match = _ORIGIN_PATTERN.fullmatch(value)
    if match is None:
        return None

    scheme = match.group("scheme").lower()
    dns = match.group("dns")
    if dns is not None:
        if len(dns) > 253:
            return None
        serialized_host = dns.lower()
    else:
        ipv6 = match.group("ipv6")
        if ipv6 is None:
            return None
        try:
            serialized_host = f"[{ipaddress.IPv6Address(ipv6).compressed}]"
        except ipaddress.AddressValueError:
            return None

    port_text = match.group("port")
    port = int(port_text) if port_text is not None else None
    if port is not None and port > 65535:
        return None
    default_port = 80 if scheme == "http" else 443
    port_suffix = "" if port is None or port == default_port else f":{port}"
    return f"{scheme}://{serialized_host}{port_suffix}"


class RequestGateError(Exception):
    """要求面での拒否理由だけを保持する。"""

    def __init__(self, reason: Literal["credential", "csrf"]) -> None:
        """値を含まない拒否理由を保持する。

        Args:
            reason: 認証情報または CSRF 条件の拒否理由。
        """
        self.reason = reason
        super().__init__()


async def require_presented_token(request: Request) -> str:
    """提示値を不透明な文字列として取り出す。

    Args:
        request: HTTP 要求。

    Returns:
        Cookie に入っていた提示値。

    Raises:
        RequestGateError: Cookie または状態変更要求の条件が不足する場合。
    """
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise RequestGateError("credential")

    if request.method not in _SAFE_METHODS:
        if request.headers.get(_REQUEST_HEADER) != "1":
            raise RequestGateError("csrf")

        origin = request.headers.get("Origin")
        configured = os.environ.get(_ALLOWED_ORIGINS_VARIABLE, "")
        allowed_origins: set[str] = set()
        for value in configured.split(","):
            serialized = _serialize_allowed_origin(value.strip())
            if serialized is not None:
                allowed_origins.add(serialized)
        if origin is None or origin == "null" or origin not in allowed_origins:
            raise RequestGateError("csrf")

    return token
