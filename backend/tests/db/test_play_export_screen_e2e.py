"""現行v3の画面記録から実ダウンロードZIPと保存原本を照合する。"""

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
    """保存済み完成CSVを独立readerでBOMから復元する。"""
    return list(
        csv.reader(io.StringIO(archive.read(name).decode("utf-8-sig"), newline=""))
    )


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="所有loopback TLS資材PATH未供給。画面実測は未成立",
)
def test_actual_screen_downloads_two_play_product_zip(vertical_database, tmp_path):
    """真正画面2球→同TX88列→実ZIP保存bytesを同じowned版へ照合する。"""
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
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        ddl = (
            _ROOT / "docs/features/ud2-csv-export/candidates/play_export_snapshots.sql"
        ).read_text()
        admin.execute(sql.SQL(cast(LiteralString, ddl)))
        admin.execute(sql.SQL(cast(LiteralString, candidate_install_sql())))
        _source_query, source_install = candidate_read_bundle()
        admin.execute(sql.SQL(cast(LiteralString, source_install)))
    assert teams is not None
    path = tmp_path / "play-csv-screen.zip"
    token = uuid4()
    config = "GameScreenPlayCsv.playwright.config.ts"
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(db, config, "play-csv-screen", https=True) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "play-csv-screen",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_CSV_DOWNLOAD_PATH": str(path),
                },
            )
    if result.returncode:
        (tmp_path / "playwright-stdout.log").write_text(result.stdout)
        (tmp_path / "playwright-stderr.log").write_text(result.stderr)
    assert result.returncode == 0, (result.stdout[-6000:], result.stderr[-1000:])
    lines = re.findall(r"PITCHLOG_CSV_SCREEN_FINAL=(\{[^\n]+\})", result.stdout)
    assert len(lines) == 1 and path.is_file()
    observed = json.loads(lines[0])
    game = UUID(observed["gameId"])
    assert game != db.game_id and observed["plays"] == 2
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
        accepted = admin.execute(
            "SELECT id FROM public.operation_events WHERE tenant_id=%s "
            "AND game_id=%s AND event_kind='play_input' AND ledger_kind='accepted' "
            "ORDER BY d2",
            (db.tenant_id, game),
        ).fetchall()
    assert len(snapshots) == len(accepted) == 2
    assert [row[0] for row in snapshots] == [row[0] for row in accepted]
    for index, (_source, _play, values, full) in enumerate(snapshots, 1):
        assert set(values) == set(CSV_HEADERS["plays.csv"])
        assert values["球数"] == str(index)
        assert full[0] == {
            "inning": 1,
            "half": "top",
            "state": "in-progress",
            "runs": 0,
        }

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
        plays = _rows(archive, "plays.csv")
        assert len(plays) == 3 and len(plays[0]) == 88
        assert [row[34] for row in plays[1:]] == ["1", "2"]
        links = _rows(archive, "play_links.csv")
        assert [row[4] for row in links[1:]] == [str(row[0]) for row in snapshots]
        innings = _rows(archive, "inning_scores.csv")
        assert [(row[5], row[6], row[7], row[8]) for row in innings[1:]] == [
            ("1", "top", "in-progress", "0"),
            ("1", "bottom", "unplayed", ""),
        ]
        assert {row[3] for row in innings[1:]} == {str(snapshots[-1][0])}
