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
    is_v3 = data.get("contract_version") == "primitive-input-v3-candidate"
    if is_v3:
        marker = case.get("provider_boundary_fixture", {}).get(
            "bf_same_frame_qualification"
        )
        if marker == "UUID-only-not-issued":
            return "SOURCE_UNVERIFIED"
        if marker == "receipt-from-different-frame":
            return "SOURCE_CHECKPOINT_MISMATCH"
        if marker == "v2-source-cannot-be-stamped-v3":
            return "SOURCE_MODEL_MISMATCH"
        for event in events:
            evidence = event["pa"]["bf_evidence"]
            if evidence["kind"] == "no-change":
                start = evidence["pa_start_source"]
                if (
                    start["kind"] == "started-game"
                    and start["id"] != event["source"]["game_id"]
                ):
                    return "PA_SOURCE_MISMATCH"
            elif evidence["kind"] == "verified-result-owner":
                if (
                    evidence["responsibility_ref"]["source_event_id"]
                    != event["source"]["source_event_id"]
                ):
                    return "PA_SOURCE_MISMATCH"
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
            (
                {k: v for k, v in event[field].items() if k != "bf_evidence"}
                if is_v3 and field == "pa"
                else event[field]
            )
            != bound[field]
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
    return generate_primitive_bundle(*_v2_models())


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
    assert v2_python["derive_rates"](actual) == expected["rates"]
    assert v2_node([{"kind": "rates", "metrics": actual}])[0] == expected["rates"]


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


def _v2_models():
    """真正v2原物2件を同compilerへ供給し現在v3と混同しない。"""
    import hashlib

    origin = json.loads((FEATURE / "primitive-cases.candidate.json").read_text())[
        "current_v3_bf_followup"
    ]["immutable_v2"]
    result = []
    for name in ("play-export.model.json", "stats.model.json"):
        path = "backend/domain/" + name
        raw = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", origin["revision"] + ":" + path]
        )
        assert hashlib.sha256(raw).hexdigest() == origin["paths"][path]
        result.append(json.loads(raw))
    return tuple(result)


def test_v2_targets_are_reproducible_without_contract_input(v2_bundle):
    """真正v2八対象の全byteを同compiler出力と比較し歴史原値を保つ。"""
    assert len(v2_bundle) == 8
    assert generate_primitive_bundle(*_v2_models()) == v2_bundle
    origin = json.loads((FEATURE / "primitive-cases.candidate.json").read_text())[
        "current_v3_bf_followup"
    ]["immutable_v2"]
    for path, content in v2_bundle.items():
        assert (
            subprocess.check_output(
                ["git", "-C", str(ROOT), "show", origin["revision"] + ":" + path]
            ).decode()
            == content
        )


