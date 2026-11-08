"""凡打死3球→攻守交代を実画面と所有PGで確認する候補。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
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


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離HTTPS証明書PATH未供給。凡打死画面縦断は未実証",
)
def test_batted_out_three_pitches_actual_screen(vertical_database):
    """新規試合の実V7を保存し、重複再送後も3原本/現版だけを保持する。"""
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
        for key, category in (
            ("batting-result.batted-out", "batting_result"),
            ("batted.screen.line", "batted_ball"),
            ("batted.screen.hard", "batted_ball"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
    assert teams is not None
    token = uuid4()
    config = "GameScreenBattedOut.playwright.config.ts"
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(db, config, "batted-out", https=True) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "batted-out",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
                timeout_seconds=480,
            )
    matched = re.findall(r"PITCHLOG_BATTED_OUT_SCREEN=(\{[^\n]+\})", result.stdout)
    assert len(matched) == 1, (result.stdout[-8000:], result.stderr[-2000:])
    observed = json.loads(matched[0])
    game = UUID(observed["gameId"])
    assert game != db.game_id
    assert observed["accepted"] == 3
    assert observed["prefixLength"] == "3"
    assert observed["half"] == "bottom" and observed["outs"] == "0"
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        rows = admin.execute(
            "SELECT batting_result_key FROM public.play_rows WHERE tenant_id=%s "
            "AND game_id=%s AND retired_at IS NULL ORDER BY play_number",
            (db.tenant_id, game),
        ).fetchall()
        accepted = admin.execute(
            "SELECT event_kind,ledger_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            (db.tenant_id, game),
        ).fetchall()
        fact = admin.execute(
            "SELECT source_count,is_current FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND is_current",
            (db.tenant_id, game),
        ).fetchall()
    assert rows == [("batting-result.batted-out",)] * 3
    assert accepted == [("play_input", "accepted")] * 3
    assert fact == [(3, True)]
    assert result.returncode == 0, (result.stdout[-8000:], result.stderr[-2000:])
