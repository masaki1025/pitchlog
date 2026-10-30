"""ステップ79〜88の行要求差分と入力座標被覆を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
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
mutation_checker = _load_module(
    "check_required_set_mutation_step104",
    ROOT / "scripts/check_required_set_mutation.py",
)
expander = _load_module(
    "expand_state_transition_cases", ROOT / "scripts/expand_state_transition_cases.py"
)


def _asset(name: str) -> dict[str, Any]:
    """検査対象の現行資産を読み込む。"""
    return json.loads((ROOT / "contracts/state-transition" / name).read_text(encoding="utf-8"))


_LIVE_ROOT = ROOT
_HISTORICAL_COVERAGE_TESTS = frozenset({
    "test_prior_step_coverage_matches_its_matrix_expansion",
    "test_step80_input_coverage_is_preserved",
    "test_step81_input_coverage_is_monotone_and_matches_expansion",
    "test_step82_secondary_results_and_input_coverage",
    "test_step83_runner_events_and_input_coverage",
    "test_step84_substitution_cases_and_input_coverage",
    "test_step85_tiebreak_start_has_no_row_case_or_coverage_change",
    "test_step86_game_end_declaration_cases_and_input_coverage",
    "test_step87_adhoc_registration_cases_and_input_coverage",
    "test_step88_empty_history_undo_case_and_coverage",
    "test_step24_draw05_operation_case_preserves_input_coverage",
    "test_rbi_coverage_append_preserves_history_and_six_observed_values",
    "test_ordinary_coverage_keeps_old_history_and_rejects_pending_approval",
    "test_step98_all_normative_rows_are_referenced_by_cases",
    "test_step96_validation_errors_are_exact_and_separate_from_cases",
    "test_row_binding_declaration_controls_coverage_and_checks_sources",
    "test_step102_input_coordinate_difference_is_red_when_row_is_added",
})


@pytest.fixture(scope="module")
def historical_coverage_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """旧assertとファイル集合を固定Gitへ束縛し、新vectorを混入させない。"""
    root = tmp_path_factory.mktemp("coverage-history-30f67")
    for name in subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "30f67cbc"],
        cwd=_LIVE_ROOT, text=True,
    ).splitlines():
        source = _LIVE_ROOT / name
        if source.is_file():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    # 一時fixtureのHEADだけを旧版へ固定し、実repositoryのindex/refsは変更しない。
    common = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=_LIVE_ROOT, text=True,
    ).strip()
    git = root / ".git"
    (git / "objects/info").mkdir(parents=True)
    (git / "refs").mkdir()
    (git / "HEAD").write_text("30f67cbc0afbdae00919606a17439d64fa7e9832\n")
    (git / "objects/info/alternates").write_text(str(Path(common) / "objects") + "\n")
    for name in (
        "state_transition_contract_v1.json", "required_set_input_coverage_v1.json",
        "branch_row_mapping_v1.json", "game_end_coverage_declaration_v1.json",
    ):
        relative = "contracts/state-transition/" + name
        (root / relative).write_bytes(subprocess.check_output(
            ["git", "show", "30f67cbc:" + relative], cwd=_LIVE_ROOT,
        ))
    return root


@pytest.fixture(autouse=True)
def bind_historical_coverage_tests(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """列挙した旧段階試験だけを旧原本へ結び、全未知拒否assertを残す。"""
    if getattr(request.node, "originalname", None) in _HISTORICAL_COVERAGE_TESTS:
        monkeypatch.setattr(sys.modules[__name__], "ROOT",
                            request.getfixturevalue("historical_coverage_root"))


def _current_exact_input_counts() -> tuple[int, int, int]:
    """新currentは実12移行を検証してから177到達のexact値を比較する。"""
    if not (ROOT / "contracts/state-transition/ordinary_pitch_vectors_v1.json").exists():
        return 228, 52, 0
    checker._ordinary_case_id_migrations(ROOT, _asset("state_transition_contract_v1.json"))
    return 228, 51, 0


def test_repository_contracts_are_within_declared_byte_limit() -> None:
    """実契約が資産側のbyte上限以下である。"""
    sizes = checker.check_contract_sizes(ROOT)
    policy = _asset("contract_size_limit_v1.json")
    assert set(sizes) == set(policy["contractPaths"])
    assert all(size <= policy["maximumBytesPerFile"] for size in sizes.values())


def test_contract_size_one_byte_over_limit_is_red(tmp_path: Path) -> None:
    """上限ちょうどは通り、1 byte超過は失敗する。"""
    policy = _asset("contract_size_limit_v1.json")
    for name in ("contract_size_limit_v1.json", "input_axes_descriptor_schema_v1.json"):
        target = tmp_path / "contracts/state-transition" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / "contracts/state-transition" / name).read_bytes())
    for relative in policy["contractPaths"]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")
    target = tmp_path / policy["contractPaths"][0]
    with target.open("wb") as output:
        output.truncate(policy["maximumBytesPerFile"])
    checker.check_contract_sizes(tmp_path)
    with target.open("wb") as output:
        output.truncate(policy["maximumBytesPerFile"] + 1)
    with pytest.raises(checker.RequiredSetCoverageError, match="byte上限超過"):
        checker.check_contract_sizes(tmp_path)


def test_contract_size_policy_missing_is_red(tmp_path: Path) -> None:
    """上限を読めない場合は検査を成功させない。"""
    with pytest.raises(checker.RequiredSetCoverageError, match="宣言資産を読めない"):
        checker.check_contract_sizes(tmp_path)


@pytest.mark.parametrize(
    ("name", "check", "error_type"),
    [
        (
            "required_set_coverage_declaration_v1.json",
            checker.check_row_requirements,
            checker.RequiredSetCoverageError,
        ),
        (
            "required_set_input_coverage_declaration_v1.json",
            checker.check_input_coverage_exact,
            checker.RequiredSetCoverageError,
        ),
        (
            "game_end_coverage_declaration_v1.json",
            checker.check_game_end_coverage,
            checker.RequiredSetCoverageError,
        ),
        (
            "coverage_row_binding_policy_v1.json",
            checker.check_input_coverage_exact,
            checker.RequiredSetCoverageError,
        ),
        (
            "representative_selection_policy_v1.json",
            checker.check_input_coverage_exact,
            checker.RequiredSetCoverageError,
        ),
        (
            "required_set_mutation_policy_v1.json",
            mutation_checker.check_repository,
            FileNotFoundError,
        ),
        (
            "expander_dependency_policy_v1.json",
            expander.dependency_checker.load_policy,
            expander.dependency_checker.ExpanderDependencyError,
        ),
        (
            "deriver_dependency_policy_v1.json",
            checker.deriver.load_policy,
            checker.deriver.DeriverDependencyError,
        ),
    ],
)
def test_step104_unreadable_declarations_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    check: Any,
    error_type: type[Exception],
) -> None:
    """宣言資産1件を存在しない状態にすると実検査が必ず失敗する。"""
    target = ROOT / "contracts/state-transition" / name
    original_read_text = Path.read_text
    attempted = False

    def unreadable(path: Path, *args: Any, **kwargs: Any) -> str:
        nonlocal attempted
        if path == target:
            attempted = True
            raise FileNotFoundError(target)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    with pytest.raises(error_type):
        check(ROOT)
    assert attempted, f"検査器が宣言資産を読んでいない: {name}"


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
    """実資産の4層72行すべてにcaseからの参照があることを確認する。"""
    state = _asset("state_transition_contract_v1.json")
    game_end = _asset("game_end_contract_v1.json")
    assert [len(state[layer]) for layer in ("matrixRows", "operationRows", "undoRows")] == [
        49, 10, 10,
    ]
    assert len(game_end["decisionRows"]) == 8
    assert len(state["cases"]) == 116
    assert len(game_end["cases"]) == 248
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


def test_step26_game_end_declaration_and_direct_coverage() -> None:
    """成立段数の軸とCOLD-09追加後の到達性と被覆履歴を照合する。"""
    assert checker.check_game_end_coverage(ROOT) == {
        "total": 4656, "reachable": 1542, "unreachable": 3087,
        "requirementsImpossible": 15,
        "invalid": 12, "covered": 1542, "cases": 248,
    }
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    classified = declaration["step23Unreachability"]
    assert classified["beforeUnreachableCount"] == 2817
    assert classified["remainingUnreachableCount"] == 3087
    assert classified["countsByCause"] == {
        "noApplicableRow": {
            "pairwise": 24, "boundaryCoordinate": 291,
            "clauseBranch": 17, "total": 332,
        },
        "unfixedAxisValue": {
            "pairwise": 271, "boundaryCoordinate": 2484,
            "clauseBranch": 0, "total": 2755,
        },
        "requirementsImpossible": {
            "pairwise": 14, "boundaryCoordinate": 1,
            "clauseBranch": 0, "total": 15,
        },
    }
    assert len(contract["cases"]) == 248
    record = _asset("game_end_input_coverage_v1.json")
    assert [item["step"] for item in record["history"]] == [93, 94, 95, 96, 97, 98, 99, 100, 101]
    assert record["history"][0]["before"]["coveredCount"] == 51
    assert record["history"][0]["after"] == record["history"][1]["before"]
    assert record["history"][1]["after"] == record["history"][2]["before"]
    assert record["history"][0]["after"]["coveredCount"] == 763
    assert record["history"][1]["after"]["coveredCount"] == 1015
    assert record["history"][2]["after"]["coveredCount"] == 1021
    assert record["history"][2]["after"] == record["history"][3]["before"]
    assert record["history"][3]["after"]["coveredCount"] == 1022
    assert record["history"][3]["after"]["caseCount"] == 180
    assert record["history"][3]["after"] == record["history"][4]["before"]
    assert record["history"][4]["after"]["coveredCount"] == 1533
    assert record["history"][4]["after"]["caseCount"] == 214


def test_derived_axis_function_uses_complete_concrete_input() -> None:
    """導出元の具体入力が同じcaseだけで派生値の関数性を比べる。"""
    contract = _asset("game_end_contract_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    checker.check_derived_axis_cases(contract, descriptor)

    cold_cases = [
        case for case in contract["cases"] if case["branchId"] == "COLD-09"
    ]
    assert len(cold_cases) >= 2
    source = cold_cases[0]["derivedSourceInput"]
    assert source["gameEnd.coldConditions"] == [
        {"pointDifference": 10, "startInning": 5},
        {"pointDifference": 7, "startInning": 7},
    ]
    cold_cases[1]["raw"]["gameEnd.satisfiedColdTierCount"] = 1
    with pytest.raises(checker.RequiredSetCoverageError, match="DERIVED_FUNCTION"):
        checker.check_derived_axis_cases(contract, descriptor)
    cold_cases[1]["derivedSourceInput"]["gameEnd.coldConditions"][1][
        "startInning"
    ] = 8
    checker.check_derived_axis_cases(contract, descriptor)


def test_game_end_cases_reject_equal_concrete_input_with_different_decision() -> None:
    """記号座標が異なっても具体入力が同じなら期待値を分岐させない。"""
    contract = _asset("game_end_contract_v1.json")
    first = contract["cases"][0]
    duplicate = copy.deepcopy(first)
    duplicate["caseId"] = "GE-DUPLICATE-EXPECTED"
    duplicate["decision"]["outcome"] = "extra-continue"
    contract["cases"] = [first, duplicate]
    with pytest.raises(checker.RequiredSetCoverageError, match="CASE_FUNCTION"):
        checker.check_game_end_concrete_case_consistency(contract)


def test_l_plus_one_and_x_mark_cases_require_concrete_boundary() -> None:
    """L+1の実回と未開始の裏だけのX表記を拘束する。"""
    contract = _asset("game_end_contract_v1.json")
    normal = next(case for case in contract["cases"] if case["branchId"] == "GAME-END-NORMAL")
    normal["derivedSourceInput"]["state.inning"] = 10
    with pytest.raises(checker.RequiredSetCoverageError, match="CONCRETE_INNING"):
        checker.check_game_end_concrete_case_consistency(contract)
    normal["derivedSourceInput"]["state.inning"] = 11
    cold = next(case for case in contract["cases"] if case["branchId"] == "COLD-08")
    cold["normalized"]["state.outs"] = 1
    with pytest.raises(checker.RequiredSetCoverageError, match="XMARK_STARTED"):
        checker.check_game_end_concrete_case_consistency(contract)


def test_all_post_turn_rows_require_fresh_half_inning_state() -> None:
    """攻守交代直後の全行は次の表が進行する前の状態だけを持つ。"""
    contract = _asset("game_end_contract_v1.json")
    post_turn_rows = {
        row["branchId"] for row in contract["decisionRows"]
        if "攻守交代" in row["remarks"]
    }
    assert post_turn_rows == {
        "GAME-END-NORMAL", "GAME-END-EXTRA-CONTINUE", "GAME-END-LIMIT-DRAW",
        "COLD-08",
    }
    initial_rows = post_turn_rows | {"COLD-09", "XMARK-02"}
    cases = [case for case in contract["cases"] if case["branchId"] in initial_rows]
    assert len(cases) == 204
    for case in cases:
        coordinate = case["normalized"]
        assert coordinate["state.half"] == (
            "top" if case["branchId"].startswith("GAME-END-") else "bottom"
        )
        assert coordinate["state.outs"] == 0
        assert coordinate["state.runners"] == "empty"
        assert coordinate["state.count.strikes"] == 0
        assert coordinate["state.count.balls"] == 0


def test_post_turn_row_rejects_in_progress_top_half() -> None:
    """L+1回表でプレイが始まった後の終了期待値を拒否する。"""
    contract = _asset("game_end_contract_v1.json")
    case = next(case for case in contract["cases"] if case["branchId"] == "GAME-END-NORMAL")
    case["normalized"]["state.outs"] = 1
    with pytest.raises(checker.RequiredSetCoverageError, match="POST_TURN_STATE"):
        checker.check_game_end_concrete_case_consistency(contract)


def test_xmark02_only_regulation_final_cases_are_derived() -> None:
    """X表記は到達可能な規定最終回の未開始の裏だけから展開する。"""
    contract = _asset("game_end_contract_v1.json")
    cases = [case for case in contract["cases"] if case["branchId"] == "XMARK-02"]
    assert len(cases) == 34
    assert {case["normalized"]["gameEnd.extensionLimit"] for case in cases} == {
        "finite:R",
    }
    assert {case["derivedSourceInput"]["state.inning"] for case in cases} == {9}
    for case in cases:
        assert case["normalized"]["state.half"] == "bottom"
        assert case["derivedSourceInput"]["gameEnd.coldConditions"] == []
        assert case["decision"] == {
            "outcome": "normal-end",
            "endConditionDetected": True,
            "lockFurtherPlayInput": True,
            "promptEndDeclaration": True,
            "automaticallyEndsGame": False,
            "xMark": "x-mark",
        }
    cases[0]["normalized"]["state.outs"] = 1
    with pytest.raises(checker.RequiredSetCoverageError, match="XMARK_STARTED"):
        checker.check_game_end_concrete_case_consistency(contract)


def test_xmark02_extension_home_lead_is_red() -> None:
    """同点で入る延長回の表に後攻リードのX表記を認めない。"""
    contract = _asset("game_end_contract_v1.json")
    case = next(case for case in contract["cases"] if case["branchId"] == "XMARK-02")
    case["normalized"]["gameEnd.extensionLimit"] = "finite:R+1"
    case["normalized"]["state.inning"] = "L"
    with pytest.raises(checker.RequiredSetCoverageError, match="XMARK_EXTENSION"):
        checker.check_game_end_concrete_case_consistency(contract)


def test_tiebreak_none_cannot_be_active_in_game_end_case() -> None:
    """規則なしと実行中の矛盾をdescriptorの宣言で拒否する。"""
    contract = _asset("game_end_contract_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    case = next(case for case in contract["cases"] if case["branchId"] == "XMARK-02")
    contract["cases"] = [case]
    case["raw"]["state.tiebreakActive"] = True
    with pytest.raises(checker.RequiredSetCoverageError, match="UNREACHABLE_PAIR"):
        checker.check_derived_axis_cases(contract, descriptor)


def test_cold_tier_after_regulation_cannot_be_case_input() -> None:
    """FR-014が保存を拒否する適用開始回を実入力に認めない。"""
    contract = _asset("game_end_contract_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    case = next(case for case in contract["cases"] if case["branchId"] == "XMARK-02")
    contract["cases"] = [case]
    case["raw"]["gameEnd.coldConditions"] = "tier-count:1"
    case["derivedSourceInput"]["gameEnd.coldConditions"] = [
        {"pointDifference": 10, "startInning": 10}
    ]
    with pytest.raises(checker.RequiredSetCoverageError, match="COLD_RULE_SAVE"):
        checker.check_derived_axis_cases(contract, descriptor)


def test_normal_end_rejects_home_lead_after_completed_bottom() -> None:
    """完了した裏の後に後攻リードの通常終了を置かない。"""
    contract = _asset("game_end_contract_v1.json")
    normal = next(case for case in contract["cases"] if case["branchId"] == "GAME-END-NORMAL")
    normal["normalized"]["state.score"] = "home-lead:M"
    with pytest.raises(checker.RequiredSetCoverageError, match="NORMAL_SCORE"):
        checker.check_game_end_concrete_case_consistency(contract)


def test_walk_off_rejects_third_out_modifier() -> None:
    """本塁打行に有効得点を変える第3アウト指定を混ぜない。"""
    contract = _asset("game_end_contract_v1.json")
    case = next(
        item for item in contract["cases"] if item["branchId"] == "GAME-END-WALK-OFF"
    )
    case["normalized"]["event.perPitch.thirdOutTimingByRunner"] = (
        "single-runner-not-before-third-out"
    )
    with pytest.raises(checker.RequiredSetCoverageError, match="WALKOFF_MODIFIERS"):
        checker.check_game_end_concrete_case_consistency(contract)


def test_derived_unreachable_pair_is_absent_from_cases() -> None:
    """設定段数を上回る派生値を持つcaseを宣言規則で拒否する。"""
    contract = _asset("game_end_contract_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    cold_case = next(
        case for case in contract["cases"] if case["branchId"] == "COLD-08"
    )
    contract["cases"] = [cold_case]
    cold_case["raw"]["gameEnd.satisfiedColdTierCount"] = 2
    with pytest.raises(checker.RequiredSetCoverageError, match="DERIVED_UNREACHABLE"):
        checker.check_derived_axis_cases(contract, descriptor)


def test_tiebreak_derived_axis_uses_complete_input_for_functionality() -> None:
    """同じ指定回・規則開始回・現在回に異なる派生値を認めない。"""
    contract = _asset("state_transition_contract_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    first = next(
        case for case in contract["cases"]
        if case["inputCoordinate"].get("event.tiebreakStart.activationRelation") == "ready"
    )
    duplicate = copy.deepcopy(first)
    duplicate["inputCoordinate"]["event.tiebreakStart.activationRelation"] = "not-ready"
    duplicate["raw"]["event.tiebreakStart.activationRelation"] = "not-ready"
    contract["cases"] = [first, duplicate]
    with pytest.raises(checker.RequiredSetCoverageError, match="DERIVED_FUNCTION"):
        checker.check_state_derived_axis_cases(contract, descriptor)


def test_tiebreak_derived_axis_requires_current_inning_value() -> None:
    """派生軸の現在回の実値を欠くcaseを拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    case = next(
        item for item in contract["cases"]
        if item["inputCoordinate"].get("event.tiebreakStart.activationRelation") == "ready"
    )
    case["historyInput"]["before"]["stateFields"].pop("state.inning")
    contract["cases"] = [case]
    with pytest.raises(checker.RequiredSetCoverageError, match="DERIVED_INPUT"):
        checker.check_state_derived_axis_cases(contract, descriptor)


