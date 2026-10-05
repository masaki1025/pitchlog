"""ステップ79〜84の行要求差分と入力座標被覆を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _load_module(name: str, path: Path) -> Any:
    """検査器を既存の導出器と共有して読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_module(
    "check_required_set_coverage", ROOT / "scripts/check_required_set_coverage.py"
)
expander = _load_module(
    "expand_state_transition_cases", ROOT / "scripts/expand_state_transition_cases.py"
)


def _asset(name: str) -> dict[str, Any]:
    """検査対象の現行資産を読み込む。"""
    return json.loads((ROOT / "contracts/state-transition" / name).read_text(encoding="utf-8"))


def _observed_coverage(
    cases: list[dict[str, Any]], contract: dict[str, Any] | None = None
) -> set[tuple[str, str]]:
    """現行の要求と語彙でケース集合の入力座標被覆を実測する。"""
    requirements, _ = checker.deriver.derive_repository_input_coordinate_requirements(ROOT)
    active = checker.deriver.active_input_coordinate_requirements(
        requirements, {"req:FR-040": "adopted"}
    )
    vocabulary = json.loads(
        (ROOT / "contracts/vocabulary/input_vocabulary_v1.json").read_text(encoding="utf-8")
    )
    display_names = {
        entry["id"]: entry["initialDisplayName"]
        for axis in vocabulary["axes"] for entry in axis["entries"]
    }
    return checker.observed_input_coverage(
        cases, active, contract or _asset("state_transition_contract_v1.json"), display_names
    )


@pytest.mark.parametrize(
    ("step", "matrix_limit"),
    [(79, 12), (80, 19), (81, 26), (82, 33), (83, 42)],
)
def test_prior_step_coverage_matches_its_matrix_expansion(
    step: int, matrix_limit: int
) -> None:
    """各周の②を、その周までのmatrixRowsだけから再実測する。"""
    record = _asset("required_set_input_coverage_v1.json")
    entry = next(item for item in record["history"] if item["step"] == step)
    cases, _ = expander.expand_traced(
        ROOT, limit=matrix_limit, mode="coverage", operation_limit=0
    )
    assert {case["rowRef"]["layer"] for case in cases} == {"matrixRows"}
    assert _observed_coverage(cases) == {
        tuple(item) for item in entry["after"]["coverageSet"]
    }


def test_step79_row_gap_is_exact_and_sourced() -> None:
    """①の47要求・42規範行の差分5件は宣言で全件説明される。"""
    assert checker.check_row_requirements(ROOT) == (47, 42, 0)


def test_row_gap_rejects_stale_and_new_missing_entries() -> None:
    """宣言が充足済みになった場合と未充足が増えた場合を拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    declaration = _asset("required_set_coverage_declaration_v1.json")
    stale = copy.deepcopy(declaration)
    stale["uncoveredRowRequirements"][0]["partitionId"] = "safe"
    with pytest.raises(checker.RequiredSetCoverageError, match="古い未充足宣言"):
        checker.check_row_requirements(ROOT, contract, stale)
    reduced = copy.deepcopy(contract)
    reduced["matrixRows"].pop(0)
    with pytest.raises(checker.RequiredSetCoverageError, match="exact-set不一致"):
        checker.check_row_requirements(ROOT, reduced, declaration)


def test_row_gap_rejects_closed_or_unsourced_gap() -> None:
    """GAPの状態と典拠が一致しない宣言を拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    declaration = _asset("required_set_coverage_declaration_v1.json")
    for gap_id in ("GAP-01", "missing-gap"):
        mutant = copy.deepcopy(declaration)
        mutant["uncoveredRowRequirements"][0]["gapId"] = gap_id
        with pytest.raises(checker.RequiredSetCoverageError):
            checker.check_row_requirements(ROOT, contract, mutant)


