"""走者あり4安打を実画面・owned PG・実同期で照合する。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
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
    "single-first-second": "batting-result.single",
    "double-first-second": "batting-result.double",
    "triple-first-second": "batting-result.triple",
    "home-run-loaded": "batting-result.home-run",
    "hit-by-pitch-loaded": "batting-result.hit-by-pitch",
}

_COUNTS = {
    "single-first-to-third": 2,
    "double-first-to-home": 2,
    "home-run-first-second": 3,
    "single-first-second": 3,
    "double-first-second": 3,
    "triple-first-second": 3,
    "home-run-loaded": 4,
    "hit-by-pitch-loaded": 4,
}
_SCORES = {
    "single-first-to-third": 0,
    "double-first-to-home": 1,
    "home-run-first-second": 3,
    "single-first-second": 1,
    "double-first-second": 1,
    "triple-first-second": 2,
    "home-run-loaded": 4,
    "hit-by-pitch-loaded": 1,
}
_AFTER_RUNNERS = {
    "single-first-to-third": "first-third",
    "double-first-to-home": "second",
    "home-run-first-second": "empty",
    "single-first-second": "first-third",
    "double-first-second": "second-third",
    "triple-first-second": "third",
    "home-run-loaded": "empty",
    "hit-by-pitch-loaded": "first-second-third",
}
_AFTER_IDENTITIES = {
    "single-first-to-third": [("batter", "1"), ("1", "3")],
    "double-first-to-home": [("batter", "2")],
    "home-run-first-second": [],
    "single-first-second": [("batter", "1"), ("1", "3")],
    "double-first-second": [("batter", "2"), ("1", "3")],
    "triple-first-second": [("batter", "3")],
    "home-run-loaded": [],
    "hit-by-pitch-loaded": [("batter", "1"), ("1", "2"), ("2", "3")],
}
_STATUSES = {
    "single-first-to-third": {1: [], 2: [(1, "三進", "manual")]},
    "double-first-to-home": {1: [], 2: [(1, "本進", "manual")]},
    "home-run-first-second": {
        1: [],
        2: [(1, "二進", "manual")],
        3: [(1, "本進", "manual"), (2, "本進", "manual")],
    },
    "single-first-second": {
        1: [],
        2: [(1, "二進", "manual")],
        3: [(1, "三進", "manual"), (2, "本進", "manual")],
    },
    "double-first-second": {
        1: [],
        2: [(1, "二進", "manual")],
        3: [(1, "三進", "manual"), (2, "本進", "manual")],
    },
    "triple-first-second": {
        1: [],
        2: [(1, "二進", "manual")],
        3: [(1, "本進", "manual"), (2, "本進", "manual")],
    },
    "home-run-loaded": {
        1: [],
        2: [(1, "二進", "manual")],
        3: [(1, "二進", "manual"), (2, "三進", "manual")],
        4: [(1, "本進", "manual"), (2, "本進", "manual"), (3, "本進", "manual")],
    },
}


_STATUSES["hit-by-pitch-loaded"] = {
    **{key: _STATUSES["home-run-loaded"][key] for key in (1, 2, 3)},
    4: [(1, "二進", "auto"), (2, "三進", "auto"), (3, "本進", "auto")],
}
_TOTAL_BASES = {
    "single-first-to-third": 2,
    "double-first-to-home": 3,
    "home-run-first-second": 6,
    "single-first-second": 3,
    "double-first-second": 4,
    "triple-first-second": 5,
    "home-run-loaded": 7,
    "hit-by-pitch-loaded": 3,
}


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


def _run_runner_playwright(db, origin: str, extra_env: dict[str, str]):
    """共通runnerの期限超過出力を既ログへ保存し、元の失敗を再送出する。"""
    try:
        return _run_playwright(
            db,
            "GameScreenRunnersBattedHits.playwright.config.ts",
            origin,
            "runners-batted-hits",
            extra_env,
            timeout_seconds=900,
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
    """実原本の41列/全走者と、独立した進塁/得点/credit期待を照合する。"""
    count = _COUNTS[scenario]
    records = admin.execute(
        "SELECT to_jsonb(p), e.payload FROM public.play_rows AS p "
        "JOIN public.operation_events AS e "
        "ON e.tenant_id=p.tenant_id AND e.id=p.source_event_id "
        "WHERE p.tenant_id=%s AND p.game_id=%s "
        "ORDER BY p.play_number LIMIT 4",
        (tenant, game),
    ).fetchall()
    assert len(records) == count
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
            t1_input=request.t1,
            tenant_id=tenant,
            play_id=UUID(actual["id"]),
        )
        assert [r[0] for r in runners] == expected_runners
        statuses = [
            (r[0]["base"], r[0]["status"], r[0]["status_source"]) for r in runners
        ]
        assert statuses == _STATUSES[scenario][index + 1]
        assert response.t1.after.state_fields.balls == "0"
        assert response.t1.after.state_fields.strikes == "0"
        assert response.t1.after.state_fields.outs == "0"
        assert response.t1.after.batting_order_by_side.home == "1"
        for runner in response.runners:
            assert runner.responsible_pitcher_id == payload.participants.pitcher_id
        if index < count - 1:
            assert actual["batting_result_key"] == "batting-result.single"
            assert (
                response.t1.after.state_fields.runners
                == ("first", "first-second", "first-second-third")[index]
            )
            assert response.t1.after.state_fields.score.away == "0"
            assert response.t1.after.batting_order_by_side.away == str(index + 2)
            if index:
                assert response.t1.runner_default_advance.first.modality == "forced"
                assert response.t1.runner_default_advance.first.destination == "2"
            continue
        assert actual["batting_result_key"] == _RESULTS[scenario]
        if scenario == "hit-by-pitch-loaded":
            assert response.t1.stat_flags.hit_by_pitch is True
            assert "runnerAdvanceOverrides" not in request.t1.model_dump(
                by_alias=True, exclude_unset=True
            )
            assert [
                (
                    getattr(response.t1.runner_default_advance, name).modality,
                    getattr(response.t1.runner_default_advance, name).destination,
                )
                for name in ("first", "second", "third")
            ] == [("forced", "2"), ("forced", "3"), ("forced", "4")]
        else:
            assert request.t1.runner_advance_overrides.kind == "applied"
            observation = payload.observations.runner_advance_overrides
            assert observation.kind == "applied"
            assert [
                (o.runner_base, o.destination)
                for o in request.t1.runner_advance_overrides.overrides
            ] == [(o.runner_base, o.destination) for o in observation.overrides]
        assert response.t1.after.state_fields.runners == _AFTER_RUNNERS[scenario]
        assert response.t1.after.state_fields.score.away == str(_SCORES[scenario])
        assert response.t1.after.scoreboard.inning_scores.away == str(_SCORES[scenario])
        assert response.t1.after.batting_order_by_side.away == str(count + 1)
        expected_after = []
        for origin, base in _AFTER_IDENTITIES[scenario]:
            runner_id = (
                payload.participants.batter_id
                if origin == "batter"
                else next(
                    r.runner_id for r in request.source.runners if r.base == origin
                )
            )
            expected_after.append((runner_id, base))
        assert sorted((r.runner_id, r.base) for r in response.runners) == sorted(
            expected_after
        )
        assert response.t1.stat_flags.run is (_SCORES[scenario] > 0)
        assert response.t1.stat_flags.rbi is (_SCORES[scenario] > 0)
        assert response.t1.stat_flags.home_run is (
            _RESULTS[scenario] == "batting-result.home-run"
        )
    ledger = admin.execute(
        "SELECT count(*) FROM public.idempotency_ledger AS l "
        "JOIN public.operation_events AS e ON l.tenant_id=e.tenant_id AND l.d5=e.d5 "
        "WHERE e.tenant_id=%s AND e.game_id=%s",
        (tenant, game),
    ).fetchone()
    assert ledger == (count,)
    versions = admin.execute(
        "SELECT id,source_count,completion_state FROM sync_fence.stats_fact_versions "
        "WHERE tenant_id=%s AND game_id=%s AND is_current",
        (tenant, game),
    ).fetchall()
    assert len(versions) == 1
    assert versions[0][1:] == (count, "current_open")
    saved_states = admin.execute(
        "SELECT metric_states FROM sync_fence.stats_primitive_sources "
        "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s ORDER BY d2",
        (tenant, game, versions[0][0]),
    ).fetchall()
    assert len(saved_states) == count
    for (saved,) in saved_states:
        metrics = saved["metrics"]
        assert len(metrics) == 27
        assert {
            k: m["reason"] for k, m in metrics.items() if m["state"] != "available"
        } == {}
        assert metrics["stolen_bases"]["value"] == "0"
    base_facts = admin.execute(
        "SELECT metric_id,SUM(amount) FROM sync_fence.stats_primitive_facts "
        "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s "
        "AND metric_id IN ('total_bases','doubles','triples','stolen_bases') "
        "GROUP BY metric_id",
        (tenant, game, versions[0][0]),
    ).fetchall()
    expected_bases = {"total_bases": _TOTAL_BASES[scenario]}
    if scenario in ("double-first-to-home", "double-first-second"):
        expected_bases["doubles"] = 1
    if scenario == "triple-first-second":
        expected_bases["triples"] = 1
    assert dict(base_facts) == expected_bases
    print(
        "PITCHLOG_RUNNER_DB_STATS="
        + json.dumps(
            {
                "scenario": scenario,
                "sources": count,
                "availableMetricsPerSource": 27,
                "primitiveSums": {k: str(v) for k, v in base_facts},
            }
        )
    )
    if _SCORES[scenario] == 0:
        return  # 0credit行の存在は本単位で仮定せず、T1の0得点/falseで照合済み。
    facts = admin.execute(
        "SELECT metric_id,SUM(amount),COUNT(*) FILTER (WHERE state<>'available') "
        "FROM sync_fence.stats_primitive_facts "
        "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s "
        "AND metric_id IN ('runs','rbi','runs_allowed') GROUP BY metric_id",
        (tenant, game, versions[0][0]),
    ).fetchall()
    assert {metric: (amount, unavailable) for metric, amount, unavailable in facts} == {
        key: (_SCORES[scenario], 0) for key in ("runs", "rbi", "runs_allowed")
    }


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS証明書/鍵PATH未供給のため走者あり打球の画面縦断は未実証",
)
def test_screen_runner_batted_hits(
    vertical_database, tmp_path: Path, monkeypatch
) -> None:
    """正常8/故障/越境と全DBをまとめた受入検証。"""
    _screen_runner_batted_hits(
        vertical_database, tmp_path, monkeypatch, fault_only=False
    )


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS PATH未供給のため故障画面は未実証",
)
def test_screen_runner_batted_fault(
    vertical_database, tmp_path: Path, monkeypatch
) -> None:
    """真正先行1球からT4故障だけを実行し、全T5版の不変を比較する。"""
    _screen_runner_batted_hits(
        vertical_database, tmp_path, monkeypatch, fault_only=True
    )


def _screen_runner_batted_hits(vertical_database, tmp_path, monkeypatch, *, fault_only):
    """走者状態は画面の先行単打だけで作り、DBへ事前投入しない。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file()
    _install_runner_fault_server(monkeypatch)
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
            checkpoint = tmp_path / "fault-before.json"
            stop = threading.Event()
            with ThreadPoolExecutor(max_workers=1) as workers:
                captured = workers.submit(
                    _capture_runner_fault_baseline, db, checkpoint, stop
                )
                try:
                    completed = _run_runner_playwright(
                        db,
                        origin,
                        {
                            "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                            "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                            "PITCHLOG_E2E_OTHER_TEAM": db.other_team_name,
                            "PITCHLOG_E2E_RESULT_FILE": str(
                                tmp_path / "result-game.txt"
                            ),
                            "PITCHLOG_E2E_RUNNER_FAULT_CHECKPOINT": str(checkpoint),
                            "PITCHLOG_E2E_RUNNER_SCOPE": "fault"
                            if fault_only
                            else "all",
                        },
                    )
                finally:
                    stop.set()
                baseline = captured.result()
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
            expected = set() if fault_only else set(_RESULTS)
            assert len(observed) == len(expected)
            assert {r["scenario"] for r in observed} == expected
            created_games = {r["game"] for r in observed}
            assert len(created_games) == len(expected)
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
                        expected_count = _COUNTS[result["scenario"]]
                        assert count == (expected_count,), table
                    _verify_saved_rows(admin, db.tenant_id, game, result["scenario"])
                fault_results = [
                    json.loads(value)
                    for value in re.findall(
                        r"PITCHLOG_RUNNER_FAULT_RESULT=(\{[^\n]+\})", completed.stdout
                    )
                ]
                assert len(fault_results) == 1
                assert fault_results[0]["game"] not in created_games
                assert fault_results[0]["game"] != str(db.game_id)
                assert (
                    "PITCHLOG_RUNNER_T4_REACHED"
                    in (_LOGS / "runners-batted-hits-app.log").read_text()
                )
                _verify_runner_fault_rollback(
                    admin, db.tenant_id, fault_results[0], baseline
                )