def test_tiebreak_rule_none_and_ready_is_unreachable() -> None:
    """規則に指定がないときの ready を宣言済み到達不可として拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    descriptor = _asset("input_axes_descriptor_v1.json")
    case = next(
        item for item in contract["cases"]
        if item["inputCoordinate"].get("event.tiebreakStart.activationRelation") == "not-ready"
    )
    case["inputCoordinate"]["event.tiebreakStart.activationRelation"] = "ready"
    case["raw"]["event.tiebreakStart.activationRelation"] = "ready"
    contract["cases"] = [case]
    with pytest.raises(checker.RequiredSetCoverageError, match="DERIVED_UNREACHABLE"):
        checker.check_state_derived_axis_cases(contract, descriptor)


@pytest.mark.parametrize("mutation", ["remove", "unknown", "source", "count"])
def test_step23_impossible_requirement_declaration_drift_is_red(mutation: str) -> None:
    """要件上の到達不可15件の欠落・混入・典拠・件数ずれを拒否する。"""
    declaration = _asset("game_end_coverage_declaration_v1.json")
    policy = declaration["step23Unreachability"]
    if mutation == "remove":
        policy["requirementsImpossible"].pop()
    elif mutation == "unknown":
        policy["requirementsImpossible"][0]["identity"][-1] = '"finite:R"'
    elif mutation == "source":
        policy["requirementsImpossible"][0]["clauseIds"] = ["req:DRAW-03"]
    else:
        policy["countsByCause"]["requirementsImpossible"]["total"] += 1
    with pytest.raises(checker.RequiredSetCoverageError, match="S28の"):
        checker.check_game_end_coverage(ROOT, declaration=declaration)


def test_step95_decision_properties_hold_for_all_cases() -> None:
    """全248ケースの自動遷移なし・分岐別出力・X表記を宣言と照合する。"""
    contract = _asset("game_end_contract_v1.json")
    declaration = _asset("game_end_coverage_declaration_v1.json")
    properties = declaration["step95DecisionProperties"]
    automatic = properties["automaticTransition"]
    branches = {
        branch["branchId"]: branch for branch in properties["branchExpectations"]
    }
    x_mark = properties["xMark"]
    assert len(contract["cases"]) == 248
    assert automatic["field"] == "automaticallyEndsGame"
    assert automatic["expected"] is False
    assert set(branches) == {row["branchId"] for row in contract["decisionRows"]}
    assert x_mark["status"] == "represented-in-decision"
    assert x_mark["decisionField"] == "xMark"
    assert x_mark["enumValues"] == ["recorded-score", "x-mark", "blank"]
    x_by_branch = {item["branchId"]: item for item in x_mark["expectedByBranch"]}
    assert set(x_by_branch) == set(branches)
    assert {branch: item["value"] for branch, item in x_by_branch.items()} == {
        "GAME-END-NORMAL": "recorded-score",
        "GAME-END-EXTRA-CONTINUE": "recorded-score",
        "GAME-END-LIMIT-DRAW": "recorded-score",
        "GAME-END-TIEBREAK-CONTINUE": "recorded-score",
        "COLD-08": "x-mark",
        "COLD-09": "x-mark",
        "GAME-END-WALK-OFF": "recorded-score",
        "XMARK-02": "x-mark",
    }
    for branch, item in x_by_branch.items():
        expected_rule = (
            "req:XMARK-02"
            if branch in {"COLD-08", "COLD-09", "XMARK-02"}
            else "req:XMARK-01"
        )
        assert expected_rule in item["clauseIds"]
    assert set(x_mark["observedDecisionFields"]) == {
        "outcome", "endConditionDetected", "lockFurtherPlayInput",
        "promptEndDeclaration", "automaticallyEndsGame", "xMark",
    }
    for case in contract["cases"]:
        decision = case["decision"]
        expected = branches[case["branchId"]]
        assert decision[automatic["field"]] is automatic["expected"]
        assert decision["lockFurtherPlayInput"] is expected["lockFurtherPlayInput"]
        assert decision["promptEndDeclaration"] is expected["promptEndDeclaration"]
        assert decision["xMark"] == x_by_branch[case["branchId"]]["value"]
        assert set(decision) == set(x_mark["observedDecisionFields"])
    counts, _, reachable, observed = checker._game_end_measure(
        ROOT, contract, declaration
    )
    assert counts["cases"] == 248
    assert counts["covered"] == counts["reachable"] == 1542
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
    assert len(state["cases"]) == 116
    assert len(contract["cases"]) == 248
    assert all("caseId" not in item and "inputCoordinate" not in item for item in entries)
    assert all("保証範囲外" in item["claimBoundary"]["notGuaranteed"] for item in entries)
    checker._check_game_end_validation_errors(ROOT, contract, declaration, state)
    counts, _, _, _ = checker._game_end_measure(ROOT, contract, declaration)
    assert counts["cases"] == 248
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
    """拒否要求を正常ケースへ追加してもcase schemaで受理しない。"""
    contract = _asset("game_end_contract_v1.json")
    contract["cases"].append(copy.deepcopy(contract["validationErrors"][0]))
    with pytest.raises(checker.RequiredSetCoverageError, match="schema違反"):
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


def test_step95_x_mark_case_drift_is_rejected() -> None:
    """caseだけのX表記の変異を分岐別期待値との照合で検出する。"""
    contract = _asset("game_end_contract_v1.json")
    contract["cases"][0]["decision"]["xMark"] = "x-mark"
    with pytest.raises(checker.RequiredSetCoverageError, match="X表記が分岐別期待値と不一致"):
        checker.check_game_end_coverage(ROOT, contract=contract)


def test_step95_x_mark_normative_row_drift_is_rejected() -> None:
    """規範行だけのX表記の変異を典拠別期待値との照合で検出する。"""
    contract = _asset("game_end_contract_v1.json")
    contract["decisionRows"][0]["decision"]["xMark"] = "x-mark"
    with pytest.raises(
        checker.RequiredSetCoverageError, match="規範行のX表記が典拠別期待値と不一致"
    ):
        checker.check_game_end_coverage(ROOT, contract=contract)


def test_step95_x_mark_schema_enum_drift_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """schemaのenumと被覆宣言の不一致を拒否する。"""
    schema = _asset("game_end_contract_schema_v1.json")
    decision_schema = schema["$defs"]["gameEndDecision"]
    decision_schema["properties"]["xMark"]["enum"] = ["recorded-score", "x-mark"]
    original_document = checker._document

    def changed_document(root: Path, name: str) -> dict[str, Any]:
        if name == "game_end_contract_schema_v1.json":
            return schema
        return original_document(root, name)

    monkeypatch.setattr(checker, "_document", changed_document)
    with pytest.raises(checker.RequiredSetCoverageError, match="X表記の出力宣言がschemaと不一致"):
        checker.check_game_end_coverage(ROOT)


def test_step93_two_new_branches_keep_their_frozen_coverage_record() -> None:
    """新軸導入後もステップ93・94の受理済み被覆値を保持する。"""
    record = _asset("game_end_input_coverage_v1.json")
    assert record["history"][0]["after"]["coveredCount"] == 763
    assert record["history"][1]["after"]["coveredCount"] == 1015
    assert record["history"][0]["after"] == record["history"][1]["before"]


def test_step94_cold_cases_keep_their_frozen_coverage_record() -> None:
    """COLD-08の既存34ケースと被覆履歴を変更しない。"""
    contract = _asset("game_end_contract_v1.json")
    cases = [case for case in contract["cases"] if case["branchId"] == "COLD-08"]
    record = _asset("game_end_input_coverage_v1.json")
    assert len(cases) == 34
    assert record["history"][1]["after"]["caseCount"] == 170
    assert record["history"][1]["after"]["coveredCount"] == 1015


def test_step26_walk_off_and_cold09_rows_are_unique() -> None:
    """walk-offとCOLD-09の行は各1件で、成立段数2を固定する。"""
    contract = _asset("game_end_contract_v1.json")
    rows = contract["decisionRows"]
    assert [row["branchId"] for row in rows if row["branchId"].startswith("COLD-")] == [
        "COLD-08", "COLD-09"
    ]
    assert [row["branchId"] for row in rows if row["decision"]["outcome"] == "walk-off"] == [
        "GAME-END-WALK-OFF"
    ]
    cold09 = next(row for row in rows if row["branchId"] == "COLD-09")
    assert cold09["sourceClauseIds"] == ["req:F-1"]
    assert cold09["decision"] == {
        "outcome": "cold-end",
        "endConditionDetected": True,
        "lockFurtherPlayInput": True,
        "promptEndDeclaration": True,
        "automaticallyEndsGame": False,
        "xMark": "x-mark",
    }
    assert "{10点, 5回}" in cold09["remarks"]
    assert "{7点, 7回}" in cold09["remarks"]
    assert checker._fixed_game_end_values(cold09, {
        "gameEnd.regulationInnings", "gameEnd.coldConditions",
        "gameEnd.satisfiedColdTierCount", "gameEnd.extensionLimit", "gameEnd.tiebreak",
    })["gameEnd.coldConditions"] == '"tier-count:2"'
    assert checker._fixed_game_end_values(cold09, {
        "gameEnd.regulationInnings", "gameEnd.coldConditions",
        "gameEnd.satisfiedColdTierCount", "gameEnd.extensionLimit", "gameEnd.tiebreak",
    })["gameEnd.satisfiedColdTierCount"] == "2"
    assert any(case["branchId"] == "COLD-08" for case in contract["cases"])
    assert len([case for case in contract["cases"] if case["branchId"] == "COLD-09"]) == 34
    changed = copy.deepcopy(contract)
    changed["decisionRows"][0]["decision"]["outcome"] = "walk-off"
    with pytest.raises(checker.RequiredSetCoverageError, match="walk-off行"):
        checker.check_game_end_coverage(ROOT, contract=changed)
    added_cold09 = copy.deepcopy(contract)
    new_row = copy.deepcopy(next(row for row in rows if row["branchId"] == "COLD-08"))
    new_row["branchId"] = "COLD-10"
    added_cold09["decisionRows"].append(new_row)
    with pytest.raises(checker.RequiredSetCoverageError, match="COLD行集合"):
        checker.check_game_end_coverage(ROOT, contract=added_cold09)


def test_step94_unmet_reason_and_scoring_rule_are_recorded() -> None:
    """walk-offとCOLD-09の解決、得点値の送り先を宣言へ固定する。"""
    declaration = _asset("game_end_coverage_declaration_v1.json")
    unmet = declaration["step94UnmetCriteria"]
    assert unmet["walkOff"]["ownerStep"] == 46
    assert unmet["walkOff"]["status"] == "resolved-decision-row"
    assert unmet["walkOff"]["resolutionStep"] == 25
    assert unmet["walkOff"]["resolvedBranchId"] == "GAME-END-WALK-OFF"
    assert "design:step67-68-po-decision" in unmet["walkOff"]["sources"]
    assert unmet["cold09"]["ownerStage"] == 2
    assert unmet["cold09"]["status"] == "resolved-decision-row"
    assert unmet["cold09"]["resolutionStep"] == 26
    assert unmet["cold09"]["resolvedBranchId"] == "COLD-09"
    assert "gameEnd.satisfiedColdTierCount" in unmet["cold09"]["reason"]
    assert unmet["walkOffScoring"]["sourceClauseId"] == "req:A-1"
    assert unmet["walkOffScoring"]["status"] == "deferred-to-step32"
    assert "ステップ32" in unmet["walkOffScoring"]["stage2Acceptance"]
    assert "決勝点" in unmet["walkOffScoring"]["rule"]
    assert "OUT3-*" in unmet["walkOffScoring"]["ordering"]


def test_step94_unfixed_axis_values_contract_by_exact_set() -> None:
    """旧軸の縮小履歴20→18件と、現行5軸の未固定18件を照合する。"""
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
            for alternative in checker._fixed_game_end_alternatives(row, game_axes)
            for axis, value in alternative.items()
        }
        return all_values - fixed

    before = unfixed(contract["decisionRows"][:4])
    after = unfixed(contract["decisionRows"])
    declared = {
        (item["axisId"], item["valueIdentity"])
        for item in declaration["unfixedGameEndAxisValues"]
    }
    assert len(before) == 24
    assert len(after) == 18
    assert after == declared
    assert before - after == {
        ("gameEnd.coldConditions", '"tier-count:1"'),
        ("gameEnd.coldConditions", '"tier-count:2"'),
        ("gameEnd.satisfiedColdTierCount", "1"),
        ("gameEnd.satisfiedColdTierCount", "2"),
        ("gameEnd.extensionLimit", '"none"'),
        ("gameEnd.extensionLimit", '"finite:R"'),
    }
    assert {
        (item["axisId"], item["valueIdentity"])
        for item in declaration["step94Contraction"]["removedAxisValues"]
    } == {
        ("gameEnd.coldConditions", '"tier-count:1"'),
        ("gameEnd.extensionLimit", '"none"'),
    }


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
    with pytest.raises(checker.RequiredSetCoverageError, match="独立被覆"):
        checker.check_game_end_coverage(ROOT, record=drifted)
    changed = copy.deepcopy(contract)
    changed["cases"][4]["inputCoordinate"]["state.outs"] = 2
    with pytest.raises(checker.RequiredSetCoverageError, match="代表値展開"):
        checker.check_game_end_coverage(ROOT, contract=changed)


def test_game_end_coverage_history_is_one_append_from_prior_step() -> None:
    """直前の被覆履歴を保持し、この変更を1件だけ追記する。"""
    relative = "contracts/state-transition/game_end_input_coverage_v1.json"
    previous: dict[str, Any] | None = None
    revisions = subprocess.run(
        ["git", "log", "--format=%H", "--", relative],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for revision in revisions:
        result = subprocess.run(
            ["git", "show", f"{revision}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            candidate = json.loads(result.stdout)
            if candidate["currentStep"] == 100:
                previous = candidate
                break
    assert previous is not None
    current = _asset("game_end_input_coverage_v1.json")
    assert current["history"][:-1] == previous["history"]
    assert len(current["history"]) == len(previous["history"]) + 1


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
    baseline = checker.check_game_end_coverage(ROOT)
    counts, _, _, _ = checker._game_end_measure(
        ROOT, expanded, declaration, classify=False
    )
    assert counts["reachable"] > baseline["reachable"]
    assert counts["unreachable"] < baseline["unreachable"]


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
    """①の49要求・44規範行の差分5件は宣言で全件説明される。"""
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)


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
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)


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
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)
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
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)
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
    runner_rows = contract["matrixRows"][33:42]
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
    """ステップ85時点の被覆履歴が据え置きだったことを確かめる。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")

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
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)


