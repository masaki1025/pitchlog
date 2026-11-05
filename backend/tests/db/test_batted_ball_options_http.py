"""実認証と製品SECDEFを経由する打球語彙ページをowned PGで確認する。"""

import json
import subprocess

import psycopg
import pytest

from .test_first_ball_vertical_http import (
    _APP_SCRIPT,
    _PASSWORD,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import admin_connection as admin_connection
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)
from .test_ordinary_pitch_vertical_http import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db

_READ_SCRIPT = (
    _APP_SCRIPT.split("async def run():")[0]
    + r"""
async def run():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        unauthenticated = await client.get("/vocabularies/batted-balls")
        assert unauthenticated.status_code == 401
        logged = await login(client, team)
        assert logged.status_code == 200
        wrong = headers()
        wrong["X-Pitchlog-Expected-Tenant"] = case["other_tenant"]
        rejected = await client.get("/vocabularies/batted-balls", headers=wrong)
        assert rejected.status_code == 404
        malformed = await client.get(
            "/vocabularies/batted-balls", params={"cursor": "!!"}, headers=headers()
        )
        assert malformed.status_code == 422
        keys = []
        cursor = None
        sizes = []
        for page in range(10):
            query = {"limit": 31}
            if cursor is not None:
                query["cursor"] = cursor
            response = await client.get(
                "/vocabularies/batted-balls", params=query, headers=headers()
            )
            assert response.status_code == 200, ("page", response.status_code)
            value = response.json()
            assert set(value) == {"items", "next_cursor"}
            assert len(value["items"]) <= 31
            sizes.append(len(value["items"]))
            for item in value["items"]:
                assert set(item) == {"key", "display_name"}
                keys.append(item["key"])
            cursor = value["next_cursor"]
            if cursor is None:
                break
        else:
            raise AssertionError("finite fixture pages exhausted")
        assert keys == sorted(set(keys))
        selected = [key for key in keys if key.startswith("batted.http.")]
        assert selected == case["expected_keys"]
        assert len(sizes) >= 5
        return {"pages": len(sizes), "sizes": sizes, "selected": selected,
                "unauthenticated": 401, "mismatched_tenant": 404,
                "malformed_cursor": 422}

print(json.dumps(asyncio.run(run()), ensure_ascii=False))
"""
)


def test_real_batted_vocabulary_pages_and_direct_write_denial(
    vertical_database,
) -> None:
    """参照語彙だけを準備し、実HTTPのページ列とDB直接書込拒否を確かめる。"""
    db = vertical_database
    expected = [f"batted.http.{index:03d}" for index in range(130)]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for key in expected:
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batted_ball',%s)",
                (key, key),
            )
        for key, category, disabled in (
            ("batted.http.disabled", "batted_ball", True),
            ("batted.http.wrong-category", "season", False),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies"
                "(key,category,display_name,disabled) VALUES (%s,%s,%s,%s)",
                (key, category, key, disabled),
            )
        index = admin.execute(
            "SELECT indexdef FROM pg_catalog.pg_indexes WHERE schemaname='public' "
            "AND indexname='ix_admin_vocabularies_batted_ball_key_c'"
        ).fetchone()
        assert index is not None
        assert 'COLLATE "C"' in index[0]
        assert "batted_ball" in index[0]
        assert "disabled = false" in index[0]

    # 既正式global_read_onlyのSELECTは維持し、appからの書込を実権限で拒否する。
    with psycopg.connect(db.authority.database.business_admin) as denied:
        denied.execute("SET SESSION AUTHORIZATION pitchlog_app")
        assert denied.execute("SELECT session_user, current_user").fetchone() == (
            "pitchlog_app",
            "pitchlog_app",
        )
        assert denied.execute(
            "SELECT key FROM public.admin_vocabularies WHERE key=%s", (expected[0],)
        ).fetchall() == [(expected[0],)]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            denied.execute(
                "UPDATE public.admin_vocabularies "
                "SET display_name=display_name WHERE false"
            )
        denied.rollback()

    _prepare_app_configuration(db)
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "other_tenant": str(db.other_tenant_id),
        "password": _PASSWORD,
        "expected_keys": expected,
    }
    process = subprocess.run(
        ["docker", *_app_arguments(db, case), "-u", "-c", _READ_SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert process.returncode == 0, (process.stdout[-1200:], process.stderr[-1200:])
    result = json.loads(process.stdout)
    assert result["selected"] == expected
    assert result["pages"] >= 5
    assert result["unauthenticated"] == 401
    assert result["mismatched_tenant"] == 404
    assert result["malformed_cursor"] == 422
