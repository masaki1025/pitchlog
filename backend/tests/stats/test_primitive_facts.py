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


def _historical_models():
    """同compilerへ実固定Gitのv1モデルを渡し、34pending全期待を残す。"""
    import hashlib

    origin = json.loads((FEATURE / "primitive-cases.candidate.json").read_text())[
        "current_v2_followup"
    ]["legacy_comparison"]["immutable_v1_model_inputs"]
    models = []
    for name in ("play-export.model.json", "stats.model.json"):
        path = "backend/domain/" + name
        raw = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", origin["revision"] + ":" + path]
        )
        assert hashlib.sha256(raw).hexdigest() == origin["paths"][path]
        models.append(json.loads(raw))
    return tuple(models)


@pytest.fixture(scope="module")
def bundle():
    """期待caseを渡さずmodel2件だけから生成する。"""
    return generate_primitive_bundle(*_historical_models())


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


def _node_api_from_bundle(bundle, tmp_path_factory):
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
const result=input.map(x=>{
 if(x.kind==='add')return api.addCounts(x.left,x.right);
 if(x.kind==='rates')return api.deriveRates(x.metrics);
 if(x.kind==='select')return api.selectGameTypeKeys(x.category,x.keys);
 if(x.kind==='metadata')return api.decisionMetadata();
 return api.eventFacts(x.event,x.requested);
});
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


@pytest.fixture(scope="module")
def node_api(bundle, tmp_path_factory):
    """同じdriver構築器を歴史v1へ束縛する。"""
    return _node_api_from_bundle(bundle, tmp_path_factory)


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


