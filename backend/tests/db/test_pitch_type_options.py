"""owned製品DBと実認証・C2を通した球種の有限readを検査する。"""

from __future__ import annotations

import json
import subprocess
from uuid import uuid4

import psycopg
import pytest

from .test_first_ball_vertical_http import _app_arguments
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db

_SCRIPT = r"""
import asyncio, base64, json, os, sys
from uuid import uuid4
from httpx import AsyncClient, ASGITransport

case = json.loads(os.environ["PITCHLOG_VERTICAL_CASE"])
assert os.geteuid() == 20003 and os.getegid() == 20003
os.environ["PITCHLOG_TOKEN_SIGNING_KEY_B64"] = base64.b64encode(
    bytes(range(32))
).decode()
os.environ["PITCHLOG_ALLOWED_ORIGINS"] = "https://test"
os.environ["PITCHLOG_DATABASE_URL"] = (
    "postgresql+psycopg://pitchlog_app@/ledger_fixture?host=%2Fbusiness-socket&sslmode=disable"
)
os.environ["PITCHLOG_DATABASE_POOLED"] = "false"
from pitchlog.api.app import create_app
from pitchlog.api.schemas.games import encode_preparation_options_cursor

app = create_app()


def hook(kind, value, tb):
    # 資格・原要求・原例外をログへ出さない。失敗は型だけで終結する。
    print(json.dumps({"fixture_failure": kind.__name__}), flush=True)


sys.excepthook = hook


def headers(tenant):
    return {
        "Origin": "https://test",
        "X-Pitchlog-Request": "1",
        "X-Pitchlog-Expected-Tenant": tenant,
        "X-Pitchlog-Tenant-Challenge": str(uuid4()),
    }


async def login(client, team):
    response = await client.post(
        "/auth/login",
        headers={"Origin": "https://test", "X-Pitchlog-Request": "1"},
        json={"team_name": team, "password": "public-owned-vertical-password-A1"},
    )
    assert response.status_code == 200


async def read(client, tenant, params):
    h = headers(tenant)
    response = await client.get("/vocabularies/pitch-types", headers=h, params=params)
    if response.status_code == 200:
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["X-Pitchlog-Tenant-Match"] == "1"
        assert (
            response.headers["X-Pitchlog-Tenant-Challenge"]
            == h["X-Pitchlog-Tenant-Challenge"]
        )
    return response


async def main():
    tenant = case["tenant"]
    other = case["other_tenant"]
    cursor = encode_preparation_options_cursor("zz-owned-before")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        denied = await client.get("/vocabularies/pitch-types", params={"limit": "bad"})
        assert denied.status_code == 401
        await login(client, case["team_name"])
        first = await read(client, tenant, {"limit": 1, "cursor": cursor})
        assert first.status_code == 200
        assert first.json() == {
            "items": [{"key": "zz-owned-pitch-a", "display_name": "A直球"}],
            "next_cursor": encode_preparation_options_cursor("zz-owned-pitch-a"),
        }
        assert first.json()["next_cursor"] != "zz-owned-pitch-a"
        second = await read(
            client, tenant, {"limit": 1, "cursor": first.json()["next_cursor"]}
        )
        assert second.status_code == 200
        assert second.json() == {
            "items": [{"key": "zz-owned-pitch-b", "display_name": "A変化球"}],
            "next_cursor": None,
        }
        all_ = await read(client, tenant, {"limit": 100, "cursor": cursor})
        assert all_.status_code == 200
        assert all_.json() == {
            "items": first.json()["items"] + second.json()["items"],
            "next_cursor": None,
        }
        for bad in [0, 101, "bad"]:
            response = await read(client, tenant, {"limit": bad})
            assert response.status_code == 422
        invalid_cursor = await read(client, tenant, {"cursor": "invalid!", "limit": 1})
        assert invalid_cursor.status_code == 422
        crossed = await read(client, other, {"limit": "bad"})
        assert crossed.status_code == 404
        assert "X-Pitchlog-Tenant-Match" not in crossed.headers
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        await login(client, case["other_team_name"])
        foreign = await read(client, other, {"limit": 100, "cursor": cursor})
        assert foreign.status_code == 200
        assert foreign.json() == {
            "items": [{"key": "zz-owned-pitch-a", "display_name": "B球種"}],
            "next_cursor": None,
        }
    print(
        json.dumps(
            {
                "checks": [
                    "real-login-two-tenants",
                    "normal-page",
                    "opaque-cursor",
                    "disabled-and-category-filter",
                    "limit",
                    "invalid-cursor",
                    "c2-cross-tenant",
                ],
                "page_sizes": [1, 1, 2, 1],
            }
        ),
        flush=True,
    )


asyncio.run(main())
"""


def test_pitch_type_real_get_is_paged_and_tenant_scoped(vertical_database) -> None:
    """実app/Cookie/SQL/owned PGで他tenant・他区分・無効行を除外する。"""
    db = vertical_database
    # 固定prefixの後ろに置き、既fixtureのu06球種を壊さずページを検証する。
    rows = (
        (db.tenant_id, "zz-owned-pitch-a", "pitch_type", "A直球", "fastball", False),
        (db.tenant_id, "zz-owned-pitch-b", "pitch_type", "A変化球", "fastball", False),
        (
            db.tenant_id,
            "zz-owned-pitch-disabled",
            "pitch_type",
            "無効",
            "fastball",
            True,
        ),
        (db.tenant_id, "zz-owned-strategy", "strategy", "戦術", None, False),
        (
            db.other_tenant_id,
            "zz-owned-pitch-a",
            "pitch_type",
            "B球種",
            "fastball",
            False,
        ),
    )
    with psycopg.connect(db.authority.database.business_admin) as admin:
        with admin.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO public.tenant_vocabularies "
                "(tenant_id,key,category,display_name,pitch_family,disabled) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                rows,
            )
        before = admin.execute(
            "SELECT tenant_id,key,category,display_name,disabled "
            "FROM public.tenant_vocabularies ORDER BY tenant_id,key"
        ).fetchall()
    case = {
        "tenant": str(db.tenant_id),
        "other_tenant": str(db.other_tenant_id),
        "team_name": db.team_name,
        "other_team_name": db.other_team_name,
        "fixture_run": str(uuid4()),
    }
    process = subprocess.run(  # noqa: S603
        ["docker", *_app_arguments(db, case), "-u", "-c", _SCRIPT],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert process.returncode == 0, "球種実readの隔離appが失敗しました"
    result = json.loads(process.stdout)
    assert result["page_sizes"] == [1, 1, 2, 1]
    assert len(result["checks"]) == 7
    with psycopg.connect(db.authority.database.business_admin) as admin:
        after = admin.execute(
            "SELECT tenant_id,key,category,display_name,disabled "
            "FROM public.tenant_vocabularies ORDER BY tenant_id,key"
        ).fetchall()
    assert after == before, "GETが語彙行を書き換えました"