def test_step86_game_end_declaration_cases_and_input_coverage() -> None:
    """FR-010の2行からケースを展開し、②の増分2件を実測する。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    target_rows = [
        row for row in contract["operationRows"]
        if row["operationKind"] == "game-end-declaration"
    ]
    assert len(target_rows) == 3
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
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)
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
    assert len(contract["operationRows"]) == 10
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
        176, record["history"][-1]["after"]["digest"], 6
    )
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step85_rejects_a_new_tiebreak_start_row() -> None:
    """FR-009 の操作行を欠いた現行契約を拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    contract["operationRows"] = [
        row for row in contract["operationRows"]
        if row["operationKind"] != "tiebreak-start"
    ]
    contract["cases"] = [
        case for case in contract["cases"]
        if case["inputCoordinate"].get("operationKind") != "tiebreak-start"
    ]
    _assert_no_tiebreak_start_row(contract)
    with pytest.raises(checker.RequiredSetCoverageError, match="操作欠落の典拠宣言が不足"):
        checker.check_input_coverage_exact(ROOT, contract)


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
    """空履歴の規範行が先頭に保持されていることを固定する。"""
    assert contract["undoRows"][0]["guaranteeMode"] == "full-equality"
    assert contract["undoRows"][0]["targetKind"] == "none"


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
    historical = [
        case for case in contract["cases"]
        if case["inputCoordinate"].get("operationKind") != "tiebreak-start"
    ]
    assert historical[:95] + [historical[96]] == cases
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

    assert record["currentStep"] == 95
    assert [item["step"] for item in record["history"][:15]] == list(range(79, 94))
    assert [item["step"] for item in record["history"][:16]] == list(range(79, 95))
    assert [item["step"] for item in record["history"]] == list(range(79, 96))
    current = next(item for item in record["history"] if item["step"] == 88)
    previous = next(item for item in record["history"] if item["step"] == 87)
    assert current["before"] == previous["after"]
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
    assert checker.check_input_coverage(ROOT) == (176, record["history"][-1]["after"]["digest"], 6)
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)
    policy = expander.dependency_checker.load_policy(ROOT)
    assert trace.observed_read_paths == policy.expanders[
        "state-transition-cases"
    ].allowed_read_paths


