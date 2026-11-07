"""実画面の取消・再入力で有効CSVと旧監査原本を検証する。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import threading
import time
import zipfile
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.play_export_writer_product import candidate_install_sql
from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import apply_product_authz_ddl
from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db
_ROOT = Path(__file__).resolve().parents[3]


def _csv_rows(archive: zipfile.ZipFile, name: str) -> list[list[str]]:
    """BOM付きの完成bytesから行を読む。"""
    return list(csv.reader(io.StringIO(archive.read(name).decode("utf-8-sig"))))


def _observe_current_sources(db, directory: Path, stop: threading.Event) -> None:
    """画面の次操作前に現行T5版と有限source identityを保存する。"""
    for label in ("one-current", "all-undone", "reentered", "reloaded"):
        ready = directory / f"{label}.ready"
        deadline = time.monotonic() + 180
        while not ready.exists():
            if stop.is_set():
                return
            if time.monotonic() >= deadline:
                raise AssertionError(f"{label}: 版観測要求がない")
            time.sleep(0.05)
        game = UUID(ready.read_text(encoding="utf-8"))
        with psycopg.connect(
            db.authority.database.business_admin,
            options="-c default_transaction_read_only=on",
        ) as admin:
            versions = admin.execute(
                "SELECT id,revision,source_count,source_set_sha256,completion_state,"
                "last_generation,last_d1,last_d2 FROM sync_fence.stats_fact_versions "
                "WHERE tenant_id=%s AND game_id=%s AND model_sha256=%s "
                "AND is_current AND invalidated_at IS NULL",
                (db.tenant_id, game, SOURCE_MODEL_HASH),
            ).fetchall()
            assert len(versions) == 1, (label, len(versions))
            version = versions[0]
            sources = admin.execute(
                "SELECT source_event_id,play_row_id,recording_generation,d1,d2,"
                "slot_version,play_row_version,provider_kind "
                "FROM sync_fence.stats_primitive_sources "
                "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s "
                "ORDER BY recording_generation,d1,slot_version",
                (db.tenant_id, game, version[0]),
            ).fetchall()
        record = {
            "label": label,
            "game": str(game),
            "version_id": str(version[0]),
            "revision": version[1],
            "source_count": version[2],
            "source_set_sha256": version[3],
            "completion_state": version[4],
            "last_position": list(version[5:]),
            "sources": [
                {
                    "source_event_id": str(row[0]),
                    "play_row_id": str(row[1]),
                    "generation": row[2],
                    "d1": row[3],
                    "d2": row[4],
                    "slot_version": row[5],
                    "play_row_version": row[6],
                    "provider_kind": row[7],
                }
                for row in sources
            ],
        }
        (directory / f"{label}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (directory / f"{label}.observed").write_text("ok\n", encoding="utf-8")


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="所有loopback TLS資材PATH未供給。画面実測は未成立",
)
def test_actual_undo_effective_csv_and_preserved_snapshot(vertical_database, tmp_path):
    """2球→1取消→全取消→再入力→reloadの実ZIPを同一試合で照合する。"""
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
        ddl = (
            _ROOT / "docs/features/ud2-csv-export/candidates/play_export_snapshots.sql"
        ).read_text()
        admin.execute(sql.SQL(cast(LiteralString, ddl)))
        admin.execute(sql.SQL(cast(LiteralString, candidate_install_sql())))
    assert teams is not None
    token = uuid4()
    config = "GameScreenPlayCsvEffective.playwright.config.ts"
    observer = tmp_path / "t5-observations"
    observer.mkdir()
    stop = threading.Event()
    failures: list[BaseException] = []

    def observe() -> None:
        try:
            _observe_current_sources(db, observer, stop)
        except BaseException as error:
            failures.append(error)

    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, config, "play-csv-effective", https=True
        ) as origin:
            worker = threading.Thread(target=observe, daemon=True)
            worker.start()
            try:
                run = _run_playwright(
                    db,
                    config,
                    origin,
                    "play-csv-effective",
                    {
                        "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                        "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                        "PITCHLOG_E2E_CSV_DOWNLOAD_DIR": str(tmp_path),
                        "PITCHLOG_E2E_CSV_OBSERVER_DIR": str(observer),
                    },
                )
            finally:
                stop.set()
                worker.join(timeout=5)
    assert not worker.is_alive() and not failures, failures
    if run.returncode:
        (tmp_path / "playwright-stdout.log").write_text(run.stdout)
        (tmp_path / "playwright-stderr.log").write_text(run.stderr)
    assert run.returncode == 0, (run.stdout[-7000:], run.stderr[-1200:])
    lines = re.findall(r"PITCHLOG_EFFECTIVE_CSV_RESULT=(\{[^\n]+\})", run.stdout)
    assert len(lines) == 1
    result = json.loads(lines[0])
    game = UUID(result["game"])
    assert game != db.game_id
    expected = (
        ("one-current", 1, 2, 3),
        ("all-undone", 0, 2, 4),
        ("reentered", 1, 3, 5),
        ("reloaded", 1, 3, 5),
    )
    assert [file["label"] for file in result["files"]] == [item[0] for item in expected]
    observed = [
        json.loads((observer / f"{label}.json").read_text(encoding="utf-8"))
        for label, *_ in expected
    ]
    assert [item["source_count"] for item in observed] == [1, 0, 1, 1]
    assert [item["revision"] for item in observed] == [3, 4, 5, 5]
    assert all(item["completion_state"] == "current_open" for item in observed)
    assert observed[2]["version_id"] == observed[3]["version_id"]
    assert observed[2]["source_set_sha256"] == observed[3]["source_set_sha256"]
    assert all(item["source_count"] == len(item["sources"]) for item in observed)
    assert observed[0]["sources"] != observed[2]["sources"]
    assert observed[2]["sources"] == observed[3]["sources"]
    archived: dict[str, dict[str, list[list[str]]]] = {}
    for item, (label, active, historical, events) in zip(
        result["files"], expected, strict=True
    ):
        file = tmp_path / f"{label}.zip"
        assert item["filename"] == str(file) and file.is_file()
        data = file.read_bytes()
        assert len(data) == item["bytes"] and data.startswith(b"PK")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert archive.testzip() is None
            assert set(archive.namelist()) == set(CSV_HEADERS) | {"manifest.json"}
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["game_id"] == str(game)
            assert len(manifest["files"]) == 11
            tables = {name: _csv_rows(archive, name) for name in CSV_HEADERS}
            for entry in manifest["files"]:
                raw = archive.read(entry["name"])
                assert raw.startswith(b"\xef\xbb\xbf")
                assert entry["byte_length"] == len(raw)
                assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
                assert entry["data_row_count"] == len(tables[entry["name"]]) - 1
                assert tables[entry["name"]][0] == list(CSV_HEADERS[entry["name"]])
            assert len(tables["plays.csv"]) == active + 1
            assert len(tables["plays.csv"][0]) == 88
            assert len(tables["play_links.csv"]) == active + 1
            source = next(item for item in observed if item["label"] == label)
            assert [
                (row[4], row[5], int(row[2]), int(row[3]), int(row[7]))
                for row in tables["play_links.csv"][1:]
            ] == [
                (
                    row["source_event_id"],
                    row["play_row_id"],
                    row["generation"],
                    row["d2"],
                    row["play_row_version"],
                )
                for row in source["sources"]
            ]
            assert len(tables["projections.csv"]) == historical + 1
            assert len(tables["events.csv"]) == events + 1
            archived[label] = tables
    assert archived["reentered"]["plays.csv"] == archived["reloaded"]["plays.csv"]
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        plays = admin.execute(
            "SELECT id,source_event_id,hidden_at IS NOT NULL FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY play_number",
            (db.tenant_id, game),
        ).fetchall()
        snapshots = admin.execute(
            "SELECT play_row_id,source_event_id,plays_csv_json "
            "FROM public.play_export_snapshots "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY event_sequence",
            (db.tenant_id, game),
        ).fetchall()
        accepted = admin.execute(
            "SELECT id,event_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s AND ledger_kind='accepted' "
            "ORDER BY d1",
            (db.tenant_id, game),
        ).fetchall()
    assert len(plays) == len(snapshots) == 3
    assert [row[2] for row in plays] == [True, True, False]
    assert [(row[0], row[1]) for row in snapshots] == [
        (row[0], row[1]) for row in plays
    ]
    assert [kind for _, kind in accepted] == [
        "play_input",
        "play_input",
        "undo",
        "undo",
        "play_input",
    ]
    for label in ("reentered", "reloaded"):
        projections = archived[label]["projections.csv"]
        assert {row[3] for row in projections[1:]} == {str(row[1]) for row in snapshots}
        assert {row[6] for row in projections[1:]} == {
            json.dumps(
                row[2], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            for row in snapshots
        }
