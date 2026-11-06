"""記録者と別ブラウザcontextのライブ閲覧を実HTTPSで照合する。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


def test_viewer_https_two_context_auto_update_and_offline(vertical_database) -> None:
    """新規UI開始から1球保存後10秒反映・reload・未更新までを実測する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            "GameScreenViewerLive.playwright.config.ts",
            "viewer-https",
            https=True,
        ) as origin:
            result = _run_playwright(
                db,
                "GameScreenViewerLive.playwright.config.ts",
                origin,
                "viewer-https",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-3000:],
            )
            match = re.search(r"PITCHLOG_VIEWER_VISIBLE_MS=([0-9]+)", result.stdout)
            assert match is not None and int(match.group(1)) <= 10000