def test_step24_draw05_operation_case_preserves_input_coverage() -> None:
    """DRAW-05の同点終了宣言行を派生caseと被覆履歴へ結び付ける。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    cases, _ = expander.expand_traced(
        ROOT, limit=42, mode="coverage", operation_limit=7, undo_limit=1
    )
    historical = [
        case for case in contract["cases"]
        if case["inputCoordinate"].get("operationKind") != "tiebreak-start"
    ]
    assert historical[:97] == cases
    assert len(cases) == 97
    draw_case = cases[-2]
    assert draw_case["inputCoordinate"]["state.score"] == "tie"
    assert draw_case["expected"]["operationResult"] == "applied"
    effects = draw_case["expected"]["stateEffect"]["stateFields"]
    assert effects["state.gameEnded"] == {"kind": "set", "value": True}
    assert effects["state.score"] == {"kind": "unchanged"}
    step90 = next(item for item in record["history"] if item["step"] == 90)
    assert step90["before"] == step90["after"]
    assert checker.check_input_coverage(ROOT)[2] == 6


def test_step24_draw05_cross_layer_binding_fails_closed_on_case_drift() -> None:
    """DRAW-05の状況判定case参照をずらすと被覆検査が拒否する。"""
    declaration = _asset("game_end_coverage_declaration_v1.json")
    draw = next(
        item for item in declaration["uncoveredClauseBranches"]
        if item["branchId"] == "DRAW-05"
    )
    draw["crossLayerResolution"]["caseId"] = "ST-UNKNOWN"
    with pytest.raises(checker.RequiredSetCoverageError, match="DRAW-05の状況判定の行参照"):
        checker.check_game_end_coverage(ROOT, declaration=declaration)


def test_step30_rejects_liveness_only_on_empty_history_row() -> None:
    """空履歴行をliveness-onlyへ変えるとXC-09で拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    changed = copy.deepcopy(contract)
    changed["undoRows"][0]["guaranteeMode"] = "liveness-only"
    with pytest.raises(expander.history_checker.HistoryEffectError, match="XC-09"):
        expander.history_checker.validate_rows(
            changed, _asset("input_axes_descriptor_v1.json")
        )


