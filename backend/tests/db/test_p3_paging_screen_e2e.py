"""正常CURRENT49の実画面で26球目のページ選択・訂正・復元を検証する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.db.current_product_startup import CURRENT_REVISION

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
    reason="隔離HTTPS未供給。26件画面訂正は未実証",
)
def test_screen_create_26_pitches_correct_last_reload(vertical_database, tmp_path):
    """後付SQLなしで画面原要求と実slot/T5旧新版を照合する。"""
    for key in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[key])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchall() == [(CURRENT_REVISION,)]
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert teams is not None
        for key, label in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "見逃し三振"),
            ("batting-result.foul", "ファウル"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, label),
            )
    config = "GameScreenPastCorrectionProduct.playwright.config.ts"
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(db, config, "p3-paging-screen", https=True) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "p3-paging-screen",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_P3_PAGING": "26",
                },
            )
    assert result.returncode == 0, "26件画面試験が成功終了していません"
    matches = re.findall(r"PITCHLOG_P3_PAGING_SCREEN=(\{[^\n]+\})", result.stdout)
    assert len(matches) == 1
    observed = json.loads(matches[0])
    game = UUID(observed["gameId"])
    assert game != db.game_id
    assert {
        key: observed[key]
        for key in ("pitches", "targetD1", "accepted", "replayStatus", "reloaded")
    } == {
        "pitches": 26,
        "targetD1": 26,
        "accepted": 1,
        "replayStatus": 200,
        "reloaded": True,
    }
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        slots = admin.execute(
            "SELECT d1,confirmed_version FROM public.event_slots "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            (db.tenant_id, game),
        ).fetchall()
        assert slots == [(d1, 2 if d1 == 26 else 1) for d1 in range(1, 27)]
        versions = admin.execute(
            "SELECT id,is_current,source_count,completion_state "
            "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s AND game_id=%s "
            "ORDER BY created_at",
            (db.tenant_id, game),
        ).fetchall()
        assert len(versions) == 2
        assert [row[1:] for row in versions] == [
            (False, 26, "current_open"),
            (True, 26, "current_open"),
        ]
        assert versions[1][0] == UUID(observed["statsVersionId"])
        for version, expected_k in ((versions[0][0], "1"), (versions[1][0], "0")):
            metrics = admin.execute(
                "SELECT metric_states FROM sync_fence.stats_primitive_sources "
                "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s AND d1=26",
                (db.tenant_id, game, version),
            ).fetchall()
            assert len(metrics) == 1
            for name in ("k", "pitcher_k"):
                assert metrics[0][0]["metrics"][name]["value"] == expected_k
    (tmp_path / "p3-paging-screen-db-evidence.json").write_text(
        json.dumps(
            {
                "pitches": 26,
                "target_d1": 26,
                "versions": 2,
                "replay_status": 200,
                "reloaded": True,
                "db_verified": True,
            }
        )
    )
