"""実画面の守備変更を控え選手で保存し、現在配置へ反映する。"""

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

_CONFIG = "GameScreenSubstitutionDefense.playwright.config.ts"
_PROJECT = "defense-change"
_REPORT = re.compile(r"PITCHLOG_DEFENSE_FINAL=(\{[^\n]+\})")
_BENCH = UUID(int=213)


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離HTTPS証明書PATH未供給。画面縦断は未実証",
)
def test_defense_change_screen_e2e(vertical_database):
    """控えの遊撃手交代を受理し、current fielding 6へ反映する。"""
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
            "VALUES (%s,%s,%s,'画面守備控え','13','active')",
            (db.tenant_id, _BENCH, teams[1]),
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
    assert observed["incoming"] == str(_BENCH)
    assert observed["accepted"] == 2
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        events = admin.execute(
            "SELECT event_kind,ledger_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            (db.tenant_id, game),
        ).fetchall()
        receipts = admin.execute(
            "SELECT count(*) FROM sync_fence.substitution_write_receipts "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, game),
        ).fetchone()
        fielding = admin.execute(
            "SELECT content->'content'->'restored'->'substitutionState'"
            "->'home'->'fielding'->>'6' "
            "FROM sync_fence.ordinary_pitch_checkpoints "
            "WHERE tenant_id=%s AND game_id=%s AND state='current'",
            (db.tenant_id, game),
        ).fetchall()
    assert events == [
        ("play_input", "accepted"),
        ("substitution", "accepted"),
    ]
    assert receipts == (1,)
    assert fielding == [(str(_BENCH),)]
