"""妨害 INT01〜07 の真正UI保存と物理原本・現行T5を同じ受理eventへ照合する。"""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.db.current_product_startup import CURRENT_REVISION
from pitchlog.repositories.first_ball_operations import PLAY_ROW_COLUMNS
from pitchlog.stats.facts import evaluate_native_projection

from . import test_screen_start_e2e as screen_harness
from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db

_READ_SQL: dict[str, LiteralString] = {
    "revision": "SELECT version_num FROM alembic_version",
    "teams": (
        "SELECT g.away_team_record_id,g.home_team_record_id,(SELECT tr.id "
        "FROM public.team_records tr WHERE tr.tenant_id=g.tenant_id AND "
        "tr.kind='self' AND tr.hidden_at IS NULL) FROM public.games g "
        "WHERE g.tenant_id=%s AND g.id=%s"
    ),
    "events": (
        "SELECT event_kind,ledger_kind,d5 FROM public.operation_events "
        "WHERE tenant_id=%s AND game_id=%s ORDER BY d1,d2,id"
    ),
    "physical": (
        "SELECT to_jsonb(p),e.payload FROM public.play_rows p JOIN "
        "public.operation_events e ON e.tenant_id=p.tenant_id AND "
        "e.game_id=p.game_id AND e.id=p.source_event_id WHERE p.tenant_id=%s "
        "AND p.game_id=%s AND p.hidden_at IS NULL ORDER BY p.play_number,p.id"
    ),
    "runners": (
        "SELECT to_jsonb(r) FROM public.play_runners r JOIN public.play_rows p "
        "ON p.tenant_id=r.tenant_id AND p.id=r.play_id WHERE p.tenant_id=%s "
        "AND p.game_id=%s AND p.hidden_at IS NULL ORDER BY p.play_number,r.base"
    ),
    "active_version": (
        "SELECT v.id,v.source_count,v.is_current FROM "
        "sync_fence.game_lifecycle_heads h JOIN sync_fence.stats_fact_versions v "
        "ON v.tenant_id=h.tenant_id AND v.game_id=h.game_id AND "
        "v.id=h.active_stats_version_id WHERE h.tenant_id=%s AND h.game_id=%s"
    ),
    "sources": (
        "SELECT source_event_id,metric_states,computed_metric_keys FROM "
        "sync_fence.stats_primitive_sources WHERE tenant_id=%s AND "
        "game_id=%s AND fact_version_id=%s ORDER BY d1,d2,source_event_id"
    ),
    "facts": (
        "SELECT source_event_id,metric_id,player_id,credit_ordinal,state,amount "
        "FROM sync_fence.stats_primitive_facts WHERE tenant_id=%s AND "
        "game_id=%s AND fact_version_id=%s"
    ),
}


