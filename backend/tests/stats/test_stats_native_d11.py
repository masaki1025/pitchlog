"""native27の有限D11を独立規範・実生成Python/TSの全fieldへ接続する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domaincheck.collect_layers import (
    StageExpectation,
    TargetExpectation,
    collect_pytest_junit,
)
from pitchlog.domaincheck.runners import stats_native as runner

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = runner.read_json(ROOT, runner.MANIFEST)
CALC = MANIFEST["calculations"][0]
VECTORS = runner.read_json(ROOT, CALC["vectors"][0]["path"])


@pytest.fixture(scope="module")
def actual_ts(tmp_path_factory):
    """期待値を一切渡さず全27生入力だけを実TSへ渡す。"""
    requests = [case["request"] for case in VECTORS["cases"]]
    results = runner.execute_typescript(
        ROOT, requests, tmp_path_factory.mktemp("d11-ts")
    )
    assert len(results) == len(requests) == 27
    return {
        case["caseId"]: value
        for case, value in zip(VECTORS["cases"], results, strict=True)
    }


def _record(record_property, case, direct, target, kind):
    """全生出力と実hashを既JUnit収集器の固定契約へ記録する。"""
    actual = runner.execute_python(case["request"])
    expected = case["expected"]["expected"]
    assert runner.full_values_match(
        CALC["calculation"], case["caseId"], expected, actual, direct
    )
    if kind == "invariant":
        assert set(actual) == {
            "metrics",
            "pa_row",
            "decisions",
            "selected",
            "source_event_id",
        }
        assert len(actual["metrics"]) == 27
        assert type(actual["selected"]) is bool
        for value in actual["metrics"].values():
            assert set(value) == {"state", "value", "display", "reason", "credits"}
            if value["state"] == "available":
                assert type(value["value"]) is str and value["value"].isdigit()
                assert value["display"] == value["value"] and value["reason"] is None
                assert sum(int(c["quantity"]) for c in value["credits"]) == int(
                    value["value"]
                )
            else:
                assert value["state"] == "source_unavailable"
                assert value["value"] is value["display"] is None
                assert value["credits"] == []
    trace = {
        "vector": CALC["vectors"][0]["vectorId"],
        "case": case["caseId"],
        "entrypointId": CALC["entrypoints"][0]["entrypointId"],
        "directTargetId": target["directTargetId"],
        "expected": expected,
        "entrypointOutput": actual,
        "directTargetOutput": direct,
        "artifactHashes": {"single": target["hash"]},
        "issuedSqlOrAst": None,
        "stageIO": [],
    }
    for key, value in {
        "calculation": CALC["calculation"],
        "propertyId": CALC["calculation"] + "-" + kind,
        "propertyKind": kind,
        "generatedCases": 1,
        "status": "passed",
        "trace": trace,
    }.items():
        record_property(key, json.dumps(value) if isinstance(value, dict) else value)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["caseId"])
@pytest.mark.parametrize("target_index", [0, 1])
@pytest.mark.parametrize("kind", ["invariant", "equivalence"])
def test_d11_evidence_all_fields_credits_pa_and_display(
    case,
    target_index,
    kind,
    actual_ts,
    record_property,
):
    """全27×全field・帰属・PA・状態・表示を丸め/無視なしで比較する。"""
    target = CALC["directTargets"][target_index]
    direct = (
        runner.execute_python(case["request"])
        if target_index == 0
        else actual_ts[case["caseId"]]
    )
    _record(record_property, case, direct, target, kind)


def test_d11_registration_and_all_legacy_current_normative_references():
    """別manifestを共通CLI schemaへ通し、元55/現75を変更/黙示削減しない。"""
    assert runner.validate_registration(ROOT) == MANIFEST
    original = runner.read_json(ROOT, runner.SOURCE_CASES)
    assert len(original["cases"]) == 55
    assert len(original["current_v2_followup"]["regression_cases"]) == 55
    assert len(original["current_v2_followup"]["cases"]) == 20
    used = {c["caseId"] for c in VECTORS["cases"]}
    remaining = set(VECTORS["notDeclaredAsExecutedHere"])
    assert not used & remaining
    assert used | remaining == set(VECTORS["sourceReferences"]["currentCaseIds"])
    # 残りは既test_primitive_facts.pyの旧55/現75比較で引き続き必須。
    # source fixtureの拒否を、本物SQL資格や本native子計算の成功には数えない。


def test_d11_v3_keeps_every_historical_v2_expected_field():
    """旧v2の全期待を保存し、新v3はBF一欄だけを明示追加する。"""
    old_alpha = runner.read_json(ROOT, "contracts/stats/native_event_facts_d11_v2.json")
    old_beta = runner.read_json(
        ROOT, "contracts/stats/native_current_totals_d11_v2.json"
    )
    new_alpha = VECTORS
    new_beta = runner.read_json(ROOT, MANIFEST["calculations"][1]["vectors"][0]["path"])
    assert [case["caseId"] for case in old_alpha["cases"]] == [
        case["caseId"] for case in new_alpha["cases"]
    ]
    for before, after in zip(old_alpha["cases"], new_alpha["cases"], strict=True):
        assert before["request"] == after["request"]
        old_expected = before["expected"]["expected"]
        new_expected = copy.deepcopy(after["expected"]["expected"])
        assert set(new_expected["metrics"]) == set(old_expected["metrics"]) | {
            "batters_faced"
        }
        del new_expected["metrics"]["batters_faced"]
        assert new_expected == old_expected
    old_case = old_beta["cases"][0]
    new_case = new_beta["cases"][0]
    assert old_case["request"] == new_case["request"]
    old_rows = old_case["expected"]["expected"]
    new_rows = new_case["expected"]["expected"]
    assert [r for r in new_rows if r["metric_id"] != "batters_faced"] == old_rows
    assert [r for r in new_rows if r["metric_id"] == "batters_faced"] == [
        {
            "metric_id": "batters_faced",
            "state": "available",
            "value": "0",
            "display": "0",
        }
    ]


@pytest.mark.parametrize(
    "mutation", ["sql", "target", "property", "entrypoint", "case", "formatter"]
)
def test_d11_mutable_declaration_cannot_reduce_required_surface(monkeypatch, mutation):
    """自己宣言の削減・未使用formatterへの付替えで全検査を成立させない。"""
    read = runner.read_json

    def mutated(root, path):
        value = copy.deepcopy(read(root, path))
        if path == runner.MANIFEST:
            if mutation == "sql":
                value["calculations"].pop()
            elif mutation == "target":
                value["calculations"][0]["directTargets"].pop()
            elif mutation == "property":
                value["calculations"][0]["properties"].pop()
            elif mutation == "entrypoint":
                value["calculations"][0]["entrypoints"][0]["symbol"] = "missing"
            elif mutation == "formatter":
                calc = value["calculations"][1]
                calc["directTargets"][0]["components"][2]["hash"] = "sha256:" + "0" * 64
        elif path == CALC["vectors"][0]["path"] and mutation == "case":
            value["cases"] = value["cases"][:1]
        return value

    monkeypatch.setattr(runner, "read_json", mutated)
    with pytest.raises(ValueError):
        runner.validate_registration(ROOT)


@pytest.mark.parametrize("link", ["receiver", "formatter", "direct", "entrypoint"])
def test_d11_every_stage_link_distinguishes_integer_zero_from_false(link):
    """全段間・両終端の型連鎖を確認し、SQL実行証拠とは区別する。"""
    calc = MANIFEST["calculations"][1]
    target = calc["directTargets"][0]
    trace = {
        "artifactHashes": {p["stage"]: p["hash"] for p in target["components"]},
        "directTargetOutput": [0],
        "entrypointOutput": [0],
        "stageIO": [
            {
                "stage": part["stage"],
                "artifactHash": part["hash"],
                "input": [0],
                "output": [0],
            }
            for part in target["components"]
        ],
    }
    runner.validate_stage_trace(trace, calc["calculation"], target)
    if link == "receiver":
        trace["stageIO"][1]["input"] = [False]
    elif link == "formatter":
        trace["stageIO"][2]["input"] = [False]
    elif link == "direct":
        trace["directTargetOutput"] = [False]
    else:
        trace["entrypointOutput"] = [False]
    with pytest.raises(ValueError):
        runner.validate_stage_trace(trace, calc["calculation"], target)


@pytest.mark.parametrize(
    "mutation",
    ["value", "display", "credit", "state", "extra", "missing", "selected-type"],
)
def test_d11_full_comparison_refuses_each_output_surface_mutation(mutation):
    """field無視/部分一致で全比較を緩めない。"""
    case = next(
        c for c in VECTORS["cases"] if c["caseId"].endswith("incomplete-pa-one-pitch")
    )
    actual = runner.execute_python(case["request"])
    bad = copy.deepcopy(actual)
    if mutation == "value":
        bad["metrics"]["pitch_count"]["value"] = "2"
    elif mutation == "display":
        bad["metrics"]["pitch_count"]["display"] = "0"
    elif mutation == "credit":
        bad["metrics"]["pitch_count"]["credits"] = []
    elif mutation == "state":
        bad["metrics"]["pitch_count"]["state"] = "source_unavailable"
    elif mutation == "selected-type":
        bad["selected"] = 1
    elif mutation == "extra":
        bad["extra"] = True
    else:
        del bad["pa_row"]
    with pytest.raises(AssertionError):
        _record(lambda *a: None, case, bad, CALC["directTargets"][0], "invariant")


def test_d11_stage_links_and_same_file_formatter_are_not_metadata_only():
    """実receiver/formatterを呼び、型付き0/null/巨大数・全段改変を検査する。"""
    calc = MANIFEST["calculations"][1]
    target = calc["directTargets"][0]
    rows, calls = runner.receiver_formatter_rows(
        [
            ("pitch_count", "available", 0),
            ("runs", "source_unavailable", None),
            ("h", "available", "9007199254740993"),
        ]
    )
    assert [r["display"] for r in rows] == ["0", None, "9007199254740993"]
    assert any(c["event"] == "call" and c["input"] is None for c in calls)
    assert any(
        c["event"] == "return" and c["output"] == "9007199254740993" for c in calls
    )
    stages = target["components"]
    hashes = {s["stage"]: s["hash"] for s in stages}
    trace = {
        "artifactHashes": hashes,
        "directTargetOutput": rows,
        "entrypointOutput": rows,
        "stageIO": [
            {
                "stage": "sql",
                "artifactHash": hashes["sql"],
                "input": None,
                "output": rows,
            },
            {
                "stage": "typed-receiver",
                "artifactHash": hashes["typed-receiver"],
                "input": rows,
                "output": rows,
            },
            {
                "stage": "formatter",
                "artifactHash": hashes["formatter"],
                "input": rows,
                "output": rows,
            },
        ],
    }
    # この純例は収集器の対向だけ。SQLを実行したD11証跡には記録しない。
    runner.validate_stage_trace(trace, calc["calculation"], target)
    for index in range(3):
        bad = copy.deepcopy(trace)
        bad["stageIO"][index]["artifactHash"] = "sha256:" + "0" * 64
        with pytest.raises(ValueError):
            runner.validate_stage_trace(bad, calc["calculation"], target)
    bad = copy.deepcopy(trace)
    bad["stageIO"][1]["input"] = []
    with pytest.raises(ValueError):
        runner.validate_stage_trace(bad, calc["calculation"], target)


def test_d11_existing_collector_rejects_zero_and_incomplete_documents(tmp_path):
    """正規JUnitの収集口を使用し、未実行を成功にしない。"""
    target = CALC["directTargets"][0]
    expectations = {
        (CALC["calculation"], target["directTargetId"]): TargetExpectation(
            CALC["calculation"],
            target["directTargetId"],
            "single",
            (StageExpectation("single", target["hash"]),),
        )
    }
    path = tmp_path / "empty.xml"
    path.write_text('<testsuites name="pytest"><testsuite name="pytest"/></testsuites>')
    assert not collect_pytest_junit(path, expectations).complete


@pytest.mark.parametrize("metric_index", range(26))
def test_d11_existing_non_equivalent_generated_quantity_mutations(metric_index):
    """旧26数量式の変異killを保持し、新BFは別の対向で検証する。"""
    import importlib.util

    path = ROOT / "backend/tests/stats/test_basic_stats.py"
    spec = importlib.util.spec_from_file_location("stats_d11_existing_mutations", path)
    assert spec is not None and spec.loader is not None
    existing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(existing)
    existing.test_each_metric_non_equivalent_quantity_mutation_is_killed(metric_index)


def test_d11_non_equivalent_generated_formatter_mutation_is_killed(monkeypatch):
    """実生成formatterの戻りを変える非等価変異を実adapterで検出する。"""
    from pitchlog.stats.generated import receiver

    source = (ROOT / "backend/src/pitchlog/stats/generated/receiver.py").read_text()
    anchor = (
        '    return groups[-1] + "".join((group.zfill(9) '
        "for group in reversed(groups[:-1])))"
    )
    assert source.count(anchor) == 1
    namespace = {}
    exec(
        compile(source.replace(anchor, '    return "0"'), "<mutant-receiver>", "exec"),
        namespace,
    )
    with monkeypatch.context() as patch:
        patch.setattr(receiver, "format_count", namespace["format_count"])
        actual, _ = runner.receiver_formatter_rows([("pitch_count", "available", 3)])
    assert actual != [
        {"metric_id": "pitch_count", "state": "available", "value": "3", "display": "3"}
    ]


def test_d11_collector_does_not_accept_skipped_real_sql_as_complete(tmp_path):
    """実SQL未実行を、pytest skipのgreenで成立扱いにしない。"""
    path = tmp_path / "skipped.xml"
    path.write_text(
        '<testsuites name="pytest"><testsuite name="pytest">'
        '<testcase name="test_d11_evidence_real_sql"><skipped/>'
        "</testcase></testsuite></testsuites>"
    )
    with pytest.raises(ValueError, match="skip/未完/失敗"):
        runner.collect_execution_evidence(ROOT, path)


@pytest.mark.parametrize("side", ["expected", "entrypoint", "direct"])
@pytest.mark.parametrize("mutation", ["bool-int", "extra-null", "missing-null"])
def test_d11_canonical_carrier_keeps_all_fields_and_types_in_both_directions(
    side, mutation
):
    """carrier化前にfieldを絞らず、期待側/両実装側の逆対向も拒否する。"""
    original: dict[str, object] = {
        "selected": True,
        "pa_row": None,
        "display": "0",
        "nested": {"x": [None, False]},
    }
    values = {
        key: copy.deepcopy(original) for key in ("expected", "entrypoint", "direct")
    }
    if mutation == "bool-int":
        values[side]["selected"] = 1
    elif mutation == "extra-null":
        values[side]["extra"] = None
    else:
        del values[side]["pa_row"]
    assert not runner.full_values_match(
        CALC["calculation"],
        "canonicalCarrier",
        values["expected"],
        values["entrypoint"],
        values["direct"],
    )


def test_d11_sql_adapter_uses_fixed_producer_and_propagates_real_execution_failure():
    """SQL未実行の失敗対向。任意SQLや成功stubで実PG成立を代用しない。"""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql.psycopg import dialect

    from pitchlog.authz.stats_primitive_sql import _verified_inputs

    _, sections, _, _ = _verified_inputs(ROOT)
    compiled = text(sections["current_totals"]).compile(
        dialect=dialect(paramstyle="pyformat")
    )
    parameters = {key: None for key in compiled.params}

    class StopAtExecution:
        """SQL/全bindだけを観測し、成功結果を絶対に返さない。"""

        def __init__(self):
            self.calls = []

        def execute(self, statement, values):
            self.calls.append((statement, values))
            raise RuntimeError("explicit no-DB stop")

    failing = StopAtExecution()
    with pytest.raises(RuntimeError, match="explicit no-DB stop"):
        runner.execute_sql_composite(failing, parameters, root=ROOT)
    assert failing.calls == [(str(compiled), parameters)]
    for invalid in ({}, {**parameters, "tenant_override": "forbidden"}):
        before = len(failing.calls)
        with pytest.raises(ValueError, match="全bind集合"):
            runner.execute_sql_composite(failing, invalid, root=ROOT)
        assert len(failing.calls) == before


@pytest.mark.parametrize("mutation", ["missing", "extra-category", "extra-game-types"])
def test_d11_sql_adapter_rejects_wrong_bind_surface_before_execution(mutation):
    """単一試合の固定SQLへ別集計の引数を混ぜず、欠落も実行前に拒否する。"""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql.psycopg import dialect

    from pitchlog.authz.stats_primitive_sql import _verified_inputs

    _, sections, _, _ = _verified_inputs(ROOT)
    compiled = text(sections["current_totals"]).compile(
        dialect=dialect(paramstyle="pyformat")
    )
    assert set(compiled.params) == {
        "tenant_id",
        "game_id",
        "player_id",
        "model_sha256",
        "fact_version_id",
        "revision",
        "source_set_sha256",
    }
    parameters = dict.fromkeys(compiled.params)
    if mutation == "missing":
        del parameters["revision"]
    elif mutation == "extra-category":
        parameters["named_category"] = "all"
    else:
        parameters["raw_game_type_keys"] = []

    class NoExecution:
        """引数拒否の後にSQLへ到達すれば失敗する。"""

        def execute(self, *args):
            pytest.fail("invalid bindings reached SQL")

    with pytest.raises(ValueError, match="全bind集合"):
        runner.execute_sql_composite(NoExecution(), parameters, root=ROOT)
