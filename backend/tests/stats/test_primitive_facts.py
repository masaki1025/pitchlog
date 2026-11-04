"""独立55ケースと生成Python/Nodeの単一遷移寄与を照合する。"""

from __future__ import annotations

import copy
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from pitchlog.domaingen.core import generate_primitive_bundle

ROOT = Path(__file__).resolve().parents[3]
FEATURE = ROOT / "docs/features/mvp-stats-primitives"
CASES = json.loads((FEATURE / "primitive-cases.candidate.json").read_text())["cases"]
INPUT_VALIDATOR = Draft202012Validator(
    json.loads((FEATURE / "primitive-input.candidate.json").read_text())
)


def _load_model(name):
    return json.loads((ROOT / "backend/domain" / name).read_text())


@pytest.fixture(scope="module")
def bundle():
    """期待caseを渡さずmodel2件だけから生成する。"""
    return generate_primitive_bundle(
        _load_model("play-export.model.json"), _load_model("stats.model.json")
    )


@pytest.fixture(scope="module")
def py_api(bundle):
    """登録wrapper同様の名前空間で生成targetをロードする。"""
    namespace: dict[str, Any] = {"__name__": "__pitchlog_generated_wrapper__"}
    exec(
        compile(
            bundle["backend/src/pitchlog/stats/generated/facts.py"],
            "<generated-facts>",
            "exec",
        ),
        namespace,
    )
    return namespace


