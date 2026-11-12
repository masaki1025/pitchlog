"""実画面初回単打の送信前診断。資格や要求内容を採取しない。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_batted_operations_batch_screen_e2e import (
    _READ_SQL,
    _explain_read_sql,
    _owned_logs,
)
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
    reason="隔離HTTPS証明書PATH未供給。初回単打診断未実施",
)
def test_first_batted_send_diagnostic(vertical_database):
    """新規UI試合の初回単打送信前状態を安全な分類で診断する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _explain_read_sql(admin, db.tenant_id, db.game_id)
        assert admin.execute(_READ_SQL["read_0"]).fetchone() == (
            "0050_play_export_p3_snapshots",
        )
        teams = admin.execute(
            _READ_SQL["read_1"],
            (db.tenant_id, db.game_id),
        ).fetchone()
        for key, category in (
            *[
                ("batting-result." + key, "batting_result")
                for key in (
                    "single",
                    "double-play",
                    "fielders-choice",
                    "error",
                    "sacrifice-bunt",
                    "sacrifice-fly",
                )
            ],
            ("batting-result.batted-out", "batting_result"),
            ("batted.screen.line", "batted_ball"),
            ("batted.screen.hard", "batted_ball"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
    assert teams is not None and teams[2] is not None
    cache = Path.home() / ".cache/pitchlog/batted-operations-screen-author-20261108"
    cache.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="full-game-batted-", dir=cache))
    evidence.chmod(0o700)
    token = uuid4()
    config = "GameScreenBattedFirstSendDiagnostic.playwright.config.ts"
    with _owned_logs(evidence), db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, config, "batted-first-send-diagnostic", https=True
        ) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "batted-first-send-diagnostic",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_SELF_TEAM": str(teams[2]),
                    "PITCHLOG_FULLGAME_EVIDENCE_DIR": str(evidence),
                },
                timeout_seconds=240,
            )
    (evidence / "playwright.log").write_text(result.stdout + "\n" + result.stderr)
    safe = json.loads((evidence / "first-send-safe.json").read_text())
    assert safe["outcome"] == "single-accepted-and-read", safe
    assert result.returncode == 0, safe
