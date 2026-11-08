"""九回55プレイの画面完走と同終了版の成績/CSVを保存原本へ照合する。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.stats.basic_stats import BATTING_ITEMS, PITCHING_ITEMS
from pitchlog.stats.generated.receiver import METRIC_IDS

from . import test_screen_start_e2e as screen_harness
from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db

# 直接表示countと既率の依存原始値だけを要求する。原始27と表示27を混同しない。
_DISPLAY_PRIMITIVE_KEYS = frozenset(
    metric
    for metric, _, kind in (*BATTING_ITEMS, *PITCHING_ITEMS)
    if kind in {"count", "batters_faced"}
) | {"pitching_outs", "sf", "total_bases"}
assert _DISPLAY_PRIMITIVE_KEYS <= set(METRIC_IDS)
_KNOWN_TOTALS = {
    "pitch_count": 55,
    "pa": 55,
    "ab": 55,
    "h": 1,
    "hr": 1,
    "runs": 1,
    "rbi": 1,
    "pitching_outs": 54,
    "batters_faced": 55,
    "k": 0,
    "bb": 0,
    "hbp": 0,
    "stolen_bases": 0,
}


_READ_SQL: dict[str, LiteralString] = {
    "read_0": ("SELECT version_num FROM alembic_version"),
    "read_1": (
        "SELECT g.away_team_record_id,g.home_team_record_id,(SELECT tr.id"
        " FROM public.team_records tr WHERE tr.tenant_id=g.tenant_id AND "
        "tr.kind='self' AND tr.hidden_at IS NULL) FROM public.games g "
        "WHERE g.tenant_id=%s AND g.id=%s"
    ),
    "read_2": (
        "SELECT "
        "g.status,h.last_version,h.is_finished,v.id,v.completion_state,v.is_current,v.source_count,h.active_receipt_id,v.completion_receipt_id,v.public_pointer_receipt_id"
        " FROM public.games g JOIN sync_fence.game_lifecycle_heads h ON "
        "h.tenant_id=g.tenant_id AND h.game_id=g.id JOIN "
        "sync_fence.stats_fact_versions v ON v.tenant_id=h.tenant_id AND "
        "v.game_id=h.game_id AND v.id=h.active_stats_version_id WHERE "
        "g.tenant_id=%s AND g.id=%s"
    ),
    "read_3": (
        "SELECT event_kind,ledger_kind FROM public.operation_events WHERE"
        " tenant_id=%s AND game_id=%s ORDER BY d1"
    ),
    "read_4": (
        "SELECT "
        "p.id,p.source_event_id,p.batting_result_key,s.plays_csv_json "
        "FROM public.play_rows p JOIN public.play_export_snapshots s ON "
        "s.tenant_id=p.tenant_id AND s.play_row_id=p.id AND "
        "s.game_id=p.game_id WHERE p.tenant_id=%s AND p.game_id=%s AND "
        "p.hidden_at IS NULL AND p.import_batch_id IS NULL ORDER BY "
        "p.play_number,p.id"
    ),
    "read_5": (
        "SELECT source_event_id,metric_states,computed_metric_keys FROM "
        "sync_fence.stats_primitive_sources WHERE tenant_id=%s AND "
        "game_id=%s AND fact_version_id=%s ORDER BY d1"
    ),
    "read_6": (
        "SELECT "
        "source_event_id,metric_id,player_id,credit_ordinal,state,amount "
        "FROM sync_fence.stats_primitive_facts WHERE tenant_id=%s AND "
        "game_id=%s AND fact_version_id=%s"
    ),
    "read_7": (
        "SELECT p.player,m.metric,COALESCE(sum(f.amount),0) FROM "
        "unnest(%s::uuid[]) p(player) CROSS JOIN unnest(%s::text[]) "
        "m(metric) LEFT JOIN sync_fence.stats_primitive_facts f ON "
        "f.player_id=p.player AND f.metric_id=m.metric AND f.tenant_id=%s"
        " AND f.game_id=%s AND f.fact_version_id=%s GROUP BY "
        "p.player,m.metric"
    ),
    "read_8": (
        "SELECT m.metric,COALESCE(sum(f.amount),0) FROM "
        "unnest(%s::text[]) m(metric) LEFT JOIN "
        "sync_fence.stats_primitive_facts f ON f.metric_id=m.metric AND "
        "f.tenant_id=%s AND f.game_id=%s AND f.fact_version_id=%s GROUP "
        "BY m.metric"
    ),
    "read_9": (
        "SELECT DISTINCT pitcher_id FROM public.play_rows WHERE "
        "tenant_id=%s AND game_id=%s AND hidden_at IS NULL AND "
        "import_batch_id IS NULL"
    ),
}


def _explain_read_sql(admin, tenant: UUID, game: UUID) -> None:
    """UIの長時間記録より前に、全固定SELECTの列/型/結合を実PGで計画する。"""
    for statement in _READ_SQL.values():
        count = statement.count("%s")
        if count == 0:
            parameters = ()
        elif count == 2:
            parameters = (tenant, game)
        elif count == 3:
            parameters = (tenant, game, UUID(int=0))
        elif count == 4:
            parameters = (list(_KNOWN_TOTALS), tenant, game, UUID(int=0))
        elif count == 5:
            parameters = (
                [UUID(int=0)],
                sorted(_DISPLAY_PRIMITIVE_KEYS),
                tenant,
                game,
                UUID(int=0),
            )
        else:
            raise AssertionError("未登録の固定read parameter形")
        assert admin.execute(
            "EXPLAIN (FORMAT JSON) " + statement, parameters
        ).fetchone()


@contextmanager
def _owned_logs(evidence: Path):
    """共有/tmpのログを上書きせず、自分の試験出力だけへ分離する。"""
    previous = screen_harness._LOGS
    target = evidence / "logs"
    target.mkdir(mode=0o700)
    screen_harness._LOGS = target
    try:
        yield
    finally:
        screen_harness._LOGS = previous


def _csv_rows(raw: bytes) -> list[dict[str, str]]:
    """BOMと閉ヘッダを保つ実CSVだけを読む。"""
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    assert rows.fieldnames is not None
    assert len(rows.fieldnames) == len(set(rows.fieldnames))
    result = list(rows)
    assert all(None not in row for row in result)
    return result


def _assert_stats_csv(path: Path, players: list[dict]) -> None:
    """CSVの各表示セルを同じ実APIの27項目へ全値照合する。"""
    rows = _csv_rows(path.read_bytes())
    assert len(rows) == len(players)
    by_id = {row["player_id"]: row for row in rows}
    assert len(by_id) == len(rows)
    assert set(by_id) == {p["player_id"] for p in players}
    for player in players:
        expected = {
            key: player[key]
            for key in ("player_id", "player_name", "uniform_number", "team_name")
        }
        expected["is_pitcher"] = "1" if player["is_pitcher"] else "0"
        unavailable = []
        for section in ("batting", "pitching"):
            for item in player[section]:
                expected[section + "_" + item["metric_id"]] = (
                    item["display"] if item["state"] == "available" else ""
                )
                if item["state"] != "available":
                    unavailable.append(item["metric_id"])
        expected["pending"] = ";".join(player["pending"])
        expected["source_unavailable_metrics"] = ";".join(unavailable)
        assert by_id[player["player_id"]] == expected


def _saved_cell(value):
    """既保存された完成セルを比較用文字列へ写す。計算や補完はしない。"""
    if value is None:
        return ""
    if type(value) is bool:
        return "true" if value else "false"
    assert type(value) in (str, int)
    return str(value)


def _assert_archive(path: Path, game: UUID, saved: list[tuple]) -> None:
    """ZIP全memberのhash/件数と88列を、記録時snapshotの全列へ照合する。"""
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {*CSV_HEADERS, "manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["game_id"] == str(game)
        assert manifest["timezone"] == "Asia/Tokyo"
        assert {row["name"] for row in manifest["files"]} == set(CSV_HEADERS)
        for row in manifest["files"]:
            raw = archive.read(row["name"])
            assert len(raw) == row["byte_length"]
            assert hashlib.sha256(raw).hexdigest() == row["sha256"]
            assert len(_csv_rows(raw)) == row["data_row_count"]
        rows = _csv_rows(archive.read("plays.csv"))
        assert len(rows) == len(saved) == 55
        assert list(rows[0]) == list(CSV_HEADERS["plays.csv"])
        for row, (_, _, _, original) in zip(rows, saved, strict=True):
            assert set(original) == set(CSV_HEADERS["plays.csv"])
            assert row == {key: _saved_cell(value) for key, value in original.items()}
        links = _csv_rows(archive.read("play_links.csv"))
        assert [r["play_row_id"] for r in links] == [str(r[0]) for r in saved]
        assert [r["source_event_id"] for r in links] == [str(r[1]) for r in saved]


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離HTTPS証明書PATH未供給。55プレイ画面通しは未実証",
)
def test_screen_nine_innings_batted_out_stats_and_csv(vertical_database):
    """新規UI試合の55原本/終了版と実API/CSVを読取専用で照合する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _explain_read_sql(admin, db.tenant_id, db.game_id)
        assert admin.execute(_READ_SQL["read_0"]).fetchone() == (
            "0049_pitcher_entry_sources",
        )
        teams = admin.execute(
            _READ_SQL["read_1"],
            (db.tenant_id, db.game_id),
        ).fetchone()
        for key, category in (
            ("batting-result.home-run", "batting_result"),
            ("batting-result.batted-out", "batting_result"),
            ("batted.screen.line", "batted_ball"),
            ("batted.screen.hard", "batted_ball"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key),
            )
    assert teams is not None and teams[2] is not None
    cache = Path.home() / ".cache/pitchlog/full-game-batted-out-author-20261108"
    cache.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="full-game-batted-", dir=cache))
    evidence.chmod(0o700)
    token = uuid4()
    config = "GameScreenFullGameBattedOut.playwright.config.ts"
    with _owned_logs(evidence), db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, config, "full-game-batted-out", https=True
        ) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "full-game-batted-out",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_SELF_TEAM": str(teams[2]),
                    "PITCHLOG_FULLGAME_EVIDENCE_DIR": str(evidence),
                },
                timeout_seconds=3600,
            )
    (evidence / "playwright.log").write_text(result.stdout + "\n" + result.stderr)
    matched = re.findall(r"PITCHLOG_FULL_GAME_BATTED_FINAL=(\{[^\n]+\})", result.stdout)
    assert len(matched) == 1, (result.stdout[-12000:], result.stderr[-2000:])
    observed = json.loads(matched[0])
    game = UUID(observed["gameId"])
    assert game != db.game_id and observed["plays"] == 55
    players = json.loads((evidence / "game-stats.json").read_text())["players"]
    season = json.loads((evidence / "season-stats.json").read_text())["players"]
    self_players = [p for p in players if p["team_record_id"] == str(teams[2])]
    assert self_players
    assert sorted(self_players, key=lambda p: p["player_id"]) == sorted(
        season, key=lambda p: p["player_id"]
    )
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        admin.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        final = admin.execute(
            _READ_SQL["read_2"],
            (db.tenant_id, game),
        ).fetchall()
        assert len(final) == 1
        (
            status,
            version,
            finished,
            fact_id,
            completion,
            current,
            count,
            receipt,
            saved_receipt,
            pointer,
        ) = final[0]
        assert (status, version, finished, completion, current, count) == (
            "finished",
            1,
            True,
            "confirmed_ended",
            True,
            55,
        )
        assert receipt is not None and receipt == saved_receipt == pointer
        public_head = json.loads((evidence / "final-head.json").read_text())
        assert public_head["lifecycle"]["activeStatsVersionId"] == str(fact_id)
        assert public_head["lifecycle"]["active"]["receiptId"] == str(receipt)
        assert public_head["lifecycle"]["active"]["version"] == "1"
        assert public_head["checkpoint"]["content"]["d3"] == "56"
        events = admin.execute(
            _READ_SQL["read_3"],
            (db.tenant_id, game),
        ).fetchall()
        assert events == [("play_input", "accepted")] * 55 + [
            ("game_end_declaration", "accepted")
        ]
        saved = admin.execute(
            _READ_SQL["read_4"],
            (db.tenant_id, game),
        ).fetchall()
        assert [r[2] for r in saved] == ["batting-result.home-run"] + [
            "batting-result.batted-out"
        ] * 54
        sources = admin.execute(
            _READ_SQL["read_5"],
            (db.tenant_id, game, fact_id),
        ).fetchall()
        assert [r[0] for r in sources] == [r[1] for r in saved]
        # 明示availableなsourceと全creditが揃った場合だけ、空creditを0と比較する。
        for _, states, computed in sources:
            assert set(states["metrics"]) == set(METRIC_IDS)
            assert _DISPLAY_PRIMITIVE_KEYS <= set(computed) <= set(METRIC_IDS)
            assert all(
                states["metrics"][key]["state"] == "available"
                for key in _DISPLAY_PRIMITIVE_KEYS
            )
        actual_credits = admin.execute(
            _READ_SQL["read_6"],
            (db.tenant_id, game, fact_id),
        ).fetchall()
        expected_credits = {
            (
                event,
                metric,
                UUID(credit["player_id"]),
                ordinal,
                "available",
                Decimal(str(credit["quantity"])),
            )
            for event, states, _ in sources
            for metric, item in states["metrics"].items()
            for ordinal, credit in enumerate(item["credits"])
        }
        assert set(actual_credits) == expected_credits
        facts = admin.execute(
            _READ_SQL["read_7"],
            (
                [UUID(p["player_id"]) for p in players],
                sorted(_DISPLAY_PRIMITIVE_KEYS),
                db.tenant_id,
                game,
                fact_id,
            ),
        ).fetchall()
        totals = dict(
            admin.execute(
                _READ_SQL["read_8"],
                (list(_KNOWN_TOTALS), db.tenant_id, game, fact_id),
            ).fetchall()
        )
        assert totals == _KNOWN_TOTALS
        pitchers = {
            r[0]
            for r in admin.execute(
                _READ_SQL["read_9"],
                (db.tenant_id, game),
            ).fetchall()
        }
    assert len(pitchers) == 2
    by_player_metric = {
        (str(player), metric): amount for player, metric, amount in facts
    }
    for player in players:
        assert len(player["batting"]) == 16 and len(player["pitching"]) == 11
        assert player["pending"] == []
        for section, declarations in (
            ("batting", BATTING_ITEMS),
            ("pitching", PITCHING_ITEMS),
        ):
            for item, (metric, _, kind) in zip(
                player[section], declarations, strict=True
            ):
                assert item["metric_id"] == metric and item["state"] == "available"
                if kind == "appearance":
                    assert item["value"] == int(UUID(player["player_id"]) in pitchers)
                elif kind == "innings":
                    amount = by_player_metric[(player["player_id"], "pitching_outs")]
                    assert item["value"] == {
                        "numerator": str(amount),
                        "denominator": "3",
                    }
                elif kind in ("count", "batters_faced"):
                    amount = by_player_metric[(player["player_id"], metric)]
                    assert item["value"] == amount
    _assert_stats_csv(evidence / "game-stats.csv", players)
    _assert_stats_csv(evidence / "season-stats.csv", season)
    _assert_archive(evidence / "plays.zip", game, saved)
    (evidence / "db-result.json").write_text(
        json.dumps(
            {
                "game_id": str(game),
                "version": version,
                "receipt": str(receipt),
                "fact_version": str(fact_id),
                "source_count": len(sources),
                "accepted_events": len(events),
                "snapshot_rows": len(saved),
                "stats_players": len(players),
                "performance": observed["performance"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    assert result.returncode == 0, (result.stdout[-12000:], result.stderr[-2000:])