@pytest.fixture(scope="module")
def node_api(bundle, tmp_path_factory):
    """生成TSを実Nodeへ下げ、数値をJSON経由で比較する。"""
    folder = tmp_path_factory.mktemp("stats-node")
    source = folder / "target.ts"
    source.write_text(bundle["frontend/src/lib/generated/statsPrimitives.ts"])
    local = ROOT / "frontend/node_modules/.bin/esbuild"
    fallback = ROOT.parents[1] / "pitchlog/frontend/node_modules/.bin/esbuild"
    esbuild = local if local.exists() else fallback
    assert esbuild.exists(), "実Node比較には既frontend esbuildが必要です"
    output = folder / "target.cjs"
    subprocess.run(
        [
            str(esbuild),
            str(source),
            "--format=cjs",
            "--platform=node",
            f"--outfile={output}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    driver = folder / "driver.cjs"
    driver.write_text("""
globalThis.__PITCHLOG_GENERATED_WRAPPER__=true;
const api=require('./target.cjs');
const fs=require('fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));
const result=input.map(x=>x.kind==='add'
  ? api.addCounts(x.left,x.right) : api.eventFacts(x.event));
process.stdout.write(JSON.stringify(result));
""")

    def call(commands):
        result = subprocess.run(
            ["node", str(driver)],
            input=json.dumps(commands, ensure_ascii=False),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    return call


def _provider_fixture_gate(case):
    """独立fixture resolverを模擬する。正式認可/DBの実証ではない。"""
    data = case["input"]
    if not INPUT_VALIDATOR.is_valid(data):
        return "INPUT_SCHEMA_INVALID"
    if data["scope"] == "t6_sufficient_statistics":
        seen = set()
        for fact in data["facts"]:
            key = (fact["game_id"], fact["player_id"], fact["public_fact_version"])
            if key in seen and fact["lifecycle"] == "effective_latest":
                return "SOURCE_DUPLICATE"
            seen.add(key)
            if (
                fact["model_sha256"]
                != data["expected_versions"]["primitive_model_sha256"]
            ):
                return "SOURCE_MODEL_MISMATCH"
        return None
    events = data["events"]
    rows = case.get("provider_boundary_fixture", {}).get("receipt_binding_rows", [])
    if events and not rows:
        return "SOURCE_UNVERIFIED"
    seen = set()
    codes = {
        "tenant_id": "SOURCE_TENANT_MISMATCH",
        "game_id": "SOURCE_GAME_MISMATCH",
        "slot_version": "SOURCE_VERSION_MISMATCH",
        "checkpoint_revision": "SOURCE_CHECKPOINT_MISMATCH",
        "ledger_id": "SOURCE_LEDGER_MISMATCH",
    }
    for event, bound in zip(events, rows, strict=True):
        source = event["source"]
        if data["scope"] == "confirmed_game" and source["applied_state"] != "applied":
            return "SOURCE_NOT_APPLIED"
        key = (source["source_event_id"], source["recording_generation"], source["d1"])
        if key in seen:
            return "SOURCE_DUPLICATE"
        seen.add(key)
        for field, code in codes.items():
            if source[field] != bound[field]:
                return code
        for field, code in [
            ("primitive_model_sha256", "SOURCE_MODEL_MISMATCH"),
            ("t1_artifact_sha256", "SOURCE_ARTIFACT_MISMATCH"),
        ]:
            if source["versions"][field] != bound["versions"][field]:
                return code
        if (event["event_kind"] == "pitch") != event["stat_flags"]["投球数"]:
            return "T1_FLAG_KIND_MISMATCH"
    for bound in case.get("provider_boundary_fixture", {}).get(
        "bound_source_observations", []
    ):
        event = next(
            e
            for e in events
            if e["source"]["source_event_id"] == bound["source_event_id"]
        )
        if any(
            event[field] != bound[field]
            for field in ("before", "after", "pa", "steal_attempts")
        ):
            return "T1_QUANTITY_MISMATCH"
    return None


def _compare_event_results(case, results):
    """有限独立caseの比較専用収集。製品全game集計ではない。"""
    totals = defaultdict(int)
    unavailable = set()
    credits = []
    pa_rows = []
    for event, result in zip(case["input"]["events"], results, strict=True):
        assert result["source_event_id"] == event["source"]["source_event_id"]
        assert result["pending"] == case["expected"]["pending"]
        assert result["selected"] == (event["source"]["lifecycle"] == "effective")
        for metric, value in result["metrics"].items():
            if value["state"] == "available":
                totals[metric] += int(value["value"])
                assert value["display"] == value["value"]
                assert value["reason"] is None
            else:
                unavailable.add(metric)
                assert value["value"] is value["display"] is None
            for credit in value["credits"]:
                credits.append(
                    {
                        **credit,
                        "metric": metric,
                        "source_event_id": result["source_event_id"],
                        "source_fact_snapshot_sha256": None,
                    }
                )
        if result["pa_row"] is not None:
            pa_rows.append(result["pa_row"])
    for metric, expected in case["expected"]["totals"].items():
        assert (metric in unavailable) == (expected["state"] == "source_unavailable")
        if metric not in unavailable:
            assert str(totals[metric]) == expected["value"]

    def key(row):
        """順序に依存せず帰属を比較する。"""
        return (
            row["player_id"],
            row["metric"],
            row["source_event_id"] or "",
            row["quantity"],
        )

    assert sorted(credits, key=key) == sorted(case["expected"]["credits"], key=key)
    assert pa_rows == case["expected"]["completed_pa_rows"]
    assert {p["decision_id"] for p in case["expected"]["pending"].values()} == {
        "D02",
        "D03",
        "D04",
        "D05",
    }


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_independent_contract_cases_against_generated_targets(case, py_api, node_api):
    """正式source境界と生成数学を区別して独立期待へ照合する。"""
    rejected = _provider_fixture_gate(case)
    if case["expected"]["status"] == "rejected":
        assert rejected == case["expected"]["code"]
        return
    assert rejected is None
    if case["input"]["scope"] == "t6_sufficient_statistics":
        # SQLの本番集計は後段DB担当。ここは有限fixtureのadd primitive/formatter比較。
        known = defaultdict(lambda: "0")
        commands = []
        answers = []
        unknown = set()
        for fact in case["input"]["facts"]:
            if (
                fact["completion_state"] != "confirmed_ended"
                or fact["lifecycle"] != "effective_latest"
            ):
                continue
            if (
                fact["calendar_year_jst"] != case["input"]["calendar_year_jst"]
                or fact["raw_game_type_key"] not in case["input"]["raw_game_type_keys"]
            ):
                continue
            for metric, value in fact["counts"].items():
                if metric not in fact["computed_metric_keys"]:
                    unknown.add(metric)
                    continue
                python_value = py_api["add_counts"](known[metric], value)
                commands.append({"kind": "add", "left": known[metric], "right": value})
                answers.append(python_value)
                known[metric] = python_value
        assert node_api(commands) == answers
        for metric, expected in case["expected"]["totals"].items():
            assert (metric in unknown) == (expected["state"] == "source_unavailable")
            if metric not in unknown:
                assert known[metric] == expected["value"]
        return
    python_results = [py_api["_pitchlog_generated"](e) for e in case["input"]["events"]]
    node_results = node_api(
        [{"kind": "event", "event": e} for e in case["input"]["events"]]
    )
    assert python_results == node_results
    _compare_event_results(case, python_results)


def test_targets_are_reproducible_without_case_or_property_input(bundle):
    """全生成bytesがmodelだけで再現される。"""
    for path, content in bundle.items():
        assert (ROOT / path).read_text() == content


@pytest.mark.parametrize("value", [True, 1.5, -1, "01", None])
def test_integer_add_rejects_noncanonical_or_missing(value, py_api):
    """bool/float/負値/不正字面/NULLを整数0へ変換しない。"""
    with pytest.raises(ValueError):
        py_api["add_counts"](value, "1")


def test_finite_transition_reducer_rejects_unbounded_collection(py_api):
    """遷移内4人を超えるcollectionを処理しない。"""
    event = copy.deepcopy(
        next(c for c in CASES if c["case_id"] == "home-run-3-effective-runs")["input"][
            "events"
        ][0]
    )
    event["runner_scores"] *= 2
    with pytest.raises(ValueError):
        py_api["_pitchlog_generated"](event)


def test_arbitrary_precision_codec_does_not_impose_128_or_global_4300_limit(
    py_api, node_api
):
    """汎用整数codecは値域を128桁へ狭めずglobal設定も変更しない。"""
    import sys

    before = sys.get_int_max_str_digits()
    for digits in (129, 5001):
        value = "1" + "0" * (digits - 1)
        assert py_api["add_counts"](value, "0") == value
        assert node_api([{"kind": "add", "left": value, "right": "0"}])[0] == value
    assert sys.get_int_max_str_digits() == before


def test_generated_closed_flag_record_rejects_24th_field(py_api, node_api):
    """正式型validatorだけに頼らず生成targetも23fieldを閉じる。"""
    event = copy.deepcopy(
        next(c for c in CASES if c["case_id"] == "incomplete-pa-one-pitch")["input"][
            "events"
        ][0]
    )
    event["stat_flags"]["unregistered"] = False
    with pytest.raises(ValueError):
        py_api["_pitchlog_generated"](event)
    with pytest.raises(subprocess.CalledProcessError):
        node_api([{"kind": "event", "event": event}])
