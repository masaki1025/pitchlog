"""申告敬遠を含む実画面4記録から同TX88列と実ZIPを照合する。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.play_export_source_read_product import candidate_read_bundle
from pitchlog.authz.play_export_writer_product import candidate_install_sql
from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import apply_product_authz_ddl
from pitchlog.exports.play_rows import CSV_HEADERS

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db
_ROOT = Path(__file__).resolve().parents[3]


def _rows(archive: zipfile.ZipFile, name: str) -> list[list[str]]:
    """保存済みCSVをBOMを含む実bytesから独立に読む。"""
    return list(
        csv.reader(io.StringIO(archive.read(name).decode("utf-8-sig"), newline=""))
    )


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="所有loopback TLS資材PATH未供給。画面実測は未成立",
)
def test_actual_nonpitch_screen_downloads_four_play_product_zip(
    vertical_database, tmp_path
):
    """二単打→申告敬遠→次球の保存原本と画面ZIPを同一owned版で検査する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        apply_product_authz_ddl(admin)
        identity = admin.execute(
            "SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert identity is not None
        report = inspect_product_authz_catalog(
            admin, privileged_role_oids=frozenset({identity[0]})
        )
        assert report.ok, [value.check_id for value in report.violations]
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        for key in (
            "batting-result.single",
            "batting-result.intentional-walk",
            "batting-result.ball",
            "batted.screen.line",
            "batted.screen.hard",
        ):
            category = (
                "batting_result" if key.startswith("batting-result") else "batted_ball"
            )
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
        ddl = (
            _ROOT / "docs/features/ud2-csv-export/candidates/play_export_snapshots.sql"
        ).read_text()
        admin.execute(sql.SQL(cast(LiteralString, ddl)))
        admin.execute(sql.SQL(cast(LiteralString, candidate_install_sql())))
        _source_query, source_install = candidate_read_bundle()
        admin.execute(sql.SQL(cast(LiteralString, source_install)))
    assert teams is not None
    path = tmp_path / "nonpitch-play-csv.zip"
    token = uuid4()
    config = "GameScreenNonpitchPlayCsv.playwright.config.ts"
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, config, "nonpitch-play-csv", https=True
        ) as origin:
            run = _run_playwright(
                db,
                config,
                origin,
                "nonpitch-play-csv",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_CSV_DOWNLOAD_PATH": str(path),
                },
            )
    if run.returncode:
        (tmp_path / "playwright-stdout.log").write_text(run.stdout)
        (tmp_path / "playwright-stderr.log").write_text(run.stderr)
    assert run.returncode == 0, (run.stdout[-6000:], run.stderr[-1000:])
    lines = re.findall(r"PITCHLOG_NONPITCH_CSV_SCREEN_RESULT=(\{[^\n]+\})", run.stdout)
    assert len(lines) == 1 and path.is_file()
    observed = json.loads(lines[0])
    game = UUID(observed["gameId"])
    assert game != db.game_id
    assert observed["plays"] == 4
    assert observed["replayStatus"] == 200 and observed["replayA5"] == "重複"
    data = path.read_bytes()
    assert len(data) == observed["downloadBytes"] == observed["contentLength"]
    assert (
        hashlib.sha256(data).hexdigest()
        == observed["downloadSha256"]
        == observed["headerSha256"]
    )
    assert observed["downloadFilename"] == f"pitchlog-plays-{game}.zip"

    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        snapshots = admin.execute(
            "SELECT source_event_id,play_row_id,plays_csv_json,full_innings_json "
            "FROM public.play_export_snapshots WHERE tenant_id=%s AND game_id=%s "
            "ORDER BY event_sequence",
            (db.tenant_id, game),
        ).fetchall()
        plays = admin.execute(
            "SELECT id,source_event_id,event_kind,pitch_type_key,course_x,course_y,"
            "pitch_speed FROM public.play_rows WHERE tenant_id=%s AND game_id=%s "
            "ORDER BY play_number",
            (db.tenant_id, game),
        ).fetchall()
        accepted = admin.execute(
            "SELECT id FROM public.operation_events WHERE tenant_id=%s "
            "AND game_id=%s AND event_kind='play_input' AND ledger_kind='accepted' "
            "ORDER BY d2",
            (db.tenant_id, game),
        ).fetchall()
        primitive = admin.execute(
            "SELECT source_event_id,metric_states "
            "FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY source_event_id",
            (db.tenant_id, game),
        ).fetchall()
    assert len(snapshots) == len(plays) == len(accepted) == len(primitive) == 4
    assert [row[0] for row in snapshots] == [row[0] for row in accepted]
    assert [row[1] for row in snapshots] == [row[0] for row in plays]
    assert [row[2] for row in plays] == ["pitch", "pitch", "non_pitch", "pitch"]
    assert plays[2][3:] == (None, None, None, None)
    assert {row[0] for row in primitive} == {row[0] for row in snapshots}
    nonpitch_metrics = next(
        state["metrics"]
        for source_id, state in primitive
        if source_id == snapshots[2][0]
    )
    assert nonpitch_metrics["pitch_count"]["value"] == "0"
    assert nonpitch_metrics["pitch_count"]["credits"] == []
    for metric in ("pa", "bb", "pitcher_bb", "batters_faced"):
        assert nonpitch_metrics[metric]["value"] == "1"
        assert len(nonpitch_metrics[metric]["credits"]) == 1
    for index, (_source, _play, values, full) in enumerate(snapshots):
        assert set(values) == set(CSV_HEADERS["plays.csv"])
        assert values["球数"] == ["1", "2", "2", "3"][index]
        assert full[0] == {
            "inning": 1,
            "half": "top",
            "state": "in-progress",
            "runs": 0,
        }
    nonpitch_values = snapshots[2][2]
    assert nonpitch_values["プレイの種類"] == "非投球"
    for key in ("コースX", "コースY", "球種", "球速"):
        assert nonpitch_values[key] is None

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(CSV_HEADERS) | {"manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["game_id"] == str(game)
        assert manifest["format_version"] == "pitchlog-play-export-v2-candidate"
        assert len(manifest["files"]) == 11
        for item in manifest["files"]:
            raw = archive.read(item["name"])
            rows = _rows(archive, item["name"])
            assert item["byte_length"] == len(raw)
            assert item["sha256"] == hashlib.sha256(raw).hexdigest()
            assert item["data_row_count"] == len(rows) - 1
            assert rows[0] == list(CSV_HEADERS[item["name"]])
        exported = _rows(archive, "plays.csv")
        assert len(exported) == 5 and len(exported[0]) == 88
        assert [row[34] for row in exported[1:]] == ["1", "2", "2", "3"]
        assert [row[40] for row in exported[1:]] == ["投球", "投球", "非投球", "投球"]
        for index in (42, 43, 44, 56):
            assert exported[3][index] == ""
        assert [row[40] for row in exported[1:3]] == ["投球", "投球"]
        links = _rows(archive, "play_links.csv")
        assert [row[4] for row in links[1:]] == [str(row[0]) for row in snapshots]
        innings = _rows(archive, "inning_scores.csv")
        assert [(row[5], row[6], row[7], row[8]) for row in innings[1:]] == [
            ("1", "top", "in-progress", "0"),
            ("1", "bottom", "unplayed", ""),
        ]
        assert {row[3] for row in innings[1:]} == {str(snapshots[-1][0])}
