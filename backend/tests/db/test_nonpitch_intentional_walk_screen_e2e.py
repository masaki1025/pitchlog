"""申告敬遠を実画面から保存し、非投球原本・次球・再取得まで照合する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import apply_product_authz_ddl
from pitchlog.repositories.ordinary_prefix_read import _evaluate_lineup_payload
from pitchlog.repositories.recorded_snapshot_operations import RECORDED_PLAY_ROW_COLUMNS
from pitchlog.sync.nonpitch_execution import intentional_walk_physical_row

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS証明書/鍵PATH未供給のため申告敬遠画面縦断は未実証",
)
def test_nonpitch_intentional_walk_screen(vertical_database) -> None:
    """画面で一三塁を作り、同期本文と保存41列を真正計算へ照合する。"""
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
        catalog = inspect_product_authz_catalog(
            admin, privileged_role_oids=frozenset({identity[0]})
        )
        assert catalog.ok, [value.check_id for value in catalog.violations]
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        for key in (
            "batting-result.single",
            "batting-result.intentional-walk",
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
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            "GameScreenNonpitchIntentionalWalk.playwright.config.ts",
            "nonpitch-intentional-walk",
            https=True,
        ) as origin:
            run = _run_playwright(
                db,
                "GameScreenNonpitchIntentionalWalk.playwright.config.ts",
                origin,
                "nonpitch-intentional-walk",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_OTHER_TEAM": db.other_team_name,
                },
            )
            assert run.returncode == 0, (run.stdout[-10000:], run.stderr[-3000:])
            matches = re.findall(
                r"PITCHLOG_NONPITCH_SCREEN_RESULT=(\{[^\n]+\})", run.stdout
            )
            assert len(matches) == 1
            observed = json.loads(matches[0])
            game = observed["game"]
            assert game != str(db.game_id)
            with psycopg.connect(db.authority.database.business_admin) as admin:
                rows = admin.execute(
                    "SELECT to_jsonb(p),e.payload FROM public.play_rows AS p "
                    "JOIN public.operation_events AS e "
                    "ON e.tenant_id=p.tenant_id AND e.id=p.source_event_id "
                    "WHERE p.tenant_id=%s AND p.game_id=%s ORDER BY p.play_number",
                    (db.tenant_id, game),
                ).fetchall()
                assert len(rows) == 4
                assert [row[0]["event_kind"] for row in rows] == [
                    "pitch",
                    "pitch",
                    "non_pitch",
                    "pitch",
                ]
                actual, raw = rows[2]
                payload = _evaluate_lineup_payload(raw)
                assert payload.observations.kind == "intentional-walk"
                assert (
                    payload.calculation.request.t1.pitch_event_kind == "non-pitch-event"
                )
                response = payload.calculation.response.value
                assert response.t1.after.state_fields.runners == "first-second-third"
                assert response.t1.after.state_fields.balls == "0"
                assert response.t1.after.state_fields.strikes == "0"
                assert response.t1.stat_flags.walk is True
                assert response.t1.stat_flags.rbi is False
                expected = intentional_walk_physical_row(
                    payload.observations,
                    payload.participants,
                    payload.calculation.request.t1.result_id,
                    tenant_id=db.tenant_id,
                    game_id=UUID(game),
                    source_event_id=UUID(actual["source_event_id"]),
                    row_id=UUID(actual["id"]),
                    play_number=3,
                )
                assert set(actual) == set(RECORDED_PLAY_ROW_COLUMNS)
                assert actual == expected
                assert actual["pitch_type_key"] is None
                assert actual["course_x"] is None
                assert actual["course_y"] is None
                published = observed["rows"][2]["play_row"]
                internal = {
                    "tenant_id",
                    "hidden_at",
                    "import_batch_id",
                    "legacy_row_identifier",
                    "migration_unverified",
                    "course_x",
                    "course_y",
                }
                assert set(published) == (set(actual) - internal) | {"course"}
                assert published["course"] is None
                for key in set(actual) - internal:
                    assert published[key] == actual[key]
                native_source = admin.execute(
                    "SELECT metric_states FROM sync_fence.stats_primitive_sources "
                    "WHERE tenant_id=%s AND game_id=%s AND source_event_id=%s",
                    (db.tenant_id, game, actual["source_event_id"]),
                ).fetchall()
                assert len(native_source) == 1
                evaluation = native_source[0][0]
                assert evaluation["selected"] is True
                assert evaluation["source_event_id"] == actual["source_event_id"]
                metrics = evaluation["metrics"]
                assert len(metrics) == 27
                assert metrics["pitch_count"] == {
                    "credits": [],
                    "display": "0",
                    "reason": None,
                    "state": "available",
                    "value": "0",
                }
                for metric_id in ("pa", "bb", "pitcher_bb", "batters_faced"):
                    assert metrics[metric_id]["state"] == "available"
                    assert metrics[metric_id]["value"] == "1"
                    assert len(metrics[metric_id]["credits"]) == 1
                    assert metrics[metric_id]["credits"][0]["quantity"] == "1"
                for metric_id in ("runs", "rbi"):
                    assert metrics[metric_id]["state"] == "source_unavailable"
                    assert metrics[metric_id]["value"] is None
                facts = admin.execute(
                    "SELECT f.metric_id,f.player_id,f.credit_ordinal,f.state,"
                    "f.amount FROM sync_fence.stats_primitive_facts AS f "
                    "JOIN sync_fence.stats_fact_versions AS v "
                    "ON (v.tenant_id,v.game_id,v.id)="
                    "(f.tenant_id,f.game_id,f.fact_version_id) "
                    "WHERE f.tenant_id=%s AND f.game_id=%s "
                    "AND f.source_event_id=%s AND v.is_current "
                    "ORDER BY f.metric_id,f.player_id,f.credit_ordinal",
                    (db.tenant_id, game, actual["source_event_id"]),
                ).fetchall()
                expected_credit = {
                    "pa": str(payload.participants.batter_id),
                    "bb": str(payload.participants.batter_id),
                    "pitcher_bb": str(payload.participants.pitcher_id),
                    "batters_faced": str(payload.participants.pitcher_id),
                }
                assert len(facts) == 4
                assert {
                    metric: (str(player), ordinal, state, str(amount))
                    for metric, player, ordinal, state, amount in facts
                } == {
                    metric: (player, 0, "available", "1")
                    for metric, player in expected_credit.items()
                }
                assert observed["after"]["stateFields"]["state.count.balls"] == "1"
                print(
                    "PITCHLOG_NONPITCH_OWNED_RESULT="
                    + json.dumps(
                        {
                            "game": game,
                            "sourceEvent": actual["source_event_id"],
                            "playRows": len(rows),
                            "nativeMetricCount": len(metrics),
                            "nativeFactCount": len(facts),
                            "reloadedPrefixLength": len(observed["rows"]),
                        },
                        sort_keys=True,
                    )
                )
