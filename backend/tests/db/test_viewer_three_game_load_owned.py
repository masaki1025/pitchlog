"""同時3試合の記録3contextと閲覧30contextを所有環境で実測する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest

from .owned_pg_network_lock import owned_pg_browser_network_lock
from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database
from .viewer_owned_support import assert_current_viewer_catalog

pytestmark = pytest.mark.requires_db

_QUERIES: dict[str, LiteralString] = {
    "game": "SELECT status FROM public.games WHERE tenant_id=%s AND id=%s",
    "plays": "SELECT count(*) FROM public.play_rows "
    "WHERE tenant_id=%s AND game_id=%s AND hidden_at IS NULL",
    "results": "SELECT batting_result_key FROM public.play_rows "
    "WHERE tenant_id=%s AND game_id=%s AND hidden_at IS NULL ORDER BY play_number,id",
    "events": "SELECT count(*) FROM public.operation_events "
    "WHERE tenant_id=%s AND game_id=%s "
    "AND ledger_kind='accepted' AND event_kind='play_input'",
}


@pytest.fixture(autouse=True)
def _exclusive_fixture_lifetime():
    """fixture作成前から破棄後まで共通排他を保つ。外側flockとの二重取得は禁止。"""
    # owned launcherが外部DSNを拒否し、新一時PGのDSNだけをpytestへ注入する。
    # ここで環境変数の存在を拒むと、その正規owned注入まで必ず拒否してしまう。
    # 実接続のsubject/identityは既db autouse guardと専用fixtureが照合する。
    with owned_pg_browser_network_lock():
        yield


def test_three_games_and_thirty_viewers(
    vertical_database, monkeypatch, tmp_path
) -> None:
    """実UIの新規3試合を2wave記録し、30閲覧の自然更新と保存値を照合する。"""
    from . import test_screen_start_e2e as harness

    for key in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(key)
        assert path and Path(path).is_absolute() and Path(path).is_file()
    db = vertical_database
    evidence = Path.home() / ".cache/pitchlog/viewer-three-game-load-20261108"
    evidence.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(harness, "_LOGS", evidence / "browser-logs")
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert_current_viewer_catalog(admin)
        for key, label in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.swinging-strike", "空振り"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, label),
            )
        for query in _QUERIES.values():
            admin.execute("EXPLAIN " + query, (db.tenant_id, db.game_id))
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
    assert teams is not None
    game_path = tmp_path / "created-games.json"
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            "GameScreenViewerThreeGameLoad.playwright.config.ts",
            "viewer-three-game",
            https=True,
        ) as origin:
            result = _run_playwright(
                db,
                "GameScreenViewerThreeGameLoad.playwright.config.ts",
                origin,
                "viewer-three-game",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_VIEWER_LOAD_GAME_PATH": str(game_path),
                },
                timeout_seconds=960,
            )
            partial = {"audit": "not-created"}
            if game_path.is_file():
                try:
                    game_ids = json.loads(game_path.read_text())["gameIds"]
                    assert type(game_ids) is list and 1 <= len(game_ids) <= 3
                    assert len(game_ids) == len(set(game_ids))
                    rows = []
                    with psycopg.connect(
                        db.authority.database.business_admin,
                        options="-c default_transaction_read_only=on",
                    ) as admin:
                        for item in game_ids:
                            game_id = UUID(item)
                            assert game_id != db.game_id
                            rows.append(
                                {
                                    name: admin.execute(
                                        query, (db.tenant_id, game_id)
                                    ).fetchall()
                                    for name, query in _QUERIES.items()
                                }
                            )
                    partial = {"audit": "actual", "games": rows}
                except Exception as error:
                    partial = {
                        "audit": "unavailable",
                        "exception": type(error).__name__,
                    }
            (evidence / "partial-db.json").write_text(
                json.dumps(partial, default=str) + "\n"
            )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-2000:],
            )
            match = re.search(
                r"PITCHLOG_VIEWER_THREE_GAME_RESULT=(\{[^\n]+\})", result.stdout
            )
            assert match is not None
            actual = json.loads(match[1])
            assert (
                actual["writers"],
                actual["viewers"],
                actual["independentContexts"],
                actual["waves"],
            ) == (3, 30, 33, 2)
            assert len(actual["gameIds"]) == len(set(actual["gameIds"])) == 3
            assert len(actual["timings"]) == 60
            assert {(r["wave"], r["viewer"]) for r in actual["timings"]} == {
                (wave, viewer) for wave in (1, 2) for viewer in range(30)
            }
            assert all(
                type(r["milliseconds"]) is int and 0 <= r["milliseconds"] <= 10000
                for r in actual["timings"]
            )
            assert len(actual["writeTraffic"]) == 6
            for wave in (1, 2):
                traffic = [row for row in actual["writeTraffic"] if row["wave"] == wave]
                assert {row["game"] for row in traffic} == {0, 1, 2}
                assert max(row["start"] for row in traffic) < min(
                    row["end"] for row in traffic
                )
            with psycopg.connect(db.authority.database.business_admin) as admin:
                for game_index, game in enumerate(actual["gameIds"]):
                    game_id = UUID(game)
                    assert game_id != db.game_id
                    assert admin.execute(
                        _QUERIES["game"], (db.tenant_id, game_id)
                    ).fetchone() == ("in_progress",)
                    assert admin.execute(
                        _QUERIES["plays"], (db.tenant_id, game_id)
                    ).fetchone() == (2,)
                    assert admin.execute(
                        _QUERIES["events"], (db.tenant_id, game_id)
                    ).fetchone() == (2,)
                    assert admin.execute(
                        _QUERIES["results"], (db.tenant_id, game_id)
                    ).fetchall() == [
                        (result,) for result in actual["gameResults"][game_index]
                    ]
            (evidence / "result.json").write_text(
                json.dumps(actual, ensure_ascii=False, indent=2) + "\n"
            )
