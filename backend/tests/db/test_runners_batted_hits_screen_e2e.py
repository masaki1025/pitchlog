"""走者あり打球2シナリオを実画面・owned PG・実同期で照合する。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import apply_product_authz_ddl
from pitchlog.repositories.ordinary_prefix_read import _evaluate_lineup_payload
from pitchlog.repositories.recorded_snapshot_operations import RECORDED_PLAY_ROW_COLUMNS
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _LOGS, _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db

ROOT = Path(__file__).resolve().parents[3]
_RESULTS = {
    "single-first-to-third": "batting-result.single",
    "double-first-to-home": "batting-result.double",
    "home-run-first-second": "batting-result.home-run",
}


def _run_runner_playwright(db, origin: str, extra_env: dict[str, str]):
    """共通runnerの期限超過出力を既ログへ保存し、元の失敗を再送出する。"""
    try:
        return _run_playwright(
            db,
            "GameScreenRunnersBattedHits.playwright.config.ts",
            origin,
            "runners-batted-hits",
            extra_env,
        )
    except subprocess.TimeoutExpired as error:
        try:
            _LOGS.mkdir(parents=True, exist_ok=True)
            (_LOGS / "runners-batted-hits-playwright.log").write_bytes(
                (
                    error.stdout.encode("utf-8")
                    if isinstance(error.stdout, str)
                    else error.stdout or b""
                )
                + b"\n"
                + (
                    error.stderr.encode("utf-8")
                    if isinstance(error.stderr, str)
                    else error.stderr or b""
                )
            )
        except OSError:
            error.add_note("Playwright期限超過の部分出力を保存できませんでした")
        raise


def _verify_saved_rows(admin, tenant, game, scenario: str) -> None:
    """実原本を唯一reader/projectorへ通し、親41列とrunner全列を照合する。"""
    records = admin.execute(
        "SELECT to_jsonb(p), e.payload FROM public.play_rows AS p "
        "JOIN public.operation_events AS e "
        "ON e.tenant_id=p.tenant_id AND e.id=p.source_event_id "
        "WHERE p.tenant_id=%s AND p.game_id=%s "
        "ORDER BY p.play_number LIMIT 3",
        (tenant, game),
    ).fetchall()
    expected_count = 3 if scenario == "home-run-first-second" else 2
    assert len(records) == expected_count
    for index, (actual, raw) in enumerate(records):
        payload = _evaluate_lineup_payload(raw)
        request = payload.calculation.request
        response = payload.calculation.response.value
        expected = pitch_physical_row(
            payload.observations,
            payload.participants,
            request.t1.result_id,
            tenant_id=tenant,
            game_id=UUID(game),
            source_event_id=UUID(actual["source_event_id"]),
            row_id=UUID(actual["id"]),
            play_number=actual["play_number"],
        )
        assert len(actual) == len(RECORDED_PLAY_ROW_COLUMNS) == 41
        assert set(actual) == set(RECORDED_PLAY_ROW_COLUMNS)
        assert actual == expected
        runners = admin.execute(
            "SELECT to_jsonb(r) FROM public.play_runners AS r "
            "WHERE tenant_id=%s AND play_id=%s ORDER BY base LIMIT 4",
            (tenant, actual["id"]),
        ).fetchall()
        expected_runners = runner_physical_rows(
            request.source.runners,
            t1=response.t1,
            tenant_id=tenant,
            play_id=UUID(actual["id"]),
        )
        assert [r[0] for r in runners] == expected_runners
        if index == 0:
            assert runners == []
            assert response.t1.after.state_fields.runners == "first"
            assert response.t1.after.state_fields.balls == "0"
            assert response.t1.after.state_fields.strikes == "0"
            assert response.t1.after.state_fields.outs == "0"
            assert response.t1.after.batting_order_by_side.away == "2"
            assert response.t1.after.batting_order_by_side.home == "1"
        elif scenario == "home-run-first-second" and index == 1:
            assert actual["batting_result_key"] == "batting-result.single"
            assert response.t1.after.state_fields.runners == "first-second"
            assert response.t1.after.state_fields.score.away == "0"
            assert response.t1.runner_default_advance.first.modality == "forced"
            assert response.t1.runner_default_advance.first.destination == "2"
        else:
            assert actual["batting_result_key"] == _RESULTS[scenario]
            assert request.t1.runner_advance_overrides.kind == "applied"
            observation = payload.observations.runner_advance_overrides
            assert observation.kind == "applied"
            assert [
                (o.runner_base, o.destination)
                for o in request.t1.runner_advance_overrides.overrides
            ] == [(o.runner_base, o.destination) for o in observation.overrides]
            if scenario == "single-first-to-third":
                assert response.t1.after.state_fields.runners == "first-third"
                assert response.t1.after.state_fields.score.away == "0"
                assert response.t1.after.batting_order_by_side.away == "3"
                assert sorted(
                    (r.runner_id, r.base) for r in response.runners
                ) == sorted(
                    [
                        (payload.participants.batter_id, "1"),
                        (request.source.runners[0].runner_id, "3"),
                    ]
                )
            elif scenario == "double-first-to-home":
                assert response.t1.after.state_fields.runners == "second"
                assert response.t1.after.state_fields.score.away == "1"
                assert response.t1.after.batting_order_by_side.away == "3"
                assert [(r.runner_id, r.base) for r in response.runners] == [
                    (payload.participants.batter_id, "2")
                ]
                assert response.t1.stat_flags.run is True
                assert response.t1.stat_flags.rbi is True
            else:
                assert index == 2
                assert len(request.source.runners) == 2
                assert response.t1.after.state_fields.runners == "empty"
                assert response.t1.after.state_fields.score.away == "3"
                assert response.t1.after.scoreboard.inning_scores.away == "3"
                assert response.runners == ()
                assert response.t1.stat_flags.run is True
                assert response.t1.stat_flags.rbi is True
                assert response.t1.stat_flags.home_run is True
    ledger = admin.execute(
        "SELECT count(*) FROM public.idempotency_ledger AS l "
        "JOIN public.operation_events AS e "
        "ON l.tenant_id=e.tenant_id AND l.d5=e.d5 "
        "WHERE e.tenant_id=%s AND e.game_id=%s",
        (tenant, game),
    ).fetchone()
    assert ledger == (expected_count,)


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS証明書/鍵PATH未供給のため走者あり打球の画面縦断は未実証",
)
def test_screen_runner_batted_hits(vertical_database) -> None:
    """走者状態は画面の先行単打だけで作り、DBへ事前投入しない。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        apply_product_authz_ddl(admin)
        identity = admin.execute(
            "SELECT oid FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert identity is not None
        report = inspect_product_authz_catalog(
            admin, privileged_role_oids=frozenset({identity[0]})
        )
        assert report.ok, [v.check_id for v in report.violations]
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        for key in _RESULTS.values():
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, key),
            )
        for key in ("batted.screen.line", "batted.screen.hard"):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batted_ball',%s) ON CONFLICT(key) DO NOTHING",
                (key, key),
            )
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            "GameScreenRunnersBattedHits.playwright.config.ts",
            "runners-batted-hits",
            https=True,
        ) as origin:
            completed = _run_runner_playwright(
                db,
                origin,
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_OTHER_TEAM": db.other_team_name,
                    "PITCHLOG_E2E_RESULT_FILE": (
                        "/tmp/opencode/pitchlog-runner-e2e/result-game.txt"
                    ),
                },
            )
            assert completed.returncode == 0, (
                completed.stdout[-10000:],
                completed.stderr[-3000:],
            )
            observed = [
                json.loads(value)
                for value in re.findall(
                    r"PITCHLOG_RUNNER_SCREEN_RESULT=(\{[^\n]+\})",
                    completed.stdout,
                )
            ]
            assert len(observed) == 3
            assert {r["scenario"] for r in observed} == set(_RESULTS)
            created_games = {r["game"] for r in observed}
            assert len(created_games) == 3
            assert str(db.game_id) not in created_games
            with psycopg.connect(db.authority.database.business_admin) as admin:
                for result in observed:
                    game = result["game"]
                    for table in ("play_rows", "operation_events", "event_slots"):
                        count = admin.execute(
                            sql.SQL(
                                "SELECT count(*) FROM public.{} "
                                "WHERE tenant_id=%s AND game_id=%s"
                            ).format(sql.Identifier(table)),
                            (db.tenant_id, game),
                        ).fetchone()
                        expected_count = (
                            3 if result["scenario"] == "home-run-first-second" else 2
                        )
                        assert count == (expected_count,), table
                    _verify_saved_rows(admin, db.tenant_id, game, result["scenario"])