@pytest.fixture
def tls_paths() -> None:
    """DB生成より前に既隔離HTTPS資材の存在だけを確認する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        raw = os.environ.get(name)
        assert raw is not None and Path(raw).is_absolute() and Path(raw).is_file()


@contextmanager
def _owned_logs(evidence: Path):
    """既共通ログを上書きせず、この実証の出力を隔離する。"""
    previous = screen_harness._LOGS
    target = evidence / "logs"
    target.mkdir(mode=0o700)
    screen_harness._LOGS = target
    try:
        yield
    finally:
        screen_harness._LOGS = previous


def _explain_all(admin, tenant: UUID, game: UUID) -> None:
    """UI実行前に固定readの列・結合・型を全て実catalogへ照合する。"""
    for statement in _READ_SQL.values():
        parameters = (
            (tenant, game, UUID(int=0))
            if statement.count("%s") == 3
            else (tenant, game)
        )
        if statement.count("%s") == 0:
            parameters = ()
        assert admin.execute(
            "EXPLAIN (FORMAT JSON) " + statement, parameters
        ).fetchone()


def _assert_saved_game(
    admin, tenant: UUID, game: UUID, branches: list[str], plays: int
) -> None:
    """実受理原本を唯一mapper・唯一生成T5で再評価し、DB全値と比較する。"""
    from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
    from pitchlog.sync.terminal_pitch_payload import (
        LineupPitchCalculation,
        read_lineup_pitch_payload,
    )
    from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

    events = admin.execute(_READ_SQL["events"], (tenant, game)).fetchall()
    assert len(events) == plays
    assert [(row[0], row[1]) for row in events] == [("play_input", "accepted")] * plays
    assert len({row[2] for row in events}) == plays
    rows = admin.execute(_READ_SQL["physical"], (tenant, game)).fetchall()
    assert len(rows) == plays
    expected_runners: list[dict] = []
    evaluations: list[tuple[UUID, dict]] = []
    for number, (actual, raw) in enumerate(rows, start=1):
        assert set(actual) == set(PLAY_ROW_COLUMNS) and len(actual) == 41
        calc = LineupPitchCalculation.model_validate_json(
            json.dumps(raw["calculation"])
        )
        payload = read_lineup_pitch_payload(
            json.dumps(raw),
            calc.response.value.new_history_entry.difference.model_dump_json(
                by_alias=True, exclude_unset=True
            ),
            expected_calculation=calc,
            require_current_rbi=True,
        )
        row_id, event_id = UUID(actual["id"]), UUID(actual["source_event_id"])
        assert row_id == UUID(calc.request.play_identity.play_id)
        assert event_id == UUID(calc.request.play_identity.event_id)
        expected = pitch_physical_row(
            payload.observations,
            payload.participants,
            calc.request.t1.result_id,
            tenant_id=tenant,
            game_id=game,
            source_event_id=event_id,
            row_id=row_id,
            play_number=number,
        )
        assert actual == expected
        expected_runners.extend(
            runner_physical_rows(
                calc.request.source.runners,
                t1=calc.response.value.t1,
                t1_input=calc.request.t1,
                tenant_id=tenant,
                play_id=row_id,
            )
        )
        ruling = raw["observations"]["interferenceRuling"]
        if branches[number - 1] in {"ordinary-single", "ordinary-triple"}:
            assert ruling == {"kind": "not-required"}
        else:
            assert type(ruling) is dict and ruling["kind"] in (
                "batting-interference",
                "obstruction",
                "offensive-interference",
            )
            assert raw["calculation"]["request"]["t1"]["interferenceRuling"] == ruling
        evaluation = evaluate_native_projection(raw, source_event_id=event_id)
        if branches[number - 1] == "INT-02-steal-home":
            assert evaluation["metrics"]["stolen_bases"]["state"] == "unavailable"
            assert evaluation["metrics"]["stolen_bases"]["credits"] == []
        evaluations.append((event_id, evaluation))
    actual_runners = [
        row[0] for row in admin.execute(_READ_SQL["runners"], (tenant, game)).fetchall()
    ]
    assert actual_runners == expected_runners
    version = admin.execute(_READ_SQL["active_version"], (tenant, game)).fetchall()
    assert len(version) == 1 and version[0][1:] == (plays, True)
    fact_id = version[0][0]
    sources = admin.execute(_READ_SQL["sources"], (tenant, game, fact_id)).fetchall()
    assert len(sources) == plays
    assert [(row[0], row[1]) for row in sources] == evaluations
    for _, states, computed in sources:
        assert set(states["metrics"]) == set(evaluations[0][1]["metrics"])
        assert set(computed) <= set(states["metrics"])
        assert all(states["metrics"][key]["state"] == "available" for key in computed)
        # unavailableを空の成功creditへ置換しない。
        assert all(
            not states["metrics"][key]["credits"]
            for key in set(states["metrics"]) - set(computed)
        )
    actual_facts = set(
        admin.execute(_READ_SQL["facts"], (tenant, game, fact_id)).fetchall()
    )
    expected_facts = {
        (
            event_id,
            metric,
            UUID(credit["player_id"]),
            ordinal,
            "available",
            Decimal(str(credit["quantity"])),
        )
        for event_id, states in evaluations
        for metric, item in states["metrics"].items()
        for ordinal, credit in enumerate(item["credits"])
    }
    assert actual_facts == expected_facts


def test_interference_screen_actual(tls_paths, vertical_database):
    """実UI五試合のINT01〜07を同一実DB原本へ照合する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _explain_all(admin, db.tenant_id, db.game_id)
        assert admin.execute(_READ_SQL["revision"]).fetchone() == (CURRENT_REVISION,)
        teams = admin.execute(_READ_SQL["teams"], (db.tenant_id, db.game_id)).fetchone()
        for key, category in (
            ("batting-result.single", "batting_result"),
            ("batting-result.triple", "batting_result"),
            ("batting-result.batted-out", "batting_result"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
    assert teams is not None and all(value is not None for value in teams)
    cache = Path.home() / ".cache/pitchlog/interference-screen-author-20261108"
    cache.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="interference-", dir=cache))
    evidence.chmod(0o700)
    token = uuid4()
    config = "GameScreenInterferenceActual.playwright.config.ts"
    with _owned_logs(evidence), db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, config, "interference-actual", https=True
        ) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "interference-actual",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_SELF_TEAM": str(teams[2]),
                },
                timeout_seconds=1800,
            )
    (evidence / "playwright.log").write_text(result.stdout + "\n" + result.stderr)
    matched = re.findall(r"PITCHLOG_INTERFERENCE_SCREEN=(\[[^\n]+\])", result.stdout)
    assert len(matched) == 1, (result.stdout[-12000:], result.stderr[-2000:])
    observed = json.loads(matched[0])
    assert [item["branches"] for item in observed] == [
        ["INT-02"],
        ["INT-01", "INT-03"],
        ["ordinary-triple", "INT-02-steal-home"],
        ["INT-04", "INT-05"],
        ["INT-06", "ordinary-single", "INT-07"],
    ]
    assert len({item["gameId"] for item in observed}) == 5
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        admin.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        for item in observed:
            game = UUID(item["gameId"])
            assert game != db.game_id
            _assert_saved_game(
                admin, db.tenant_id, game, item["branches"], item["plays"]
            )
    (evidence / "db-result.json").write_text(
        json.dumps(
            {
                "games": len(observed),
                "branches": [item["branches"] for item in observed],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    assert result.returncode == 0, (result.stdout[-12000:], result.stderr[-2000:])