def test_row_gap_rejects_resolved_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    """典拠があってもGAPがopenでなければ未充足を許可しない。"""
    original = checker._document

    def changed_document(root: Path, name: str) -> dict[str, Any]:
        document = original(root, name)
        if name == "gap_register_v1.json":
            document = copy.deepcopy(document)
            next(gap for gap in document["gaps"] if gap["gapId"] == "GAP-08")[
                "state"
            ] = "resolved"
        return document

    monkeypatch.setattr(checker, "_document", changed_document)
    with pytest.raises(checker.RequiredSetCoverageError, match="open GAP"):
        checker.check_row_requirements(ROOT)


def test_row_gap_declaration_is_fail_closed(tmp_path: Path) -> None:
    """①の宣言を読めない場合は判定を省略せず失敗する。"""
    with pytest.raises(checker.RequiredSetCoverageError, match="宣言資産を読めない"):
        checker.check_row_requirements(
            tmp_path,
            contract=_asset("state_transition_contract_v1.json"),
        )


def test_step80_input_coverage_is_preserved() -> None:
    """ステップ80の記録と対象7行の展開結果を保持する。"""
    record = _asset("required_set_input_coverage_v1.json")
    assert record["history"][0]["after"] == record["history"][1]["before"]
    assert record["history"][0]["after"]["count"] == 71
    assert record["history"][1]["after"]["count"] == 80
    cases, trace = expander.expand_traced(
        ROOT, limit=19, mode="coverage", operation_limit=0
    )
    representatives, _ = expander.expand_traced(ROOT, limit=19, operation_limit=0)
    assert cases[:19] == representatives
    assert len(cases) == 63
    assert len(cases[19:]) == 44
    target_ids = {
        "batting-result.single",
        "batting-result.double",
        "batting-result.triple",
        "batting-result.home-run",
        "batting-result.batted-out",
        "batting-result.batted-reach",
        "batting-result.foul-fly",
    }
    assert {case["rowRef"]["coordinate"]["resultId"] for case in cases[12:19]} == target_ids
    assert {
        case["rowRef"]["coordinate"]["resultId"] for case in cases[19:]
    } >= target_ids
    before = {tuple(item) for item in record["history"][1]["before"]["coverageSet"]}
    after = {tuple(item) for item in record["history"][1]["after"]["coverageSet"]}
    assert after - before == {
        ("event.perPitch.resultId", f'"{name}"')
        for name in ("単打", "二塁打", "三塁打", "本塁打", "凡打死", "凡打出塁", "ファールフライ")
    } | {
        ("state.runners", '"first-second"'),
        ("state.runners", '"loaded"'),
    }
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step81_input_coverage_is_monotone_and_matches_expansion() -> None:
    """対象7行の代表値と被覆展開が②を8要求増やす。"""
    record = _asset("required_set_input_coverage_v1.json")
    assert record["history"][1]["after"] == record["history"][2]["before"]
    before = {tuple(item) for item in record["history"][2]["before"]["coverageSet"]}
    after = {tuple(item) for item in record["history"][2]["after"]["coverageSet"]}
    assert len(after) == 88
    assert record["history"][2]["after"]["digest"] == checker._digest(after)
    assert len(after - before) == 8
    contract = _asset("state_transition_contract_v1.json")
    cases, trace = expander.expand_traced(
        ROOT, limit=26, mode="coverage", operation_limit=0
    )
    representatives, _ = expander.expand_traced(ROOT, limit=26, operation_limit=0)
    assert contract["cases"][:26] == representatives
    assert cases[:26] == representatives
    assert len(cases) == 70
    assert len(cases[26:]) == 44
    target_ids = {
        "batting-result.double-play",
        "batting-result.line-double-play",
        "batting-result.error",
        "batting-result.fielders-choice",
        "batting-result.sacrifice-bunt",
        "batting-result.sacrifice-fly",
        "batting-result.sacrifice-bunt-error",
    }
    assert {case["rowRef"]["coordinate"]["resultId"] for case in cases[19:26]} == target_ids
    assert {
        case["rowRef"]["coordinate"]["resultId"] for case in cases[26:]
    } >= target_ids
    assert after - before == {
        ("event.perPitch.resultId", f'"{name}"')
        for name in ("併殺打", "ライナー併殺", "エラー", "野手選択", "犠打", "犠飛", "犠打失策")
    } | {("state.runners", '"third"')}
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step82_secondary_results_and_input_coverage() -> None:
    """打撃結果2の7行だけを展開し、妨害裁定を該当行で被覆する。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    declaration = _asset("required_set_coverage_declaration_v1.json")
    assert checker.check_row_requirements(ROOT) == (47, 42, 0)
    secondary_requirements = [
        item
        for item in checker.deriver.derive_repository_row_requirements(ROOT)[0]
        if item.result_id.startswith("secondary-result.")
    ]
    secondary_missing = [
        item
        for item in declaration["uncoveredRowRequirements"]
        if item["vocabularyId"].startswith("secondary-result.")
    ]
    assert len(secondary_requirements) == 11
    assert len(secondary_missing) == 4
    assert {item["gapId"] for item in secondary_missing} == {"GAP-07"}

    assert [entry["step"] for entry in record["history"][:5]] == [79, 80, 81, 82, 83]
    assert record["history"][2]["after"] == record["history"][3]["before"]
    assert record["history"][3]["after"]["count"] == 100
    assert record["history"][3]["after"]["digest"] == checker._digest(
        {tuple(item) for item in record["history"][3]["after"]["coverageSet"]}
    )
    before = {tuple(item) for item in record["history"][3]["before"]["coverageSet"]}
    after = {tuple(item) for item in record["history"][3]["after"]["coverageSet"]}
    assert after - before == {
        ("event.perPitch.kind", '"secondary-result"'),
        *( ("event.perPitch.resultId", f'"{name}"') for name in (
            "PB", "WP", "守備妨害", "打撃妨害", "走塁妨害", "ボーク", "ピッチクロック違反"
        )),
        *( ("event.perPitch.interferenceRuling", f'"{value}"') for value in (
            "not-required",
            "batting:penalty-award",
            "obstruction:play-on-obstructed-runner-with-awarded-destinations",
            "offensive-interference:batter-included-with-out-targets-and-return-bases",
        )),
    }

    cases, trace = expander.expand_traced(
        ROOT, limit=33, mode="coverage", operation_limit=0
    )
    representatives, _ = expander.expand_traced(ROOT, limit=33, operation_limit=0)
    assert contract["cases"][:33] == cases[:33]
    assert cases[:33] == representatives
    assert len(cases) == 78
    assert len(cases[33:]) == 45
    secondary = contract["matrixRows"][26:33]
    assert len(secondary) == 7
    assert {case["rowRef"]["coordinate"]["resultId"] for case in cases[26:33]} == {
        row["resultId"] for row in secondary
    }
    for case in cases:
        ruling = case["inputCoordinate"].get("event.perPitch.interferenceRuling")
        if ruling is not None and ruling != "not-required":
            predicate_axes = expander.representative_selection.predicate_axes(
                case["rowRef"]["coordinate"]["precondition"]
            )
            assert "event.perPitch.interferenceRuling" in predicate_axes
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step83_runner_events_and_input_coverage() -> None:
    """走者イベント9行を展開し、規範行と整合する走者結果だけを被覆する。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    declaration = _asset("required_set_coverage_declaration_v1.json")
    assert checker.check_row_requirements(ROOT) == (47, 42, 0)
    runner_requirements = [
        item
        for item in checker.deriver.derive_repository_row_requirements(ROOT)[0]
        if item.result_id.startswith(("strategy-category.", "pitcher-pickoff-destination.",
                                      "catcher-pickoff-destination."))
    ]
    assert len(runner_requirements) == 9
    assert not any(
        item["vocabularyId"].startswith(("strategy-category.",
                                            "pitcher-pickoff-destination.",
                                            "catcher-pickoff-destination."))
        for item in declaration["uncoveredRowRequirements"]
    )

    cases, trace = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=0
    )
    representatives, _ = expander.expand_traced(ROOT, limit=42, operation_limit=0)
    assert contract["cases"][:len(cases)] == cases
    assert cases[:42] == representatives
    assert len(cases) == 89
    assert len(cases[42:]) == 47
    assert sum(
        case["rowRef"]["coordinate"]["eventKind"] == "runner-event"
        for case in cases[42:]
    ) == 9
    runner_rows = contract["matrixRows"][33:]
    assert len(runner_rows) == 9
    assert {case["rowRef"]["coordinate"]["resultId"] for case in cases[33:42]} == {
        row["resultId"] for row in runner_rows
    }
    payload_cases = [
        case for case in cases[42:]
        if "event.perPitch.runnerEventPayload" in case["inputCoordinate"]
    ]
    assert {
        (case["rowRef"]["coordinate"]["resultId"],
         case["inputCoordinate"]["event.perPitch.runnerEventPayload"])
        for case in payload_cases
    } == {
        ("strategy-category.steal", "single-runner-safe-advance"),
        ("strategy-category.bunt", "single-runner-hold"),
    }
    for case in payload_cases:
        row = next(
            row for row in runner_rows
            if row["resultId"] == case["rowRef"]["coordinate"]["resultId"]
        )
        advance = row["runnerDefaultAdvance"]["first"]
        if case["inputCoordinate"]["event.perPitch.runnerEventPayload"] == "single-runner-hold":
            assert advance["modality"] == "hold"
        else:
            assert advance == {"modality": "optional", "destination": 2}

    assert record["history"][3]["after"] == record["history"][4]["before"]
    before = {tuple(item) for item in record["history"][4]["before"]["coverageSet"]}
    after = {tuple(item) for item in record["history"][4]["after"]["coverageSet"]}
    assert after - before == {
        ("event.perPitch.kind", '"runner-event"'),
        ("state.runners", '"second"'),
        ("event.perPitch.runnerEventPayload", '"single-runner-safe-advance"'),
        ("event.perPitch.runnerEventPayload", '"single-runner-hold"'),
    }
    assert _observed_coverage(cases) == after
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step84_substitution_cases_and_input_coverage() -> None:
    """選手交代の2行と②の増分2件を現行ケースから実測する。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    cases, trace = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=2
    )
    representatives, _ = expander.expand_traced(
        ROOT, limit=42, operation_limit=2
    )
    assert contract["cases"] == cases
    assert len(cases) == 91
    assert len(representatives) == 44
    assert [case["rowRef"]["layer"] for case in cases].count("matrixRows") == 89
    operation_cases = [
        case for case in cases if case["rowRef"]["layer"] == "operationRows"
    ]
    assert operation_cases == representatives[-2:]
    assert len(operation_cases) == 2
    assert {case["inputCoordinate"]["state.gameEnded"] for case in operation_cases} == {
        False, True
    }
    for case in operation_cases:
        assert case["caseId"].startswith("ST-OPERATION-")
        assert case["rowRef"]["coordinate"]["operationKind"] == "substitution"
        assert case["inputCoordinate"]["operationKind"] == "substitution"
        assert case["inputCoordinate"]["event.operationPayload"] == "substitution"
        assert case["expected"]["clauseId"] == "FR-011"

    assert record["currentStep"] == 84
    assert [entry["step"] for entry in record["history"]] == list(range(79, 85))
    previous = record["history"][-2]["after"]
    current = record["history"][-1]
    assert previous["count"] == 104
    assert current["before"] == previous
    before = {tuple(item) for item in current["before"]["coverageSet"]}
    after = {tuple(item) for item in current["after"]["coverageSet"]}
    assert before <= after
    assert after - before == {
        ("event.operationKind", '"substitution"'),
        ("event.operationPayload", '"substitution"'),
    }
    assert len(after) == current["after"]["count"] == 106
    assert _observed_coverage(cases) == after
    assert checker.check_input_coverage(ROOT) == (106, checker._digest(after), 2)
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("kind", "ケースの操作またはpayloadタグ"),
        ("payload", "ケースの操作またはpayloadタグ"),
        ("unknown-layer", "ケースの行参照層"),
        ("ambiguous-reference", "ケースが規範行を一意に参照しない"),
        ("expected", "ケースの期待値が規範行と不一致"),
    ],
)
def test_checker_rejects_invalid_operation_cases(mutation: str, message: str) -> None:
    """操作行の層・タグ・参照・期待値の破損を拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    changed = copy.deepcopy(contract["cases"][-1])
    if mutation == "kind":
        changed["inputCoordinate"]["operationKind"] = "undo"
    elif mutation == "payload":
        changed["inputCoordinate"]["event.operationPayload"] = "undo"
    elif mutation == "unknown-layer":
        changed["rowRef"]["layer"] = "undoRows"
    elif mutation == "ambiguous-reference":
        del changed["rowRef"]["coordinate"]["precondition"]
    else:
        changed["expected"]["operationResult"] = "applied"
    with pytest.raises(checker.RequiredSetCoverageError, match=message):
        _observed_coverage([changed])


