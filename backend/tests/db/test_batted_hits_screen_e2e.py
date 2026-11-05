"""新規4試合の安打→次球→再送→再読込を実画面とowned PGで照合する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import apply_product_authz_ddl
from pitchlog.repositories.ordinary_prefix_read import (
    _evaluate_lineup_payload,
    _public_play,
)
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

ROOT = Path(__file__).resolve().parents[3]
_GOLDEN = ROOT / "contracts/state-transition/batted_hit_cases_v1.json"
_RESULTS = {
    "batting-result.single": "BH-Single-top-O1",
    "batting-result.double": "BH-Double-top-O1",
    "batting-result.triple": "BH-Triple-top-O1",
    "batting-result.home-run": "BH-HomeRun-top-O1",
}


def _verify_saved_rows(admin, tenant, game, result) -> None:
    """実原本を唯一reader/projectorへ通し、親41列とrunner全列を照合する。

    数学の正解は別途goldenの固定帰結で検査する。この照合は保存境界の検査。
    """
    records = admin.execute(
        "SELECT to_jsonb(p), e.payload FROM public.play_rows AS p "
        "JOIN public.operation_events AS e "
        "ON e.tenant_id=p.tenant_id AND e.id=p.source_event_id "
        "WHERE p.tenant_id=%s AND p.game_id=%s "
        "ORDER BY p.play_number LIMIT 3",
        (tenant, game),
    ).fetchall()
    assert len(records) == 2
    golden = next(
        c
        for c in json.loads(_GOLDEN.read_text())["cases"]
        if c["caseId"] == _RESULTS[result["resultId"]]
    )
    assert golden["expected"]["ok"] is True
    ball_golden = next(
        c
        for c in json.loads(
            (ROOT / "contracts/state-transition/play_prefix_v2_cases.json").read_text()
        )["cases"]
        if c["caseId"] == "V2-FOLLOW-ORDINARY-PITCH-25"
    )["expected"]["value"]["t1"]
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
        assert result["rows"][index]["play_row"] == _public_play(
            actual, payload.observations.course.model_dump(mode="json", by_alias=True)
        )
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
        assert result["rows"][index]["play_runners"] == expected_runners
        if index == 0:
            assert runners == []  # 第1球のbeforeは無走者。
            assert (
                response.t1.stat_flags.model_dump(mode="json", by_alias=True)
                == (golden["expected"]["value"]["statFlags"])
            )
            assert (
                response.t1.batter_destination.model_dump(mode="json", by_alias=True)
                == golden["expected"]["value"]["batterDestination"]
            )
        else:
            assert actual["batting_result_key"] == "batting-result.ball"
            assert request.t1.before.state_fields.balls == "0"
            assert (
                response.t1.count_effect.model_dump(mode="json", by_alias=True)
                == ball_golden["countEffect"]
            )
            assert (
                response.t1.stat_flags.model_dump(mode="json", by_alias=True)
                == ball_golden["statFlags"]
            )


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS証明書/鍵PATH未供給のため安打4種の画面縦断は未実証",
)
def test_screen_four_new_games_hits_next_ball_replay_and_reload(
    vertical_database,
) -> None:
    """対象試合/記録は画面だけで生成し、四つの新規試合を実保存へ照合する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        # fixtureが初回適用した同じowned DBへ正式producerを再適用する。
        # IDLE接続を渡し、新stable語彙関数も旧fullprofileと同じ検査を受ける。
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
        # 既owned fixtureの参照選手/球種を使い、語彙だけを準備する。
        for key in _RESULTS:
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
            db, "GameScreenBattedHits.playwright.config.ts", "batted-hits", https=True
        ) as origin:
            completed = _run_playwright(
                db,
                "GameScreenBattedHits.playwright.config.ts",
                origin,
                "batted-hits",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert completed.returncode == 0, (
                completed.stdout[-10000:],
                completed.stderr[-3000:],
            )
            observed = [
                json.loads(value)
                for value in re.findall(
                    r"PITCHLOG_BATTED_SCREEN_RESULT=(\{[^\n]+\})", completed.stdout
                )
            ]
            assert len(observed) == 4
            assert {r["resultId"] for r in observed} == set(_RESULTS)
            created_games = {r["game"] for r in observed}
            assert len(created_games) == 4
            assert str(db.game_id) not in created_games
            with psycopg.connect(db.authority.database.business_admin) as admin:
                for result in observed:
                    game = result["game"]
                    assert result["goldenCase"] == _RESULTS[result["resultId"]]
                    for table in ("play_rows", "operation_events", "event_slots"):
                        count = admin.execute(
                            sql.SQL(
                                "SELECT count(*) FROM public.{} "
                                "WHERE tenant_id=%s AND game_id=%s"
                            ).format(sql.Identifier(table)),
                            (db.tenant_id, game),
                        ).fetchone()
                        assert count == (2,), table
                    ledger = admin.execute(
                        "SELECT count(*) FROM public.idempotency_ledger AS l "
                        "JOIN public.operation_events AS e "
                        "ON l.tenant_id=e.tenant_id AND l.d5=e.d5 "
                        "WHERE e.tenant_id=%s AND e.game_id=%s",
                        (db.tenant_id, game),
                    ).fetchone()
                    assert ledger == (2,)
                    _verify_saved_rows(admin, db.tenant_id, game, result)
