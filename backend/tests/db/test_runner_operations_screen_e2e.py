"""同一試合の走塁操作を実画面・実保存・原本全値で検査する。"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.repositories.ordinary_prefix_read import _evaluate_lineup_payload
from pitchlog.repositories.recorded_snapshot_operations import RECORDED_PLAY_ROW_COLUMNS
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db
_CONFIG = "GameScreenRunnerOperations.playwright.config.ts"


def _install_runner_fault_server(monkeypatch) -> None:
    """隔離appだけに固定T4故障を注入し、実認可/実TX/元応答は変更しない。"""
    from . import test_screen_start_e2e as screen

    original = screen._app_container
    bootstrap = r"""
import sys,uvicorn
from pitchlog.api.app import create_app
from pitchlog.sync.crash_points import testing_crash_hook
app=create_app()
class OwnedRunnerT4Fault(RuntimeError):
 pass
@app.middleware('http')
async def owned_runner_fault(request,call_next):
 if (request.method=='POST'
     and request.url.path.endswith('/sync/events')
     and request.headers.get('X-Pitchlog-Owned-Runner-Fault')=='after_t4_projection'):
  def fail(point):
   if point=='after_t4_projection':
    print('PITCHLOG_RUNNER_T4_REACHED',flush=True)
    raise OwnedRunnerT4Fault('owned runner projection fault')
  with testing_crash_hook(fail):
   return await call_next(request)
 return await call_next(request)
