"""実HTTPS画面の2球2取消次球。作者collectのみ、root所有環境で実行する。"""

from __future__ import annotations

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
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="実HTTPS証明書PATH未供給。画面縦断は未実証",
)
def test_screen_create_two_pitches_two_undo_next_pitch_reload(vertical_database):
    """事前game投入を実証にせず、新UIが作ったgameの原本を実DBで照合する。"""
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
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, "GameScreenUndoProduct.playwright.config.ts", "undo-product", https=True
        ) as origin:
            result = _run_playwright(
                db,
                "GameScreenUndoProduct.playwright.config.ts",
                origin,
                "undo-product",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-3000:],
            )
    matches = re.findall(r"PITCHLOG_UNDO_PRODUCT_GAME=([a-f0-9-]{36})", result.stdout)
    assert len(matches) == 1
    created = UUID(matches[0])
    assert created != db.game_id
    with psycopg.connect(db.authority.database.business_admin) as admin:
        events = admin.execute(
            "SELECT d1,event_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s AND ledger_kind='accepted' "
            "ORDER BY d1",
            (db.tenant_id, created),
        ).fetchall()
        assert events == [
            (1, "play_input"),
            (2, "play_input"),
            (3, "undo"),
            (4, "undo"),
            (5, "play_input"),
        ]
        plays = admin.execute(
            "SELECT play_number,hidden_at IS NOT NULL FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY play_number",
            (db.tenant_id, created),
        ).fetchall()
        assert plays == [(1, True), (2, True), (3, False)]
