"""候補0046を隔離owned DBへ配備して、真正P3画面を確認する。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_p3_candidate_compile_author import _PACKET
from .test_p3_candidate_compile_author import (
    test_owned_candidate_0046_compiles as _install_p3_candidate,
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
    reason="隔離HTTPS証明書PATH未供給。P3画面縦断は未実証",
)
def test_screen_p3_https_create_three_pitches_correct_reload(vertical_database) -> None:
    """実画面の原版・原要求・再掲とT5旧新版を同じowned DBで確認する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    _install_p3_candidate(db)
    control_sql = (_PACKET / "p3-d1less-control-functions.candidate.sql").read_text()
    control = subprocess.run(
        [
            "docker", "exec", "-i", "--user", "postgres",
            db.authority.binding_control, "psql", "-X", "-q",
            "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d",
            "binding_control_fixture",
        ],
        input=control_sql,
        capture_output=True,
        text=True,
        check=False,
    )
    assert control.returncode == 0, control.stderr[-500:]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert teams is not None
        for key, label in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "見逃し三振"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, label),
            )
    config = "GameScreenPastCorrectionProduct.playwright.config.ts"
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(db, config, "p3-screen", https=True) as origin:
            result = _run_playwright(
                db, config, origin, "p3-screen",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert result.returncode == 0, (
                result.stdout[-12000:], result.stderr[-3000:]
            )
    found = re.findall(r"PITCHLOG_P3_SCREEN=(\{[^\n]+\})", result.stdout)
    assert len(found) == 1
    observed = json.loads(found[0])
    game_id = UUID(observed["gameId"])
    assert game_id != db.game_id
    assert observed["accepted"] == 1 and observed["replayStatus"] == 200
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        key = (db.tenant_id, game_id)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s", key,
        ).fetchone() == (1,)
        versions = admin.execute(
            "SELECT id,is_current,source_count FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND source_count=3 "
            "ORDER BY created_at", key,
        ).fetchall()
        assert len(versions) == 2
        assert [row[1:] for row in versions] == [(False, 3), (True, 3)]
        old = admin.execute(
            "SELECT metric_states FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s AND d1=3",
            (*key, versions[0][0]),
        ).fetchone()
        current = admin.execute(
            "SELECT metric_states FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s AND d1=3",
            (*key, versions[1][0]),
        ).fetchone()
        assert old is not None and current is not None
        assert old[0]["metrics"]["k"]["value"] == "1"
        assert current[0]["metrics"]["k"]["value"] == "0"
        assert old[0]["metrics"]["pitcher_k"]["value"] == "1"
        assert current[0]["metrics"]["pitcher_k"]["value"] == "0"