def test_step30_liveness_case_with_only_d_plays_is_red() -> None:
    """シナリオ長D+1を宣言して4件しか積まないcaseを拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    liveness = next(
        item for item in contract["cases"]
        if item["expected"].get("guaranteeMode") == "liveness-only"
    )
    liveness["historyInput"]["stack"].pop()
    with pytest.raises(checker.RequiredSetCoverageError, match="XC-09"):
        checker.check_input_coverage(ROOT, contract=contract)


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
    case = copy.deepcopy(next(
        item for item in _asset("state_transition_contract_v1.json")["cases"]
        if item["rowRef"]["layer"] == "undoRows"
        and item["rowRef"]["coordinate"]["targetKind"] == "none"
    ))
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


@pytest.mark.parametrize("undo_limit", [-1, 11])
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


@pytest.mark.parametrize("operation_limit", [-1, 11])
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


def test_step103_coverage_count_changed_by_one_is_red() -> None:
    """②の被覆件数だけを1増やすと件数照合の述語が拒否する。"""
    contract = _asset("state_transition_contract_v1.json")
    record = _asset("required_set_input_coverage_v1.json")
    snapshot = record["history"][-1]["after"]
    original_digest = snapshot["digest"]
    assert original_digest == checker._digest(checker._identity_set(snapshot["coverageSet"]))
    snapshot["count"] += 1
    assert snapshot["digest"] == original_digest
    assert snapshot["count"] == len(snapshot["coverageSet"]) + 1

    with pytest.raises(
        checker.RequiredSetCoverageError, match="被覆集合の件数またはdigestが不一致"
    ):
        checker.check_input_coverage(ROOT, contract, record)


def test_step102_both_required_set_differences_are_empty() -> None:
    """①の宣言除外と②の規則除外を実資産で共に検査する。"""
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)
    assert checker.check_input_coverage_exact(ROOT) == _current_exact_input_counts()


def test_step102_row_requirement_difference_is_red() -> None:
    """①の未充足宣言を1件欠かすと①のexact-setだけが赤になる。"""
    declaration = _asset("required_set_coverage_declaration_v1.json")
    declaration["uncoveredRowRequirements"].pop()
    with pytest.raises(checker.RequiredSetCoverageError, match="未充足宣言がexact-set不一致"):
        checker.check_row_requirements(
            ROOT, _asset("state_transition_contract_v1.json"), declaration
        )
    assert checker.check_input_coverage_exact(ROOT) == _current_exact_input_counts()


def test_step102_input_coordinate_difference_is_red_when_row_is_added() -> None:
    """②は新行が未固定値を受け持つと除外を縮め、未被覆を赤にする。"""
    contract = _asset("state_transition_contract_v1.json")
    assert checker.check_input_coverage_exact(ROOT) == _current_exact_input_counts()
    assert ("state.count.balls", "1") not in _observed_coverage(contract["cases"], contract)
    added = copy.deepcopy(contract["matrixRows"][0])

    def change_balls(predicate: dict[str, Any]) -> bool:
        if predicate.get("op") == "eq" and predicate.get("axisId") == "state.count.balls":
            predicate["value"] = 1
            return True
        return any(
            change_balls(child) for child in predicate.get("args", [])
            if isinstance(child, dict)
        )

    assert change_balls(added["precondition"])
    contract["matrixRows"].append(added)
    with pytest.raises(
        checker.RequiredSetCoverageError, match="②の規則除外後の差分がexact-set不一致"
    ) as error:
        checker.check_input_coverage_exact(ROOT, contract)
    assert "('state.count.balls', '1')" in str(error.value)
    assert checker.check_input_coverage_exact(ROOT) == _current_exact_input_counts()
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)


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


@pytest.mark.parametrize("raw_result", ("単打", "batting-result.single"))
def test_game_end_display_names_resolves_closed_id_without_changing_raw(
    tmp_path: Path, raw_result: str
) -> None:
    """従来の表示名と閉入力IDを同じ語彙へ結び、原入力は保持する。"""
    state = tmp_path / "contracts/state-transition/state_transition_contract_v1.json"
    vocabulary = tmp_path / "contracts/vocabulary/input_vocabulary_v1.json"
    state.parent.mkdir(parents=True)
    vocabulary.parent.mkdir(parents=True)
    case = {"normalized": {"resultId": "batting-result.single"},
            "raw": {"resultId": raw_result}}
    content = json.dumps({"cases": [case]}, ensure_ascii=False)
    state.write_text(content, encoding="utf-8")
    vocabulary.write_text(json.dumps({"axes": [{"entries": [
        {"id": "batting-result.single", "initialDisplayName": "単打"}
    ]}]}), encoding="utf-8")
    assert checker._game_end_display_names(tmp_path) == {"batting-result.single": "単打"}
    assert state.read_text(encoding="utf-8") == content


def test_game_end_display_names_rejects_unknown_closed_id(tmp_path: Path) -> None:
    """未知のIDを表示名へ推測変換しない。"""
    state = tmp_path / "contracts/state-transition/state_transition_contract_v1.json"
    vocabulary = tmp_path / "contracts/vocabulary/input_vocabulary_v1.json"
    state.parent.mkdir(parents=True)
    vocabulary.parent.mkdir(parents=True)
    state.write_text(json.dumps({"cases": [
        {"normalized": {"resultId": "unknown"}, "raw": {"resultId": "unknown"}}
    ]}), encoding="utf-8")
    vocabulary.write_text(json.dumps({"axes": []}), encoding="utf-8")
    with pytest.raises(checker.RequiredSetCoverageError, match="一意でない"):
        checker._game_end_display_names(tmp_path)


def _row_refinement_identities(
    contract: dict[str, Any], declaration: dict[str, Any],
) -> list[tuple[str, str, str]]:
    """原観測の親と精密化後のidentityを同じ実行bodyで照合する。"""
    requirements, _ = checker.deriver.derive_repository_row_requirements(ROOT)
    required = {(item.result_id, item.partition_rule_id, item.partition_id): item
                for item in requirements}
    observations = declaration["rowPartitionObservations"]
    refinements = checker._validated_row_refinements(
        ROOT, declaration["rowPartitionRefinements"], required,
        [checker._identity(item) for item in observations],
    )
    special = {item["vocabularyId"] for item in observations}
    return [checker._refined_partition(
        row, checker._observed_partition(row, observations)
        if row["resultId"] in special else (row["resultId"], "identity", "identity"),
        refinements,
    ) for row in contract["matrixRows"]]


def test_row_partition_refinement_preserves_old44_and_unique_new5() -> None:
    """旧親identityを保持し、RBI原観測だけで追加5行を一対一に区別する。"""
    contract = _asset("state_transition_contract_v1.json")
    declaration = _asset("required_set_coverage_declaration_v1.json")
    observations = declaration["rowPartitionObservations"]
    assert len(observations) == 7
    special = {item["vocabularyId"] for item in observations}
    old_identities = [checker._observed_partition(row, observations)
                      if row["resultId"] in special
                      else (row["resultId"], "identity", "identity")
                      for row in contract["matrixRows"][:44]]
    actual = _row_refinement_identities(contract, declaration)
    assert actual[:44] == old_identities
    assert actual[42] == ("batting-result.single", "identity", "out3-explicit-home-before")
    assert [identity[2] for identity in actual[44:]] == [
        item["partitionId"] for item in declaration["rowPartitionRefinements"]
    ]
    assert len(actual) == len(set(actual)) == 49
    assert len(declaration["uncoveredRowRequirements"]) == 5
    assert checker.check_row_requirements(ROOT) == (54, 49, 0)


@pytest.mark.parametrize("mutation", [
    "unknown-parent", "unknown-child", "duplicate-child", "empty-selector",
    "unknown-axis", "duplicate-axis", "wrong-bool-type", "unknown-value",
    "extra-refinement-key", "extra-selector-key", "missing-parent-key",
    "unknown-clause", "empty-clause", "multiple-child-matches",
    "selector-missing-child", "all-refinements-missing",
])
def test_row_partition_refinement_rejects_ambiguous_or_unknown_observations(
    mutation: str,
) -> None:
    """曖昧さ・型変換・selector不足を重複のset化で救済しない。"""
    declaration = _asset("required_set_coverage_declaration_v1.json")
    refinements = declaration["rowPartitionRefinements"]
    first = refinements[0]
    if mutation == "unknown-parent":
        first["parent"]["partitionId"] = "unknown"
    elif mutation == "unknown-child":
        first["partitionId"] = "unknown"
    elif mutation == "duplicate-child":
        refinements.append(copy.deepcopy(first))
    elif mutation == "empty-selector":
        first["all"] = []
    elif mutation == "unknown-axis":
        first["all"][0]["axisId"] = "unknown.axis"
    elif mutation == "duplicate-axis":
        first["all"].append(copy.deepcopy(first["all"][0]))
    elif mutation == "wrong-bool-type":
        first["all"][0]["value"] = 1
    elif mutation == "unknown-value":
        first["all"][0]["value"] = "not-an-observation"
    elif mutation == "extra-refinement-key":
        first["rowId"] = "direct-answer-forbidden"
    elif mutation == "extra-selector-key":
        first["all"][0]["rowId"] = "direct-answer-forbidden"
    elif mutation == "missing-parent-key":
        del first["parent"]["partitionRuleId"]
    elif mutation == "unknown-clause":
        first["sourceClauseIds"] = ["req:UNKNOWN"]
    elif mutation == "empty-clause":
        first["sourceClauseIds"] = []
    elif mutation == "multiple-child-matches":
        first["all"] = copy.deepcopy(refinements[1]["all"])
    elif mutation == "selector-missing-child":
        refinements.pop()
    else:
        declaration.pop("rowPartitionRefinements")
    with pytest.raises(checker.RequiredSetCoverageError):
        checker.check_row_requirements(
            ROOT, _asset("state_transition_contract_v1.json"), declaration,
        )


def test_row_partition_refinement_missing_leaf_is_not_inferred() -> None:
    """観測葉欠落は旧parentへ留まり、重複拒否を維持する。"""
    contract = _asset("state_transition_contract_v1.json")
    predicate = contract["matrixRows"][44]["precondition"]
    predicate["args"] = [item for item in predicate["args"]
                         if item.get("axisId") != "event.perPitch.rbi.runnerContinuityByRunner"]
    with pytest.raises(checker.RequiredSetCoverageError, match="行要求区分が重複"):
        checker.check_row_requirements(ROOT, contract)


def test_row_partition_refinement_duplicate_normative_row_is_still_rejected() -> None:
    """子区分に同じ行を複製しても従来の重複拒否を回避しない。"""
    contract = _asset("state_transition_contract_v1.json")
    contract["matrixRows"].append(copy.deepcopy(contract["matrixRows"][44]))
    with pytest.raises(checker.RequiredSetCoverageError, match="行要求区分が重複"):
        checker.check_row_requirements(ROOT, contract)


def test_rbi_coverage_append_preserves_history_and_six_observed_values() -> None:
    """旧16記録を基線にした追加6被覆と現在宣言だけを照合する。"""
    record = _asset("required_set_input_coverage_v1.json")
    assert record["currentStep"] == 95
    assert [entry["step"] for entry in record["history"][:16]] == list(range(79, 95))
    assert len(record["history"]) == 17
    previous, latest = record["history"][-2:]
    assert latest["step"] == 95
    assert latest["before"] == previous["after"]
    before = {tuple(item) for item in latest["before"]["coverageSet"]}
    after = {tuple(item) for item in latest["after"]["coverageSet"]}
    assert len(before) == latest["before"]["count"] == 170
    assert len(after) == latest["after"]["count"] == 176
    assert not before - after
    assert after - before == {
        ("event.perPitch.rbi.cause_by_runner.third.held_too_long", "true"),
        ("event.perPitch.rbi.cause_by_runner.third.unnecessary_throw", "true"),
        ("event.perPitch.rbi.restart_by_runner.third.after_observing_misplay", "false"),
        ("event.perPitch.rbi.restart_by_runner.third.after_observing_misplay", "true"),
        ("event.perPitch.rbi.runnerContinuityByRunner", '"single-runner-kept-running"'),
        ("event.perPitch.rbi.runnerContinuityByRunner", '"single-runner-stopped-and-restarted"'),
    }
    assert latest["before"]["digest"] == checker._digest(before)
    assert latest["after"]["digest"] == checker._digest(after)
    contract = _asset("state_transition_contract_v1.json")
    assert after == _observed_coverage(contract["cases"], contract)
    assert checker.check_input_coverage(ROOT) == (176, checker._digest(after), 6)


_ORDINARY_CASE_IDS = {
    "ST-MATRIX-07c1f26a645dae53": "ST-MATRIX-d9d9eed7a690d48d",
    "ST-MATRIX-fc643ce7a079df4f": "ST-MATRIX-46ce2f059dfc233d",
    "ST-MATRIX-2bc8d110689a88e4": "ST-MATRIX-b931c9ca96959a1e",
    "ST-MATRIX-0529a0eb116d64a9": "ST-MATRIX-99b1523fb41399e3",
    "ST-COVERAGE-5ffabae886307443": "ST-COVERAGE-baf65198d047cf8a",
    "ST-COVERAGE-07195169e423e561": "ST-COVERAGE-f709e5fc1069d6ac",
    "ST-COVERAGE-9e3198e12b1d2e23": "ST-COVERAGE-8c8d497a5880b267",
    "ST-COVERAGE-9999f9fbf18b91f6": "ST-COVERAGE-01ea03a03cd16776",
    "ST-COVERAGE-459bc92fd7655892": "ST-COVERAGE-0d22f0ed34b83a2e",
    "ST-COVERAGE-a6919767c2d92d6c": "ST-COVERAGE-f1078be57353ce09",
    "ST-COVERAGE-68907918cdcec80e": "ST-COVERAGE-b1e096211962a847",
    "ST-COVERAGE-74908e4c51a7dd84": "ST-COVERAGE-a0b70e858a97e151",
}


def _ordinary_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    """旧Git原本を保ち、受理候補の4guard/12ID/B1一件だけを合成する。"""
    raw = subprocess.check_output(
        ["git", "show", "30f67cbc:contracts/state-transition/state_transition_contract_v1.json"],
        cwd=ROOT,
    )
    contract = json.loads(raw)
    import hashlib

    def broaden(node: Any) -> None:
        if isinstance(node, dict):
            coordinate = node.get("coordinate", node)
            if coordinate.get("resultId") in {
                "batting-result.called-pitch", "batting-result.swinging-strike",
                "batting-result.foul", "batting-result.ball",
            } and "precondition" in coordinate:
                for leaf in coordinate["precondition"]["args"]:
                    axis = leaf.get("axisId")
                    if axis in {"state.count.strikes", "state.count.balls"}:
                        values = [0, 1, 2] if coordinate["resultId"] == "batting-result.ball" else (
                            [0, 1] if axis == "state.count.strikes" else [0, 1, 2, 3]
                        )
                        leaf.clear()
                        leaf.update(op="in", axisId=axis, values=values)
            for value in list(node.values()):
                broaden(value)
        elif isinstance(node, list):
            for value in node:
                broaden(value)

    broaden(contract)
    for case in contract["cases"]:
        case["caseId"] = _ORDINARY_CASE_IDS.get(case["caseId"], case["caseId"])
    added = copy.deepcopy(next(case for case in contract["cases"]
                               if case["caseId"] == "ST-MATRIX-b931c9ca96959a1e"))
    added["caseId"] = "ST-COVERAGE-8d5c59594f90b5bd"
    for surface in ("inputCoordinate", "raw", "normalized"):
        added[surface]["state.count.balls"] = 1
    for surface in ("before", "after"):
        added["historyInput"][surface]["stateFields"]["state.count.balls"] = 1
    contract["cases"].append(added)
    asset = {
        "schemaVersion": 1, "operation": "deriveOrdinaryPitch",
        "caseIdMigrations": {
            "baselineCommit": "30f67cbc0afbdae00919606a17439d64fa7e9832",
            "baselineContractSHA256": hashlib.sha256(raw).hexdigest(),
            "caseIds": copy.deepcopy(_ORDINARY_CASE_IDS),
        },
    }
    return contract, asset


def test_ordinary_finite_guards_realize_b1_without_free_operation_fill() -> None:
    """有限inが新B1を実現し、旧全要求228から除外だけが1減る。"""
    contract, _ = _ordinary_fixture()
    assert checker.check_input_coverage_exact(ROOT, contract) == (228, 51, 0)
    for row in contract["matrixRows"][:4]:
        for leaf in row["precondition"]["args"]:
            if leaf.get("axisId") == "state.count.balls":
                leaf.clear()
                leaf.update(op="eq", axisId="state.count.balls", value=0)
    with pytest.raises(checker.RequiredSetCoverageError):
        checker.check_input_coverage_exact(ROOT, contract)


@pytest.mark.parametrize("wrapper", ("not", "or"))
def test_finite_in_under_negation_or_choice_does_not_bind_free_axis(wrapper: str) -> None:
    """否定や選言を、正の有限状態軸束縛へ流用しない。"""
    leaf = {"op": "in", "axisId": "state.count.balls", "values": [0, 1]}
    assert checker._row_finite_input_values(
        {"op": wrapper, "args": [leaf]}, "state.count.balls"
    ) == set()


@pytest.mark.parametrize("values", ([], [0, 0], None))
def test_finite_in_empty_duplicate_and_non_array_are_rejected(values: Any) -> None:
    """有限inの未束縛・重複・異型を成功にしない。"""
    with pytest.raises(checker.RequiredSetCoverageError):
        checker._row_finite_input_values(
            {"op": "in", "axisId": "state.count.balls", "values": values},
            "state.count.balls",
        )


def test_ordinary_case_migration_preserves_old_full_values_and_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧代表IDを黙って置換せず、Git原本との12件全値同値から解決する。"""
    contract, asset = _ordinary_fixture()
    original = checker._document
    monkeypatch.setattr(checker, "_document", lambda root, name: asset
                        if name == "ordinary_pitch_vectors_v1.json" else original(root, name))
    assert checker._ordinary_case_id_migrations(ROOT, contract) == _ORDINARY_CASE_IDS