def test_matrix_observation_keeps_its_per_pitch_assignment() -> None:
    """matrixRowsでは操作タグ風の追加値を被覆に算入せず、イベント不一致は拒否する。"""
    matrix_case = copy.deepcopy(_asset("state_transition_contract_v1.json")["cases"][0])
    baseline = _observed_coverage([matrix_case])
    matrix_case["inputCoordinate"]["operationKind"] = "substitution"
    matrix_case["inputCoordinate"]["event.operationPayload"] = "substitution"
    assert _observed_coverage([matrix_case]) == baseline
    matrix_case["inputCoordinate"]["eventKind"] = "runner-event"
    with pytest.raises(checker.RequiredSetCoverageError, match="ケースのイベントが規範行と不一致"):
        _observed_coverage([matrix_case])


def test_checker_rejects_operation_row_without_payload_shape() -> None:
    """操作行のpayloadShapeが消えた場合は②を観測しない。"""
    contract = _asset("state_transition_contract_v1.json")
    case = copy.deepcopy(contract["cases"][-1])
    del case["rowRef"]["coordinate"]["payloadShape"]
    del contract["operationRows"][1]["payloadShape"]
    with pytest.raises(
        checker.RequiredSetCoverageError,
        match="ケースの操作またはpayloadタグが規範行と不一致",
    ):
        _observed_coverage([case], contract)


