"""正常CURRENT49の実画面で26件訂正から終了再開・成績CSVまで検証する。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import LiteralString
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

# すべて同一owned試合の有限WHERE。UI開始前に同一SQLをEXPLAINする。
_QUERIES: dict[str, LiteralString] = {
    "slots": "SELECT d1,confirmed_version FROM public.event_slots "
    "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
    "versions": "SELECT id,is_current,source_count,completion_state,"
    "completion_receipt_id,public_pointer_receipt_id "
    "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s AND game_id=%s "
    "ORDER BY created_at",
    "head": "SELECT active_stats_version_id,active_receipt_id FROM "
    "sync_fence.game_lifecycle_heads WHERE tenant_id=%s AND game_id=%s",
    "events": "SELECT d1,event_kind,ledger_kind FROM public.operation_events "
    "WHERE tenant_id=%s AND game_id=%s AND event_kind IN "
    "('game_end_declaration','game_reopen') ORDER BY d1",
    "sources": "SELECT d1,slot_version FROM sync_fence.stats_primitive_sources "
    "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s ORDER BY d1",
    "metric": "SELECT metric_states FROM sync_fence.stats_primitive_sources "
    "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s AND d1=26",
    "capsules": "SELECT count(*) FROM sync_fence.p3_projection_capsules "
    "WHERE tenant_id=%s AND game_id=%s",
}


def _params(name, tenant, game, version=UUID(int=0)):
    """固定SQLの引数だけを供給し、列名やSQLを入力から生成しない。"""
    return (tenant, game, version) if name in {"sources", "metric"} else (tenant, game)


def _partial_evidence(db, game_path, output):
    """UI失敗でも実在する原本の有限件数を読む。失敗を成功へ変更しない。"""
    if not game_path.is_file():
        output.write_text(json.dumps({"game_created": False, "audit": "not-reached"}))
        return
    game = UUID(json.loads(game_path.read_text())["gameId"])
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        counts = []
        for table in (
            "public.play_rows",
            "public.operation_events",
            "public.event_slots",
            "sync_fence.stats_fact_versions",
            "sync_fence.p3_projection_capsules",
        ):
            row = admin.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, game),
            ).fetchone()
            assert row is not None
            counts.append(row[0])
    output.write_text(json.dumps({"game_created": True, "counts": counts}))


def _verify_stats_csv(csv_path, observed):
    """実API全表示値と同じ終了版CSVの全byteを製品serializerで照合する。"""
    from pitchlog.api.routers.basic_stats import _CSV_HEADERS, _csv_row
    from pitchlog.api.schemas.basic_stats import PlayerBasicStats
    from pitchlog.exports.csv import stream_csv

    api = json.loads(Path(str(csv_path) + ".api.json").read_text())
    assert api["game_id"] == observed["gameId"] and api["mode"] == "official"
    assert api["next_cursor"] is None
    players = [PlayerBasicStats.model_validate(row) for row in api["players"]]
    assert len(players) == observed["statsRows"] > 0
    expected = b"".join(stream_csv(_CSV_HEADERS, (_csv_row(row) for row in players)))
    actual = csv_path.read_bytes()
    assert actual == expected
    assert len(actual) == observed["csvBytes"]
    assert hashlib.sha256(actual).hexdigest() == observed["csvSha256"]


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離HTTPS未供給。26件画面訂正は未実証",
)
def test_screen_create_26_pitches_correct_last_reload(vertical_database, tmp_path):
    """後付SQLなしで26球・訂正・再開後追記・終了版成績を照合する。"""
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
        for name, query in _QUERIES.items():
            admin.execute("EXPLAIN " + query, _params(name, db.tenant_id, db.game_id))
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
    game_path, csv_path = tmp_path / "p3-game.json", tmp_path / "p3-stats.csv"
    result = None
    try:
        with db.broker_worker(token), binding_broker(db, token):
            with _browser_environment(
                db, config, "p3-paging-screen", https=True
            ) as origin:
                result = _run_playwright(
                    db,
                    config,
                    origin,
                    "p3-paging-screen",
                    {
                        "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                        "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                        "PITCHLOG_E2E_P3_PAGING": "26",
                        "PITCHLOG_E2E_P3_GAME_PATH": str(game_path),
                        "PITCHLOG_E2E_P3_CSV_PATH": str(csv_path),
                    },
                    timeout_seconds=960,
                )
    finally:
        # 診断失敗でも元UI失敗を置換せず、別証拠として不足を明示する。
        try:
            _partial_evidence(db, game_path, tmp_path / "p3-screen-partial-db.json")
        except Exception as error:
            (tmp_path / "p3-screen-partial-db.json").write_text(
                json.dumps(
                    {
                        "audit": "unavailable",
                        "exception": type(error).__name__,
                    }
                )
            )
    assert result is not None and result.returncode == 0, (
        "26件画面試験が成功終了していません"
    )
    matches = re.findall(r"PITCHLOG_P3_PAGING_SCREEN=(\{[^\n]+\})", result.stdout)
    assert len(matches) == 1
    observed = json.loads(matches[0])
    game = UUID(observed["gameId"])
    assert game != db.game_id
    assert {
        key: observed[key]
        for key in (
            "pitches",
            "targetD1",
            "accepted",
            "replayStatus",
            "reloaded",
            "suffixPitch",
            "endedAfterCorrection",
            "reopenedAndPitchSaved",
            "reendedAfterCorrection",
            "playZipStatus",
        )
    } == dict(
        pitches=26,
        targetD1=26,
        accepted=1,
        replayStatus=200,
        reloaded=True,
        suffixPitch=1,
        endedAfterCorrection=True,
        reopenedAndPitchSaved=True,
        reendedAfterCorrection=True,
        playZipStatus=409,
    )
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:

        def rows(name, version=UUID(int=0)):
            return admin.execute(
                _QUERIES[name], _params(name, db.tenant_id, game, version)
            ).fetchall()

        slots = rows("slots")
        assert slots == [(d1, 2 if d1 == 26 else 1) for d1 in range(1, 32)]
        versions = rows("versions")
        assert len(versions) == 5
        assert [row[1:4] for row in versions] == [
            (False, 26, "current_open"),
            (False, 27, "current_open"),
            (False, 27, "confirmed_ended"),
            (False, 28, "current_open"),
            (True, 28, "confirmed_ended"),
        ]
        assert versions[1][0] == UUID(observed["statsVersionId"])
        assert versions[2][4] is not None and versions[2][4] == versions[2][5]
        assert versions[4][4] is not None and versions[4][4] == versions[4][5]
        assert versions[2][4] != versions[4][4]
        assert rows("head") == [(versions[4][0], versions[4][4])]
        assert rows("events") == [
            (28, "game_end_declaration", "accepted"),
            (29, "game_reopen", "accepted"),
            (31, "game_end_declaration", "accepted"),
        ]
        assert rows("sources", versions[4][0]) == slots[:27] + [(30, 1)]
        assert rows("capsules") == [(1,)]
        for version, expected_k in ((versions[0][0], "1"), (versions[4][0], "0")):
            metrics = rows("metric", version)
            assert len(metrics) == 1
            for name in ("k", "pitcher_k"):
                assert metrics[0][0]["metrics"][name]["value"] == expected_k
    _verify_stats_csv(csv_path, observed)
    (tmp_path / "p3-paging-screen-db-evidence.json").write_text(
        json.dumps(
            {
                "pitches": 26,
                "target_d1": 26,
                "versions": 5,
                "replay_status": 200,
                "reloaded": True,
                "final_sources": 28,
                "csv_api_all_values_equal": True,
                "play_zip_status": 409,
                "db_verified": True,
            }
        )
    )
