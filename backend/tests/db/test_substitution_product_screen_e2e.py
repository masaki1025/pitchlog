"""新規試合の投手交代と次球を実HTTPS画面から保存する。"""

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
    reason="隔離HTTPS証明書PATH未供給。画面縦断は未実証",
)
def test_screen_create_substitute_next_pitch_reload(vertical_database):
    """UI新規試合の受理3件と交代receipt・新投手CPをDBへ照合する。"""
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
        admin.execute(
            "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
            "uniform_number,roster_status_key) "
            "VALUES (%s,%s,%s,'画面交代試験選手','11','active')",
            (db.tenant_id, UUID(int=211), teams[1]),
        )
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
    token = uuid4()
    config = "GameScreenSubstitutionProduct.playwright.config.ts"
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, config, "substitution-product", https=True
        ) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "substitution-product",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert result.returncode == 0, (
                result.stdout[-12000:],
                result.stderr[-2000:],
            )
    lines = re.findall(r"PITCHLOG_SUBSTITUTION_FINAL=(\{[^\n]+\})", result.stdout)
    assert len(lines) == 1
    observed = json.loads(lines[0])
    game = UUID(observed["gameId"])
    assert game != db.game_id
    assert observed["accepted"] == 3 and observed["balls"] == 2
    assert observed["incoming"] == str(UUID(int=211))
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        events = admin.execute(
            "SELECT event_kind,ledger_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            (db.tenant_id, game),
        ).fetchall()
        receipt = admin.execute(
            "SELECT source_event_id FROM sync_fence.substitution_write_receipts "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, game),
        ).fetchall()
        checkpoints = admin.execute(
            "SELECT content->'content'->'restored'->'participants'->>'pitcherId' "
            "FROM sync_fence.ordinary_pitch_checkpoints "
            "WHERE tenant_id=%s AND game_id=%s AND state='current'",
            (db.tenant_id, game),
        ).fetchall()
    assert events == [
        ("play_input", "accepted"),
        ("substitution", "accepted"),
        ("play_input", "accepted"),
    ]
    assert len(receipt) == 1
    assert checkpoints == [(observed["incoming"],)]
