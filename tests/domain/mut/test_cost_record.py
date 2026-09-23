"""変異コストの拘束実測レコードと上限比較を検査する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
COST_PATH = ROOT / "docs/features/domain-calc-dsl/mutation-cost.json"

sys.path.insert(0, str(BACKEND_SRC))
COST = importlib.import_module("pitchlog.domainmut.cost_record")


def _asset() -> dict[str, Any]:
    """変異コスト資産を JSON object として返す。"""
    value = json.loads(COST_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _step_49_record() -> dict[str, Any]:
    """資産内のステップ 49 記録を一意に返す。"""
    matches = [item for item in _asset()["measurements"] if item["step"] == 49]
    assert len(matches) == 1
    return matches[0]


def test_record_contains_strict_schema_for_all_five_evidence_fields() -> None:
    """生ログ・コマンド・SHA・runner・分類の五項目を厳密 schema で固定する。"""
    record = _step_49_record()

    COST.validate_measurement(record)

    schema = record["recordSchema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "rawLogs",
        "commands",
        "commitSha",
        "runners",
        "mutantClassifications",
    }


@pytest.mark.parametrize(
    "field",
    (
        "rawLogs",
        "commands",
        "commitSha",
        "runners",
        "mutantClassifications",
    ),
)
def test_missing_each_evidence_field_is_rejected(field: str) -> None:
    """五証拠項目を一つずつ欠落させたレコードを拒否する。"""
    record = copy.deepcopy(_step_49_record())
    del record["evidence"][field]

    with pytest.raises(COST.CostRecordError, match="キー集合差"):
        COST.validate_measurement(record)


def test_unknown_evidence_field_is_rejected() -> None:
    """証拠レコードの未知キーを拒否する。"""
    record = copy.deepcopy(_step_49_record())
    record["evidence"]["selfReportedPass"] = True

    with pytest.raises(COST.CostRecordError, match="unknown"):
        COST.validate_measurement(record)


def test_mutant_inventory_is_derived_from_step_30_for_four_classes() -> None:
    """Step 30 の実生成物から四変異系統の非空な母数を導出する。"""
    inventory = COST.collect_mutant_inventory(ROOT)
    recorded = _step_49_record()["evidence"]["mutantClassifications"]

    assert len(inventory) == 4
    assert {item["id"] for item in inventory} == {
        item.value for item in COST.MutationClassification
    }
    assert all(item["mutantCount"] > 0 for item in inventory)
    assert recorded == list(inventory)


def test_all_runner_tests_are_in_each_recorded_command() -> None:
    """Step 34〜38 の全 runner が実行コマンドへ含まれる。"""
    evidence = _step_49_record()["evidence"]
    runner_paths = {runner["testPath"] for runner in evidence["runners"]}

    assert len(runner_paths) == 5
    assert all((ROOT / path).is_file() for path in runner_paths)
    for command in evidence["commands"]:
        assert runner_paths <= set(command["argv"])


def test_recorded_scopes_recompute_product_and_budget_decision() -> None:
    """記録済みの積と 10 分・30 分の比較を値の固定なしで再計算する。"""
    record = _step_49_record()

    COST.validate_measurement(record)

    for scope in record["scopes"]:
        assert scope["estimatedTotalSeconds"] == pytest.approx(
            scope["mutantCount"] * scope["suiteRerunSeconds"]
        )
        assert scope["withinBudget"] is (
            scope["estimatedTotalSeconds"] <= scope["budgetSeconds"]
        )


def test_over_budget_transition_is_rejected_as_within_budget() -> None:
    """時間を上限超過へ動かすと合格判定へ倒れない。"""
    result = COST.budget_result("differential", 2, 301.0, 600)

    assert result["withinBudget"] is False
    assert result["headroomSeconds"] < 0


def test_actual_measurement_is_generated_and_passes_both_budgets() -> None:
    """実スイートを二範囲で起動し、上限内の測定レコードを生成する。"""
    measurement = COST.create_measurement(
        ROOT,
        measured_at="2026-09-20T00:00:00+00:00",
    )

    COST.validate_measurement(measurement)
    assert all(scope["withinBudget"] for scope in measurement["scopes"])
    assert all(log["exitCode"] == 0 for log in measurement["evidence"]["rawLogs"])
    assert all(log["stdout"] for log in measurement["evidence"]["rawLogs"])


def test_appending_preserves_step_40_and_41_measurements() -> None:
    """ステップ 49 の再記録が既存の言語別・表示系実測を保持する。"""
    document = _asset()
    before = [
        copy.deepcopy(item)
        for item in document["measurements"]
        if item["step"] in {40, 41}
    ]

    updated = COST.append_measurement(document, _step_49_record())

    after = [
        item for item in updated["measurements"] if item["step"] in {40, 41}
    ]
    assert after == before


def test_product_scale_extrapolation_records_its_limit() -> None:
    """合成対象から未実測の製品規模を数値として推定しない。"""
    extrapolation = _step_49_record()["extrapolation"]

    assert extrapolation["basis"] == "mutant-count-times-suite-rerun-seconds"
    assert extrapolation["productProjectionAvailable"] is False
    assert extrapolation["limitation"]
