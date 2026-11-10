"""公式成績27項目と成績CSVを実HTTPS画面から確認する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

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

_CONFIG = "GameScreenStatsScreen.playwright.config.ts"
_PROJECT = "stats-screen"
_REPORT = re.compile(r"PITCHLOG_STATS_SCREEN_FINAL=(\{[^\n]+\})")


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離HTTPS証明書PATH未供給。画面縦断は未実証",
)
def test_stats_screen_e2e(vertical_database):
    """終了後に公式27項目を表示し、成績CSVを実ダウンロードする。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert teams is not None
        for key, category in (
            ("batting-result.home-run", "batting_result"),
            ("batting-result.batted-out", "batting_result"),
            ("batted.screen.line", "batted_ball"),
            ("batted.screen.hard", "batted_ball"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(db, _CONFIG, _PROJECT, https=True) as origin:
            result = _run_playwright(
                db,
                _CONFIG,
                origin,
                _PROJECT,
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
                timeout_seconds=600,
            )
    assert result.returncode == 0, (
        result.stdout[-16000:],
        result.stderr[-3000:],
    )
    lines = _REPORT.findall(result.stdout)
    assert len(lines) == 1, result.stdout[-16000:]
    observed = json.loads(lines[0])
    game = UUID(observed["gameId"])
    assert observed["plays"] == 7
    assert observed["metrics"] == 27
    assert observed["battingHeaders"] > 2 and observed["pitchingHeaders"] > 2
    assert observed["csvBytes"] > 0
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        events = admin.execute(
            "SELECT event_kind,ledger_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            (db.tenant_id, game),
        ).fetchall()
        version = admin.execute(
            "SELECT source_count,completion_state,is_current FROM "
            "sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND is_current",
            (db.tenant_id, game),
        ).fetchone()
    assert events == [("play_input", "accepted")] * 7 + [
        ("game_end_declaration", "accepted")
    ]
    assert version is not None
    assert cast(tuple[object, ...], version)[0] == 7
    assert cast(tuple[object, ...], version)[1] == "confirmed_ended"
    assert cast(tuple[object, ...], version)[2] is True
