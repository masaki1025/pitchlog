"""規範行の全件展開と手作業fixtureを分岐IDで照合する。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import check_branch_row_mapping as mapping_checker
import expand_game_end_cases
import expand_state_transition_cases

ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = Path("contracts/state-transition/branch_row_mapping_v1.json")


class FixtureParityError(ValueError):
    """展開結果とfixtureの照合不一致を表す。"""


def _cross_constraint_helpers(root: Path = ROOT) -> Any:
    """既存の交差制約判定を二重実装せず読み込む。"""
    path = root / "tests/test_state_transition_contract_schema.py"
    spec = importlib.util.spec_from_file_location("fixture_parity_cross_constraints", path)
    if spec is None or spec.loader is None:
        raise FixtureParityError("交差制約判定器を読み込めない")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _key(value: Any) -> str:
    """JSON値の順序に依存しない照合キーを作る。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _assert_equal(branch_id: str, field: str, fixture: Any, expanded: Any) -> None:
    """分岐・フィールド・両値を示して完全一致を検査する。"""
    if fixture != expanded:
        raise FixtureParityError(
            f"{branch_id}: {field} 不一致: fixture={fixture!r}; expanded={expanded!r}"
        )


def check_documents(
    mapping: dict[str, Any],
    fixtures: list[dict[str, Any]],
    state_contract: dict[str, Any],
    expanded_state: list[dict[str, Any]],
    expanded_game_end: list[dict[str, Any]],
    *,
    helpers: Any | None = None,
) -> tuple[int, dict[str, list[str]]]:
    """全展開結果の正例・負例を資産の宣言へ突合する。

    Args:
        mapping: 分岐と規範行の対応表。
        fixtures: 手作業fixtureの集合。
        state_contract: 状況判定の規範行契約。
        expanded_state: 状況判定の全件展開結果。
        expanded_game_end: 終了判定の全件展開結果。
        helpers: 既存の交差制約判定器。テスト時に注入できる。

    Returns:
        正例照合件数と負例ごとの実際の違反集合。
    """
    if helpers is None:
        helpers = _cross_constraint_helpers()
    fixture_by_branch: dict[str, dict[str, Any]] = {}
    for item in fixtures:
        case = item["case"]
        branch_id = case["branchId"]
        if branch_id in fixture_by_branch:
            raise FixtureParityError(f"fixtureのbranchIdが重複: {branch_id}")
        fixture_by_branch[branch_id] = case

    entries_by_ref: dict[str, list[dict[str, Any]]] = {}
    entries_by_branch: dict[str, dict[str, Any]] = {}
    for entry in mapping["mappings"]:
        branch_id = entry["branchId"]
        if branch_id in entries_by_branch:
            raise FixtureParityError(f"対応表のbranchIdが重複: {branch_id}")
        entries_by_branch[branch_id] = entry
        if entry["fixtureRelation"] == "cross-constraint-negative":
            continue
        ref_key = _key(entry["rowRef"])
        entries_by_ref.setdefault(ref_key, []).append(entry)
    if set(fixture_by_branch) != set(entries_by_branch):
        raise FixtureParityError("fixtureと対応表のbranchId exact-setが不一致")

    expanded_by_branch: dict[str, dict[str, Any]] = {}
    for case in [*expanded_state, *expanded_game_end]:
        for entry in entries_by_ref.get(_key(case["rowRef"]), []):
            branch_id = entry["branchId"]
            if branch_id in expanded_by_branch:
                raise FixtureParityError(f"展開結果のbranchIdが重複: {branch_id}")
            if "branchId" in case and case["branchId"] != branch_id:
                raise FixtureParityError(f"展開結果のbranchIdが対応表と不一致: {branch_id}")
            expanded_by_branch[branch_id] = case

    positives = [
        entry for entry in mapping["mappings"]
        if entry["fixtureRelation"] != "cross-constraint-negative"
    ]
    if len(positives) != mapping["expectedPositiveMatches"]:
        raise FixtureParityError("正例の期待照合件数が不一致")
    matched = 0
    for entry in positives:
        branch_id = entry["branchId"]
        case = fixture_by_branch[branch_id]
        expanded = expanded_by_branch.get(branch_id)
        if expanded is None:
            raise FixtureParityError(f"対応する展開結果がない: {branch_id}")
        _assert_equal(
            branch_id, "inputCoordinate", case["inputCoordinate"], expanded["inputCoordinate"]
        )
        output_field = "decision" if entry["fixtureRelation"] == "decision-output" else "expected"
        _assert_equal(branch_id, output_field, case[output_field], expanded[output_field])
        matched += 1
    if matched != mapping["expectedPositiveMatches"]:
        raise FixtureParityError(
            f"照合件数が不一致: actual={matched}; expected={mapping['expectedPositiveMatches']}"
        )

    configuration, rules = helpers._cross_constraint_configuration()
    negative_entries = [
        entry for entry in mapping["mappings"]
        if entry["fixtureRelation"] == "cross-constraint-negative"
    ]
    if len(negative_entries) != mapping["expectedNegativeMatches"]:
        raise FixtureParityError("負例の期待照合件数が不一致")
    violation_sets: dict[str, list[str]] = {}
    for entry in negative_entries:
        branch_id = entry["branchId"]
        case = fixture_by_branch[branch_id]
        if case["expected"] != {"rejectedBy": branch_id}:
            raise FixtureParityError(f"{branch_id}: rejectedByが分岐宣言と不一致")
        row = mapping_checker._unique_rows(
            state_contract["matrixRows"], entry["rowRef"]["coordinate"]
        )
        candidate = helpers._manual_fixture_candidate(case, row)
        coordinate = case["inputCoordinate"]
        candidate_input = {
            key: value for key, value in coordinate.items() if key != "candidateEffects"
        }
        if any(
            generated["inputCoordinate"] == candidate_input
            and generated["expected"] == coordinate["candidateEffects"]
            for generated in expanded_state
        ):
            raise FixtureParityError(f"{branch_id}: 展開器が負例候補を出力した")
        actual: set[str] = set()
        for rule in rules:
            if rule.get("enforcement") == "deferred-stage-2":
                continue
            try:
                violation = helpers._cross_rule_violation(candidate, rule, configuration)
            except helpers.CrossConstraintError as error:
                violation = str(error)
            if violation is not None:
                actual.add(rule["constraintId"])
        if not actual:
            raise FixtureParityError(f"{branch_id}: 負例候補が拒否されていない")
        if branch_id not in actual:
            raise FixtureParityError(
                f"{branch_id}: rejectedByが実際の違反集合にない: {sorted(actual)}"
            )
        declared = entry.get("expectedViolationIds")
        if (
            not isinstance(declared, list)
            or len(declared) != len(set(declared))
            or set(declared) != actual
        ):
            raise FixtureParityError(
                f"{branch_id}: 違反集合が不一致: declared={declared!r}; actual={sorted(actual)!r}"
            )
        violation_sets[branch_id] = sorted(actual)
    return matched, violation_sets


