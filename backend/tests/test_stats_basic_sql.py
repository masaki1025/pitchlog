"""基本成績の27項目写像・T6表示率・候補SQLの純検査。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitchlog.api.routers.stats import _jst_boundaries, _metrics
from pitchlog.domaingen.core import generate_display_rates_bundle
from pitchlog.stats.basic_sql import candidate_sql, read_query
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
    assert pitching["whip"]["display"] == "−(投球回0)"


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
    assert pitching["innings_pitched"]["display"] == "3.1"
    batting = {item["metric_id"]: item for item in result["batting"]}
    assert batting["runs"]["state"] == "source_unavailable"
    assert batting["runs"]["reason"] == "MISSING_OBSERVATION"


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


def test_jst_calendar_year_boundaries():
    """シーズン境界はJSTの1/1〜翌1/1で、UTC年へ委ねない。"""
    start, end = _jst_boundaries(2026)
    assert start.startswith("2026-01-01T00:00:00+09:00")
    assert end.startswith("2027-01-01T00:00:00+09:00")
