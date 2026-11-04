"""打球語彙の閉DTO・固定関数・認証C2候補の純粋境界を検証する。"""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from pitchlog.api import tenant_access
from pitchlog.api.errors import register_exception_handlers
from pitchlog.api.routers import batted_ball_options as routes
from pitchlog.api.schemas.batted_ball_options import (
    BattedBallOption,
    BattedBallOptionsRequest,
)
from pitchlog.api.schemas.games import encode_preparation_options_cursor
from pitchlog.repositories.batted_ball_options import (
    BATTED_BALL_OPTIONS_OPERATIONS,
    BattedBallOptionsToken,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    build_function_registry,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction


@pytest.mark.parametrize("limit", [0, 101, True, 1.5, "+1", "1.0"])
def test_bad_limit(limit: Any) -> None:
    """clamp・型補修をせず上限とexact整数を拒否する。"""
    with pytest.raises((ValidationError, ValueError)):
        BattedBallOptionsRequest(limit=limit)
    with pytest.raises((ValidationError, ValueError)):
        BattedBallOptionsToken(page_size=limit)


@pytest.mark.parametrize("field", ["tenant_id", "category", "disabled"])
def test_closed_request_and_dto(field: str) -> None:
    """category/tenantを外部入力で選ばせず未知fieldを拒否する。"""
    with pytest.raises(ValidationError):
        BattedBallOptionsRequest.model_validate({field: "foreign"})
    with pytest.raises(ValidationError):
        BattedBallOption.model_validate(
            {"key": "a", "display_name": "打球", field: "x"}
        )


def test_http_and_cursor_shapes() -> None:
    """既opaque cursorとHTTP正準整数を消費する。"""
    cursor = encode_preparation_options_cursor("打球-a")
    assert BattedBallOptionsRequest(limit="100", cursor=cursor).limit == 100
    for invalid in ("!", "", "YQ==", True, 1):
        with pytest.raises(ValidationError):
            BattedBallOptionsRequest.model_validate({"cursor": invalid})
    for key, name in ((1, "打球"), ("", "打球"), ("a", ""), ("a", 1)):
        with pytest.raises(ValidationError):
            BattedBallOption.model_validate({"key": key, "display_name": name})


def test_fixed_function_binding() -> None:
    """直接global SELECTにせずscopeだけがtenantを注入する。"""
    spec = BATTED_BALL_OPTIONS_OPERATIONS[0]
    registry = build_function_registry((spec,), frozenset())
    _, params = prepare_function_operation(
        BattedBallOptionsToken(100, "打球-a"), UUID(int=1), registry
    )
    assert params == {
        "tenant_id": UUID(int=1),
        "page_size": 100,
        "cursor_key": "打球-a",
    }
    sql = str(spec.statement.compile(dialect=postgresql.dialect()))
    assert "recording_vocab_api.read_batted_ball_options" in sql
    assert "admin_vocabularies" not in sql
    assert spec.capability_id == "CAP:recording_vocabularies:read"
    assert spec.result_fields == (("key", str), ("display_name", str))
    assert (spec.min_rows, spec.max_rows) == (0, 101)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(cast(Any, object()), UUID(int=1), registry)
    for name, value in (
        ("page_size", 101),
        ("page_size", True),
        ("cursor_key", None),
        ("cursor_key", "a\x00"),
    ):
        token = BattedBallOptionsToken()
        object.__setattr__(token, name, value)
        with pytest.raises((ValueError, ValidationError)):
            prepare_function_operation(token, UUID(int=1), registry)
    with pytest.raises(FunctionOperationError):
        replace(spec, statement=spec.statement.limit(100))


@pytest.mark.parametrize(
    "rows",
    [(("a", 1),), (("a", "A", "extra"),), tuple((str(i), "A") for i in range(102))],
)
def test_fixed_decoder_refuses_bad_result(rows: Any) -> None:
    """未知列/型/上限を共通decoderでも検査する。"""
    with pytest.raises(FunctionOperationError):
        decode_function_result(
            BATTED_BALL_OPTIONS_OPERATIONS[0], TenantOperationResult(rows)
        )


def test_pages_keep_names_and_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    """同admin categoryの結果を分類し直さず表示名のまま返す。"""
    seen = []

    def run(_self: object, token: object) -> TenantOperationResult:
        seen.append(token)
        return TenantOperationResult((("b", "ライナー"), ("c", "強い")))

    monkeypatch.setattr(_TenantTransaction, "run_function", run)
    page = routes.read_batted_ball_options(
        object.__new__(_TenantTransaction),
        BattedBallOptionsRequest(
            limit=1, cursor=encode_preparation_options_cursor("a")
        ),
    )
    assert page.model_dump() == {
        "items": [{"key": "b", "display_name": "ライナー"}],
        "next_cursor": encode_preparation_options_cursor("b"),
    }
    assert seen == [BattedBallOptionsToken(1, "a")]


@pytest.mark.parametrize(
    "rows",
    [
        (("b", "B"), ("a", "A")),
        (("b", "B"), ("b", "B")),
        (("a", "A"),),
        (("b", "B"), ("c", "C"), ("d", "D")),
        (("b", ""),),
        ((1, "B"),),
        (("b", "B", "extra"),),
    ],
)
def test_invalid_page_is_not_repaired(
    rows: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cursor以前/逆順/重複/過剰/空表示/未知型を成功化しない。"""
    monkeypatch.setattr(
        _TenantTransaction, "run_function", lambda *_: TenantOperationResult(rows)
    )
    with pytest.raises((ValueError, ValidationError)):
        routes.read_batted_ball_options(
            object.__new__(_TenantTransaction),
            BattedBallOptionsRequest(
                limit=1, cursor=encode_preparation_options_cursor("a")
            ),
        )


def test_fake_scope_and_fixed_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """自由scopeを拒否し、失敗を固定503にしてDB材料を漏らさない。"""
    with pytest.raises(TypeError):
        routes.read_batted_ball_options(cast(Any, object()), BattedBallOptionsRequest())

    @contextmanager
    def broken(_context: object):
        raise RuntimeError("private-marker")
        yield

    monkeypatch.setattr(routes, "tenant_transaction_scope", broken)
    with pytest.raises(HTTPException) as caught:
        routes.batted_ball_options(
            BattedBallOptionsRequest(), cast(TenantContext, object())
        )
    assert caught.value.status_code == 503
    assert "private-marker" not in str(caught.value)


def test_real_auth_dependency_and_candidate_c2(monkeypatch: pytest.MonkeyPatch) -> None:
    """未認証拒否と、root登録候補のC2先行照合を実routeで区別する。"""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(routes.router)
    route = cast(APIRoute, routes.router.routes[0])
    assert type(route) is tenant_access.TenantMatchedRoute
    assert route.operation_id == "batted_ball_options"
    assert any(
        d.call is tenant_access.require_tenant_access
        for d in route.dependant.dependencies
    )
    client = TestClient(app)
    assert client.get("/vocabularies/batted-balls").status_code == 401
    context = SimpleNamespace(tenant_id=UUID(int=1))

    async def presented(_request: object) -> object:
        return object()

    original = tenant_access.require_tenant_access
    monkeypatch.setattr(tenant_access, "require_presented_token", presented)
    monkeypatch.setattr(tenant_access, "require_tenant_access", lambda *_: context)
    monkeypatch.setattr(
        tenant_access,
        "_MATCH_OPERATIONS",
        tenant_access._MATCH_OPERATIONS | {"batted_ball_options"},
    )
    app.dependency_overrides[original] = lambda: context
    headers = {
        "X-Pitchlog-Expected-Tenant": str(UUID(int=2)),
        "X-Pitchlog-Tenant-Challenge": str(UUID(int=3)),
    }
    assert (
        client.get("/vocabularies/batted-balls?limit=bad", headers=headers).status_code
        == 404
    )
    headers["X-Pitchlog-Expected-Tenant"] = str(UUID(int=1))
    assert (
        client.get("/vocabularies/batted-balls?limit=bad", headers=headers).status_code
        == 422
    )


def test_empty_page_and_tampered_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """欠測を固定候補へ置換せず、構築後改竄を実行前に拒否する。"""
    observed = []

    def run(_self: object, token: object) -> TenantOperationResult:
        observed.append(token)
        return TenantOperationResult(())

    monkeypatch.setattr(_TenantTransaction, "run_function", run)
    scope = object.__new__(_TenantTransaction)
    query = BattedBallOptionsRequest()
    assert routes.read_batted_ball_options(scope, query).model_dump() == {
        "items": [],
        "next_cursor": None,
    }
    with pytest.raises(ValidationError):
        routes.read_batted_ball_options(scope, query.model_copy(update={"limit": 101}))
    assert len(observed) == 1