def check_repository(root: Path = ROOT) -> tuple[int, dict[str, list[str]]]:
    """資産・全件展開を読み、分岐被覆とfixture照合を実行する。"""
    mapping_checker.check_repository(root, MAPPING_PATH)
    mapping = mapping_checker._read_object(root, MAPPING_PATH)
    coverage = mapping_checker._read_object(root, mapping["fixtureCoveragePath"])
    fixtures = [
        item
        for source in coverage["fixtureSources"]
        for item in mapping_checker._read_object(root, source["fixturePath"])["fixtures"]
    ]
    state = mapping_checker._read_object(root, mapping["stateContractPath"])
    game_end = mapping_checker._read_object(root, mapping["gameEndContractPath"])
    expanded_state, _ = expand_state_transition_cases.expand_traced(
        root, limit=len(state["matrixRows"])
    )
    expanded_game_end, _ = expand_game_end_cases.expand_traced(
        root, limit=len(game_end["decisionRows"])
    )
    if len(expanded_state) != len(state["matrixRows"]):
        raise FixtureParityError("状況判定の全規範行を展開できていない")
    if len(expanded_game_end) != len(game_end["decisionRows"]):
        raise FixtureParityError("終了判定の全規範行を展開できていない")
    return check_documents(
        mapping, fixtures, state, expanded_state, expanded_game_end,
        helpers=_cross_constraint_helpers(root),
    )


def main(argv: list[str] | None = None) -> int:
    """照合結果を表示し、違反時は非ゼロで終了する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        matched, violation_sets = check_repository(args.root.resolve())
    except (
        FixtureParityError, mapping_checker.BranchRowMappingError,
        OSError, ValueError, KeyError,
    ) as error:
        print(f"expanded-fixture-parity: 違反: {error}", file=sys.stderr)
        return 1
    print(f"expanded-fixture-parity: OK: positives={matched}; negatives={len(violation_sets)}")
    for branch_id, actual in violation_sets.items():
        print(f"{branch_id}: {','.join(actual)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
