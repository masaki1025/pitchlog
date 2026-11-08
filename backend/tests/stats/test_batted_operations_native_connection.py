"""実唯一host→閉V7→既生成T5へ、新打球の観測と算入IDを接続する。"""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest
from test_batted_operations_schema import actual_batted_payload

from pitchlog.domainrt.host import open_domain_host
from pitchlog.stats.facts import evaluate_native_projection

ROOT = Path(__file__).resolve().parents[3]
ROWS = json.loads(
    (
        ROOT
        / "backend/tests/fixtures/batted_operations_schema_runtime_requests_v1.json"
    ).read_text()
)["samples"]
# 入力の操作/原観測に対する既規範の手例。実host出力を期待へ採取しない。
EXPECTED = [
    ("single", "0", "0", "0"),
    ("batted-out", "0", "0", "0"),
    ("sacrifice-bunt", "0", "0", "0"),
    ("single", "1", "0", "0"),  # RBI-04: 生還は有効、停止後再発進は打点なし。
    ("double-play", "0", "0", "0"),
    ("fielders-choice", "0", "0", "0"),
    ("error", "0", "0", "1"),
    ("sacrifice-fly", "1", "1", "0"),
    ("batted-reach", "0", "0", "0"),
    ("sacrifice-bunt-error", "0", "0", "1"),
]
assert len(ROWS) == len(EXPECTED) == 10


@pytest.fixture(scope="module")
def host():
    """全行を同じ実hostで再計算し、応答のキャッシュは作らない。"""
    with open_domain_host() as real:
        yield real


@pytest.mark.parametrize("index", range(10))
def test_real_batted_wire_supplies_all_27_primitive_inputs(host, index):
    """手定応答やframeを使わず、実計算の算入を実IDへ写す。DB成功ではない。"""
    name, runs, rbi, errors = EXPECTED[index]
    assert ROWS[index]["operation"] == name
    typed = actual_batted_payload(ROWS[index], host)
    raw = typed.model_dump(mode="json", by_alias=True, exclude_unset=True)
    before = copy.deepcopy(raw)
    result = evaluate_native_projection(
        raw, source_event_id=UUID(typed.calculation.request.play_identity.event_id)
    )
    metrics = result["metrics"]
    assert len(metrics) == 27
    assert {
        k: v["reason"] for k, v in metrics.items() if v["state"] != "available"
    } == {}
    for key, expected in (
        ("runs", runs),
        ("rbi", rbi),
        ("runs_allowed", runs),
        ("fielding_errors", errors),
        ("stolen_bases", "0"),
    ):
        assert metrics[key]["value"] == expected
    if errors == "1":
        field = raw["observations"]["officialScoringPayload"]["errors"][0]["fielder"][
            "player_id"
        ]
        assert metrics["fielding_errors"]["credits"] == [
            {"player_id": field, "quantity": "1"}
        ]
        # boolを数値1と等価に補修して失策を帰属させない。
        bad = copy.deepcopy(raw)
        bad["observations"]["officialScoringPayload"]["errors"][0]["count"] = True
        rejected = evaluate_native_projection(
            bad, source_event_id=UUID(typed.calculation.request.play_identity.event_id)
        )
        assert rejected["metrics"]["fielding_errors"]["state"] == "source_unavailable"
    assert raw == before