@pytest.mark.parametrize("operation_limit", [-1, 7])
def test_expander_rejects_operation_limit_outside_references(operation_limit: int) -> None:
    """操作行の参照件数を越える指定と負数を拒否する。"""
    with pytest.raises(expander.CaseExpansionError, match="操作行の出力件数"):
        expander.expand_traced(ROOT, limit=42, operation_limit=operation_limit)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing-operation-rows", "操作の規範行がない"),
        ("missing-payload-axis", "操作payload軸がない"),
        ("missing-payload-tags", "操作payloadのタグ宣言がない"),
        ("missing-row", "操作行参照が規範行を一意に指していない"),
        ("ambiguous-reference", "操作行参照が規範行を一意に指していない"),
        ("missing-tag", "操作種別に対応するpayloadタグがない"),
        ("invalid-coordinate", "操作行の入力座標が不正"),
        ("invalid-predicate", "操作行の事前条件が述語でない"),
    ],
)
def test_expander_rejects_invalid_operation_inputs(
    monkeypatch: pytest.MonkeyPatch, mutation: str, message: str
) -> None:
    """操作行の規範行・行参照・タグ・前提条件の破損を拒否する。"""
    original = expander._read_document

    def changed_document(root: Path, relative: Any) -> dict[str, Any]:
        document = original(root, relative)
        if (
            mutation in {"missing-payload-axis", "missing-payload-tags", "missing-tag"}
            and "stateTransitionAxes" in document
        ):
            document = copy.deepcopy(document)
            payload_axis = next(
                axis for axis in document["stateTransitionAxes"]
                if axis["axisId"] == "event.operationPayload"
            )
            if mutation == "missing-payload-axis":
                document["stateTransitionAxes"].remove(payload_axis)
            elif mutation == "missing-payload-tags":
                del payload_axis["representationCapability"]["variantTags"]
            else:
                payload_axis["representationCapability"]["variantTags"].remove("substitution")
        elif "matrixRows" in document:
            document = copy.deepcopy(document)
            if mutation == "missing-operation-rows":
                del document["operationRows"]
            elif mutation == "missing-row":
                document["operationRows"].pop(0)
            elif mutation == "ambiguous-reference":
                reference = next(
                    ref
                    for mapping in document["mustOperationCoverage"]["mappings"]
                    for ref in mapping["rowRefs"]
                    if ref["layer"] == "operationRows"
                )
                del reference["coordinate"]["precondition"]
            elif mutation == "invalid-coordinate":
                reference = next(
                    ref
                    for mapping in document["mustOperationCoverage"]["mappings"]
                    for ref in mapping["rowRefs"]
                    if ref["layer"] == "operationRows"
                )
                reference["coordinate"] = None
            elif mutation == "invalid-predicate":
                reference = next(
                    ref
                    for mapping in document["mustOperationCoverage"]["mappings"]
                    for ref in mapping["rowRefs"]
                    if ref["layer"] == "operationRows"
                )
                reference["coordinate"]["precondition"] = None
                document["operationRows"][0]["precondition"] = None
        return document

    monkeypatch.setattr(expander, "_read_document", changed_document)
    with pytest.raises(expander.CaseExpansionError, match=message):
        expander.expand_traced(ROOT, limit=42, operation_limit=1)