def _compare_event_results(case, results, metadata_key="pending"):
    """有限独立caseの比較専用収集。製品全game集計ではない。"""
    totals = defaultdict(int)
    unavailable = set()
    credits = []
    pa_rows = []
    for event, result in zip(case["input"]["events"], results, strict=True):
        assert result["source_event_id"] == event["source"]["source_event_id"]
        assert result[metadata_key] == case["expected"][metadata_key]
        assert result["selected"] == (event["source"]["lifecycle"] == "effective")
        for metric, value in result["metrics"].items():
            if metric not in case["expected"]["totals"]:
                # 固定済み旧26期待は新BFを含まない。新項目は専用caseで比較する。
                assert metadata_key == "decisions" and metric == "batters_faced"
                continue
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
    assert {p["decision_id"] for p in case["expected"][metadata_key].values()} == {
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
    origin = json.loads((FEATURE / "primitive-cases.candidate.json").read_text())[
        "current_v2_followup"
    ]["legacy_comparison"]["immutable_v1_model_inputs"]
    assert len(bundle) == 7
    for path, content in bundle.items():
        assert (
            subprocess.check_output(
                ["git", "-C", str(ROOT), "show", origin["revision"] + ":" + path],
                text=True,
            )
            == content
        )


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


def test_projection_uses_only_demanded_fields_and_preserves_independent_counts(
    py_api, node_api
):
    """同じmodelの有限射影は不要PA値を捏造せず球数を返す。"""
    source = copy.deepcopy(
        next(c for c in CASES if c["case_id"] == "incomplete-pa-one-pitch")["input"][
            "events"
        ][0]
    )
    projected = {
        k: source[k]
        for k in ("event_kind", "source", "stat_flags", "participants", "completeness")
    }
    projected["participants"] = {
        "actual_pitcher_id": source["participants"]["actual_pitcher_id"]
    }
    projected["completeness"] = {"participants": "complete"}
    expected = {
        "state": "available",
        "value": "1",
        "display": "1",
        "reason": None,
        "credits": [
            {"player_id": source["participants"]["actual_pitcher_id"], "quantity": "1"}
        ],
    }
    actual = py_api["_pitchlog_generated"](projected, ["pitch_count"])
    assert actual["metrics"] == {"pitch_count": expected}
    assert actual["pa_row"] is None
    assert (
        node_api([{"kind": "event", "event": projected, "requested": ["pitch_count"]}])[
            0
        ]
        == actual
    )
    with pytest.raises(ValueError):
        py_api["_pitchlog_generated"](projected)


def test_projection_matches_full_entrypoint_on_existing_case_inputs(py_api, node_api):
    """既case入力で全field入口と有限射影の同値を補助比較する。"""
    commands = []
    expected = []
    for case in CASES:
        if case["input"]["scope"] != "confirmed_game" or case.get("expected_error"):
            continue
        if (
            len(case["input"]["events"]) != 1
            or _provider_fixture_gate(case) is not None
        ):
            continue
        event = case["input"]["events"][0]
        # 既caseの期待は変更せず、旧比較関数と同じ単遷移算入面を照合する。
        full = py_api["_pitchlog_generated"](event)
        for metric, value in full["metrics"].items():
            actual = py_api["_pitchlog_generated"](event, [metric])
            assert actual["metrics"] == {metric: value}
            commands.append({"kind": "event", "event": event, "requested": [metric]})
            expected.append(actual)
    assert commands
    assert node_api(commands) == expected


@pytest.mark.parametrize(
    "requested", [["unknown"], ["pa", "pa"], [False], ["pa"] * 27, "pa"]
)
def test_projection_rejects_unknown_duplicate_or_unbounded_ids(
    py_api, node_api, requested
):
    """有限ID射影を未知演算や任意iteratorの入口にしない。"""
    source = copy.deepcopy(
        next(c for c in CASES if c["case_id"] == "incomplete-pa-one-pitch")["input"][
            "events"
        ][0]
    )
    with pytest.raises(ValueError):
        py_api["_pitchlog_generated"](source, requested)
    with pytest.raises(subprocess.CalledProcessError):
        node_api([{"kind": "event", "event": source, "requested": requested}])


@pytest.fixture(scope="module")
def v2_bundle():
    """現在v2モデルだけを同じcompilerへ渡す。"""
    return generate_primitive_bundle(
        _load_model("play-export.model.json"), _load_model("stats.model.json")
    )


@pytest.fixture(scope="module")
def v2_python(v2_bundle):
    """新生成物を実wrapper namespaceでロードする。"""
    namespace = {"__name__": "__pitchlog_generated_wrapper__"}
    exec(
        compile(
            v2_bundle["backend/src/pitchlog/stats/generated/facts.py"],
            "<v2-generated>",
            "exec",
        ),
        namespace,
    )
    return namespace


@pytest.fixture(scope="module")
def v2_node(v2_bundle, tmp_path_factory):
    """同じ実Node driverを新生成TSへ使い、別実装にしない。"""
    return _node_api_from_bundle(v2_bundle, tmp_path_factory)


def _current_cases():
    data = json.loads((FEATURE / "primitive-cases.candidate.json").read_text())[
        "current_v2_followup"
    ]
    return [*data["regression_cases"], *data["cases"]]


@pytest.mark.parametrize("case", _current_cases(), ids=lambda c: c["case_id"])
def test_current_v2_all_primitive_pa_credit_and_derived_values(
    case, v2_python, v2_node
):
    """旧26/PA/creditの全比較と新selector/ratioの独立75期待を保持する。"""
    rejection = _provider_fixture_gate(case)
    if case["expected"]["status"] == "rejected":
        assert rejection == case["expected"]["code"]
        return
    assert rejection is None
    expected = case["expected"]
    assert v2_python["decision_metadata"]() == expected["decisions"]
    assert v2_node([{"kind": "metadata"}])[0] == expected["decisions"]
    data = case["input"]
    if data["scope"] != "t6_sufficient_statistics":
        py = [v2_python["_pitchlog_generated"](event) for event in data["events"]]
        node = v2_node([{"kind": "event", "event": event} for event in data["events"]])
        assert py == node
        _compare_event_results(case, py, "decisions")
        assert expected["rates"]["ops"] is None
        return
    keys = v2_python["select_game_type_keys"](
        data["named_category"], data["raw_game_type_keys"]
    )
    assert (
        v2_node(
            [
                {
                    "kind": "select",
                    "category": data["named_category"],
                    "keys": data["raw_game_type_keys"],
                }
            ]
        )[0]
        == keys
    )
    known = {key: "0" for key in expected["totals"]}
    missing = set()
    for fact in data["facts"]:
        if (
            fact["completion_state"] != "confirmed_ended"
            or fact["lifecycle"] != "effective_latest"
            or fact["calendar_year_jst"] != data["calendar_year_jst"]
            or fact["raw_game_type_key"] not in keys
        ):
            continue
        for key, value in fact["counts"].items():
            if key not in fact["computed_metric_keys"]:
                missing.add(key)
            else:
                known[key] = v2_python["add_counts"](known[key], value)
    actual = {
        key: (
            {
                "state": "source_unavailable",
                "value": None,
                "display": None,
                "reason": "MISSING_OBSERVATION",
            }
            if key in missing
            else {
                "state": "available",
                "value": value,
                "display": value,
                "reason": None,
            }
        )
        for key, value in known.items()
    }
    assert actual == expected["totals"]
    credits = [
        {
            "player_id": data["player_id"],
            "metric": key,
            "quantity": value["value"],
            "source_event_id": None,
            "source_fact_snapshot_sha256": data["source_snapshot_sha256"],
        }
        for key, value in actual.items()
        if value["value"] not in ("0", None)
    ]
    assert credits == expected["credits"]
    assert expected["completed_pa_rows"] == []
    # 旧26の率goldenはBFと独立。27入口へだけ中立値を供給して原期待を維持する。
    current_rate_input = {
        **actual,
        "batters_faced": {
            "state": "available",
            "value": "0",
            "display": "0",
            "reason": None,
        },
    }
    assert v2_python["derive_rates"](current_rate_input) == expected["rates"]
    assert v2_node([{"kind": "rates", "metrics": current_rate_input}])[0] == expected["rates"]


@pytest.mark.parametrize(
    "mutation", ["category", "missing-other", "raw-order", "raw-extra", "raw-type"]
)
def test_generated_named_sets_refuse_arbitrary_raw_override(
    mutation, v2_python, v2_node
):
    """正準raw集合を呼出側の自由一覧へ戻さない。"""
    category, keys = "practice", ["game_open", "game_intrasquad", "game_other"]
    if mutation == "category":
        category = "unknown"
    elif mutation == "missing-other":
        keys.pop()
    elif mutation == "raw-order":
        keys.reverse()
    elif mutation == "raw-extra":
        keys.append("game_official")
    else:
        keys = "game_open"
    with pytest.raises(ValueError):
        v2_python["select_game_type_keys"](category, keys)
    with pytest.raises(subprocess.CalledProcessError):
        v2_node([{"kind": "select", "category": category, "keys": keys}])


def test_v2_targets_are_reproducible_without_contract_input(v2_bundle):
    """新8byteはmodel2件から再現され、旧7の歴史比較と混同しない。"""
    assert len(v2_bundle) == 8
    assert (
        generate_primitive_bundle(
            _load_model("play-export.model.json"), _load_model("stats.model.json")
        )
        == v2_bundle
    )
    for path, content in v2_bundle.items():
        assert (ROOT / path).read_text() == content


def test_v2_ratio_has_no_float_or_global_digit_limit(
    v2_python, v2_node, record_property
):
    """5001桁の実十分統計から同じexact2を出し、global上限は変更しない。"""
    import sys

    before = sys.get_int_max_str_digits()
    known = {
        key: "0"
        for key in _load_model("play-export.model.json")["calculations"][0][
            "typedProgram"
        ]["metrics"]
        for key in [key["id"]]
    }
    large = "1" + "0" * 5000
    for key in ("ab", "h", "total_bases"):
        known[key] = large
    py = v2_python["derive_rates"](known)
    assert py["ops"]["exact_ratio"] == {"numerator": "2", "denominator": "1"}
    assert py["ops"]["formatted_value"] == "2.000"
    assert py["ops"]["components"]["obp"]["denominator"] == large
    assert v2_node([{"kind": "rates", "metrics": known}])[0] == py
    # 約分後の最終分子・分母自体も4300桁を超える。期待文字列は整数str変換せず固定する。
    almost = "9" * 5000
    known["h"] = known["total_bases"] = almost
    nontrivial = v2_python["derive_rates"](known)
    assert nontrivial["ops"]["exact_ratio"] == {
        "numerator": almost,
        "denominator": "5" + "0" * 4999,
    }
    assert nontrivial["ops"]["formatted_value"] == "2.000"
    assert nontrivial["ops"]["components"]["obp"]["denominator"] == large
    assert v2_node([{"kind": "rates", "metrics": known}])[0] == nontrivial
    assert sys.get_int_max_str_digits() == before
    record_property("integer_global_limit_before", before)
    record_property("integer_global_limit_after", sys.get_int_max_str_digits())
    record_property("input_decimal_digits", len(large))
    record_property("exact_numerator_digits", len(almost))
    record_property("exact_denominator_digits", len("5" + "0" * 4999))


@pytest.mark.parametrize(
    "mutation",
    ["available-null", "boolean", "float", "newline", "missing", "extra", "bad-reason"],
)
def test_v2_rate_input_state_and_values_are_closed(mutation, v2_python, v2_node):
    """不正なavailable/NULLをsource不足へ黙って補修しない。"""
    case = next(
        c
        for c in _current_cases()
        if c["case_id"] == "current-v2-po-d05-one-third-plus-one-third"
    )
    metrics = copy.deepcopy(case["expected"]["totals"])
    if mutation == "available-null":
        metrics["h"]["value"] = metrics["h"]["display"] = None
    elif mutation == "boolean":
        metrics["h"] = True
    elif mutation == "float":
        metrics["h"] = 1.5
    elif mutation == "newline":
        metrics["h"]["value"] = metrics["h"]["display"] = "1\n"
    elif mutation == "missing":
        del metrics["h"]
    elif mutation == "extra":
        metrics["unknown"] = "0"
    else:
        metrics["h"] = {
            "state": "source_unavailable",
            "value": None,
            "display": None,
            "reason": "unknown",
        }
    with pytest.raises(ValueError):
        v2_python["derive_rates"](metrics)
    with pytest.raises(subprocess.CalledProcessError):
        v2_node([{"kind": "rates", "metrics": metrics}])


def test_nonplay_normal_uses_same_projection_and_exact_restored_responsibility():
    """NPの原責任をaliasし、再計算/別event集合を作らない。"""
    import importlib.util
    from pathlib import Path
    from uuid import UUID

    from pitchlog.stats.facts import evaluate_native_projection, native_projection

    p = Path(__file__).resolve().parents[1] / "test_nonplay_normal_payload.py"
    spec = importlib.util.spec_from_file_location("np_fact_fixture", p)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw, _ = module.fixture_values()
    q = raw["calculation"]["request"]
    before = q["source"]["checkpoint"]["content"]["restored"]
    people = raw["participants"]
    event = UUID(q["playIdentity"]["eventId"])
    expected = {
        "event_kind": "pitch",
        "source": {"lifecycle": "effective", "source_event_id": str(event)},
        "before": {"inning": "1", "half": "top"},
        "stat_flags": raw["calculation"]["response"]["value"]["t1"]["statFlags"],
        "out_effect": {"effective_count": "0"},
        "pa": {
            "ended_here": False,
            "pa_id": before["responsibility"]["paStartSource"]["id"],
        },
        "participants": {
            "actual_pitcher_id": people["pitcherId"],
            "actual_batter_id": people["batterId"],
            "credited_batter_id": people["batterId"],
            **{
                key: people["pitcherId"]
                for key in (
                    "strikeout_pitcher_id",
                    "walk_pitcher_id",
                    "hbp_pitcher_id",
                    "hit_pitcher_id",
                    "home_run_pitcher_id",
                    "outs_pitcher_id",
                )
            },
        },
        "completeness": {
            "participants": "complete",
            "pa": "complete",
            "outs": "complete",
            "runs_rbi": "unavailable",
            "steals": "unavailable",
        },
    }
    assert native_projection(raw, source_event_id=event) == expected
    result = evaluate_native_projection(raw, source_event_id=event)
    assert result["metrics"]["pitch_count"]["value"] == "1"
    assert result["metrics"]["pitching_outs"]["value"] == "0"
    bad = copy.deepcopy(raw)
    bad["calculation"]["request"]["source"]["checkpoint"]["content"]["restored"][
        "responsibility"
    ]["kind"] = "unknown"
    with pytest.raises(ValueError):
        native_projection(bad, source_event_id=event)
