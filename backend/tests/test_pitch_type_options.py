"""球種readのDTO・固定SQL・真正scope・route失敗境界を検査する。"""

from contextlib import contextmanager
from typing import Any, cast

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from pitchlog.api.routers import pitch_type_options as routes
from pitchlog.api.schemas.games import encode_preparation_options_cursor
from pitchlog.api.schemas.pitch_type_options import (
    PitchTypeOption,
    PitchTypeOptionsRequest,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.pitch_type_options import (
    PITCH_TYPE_OPTIONS_OPERATIONS,
    PitchTypeOptionsToken,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction


@pytest.mark.parametrize("limit", [0, 101, True, 1.5, "+1", "1.0"])
def test_bad_limit_is_rejected(limit: Any) -> None:
    """暗黙丸め・clampせず閉じた件数を検査する。"""
    with pytest.raises((ValidationError, ValueError)):
        PitchTypeOptionsRequest(limit=limit)
    with pytest.raises((ValidationError, ValueError)):
        PitchTypeOptionsToken(limit=limit)


def test_query_limit_and_cursor_preserve_normal_http_input() -> None:
    """HTTPの正準整数とUnicodeの不透明cursorを往復する。"""
    cursor = encode_preparation_options_cursor("球種-a")
    assert PitchTypeOptionsRequest(limit="100", cursor=cursor).limit == 100
    with pytest.raises(ValidationError):
        PitchTypeOptionsRequest(cursor="not valid!")
    with pytest.raises(ValidationError):
        PitchTypeOptionsRequest.model_validate({"tenant_id": "foreign"})
    with pytest.raises(ValidationError):
        PitchTypeOption.model_validate({"key": 1, "display_name": "球種"})
    with pytest.raises(ValidationError):
        PitchTypeOption.model_validate(
            {"key": "pitch-a", "display_name": "球種", "category": "pitch_type"}
        )


@pytest.mark.parametrize("cursor", [None, encode_preparation_options_cursor("pitch-a")])
def test_registration_has_closed_tenant_category_enabled_and_page(
    cursor: str | None,
) -> None:
    """他tenant/無効/他categoryをSQLで除外し、上限はlimit+1だけにする。"""
    registration = PITCH_TYPE_OPTIONS_OPERATIONS[0]
    statement, values = registration.prepare(PitchTypeOptionsToken(100, cursor))
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "tenant_id = %(tenant_id)s" in sql
    assert "category = %(category)s" in sql
    assert "disabled = %(disabled)s" in sql
    assert "ORDER BY" in sql and "LIMIT" in sql
    assert values["category"] == "pitch_type"
    assert values["disabled"] is False
    assert values["limit"] == 101
    assert "tenant_id" not in values  # 実executorが真正contextからだけ注入する。
    assert registration.capability_id == "CAP:tenant_vocabularies:read"
    assert registration.required_limit_max == 101
    assert [(b.parameter_name, b.value) for b in registration.required_bindings] == [
        ("category", "pitch_type"),
        ("disabled", False),
    ]
    if cursor:
        assert values["cursor_key"] == "pitch-a"
        assert "key > %(cursor_key)s" in sql
    else:
        assert "cursor_key" not in values
    with pytest.raises(ValueError):
        registration.prepare(cast(TenantOperationToken, object()))
    token = PitchTypeOptionsToken()
    object.__setattr__(token, "limit", 101)
    with pytest.raises(ValidationError):
        registration.prepare(token)


def test_fake_scope_is_rejected_without_execution() -> None:
    """Protocol形だけのscopeで正式readを実行させない。"""

    class Fake:
        def run(self, _token: object) -> object:
            pytest.fail("偽scopeを実行した")

    with pytest.raises(TypeError):
        routes.read_pitch_type_options(
            cast(_TenantTransaction, Fake()), PitchTypeOptionsRequest()
        )


def test_real_scope_shape_pages_and_encodes_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unitでは実scope型のrunだけを注入し、DTOとページ組立を検査する。"""
    observed = []

    def run(_self: object, token: object) -> TenantOperationResult:
        observed.append(token)
        return TenantOperationResult((("a", "直球"), ("b", "変化球")))

    monkeypatch.setattr(_TenantTransaction, "run", run)
    scope = object.__new__(_TenantTransaction)
    page = routes.read_pitch_type_options(scope, PitchTypeOptionsRequest(limit=1))
    assert page.model_dump() == {
        "items": [{"key": "a", "display_name": "直球"}],
        "next_cursor": encode_preparation_options_cursor("a"),
    }
    assert type(observed[0]) is PitchTypeOptionsToken


@pytest.mark.parametrize(
    "rows",
    [
        (("a", "A", "extra"),),
        (("b", "B"), ("a", "A")),
        (("a", "A"), ("a", "A")),
        (("a", "A"), ("b", "B"), ("c", "C")),
    ],
)
def test_bad_read_results_are_not_exposed(
    rows: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """余剰列・逆順・重複・過剰件数を補修せず拒否する。"""
    monkeypatch.setattr(
        _TenantTransaction, "run", lambda _self, _token: TenantOperationResult(rows)
    )
    with pytest.raises((ValueError, ValidationError)):
        routes.read_pitch_type_options(
            object.__new__(_TenantTransaction), PitchTypeOptionsRequest(limit=1)
        )


def test_route_preserves_fixed_503_on_read_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rollback後にDB原値/例外をresponseへ流さない。"""

    @contextmanager
    def broken(_context: object):
        raise RuntimeError("private-material-marker")
        yield

    monkeypatch.setattr(routes, "tenant_transaction_scope", broken)
    with pytest.raises(HTTPException) as caught:
        routes.pitch_type_options(
            PitchTypeOptionsRequest(), cast(TenantContext, object())
        )
    assert caught.value.status_code == 503
    assert "private-material-marker" not in str(caught.value)
    route = cast(APIRoute, routes.router.routes[0])
    assert route.path == "/vocabularies/pitch-types"
    assert route.operation_id == "pitch_type_options"
