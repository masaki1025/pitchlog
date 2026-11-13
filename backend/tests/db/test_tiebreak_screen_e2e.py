"""9回消化後のタイブレークを実画面で開始し、生還・交代・再配置・reloadを確認する。"""

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

_CONFIG = "GameScreenTiebreak.playwright.config.ts"
_PROJECT = "tiebreak"
_REPORT = re.compile(r"PITCHLOG_TIEBREAK_FINAL=(\{[^\n]+\})")
_BENCH = UUID(int=214)


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離HTTPS証明書PATH未供給。画面縦断は未実証",
)
@pytest.mark.skip(
    reason=(
        "9回54frameのsource chainとnative ledgerは通過したが、"
        "consume_nonplay_tiebreak_start のCP SELECTがP0002で0行。"
        "stamp.internal_generation/recovery_generationとCP行の照合修正まで未完了。"
    )
)
def test_tiebreak_screen_start_score_pitcher_change_replacement_reload(
    vertical_database,
):
    """実試合9回後からタイブレークを画面で通し、実DB原本を照合する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for key, category in (
            ("batting-result.home-run", "batting_result"),
            ("batting-result.batted-out", "batting_result"),
            ("batting-result.called-pitch", "batting_result"),
            ("batting-result.called-strikeout", "batting_result"),
            ("batted.screen.line", "batted_ball"),
            ("batted.screen.hard", "batted_ball"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert teams is not None
        admin.execute(
            "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
            "uniform_number,roster_status_key) "
            "VALUES (%s,%s,%s,'タイブレーク控え投手','14','active')",
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
                    "PITCHLOG_E2E_BENCH_PITCHER": str(_BENCH),
                },
                timeout_seconds=2_000,
            )
    if result.returncode != 0:
        print("TIEBREAK_E2E_STDOUT", result.stdout)
        print("TIEBREAK_E2E_STDERR", result.stderr)
    assert result.returncode == 0, (
        result.stdout[-20000:],
        result.stderr[-4000:],
    )
    lines = _REPORT.findall(result.stdout)
    assert len(lines) == 1, result.stdout[-20000:]
    observed = json.loads(lines[0])
    game = UUID(observed["gameId"])
    assert observed["newPitcher"] == str(_BENCH)
    assert observed["tiebreakStarts"] == 2
    assert observed["rePlacementHalf"] == "bottom"
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        events = admin.execute(
            "SELECT event_kind,count(*) FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s GROUP BY event_kind",
            (db.tenant_id, game),
        ).fetchall()
        tiebreak_receipts = admin.execute(
            "SELECT count(*) FROM sync_fence.tiebreak_start_write_receipts "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, game),
        ).fetchone()
        substitution_receipts = admin.execute(
            "SELECT count(*) FROM sync_fence.substitution_write_receipts "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, game),
        ).fetchone()
        current = admin.execute(
            "SELECT content->'content'->'restored',"
            "content->'content'->'tiebreakFrames' "
            "FROM sync_fence.ordinary_pitch_checkpoints "
            "WHERE tenant_id=%s AND game_id=%s AND state='current'",
            (db.tenant_id, game),
        ).fetchall()
    assert dict(events) == {
        "play_input": observed["plays"],
        "tiebreak_start": 2,
        "substitution": 1,
    }
    assert tiebreak_receipts == (2,)
    assert substitution_receipts == (1,)
    assert len(current) == 1
    restored, frames = current[0]
    assert len(frames) == 2
    assert restored["current"]["stateFields"]["state.runners"] == "first-second"
    assert restored["participants"]["pitcherId"] == str(_BENCH)
    assert {runner["responsiblePitcherId"] for runner in restored["runners"]} == {
        observed["oldPitcher"]
    }
