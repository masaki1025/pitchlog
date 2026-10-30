"""自チーム読み取りの固定SQLと公開HTTP境界を検査する。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.selectable import Select
from test_roster_boundary import (
    _TENANT_A,
    _TENANT_B,
    _client_app,
    _metadata_headers,
    _PlayerStore,
)

from pitchlog.api import tenant_access
from pitchlog.api.routers import team_records
from pitchlog.repositories.base import _prepare_operation
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.roster import SelfTeamRecordReadToken, TeamRecordReadToken
from pitchlog.repositories.tokens import ImmutableValue, TenantOperationResult

_SELF_ID = UUID("44444444-4444-4444-8444-444444444444")
_ACK = "x-pitchlog-tenant-match"
_CHALLENGE = "x-pitchlog-tenant-challenge"


def test_tenant_match_operations_keep_old_routes_and_add_self() -> None:
    """C2の旧対象と開始/enroll/resolveの採用済3入口を完全照合する。"""
    assert tenant_access._MATCH_OPERATIONS == frozenset(
        {
            "roster_team_list",
            "roster_team_create",
            "roster_team_update",
            "roster_player_list",
            "roster_player_create",
            "roster_player_read",
            "roster_player_update",
            "roster_self_team_read",
            "preparing_game_list",
            "preparing_game_detail",
            "initial_device_enroll",
            "initial_game_start",
            "initial_game_start_resolve",
        }
    )


def test_self_token_has_no_variable_arguments_and_is_frozen() -> None:
    """端末のtenant・ID・kind・limitをtokenへ渡せない。"""
    token = SelfTeamRecordReadToken()
    assert token.capability_id == TeamRecordReadToken(1).capability_id
    for keyword in ("tenant_id", "record_id", "kind", "limit", "include_hidden"):
        with pytest.raises(TypeError):
            SelfTeamRecordReadToken(**{keyword: "untrusted"})
    with pytest.raises(TypeError):
        cast(Any, SelfTeamRecordReadToken)(_SELF_ID)
    with pytest.raises((FrozenInstanceError, TypeError, AttributeError)):
        setattr(token, "capability_id", "CAP:team_records:update")


def test_self_statement_has_context_bind_and_fixed_predicates() -> None:
    """業務SQLが認証文脈のtenantとself・公開・1件に閉じる。"""
    statement, parameters = _prepare_operation(SelfTeamRecordReadToken(), _TENANT_A)
    assert isinstance(statement, Select)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert parameters == {"tenant_id": _TENANT_A, "kind": "self", "limit": 1}
    assert "team_records.tenant_id = %(tenant_id)s" in sql
    assert "team_records.kind = %(kind)s" in sql
    assert "team_records.hidden_at IS NULL" in sql
    assert "LIMIT %(limit)s" in sql
    assert "record_id" not in sql and "include_hidden" not in sql
    assert tuple(column.name for column in statement.selected_columns) == (
        "id",
        "kind",
        "name",
        "hidden_at",
    )


class _SelfRows:
    """HTTP境界に実体化済み結果を渡し、実行回数を記録する。"""

    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.rows = rows
        self.calls: list[tuple[UUID, object]] = []

    def result(self, tenant_id: UUID, operation: object) -> TenantOperationResult:
        """要求tenantとtokenを記録して注入行を返す。"""
        self.calls.append((tenant_id, operation))
        assert type(operation) is SelfTeamRecordReadToken
        return TenantOperationResult(
            cast(tuple[tuple[ImmutableValue, ...], ...], self.rows)
        )


def _self_app(monkeypatch: pytest.MonkeyPatch, store: _SelfRows):
    """既存公開アプリの業務実行だけを注入結果へ置き換える。"""
    app = _client_app(monkeypatch, _PlayerStore())

    @contextmanager
    def scope(context: TenantContext) -> Iterator[object]:
        class Handle:
            def run(self, operation: object) -> TenantOperationResult:
                return store.result(context.tenant_id, operation)

        yield Handle()

    monkeypatch.setattr(team_records, "tenant_transaction_scope", scope)
    return app


@pytest.mark.anyio
async def test_self_http_one_row_and_openapi(monkeypatch: pytest.MonkeyPatch) -> None:
    """1行だけ既存DTOの4項目とC2成功証跡を返す。"""
    store = _SelfRows(((_SELF_ID, "self", "自チーム", None),))
    app = _self_app(monkeypatch, store)
    operation = app.openapi()["paths"]["/team-records/self"]["get"]
    assert operation["operationId"] == "roster_self_team_read"
    assert operation["responses"]["200"]["content"]["application/json"] == {
        "schema": {"$ref": "#/components/schemas/TeamRecordRead"}
    }
    assert "parameters" not in operation
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        headers = _metadata_headers(_TENANT_A)
        response = await client.get(
            "/team-records/self",
            headers=headers,
            params={
                "tenant_id": str(_TENANT_B),
                "record_id": str(uuid4()),
                "kind": "opponent",
                "limit": "200",
                "include_hidden": "true",
            },
        )
    assert response.status_code == 200
    assert response.json() == {
        "id": str(_SELF_ID),
        "kind": "self",
        "name": "自チーム",
        "hidden_at": None,
    }
    assert response.headers[_ACK] == "1"
    assert response.headers[_CHALLENGE] == headers["X-Pitchlog-Tenant-Challenge"]
    assert response.headers["cache-control"] == "no-store"
    assert len(store.calls) == 1 and store.calls[0][0] == _TENANT_A


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("rows", "status"),
    [
        ((), 404),
        (((_SELF_ID, "self", "甲", None), (_SELF_ID, "self", "乙", None)), 500),
        (((_SELF_ID, "opponent", "甲", None),), 500),
        (((_SELF_ID, "self", "甲", "hidden"),), 500),
        (((_SELF_ID, "self", 123, None),), 500),
        (((str(_SELF_ID), "self", "甲", None),), 500),
        (((_SELF_ID, "self", "甲"),), 500),
        (((_SELF_ID, "self", "甲", None, "extra"),), 500),
    ],
)
async def test_self_http_rejects_missing_and_bad_materialized_results(
    monkeypatch: pytest.MonkeyPatch,
    rows: tuple[tuple[object, ...], ...],
    status: int,
) -> None:
    """0行は404、複数行や不正形は内容を隠した5xxで拒否する。"""
    store = _SelfRows(rows)
    app = _self_app(monkeypatch, store)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.get(
            "/team-records/self", headers=_metadata_headers(_TENANT_A)
        )
    assert response.status_code == status
    assert "甲" not in response.text and "乙" not in response.text
    assert str(_SELF_ID) not in response.text
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert len(store.calls) == 1


@pytest.mark.anyio
async def test_self_http_auth_and_c2_precede_business_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未認証・欠落metadata・別tenantは業務SQLを呼ばない。"""
    store = _SelfRows(((_SELF_ID, "self", "自チーム", None),))
    app = _self_app(monkeypatch, store)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        missing_auth = await client.get("/team-records/self")
        client.cookies.set("__Host-pitchlog_token", "token-a")
        missing_metadata = await client.get("/team-records/self")
        wrong_tenant = await client.get(
            "/team-records/self", headers=_metadata_headers(_TENANT_B)
        )
        malformed = await client.get(
            "/team-records/self",
            headers={
                "X-Pitchlog-Expected-Tenant": str(_TENANT_A),
                "X-Pitchlog-Tenant-Challenge": "not-a-uuid",
            },
        )
    assert missing_auth.status_code == 401
    assert missing_metadata.status_code == wrong_tenant.status_code == 404
    assert malformed.status_code == 404
    for response in (missing_auth, missing_metadata, wrong_tenant, malformed):
        assert _ACK not in response.headers and _CHALLENGE not in response.headers
        assert response.headers["cache-control"] == "no-store"
    assert store.calls == []


@pytest.mark.anyio
async def test_self_path_does_not_expand_opponent_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """selfの静的経路をUUIDの更新・削除へ解釈しない。"""
    store = _SelfRows(())
    app = _self_app(monkeypatch, store)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        headers = _metadata_headers(_TENANT_A)
        assert (
            await client.patch("/team-records/self", headers=headers)
        ).status_code == 405
        assert (
            await client.delete("/team-records/self", headers=headers)
        ).status_code == 405
        assert (
            await client.get(f"/team-records/{uuid4()}", headers=headers)
        ).status_code == 405
    assert store.calls == []