def test_row_binding_declaration_controls_coverage_and_checks_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """行束縛の例外を資産から読み、根拠IDの不整合を拒否する。"""
    original = expander._read_document
    replacement: dict[str, Any] = {}

    def changed_document(root: Path, relative: Any) -> dict[str, Any]:
        document = original(root, relative)
        if "rowBoundAxes" in document:
            document = copy.deepcopy(document)
            document["rowBoundAxes"][0].update(replacement)
        return document

    monkeypatch.setattr(expander, "_read_document", changed_document)
    replacement = {"unboundValues": []}
    cases, _ = expander.expand_traced(ROOT, limit=33, mode="coverage")
    assert len(cases) == 77
    assert not any(
        case["inputCoordinate"].get("event.perPitch.interferenceRuling") == "not-required"
        for case in cases
    )
    replacement = {"sourceClauseIds": ["req:unknown"]}
    with pytest.raises(expander.CaseExpansionError, match="根拠がdescriptorと不一致"):
        expander.expand_traced(ROOT, limit=33, mode="coverage")


def test_input_coverage_rejects_regression_and_digest_change() -> None:
    """②の後退・件数やdigestの改ざんを拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    regressed = copy.deepcopy(record)
    regressed["history"][0]["after"]["coverageSet"] = []
    with pytest.raises(checker.RequiredSetCoverageError):
        checker.check_input_coverage(ROOT, contract, regressed)
    wrong_digest = copy.deepcopy(record)
    wrong_digest["history"][0]["after"]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(checker.RequiredSetCoverageError, match="digest"):
        checker.check_input_coverage(ROOT, contract, wrong_digest)


def test_coverage_history_is_append_only() -> None:
    """承認履歴の既存行の書換えと一度に複数行の追加を拒否する。"""
    current = _asset("required_set_input_coverage_v1.json")
    rewritten = copy.deepcopy(current)
    rewritten["history"][0]["reason"] = "書き換え"
    with pytest.raises(checker.RequiredSetCoverageError, match="追記のみでない"):
        checker._check_history_append_only(current, rewritten)
    multiple = copy.deepcopy(current)
    multiple["history"].extend([copy.deepcopy(current["history"][0])] * 2)
    with pytest.raises(checker.RequiredSetCoverageError, match="複数"):
        checker._check_history_append_only(current, multiple)