@pytest.mark.parametrize("mutation", (
    "missing", "duplicate", "wrong-target", "wrong-git", "wrong-digest",
    "input", "expected", "history", "unaffected", "wrong-kind",
))
def test_ordinary_case_migration_rejects_partial_or_changed_values(
    monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    """欠落・別ID・原本不一致・入力/期待/履歴の片側変更を拒否する。"""
    contract, asset = _ordinary_fixture()
    mapping = asset["caseIdMigrations"]["caseIds"]
    ids = list(mapping)
    if mutation == "missing":
        mapping.pop(ids[0])
    elif mutation == "duplicate":
        mapping[ids[1]] = mapping[ids[0]]
    elif mutation == "wrong-target":
        mapping[ids[0]] = "ST-MATRIX-wrong"
        next(c for c in contract["cases"] if c["caseId"] == _ORDINARY_CASE_IDS[ids[0]])[
            "caseId"
        ] = "ST-MATRIX-wrong"
    elif mutation == "wrong-git":
        asset["caseIdMigrations"]["baselineCommit"] = "0" * 40
    elif mutation == "wrong-digest":
        asset["caseIdMigrations"]["baselineContractSHA256"] = "0" * 64
    elif mutation == "wrong-kind":
        asset["operation"] = "deriveState"
    else:
        case = next(c for c in contract["cases"] if c["caseId"] == mapping[ids[0]])
        if mutation == "input":
            case["inputCoordinate"]["state.count.balls"] = 1
        elif mutation == "expected":
            case["expected"]["statFlags"]["打席"] = True
        elif mutation == "history":
            case["historyInput"]["before"]["stateFields"]["state.count.balls"] = 1
        else:
            next(c for c in contract["cases"] if c["caseId"] not in mapping.values())[
                "unknown"
            ] = True
    original = checker._document
    monkeypatch.setattr(checker, "_document", lambda root, name: asset
                        if name == "ordinary_pitch_vectors_v1.json" else original(root, name))
    with pytest.raises(checker.RequiredSetCoverageError):
        checker._ordinary_case_id_migrations(ROOT, contract)


def test_ordinary_coverage_keeps_old_history_and_rejects_pending_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """177の実測と旧基線ID解決を結び、旧履歴書換えと未承認を別々に拒否する。"""
    contract, asset = _ordinary_fixture()
    original = checker._document
    monkeypatch.setattr(checker, "_document", lambda root, name: asset
                        if name == "ordinary_pitch_vectors_v1.json" else original(root, name))
    record = json.loads(subprocess.check_output([
        "git", "show", "30f67cbc:contracts/state-transition/required_set_input_coverage_v1.json"
    ], cwd=ROOT))
    historical = copy.deepcopy(record["history"])
    observed = _observed_coverage(contract["cases"], contract)
    assert len(observed) == 177
    assert observed - {tuple(item) for item in record["coverageSet"]} == {
        ("state.count.balls", "1")
    }
    after = {"coverageSet": [list(v) for v in sorted(observed)], "count": 177,
             "digest": checker._digest(observed)}
    record["history"].append({
        "step": 96, "before": copy.deepcopy(historical[-1]["after"]), "after": after,
        "change": "公開test fixture", "fact": "実測B1追加", "reason": "履歴移行対向",
        "recordedOn": None, "approvedBy": None, "approvedOn": None,
    })
    record["coverageSet"] = after["coverageSet"]
    record["currentStep"] = 96
    with pytest.raises(checker.RequiredSetCoverageError, match="承認記録"):
        checker.check_input_coverage(ROOT, contract, record)
    # これは正例testの明示fixture値であり、正式/候補受理receiptへ書かない。
    record["history"][-1].update(
        recordedOn="2000-01-01", approvedOn="2000-01-01", approvedBy="公開test fixture"
    )
    assert record["history"][:-1] == historical
    assert checker.check_input_coverage(ROOT, contract, record) == (
        177, checker._digest(observed), 1
    )
    record["history"][0]["baselineCaseIds"][0] = _ORDINARY_CASE_IDS[
        "ST-MATRIX-07c1f26a645dae53"
    ]
    with pytest.raises(checker.RequiredSetCoverageError, match="追記のみ"):
        checker.check_input_coverage(ROOT, contract, record)


def test_current_ordinary_contract_closes_all_cases_and_history_migration() -> None:
    """currentと歴史を分け、正式移行後は12全値/104不変と現177を照合する。"""
    contract = _asset("state_transition_contract_v1.json")
    vector_path = ROOT / "contracts/state-transition/ordinary_pitch_vectors_v1.json"
    if not vector_path.exists():
        assert len(contract["cases"]) == 116
        assert checker.check_input_coverage_exact(ROOT) == (228, 52, 0)
        return
    assert checker._ordinary_case_id_migrations(ROOT, contract) == _ORDINARY_CASE_IDS
    assert len(contract["cases"]) == 117
    observed = _observed_coverage(contract["cases"], contract)
    assert len(observed) == 177
    assert checker.check_input_coverage_exact(ROOT) == (228, 51, 0)
    record = _asset("required_set_input_coverage_v1.json")
    assert checker.check_input_coverage(ROOT) == (177, checker._digest(observed), 1)
    assert record["currentStep"] == 96 and len(record["history"]) == 18


def test_historical_coverage_view_uses_only_fixed_git_file_set(
    historical_coverage_root: Path,
) -> None:
    """旧Gitにないordinary vectorは実在/追跡後でも歴史viewへ混入しない。"""
    fixed = set(subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "30f67cbc"],
        cwd=_LIVE_ROOT, text=True,
    ).splitlines())
    actual = {
        p.relative_to(historical_coverage_root).as_posix()
        for p in historical_coverage_root.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(historical_coverage_root).parts
    }
    vector = "contracts/state-transition/ordinary_pitch_vectors_v1.json"
    assert vector not in fixed and vector not in actual
    assert actual <= fixed
    historical_state = (
        historical_coverage_root / "contracts/state-transition/state_transition_contract_v1.json"
    )
    assert json.loads(historical_state.read_text())["cases"] == json.loads(subprocess.check_output(
        ["git", "show", "30f67cbc:contracts/state-transition/state_transition_contract_v1.json"],
        cwd=_LIVE_ROOT, text=True,
    ))["cases"]


