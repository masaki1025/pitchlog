"""基本成績の27項目写像・T6表示率・候補SQLの純検査。"""

from __future__ import annotations

import json
from pathlib import Path

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
    """27項目を打撃16・投手11へ閉じ、D03/D04は0でなく未取得にする。"""
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
    assert pitches["batters_faced"]["reason"] == "D04_SOURCE_PENDING"
    assert result["pending"] == ["D03_SOURCE_PENDING", "D04_SOURCE_PENDING"]


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
