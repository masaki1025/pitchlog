"""前回スタメンの公開 GET を実 DB と認証済み要求で検証する。"""

from __future__ import annotations

import base64
import json
import secrets
from typing import cast
from uuid import UUID, uuid4

import pytest
from db.test_product_authz_authn_app import (
    _app_dsn,
    _login,
    _seed_identity,
    _seed_settings,
)
from db_fixtures import (
    ProvisionedProductCatalog,
    _product_migration_url,
    disposable_postgres_cluster,
    provisioned_product_catalog,
)
from httpx import ASGITransport, AsyncClient

from pitchlog.api.app import create_app
from pitchlog.authz.token_presentation import TokenPresentation

_ORIGIN = "https://lineup-memory.example"
__all__ = ("disposable_postgres_cluster", "provisioned_product_catalog")


@pytest.mark.requires_db
@pytest.mark.anyio
async def test_get_lineup_memory_restores_only_current_active_self_players(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保存順と位置を保ち、越境・非現役・非表示・欠損を差し替えにする。"""
    catalog = cast(
        ProvisionedProductCatalog,
        request.getfixturevalue("provisioned_product_catalog"),
    )
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    tenant_a = _seed_identity(catalog, app_dsn)
    tenant_b = _seed_identity(catalog, app_dsn)
    token_a = _login(tenant_a)
    token_b = _login(tenant_b)
    assert isinstance(token_a, UUID)
    assert isinstance(token_b, UUID)

    team_a, team_b, opponent = (uuid4() for _ in range(3))
    active, ob, other, hidden, foreign_team, missing, tenant_b_player, dh_pitcher = (
        uuid4() for _ in range(8)
    )
    lineup: list[dict[str, object]] = [
        {
            "player_id": str(player_id),
            "batting_order": order,
            "fielding_position": position,
        }
        for order, (player_id, position) in enumerate(
            (
                (active, {"code": "catcher", "meta": [1, "C"]}),
                (ob, "first"),
                (other, "second"),
                (hidden, "third"),
                (foreign_team, "short"),
                (missing, "left"),
                (tenant_b_player, "right"),
            ),
            start=1,
        )
    ]
    lineup.append(
        {
            "player_id": str(dh_pitcher),
            "batting_order": None,
            "fielding_position": [1, {"role": "pitcher"}],
        }
    )
    with catalog.applicator.cursor() as cursor:
        for tenant_id, team_id, kind, hidden_at in (
            (tenant_a.tenant_id, team_a, "self", False),
            (tenant_a.tenant_id, opponent, "opponent", False),
            (tenant_b.tenant_id, team_b, "self", False),
        ):
            cursor.execute(
                "INSERT INTO team_records (tenant_id, id, kind, name, hidden_at) "
                "VALUES (%s, %s, %s, %s, "
                "CASE WHEN %s THEN pg_catalog.clock_timestamp() ELSE NULL END)",
                (tenant_id, team_id, kind, f"team-{team_id.hex}", hidden_at),
            )
        for tenant_id, player_id, team_id, name, number, status, hidden_at in (
            (tenant_a.tenant_id, active, team_a, "旧名", "7", "active", False),
            (tenant_a.tenant_id, ob, team_a, "OB", "2", "ob", False),
            (tenant_a.tenant_id, other, team_a, "その他", "3", "other", False),
            (tenant_a.tenant_id, hidden, team_a, "非表示", "4", "active", True),
            (tenant_a.tenant_id, foreign_team, opponent, "相手", "5", "active", False),
            (tenant_b.tenant_id, tenant_b_player, team_b, "越境", "6", "active", False),
        ):
            cursor.execute(
                "INSERT INTO players (tenant_id, id, team_record_id, name, "
                "uniform_number, roster_status_key, hidden_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, "
                "CASE WHEN %s THEN pg_catalog.clock_timestamp() ELSE NULL END)",
                (tenant_id, player_id, team_id, name, number, status, hidden_at),
            )
        cursor.execute(
            "INSERT INTO lineup_memories "
            "(tenant_id, id, team_record_id, lineup, migration_preserved_only) "
            "VALUES (%s, %s, %s, %s::jsonb, false)",
            (tenant_a.tenant_id, uuid4(), team_a, json.dumps(lineup)),
        )
        cursor.execute(
            "UPDATE players SET name = %s, uniform_number = %s "
            "WHERE tenant_id = %s AND id = %s",
            ("新しい名前", "42", tenant_a.tenant_id, active),
        )
    catalog.applicator.commit()

    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL", f"{_product_migration_url(app_dsn)}?sslmode=disable"
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", _ORIGIN)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    app = create_app()
    signer: TokenPresentation = app.state.token_presentation
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/team-records/{team_a}/lineup-memory"
        assert (await client.get(path)).status_code == 401
        client.cookies.set("__Host-pitchlog_token", signer.encode(token_a))
        response = await client.get(path)
        assert response.status_code == 200
        entries = response.json()["entries"]
        assert len(entries) == 8
        assert [entry["batting_order"] for entry in entries] == [*range(1, 8), None]
        assert [entry["fielding_position"] for entry in entries] == [
            slot["fielding_position"] for slot in lineup
        ]
        assert entries[0] == {
            "batting_order": 1,
            "fielding_position": {"code": "catcher", "meta": [1, "C"]},
            "player_id": str(active),
            "name": "新しい名前",
            "uniform_number": "42",
            "replacement_required": False,
        }
        for entry in entries[1:]:
            assert entry["player_id"] is None
            assert entry["name"] is None
            assert entry["uniform_number"] is None
            assert entry["replacement_required"] is True
        assert entries[-1]["fielding_position"] == [1, {"role": "pitcher"}]
        assert "tenant_id" not in response.text

        for rejected in (opponent, team_b, uuid4()):
            assert (
                await client.get(f"/team-records/{rejected}/lineup-memory")
            ).status_code == 404
        assert (await client.post(path, json=lineup)).status_code == 405

        client.cookies.set("__Host-pitchlog_token", signer.encode(token_b))
        assert (await client.get(path)).status_code == 404
        assert (
            await client.get(f"/team-records/{team_b}/lineup-memory")
        ).status_code == 204

        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "UPDATE lineup_memories SET migration_preserved_only = true "
                "WHERE tenant_id = %s AND team_record_id = %s",
                (tenant_a.tenant_id, team_a),
            )
        catalog.applicator.commit()
        client.cookies.set("__Host-pitchlog_token", signer.encode(token_a))
        assert (await client.get(path)).status_code == 204
