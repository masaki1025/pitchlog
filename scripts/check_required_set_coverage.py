"""状況判定の行要求差分と入力座標被覆の追記記録を検査する。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import check_deriver_dependencies as deriver
import expand_game_end_cases
import representative_selection

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = Path("contracts/state-transition")
COVERAGE_RECORD_PATH = ASSET_DIR / "required_set_input_coverage_v1.json"


class RequiredSetCoverageError(ValueError):
    """宣言または実測した被覆が不正であることを表す。"""


def _document(root: Path, name: str) -> dict[str, Any]:
    """必須資産を読み、欠落・不正時は必ず失敗する。"""
    try:
        value = json.loads((root / ASSET_DIR / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RequiredSetCoverageError(f"宣言資産を読めない: {name}") from error
    if not isinstance(value, dict):
        raise RequiredSetCoverageError(f"宣言資産がobjectでない: {name}")
    return value


def _identity(item: dict[str, Any]) -> tuple[str, str, str]:
    """行要求の資産側identityを取得する。"""
    keys = ("vocabularyId", "partitionRuleId", "partitionId")
    if not all(isinstance(item.get(key), str) and item[key] for key in keys):
        raise RequiredSetCoverageError("行要求identityが不正")
    return (item[keys[0]], item[keys[1]], item[keys[2]])


def _predicate_value(predicate: dict[str, Any], axis_id: str) -> Any:
    """行の連言にある等値条件を一意に取り出す。"""
    if predicate.get("op") == "eq" and predicate.get("axisId") == axis_id:
        return predicate.get("value")
    if predicate.get("op") == "and":
        values = [
            _predicate_value(arg, axis_id)
            for arg in predicate.get("args", [])
            if isinstance(arg, dict)
        ]
        present = [value for value in values if value is not None]
        if len(present) == 1:
            return present[0]
    return None


def _observed_partition(
    row: dict[str, Any], observations: list[dict[str, Any]]
) -> tuple[str, str, str]:
    """資産の観測信号と規範行を突合して区分を決める。"""
    matches = []
    for item in observations:
        if item.get("vocabularyId") != row.get("resultId"):
            continue
        signal = item.get("signal")
        if not isinstance(signal, dict):
            raise RequiredSetCoverageError("行区分観測信号が不正")
        if signal.get("location") == "precondition":
            actual = _predicate_value(row["precondition"], signal.get("axisId"))
        elif signal.get("location") == "expected":
            actual = row
            for field in signal.get("field", "").split("."):
                actual = actual.get(field) if isinstance(actual, dict) else None
        else:
            raise RequiredSetCoverageError("行区分観測信号の位置が不正")
        if actual == signal.get("value") and type(actual) is type(signal.get("value")):
            matches.append(_identity(item))
    if len(matches) != 1:
        raise RequiredSetCoverageError(f"規範行の区分を一意に観測できない: {row.get('resultId')}")
    return matches[0]


def check_row_requirements(
    root: Path, contract: dict[str, Any] | None = None, declaration: dict[str, Any] | None = None
) -> tuple[int, int, int]:
    """①の実際の未充足と宣言をexact-setで比較し、GAP典拠も確かめる。"""
    contract = contract if contract is not None else _document(
        root, "state_transition_contract_v1.json"
    )
    declaration = declaration if declaration is not None else _document(
        root, "required_set_coverage_declaration_v1.json"
    )
    rules = _document(root, "required_set_row_rules_v1.json")
    register = _document(root, "gap_register_v1.json")
    if (
        declaration.get("schemaVersion") != 1
        or declaration.get("version") != "required_set_coverage_declaration_v1"
    ):
        raise RequiredSetCoverageError("行差分宣言の版が不正")
    observations = declaration.get("rowPartitionObservations")
    uncovered = declaration.get("uncoveredRowRequirements")
    rows = contract.get("matrixRows")
    if (
        not isinstance(observations, list)
        or not isinstance(uncovered, list)
        or not isinstance(rows, list)
    ):
        raise RequiredSetCoverageError("行差分宣言または規範行が不正")
    requirements, _ = deriver.derive_repository_row_requirements(root)
    required = {
        (item.result_id, item.partition_rule_id, item.partition_id): item
        for item in requirements
    }
    special_ids = {item.get("vocabularyId") for item in observations}
    if len(special_ids) != len(observations):
        raise RequiredSetCoverageError("行区分観測の語彙IDが重複")
    covered: list[tuple[str, str, str]] = []
    for row in rows:
        result_id = row.get("resultId")
        if result_id in special_ids:
            identity = _observed_partition(row, observations)
        else:
            identity = (result_id, "identity", "identity")
        if identity not in required:
            raise RequiredSetCoverageError(f"規範行が要求外の区分に属する: {identity}")
        covered.append(identity)
    if len(covered) != len(set(covered)):
        raise RequiredSetCoverageError("規範行の行要求区分が重複")
    actual_missing = set(required) - set(covered)
    declared = [_identity(item) for item in uncovered]
    if len(declared) != len(set(declared)):
        raise RequiredSetCoverageError("未充足宣言が重複")
    stale = set(declared) & set(covered)
    if stale:
        raise RequiredSetCoverageError(f"充足済みの古い未充足宣言: {sorted(stale)}")
    if actual_missing != set(declared):
        raise RequiredSetCoverageError(
            f"未充足宣言がexact-set不一致: missing={sorted(actual_missing - set(declared))}; "
            f"unexpected={sorted(set(declared) - actual_missing)}"
        )
    gap_by_id = {item.get("gapId"): item for item in register.get("gaps", [])}
    if len(gap_by_id) != len(register.get("gaps", [])):
        raise RequiredSetCoverageError("GAP IDが重複")
    rule_by_id = {item.get("partitionRuleId"): item for item in rules.get("partitionRules", [])}
    for item in uncovered:
        identity = _identity(item)
        gap = gap_by_id.get(item.get("gapId"))
        if not isinstance(gap, dict) or gap.get("state") != "open":
            raise RequiredSetCoverageError(f"未充足のopen GAPがない: {identity}")
        rule = rule_by_id.get(identity[1])
        if not isinstance(rule, dict) or identity[0] not in rule.get("vocabularyIds", []):
            raise RequiredSetCoverageError(f"分割規則が見つからない: {identity}")
        clauses = {
            source[4:] for source in rule.get("sourceClauseIds", [])
            if isinstance(source, str) and source.startswith("req:")
        }
        gap_sources = set(gap.get("clauseIds", [])) | set(gap.get("branchIds", []))
        if not clauses or not clauses & gap_sources:
            raise RequiredSetCoverageError(f"未充足GAPとの典拠交差がない: {identity}")
    return len(required), len(covered), len(actual_missing - set(declared))


def _digest(identities: set[tuple[str, str]]) -> str:
    """軸値identity集合を順序固定のJSONでハッシュ化する。"""
    data = json.dumps(sorted(identities), ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def observed_input_coverage(
    cases: list[dict[str, Any]], requirements: tuple[deriver.InputCoordinateRequirement, ...],
    contract: dict[str, Any], display_names: dict[str, str],
) -> set[tuple[str, str]]:
    """②をケースの実入力と行層から観測する。"""
    observed: set[tuple[str, str]] = set()
    for case in cases:
        reference = case.get("rowRef")
        coordinate = case.get("inputCoordinate")
        if not isinstance(reference, dict) or not isinstance(coordinate, dict):
            raise RequiredSetCoverageError("ケースの行参照または座標が不正")
        layer = reference.get("layer")
        if layer not in ("matrixRows", "operationRows", "undoRows"):
            raise RequiredSetCoverageError("ケースの行参照層が不正")
        rows = contract.get(layer)
        row_coordinate = reference.get("coordinate")
        if not isinstance(rows, list) or not isinstance(row_coordinate, dict):
            raise RequiredSetCoverageError("ケースの行参照または規範行が不正")
        matches = [
            row for row in rows
            if isinstance(row, dict)
            if all(
                row.get(key) == value
                for key, value in row_coordinate.items()
            )
        ]
        if len(matches) != 1:
            raise RequiredSetCoverageError("ケースが規範行を一意に参照しない")
        row = matches[0]
        if layer == "matrixRows":
            if (
                coordinate.get("eventKind") != row.get("eventKind")
                or coordinate.get("resultId") != row.get("resultId")
            ):
                raise RequiredSetCoverageError("ケースのイベントが規範行と不一致")
        elif layer == "operationRows" and (
            coordinate.get("operationKind") != row.get("operationKind")
            or coordinate.get("event.operationPayload") != row.get("operationKind")
            or not isinstance(row.get("payloadShape"), dict)
        ):
            raise RequiredSetCoverageError("ケースの操作またはpayloadタグが規範行と不一致")
        elif layer == "undoRows" and coordinate.get("operationKind") != "undo":
            raise RequiredSetCoverageError("ケースのundo操作種別が不一致")
        if not representative_selection.predicate_holds(row["precondition"], coordinate):
            raise RequiredSetCoverageError("ケースが規範行の前提条件を満たさない")
        expected = {
            key: value for key, value in row.items()
            if key not in (*row_coordinate, "remarks")
        }
        if case.get("expected") != expected:
            raise RequiredSetCoverageError("ケースの期待値が規範行と不一致")
        for requirement in requirements:
            if layer not in requirement.row_layers:
                continue
            axis_id = requirement.axis_id
            if requirement.natural_key_role == "predicate-axis":
                value = coordinate.get(axis_id)
            elif layer == "matrixRows" and axis_id == "event.perPitch.kind":
                value = coordinate["eventKind"]
            elif layer == "matrixRows" and axis_id == "event.perPitch.resultId":
                value = display_names.get(coordinate["resultId"])
            elif layer == "matrixRows" and axis_id == "event.operationKind":
                value = "per-pitch"
            elif layer == "matrixRows" and axis_id == "event.operationPayload":
                value = "not-applicable"
            elif layer == "operationRows" and axis_id == "event.operationKind":
                value = row[requirement.natural_key_field]
            elif layer == "operationRows" and axis_id == "event.operationPayload":
                value = coordinate[axis_id]
            elif layer == "undoRows" and axis_id == "event.operationKind":
                value = "undo"
            elif layer == "undoRows" and axis_id == "event.operationPayload":
                value = "not-applicable"
            else:
                raise RequiredSetCoverageError(f"未対応の行割当: {axis_id}")
            if (
                type(value) is type(requirement.coverage_value)
                and value == requirement.coverage_value
            ):
                observed.add(requirement.identity)
    return observed


def _identity_set(items: Any) -> set[tuple[str, str]]:
    """記録された被覆集合を読み、重複を拒否する。"""
    if not isinstance(items, list):
        raise RequiredSetCoverageError("被覆集合が配列でない")
    identities = []
    for item in items:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(value, str) for value in item)
        ):
            raise RequiredSetCoverageError("被覆identityが不正")
        identities.append((item[0], item[1]))
    if len(identities) != len(set(identities)):
        raise RequiredSetCoverageError("被覆identityが重複")
    return set(identities)


def _check_history_append_only(
    previous: dict[str, Any], current: dict[str, Any]
) -> None:
    """1回の版更新で既存記録を保持し、追加を高々1件に制限する。"""
    old = previous.get("history")
    new = current.get("history")
    if not isinstance(old, list) or not isinstance(new, list):
        raise RequiredSetCoverageError("比較元の被覆履歴が不正")
    if new[: len(old)] != old:
        raise RequiredSetCoverageError("被覆履歴が追記のみでない")
    if len(new) > len(old) + 1:
        raise RequiredSetCoverageError("1ステップに複数の被覆記録を追加した")
    if len(new) == len(old) and (
        previous.get("coverageSet") != current.get("coverageSet")
        or previous.get("identitySpec") != current.get("identitySpec")
    ):
        raise RequiredSetCoverageError("追記なしで被覆基準が変更された")


def _check_repository_history(root: Path, current: dict[str, Any]) -> None:
    """Git上の各版と作業木を突合し、履歴の書換えを拒否する。"""
    relative = COVERAGE_RECORD_PATH.as_posix()
    revisions = subprocess.run(
        ["git", "log", "--format=%H", "--", relative],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if revisions.returncode != 0:
        raise RequiredSetCoverageError("被覆記録のGit履歴を読めない")
    previous: dict[str, Any] | None = None
    for revision in reversed(revisions.stdout.splitlines()):
        result = subprocess.run(
            ["git", "show", f"{revision}:{relative}"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RequiredSetCoverageError("被覆記録の過去版を読めない")
        try:
            version = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RequiredSetCoverageError("被覆記録の過去版が不正") from error
        if not isinstance(version, dict):
            raise RequiredSetCoverageError("被覆記録の過去版がobjectでない")
        if previous is not None:
            _check_history_append_only(previous, version)
        previous = version
    if previous is None:
        if len(current["history"]) != 1:
            raise RequiredSetCoverageError("初回の被覆記録が1件でない")
    else:
        _check_history_append_only(previous, current)


def check_input_coverage(
    root: Path,
    contract: dict[str, Any] | None = None,
    record: dict[str, Any] | None = None,
) -> tuple[int, str, int]:
    """②の全体被覆集合と1ステップ1記録の単調増加を照合する。"""
    contract = contract if contract is not None else _document(
        root, "state_transition_contract_v1.json"
    )
    record = record if record is not None else _document(
        root, "required_set_input_coverage_v1.json"
    )
    requirements, _ = deriver.derive_repository_input_coordinate_requirements(root)
    active = deriver.active_input_coordinate_requirements(requirements, {"req:FR-040": "adopted"})
    vocabulary = json.loads(
        (root / "contracts/vocabulary/input_vocabulary_v1.json").read_text(encoding="utf-8")
    )
    display_names = {
        entry["id"]: entry["initialDisplayName"]
        for axis in vocabulary["axes"] for entry in axis["entries"]
    }
    cases = contract.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RequiredSetCoverageError("ケース集合が空または不正")
    actual = observed_input_coverage(cases, active, contract, display_names)
    declared = _identity_set(record.get("coverageSet"))
    required_ids = {item.identity for item in active}
    if declared != actual or not declared <= required_ids:
        raise RequiredSetCoverageError("②の実測被覆と資産側宣言が不一致")
    history = record.get("history")
    if record.get("schemaVersion") != 1 or not isinstance(history, list) or not history:
        raise RequiredSetCoverageError("②の追記記録が不正")
    prior: set[tuple[str, str]] | None = None
    previous_step = 0
    for index, entry in enumerate(history):
        step = entry.get("step")
        if not isinstance(step, int) or isinstance(step, bool) or step <= previous_step:
            raise RequiredSetCoverageError("被覆記録のステップが重複または逆行")
        previous_step = step
        before = _identity_set(entry.get("before", {}).get("coverageSet"))
        after = _identity_set(entry.get("after", {}).get("coverageSet"))
        if index == 0:
            baseline_ids = entry.get("baselineCaseIds")
            if not isinstance(baseline_ids, list) or not baseline_ids:
                raise RequiredSetCoverageError("初回被覆の基線ケースがない")
            baseline = [case for case in cases if case.get("caseId") in baseline_ids]
            measured_before = observed_input_coverage(
                baseline, active, contract, display_names
            )
            if len(baseline) != len(baseline_ids) or before != measured_before:
                raise RequiredSetCoverageError("初回被覆の直前集合が実測と不一致")
        elif before != prior:
            raise RequiredSetCoverageError("被覆記録の連鎖が不一致")
        if not before <= after:
            raise RequiredSetCoverageError("②の被覆が後退した")
        for state, identities in ((entry["before"], before), (entry["after"], after)):
            if state.get("count") != len(identities) or state.get("digest") != _digest(identities):
                raise RequiredSetCoverageError("被覆集合の件数またはdigestが不一致")
        record_fields = (
            "change", "fact", "reason", "recordedOn", "approvedBy", "approvedOn"
        )
        if not all(
            isinstance(entry.get(key), str) and entry[key] for key in record_fields
        ):
            raise RequiredSetCoverageError("被覆更新の理由・承認記録が不正")
        prior = after
    if prior != declared or record.get("currentStep") != previous_step:
        raise RequiredSetCoverageError("最終被覆記録と現行宣言が不一致")
    _check_repository_history(root, record)
    previous = _identity_set(history[-1]["before"]["coverageSet"])
    return len(actual), _digest(actual), len(actual - previous)


def _game_end_identity(value: Any) -> str:
    """導出器と同じRFC 8785の値identityを得る。"""
    return deriver.descriptor_checker._canonical_json_text(value)


def _fixed_game_end_values(
    row: dict[str, Any], axis_ids: set[str]
) -> dict[str, str]:
    """行が正の等値述語で固定する終了規則の軸値を得る。"""
    fixed: dict[str, str] = {}

    def visit(node: dict[str, Any]) -> None:
        if node.get("op") == "and":
            for child in node.get("args", []):
                visit(child)
        elif node.get("op") == "eq" and node.get("axisId") in axis_ids:
            axis = node["axisId"]
            if axis in fixed:
                raise RequiredSetCoverageError(f"終了規則軸の固定が重複: {axis}")
            fixed[axis] = _game_end_identity(node["value"])

    visit(row["precondition"])
    if set(fixed) != axis_ids:
        raise RequiredSetCoverageError("decisionRowsが終了規則4軸を固定しない")
    return fixed


def _game_end_measure(
    root: Path, contract: dict[str, Any], declaration: dict[str, Any]
) -> tuple[dict[str, int], set[tuple[str, ...]], set[tuple[str, ...]], set[tuple[str, ...]]]:
    """終了判定行の到達性と実ケースからの直接充足を独立導出する。"""
    required, _ = deriver.derive_repository_game_end_required_set(root)
    descriptor = _document(root, "input_axes_descriptor_v1.json")
    values = representative_selection.axis_values(
        descriptor, ("gameEndAxes", "stateTransitionAxes")
    )
    selection_policy = _document(root, "representative_selection_policy_v1.json")
    game_axes = {axis["axisId"] for axis in descriptor["gameEndAxes"]}
    rows = contract.get("decisionRows")
    cases = contract.get("cases")
    if not isinstance(rows, list) or not isinstance(cases, list):
        raise RequiredSetCoverageError("終了判定の行またはケースが不正")
    row_by_branch = {row["branchId"]: row for row in rows}
    if len(row_by_branch) != len(rows):
        raise RequiredSetCoverageError("終了判定の行分岐が重複")
    fixed_by_row = [_fixed_game_end_values(row, game_axes) for row in rows]
    fixed_values = {
        (axis, value) for fixed in fixed_by_row for axis, value in fixed.items()
    }
    all_values = {
        (axis, _game_end_identity(value))
        for axis in game_axes for value in values[axis]
    }
    missing_values = all_values - fixed_values
    raw_missing = declaration.get("unfixedGameEndAxisValues")
    if not isinstance(raw_missing, list):
        raise RequiredSetCoverageError("未固定の終了規則軸値宣言がない")
    if not all(
        isinstance(item, dict)
        and set(item) == {"axisId", "valueIdentity"}
        and isinstance(item["axisId"], str)
        and isinstance(item["valueIdentity"], str)
        for item in raw_missing
    ):
        raise RequiredSetCoverageError("終了規則軸値宣言の形式が不正")
    declared_values = {
        (item.get("axisId"), item.get("valueIdentity"))
        for item in raw_missing if isinstance(item, dict)
    }
    if len(declared_values) != len(raw_missing) or not declared_values <= all_values:
        raise RequiredSetCoverageError("終了規則軸値宣言が重複または値域外")
    # 行が増えて固定した軸値は宣言から自動的に消える。新しい未固定値は赤にする。
    effective_missing = declared_values & missing_values
    if effective_missing != missing_values:
        raise RequiredSetCoverageError("未固定の終了規則軸値がexact-set不一致")

    def rows_for(targets: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
        return [
            row for row, fixed in zip(rows, fixed_by_row, strict=True)
            if all(fixed.get(axis) == value for axis, value in targets if axis in game_axes)
        ]

    def reachable_coordinate(row: dict[str, Any], axis: str, identity: str) -> bool:
        if axis not in values:
            return False
        target = next(
            (value for value in values[axis] if _game_end_identity(value) == identity),
            None,
        )
        if target is None:
            return False
        predicate = {
            "op": "and",
            "args": [row["precondition"], {"op": "eq", "axisId": axis, "value": target}],
        }
        axes = [
            candidate for candidate in values
            if candidate in representative_selection.predicate_axes(predicate)
        ]
        try:
            representative_selection.select_coordinate(
                predicate, values, axes, selection_policy,
            )
        except representative_selection.RepresentativeSelectionError:
            return False
        return True

    required_ids: set[tuple[str, ...]] = {
        tuple(item.identity) for item in required.requirements
    }
    reachable: set[tuple[str, ...]] = set()
    for item in required.pairwise_requirements:
        if rows_for(((item.left_axis_id, item.left_value_identity),
                     (item.right_axis_id, item.right_value_identity))):
            reachable.add(item.identity)
    for item in required.boundary_coordinate_requirements:
        candidates = rows_for(((item.game_end_axis_id, item.game_end_value_identity),))
        if any(reachable_coordinate(row, item.coordinate_axis_id,
                                    item.coordinate_value_identity) for row in candidates):
            reachable.add(item.identity)
    for item in required.clause_branch_requirements:
        if item.branch_id in row_by_branch:
            reachable.add(item.identity)
    invalid_ids: set[tuple[str, ...]] = {
        tuple(item.identity) for item in required.invalid_boundary_requirements
    }
    if len(invalid_ids) != 12:
        raise RequiredSetCoverageError("不正値拒否の件数が裁定の12件と異なる")
    if declaration.get("deferredValidationErrors") != {
        "requirementKind": "invalid-boundary", "count": 12,
        "ownerStep": 96, "targetCollection": "validationErrors",
    }:
        raise RequiredSetCoverageError("不正値拒否12件のステップ96への移管宣言が不正")

    raw_branches = declaration.get("uncoveredClauseBranches")
    if not isinstance(raw_branches, list):
        raise RequiredSetCoverageError("条文分岐の未充足宣言がない")
    if not all(
        isinstance(item, dict)
        and set(item) == {"branchId", "gapId"}
        and isinstance(item["branchId"], str)
        and isinstance(item["gapId"], str)
        for item in raw_branches
    ):
        raise RequiredSetCoverageError("条文分岐の未充足宣言の形式が不正")
    branch_gap = {
        item.get("branchId"): item.get("gapId")
        for item in raw_branches if isinstance(item, dict)
    }
    if len(branch_gap) != len(raw_branches):
        raise RequiredSetCoverageError("条文分岐の未充足宣言が重複または不正")
    missing_branches = {
        item.branch_id for item in required.clause_branch_requirements
        if item.identity not in reachable
    }
    if set(branch_gap) != missing_branches:
        raise RequiredSetCoverageError("条文分岐の未充足宣言がexact-set不一致")
    register = _document(root, "gap_register_v1.json")
    gaps = {gap["gapId"]: gap for gap in register["gaps"]}
    if len(gaps) != len(register["gaps"]):
        raise RequiredSetCoverageError("GAP IDが重複")
    requirement_by_branch = {
        item.branch_id: item for item in required.clause_branch_requirements
    }
    for branch, gap_id in branch_gap.items():
        gap = gaps.get(gap_id)
        if (
            not isinstance(gap, dict)
            or gap.get("state") != "open"
            or branch not in gap.get("branchIds", [])
        ):
            raise RequiredSetCoverageError(f"open GAPの分岐典拠がない: {branch}")
        sources = requirement_by_branch[branch].source_clause_ids
        if not any(f"req:{clause}" in sources for clause in gap.get("clauseIds", [])):
            raise RequiredSetCoverageError(f"条文分岐のGAP典拠が不正: {branch}")

    actual_unreachable = required_ids - reachable - invalid_ids
    rule_excluded: set[tuple[str, ...]] = set()
    for item in required.pairwise_requirements:
        targets = ((item.left_axis_id, item.left_value_identity),
                   (item.right_axis_id, item.right_value_identity))
        if any(target in effective_missing for target in targets) or not rows_for(targets):
            rule_excluded.add(item.identity)
    for item in required.boundary_coordinate_requirements:
        target = (item.game_end_axis_id, item.game_end_value_identity)
        candidates = rows_for((target,))
        if target in effective_missing or not candidates or not any(
            reachable_coordinate(row, item.coordinate_axis_id,
                                 item.coordinate_value_identity) for row in candidates
        ):
            rule_excluded.add(item.identity)
    rule_excluded.update(("clause-branch", branch) for branch in branch_gap)
    if actual_unreachable != rule_excluded or declaration.get("exclusionRule") != {
        "rowLayer": "decisionRows",
        "axisValuePredicate": "no-row-fixes-game-end-axis-value",
        "combinationPredicate": "no-single-row-satisfies-all-targets-and-state-event-value",
        "onNewRow": "intersect-declared-values-with-currently-unfixed-values",
    }:
        raise RequiredSetCoverageError("規則による到達不可集合がexact-set不一致")

    observed: set[tuple[str, ...]] = set()
    for case in cases:
        row = row_by_branch.get(case.get("branchId"))
        coordinate = case.get("inputCoordinate")
        if (
            row is None or not isinstance(coordinate, dict)
            or case.get("decision") != row["decision"]
        ):
            raise RequiredSetCoverageError("終了判定ケースが規範行を参照しない")
        reference = {"layer": "decisionRows", "coordinate": {"branchId": row["branchId"]}}
        if case.get("rowRef") != reference:
            raise RequiredSetCoverageError("終了判定ケースの行参照が不正")
        if not representative_selection.predicate_holds(row["precondition"], coordinate):
            raise RequiredSetCoverageError("終了判定ケースが行前提を満たさない")
        actual = {axis: _game_end_identity(value) for axis, value in coordinate.items()}
        for item in required.pairwise_requirements:
            if (
                actual.get(item.left_axis_id) == item.left_value_identity
                and actual.get(item.right_axis_id) == item.right_value_identity
            ):
                observed.add(item.identity)
        for item in required.boundary_coordinate_requirements:
            if (
                actual.get(item.game_end_axis_id) == item.game_end_value_identity
                and actual.get(item.coordinate_axis_id) == item.coordinate_value_identity
            ):
                observed.add(item.identity)
        if ("clause-branch", row["branchId"]) in required_ids:
            observed.add(("clause-branch", row["branchId"]))
    if not observed <= reachable:
        raise RequiredSetCoverageError("終了判定ケースが到達不可要求を充足した")
    counts = {
        "total": len(required_ids), "reachable": len(reachable),
        "unreachable": len(actual_unreachable), "invalid": len(invalid_ids),
        "covered": len(observed), "cases": len(cases),
    }
    return counts, actual_unreachable, reachable, observed


def _check_game_end_documents(
    root: Path, contract: dict[str, Any], declaration: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, int]:
    """終了判定資産を独立導出結果と突合する。"""
    if (
        set(declaration) != {
            "schemaVersion", "version", "exclusionRule", "unfixedGameEndAxisValues",
            "uncoveredClauseBranches", "deferredValidationErrors", "checkerAllowedReadPaths",
            "step94Contraction", "step94UnmetCriteria",
        }
        or declaration.get("schemaVersion") != 1
        or declaration.get("version") != "game_end_coverage_declaration_v1"
    ):
        raise RequiredSetCoverageError("終了判定の除外宣言が不正")
    rows = contract.get("decisionRows", [])
    if any(row["decision"]["outcome"] == "walk-off" for row in rows):
        raise RequiredSetCoverageError("ステップ94の前提に反するwalk-off行がある")
    if {row["branchId"] for row in rows if row["branchId"].startswith("COLD-")} != {
        "COLD-08"
    }:
        raise RequiredSetCoverageError("ステップ94のCOLD行集合が不正")
    branch_register = _document(root, "clause_branch_register_v1.json")
    if branch_register.get("branchCount") != 68 or any(
        "walk-off" in branch["branchId"].lower()
        for branch in branch_register["branches"]
    ):
        raise RequiredSetCoverageError("ステップ94のサヨナラ分岐不在の前提が変わった")
    descriptor = _document(root, "input_axes_descriptor_v1.json")
    axes = {axis["axisId"] for axis in descriptor["gameEndAxes"]}
    values = representative_selection.axis_values(descriptor, ("gameEndAxes",))
    all_values = {
        (axis, _game_end_identity(value)) for axis in axes for value in values[axis]
    }
    first_four_fixed = {
        (axis, value)
        for row in rows[:4]
        for axis, value in _fixed_game_end_values(row, axes).items()
    }
    current_fixed = {
        (axis, value)
        for row in rows
        for axis, value in _fixed_game_end_values(row, axes).items()
    }
    before_unfixed = all_values - first_four_fixed
    after_unfixed = all_values - current_fixed
    removed = before_unfixed - after_unfixed
    if declaration.get("step94Contraction") != {
        "beforeRowCount": 4,
        "afterRowCount": len(rows),
        "beforeUnfixedCount": len(before_unfixed),
        "afterUnfixedCount": len(after_unfixed),
        "removedAxisValues": [
            {"axisId": axis, "valueIdentity": value} for axis, value in sorted(removed)
        ],
    } or len(removed) != 2:
        raise RequiredSetCoverageError("ステップ94の未固定軸値縮小が実測と不一致")
    unmet = declaration.get("step94UnmetCriteria")
    if not isinstance(unmet, dict) or set(unmet) != {
        "walkOff", "cold09", "walkOffScoring"
    }:
        raise RequiredSetCoverageError("ステップ94の未達記録がない")
    for key, status in (
        ("walkOff", "unmet-no-decision-row"),
        ("cold09", "unmet-no-decision-row"),
        ("walkOffScoring", "unverified-no-walk-off-row"),
    ):
        item = unmet[key]
        if (
            not isinstance(item, dict)
            or item.get("status") != status
            or not isinstance(item.get("stage2Acceptance"), str)
            or not item["stage2Acceptance"]
        ):
            raise RequiredSetCoverageError(f"ステップ94の未達記録が不正: {key}")
    if any(
        not isinstance(unmet[key].get("reason"), str)
        or not unmet[key]["reason"]
        or not isinstance(unmet[key].get("sources"), list)
        or not unmet[key]["sources"]
        for key in ("walkOff", "cold09")
    ) or any(
        not isinstance(unmet["walkOffScoring"].get(field), str)
        or not unmet["walkOffScoring"][field]
        for field in ("planReference", "currentLocation", "rule", "ordering")
    ):
        raise RequiredSetCoverageError("ステップ94の未達理由または得点規則が欠落")
    if unmet["walkOff"].get("ownerStep") != 46 or unmet["cold09"].get(
        "ownerStage"
    ) != 2 or unmet["walkOffScoring"].get("sourceClauseId") != "req:A-1":
        raise RequiredSetCoverageError("ステップ94の未達事項の典拠・送り先が不正")
    generated, trace = expand_game_end_cases.expand_coverage_traced(root)
    expander_policy = expand_game_end_cases.dependency_checker.load_policy(root)
    if trace.observed_read_paths != expander_policy.expanders["game-end-cases"].allowed_read_paths:
        raise RequiredSetCoverageError("終了判定展開器のallowedReadPathsが実測と不一致")
    if contract.get("cases") != generated:
        raise RequiredSetCoverageError("終了判定ケースが代表値展開と不一致")
    counts, _, reachable, observed = _game_end_measure(root, contract, declaration)
    baseline = {**contract, "cases": contract["cases"][:4]}
    before, _, _, before_observed = _game_end_measure(root, baseline, declaration)
    previous_cases = [
        case for case in contract["cases"]
        if case["branchId"] in {row["branchId"] for row in rows[:4]}
    ]
    previous, _, _, previous_observed = _game_end_measure(
        root, {**contract, "cases": previous_cases}, declaration
    )

    def snapshot(case_count: int, identities: set[tuple[str, ...]]) -> dict[str, Any]:
        encoded = json.dumps(sorted(identities), ensure_ascii=False, separators=(",", ":"))
        return {
            "caseCount": case_count, "coveredCount": len(identities),
            "coveredDigest": "sha256:" + hashlib.sha256(encoded.encode()).hexdigest(),
        }

    if record != {
        "schemaVersion": 1, "version": "game_end_input_coverage_v1",
        "currentStep": 94,
        "basis": "game_end_contract_v1.cases and independently derived gameEnd.requiredSet",
        "history": [
            {
                "step": 93,
                "baselineCaseIds": [case["caseId"] for case in baseline["cases"]],
                "before": snapshot(before["cases"], before_observed),
                "after": snapshot(previous["cases"], previous_observed),
            },
            {
                "step": 94,
                "baselineCaseIds": [case["caseId"] for case in previous_cases],
                "before": snapshot(previous["cases"], previous_observed),
                "after": snapshot(counts["cases"], observed),
            },
        ],
    }:
        raise RequiredSetCoverageError("終了判定の独立被覆記録が実測と不一致")
    if observed != reachable:
        raise RequiredSetCoverageError("ステップ94の到達可能要求が未充足")
    return counts


def check_game_end_coverage(
    root: Path, contract: dict[str, Any] | None = None,
    declaration: dict[str, Any] | None = None,
    record: dict[str, Any] | None = None,
) -> dict[str, int]:
    """終了判定専用の到達性宣言・被覆記録・読取経路を検査する。"""
    if contract is not None or declaration is not None or record is not None:
        return _check_game_end_documents(
            root,
            contract if contract is not None else _document(root, "game_end_contract_v1.json"),
            declaration if declaration is not None else _document(
                root, "game_end_coverage_declaration_v1.json"
            ),
            record if record is not None else _document(root, "game_end_input_coverage_v1.json"),
        )
    bootstrap = _document(root, "game_end_coverage_declaration_v1.json")
    raw_paths = bootstrap.get("checkerAllowedReadPaths")
    if (
        not isinstance(raw_paths, list)
        or not raw_paths
        or not all(isinstance(path, str) and path for path in raw_paths)
    ):
        raise RequiredSetCoverageError("終了判定検査器のallowedReadPathsが不正")
    allowed = tuple(PurePosixPath(path) for path in raw_paths)
    if len(set(allowed)) != len(allowed) or any(
        path.is_absolute() or ".." in path.parts for path in allowed
    ):
        raise RequiredSetCoverageError("終了判定検査器のallowedReadPathsが重複または不正")

    def operation() -> dict[str, int]:
        current_declaration = _document(root, "game_end_coverage_declaration_v1.json")
        if current_declaration != bootstrap:
            raise RequiredSetCoverageError("検査中に終了判定宣言が変更された")
        return _check_game_end_documents(
            root, _document(root, "game_end_contract_v1.json"),
            current_declaration, _document(root, "game_end_input_coverage_v1.json"),
        )

    result, observed = deriver.trace_allowed_file_reads(
        root, allowed, "game-end-required-set-coverage", "終了判定被覆検査器", operation
    )
    if set(observed) != set(allowed):
        raise RequiredSetCoverageError("終了判定検査器のallowedReadPathsが実測と不一致")
    return result


def main() -> int:
    """実資産に状況判定と終了判定の検査を適用する。"""
    try:
        rows = check_row_requirements(ROOT)
        coverage = check_input_coverage(ROOT)
        game_end = check_game_end_coverage(ROOT)
    except (
        RequiredSetCoverageError,
        deriver.DeriverDependencyError,
        representative_selection.RepresentativeSelectionError,
        expand_game_end_cases.CaseExpansionError,
        expand_game_end_cases.dependency_checker.ExpanderDependencyError,
    ) as error:
        print(f"requiredSet被覆: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"requiredSet被覆: PASS: rows={rows}; input={coverage}; gameEnd={game_end}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
