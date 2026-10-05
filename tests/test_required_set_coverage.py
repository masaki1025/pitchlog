"""ステップ79〜82の行要求差分と入力座標被覆を検証する。"""

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
    cases, trace = expander.expand_traced(ROOT, limit=19, mode="coverage")
    representatives, _ = expander.expand_traced(ROOT, limit=19)
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
    cases, trace = expander.expand_traced(ROOT, limit=26, mode="coverage")
    representatives, _ = expander.expand_traced(ROOT, limit=26)
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

    count, digest, added = checker.check_input_coverage(ROOT)
    assert record["currentStep"] == 82
    assert len(record["history"]) == 4
    assert record["history"][2]["after"] == record["history"][3]["before"]
    assert (count, digest, added) == (
        100,
        record["history"][3]["after"]["digest"],
        12,
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

    cases, trace = expander.expand_traced(ROOT, limit=33, mode="coverage")
    representatives, _ = expander.expand_traced(ROOT, limit=33)
    assert contract["cases"] == cases
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