uvicorn.run(app,host='0.0.0.0',port=int(sys.argv[1]),log_level='warning')
"""

    def app_arguments(db, app_port, origin):
        command = original(db, app_port, origin)
        positions = [
            index
            for index in range(len(command) - 1)
            if command[index : index + 2] == ["-m", "uvicorn"]
        ]
        assert len(positions) == 1, "owned故障serverの既bootstrap形が不一致"
        return [*command[: positions[0]], "-c", bootstrap, str(app_port)]

    monkeypatch.setattr(screen, "_app_container", app_arguments)


def _all_runner_stats(admin, tenant, game):
    """有効/旧版を含む実T5全行を、当該owned試合だけで閉じて読む。"""
    return {
        table: [
            r[0]
            for r in admin.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) FROM sync_fence.{} AS t "
                    "WHERE tenant_id=%s AND game_id=%s ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(table)),
                (tenant, game),
            ).fetchall()
        ]
        for table in (
            "stats_fact_versions",
            "stats_primitive_sources",
            "stats_primitive_facts",
        )
    }


def _capture_runner_fault_baseline(db, checkpoint, stop):
    """実画面の先行1球後を読取専用で封印してから、2球目の送信を許可する。"""
    while not checkpoint.is_file():
        if stop.wait(0.05):
            return None
    game = UUID(json.loads(checkpoint.read_text())["game"])
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute("SET TRANSACTION READ ONLY")
        admin.execute("SET LOCAL statement_timeout='5s'")
        before = _all_runner_stats(admin, db.tenant_id, game)
    assert len(before["stats_fact_versions"]) == 1
    assert before["stats_fact_versions"][0]["source_count"] == 1
    checkpoint.with_suffix(".snapshot.json").write_text(
        json.dumps(before, sort_keys=True)
    )
    Path(str(checkpoint) + ".ready").write_text(str(game))
    return game, before


def _verify_runner_fault_rollback(admin, tenant, result, baseline):
    """実故障要求のlogical IDを使い、runnerを含む全保存面の残存を拒否する。"""
    game = UUID(result["game"])
    assert baseline is not None and baseline[0] == game
    assert _all_runner_stats(admin, tenant, game) == baseline[1]
    failed_play = UUID(result["failedPlayId"])
    failed_event = UUID(result["failedEventId"])
    failed_d5 = UUID(result["failedD5"])
    assert result["status"] == 500 and result["prefix"] == "1"
    for table in ("play_rows", "operation_events", "event_slots"):
        assert admin.execute(
            sql.SQL(
                "SELECT count(*) FROM public.{} WHERE tenant_id=%s AND game_id=%s"
            ).format(sql.Identifier(table)),
            (tenant, game),
        ).fetchone() == (1,)
    assert admin.execute(
        "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s AND id=%s",
        (tenant, failed_play),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM public.play_runners WHERE tenant_id=%s AND play_id=%s",
        (tenant, failed_play),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM public.operation_events WHERE tenant_id=%s AND id=%s",
        (tenant, failed_event),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM public.idempotency_ledger WHERE tenant_id=%s AND d5=%s",
        (tenant, failed_d5),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM sync_fence.stats_primitive_sources "
        "WHERE tenant_id=%s AND source_event_id=%s",
        (tenant, failed_event),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM sync_fence.stats_primitive_facts "
        "WHERE tenant_id=%s AND source_event_id=%s",
        (tenant, failed_event),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT count(*) FROM public.play_export_snapshots "
        "WHERE tenant_id=%s AND source_event_id=%s",
        (tenant, failed_event),
    ).fetchone() == (0,)
    assert admin.execute(
        "SELECT source_count FROM sync_fence.stats_fact_versions "
        "WHERE tenant_id=%s AND game_id=%s AND is_current",
        (tenant, game),
    ).fetchall() == [(1,)]


def _verify_rows(admin, tenant, game: str, result: dict) -> None:
    """唯一計算が返した原値と実41列/全走者、および独立した終状態を照合する。"""
    count = 2 if result["scope"] == "first" else 17
    assert result["length"] == count
    records = admin.execute(
        "SELECT to_jsonb(p),e.payload FROM public.play_rows AS p "
        "JOIN public.operation_events AS e "
        "ON e.tenant_id=p.tenant_id AND e.id=p.source_event_id "
        "WHERE p.tenant_id=%s AND p.game_id=%s ORDER BY p.play_number LIMIT 18",
        (tenant, game),
    ).fetchall()
    assert len(records) == count
    assert len(result["records"]) == count
    for index, (actual, raw) in enumerate(records):
        payload = _evaluate_lineup_payload(raw)
        request = payload.calculation.request
        value = payload.calculation.response.value
        assert len(actual) == len(RECORDED_PLAY_ROW_COLUMNS) == 41
        assert set(actual) == set(RECORDED_PLAY_ROW_COLUMNS)
        assert actual == pitch_physical_row(
            payload.observations,
            payload.participants,
            request.t1.result_id,
            tenant_id=tenant,
            game_id=UUID(game),
            source_event_id=UUID(actual["source_event_id"]),
            row_id=UUID(actual["id"]),
            play_number=actual["play_number"],
        )
        runners = admin.execute(
            "SELECT to_jsonb(r) FROM public.play_runners AS r "
            "WHERE tenant_id=%s AND play_id=%s ORDER BY base LIMIT 4",
            (tenant, actual["id"]),
        ).fetchall()
        assert [r[0] for r in runners] == runner_physical_rows(
            request.source.runners,
            t1=value.t1,
            t1_input=request.t1,
            tenant_id=tenant,
            play_id=UUID(actual["id"]),
        )
        observed = result["records"][index]
        assert observed["after"] == value.t1.after.model_dump(by_alias=True)
        assert observed["runners"] == [
            r.model_dump(by_alias=True) for r in value.runners
        ]
        if index == 1:
            assert actual["event_kind"] == "non_pitch"
            assert actual["course_x"] is None and actual["course_y"] is None
            assert value.runners[0].base == "2"
            assert value.runners[0].runner_id == request.source.runners[0].runner_id
            assert (
                value.runners[0].responsible_pitcher_id
                == request.source.runners[0].responsible_pitcher_id
            )
    for table in ("operation_events", "event_slots", "play_rows"):
        assert admin.execute(
            sql.SQL(
                "SELECT count(*) FROM public.{} WHERE tenant_id=%s AND game_id=%s"
            ).format(sql.Identifier(table)),
            (tenant, game),
        ).fetchone() == (count,), table
    assert result["replay"] == {"status": 200, "a5": "重複"}
    assert admin.execute(
        "SELECT count(*) FROM public.idempotency_ledger AS l "
        "JOIN public.operation_events AS e ON e.tenant_id=l.tenant_id AND e.d5=l.d5 "
        "WHERE e.tenant_id=%s AND e.game_id=%s",
        (tenant, game),
    ).fetchone() == (count,)
    version = admin.execute(
        "SELECT id,source_count,completion_state FROM sync_fence.stats_fact_versions "
        "WHERE tenant_id=%s AND game_id=%s AND is_current",
        (tenant, game),
    ).fetchall()
    assert len(version) == 1 and version[0][1:] == (count, "current_open")
    sums = dict(
        admin.execute(
            "SELECT metric_id,SUM(amount) FROM sync_fence.stats_primitive_facts "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s "
            "GROUP BY metric_id",
            (tenant, game, version[0][0]),
        ).fetchall()
    )
    expected = (
        {"h": 1, "stolen_bases": 1, "pitch_count": 1}
        if count == 2
        else {
            "h": 6,
            "stolen_bases": 1,
            "pitch_count": 11,
            "pitching_outs": 6,
            "k": 1,
            "pitcher_k": 1,
            "runs": 1,
            "runs_allowed": 1,
        }
    )
    assert {key: sums.get(key, 0) for key in expected} == expected
    assert sums.get("rbi", 0) == 0
    if count == 17:
        final = records[-1][1]["calculation"]["response"]["value"]
        fields = final["t1"]["after"]["stateFields"]
        assert fields["state.inning"] == "2"
        assert fields["state.half"] == "top"
        assert fields["state.outs"] == "0"
        assert fields["state.score"] == {"home": "0", "away": "1"}
    print(
        "PITCHLOG_RUNNER_OPERATIONS_DB="
        + json.dumps(
            {
                "scope": result["scope"],
                "plays": count,
                "primitiveSums": {key: str(value) for key, value in sums.items()},
            }
        )
    )


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離実HTTPSの明示TLS PATH未供給。画面縦断未実証",
)
def test_runner_operations_screen(
    vertical_database, tmp_path: Path, monkeypatch
) -> None:
    """UI作成/開始から実走塁の保存・重複・reload・越境とDB全値を照合する。"""
    # 共通owned PG lockはrun_owned.pyがfixture作成からcleanupまで保持する。
    # 内側で再取得すると別fdの同一process lock待ちになるため重複取得しない。
    _install_runner_fault_server(monkeypatch)
    db = vertical_database
    # 外部DSNはlauncherが起動前に除外する。fixtureが設定したowned DSNだけを認める。
    owned_admin = (
        os.environ.get("PITCHLOG_TEST_ADMIN_DSN") == db.authority.database.primary_admin
    )
    owned_role = (
        os.environ.get("PITCHLOG_TEST_ROLE_DSN")
        == db.authority.database.endpoints.primary_dsn
    )
    assert owned_admin and owned_role, "隔離fixtureのDSNへ束縛されていません"
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        # 語彙だけを供給する。証拠試合/走者/プレイは全て実画面が作る。
        vocabularies = [
            ("batting-result.single", "batting_result"),
            ("batting-result.called-pitch", "batting_result"),
            ("batting-result.strikeout-double-play", "batting_result"),
            ("secondary-result.wild-pitch", "batting_result"),
            ("secondary-result.passed-ball", "batting_result"),
            ("secondary-result.balk", "batting_result"),
            ("batted.screen.line", "batted_ball"),
            ("batted.screen.hard", "batted_ball"),
        ]
        for key, category in vocabularies:
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
    assert teams is not None
    result_file = tmp_path / "runner-operations.json"
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, _CONFIG, "runner-operations", https=True
        ) as origin:
            checkpoint = tmp_path / "fault-before.json"
            stop = threading.Event()
            with ThreadPoolExecutor(max_workers=1) as workers:
                captured = workers.submit(
                    _capture_runner_fault_baseline, db, checkpoint, stop
                )
                try:
                    completed = _run_playwright(
                        db,
                        _CONFIG,
                        origin,
                        "runner-operations",
                        {
                            "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                            "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                            "PITCHLOG_E2E_OTHER_TEAM": db.other_team_name,
                            "PITCHLOG_E2E_RESULT_FILE": str(result_file),
                            "PITCHLOG_E2E_RUNNER_FAULT_CHECKPOINT": str(checkpoint),
                        },
                        timeout_seconds=1200,
                    )
                    assert completed.returncode == 0, (
                        completed.stdout[-10000:],
                        completed.stderr[-3000:],
                    )
                finally:
                    stop.set()
                baseline = captured.result()
    result = json.loads(result_file.read_text())
    assert result["scope"] in ("first", "full")
    assert result["gameId"] != str(db.game_id)
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _verify_rows(admin, db.tenant_id, result["gameId"], result)
        fault = json.loads(Path(str(result_file) + ".fault").read_text())
        _verify_runner_fault_rollback(admin, db.tenant_id, fault, baseline)
