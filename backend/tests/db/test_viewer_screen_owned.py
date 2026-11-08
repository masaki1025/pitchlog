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
from .viewer_owned_support import (
    assert_current_viewer_catalog,
    save_viewer_evidence,
    viewer_log_directory,
)

pytestmark = pytest.mark.requires_db


def test_viewer_https_two_context_auto_update_and_offline(vertical_database) -> None:
    """新規UI開始から1球保存後10秒反映・reload・未更新までを実測する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert_current_viewer_catalog(admin)
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        for key, name in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "空振り三振"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, name),
            )
    assert teams is not None
    token = uuid4()
    with viewer_log_directory(), db.broker_worker(token), binding_broker(db, token):
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
            recovered = re.search(
                r"PITCHLOG_VIEWER_RECOVERED_MS=([0-9]+)", result.stdout
            )
            assert recovered is not None and int(recovered.group(1)) <= 10000
            print(
                "PITCHLOG_VIEWER_TIMING="
                + f"visible_ms={match.group(1)},"
                + f"recovered_ms={recovered.group(1)}"
            )

            save_viewer_evidence(
                "browser",
                {
                    "visible_ms": int(match.group(1)),
                    "recovered_ms": int(recovered.group(1)),
                    "source": "CURRENT49/new UI game/separate contexts",
                },
            )