def test_historical_coverage_copy_rejects_live_only_vector_contamination(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """live追跡集合へ新vectorが加わる状況でも固定Git集合だけを使う。"""
    live = tmp_path / "live"
    directory = live / "contracts/state-transition"
    directory.mkdir(parents=True)
    (directory / "state_transition_contract_v1.json").write_text("{}")
    (directory / "ordinary_pitch_vectors_v1.json").write_text('{"liveOnly":true}')
    original = subprocess.check_output
    source_root = _LIVE_ROOT
    commands = []

    def git_at_live(*args: Any, **kwargs: Any) -> Any:
        command = args[0]
        commands.append(command)
        if kwargs.get("cwd") == live:
            kwargs["cwd"] = source_root
        if command == ["git", "ls-files"]:
            return "contracts/state-transition/ordinary_pitch_vectors_v1.json\n"
        return original(*args, **kwargs)

    monkeypatch.setattr(sys.modules[__name__], "_LIVE_ROOT", live)
    monkeypatch.setattr(subprocess, "check_output", git_at_live)
    view = getattr(historical_coverage_root, "__wrapped__")(tmp_path_factory)
    assert not (view / "contracts/state-transition/ordinary_pitch_vectors_v1.json").exists()
    assert not any(command == ["git", "ls-files"] for command in commands)
    assert any(command[:3] == ["git", "ls-tree", "-r"] for command in commands)
    state = view / "contracts/state-transition/state_transition_contract_v1.json"
    assert len(json.loads(state.read_text())["cases"]) == 116
