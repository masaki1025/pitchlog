"""同じ提示tokenの期限延長だけを許す業務routeの閉宣言。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import MappingProxyType

from starlette.types import Scope

_STATE = "pitchlog_same_token_cookie_route"
_MARKER = object()
_POLICY_PATH = (
    Path(__file__).parents[4] / "contracts/authentication/cookie_identity_v1.json"
)


def _unique_object(pairs):
    """重複keyを補修して宣言を受理しない。"""
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Cookie policyに重複keyがあります")
        value[key] = item
    return value


def _load_policy(path: Path):
    """製品の固定宣言だけを閉検査し、不明な行を失効除外へ足さない。"""
    data = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
    )
    if (
        type(data) is not dict
        or set(data) != {"schemaVersion", "semantics", "operations"}
        or type(data["schemaVersion"]) is not int
        or data["schemaVersion"] != 1
        or data["semantics"] != "same-presented-token-renewal-only"
        or type(data["operations"]) is not list
        or not data["operations"]
    ):
        raise ValueError("Cookie policyの閉形式が不正です")
    by_id = {}
    seen = set()
    for row in data["operations"]:
        if (
            type(row) is not dict
            or set(row) != {"operationId", "method", "path"}
            or type(row["operationId"]) is not str
            or re.fullmatch(r"[a-z][a-z0-9_]*", row["operationId"]) is None
            or type(row["method"]) is not str
            or row["method"] not in {"GET", "POST", "PATCH", "DELETE"}
            or type(row["path"]) is not str
            or re.fullmatch(r"(?:/[a-z0-9-]+|/\{[a-z_]+(?::uuid)?\})+", row["path"])
            is None
            or row["path"].startswith("/auth/")
            or row["operationId"] in by_id
            or (row["method"], row["path"]) in seen
        ):
            raise ValueError("Cookie policyの操作が不正又は重複です")
        by_id[row["operationId"]] = (row["method"], row["path"])
        seen.add((row["method"], row["path"]))
    return MappingProxyType(by_id)


_OPERATIONS = _load_policy(_POLICY_PATH)


def mark_same_token_cookie_route(
    scope: Scope, operation_id: str | None, method: str, path: str
) -> None:
    """実routeと固定宣言が一致する要求だけに私有markerを置く。"""
    if _OPERATIONS.get(operation_id) == (method, path):
        scope.setdefault("state", {})[_STATE] = _MARKER


def same_token_cookie_headers(
    scope: Scope, status: int, headers: list[tuple[bytes, bytes]]
) -> list[tuple[bytes, bytes]]:
    """業務routeのCookieは真正認証が生成した同値更新だけに限定する。"""
    state = scope.get("state", {})
    if state.get(_STATE) is not _MARKER:
        return headers
    result = [(key, value) for key, value in headers if key.lower() != b"set-cookie"]
    # require_tenant_accessが検証した提示token同値/固定属性の更新だけを再掲する。
    cookie = state.get("renewed_cookie")
    if status != 401 and type(cookie) is str:
        result.append((b"set-cookie", cookie.encode("latin-1")))
    return result
