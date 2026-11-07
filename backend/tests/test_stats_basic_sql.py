"""基本成績の27項目写像・T6表示率・候補SQLの純検査。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from stats_api_candidate import _jst_boundaries, _metrics
from stats_basic_candidate import ReadBasicStatsToken
from stats_basic_candidate import test_only_finalize_sql as _test_only_finalize_sql
from stats_schemas_candidate import BasicStatItem

from pitchlog.domaingen.core import generate_display_rates_bundle
from pitchlog.stats.basic_sql import (
    candidate_sql,
    read_query,
)
from pitchlog.stats.basic_stats import (
    COUNT_METRIC_IDS,
    build_basic_stats,
)

ROOT = Path(__file__).resolve().parents[2]


def _metrics_available(**overrides):
    values = {key: {"state": "available", "value": 0} for key in COUNT_METRIC_IDS}
    values.update(overrides)
    return values


def test_basic_stats_has_16_batting_and_11_pitching_items():
    """27項目を閉じ、供給済BFと未供給登板を区別する。"""
    result = build_basic_stats(_metrics_available())
    assert len(result["batting"]) == 16
    assert len(result["pitching"]) == 11
    assert [item["metric_id"] for item in result["batting"]][:3] == [
        "pa",
        "ab",
        "h",
    ]
    assert [item["metric_id"] for item in result["pitching"]][:3] == [
        "appearances",
        "innings_pitched",
        "batters_faced",
    ]
    pitches = {item["metric_id"]: item for item in result["pitching"]}
    assert pitches["appearances"]["state"] == "source_unavailable"
    assert pitches["appearances"]["reason"] == "D03_SOURCE_PENDING"
    assert pitches["batters_faced"]["state"] == "available"
    assert pitches["batters_faced"]["value"] == 0
    assert result["pending"] == ["D03_SOURCE_PENDING", None]


def test_basic_stats_function_is_observed_by_catalog_detail_query():
    """製品で宣言した読取関数を実カタログの本文検査へ含める。"""
    from pitchlog.authz import first_ball_product, product_catalog

    identities = {(row[0], row[1]) for row in first_ball_product.function_details()}
    assert ("stats_basic_api", "read_basic_stats") in identities
    assert "'stats_basic_api'" in product_catalog._LIFECYCLE_FUNCTION_DETAILS_QUERY


def test_basic_stats_missing_bf_attribution_stays_unavailable():
    """真正な帰属が欠けたBFを0や現任へ補完しない。"""
    result = build_basic_stats(
        _metrics_available(
            batters_faced={
                "state": "source_unavailable",
                "reason": "MISSING_ATTRIBUTION",
            }
        )
    )
    bf = {row["metric_id"]: row for row in result["pitching"]}["batters_faced"]
    assert bf["state"] == "source_unavailable"
    assert bf["value"] is None
    assert bf["reason"] == "MISSING_ATTRIBUTION"
    assert result["pending"] == ["D03_SOURCE_PENDING", "D04_SOURCE_PENDING"]


def test_appearance_requires_actual_complete_defensive_entry_source():
    """スタメンだけの未守備投手を登板へ推測せず、未供給を残す。"""
    from pitchlog.stats.basic_sql import read_function_body

    body = read_function_body()
    assert "appearance_scope/member provider" in body
    assert "appearance_ready" not in body
    assert "SELECT count(*) INTO appearance_count FROM public.game_lineups" not in body
    assert (
        "'appearances',\n"
        "    pg_catalog.jsonb_build_object('state','source_unavailable','value',NULL)"
        in body
    )
    for appearances in (0, 1):
        row = build_basic_stats(_metrics_available(), appearances=appearances)
        item = next(
            part for part in row["pitching"] if part["metric_id"] == "appearances"
        )
        assert item["state"] == "available" and item["value"] == appearances
    unknown = build_basic_stats(
        _metrics_available(appearances={"state": "source_unavailable", "value": None})
    )
    item = next(
        part for part in unknown["pitching"] if part["metric_id"] == "appearances"
    )
    assert item["state"] == "source_unavailable" and item["value"] is None
    assert "D03_SOURCE_PENDING" in unknown["pending"]


def test_basic_stats_rates_use_generated_single_rule():
    """3打数1単打を打率.333・OPS0.667・WHIPへ同じ生成規則で写す。"""
    result = build_basic_stats(
        _metrics_available(
            ab={"state": "available", "value": 3},
            pa={"state": "available", "value": 3},
            h={"state": "available", "value": 1},
            total_bases={"state": "available", "value": 1},
        )
    )
    batting = {item["metric_id"]: item for item in result["batting"]}
    assert batting["avg"]["display"] == ".333(打数3)"
    assert batting["obp"]["display"] == ".333(打席3)"
    assert batting["slg"]["display"] == ".333(打数3)"
    assert batting["ops"]["display"].startswith("0.667")
    # 投球回0はWHIPの分母0で、0.00ではなく「−」。
    pitching = {item["metric_id"]: item for item in result["pitching"]}
    assert pitching["whip"]["display"] == "−(0回)"


def test_basic_stats_innings_and_missing_source_are_not_zero():
    """投球回はアウト数から表示し、不足十分統計を0へ補完しない。"""
    result = build_basic_stats(
        _metrics_available(
            pitching_outs={"state": "available", "value": 10},
            runs={
                "state": "source_unavailable",
                "value": None,
                "reason": "MISSING_OBSERVATION",
            },
        )
    )
    pitching = {item["metric_id"]: item for item in result["pitching"]}
    assert pitching["innings_pitched"]["display"] == "3回1/3"
    batting = {item["metric_id"]: item for item in result["batting"]}
    assert batting["runs"]["state"] == "source_unavailable"
    assert batting["runs"]["reason"] == "MISSING_OBSERVATION"


def test_t5_components_keep_slg_when_obp_source_is_missing():
    """T5の片側欠測でも独立した長打率を失わない。"""
    result = build_basic_stats(
        _metrics_available(
            h={"state": "available", "value": 1},
            ab={"state": "available", "value": 3},
            total_bases={"state": "available", "value": 1},
            bb={"state": "source_unavailable", "reason": "MISSING_OBSERVATION"},
        )
    )
    batting = {item["metric_id"]: item for item in result["batting"]}
    assert batting["obp"]["state"] == "source_unavailable"
    assert batting["slg"]["display"] == ".333(打数3)"
    assert batting["slg"]["value"] == {"numerator": "1", "denominator": "3"}
    assert batting["ops"]["state"] == "source_unavailable"
    reverse = build_basic_stats(
        _metrics_available(
            h={"state": "available", "value": 1},
            ab={"state": "available", "value": 3},
            total_bases={
                "state": "source_unavailable",
                "reason": "MISSING_ATTRIBUTION",
            },
        )
    )
    reverse_batting = {item["metric_id"]: item for item in reverse["batting"]}
    assert reverse_batting["obp"]["display"] == ".333(打席3)"
    assert reverse_batting["slg"]["state"] == "source_unavailable"
    assert reverse_batting["slg"]["reason"] == "MISSING_ATTRIBUTION"


def test_rate_value_is_ratio_or_null_and_innings_share_one_formatter():
    """値と表示を分離し、投球回とWHIP母数を同じ混合分数にする。"""
    result = build_basic_stats(
        _metrics_available(
            pitching_outs={"state": "available", "value": 10},
            hits_allowed={"state": "available", "value": 3},
            pitcher_bb={"state": "available", "value": 1},
        )
    )
    pitching = {item["metric_id"]: item for item in result["pitching"]}
    assert pitching["innings_pitched"]["display"] == "3回1/3"
    assert pitching["whip"]["display"] == "1.20(3回1/3)"
    assert pitching["whip"]["value"] == {"numerator": "6", "denominator": "5"}
    assert BasicStatItem.model_validate(pitching["whip"]).model_dump()["value"] == {
        "numerator": "6",
        "denominator": "5",
    }
    zero = build_basic_stats(_metrics_available())
    zero_batting = {item["metric_id"]: item for item in zero["batting"]}
    zero_pitching = {item["metric_id"]: item for item in zero["pitching"]}
    assert zero_batting["ops"]["value"] is None
    assert zero_batting["ops"]["display"] == "−(出塁率分母0打席・長打率分母0打数)"
    assert zero_pitching["whip"]["value"] is None
    assert zero_pitching["whip"]["display"] == "−(0回)"


def test_basic_stats_rejects_unknown_or_extra_metrics():
    """未知metricや閉26の欠落を無視・0補完しない。"""
    metrics = _metrics_available()
    metrics["unknown"] = {"state": "available", "value": 1}
    with pytest.raises(ValueError):
        build_basic_stats(metrics)
    del metrics["unknown"]
    del metrics["pa"]
    with pytest.raises(ValueError):
        build_basic_stats(metrics)


def test_candidate_sql_matches_committed_candidate_and_scope():
    """候補SQLのbyte固定と、公式/暫定・試合/暦年のscope差替えを確認する。"""
    committed = (
        ROOT / "docs/features/mvp-basic-stats-csv/candidates/basic_stats_functions.sql"
    ).read_text()
    assert committed == candidate_sql()
    query = read_query()
    assert ":tenant_id" not in query and ":player_id" not in query
    assert "$9" in query and "confirmed_ended" in query and "current_open" in query
    assert "g.id=$8" in query
    assert "h.active_stats_version_id=v.id" in query
    assert "h.active_receipt_id=v.completion_receipt_id" in query
    assert "h.active_end_event_id IS NOT NULL" in query
    assert "a.action='end' AND a.state='consumed'" in query
    assert "e.event_kind='game_end_declaration'" in query
    assert "e.ledger_kind='accepted' AND NOT e.is_tombstone" in query
    assert "stats_basic_api" in committed
    assert "SECURITY DEFINER" in committed
    # finalizeは製品候補に含めず、owned検証専用の別fileへ分離する。
    assert "finalize_game_stats" not in committed
    finalize = (
        ROOT / "docs/features/mvp-basic-stats-csv/candidates/"
        "finalize_game_stats.test-only.sql"
    ).read_text()
    assert finalize == _test_only_finalize_sql()
    assert "TEST ONLY" in finalize


def test_product_basic_read_uses_exact_registry_and_lifecycle_head():
    """製品入口は候補hookを使わず、真正RR readの実tokenだけを登録する。"""
    from pitchlog.authz.stats_basic_product import connection_declarations
    from pitchlog.repositories import operation_registry, transaction
    from pitchlog.repositories.stats_basic import (
        ReadBasicStatsToken as ProductReadToken,
    )
    from pitchlog.repositories.tokens import TenantOperationToken

    token = ProductReadToken(
        "",
        "2026-01-01T00:00:00+09:00",
        "2027-01-01T00:00:00+09:00",
        "all",
        True,
        "",
        10,
    )
    assert transaction._basic_stats_read_operation(token)
    assert not transaction._basic_stats_read_operation(
        cast(TenantOperationToken, object())
    )
    assert ProductReadToken in operation_registry.FUNCTION_OPERATION_REGISTRY
    assert (
        operation_registry.FUNCTION_OPERATION_REGISTRY[ProductReadToken].operation_id
        == "STATS_BASIC:read"
    )
    assert not hasattr(transaction, "_EXTRA_STATS_READ_OPERATION")
    declarations, bodies = connection_declarations()
    assert len(declarations["functions"]) == 1
    assert len(declarations["policies"]) == 2
    assert (
        "game_lifecycle_heads"
        in bodies["function|" + declarations["functions"][0]["function_id"]]
    )


def test_display_rates_generation_is_reproducible():
    """T6表示率modelからrates.pyを再生成し、T5 artifactを変更しない。"""
    common = json.loads((ROOT / "backend/domain/play-export.model.json").read_text())
    display = json.loads((ROOT / "backend/domain/stats-display.model.json").read_text())
    generated = generate_display_rates_bundle(common, display)
    path = "backend/src/pitchlog/stats/generated/rates.py"
    assert generated[path] == (ROOT / path).read_text()


def test_metrics_json_rejects_duplicate_and_unknown():
    """DB関数のJSONを重複key・未知metricのまま受理しない。"""
    payload = json.dumps(
        {key: {"state": "available", "value": "0"} for key in COUNT_METRIC_IDS}
    )
    parsed = _metrics(payload)
    assert set(parsed) == set(COUNT_METRIC_IDS)
    duplicate = payload[:-1] + ', "pa": {"state": "available", "value": "1"}}'
    with pytest.raises(ValueError):
        _metrics(duplicate)
    unknown = json.loads(payload)
    unknown["unknown"] = {"state": "available", "value": "0"}
    with pytest.raises(ValueError):
        _metrics(json.dumps(unknown))
    extended = json.loads(payload)
    extended["appearances"] = {"state": "available", "value": "1"}
    extended["batters_faced"] = {"state": "available", "value": "3"}
    parsed_extended = _metrics(json.dumps(extended))
    assert parsed_extended["appearances"]["value"] == 1


def test_jst_calendar_year_boundaries():
    """シーズン境界はJSTの1/1〜翌1/1で、UTC年へ委ねない。"""
    start, end = _jst_boundaries(2026)
    assert start.startswith("2026-01-01T00:00:00+09:00")
    assert end.startswith("2027-01-01T00:00:00+09:00")


def test_year_9999_has_closed_exclusive_end():
    """Python datetime上限の年でもJST年境界を形成する。"""
    start, end = _jst_boundaries(9999)
    assert (start, end) == (
        "9999-01-01T00:00:00+09:00",
        "10000-01-01T00:00:00+09:00",
    )
    token = ReadBasicStatsToken(
        game_id="",
        year_start=start,
        year_end=end,
        category="all",
        official=True,
        after_player_id="",
        page_size=200,
    )
    assert token.year_end == end


def test_csv_iterates_past_ui_page_boundary_with_same_player_set(monkeypatch):
    """201人目を同じcursorと表示値のCSV行まで届ける。"""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from typing import Any, cast
    from uuid import UUID

    import stats_api_candidate as api

    payload = json.dumps(
        {key: {"state": "available", "value": "0"} for key in COUNT_METRIC_IDS}
    )
    team = UUID("00000000-0000-4000-8000-000000000999")
    rows = tuple(
        (
            UUID(f"00000000-0000-4000-8000-{index:012d}"),
            f"{index}番",
            str(index),
            team,
            "自チーム",
            payload,
        )
        for index in range(1, 202)
    )
    cursors = []

    class Scope:
        def run_function(self, token):
            cursors.append(token.after_player_id)
            if not token.after_player_id:
                return SimpleNamespace(rows=rows)
            assert token.after_player_id == str(rows[199][0])
            return SimpleNamespace(rows=rows[200:])

    @contextmanager
    def scope(_context):
        yield Scope()

    monkeypatch.setattr(api, "stats_primitive_read_scope", scope)
    players = list(
        api._iter_players(
            cast(Any, None),
            game_id=UUID("00000000-0000-4000-8000-000000000998"),
            mode="current",
            year=None,
            category="all",
        )
    )
    assert len(players) == 201
    assert cursors == ["", str(rows[199][0])]
    assert players[-1].player_name == "201番"
    csv_rows = [api._csv_row(player) for player in players]
    assert len(csv_rows) == 201
    assert csv_rows[-1][0] == str(players[-1].player_id)
    assert csv_rows[-1][5 + 15] == players[-1].batting[-1].display
