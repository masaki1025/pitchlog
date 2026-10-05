"""ステップ79〜88の行要求差分と入力座標被覆を検証する。"""

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


def _unreferenced_normative_rows(
    contract: dict[str, Any], schema: dict[str, Any]
) -> list[dict[str, Any]]:
    """各規範行を入力座標で同定し、caseから未参照の行を返す。

    Args:
        contract: 状況判定または終了判定の契約。
        schema: 対応する契約schema。

    Returns:
        caseから参照されない規範行の参照一覧。
    """
    def key(reference: dict[str, Any]) -> str:
        return json.dumps(reference, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    referenced = {key(case["rowRef"]) for case in contract["cases"]}
    missing = []
    for layer in ("matrixRows", "operationRows", "undoRows", "decisionRows"):
        if layer not in contract:
            continue
        fields = (
            ("branchId",)
            if layer == "decisionRows"
            else schema["properties"][layer]["x-pitchlog-input-coordinate-fields"]
        )
        for row in contract[layer]:
            reference = {
                "layer": layer,
                "coordinate": {field: row[field] for field in fields},
            }
            if key(reference) not in referenced:
                missing.append(reference)
    return missing


def _assert_all_normative_rows_referenced(
    contract: dict[str, Any], schema: dict[str, Any]
) -> None:
    """未参照の規範行が1行でもあれば全行参照違反として失敗させる。"""
    missing = _unreferenced_normative_rows(contract, schema)
    assert not missing, f"全行参照違反: {missing!r}"


def test_step98_all_normative_rows_are_referenced_by_cases() -> None:
    """実資産の4層54行すべてにcaseからの参照があることを確認する。"""
    state = _asset("state_transition_contract_v1.json")
    game_end = _asset("game_end_contract_v1.json")
    assert [len(state[layer]) for layer in ("matrixRows", "operationRows", "undoRows")] == [
        42, 6, 1,
    ]
    assert len(game_end["decisionRows"]) == 5
    assert len(state["cases"]) == 96
    assert len(game_end["cases"]) == 170
    for contract, schema_name in (
        (state, "state_transition_contract_schema_v1.json"),
        (game_end, "game_end_contract_schema_v1.json"),
    ):
        _assert_all_normative_rows_referenced(contract, _asset(schema_name))


@pytest.mark.parametrize("layer", ["matrixRows", "operationRows", "undoRows", "decisionRows"])
def test_step98_unreferenced_row_is_red_without_other_checks(layer: str) -> None:
    """件数を維持した参照差し替えを全行参照の述語だけで拒否する。"""
    game_end = layer == "decisionRows"
    contract = _asset(
        "game_end_contract_v1.json" if game_end else "state_transition_contract_v1.json"
    )
    schema = _asset(
        "game_end_contract_schema_v1.json"
        if game_end else "state_transition_contract_schema_v1.json"
    )
    target = next(case["rowRef"] for case in contract["cases"] if case["rowRef"]["layer"] == layer)
    replacement = next(case["rowRef"] for case in contract["cases"] if case["rowRef"] != target)
    original_count = len(contract["cases"])
    for case in contract["cases"]:
        if case["rowRef"] == target:
            case["rowRef"] = copy.deepcopy(replacement)

    assert len(contract["cases"]) == original_count
    assert _unreferenced_normative_rows(contract, schema) == [target]
    with pytest.raises(AssertionError, match="全行参照違反"):
        _assert_all_normative_rows_referenced(contract, schema)


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


def _assert_no_tiebreak_start_row(contract: dict[str, Any]) -> None:
    """ステップ62の裁定に反する操作行がないことを確認する。"""
    assert not any(
        row["operationKind"] == "tiebreak-start"
        for row in contract["operationRows"]
    ), "tiebreak-startの規範行が現れた"


def test_step94_game_end_declaration_and_direct_coverage() -> None:
    """終了判定の除外集合とステップ93・94の被覆記録を実測で照合する。"""
    assert checker.check_game_end_coverage(ROOT) == {
        "total": 3844, "reachable": 1015, "unreachable": 2817,
        "invalid": 12, "covered": 1015, "cases": 170,
    }
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    before, _, _, _ = checker._game_end_measure(
        ROOT, {**contract, "cases": contract["cases"][:4]}, declaration
    )
    assert before["covered"] == 51
    record = _asset("game_end_input_coverage_v1.json")
    assert [item["step"] for item in record["history"]] == [93, 94]
    assert record["history"][0]["after"] == record["history"][1]["before"]
    assert record["history"][0]["after"]["coveredCount"] == 763
    assert record["history"][1]["after"]["coveredCount"] == 1015


def test_step95_decision_properties_hold_for_all_cases() -> None:
    """全170ケースの自動遷移なし・分岐別出力・X表記の不在を宣言と照合する。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    properties = declaration["step95DecisionProperties"]
    automatic = properties["automaticTransition"]
    branches = {
        branch["branchId"]: branch for branch in properties["branchExpectations"]
    }
    x_mark = properties["xMark"]
    assert len(contract["cases"]) == 170
    assert automatic["field"] == "automaticallyEndsGame"
    assert automatic["expected"] is False
    assert set(branches) == {row["branchId"] for row in contract["decisionRows"]}
    assert x_mark["status"] == "not-represented-in-decision"
    assert x_mark["decisionField"] is None
    assert set(x_mark["observedDecisionFields"]) == {
        "outcome", "endConditionDetected", "lockFurtherPlayInput",
        "promptEndDeclaration", "automaticallyEndsGame",
    }
    for case in contract["cases"]:
        decision = case["decision"]
        expected = branches[case["branchId"]]
        assert decision[automatic["field"]] is automatic["expected"]
        assert decision["lockFurtherPlayInput"] is expected["lockFurtherPlayInput"]
        assert decision["promptEndDeclaration"] is expected["promptEndDeclaration"]
        assert set(decision) == set(x_mark["observedDecisionFields"])
    counts, _, reachable, observed = checker._game_end_measure(
        ROOT, contract, declaration
    )
    assert counts["cases"] == 170
    assert counts["covered"] == counts["reachable"] == 1015
    assert observed == reachable
    assert checker.check_game_end_coverage(ROOT) == counts


def test_step96_validation_errors_are_exact_and_separate_from_cases() -> None:
    """導出器の不正値要求12件を別集合で引き受け、正常ケースに算入しない。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    state = _asset("state_transition_contract_v1.json")
    required, _ = checker.deriver.derive_repository_game_end_required_set(ROOT)
    expected = {item.identity for item in required.invalid_boundary_requirements}
    entries = contract["validationErrors"]
    actual = {
        ("invalid-boundary", item["axisId"], item["valueIdentity"])
        for item in entries
    }
    assert len(entries) == len(actual) == len(expected) == 12
    assert actual == expected
    assert declaration["deferredValidationErrors"]["status"] == "materialized"
    assert declaration["deferredValidationErrors"]["count"] == len(expected)
    assert len(state["cases"]) == 96
    assert len(contract["cases"]) == 170
    assert all("caseId" not in item and "inputCoordinate" not in item for item in entries)
    assert all("保証範囲外" in item["claimBoundary"]["notGuaranteed"] for item in entries)
    checker._check_game_end_validation_errors(ROOT, contract, declaration, state)
    counts, _, _, _ = checker._game_end_measure(ROOT, contract, declaration)
    assert counts["cases"] == 170
    assert counts["invalid"] == len(entries) == 12


@pytest.mark.parametrize("mutation", ["missing", "extra", "replaced"])
def test_step96_validation_error_set_mutations_are_rejected(mutation: str) -> None:
    """不正値拒否の欠落・余剰・同件数での差し替えを拒否する。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    if mutation == "missing":
        contract["validationErrors"].pop()
    elif mutation == "extra":
        extra = copy.deepcopy(contract["validationErrors"][0])
        extra["invalidValue"] = -1
        extra["valueIdentity"] = "-1"
        contract["validationErrors"].append(extra)
    else:
        replaced = contract["validationErrors"][0]
        replaced["invalidValue"] = -1
        replaced["valueIdentity"] = "-1"
        for field in ("guaranteed", "notGuaranteed"):
            replaced["claimBoundary"][field] = replaced["claimBoundary"][field].replace(
                " 0 ", " -1 "
            )
    with pytest.raises(checker.RequiredSetCoverageError, match="validationErrors"):
        checker._check_game_end_validation_errors(ROOT, contract, declaration)


@pytest.mark.parametrize("mutation", ["missing", "without-label"])
def test_step96_missing_claim_boundary_is_rejected(mutation: str) -> None:
    """1件でも保証範囲外の記述が欠ければ赤になる。"""
    contract = _asset("game_end_contract_v1.json")
    boundary = contract["validationErrors"][0]["claimBoundary"]
    if mutation == "missing":
        del boundary["notGuaranteed"]
    else:
        boundary["notGuaranteed"] = boundary["notGuaranteed"].replace("保証範囲外", "対象外")
    with pytest.raises(checker.RequiredSetCoverageError, match="schema違反|保証範囲外"):
        checker._check_game_end_validation_errors(
            ROOT, contract, _asset("game_end_coverage_declaration_v1.json")
        )


@pytest.mark.parametrize("contract_kind", ["gameEnd", "stateTransition"])
def test_step96_invalid_value_mixed_into_normal_cases_is_rejected(
    contract_kind: str,
) -> None:
    """両契約の正常ケースに不正な軸値を1件混ぜると赤になる。"""
    contract = _asset("game_end_contract_v1.json")
    state = _asset("state_transition_contract_v1.json")
    if contract_kind == "gameEnd":
        contract["cases"][0]["inputCoordinate"]["gameEnd.regulationInnings"] = 0
    else:
        state["cases"][0]["inputCoordinate"]["state.outs"] = 4
    with pytest.raises(checker.RequiredSetCoverageError, match="schema外値"):
        checker._check_game_end_validation_errors(
            ROOT, contract, _asset("game_end_coverage_declaration_v1.json"), state
        )


def test_step96_validation_error_cannot_be_counted_as_a_normal_case() -> None:
    """拒否要求を正常ケースへ追加してもケース件数として受理しない。"""
    contract = _asset("game_end_contract_v1.json")
    contract["cases"].append(copy.deepcopy(contract["validationErrors"][0]))
    with pytest.raises(checker.RequiredSetCoverageError, match="正常ケースの件数"):
        checker._check_game_end_validation_errors(
            ROOT, contract, _asset("game_end_coverage_declaration_v1.json")
        )


def test_step95_automatic_transition_mutation_is_rejected() -> None:
    """1ケースだけ試合状態を自動遷移させると検査器が失敗する。"""
    contract = _asset("game_end_contract_v1.json")
    contract["cases"][0]["decision"]["automaticallyEndsGame"] = True
    with pytest.raises(checker.RequiredSetCoverageError, match="試合状態が自動遷移する"):
        checker.check_game_end_coverage(ROOT, contract=contract)


@pytest.mark.parametrize("field", ["lockFurtherPlayInput", "promptEndDeclaration"])
@pytest.mark.parametrize("mutation", ["declaration", "case"])
def test_step95_branch_expectation_mutations_are_rejected(
    field: str, mutation: str
) -> None:
    """ロックと促しの各期待値は宣言側・実ケース側どちらの変異でも赤になる。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    if mutation == "declaration":
        branch = next(
            item for item in declaration["step95DecisionProperties"]["branchExpectations"]
            if item["branchId"] == contract["cases"][0]["branchId"]
        )
        branch[field] = not branch[field]
    else:
        decision = contract["cases"][0]["decision"]
        decision[field] = not decision[field]
    with pytest.raises(checker.RequiredSetCoverageError, match=f"分岐別の{field}期待値と不一致"):
        checker.check_game_end_coverage(ROOT, contract=contract, declaration=declaration)


def test_step95_x_mark_field_in_case_is_rejected() -> None:
    """decisionへX表記の値を足すと不在宣言との不一致を検出する。"""
    contract = _asset("game_end_contract_v1.json")
    contract["cases"][0]["decision"]["xMark"] = "X"
    with pytest.raises(checker.RequiredSetCoverageError, match="decisionのフィールドが不正"):
        checker.check_game_end_coverage(ROOT, contract=contract)


def test_step95_x_mark_schema_addition_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """将来schemaとcaseへX表記を足した場合も古い不在宣言を拒否する。"""
    schema = _asset("game_end_contract_schema_v1.json")
    decision_schema = schema["$defs"]["gameEndDecision"]
    decision_schema["properties"]["xMark"] = {"type": "string"}
    decision_schema["required"].append("xMark")
    original_document = checker._document

    def changed_document(root: Path, name: str) -> dict[str, Any]:
        if name == "game_end_contract_schema_v1.json":
            return schema
        return original_document(root, name)

    monkeypatch.setattr(checker, "_document", changed_document)
    contract = _asset("game_end_contract_v1.json")
    contract["cases"][0]["decision"]["xMark"] = "X"
    with pytest.raises(checker.RequiredSetCoverageError, match="X表記の出力不在宣言が実測と不一致"):
        checker.check_game_end_coverage(ROOT, contract=contract)


def test_step93_two_new_branches_cover_every_reachable_requirement() -> None:
    """本周の上限引き分け・タイブレーク継続だけで737要求を直接充足する。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    rows = contract["decisionRows"][2:4]
    branches = {row["branchId"] for row in rows}
    cases = [case for case in contract["cases"] if case["branchId"] in branches]
    game_axes = {axis["axisId"] for axis in descriptor["gameEndAxes"]}
    fixed = {
        (axis, value)
        for row in rows
        for axis, value in checker._fixed_game_end_values(row, game_axes).items()
    }
    all_values = {
        (axis["axisId"], checker._game_end_identity(value))
        for axis in descriptor["gameEndAxes"] for value in axis["boundaryValues"]
    }
    scoped_declaration = copy.deepcopy(declaration)
    scoped_declaration["unfixedGameEndAxisValues"] = [
        {"axisId": axis, "valueIdentity": value}
        for axis, value in sorted(all_values - fixed)
    ]
    scoped_declaration["uncoveredClauseBranches"].append(
        {"branchId": "COLD-08", "gapId": "GAP-03"}
    )
    counts, _, reachable, observed = checker._game_end_measure(
        ROOT, {**contract, "decisionRows": rows, "cases": cases}, scoped_declaration
    )
    assert counts["reachable"] == counts["covered"] == 737
    assert reachable == observed

    four_rows = contract["decisionRows"][:4]
    four_fixed = {
        (axis, value)
        for row in four_rows
        for axis, value in checker._fixed_game_end_values(row, game_axes).items()
    }
    four_declaration = copy.deepcopy(declaration)
    four_declaration["unfixedGameEndAxisValues"] = [
        {"axisId": axis, "valueIdentity": value}
        for axis, value in sorted(all_values - four_fixed)
    ]
    four_declaration["uncoveredClauseBranches"].append(
        {"branchId": "COLD-08", "gapId": "GAP-03"}
    )
    four_cases = [
        case for case in contract["cases"]
        if case["branchId"] in {row["branchId"] for row in four_rows}
    ]
    four_counts, _, four_reachable, four_observed = checker._game_end_measure(
        ROOT, {**contract, "decisionRows": four_rows, "cases": four_cases}, four_declaration
    )
    assert four_counts["reachable"] == four_counts["covered"] == 763
    assert four_counts["unreachable"] == 3069
    assert four_reachable == four_observed


def test_step94_cold_cases_cover_all_newly_reachable_requirements() -> None:
    """COLD-08の34ケースが252要求を埋め、以前の被覆も保つ。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    cases = contract["cases"]
    assert len([case for case in cases if case["branchId"] == "COLD-08"]) == 34
    assert len(cases) == 170
    previous = {**contract, "cases": cases[:136]}
    prior_counts, _, _, prior_observed = checker._game_end_measure(
        ROOT, previous, declaration
    )
    counts, _, reachable, observed = checker._game_end_measure(ROOT, contract, declaration)
    assert prior_counts["covered"] == 763
    assert counts["covered"] == 1015
    assert len(observed - prior_observed) == 252
    assert prior_observed <= observed == reachable


def test_step94_unmet_rows_are_absent_and_walk_off_mutation_is_rejected() -> None:
    """サヨナラ行・COLD-09行の出現で本周の前提を赤にする。"""
    contract = _asset("game_end_contract_v1.json")
    rows = contract["decisionRows"]
    assert [row["branchId"] for row in rows if row["branchId"].startswith("COLD-")] == [
        "COLD-08"
    ]
    assert not any(row["decision"]["outcome"] == "walk-off" for row in rows)
    assert not any(row["branchId"] == "COLD-09" for row in rows)
    assert any(case["branchId"] == "COLD-08" for case in contract["cases"])
    changed = copy.deepcopy(contract)
    changed["decisionRows"][0]["decision"]["outcome"] = "walk-off"
    with pytest.raises(checker.RequiredSetCoverageError, match="walk-off行"):
        checker.check_game_end_coverage(ROOT, contract=changed)
    added_cold09 = copy.deepcopy(contract)
    new_row = copy.deepcopy(rows[-1])
    new_row["branchId"] = "COLD-09"
    added_cold09["decisionRows"].append(new_row)
    with pytest.raises(checker.RequiredSetCoverageError, match="COLD行集合"):
        checker.check_game_end_coverage(ROOT, contract=added_cold09)


def test_step94_unmet_reason_and_scoring_rule_are_recorded() -> None:
    """未達の典拠・送り先・A-1の得点規則を宣言へ固定する。"""
    declaration = _asset("game_end_coverage_declaration_v1.json")
    unmet = declaration["step94UnmetCriteria"]
    assert unmet["walkOff"]["ownerStep"] == 46
    assert "68分岐" in unmet["walkOff"]["reason"]
    assert "design:step67-68-po-decision" in unmet["walkOff"]["sources"]
    assert unmet["cold09"]["ownerStage"] == 2
    assert "設定した段数" in unmet["cold09"]["reason"]
    assert unmet["walkOffScoring"]["sourceClauseId"] == "req:A-1"
    assert "決勝点" in unmet["walkOffScoring"]["rule"]
    assert "OUT3-*" in unmet["walkOffScoring"]["ordering"]


def test_step94_unfixed_axis_values_contract_by_exact_set() -> None:
    """onNewRowに従い、未固定軸値は20件から18件へ正確に縮む。"""
    contract = _asset("game_end_contract_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    values = checker.representative_selection.axis_values(descriptor, ("gameEndAxes",))
    game_axes = {axis["axisId"] for axis in descriptor["gameEndAxes"]}
    all_values = {
        (axis, checker._game_end_identity(value))
        for axis in game_axes for value in values[axis]
    }

    def unfixed(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
        fixed = {
            (axis, value)
            for row in rows
            for axis, value in checker._fixed_game_end_values(row, game_axes).items()
        }
        return all_values - fixed

    before = unfixed(contract["decisionRows"][:4])
    after = unfixed(contract["decisionRows"])
    declared = {
        (item["axisId"], item["valueIdentity"])
        for item in declaration["unfixedGameEndAxisValues"]
    }
    assert len(before) == 20
    assert len(after) == 18
    assert after == declared
    assert before - after == {
        ("gameEnd.coldConditions", '"tier-count:1"'),
        ("gameEnd.extensionLimit", '"none"'),
    }
    assert {
        (item["axisId"], item["valueIdentity"])
        for item in declaration["step94Contraction"]["removedAxisValues"]
    } == before - after


def test_game_end_declaration_rejects_missing_axis_branch_or_gap() -> None:
    """18軸値・18分岐の宣言欠落と未知GAPを拒否する。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    missing_axis = copy.deepcopy(declaration)
    missing_axis["unfixedGameEndAxisValues"].pop()
    with pytest.raises(checker.RequiredSetCoverageError, match="exact-set不一致"):
        checker._game_end_measure(ROOT, contract, missing_axis)
    missing_branch = copy.deepcopy(declaration)
    missing_branch["uncoveredClauseBranches"].pop()
    with pytest.raises(checker.RequiredSetCoverageError, match="exact-set不一致"):
        checker._game_end_measure(ROOT, contract, missing_branch)
    wrong_gap = copy.deepcopy(declaration)
    wrong_gap["uncoveredClauseBranches"][0]["gapId"] = "GAP-04"
    with pytest.raises(checker.RequiredSetCoverageError, match="GAPの分岐典拠"):
        checker._game_end_measure(ROOT, contract, wrong_gap)
    unknown_gap = copy.deepcopy(declaration)
    unknown_gap["uncoveredClauseBranches"][0]["gapId"] = "GAP-UNKNOWN"
    with pytest.raises(checker.RequiredSetCoverageError, match="GAPの分岐典拠"):
        checker._game_end_measure(ROOT, contract, unknown_gap)


def test_game_end_record_and_representative_drift_are_red() -> None:
    """実ケースの座標と終了判定専用被覆記録のずれを拒否する。"""
    contract = _asset("game_end_contract_v1.json")
    record = _asset("game_end_input_coverage_v1.json")
    drifted = copy.deepcopy(record)
    drifted["history"][0]["after"]["coveredCount"] -= 1
    with pytest.raises(checker.RequiredSetCoverageError, match="独立被覆記録"):
        checker.check_game_end_coverage(ROOT, record=drifted)
    changed = copy.deepcopy(contract)
    changed["cases"][4]["inputCoordinate"]["state.outs"] = 2
    with pytest.raises(checker.RequiredSetCoverageError, match="代表値展開"):
        checker.check_game_end_coverage(ROOT, contract=changed)


def test_game_end_exclusion_shrinks_when_row_fixes_a_declared_value() -> None:
    """新行が既宣言の軸値を固定すると、有効な除外集合が自動的に縮む。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    extra = copy.deepcopy(contract["decisionRows"][0])
    extra["branchId"] = "TEST-NEW"
    next(
        term for term in extra["precondition"]["args"]
        if term.get("axisId") == "gameEnd.regulationInnings"
    )["value"] = 7
    expanded = {**contract, "decisionRows": [*contract["decisionRows"], extra]}
    counts, _, _, _ = checker._game_end_measure(ROOT, expanded, declaration)
    assert counts["reachable"] > 1015
    assert counts["unreachable"] < 2817


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


def test_row_gap_rejects_missing_or_unsourced_gap() -> None:
    """実在しないGAPと典拠の交差しない宣言を拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    declaration = _asset("required_set_coverage_declaration_v1.json")
    for gap_id in ("GAP-01", "missing-gap"):
        mutant = copy.deepcopy(declaration)
        mutant["uncoveredRowRequirements"][0]["gapId"] = gap_id
        with pytest.raises(checker.RequiredSetCoverageError):
            checker.check_row_requirements(ROOT, contract, mutant)


def test_row_gap_accepts_resolved_gap_with_intersecting_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """追跡完了のresolvedでも未充足の典拠として利用できる。"""
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
    assert checker.check_row_requirements(ROOT) == (47, 42, 0)


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
    assert contract["cases"][:len(cases)] == cases
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

    assert [entry["step"] for entry in record["history"][:6]] == list(range(79, 85))
    previous = record["history"][4]["after"]
    current = record["history"][5]
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
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step85_tiebreak_start_has_no_row_case_or_coverage_change() -> None:
    """FR-009の規範行がない裁定を守り、②の被覆をステップ84から据え置く。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    _assert_no_tiebreak_start_row(contract)
    assert not any(
        case["rowRef"].get("coordinate", {}).get("operationKind") == "tiebreak-start"
        or case["inputCoordinate"].get("operationKind") == "tiebreak-start"
        or case["inputCoordinate"].get("event.operationPayload") == "tiebreak-start"
        for case in contract["cases"]
    )
    assert not any(
        mapping["operationType"] == "tiebreak-start"
        for mapping in contract["mustOperationCoverage"]["mappings"]
    )

    assert [entry["step"] for entry in record["history"][:7]] == list(range(79, 86))
    previous = record["history"][5]["after"]
    current = record["history"][6]
    assert current["before"] == previous
    assert current["after"] == current["before"]
    assert current["after"]["count"] == previous["count"] == 106
    assert current["after"]["digest"] == previous["digest"]
    after = {tuple(item) for item in current["after"]["coverageSet"]}
    assert ("event.operationKind", '"tiebreak-start"') not in after
    assert ("event.operationPayload", '"tiebreak-start"') not in after
    historical_cases, _ = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=2
    )
    assert after == _observed_coverage(historical_cases, contract)
    assert checker.check_row_requirements(ROOT) == (47, 42, 0)


def test_step86_game_end_declaration_cases_and_input_coverage() -> None:
    """FR-010の2行からケースを展開し、②の増分2件を実測する。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    target_rows = [
        row for row in contract["operationRows"]
        if row["operationKind"] == "game-end-declaration"
    ]
    assert len(target_rows) == 2
    assert all(row["clauseId"] == "FR-010" and "FR-010" in row["remarks"]
               for row in target_rows)

    cases, trace = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=4
    )
    previous_cases, _ = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=2
    )
    representatives, _ = expander.expand_traced(
        ROOT, limit=42, operation_limit=4
    )
    assert contract["cases"][:len(cases)] == cases
    assert len(cases) == 93
    assert len(previous_cases) == 91
    assert cases[:91] == previous_cases
    assert len(representatives) == 46
    assert len([case for case in cases if case["rowRef"]["layer"] == "matrixRows"]) == 89
    operation_cases = cases[-2:]
    assert operation_cases == representatives[-2:]
    assert [case["expected"]["operationResult"] for case in operation_cases] == [
        "applied", "rejected-precondition"
    ]
    assert [case["inputCoordinate"]["state.gameEnded"] for case in operation_cases] == [
        False, True
    ]
    for case in operation_cases:
        assert case["rowRef"]["coordinate"]["operationKind"] == "game-end-declaration"
        assert case["inputCoordinate"]["operationKind"] == "game-end-declaration"
        assert case["inputCoordinate"]["event.operationPayload"] == "game-end-declaration"
        assert case["rowRef"]["coordinate"]["payloadShape"] == {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False
        }
        assert case["expected"]["clauseId"] == "FR-010"

    assert [entry["step"] for entry in record["history"][:8]] == list(range(79, 87))
    previous = record["history"][6]["after"]
    current = record["history"][7]
    assert current["before"] == previous
    before = {tuple(item) for item in current["before"]["coverageSet"]}
    after = {tuple(item) for item in current["after"]["coverageSet"]}
    assert before <= after
    assert after - before == {
        ("event.operationKind", '"game-end-declaration"'),
        ("event.operationPayload", '"game-end-declaration"'),
    }
    assert len(after) == current["after"]["count"] == 108
    assert current["after"]["digest"] == checker._digest(after)
    assert after == _observed_coverage(cases, contract)
    assert checker.check_row_requirements(ROOT) == (47, 42, 0)
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step87_adhoc_registration_cases_and_input_coverage() -> None:
    """FR-015の2行を展開し、②の増分2件と過去の被覆を照合する。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    target_rows = [
        row for row in contract["operationRows"]
        if row["operationKind"] == "adhoc-registration"
    ]
    assert len(contract["operationRows"]) == 6
    assert len(target_rows) == 2
    assert all(row["clauseId"] == "FR-015" and "FR-015" in row["remarks"]
               for row in target_rows)

    cases, trace = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=6
    )
    previous_cases, _ = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=4
    )
    representatives, _ = expander.expand_traced(
        ROOT, limit=42, operation_limit=6
    )
    assert contract["cases"][:len(cases)] == cases
    assert len(cases) == 95
    assert cases[:93] == previous_cases
    assert len(representatives) == 48
    assert len([case for case in cases if case["rowRef"]["layer"] == "matrixRows"]) == 89
    operation_cases = cases[-2:]
    assert operation_cases == representatives[-2:]
    assert [case["expected"]["operationResult"] for case in operation_cases] == [
        "applied", "rejected-precondition"
    ]
    assert [case["inputCoordinate"]["state.gameEnded"] for case in operation_cases] == [
        False, True
    ]
    for case in operation_cases:
        assert case["rowRef"]["coordinate"]["operationKind"] == "adhoc-registration"
        assert case["inputCoordinate"]["operationKind"] == "adhoc-registration"
        assert case["inputCoordinate"]["event.operationPayload"] == "adhoc-registration"
        assert case["expected"]["clauseId"] == "FR-015"
        payload = case["rowRef"]["coordinate"]["payloadShape"]
        assert payload == {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "throws": {"type": "string", "enum": ["right", "left"]},
                "bats": {"type": "string", "enum": ["right", "left", "both"]},
                "uniformNumber": {"type": "string"},
                "temporaryPlayerId": {"type": "string"},
            },
            "required": ["name", "throws", "bats"],
            "additionalProperties": False,
        }

    assert record["history"][8]["step"] == 87
    assert [entry["step"] for entry in record["history"][:9]] == list(range(79, 88))
    current = record["history"][8]
    assert current["before"] == record["history"][7]["after"]
    before = {tuple(item) for item in current["before"]["coverageSet"]}
    after = {tuple(item) for item in current["after"]["coverageSet"]}
    assert after - before == {
        ("event.operationKind", '"adhoc-registration"'),
        ("event.operationPayload", '"adhoc-registration"'),
    }
    assert not before - after
    assert len(after) == current["after"]["count"] == 110
    assert current["after"]["digest"] == checker._digest(after)
    assert after == _observed_coverage(cases, contract)
    assert checker.check_input_coverage(ROOT) == (
        111, record["history"][-1]["after"]["digest"], 1
    )
    assert checker.check_row_requirements(ROOT) == (47, 42, 0)
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step85_rejects_a_new_tiebreak_start_row() -> None:
    """段階2で操作行が追加された場合、この周の前提を赤にする。"""
    contract = _asset("state_transition_contract_v1.json")
    changed = copy.deepcopy(contract)
    changed["operationRows"].append(
        {**copy.deepcopy(contract["operationRows"][0]), "operationKind": "tiebreak-start"}
    )
    with pytest.raises(AssertionError, match="tiebreak-startの規範行が現れた"):
        _assert_no_tiebreak_start_row(changed)


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
    changed = copy.deepcopy(next(
        case for case in contract["cases"]
        if case["rowRef"]["layer"] == "operationRows"
    ))
    if mutation == "kind":
        changed["inputCoordinate"]["operationKind"] = "undo"
    elif mutation == "payload":
        changed["inputCoordinate"]["event.operationPayload"] = "undo"
    elif mutation == "unknown-layer":
        changed["rowRef"]["layer"] = "unknownRows"
    elif mutation == "ambiguous-reference":
        del changed["rowRef"]["coordinate"]["precondition"]
    else:
        changed["expected"]["operationResult"] = "nothing-to-undo"
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
    case = copy.deepcopy(next(
        item for item in contract["cases"]
        if item["rowRef"]["layer"] == "operationRows"
        and item["inputCoordinate"]["operationKind"] == "substitution"
        and item["inputCoordinate"]["state.gameEnded"] is True
    ))
    del case["rowRef"]["coordinate"]["payloadShape"]
    del contract["operationRows"][1]["payloadShape"]
    with pytest.raises(
        checker.RequiredSetCoverageError,
        match="ケースの操作またはpayloadタグが規範行と不一致",
    ):
        _observed_coverage([case], contract)