def test_v2_ratio_has_no_float_or_global_digit_limit(
    v2_python, v2_node, record_property
):
    """5001桁の実十分統計から同じexact2を出し、global上限は変更しない。"""
    import sys

    before = sys.get_int_max_str_digits()
    known = {
        key: "0"
        for key in _v2_models()[0]["calculations"][0]["typedProgram"]["metrics"]
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


@pytest.fixture(scope="module")
def v3_bundle():
    """現在v3だけから公式八対象を生成する。"""
    return generate_primitive_bundle(
        _load_model("play-export.model.json"), _load_model("stats.model.json")
    )


@pytest.fixture(scope="module")
def v3_python(v3_bundle):
    """実Python生成targetをwrapperとしてロードする。"""
    namespace = {"__name__": "__pitchlog_generated_wrapper__"}
    exec(
        compile(
            v3_bundle["backend/src/pitchlog/stats/generated/facts.py"],
            "<v3-generated>",
            "exec",
        ),
        namespace,
    )
    return namespace


@pytest.fixture(scope="module")
def v3_node(v3_bundle, tmp_path_factory):
    """同じNode driverでv3実targetを実行する。"""
    return _node_api_from_bundle(v3_bundle, tmp_path_factory)


def _v3_cases():
    """受理済み期待だけを読み、model生成へは渡さない。"""
    data = json.loads((FEATURE / "primitive-cases.candidate.json").read_text())[
        "current_v3_bf_followup"
    ]
    return [*data["regression_cases"], *data["cases"], *data["rejection_cases"]]


@pytest.mark.parametrize("case", _v3_cases(), ids=lambda c: c["case_id"])
def test_v3_all_full_primitive_pa_credit_and_ops(case, v3_python, v3_node):
    """旧26/PA/全credit/OPSとBF追加の全148独立期待を同じ比較器で検査する。"""
    test_current_v2_all_primitive_pa_credit_and_derived_values(case, v3_python, v3_node)
    if (
        case["expected"]["status"] != "available"
        or case["input"]["scope"] == "t6_sufficient_statistics"
    ):
        return
    results = [v3_python["_pitchlog_generated"](e) for e in case["input"]["events"]]
    expected = case["expected"]["totals"]
    assert all(set(r["metrics"]) == set(expected) for r in results)
    for key, wanted in expected.items():
        missing = [
            r["metrics"][key]
            for r in results
            if r["metrics"][key]["state"] == "source_unavailable"
        ]
        if missing:
            actual = {k: missing[0][k] for k in ("state", "value", "display", "reason")}
        else:
            value = "0"
            for r in results:
                value = v3_python["add_counts"](value, r["metrics"][key]["value"])
            actual = {
                "state": "available",
                "value": value,
                "display": value,
                "reason": None,
            }
        assert actual == wanted


def _bf_negative_events():
    """規範no-change/refへ36の独立不正入力を作り期待値を出力採取しない。"""
    cases = _v3_cases()
    nochange = next(c for c in cases if c["case_id"] == "current-v3-bf-no-change-walk")[
        "input"
    ]["events"][0]
    verified = next(
        c for c in cases if c["case_id"] == "current-v3-bf-normative-2-0-walk"
    )["input"]["events"][0]
    changes = [
        ("pa.bf_evidence.kind", "unknown"),
        ("pa.bf_evidence.kind", True),
        ("pa.bf_evidence.extra", True),
        ("pa.bf_evidence", []),
        ("pa.bf_evidence", False),
        ("pa.bf_evidence.pa_start_source.extra", True),
        ("pa.bf_evidence.pa_start_source.kind", "unknown"),
        *[
            ("pa.bf_evidence.pa_start_source.id", v)
            for v in [
                None,
                1,
                "",
                "0",
                "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
                nochange["source"]["game_id"] + "\n",
                nochange["source"]["game_id"] + "\r",
                nochange["source"]["game_id"] + "\u2028",
            ]
        ],
        ("pa.bf_evidence.pa_start_source.id", "00000000-0000-0000-0000-000000000099"),
        ("pa.pitcher_changes", [{}]),
        ("pa.starting_pitcher_id", "00000000-0000-0000-0000-000000000099"),
    ]
    refs = [
        ("responsibility_ref.extra", True),
        ("responsibility_ref.kind", "unknown"),
        ("responsibility_ref.kind", False),
        ("responsibility_ref", []),
        *[
            ("responsibility_ref.source_event_id", v)
            for v in [
                None,
                1,
                "",
                "00000000-0000-0000-0000-000000000099",
                verified["source"]["source_event_id"] + "\n",
            ]
        ],
        *[
            ("responsibility_ref.artifact_sha256", v)
            for v in [None, 1, "a" * 63, "A" * 64, "a" * 64, "c" * 64 + "\n"]
        ],
        ("owner_field", "strikeout_pitcher_id"),
        ("owner_field", "actual_pitcher_id"),
        ("owner_id", "00000000-0000-0000-0000-000000000099"),
    ]
    result = []
    for original, rows in (
        (nochange, changes),
        (verified, [("pa.bf_evidence." + p, v) for p, v in refs]),
    ):
        for path, value in rows:
            event = copy.deepcopy(original)
            owner = event
            keys = path.split(".")
            for key in keys[:-1]:
                owner = owner[key]
            owner[keys[-1]] = value
            result.append(event)
    assert len(result) == 36
    return result


@pytest.mark.parametrize("event", _bf_negative_events())
def test_v3_independent_source_reference_negatives(event, v3_python, v3_node):
    """未知/余剰/不整合36件を拒否し、JSON値を真正資格へ読み替えない。"""
    with pytest.raises(ValueError):
        v3_python["_pitchlog_generated"](event)
    with pytest.raises(subprocess.CalledProcessError):
        v3_node([{"kind": "event", "event": event}])


def test_v3_27_projection_huge_add_and_reproducible_targets(
    v3_python, v3_node, v3_bundle
):
    """27全射影/5001桁を検査し、生成八対象を正確に再現する。"""
    import sys

    limit = sys.get_int_max_str_digits()
    large = "9" * 5001
    wanted = "1" + "0" * 5001
    assert v3_python["add_counts"](large, "1") == wanted
    assert v3_node([{"kind": "add", "left": large, "right": "1"}])[0] == wanted
    event = next(
        c for c in _v3_cases() if c["case_id"] == "current-v3-bf-no-change-walk"
    )["input"]["events"][0]
    full = v3_python["_pitchlog_generated"](event)
    assert len(full["metrics"]) == 27
    assert (
        v3_python["_pitchlog_generated"](event, list(full["metrics"]))["metrics"]
        == full["metrics"]
    )
    known = {key: large for key in full["metrics"]}
    assert (
        v3_python["derive_rates"](known)
        == v3_node([{"kind": "rates", "metrics": known}])[0]
    )
    assert sys.get_int_max_str_digits() == limit
    assert (
        generate_primitive_bundle(
            _load_model("play-export.model.json"), _load_model("stats.model.json")
        )
        == v3_bundle
    )
    for path, value in v3_bundle.items():
        assert (ROOT / path).read_text() == value
