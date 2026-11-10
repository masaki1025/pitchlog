"""9回コールド・延長・タイブレーク境界を実HTTPS画面から確認する。"""

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

_CONFIG = "GameScreenEndConditions.playwright.config.ts"
_PROJECT = "end-conditions"
_REPORT = re.compile(r"PITCHLOG_END_CONDITION_FINAL=(\{[^\n]+\})")


def _run_all(db) -> list[dict[str, object]]:
    """同じbroker/appで3シナリオを順に実画面から保存する。"""
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
    assert teams is not None
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
                timeout_seconds=3000,
            )
    assert result.returncode == 0, (
        result.stdout[-16000:],
        result.stderr[-3000:],
    )
    lines = _REPORT.findall(result.stdout)
    assert len(lines) == 3, (result.stdout[-16000:])
    return [json.loads(line) for line in lines]


def _events(db, game: UUID) -> list[tuple[str, str]]:
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        return admin.execute(
            "SELECT event_kind,ledger_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            (db.tenant_id, game),
        ).fetchall()


def _game_state(db, game: UUID) -> tuple[str, int | None, bool | None, int | None]:
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        row = admin.execute(
            "SELECT g.status,h.last_version,h.is_finished,v.source_count "
            "FROM public.games g "
            "LEFT JOIN sync_fence.game_lifecycle_heads h "
            "ON h.tenant_id=g.tenant_id AND h.game_id=g.id "
            "LEFT JOIN sync_fence.stats_fact_versions v "
            "ON v.tenant_id=h.tenant_id AND v.game_id=h.game_id "
            "AND v.id=h.active_stats_version_id "
            "WHERE g.tenant_id=%s AND g.id=%s",
            (db.tenant_id, game),
        ).fetchone()
        assert row is not None
        return cast(tuple[str, int | None, bool | None, int | None], row)


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離HTTPS証明書PATH未供給。画面縦断は未実証",
)
def test_end_conditions_screen_e2e(vertical_database):
    """コールド・延長・タイブレーク境界を同じ所有DBで実画面から保存する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
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
    scenarios = {
        str(row["scenario"]): row for row in _run_all(db)
    }

    cold = UUID(str(scenarios["cold-end"]["gameId"]))
    draw = UUID(str(scenarios["limit-draw"]["gameId"]))
    tiebreak = UUID(str(scenarios["tiebreak-required"]["gameId"]))
    assert _events(db, cold) == [("play_input", "accepted")] * 49 + [
        ("game_end_declaration", "accepted")
    ]
    assert _game_state(db, cold) == ("finished", 1, True, 49)
    assert _events(db, draw) == [("play_input", "accepted")] * 54 + [
        ("game_end_declaration", "accepted")
    ]
    assert _game_state(db, draw) == ("finished", 1, True, 54)
    assert _events(db, tiebreak) == [("play_input", "accepted")] * 54
    state = _game_state(db, tiebreak)
    assert state[0] == "in_progress"