def _assert_step88_undo_rows(contract: dict[str, Any]) -> None:
    """本周の空履歴1行だけという規範行前提を固定する。"""
    assert not any(
        row.get("guaranteeMode") == "liveness-only" for row in contract["undoRows"]
    ), "liveness-onlyの規範行が現れた"
    assert len(contract["undoRows"]) == 1, "undoRowsの行数が変わった"


def test_step88_empty_history_undo_case_and_coverage() -> None:
    """空履歴undoを1件展開し、②のundo操作種別だけを増やす。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    _assert_step88_undo_rows(contract)
    row = contract["undoRows"][0]
    assert row["precondition"] == {
        "op": "eq", "axisId": "history.depth", "value": 0,
    }
    assert row["historyEffect"] == {"pops": 0}
    assert row["operationResult"] == "nothing-to-undo"
    assert row["guaranteeMode"] == "full-equality"

    cases, trace = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=6, undo_limit=1
    )
    previous_cases, _ = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=6
    )
    assert contract["cases"] == cases
    assert cases[:-1] == previous_cases
    assert len(cases) == 96
    assert [case["rowRef"]["layer"] for case in cases].count("matrixRows") == 89
    assert [case["rowRef"]["layer"] for case in cases].count("operationRows") == 6
    assert [case["rowRef"]["layer"] for case in cases].count("undoRows") == 1
    undo_case = cases[-1]
    assert undo_case["rowRef"] == contract["mustOperationCoverage"]["mappings"][1]["rowRefs"][0]
    assert undo_case["inputCoordinate"] == {
        "operationKind": "undo", "history.depth": 0,
    }
    assert undo_case["expected"]["operationResult"] == "nothing-to-undo"
    assert undo_case["expected"]["guaranteeMode"] == "full-equality"

    assert record["currentStep"] == 88
    assert [item["step"] for item in record["history"]] == list(range(79, 89))
    current = record["history"][-1]
    assert current["before"] == record["history"][-2]["after"]
    before = {tuple(item) for item in current["before"]["coverageSet"]}
    after = {tuple(item) for item in current["after"]["coverageSet"]}
    assert after - before == {("event.operationKind", '"undo"')}
    assert before <= after
    assert len(after) == current["after"]["count"] == 111
    assert current["after"]["digest"] == checker._digest(after)
    assert after == _observed_coverage(cases, contract)
    assert "ステップ66 PO裁定" in current["reason"]
    assert "XC-09" in current["reason"]
    assert "history.scenarioLength" in current["reason"]
    assert "D+1" in current["fact"] and "未達" in current["fact"]
    assert checker.check_input_coverage(ROOT) == (111, current["after"]["digest"], 1)
    assert checker.check_row_requirements(ROOT) == (47, 42, 0)
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step88_rejects_new_liveness_only_row() -> None:
    """段階2でliveness-only行が入れば本周の前提を赤にする。"""
    contract = _asset("state_transition_contract_v1.json")
    changed = copy.deepcopy(contract)
    changed["undoRows"].append({
        **copy.deepcopy(contract["undoRows"][0]), "guaranteeMode": "liveness-only"
    })
    with pytest.raises(AssertionError, match="liveness-onlyの規範行が現れた"):
        _assert_step88_undo_rows(changed)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("kind", "ケースのundo操作種別が不一致"),
        ("ambiguous-reference", "ケースが規範行を一意に参照しない"),
        ("predicate", "ケースが規範行の前提条件を満たさない"),
        ("expected", "ケースの期待値が規範行と不一致"),
    ],
)
def test_checker_rejects_invalid_undo_case(mutation: str, message: str) -> None:
    """undoRowsの分岐で種別・参照・前提・期待値の破損を拒否する。"""
    case = copy.deepcopy(_asset("state_transition_contract_v1.json")["cases"][-1])
    if mutation == "kind":
        case["inputCoordinate"]["operationKind"] = "substitution"
    elif mutation == "ambiguous-reference":
        case["rowRef"]["coordinate"]["targetKind"] = "unknown"
    elif mutation == "predicate":
        case["inputCoordinate"]["history.depth"] = 1
    else:
        case["expected"]["operationResult"] = "applied"
    with pytest.raises(checker.RequiredSetCoverageError, match=message):
        _observed_coverage([case])


def test_existing_layers_reject_swapped_undo_assignment() -> None:
    """既存2層の操作種別とpayloadの観測をundo分岐へ流さない。"""
    cases = _asset("state_transition_contract_v1.json")["cases"]
    matrix_case = copy.deepcopy(next(
        case for case in cases if case["rowRef"]["layer"] == "matrixRows"
    ))
    operation_case = copy.deepcopy(next(
        case for case in cases if case["rowRef"]["layer"] == "operationRows"
    ))
    matrix_baseline = _observed_coverage([matrix_case])
    operation_baseline = _observed_coverage([operation_case])
    matrix_case["inputCoordinate"]["operationKind"] = "undo"
    operation_case["inputCoordinate"]["event.operationPayload"] = "not-applicable"
    assert _observed_coverage([matrix_case]) == matrix_baseline
    with pytest.raises(checker.RequiredSetCoverageError, match="ケースの操作またはpayloadタグ"):
        _observed_coverage([operation_case])
    assert ("event.operationKind", '"undo"') not in operation_baseline


@pytest.mark.parametrize("undo_limit", [-1, 2])
def test_expander_rejects_undo_limit_outside_references(undo_limit: int) -> None:
    """undo行参照の範囲を越える展開指定を拒否する。"""
    with pytest.raises(expander.CaseExpansionError, match="undo行の出力件数"):
        expander.expand_traced(ROOT, limit=42, operation_limit=6, undo_limit=undo_limit)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing-row", "undo行参照が規範行を一意に指していない"),
        ("wrong-layer", "undo行の参照層が不正"),
        ("invalid-coordinate", "undo行の入力座標が不正"),
        ("invalid-predicate", "undo行の事前条件が述語でない"),
    ],
)
def test_expander_rejects_invalid_undo_inputs(
    monkeypatch: pytest.MonkeyPatch, mutation: str, message: str
) -> None:
    """undoRowsの行・参照層・入力座標・述語の破損を拒否する。"""
    original = expander._read_document

    def changed_document(root: Path, relative: Any) -> dict[str, Any]:
        document = original(root, relative)
        if "matrixRows" not in document:
            return document
        document = copy.deepcopy(document)
        mapping = next(
            item for item in document["mustOperationCoverage"]["mappings"]
            if item["operationType"] == "undo"
        )
        reference = mapping["rowRefs"][0]
        if mutation == "missing-row":
            document["undoRows"].clear()
        elif mutation == "wrong-layer":
            reference["layer"] = "unknownRows"
        elif mutation == "invalid-coordinate":
            reference["coordinate"] = None
        else:
            reference["coordinate"]["precondition"] = None
            document["undoRows"][0]["precondition"] = None
        return document

    monkeypatch.setattr(expander, "_read_document", changed_document)
    with pytest.raises(expander.CaseExpansionError, match=message):
        expander.expand_traced(ROOT, limit=42, operation_limit=6, undo_limit=1)


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
