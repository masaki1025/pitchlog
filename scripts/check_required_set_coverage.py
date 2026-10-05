"""状況判定の行要求差分と入力座標被覆の追記記録を検査する。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import check_deriver_dependencies as deriver
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
        if layer not in ("matrixRows", "operationRows"):
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
        elif (
            coordinate.get("operationKind") != row.get("operationKind")
            or coordinate.get("event.operationPayload") != row.get("operationKind")
            or not isinstance(row.get("payloadShape"), dict)
        ):
            raise RequiredSetCoverageError("ケースの操作またはpayloadタグが規範行と不一致")
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


def main() -> int:
    """実資産に両検査を適用する。"""
    try:
        rows = check_row_requirements(ROOT)
        coverage = check_input_coverage(ROOT)
    except (
        RequiredSetCoverageError,
        deriver.DeriverDependencyError,
        representative_selection.RepresentativeSelectionError,
    ) as error:
        print(f"requiredSet被覆: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"requiredSet被覆: PASS: rows={rows}; input={coverage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
