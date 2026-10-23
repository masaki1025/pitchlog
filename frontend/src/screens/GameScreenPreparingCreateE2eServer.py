"""実画面作成だけへ所有3PG/実authority/controller/APIを供給する。"""

from __future__ import annotations

import json
import os
import re
import signal
import stat
import time
from pathlib import Path
from types import FrameType
from urllib.parse import urlsplit

import psycopg
import pytest
from db.durable_rights_ledger_support import AuthorityDatabase
from db.rg1_preparing_create_support import PreparingCreateDatabase
from db.test_rg1_preparing_create_connection import (
    admin_connection as admin_connection,
)
from db.test_rg1_preparing_create_connection import (
    authority_database as authority_database,
)
from db.test_rg1_preparing_create_connection import (
    tested_role_connection as tested_role_connection,
)

pytest_plugins = ("db_fixtures",)
pytestmark = pytest.mark.requires_db


def _write_owned(path: Path, value: object) -> None:
    """所有0700領域の新規0600ファイルへ値を保存する。"""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False)


def test_actual_browser_preparing_create(authority_database: AuthorityDatabase) -> None:
    """games投入0で実製品を起動し、ブラウザ終了後に実保存全列を観測する。"""
    ready = Path(os.environ["PITCHLOG_E2E_READY_FILE"])
    stop = Path(os.environ["PITCHLOG_E2E_STOP_FILE"])
    frontend_origin = os.environ["PITCHLOG_E2E_FRONTEND_ORIGIN"]
    database = PreparingCreateDatabase(authority_database)
    try:
        database.prepare()
        database.start_api(frontend_origin=frontend_origin)
        identity = database.identity
        assert identity is not None and database.origin is not None
        port = urlsplit(database.origin).port
        assert port is not None
        _write_owned(
            ready,
            {
                "port": port,
                "identities": [
                    {
                        "name": identity.name,
                        "password": identity.password,
                        "tenantId": str(identity.tenant_id),
                    }
                ],
                "teams": [str(team) for team in database.teams],
            },
        )
        deadline = time.monotonic() + 600
        while not stop.exists() and time.monotonic() < deadline:
            assert database.api_running(), "所有実APIが終了した"
            assert database.controller.running(), "所有実controllerが終了した"
            time.sleep(0.1)
        assert stop.exists(), "実browser終了通知がない"
        with psycopg.connect(authority_database.database.business_admin) as observer:
            rows = observer.execute(
                "SELECT id,tenant_id,scheduled_at,game_type_key,tournament_key,"
                "away_team_record_id,home_team_record_id,plate_umpire,"
                "section_label,week_label,day_label,game_number_label,status,"
                "applied_rules,rule_override,started_at FROM public.games"
            ).fetchall()
            assert len(rows) == 1, "実画面作成以外のgame又は保存欠落を拒否"
            row = rows[0]
            assert row[1] == identity.tenant_id
            assert row[12] == "preparing" and row[14:] == (None, None)
            names = observer.execute(
                "SELECT display_name FROM public.tenant_vocabularies "
                "WHERE tenant_id=%s AND category='tournament' AND key=%s",
                (identity.tenant_id, row[4]),
            ).fetchall()
            assert len(names) == 1
        assert authority_database.event_counts().get("activation_open") == 1
        _write_owned(
            ready.parent / "database-evidence.json",
            {
                "game_count": len(rows),
                "game": {
                    "id": str(row[0]),
                    "scheduled_at": row[2].isoformat(),
                    "game_type_key": row[3],
                    "tournament_key": row[4],
                    "away_team_record_id": str(row[5]),
                    "home_team_record_id": str(row[6]),
                    "plate_umpire": row[7],
                    "section_label": row[8],
                    "week_label": row[9],
                    "day_label": row[10],
                    "game_number_label": row[11],
                    "status": row[12],
                    "applied_rules": row[13],
                },
                "tournament_display_name": names[0][0],
                "activation_open_count": 1,
            },
        )
    finally:
        database.close()


def _terminate(_signum: int, _frame: FrameType | None) -> None:
    """所有fixtureのfinallyへSIGTERMを伝える。"""
    raise KeyboardInterrupt


def main() -> int:
    """外部DSNを破棄し、既存実identity autouseを保ったpytestを起動する。"""
    ready = Path(os.environ["PITCHLOG_E2E_READY_FILE"])
    stop = Path(os.environ["PITCHLOG_E2E_STOP_FILE"])
    directory = ready.parent
    origin = os.environ["PITCHLOG_E2E_FRONTEND_ORIGIN"]
    matched = re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})", origin)
    assert matched is not None and int(matched.group(1)) <= 65535
    assert ready.name == "backend-ready.json" and stop == directory / "stop"
    assert directory.name.startswith("pitchlog-e2e-")
    assert not directory.is_symlink() and directory.stat().st_uid == os.getuid()
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for name in tuple(os.environ):
        if name.startswith("PITCHLOG_") and name not in {
            "PITCHLOG_E2E_READY_FILE",
            "PITCHLOG_E2E_STOP_FILE",
            "PITCHLOG_E2E_FRONTEND_ORIGIN",
        }:
            os.environ.pop(name)
    signal.signal(signal.SIGTERM, _terminate)
    return int(
        pytest.main(
            [
                "-c",
                str(Path(__file__).resolve().parents[3] / "backend/pyproject.toml"),
                str(Path(__file__).resolve()),
                "-q",
                "-p",
                "no:cacheprovider",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
