"""状況判定の行要求差分と入力座標被覆の追記記録を検査する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import check_deriver_dependencies as deriver
import expand_game_end_cases
import expand_state_transition_cases
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


def _result_display_name(value: Any, display_names: dict[str, str]) -> str | None:
    """結果の安定IDを被覆identityの表示名へ変換する。"""
    return display_names.get(value) if isinstance(value, str) else None


def check_contract_sizes(root: Path) -> dict[str, int]:
    """descriptor schemaが参照する全契約を資産側のbyte上限と比較する。

    Args:
        root: リポジトリルート。

    Returns:
        契約の相対パスと実byte数の対応。

    Raises:
        RequiredSetCoverageError: 宣言、対象集合、または実サイズが不正な場合。
    """
    policy = _document(root, "contract_size_limit_v1.json")
    schema = _document(root, "input_axes_descriptor_schema_v1.json")
    if (
        set(policy)
        != {
            "schemaVersion",
            "version",
            "unit",
            "maximumBytesPerFile",
            "contractPaths",
            "source",
        }
        or type(policy["schemaVersion"]) is not int
        or policy["schemaVersion"] != 1
        or policy["version"] != "contract_size_limit_v1"
        or policy["unit"] != "byte"
        or not isinstance(policy["source"], str)
        or not policy["source"]
    ):
        raise RequiredSetCoverageError("契約サイズ宣言の形式または版が不正")
    limit = policy["maximumBytesPerFile"]
    if type(limit) is not int or limit < 1:
        raise RequiredSetCoverageError("契約サイズ宣言のbyte上限が不正")
    bindings = schema.get("x-pitchlog-descriptor-binding-sources")
    if not isinstance(bindings, list) or not bindings:
        raise RequiredSetCoverageError("descriptor schemaの契約対応を解決できない")
    expected = []
    for binding in bindings:
        if not isinstance(binding, dict) or not isinstance(binding.get("contractPath"), str):
            raise RequiredSetCoverageError("descriptor schemaの契約パスが不正")
        expected.append(binding["contractPath"])
    declared = policy["contractPaths"]
    if (
        not isinstance(declared, list)
        or not all(isinstance(path, str) for path in declared)
        or len(declared) != len(set(declared))
        or set(declared) != set(expected)
        or len(expected) != len(set(expected))
    ):
        raise RequiredSetCoverageError("契約サイズ宣言の契約集合がdescriptor schemaと不一致")
    sizes = {}
    for relative in sorted(declared):
        path = PurePosixPath(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.parts[:2] != ("contracts", "state-transition")
        ):
            raise RequiredSetCoverageError(f"契約パスが不正: {relative}")
        target = root / path
        if not target.is_file() or target.is_symlink():
            raise RequiredSetCoverageError(f"契約ファイルを測れない: {relative}")
        try:
            actual = target.stat().st_size
        except OSError as error:
            raise RequiredSetCoverageError(f"契約ファイルを測れない: {relative}") from error
        if actual > limit:
            raise RequiredSetCoverageError(
                f"契約ファイルがbyte上限超過: {relative}: actual={actual}, maximum={limit}"
            )
        sizes[relative] = actual
    return sizes


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


def _validated_row_refinements(
    root: Path, raw: Any, required: dict[tuple[str, str, str], Any],
    observation_ids: list[tuple[str, str, str]],
) -> list[dict[str, Any]]:
    """既区分の精密化を閉じた原観測の連言だけに制限する。"""
    if not isinstance(raw, list):
        raise RequiredSetCoverageError("行区分精密化が配列でない")
    if not raw:
        return []
    descriptor = _document(root, "input_axes_descriptor_v1.json")
    values = representative_selection.axis_values(descriptor, ("stateTransitionAxes",))
    targets: set[tuple[str, str, str]] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "parent", "partitionId", "all", "sourceClauseIds",
        }:
            raise RequiredSetCoverageError("行区分精密化のfieldが不正")
        parent = item["parent"]
        if not isinstance(parent, dict) or set(parent) != {
            "vocabularyId", "partitionRuleId", "partitionId",
        }:
            raise RequiredSetCoverageError("行区分精密化のparentが不正")
        parent_id = _identity(parent)
        if parent_id not in required or parent_id not in observation_ids:
            raise RequiredSetCoverageError("行区分精密化のparentが既観測区分にない")
        child = item["partitionId"]
        if not isinstance(child, str) or not child:
            raise RequiredSetCoverageError("行区分精密化のchildが不正")
        target = (parent_id[0], parent_id[1], child)
        if target not in required or target == parent_id or target in targets:
            raise RequiredSetCoverageError("行区分精密化のchildが未知または重複")
        targets.add(target)
        clauses = item["sourceClauseIds"]
        if (not isinstance(clauses, list) or not clauses
                or any(not isinstance(clause, str) for clause in clauses)
                or len(clauses) != len(set(clauses))
                or not set(clauses) <= set(required[target].source_clause_ids)):
            raise RequiredSetCoverageError("行区分精密化の典拠が不正")
        conditions = item["all"]
        if not isinstance(conditions, list) or not conditions:
            raise RequiredSetCoverageError("行区分精密化のselectorが空または不正")
        axes: set[str] = set()
        for condition in conditions:
            if not isinstance(condition, dict) or set(condition) != {"axisId", "value"}:
                raise RequiredSetCoverageError("行区分精密化のselector fieldが不正")
            axis = condition["axisId"]
            if not isinstance(axis, str) or axis not in values or axis in axes:
                raise RequiredSetCoverageError("行区分精密化のselector軸が未知または重複")
            axes.add(axis)
            value = condition["value"]
            if not any(type(value) is type(allowed) and value == allowed
                       for allowed in values[axis]):
                raise RequiredSetCoverageError("行区分精密化のselector値または型が不正")
    return raw


def _refined_partition(
    row: dict[str, Any], parent: tuple[str, str, str],
    refinements: list[dict[str, Any]],
) -> tuple[str, str, str]:
    """一意に観測した親から一意childだけへ写す。未観測を推測しない。"""
    matches = [item for item in refinements
               if _identity(item["parent"]) == parent and all(
                   type(actual := _predicate_value(row["precondition"], condition["axisId"]))
                   is type(condition["value"]) and actual == condition["value"]
                   for condition in item["all"])]
    if len(matches) > 1:
        raise RequiredSetCoverageError("行区分精密化のchild観測が一意でない")
    if not matches:
        return parent
    return (parent[0], parent[1], matches[0]["partitionId"])


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
    observation_ids = [_identity(item) for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise RequiredSetCoverageError("行区分観測の区分identityが重複")
    refinements = _validated_row_refinements(
        root, declaration.get("rowPartitionRefinements", []), required, observation_ids,
    )
    covered: list[tuple[str, str, str]] = []
    for row in rows:
        result_id = row.get("resultId")
        if result_id in special_ids:
            identity = _observed_partition(row, observations)
        else:
            identity = (result_id, "identity", "identity")
        identity = _refined_partition(row, identity, refinements)
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
        if not isinstance(gap, dict):
            raise RequiredSetCoverageError(f"未充足の典拠GAPがない: {identity}")
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
        case_expected = case.get("expected")
        if isinstance(case_expected, dict) and "historyInput" in case:
            case_expected = {key: value for key, value in case_expected.items()
                             if key != "historyContext"}
        if case_expected != expected:
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
                value = _result_display_name(coordinate["resultId"], display_names)
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
    _check_liveness_case_depth(root, cases)
    try:
        history = json.loads(
            (root / "backend/domain/history-depth.json").read_text(encoding="utf-8")
        )
        depth = expand_state_transition_cases.history_checker.resolve_history_depth(history)
        expand_state_transition_cases.history_checker.validate_undo_case_differences(
            contract, depth
        )
    except (OSError, UnicodeError, json.JSONDecodeError,
            expand_state_transition_cases.history_checker.HistoryEffectError) as error:
        raise RequiredSetCoverageError(f"undo差分の契約が不正: {error}") from error
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
            if (
                not isinstance(baseline_ids, list) or not baseline_ids
                or not all(isinstance(case_id, str) for case_id in baseline_ids)
                or len(set(baseline_ids)) != len(baseline_ids)
            ):
                raise RequiredSetCoverageError("初回被覆の基線ケースがない")
            ids = set(baseline_ids)
            if not ids <= {case.get("caseId") for case in cases}:
                migrations = _ordinary_case_id_migrations(root, contract)
                ids = {migrations.get(case_id, case_id) for case_id in baseline_ids}
            baseline = [case for case in cases if case.get("caseId") in ids]
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


def _check_liveness_case_depth(root: Path, cases: list[dict[str, Any]]) -> None:
    """D+1 case の入力が取消可能な確定プレイを D+1 件持つことを検査する。"""
    if not any(
        isinstance(case.get("expected"), dict)
        and case["expected"].get("guaranteeMode") == "liveness-only"
        for case in cases
    ):
        return
    try:
        history = json.loads(
            (root / "backend/domain/history-depth.json").read_text(encoding="utf-8")
        )
        depth = expand_state_transition_cases.history_checker.resolve_history_depth(history)
    except (
        OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError,
        expand_state_transition_cases.history_checker.HistoryEffectError,
    ) as error:
        raise RequiredSetCoverageError("XC-09: 履歴深さDを解決できない") from error
    for case in cases:
        expected = case.get("expected")
        if not isinstance(expected, dict) or expected.get("guaranteeMode") != "liveness-only":
            continue
        coordinate = case.get("inputCoordinate")
        history_input = case.get("historyInput")
        stack = history_input.get("stack") if isinstance(history_input, dict) else None
        row_ref = case.get("rowRef")
        if (
            not isinstance(row_ref, dict)
            or row_ref.get("layer") != "undoRows"
            or not isinstance(coordinate, dict)
            or coordinate.get("history.scenarioLength") != "D+1"
            or not isinstance(stack, list)
            or len(stack) != depth + 1
            or any(
                not isinstance(item, dict) or item.get("kind") != "confirmed-play"
                for item in stack
            )
            or "historyContext" in expected
            or expected.get("operationResult") != "applied"
        ):
            raise RequiredSetCoverageError("XC-09: D+1 case の履歴入力または比較面が不正")


def _row_fixed_input_values(predicate: dict[str, Any], axis_id: str) -> set[str]:
    """行の正の等値述語が固定する軸値をすべて得る。"""
    if predicate.get("op") == "eq":
        if predicate.get("axisId") == axis_id:
            return {deriver.descriptor_checker._canonical_json_text(predicate.get("value"))}
    if predicate.get("op") == "and":
        return set().union(*(
            _row_fixed_input_values(child, axis_id)
            for child in predicate.get("args", []) if isinstance(child, dict)
        ))
    return set()


def _row_finite_input_values(predicate: dict[str, Any], axis_id: str) -> set[str]:
    """正の有限in葉だけを集める。自由値・否定・選言を固定値と扱わない。"""
    if predicate.get("op") == "in" and predicate.get("axisId") == axis_id:
        values = predicate.get("values")
        if not isinstance(values, list) or not values:
            raise RequiredSetCoverageError("有限inの値集合が不正")
        encoded = [deriver.descriptor_checker._canonical_json_text(v) for v in values]
        if len(encoded) != len(set(encoded)):
            raise RequiredSetCoverageError("有限inの値集合が重複")
        return set(encoded)
    if predicate.get("op") == "and":
        return set().union(*(
            _row_finite_input_values(child, axis_id)
            for child in predicate.get("args", []) if isinstance(child, dict)
        ))
    return set()


def _terminal_case_extension(root: Path, contract: dict[str, Any]) -> set[str]:
    """既移行の外側へ足す無走者15例だけを、実入力/効果/参照で閉じる。"""
    supplied = contract["cases"]
    expected_ids = {
        f"ST-TERMINAL-{kind}-S{s}-B{b}"
        for kind, counts in (("BB", [(s, 3) for s in range(3)]),
                             ("HBP", [(s, b) for s in range(3) for b in range(4)]))
        for s, b in counts
    }
    present = {case["caseId"] for case in supplied} & expected_ids
    if not present:
        return set()
    if present != expected_ids:
        raise RequiredSetCoverageError("無走者terminalの追加15IDが不完全")
    asset = _document(root, "terminal_pitch_cases_v1.json")
    cases = asset.get("cases")
    if (asset.get("calculation") != "terminal-empty-bb-hbp-v1"
            or asset.get("operation") != "deriveTerminalPitch"
            or not isinstance(cases, list) or len(cases) != 15
            or not all(isinstance(case, dict)
                       and isinstance(case.get("formalCaseId"), str) for case in cases)
            or {case.get("formalCaseId") for case in cases} != expected_ids):
        raise RequiredSetCoverageError("無走者terminalの正準case資産が不一致")
    keys = (
        "投球回算入アウト", "投球数", "奪三振", "与四球", "与死球", "被安打",
        "被本塁打", "失点", "失策", "打席", "打数", "安打", "本塁打", "塁打",
        "犠打", "犠飛", "四球", "死球", "三振", "打撃妨害出塁", "走塁妨害出塁",
        "得点", "打点",
    )

    def wire(value: Any) -> Any:
        """固定した期待整数を正準wireへ写し、入力の型変換は行わない。"""
        if isinstance(value, dict):
            return {key: wire(child) for key, child in value.items()}
        if isinstance(value, list):
            return [wire(child) for child in value]
        if type(value) is int:
            return str(value)
        return value

    for source in cases:
        identifier = source["formalCaseId"]
        kind, strikes, balls = identifier.removeprefix("ST-TERMINAL-").split("-")
        s, b = int(strikes[1:]), int(balls[1:])
        walk = kind == "BB"
        result = "batting-result.walk" if walk else "batting-result.hit-by-pitch"
        predicate = {"op": "and", "args": [
            {"op": "in", "axisId": "state.outs", "values": [0, 1, 2]},
            {"op": "eq", "axisId": "state.runners", "value": "empty"},
            {"op": "in", "axisId": "state.count.strikes", "values": [0, 1, 2]},
            {"op": "eq", "axisId": "state.count.balls", "value": 3} if walk else
            {"op": "in", "axisId": "state.count.balls", "values": [0, 1, 2, 3]},
            {"op": "eq", "axisId": "state.gameEnded", "value": False},
            {"op": "eq", "axisId": "event.perPitch.pitchEventKind", "value": "pitch-event"},
        ]}
        coordinate = {"eventKind": "batting-result", "resultId": result,
                      "precondition": predicate}
        row_ref = {"layer": "matrixRows", "coordinate": coordinate}
        flags = {key: key in ({"投球数", "打席", "与四球", "四球"} if walk else
                             {"投球数", "打席", "与死球", "死球"}) for key in keys}
        effects = {"countEffect": {"strikes": {"kind": "reset"}, "balls": {"kind": "reset"}},
                   "plateAppearanceEnded": True, "batterDestination": {"kind": "reach", "base": 1},
                   "runnerDefaultAdvance": {
                       base: {"modality": "not-applicable", "destination": None}
                       for base in ("first", "second", "third")},
                   "outEffect": {"count": 0, "targets": []}, "statFlags": flags}
        before = {"stateFields": {
            "state.half": "top", "state.count.strikes": s, "state.count.balls": b,
            "state.outs": 0, "state.runners": "empty", "state.battingOrder": 1,
            "state.tiebreakActive": False, "state.gameEnded": False, "state.inning": 1,
            "state.score": {"home": 0, "away": 0},
        }, "scoreboard": {"inningScores": {"home": 0, "away": 0},
                          "hits": 0, "errors": 0, "strikeouts": 0, "walks": 0}}
        after = {"stateFields": {**before["stateFields"], "state.count.strikes": 0,
                                "state.count.balls": 0, "state.runners": "first",
                                "state.battingOrder": 2},
                 "scoreboard": {**before["scoreboard"], "walks": 1 if walk else 0}}
        request = {"eventKind": "batting-result", "resultId": result,
                   "pitchEventKind": "pitch-event", "before": before, "history": {"stack": []}}
        difference: dict[str, object] = {
            name: {key: {"before": old, "after": after[name][key]}
                   for key, old in before[name].items() if old != after[name][key]}
            for name in ("stateFields", "scoreboard")
        }
        difference["statFlags"] = flags
        response = {"ok": True, "value": {
            **effects, "after": after,
            "historyContext": [{"kind": "confirmed-play", "difference": difference}],
        }}
        input_coordinate = {"eventKind": "batting-result", "resultId": result,
                            "state.count.strikes": s, "state.count.balls": b, "state.outs": 0,
                            "state.runners": "empty", "state.gameEnded": False,
                            "event.perPitch.pitchEventKind": "pitch-event"}
        expected = {"caseId": identifier, "rowRef": row_ref,
                    "inputCoordinate": input_coordinate, "expected": effects,
                    "historyInput": {"stack": [], "before": before, "after": after},
                    "raw": {**input_coordinate, "resultId": "四球" if walk else "死球"},
                    "normalizationRuleId": "result-display-name-to-id",
                    "normalized": input_coordinate}
        matches = [case for case in supplied if case["caseId"] == identifier]
        equal = deriver.descriptor_checker._json_equal
        rows = [row for row in contract["matrixRows"]
                if equal({key: row.get(key) for key in coordinate}, coordinate)]
        if (len(matches) != 1 or not equal(matches[0], expected)
                or source.get("caseId") != identifier.removeprefix("ST-")
                or not equal(source.get("request"), wire(request))
                or not equal(source.get("expected"), wire(response))
                or len(rows) != 1 or not equal(
                    {key: value for key, value in rows[0].items()
                     if key not in {"eventKind", "resultId", "precondition", "remarks"}}, effects)):
            raise RequiredSetCoverageError("無走者terminalの入力/効果/履歴/実row参照が不一致")
    return expected_ids


def _strikeout_case_extension(root: Path, contract: dict[str, Any]) -> set[str]:
    """通常117/BBHBP15を広げず、SO規範の固定24例だけを別閉集合で照合する。"""
    ids = {f"ST-STRIKEOUT-{kind}-B{balls}-O{outs}"
           for kind in (1, 2) for balls in range(4) for outs in range(3)}
    supplied = contract["cases"]
    present = {case["caseId"] for case in supplied} & ids
    if not present:
        return set()
    if present != ids:
        raise RequiredSetCoverageError("三振の追加24IDが不完全")
    asset = _document(root, "strikeout_pitch_cases_v1.json")
    sources = asset.get("cases")
    if (asset.get("calculation") != "strikeout-caught-both-cursors-v1"
            or asset.get("operation") != "deriveStrikeoutPitch"
            or not isinstance(sources, list) or len(sources) != 24
            or not all(isinstance(case, dict) for case in sources)
            or {case.get("formalCaseId") for case in sources} != ids):
        raise RequiredSetCoverageError("三振の正準24case資産が不一致")
    def equal(actual: Any, expected: Any) -> bool:
        """この24例ではnested bool/intも混同せず、全JSON型と値を比較する。"""
        return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(
            expected, sort_keys=True, allow_nan=False,
        )

    schema = _document(root, "strikeout_pitch_schema_v1.json")
    descriptor = _document(root, "input_axes_descriptor_v1.json")
    axes = [axis for axis in descriptor["stateTransitionAxes"]
            if axis["axisId"] == "state.battingOrder"]
    projection = {
        "descriptorPath": "contracts/state-transition/input_axes_descriptor_v1.json",
        "axisId": "state.battingOrder",
        "targets": ["before.stateFields.state.battingOrder",
                    "before.battingOrderBySide.away", "before.battingOrderBySide.home"],
        "activeConstraint": "top→away / bottom→home equals state.battingOrder",
        "independentlyCrossed": ["inactive battingOrderBySide cursor"],
        "historyDifference": "difference.battingOrderBySide retains outgoing cursor change "
                             "even when scalar order unchanged",
    }
    if (len(axes) != 1 or not equal(axes[0]["values"], list(range(1, 10)))
            or not equal(asset.get("contextProjection"), projection)):
        raise RequiredSetCoverageError("三振の両cursorと既descriptor写像が不一致")
    order_domain = [str(value) for value in axes[0]["values"]]
    runner_axes = [axis for axis in descriptor["stateTransitionAxes"]
                   if axis["axisId"] == "state.runners"]
    runner_map = {runner: ("first-second-third" if runner == "loaded" else runner)
                  for runner in ("empty", "first", "second", "third", "first-second",
                                 "first-third", "second-third", "loaded")}
    runner_projection = asset.get("runnerProjection")
    if (len(runner_axes) != 1 or not equal(runner_axes[0]["values"], list(runner_map))
            or not isinstance(runner_projection, dict)
            or runner_projection.get("descriptorAxisId") != "state.runners"
            or not equal(runner_projection.get("formalToWire"), runner_map)
            or not equal(schema["$defs"]["StateFields"]["properties"]["state.runners"][
                "enum"
            ], list(runner_map.values()))):
        raise RequiredSetCoverageError("三振のformal loaded/public wire塁配置写像が不一致")
    try:
        for side in ("away", "home"):
            field = schema["$defs"]["BattingOrderBySide"]["properties"][side]
            if (field.get("x-pitchlog-axis-id") != "state.battingOrder"
                    or not equal(field.get("enum"), order_domain)):
                raise RequiredSetCoverageError("三振schemaの両cursor domainが不一致")
        before_schema = schema["$defs"]["StrikeoutPitchRequest"]["properties"]["before"]
        for snapshot in (before_schema, schema["$defs"]["AfterSnapshot"]):
            if not equal(snapshot["properties"]["stateFields"]["properties"][
                "state.battingOrder"
            ]["enum"], order_domain) or snapshot["properties"]["battingOrderBySide"] != {
                "$ref": "#/$defs/BattingOrderBySide"
            }:
                raise RequiredSetCoverageError("三振schemaのactive打順写像が不一致")
    except (KeyError, TypeError) as error:
        raise RequiredSetCoverageError("三振schemaのcontext構造が不正") from error

    def wire(value: Any) -> Any:
        """固定した規範期待整数をwireへ写すだけで入力はcoerceしない。"""
        if isinstance(value, dict):
            return {key: ("first-second-third" if key == "state.runners" and child == "loaded"
                          else wire(child)) for key, child in value.items()}
        if isinstance(value, list):
            return [wire(child) for child in value]
        return str(value) if type(value) is int else value

    # 24手例の入力座標はcaseIdから固定する。自己申告で任意scopeを受理しない。
    contexts = (
        ("top", "empty", 1, 1, 5), ("bottom", "first", 2, 3, 2),
        ("top", "second", 3, 3, 6), ("bottom", "third", 4, 7, 4),
        ("top", "first-second", 5, 5, 7), ("bottom", "first-third", 6, 6, 6),
        ("top", "second-third", 7, 7, 8),
        ("bottom", "loaded", 8, 6, 8),
        ("top", "empty", 9, 9, 9), ("bottom", "first", 1, 1, 1),
        ("top", "second", 2, 2, 1), ("bottom", "third", 3, 3, 3),
    )
    keys = _document(root, "state_transition_contract_schema_v1.json")["$defs"][
        "statFlags"
    ]["properties"]
    flags = {key: key in {"投球回算入アウト", "投球数", "奪三振", "打席", "打数", "三振"}
             for key in keys}
    for source in sources:
        identifier = source["formalCaseId"]
        kind, balls_part, outs_part = identifier.removeprefix("ST-STRIKEOUT-").split("-")
        balls, outs = int(balls_part[1:]), int(outs_part[1:])
        result = "batting-result." + ("called-strikeout" if kind == "1"
                                      else "swinging-strikeout")
        half, runners, order, away, home = contexts[balls * 3 + outs]
        before = {"stateFields": {
            "state.half": half, "state.count.strikes": 2, "state.count.balls": balls,
            "state.outs": outs, "state.runners": runners, "state.battingOrder": order,
            "state.tiebreakActive": False, "state.gameEnded": False, "state.inning": 3,
            "state.score": {"home": 7, "away": 4},
        }, "scoreboard": {"inningScores": {"home": 7, "away": 4}, "hits": 5,
                          "errors": 2, "strikeouts": 11, "walks": 3},
            "battingOrderBySide": {"away": away, "home": home}}
        side, other = ("away", "home") if half == "top" else ("home", "away")
        cursors = {"away": away, "home": home}
        cursors[side] = order % 9 + 1
        third = outs == 2
        after = {"stateFields": {
            **before["stateFields"], "state.count.strikes": 0, "state.count.balls": 0,
            "state.outs": 0 if third else outs + 1,
            "state.runners": "empty" if third else runners,
            "state.battingOrder": cursors[other] if third else cursors[side],
            "state.half": ("bottom" if half == "top" else "top") if third else half,
            "state.inning": 3 + int(third and half == "bottom"),
        }, "scoreboard": {**before["scoreboard"], "strikeouts": 12},
            "battingOrderBySide": cursors}
        effects = {"countEffect": {"strikes": {"kind": "reset"}, "balls": {"kind": "reset"}},
                   "plateAppearanceEnded": True, "batterDestination": {"kind": "out"},
                   "runnerDefaultAdvance": {
                       base: {"modality": "hold" if base in (("first", "second", "third")
                                if runners == "loaded" else runners.split("-"))
                              else "not-applicable", "destination": None}
                       for base in ("first", "second", "third")},
                   "outEffect": {"count": 1, "targets": ["batter"]}, "statFlags": flags}
        arguments: list[dict[str, Any]] = [
            {"op": "eq", "axisId": "state.runners", "value": runners},
            {"op": "in", "axisId": "state.outs", "values": [0, 1, 2]},
            {"op": "eq", "axisId": "state.count.strikes", "value": 2},
            {"op": "in", "axisId": "state.count.balls", "values": [0, 1, 2, 3]},
            {"op": "eq", "axisId": "event.perPitch.pitchEventKind", "value": "pitch-event"},
            {"op": "eq", "axisId": "state.gameEnded", "value": False},
        ]
        predicate: dict[str, Any] = {"op": "and", "args": arguments}
        if runners == "empty":
            arguments.append({"op": "not", "args": [{"op": "and", "args": [
                {"op": "eq", "axisId": "state.outs", "value": 0},
                {"op": "eq", "axisId": "state.count.balls", "value": 0},
            ]}]})
            if outs == balls == 0:
                predicate = {"op": "and", "args": [
                    {"op": "eq", "axisId": "state.outs", "value": 0},
                    {"op": "eq", "axisId": "state.runners", "value": "empty"},
                    {"op": "eq", "axisId": "state.count.strikes", "value": 2},
                    {"op": "eq", "axisId": "state.count.balls", "value": 0},
                    {"op": "eq", "axisId": "event.perPitch.pitchEventKind", "value": "pitch-event"},
                ]}
        coordinate = {"eventKind": "batting-result", "resultId": result,
                      "precondition": predicate}
        input_coordinate = {"eventKind": "batting-result", "resultId": result,
                            "state.outs": outs, "state.runners": runners,
                            "state.count.strikes": 2, "state.count.balls": balls,
                            "event.perPitch.pitchEventKind": "pitch-event",
                            "state.gameEnded": False}
        expected = {"caseId": identifier,
                    "rowRef": {"layer": "matrixRows", "coordinate": coordinate},
                    "inputCoordinate": input_coordinate, "expected": effects,
                    "historyInput": {"stack": [], "before": before, "after": after},
                    "raw": input_coordinate, "normalizationRuleId": "identity",
                    "normalized": input_coordinate}
        difference: dict[str, Any] = {
            face: {key: {"before": old, "after": after[face][key]}
                   for key, old in fields.items() if old != after[face][key]}
            for face, fields in before.items()
        }
        difference["statFlags"] = flags
        request = {"eventKind": "batting-result", "resultId": result,
                   "pitchEventKind": "pitch-event", "before": before, "history": {"stack": []}}
        response = {"ok": True, "value": {
            **effects, "after": after,
            "historyContext": [{"kind": "confirmed-play", "difference": difference}],
        }}
        matches = [case for case in supplied if case["caseId"] == identifier]
        rows = [row for row in contract["matrixRows"]
                if equal({key: row.get(key) for key in coordinate}, coordinate)]
        if (len(matches) != 1 or not equal(matches[0], expected)
                or source.get("caseId") != identifier.removeprefix("ST-")
                or not equal(source.get("request"), wire(request))
                or not equal(source.get("expected"), wire(response))
                or len(rows) != 1 or not equal(
                    {key: value for key, value in rows[0].items()
                     if key not in {"eventKind", "resultId", "precondition", "remarks"}}, effects)):
            raise RequiredSetCoverageError("三振24例の入力/全応答/効果/履歴/実row参照が不一致")
    return ids


def _ordinary_case_id_migrations(
    root: Path, contract: dict[str, Any],
) -> dict[str, str]:
    """既Git原本と全caseを照合した通常33の有限ID移行だけを解決する。"""
    asset = _document(root, "ordinary_pitch_vectors_v1.json")
    if asset.get("schemaVersion") != 1 or asset.get("operation") != "deriveOrdinaryPitch":
        raise RequiredSetCoverageError("通常投球の移行資産種別が不正")
    binding = asset.get("caseIdMigrations")
    if not isinstance(binding, dict) or set(binding) != {
        "baselineCommit", "baselineContractSHA256", "caseIds"
    }:
        raise RequiredSetCoverageError("通常投球のID移行宣言が不正")
    revision, digest, mapping = (
        binding["baselineCommit"], binding["baselineContractSHA256"], binding["caseIds"]
    )
    if (
        not isinstance(revision, str) or len(revision) != 40
        or any(c not in "0123456789abcdef" for c in revision)
        or not isinstance(digest, str) or not isinstance(mapping, dict)
        or len(mapping) != 12
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items())
        or len(set(mapping.values())) != 12
        or set(mapping) & set(mapping.values())
    ):
        raise RequiredSetCoverageError("通常投球のID移行が一意な12件でない")
    result = subprocess.run(
        ["git", "show", f"{revision}:contracts/state-transition/state_transition_contract_v1.json"],
        cwd=root, capture_output=True, check=False,
    )
    if result.returncode or hashlib.sha256(result.stdout).hexdigest() != digest:
        raise RequiredSetCoverageError("通常投球の移行前Git原本が不一致")
    try:
        original = json.loads(result.stdout)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RequiredSetCoverageError("通常投球の移行前原本が不正") from error
    if not isinstance(original, dict):
        raise RequiredSetCoverageError("通常投球の移行前原本がobjectでない")
    old_cases, new_cases = original.get("cases"), contract.get("cases")
    if not isinstance(old_cases, list) or not isinstance(new_cases, list):
        raise RequiredSetCoverageError("通常投球の移行case集合が不正")
    old = {case["caseId"]: case for case in old_cases}
    new = {case["caseId"]: case for case in new_cases}
    if len(old) != len(old_cases) or len(new) != len(new_cases):
        raise RequiredSetCoverageError("通常投球の移行caseが重複")
    if not set(mapping) <= set(old) or set(mapping.values()) - set(new):
        raise RequiredSetCoverageError("通常投球の移行caseが欠落")
    guards = {
        "batting-result.ball": ([0, 1, 2], [0, 1, 2]),
        "batting-result.called-pitch": ([0, 1], [0, 1, 2, 3]),
        "batting-result.swinging-strike": ([0, 1], [0, 1, 2, 3]),
        "batting-result.foul": ([0, 1], [0, 1, 2, 3]),
    }
    representatives = {
        case["rowRef"]["coordinate"]["resultId"]: case
        for case in old_cases
        if case.get("caseId") in mapping and case["caseId"].startswith("ST-MATRIX-")
    }
    extension = _terminal_case_extension(root, contract) | _strikeout_case_extension(root, contract)
    if (set(representatives) != set(guards) or len(old) != 116
            or len(new) != 117 + len(extension)):
        raise RequiredSetCoverageError("通常投球の4代表・116→117移行が不一致")

    def matrix_id(coordinate: dict[str, Any]) -> str:
        encoded = json.dumps(coordinate, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"))
        return "ST-MATRIX-" + hashlib.sha256(encoded.encode()).hexdigest()[:16]

    changed = set()
    for case_id, before in old.items():
        after = new.get(mapping.get(case_id, case_id))
        if after is None:
            raise RequiredSetCoverageError("通常投球の旧caseが失われた")
        if case_id not in mapping:
            if before != after:
                raise RequiredSetCoverageError("通常投球の移行対象外caseが変更された")
            continue
        ref = before.get("rowRef", {})
        coordinate = ref.get("coordinate", {})
        result_id = coordinate.get("resultId")
        if ref.get("layer") != "matrixRows" or result_id not in guards:
            raise RequiredSetCoverageError("通常投球以外のID移行")
        expected = json.loads(json.dumps(before))
        predicate = expected["rowRef"]["coordinate"]["precondition"]
        for axis, values in zip(("state.count.strikes", "state.count.balls"),
                                guards[result_id], strict=True):
            leaves = [leaf for leaf in predicate.get("args", [])
                      if leaf == {"op": "eq", "axisId": axis, "value": 0}]
            if len(leaves) != 1:
                raise RequiredSetCoverageError("通常投球の移行前guardが不一致")
            leaves[0].clear()
            leaves[0].update(op="in", axisId=axis, values=values)
        expected["caseId"] = mapping[case_id]
        new_representative_id = matrix_id(expected["rowRef"]["coordinate"])
        representative = representatives[result_id]
        if representative["caseId"] != matrix_id(representative["rowRef"]["coordinate"]):
            raise RequiredSetCoverageError("通常投球の旧代表IDが自然IDでない")
        if case_id.startswith("ST-MATRIX-"):
            natural_id = new_representative_id
        else:
            different = [(axis, value) for axis, value in before["inputCoordinate"].items()
                         if representative["inputCoordinate"].get(axis) != value]
            if len(different) != 1:
                raise RequiredSetCoverageError("通常投球のcoverage移行座標が不正")
            axis, value = different[0]
            encoded = json.dumps([new_representative_id, axis, value],
                                 sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            natural_id = "ST-COVERAGE-" + hashlib.sha256(encoded.encode()).hexdigest()[:16]
        if mapping[case_id] != natural_id:
            raise RequiredSetCoverageError("通常投球の移行先IDが自然IDと不一致")
        if expected != after:
            raise RequiredSetCoverageError("通常投球の入力・期待値・履歴が移行で変化した")
        # 参照先は現行規範の一意な行でなければならない。
        row_coordinate = expected["rowRef"]["coordinate"]
        if sum(all(row.get(k) == v for k, v in row_coordinate.items())
               for row in contract.get("matrixRows", [])) != 1:
            raise RequiredSetCoverageError("通常投球の移行参照が一意でない")
        changed.add(result_id)
    if changed != set(guards):
        raise RequiredSetCoverageError("通常投球の4代表移行が不足")
    ordinary_ids = {mapping.get(identifier, identifier) for identifier in old}
    remaining = set(new) - ordinary_ids - extension
    foul = json.loads(json.dumps(new[mapping[representatives["batting-result.foul"]["caseId"]]]))
    encoded = json.dumps([foul["caseId"], "state.count.balls", 1],
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    foul["caseId"] = "ST-COVERAGE-" + hashlib.sha256(encoded.encode()).hexdigest()[:16]
    for field in ("inputCoordinate", "raw", "normalized"):
        foul[field]["state.count.balls"] = 1
    for field in ("before", "after"):
        foul["historyInput"][field]["stateFields"]["state.count.balls"] = 1
    if (remaining != {foul["caseId"]}
            or not deriver.descriptor_checker._json_equal(new[foul["caseId"]], foul)):
        raise RequiredSetCoverageError("通常投球の117番目の既正例が変更/欠落/置換された")
    return mapping


def _check_unrepresented_operation_sources(
    root: Path, declaration: dict[str, Any], descriptor: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    """操作行が無い種別の条文と段階判断の実在を検査する。"""
    raw = declaration.get("unrepresentedOperationSources")
    if not isinstance(raw, list):
        raise RequiredSetCoverageError("操作欠落の典拠宣言がない")
    axes = {
        axis.get("axisId"): axis for axis in descriptor.get("stateTransitionAxes", [])
        if isinstance(axis, dict)
    }
    kind_axis = axes.get("event.operationKind")
    payload_axis = axes.get("event.operationPayload")
    if not isinstance(kind_axis, dict) or not isinstance(payload_axis, dict):
        raise RequiredSetCoverageError("操作軸のdescriptorがない")
    operation_values = set(kind_axis.get("values", [])) & set(
        payload_axis.get("boundaryValues", [])
    )
    represented = {row.get("operationKind") for row in rows}
    missing = operation_values - represented - {"not-applicable"}
    declared: set[str] = set()
    available_sources = {
        kind_axis.get("sourceClauseId"), payload_axis.get("sourceClauseId"),
        *kind_axis.get("supportingClauseIds", []),
        *payload_axis.get("supportingClauseIds", []),
    }
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "operationKind", "sourceClauseIds", "decisionSource"
        }:
            raise RequiredSetCoverageError("操作欠落の典拠形式が不正")
        kind = item["operationKind"]
        clauses = item["sourceClauseIds"]
        evidence = item["decisionSource"]
        if (
            not isinstance(kind, str) or kind in declared or kind not in operation_values
            or not isinstance(clauses, list) or not clauses
            or not all(isinstance(clause, str) and clause in available_sources
                       for clause in clauses)
            or len(clauses) != len(set(clauses))
            or not isinstance(evidence, dict)
            or set(evidence) != {"path", "evidenceText"}
        ):
            raise RequiredSetCoverageError("操作欠落の条文典拠が不正")
        path = evidence["path"]
        snippets = evidence["evidenceText"]
        if (
            not isinstance(path, str)
            or path not in {
                "docs/features/appendix-e-golden-vectors/design.md",
                "docs/features/appendix-e-golden-vectors/plan.md",
            }
            or not isinstance(snippets, list) or not snippets
            or not all(isinstance(snippet, str) and snippet for snippet in snippets)
        ):
            raise RequiredSetCoverageError("操作欠落の裁定参照が不正")
        try:
            source_text = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RequiredSetCoverageError("操作欠落の裁定文書を読めない") from error
        if not all(snippet in source_text for snippet in snippets):
            raise RequiredSetCoverageError("操作欠落の裁定典拠が見つからない")
        declared.add(kind)
    # 新規の操作欠落は典拠なしでは除外しない。行が増えた分は自動で縮む。
    if not missing <= declared:
        raise RequiredSetCoverageError("操作欠落の典拠宣言が不足")


def check_input_coverage_exact(
    root: Path,
    contract: dict[str, Any] | None = None,
    declaration: dict[str, Any] | None = None,
) -> tuple[int, int, int]:
    """②の規則除外後の到達可能要求と実ケースをexact-setで照合する。"""
    contract = contract if contract is not None else _document(
        root, "state_transition_contract_v1.json"
    )
    declaration = declaration if declaration is not None else _document(
        root, "required_set_input_coverage_declaration_v1.json"
    )
    descriptor = _document(root, "input_axes_descriptor_v1.json")
    binding_policy = _document(root, "coverage_row_binding_policy_v1.json")
    selection_policy = _document(root, "representative_selection_policy_v1.json")
    expected_rule = {
        "rowLayers": ["matrixRows", "operationRows", "undoRows"],
        "axisValuePredicate": "no-normative-row-realizes-axis-value-under-row-binding-policy",
        "fixedStateAxisPredicate": "matrix-row-fixed-state-axis-values",
        "rowBindingPolicyId": binding_policy.get("policyId"),
        "onNewRow": "recompute-reachability-from-current-normative-rows",
    }
    if (
        declaration.get("schemaVersion") != 1
        or declaration.get("version") != "required_set_input_coverage_declaration_v1"
        or set(declaration) != {
            "schemaVersion", "version", "exclusionRule", "unrepresentedOperationSources"
        }
        or declaration.get("exclusionRule") != expected_rule
        or expected_rule["rowBindingPolicyId"] != "state-transition-coverage-row-binding"
    ):
        raise RequiredSetCoverageError("②の規則除外宣言が不正")
    rows_by_layer: dict[str, list[dict[str, Any]]] = {}
    for layer in expected_rule["rowLayers"]:
        rows = contract.get(layer)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise RequiredSetCoverageError("②の規範行が不正")
        rows_by_layer[layer] = rows
    matrix_rows = rows_by_layer["matrixRows"]
    # 打球行が固定する状態軸を、無関係な操作行の自由値で埋めない。
    values_by_axis = representative_selection.axis_values(
        descriptor, ("stateTransitionAxes",)
    )
    fixed_state_values: dict[str, set[str]] = {}
    for axis in descriptor.get("stateTransitionAxes", []):
        axis_id = axis.get("axisId") if isinstance(axis, dict) else None
        if not isinstance(axis_id, str) or not axis_id.startswith("state."):
            continue
        fixed = set().union(*(
            _row_fixed_input_values(row["precondition"], axis_id)
            for row in matrix_rows
        ))
        for row in matrix_rows:
            for identity in _row_finite_input_values(row["precondition"], axis_id):
                predicate = {"op": "and", "args": [
                    row["precondition"],
                    {"op": "eq", "axisId": axis_id, "value": json.loads(identity)},
                ]}
                axes = [axis for axis in values_by_axis
                        if axis in representative_selection.predicate_axes(predicate)]
                try:
                    representative_selection.select_coordinate(
                        predicate, values_by_axis, axes, selection_policy
                    )
                except representative_selection.RepresentativeSelectionError:
                    continue
                fixed.add(identity)
        if fixed:
            fixed_state_values[axis_id] = fixed
    _check_unrepresented_operation_sources(
        root, declaration, descriptor, rows_by_layer["operationRows"]
    )
    values_by_axis = representative_selection.axis_values(
        descriptor, ("stateTransitionAxes",)
    )
    try:
        unbound, value_bindings = expand_state_transition_cases._row_bound_value_exceptions(
            binding_policy, descriptor, matrix_rows, values_by_axis
        )
    except expand_state_transition_cases.CaseExpansionError as error:
        raise RequiredSetCoverageError(f"行束縛宣言が不正: {error}") from error
    requirements, _ = deriver.derive_repository_input_coordinate_requirements(root)
    active = deriver.active_input_coordinate_requirements(
        requirements, {"req:FR-040": "adopted"}
    )
    vocabulary = json.loads(
        (root / "contracts/vocabulary/input_vocabulary_v1.json").read_text(encoding="utf-8")
    )
    display_names = {
        entry["id"]: entry["initialDisplayName"]
        for axis in vocabulary["axes"] for entry in axis["entries"]
    }
    cases = contract.get("cases")
    if not isinstance(cases, list):
        raise RequiredSetCoverageError("②のケース集合が不正")
    check_state_derived_axis_cases(contract, descriptor)
    observed = observed_input_coverage(cases, active, contract, display_names)
    required_ids = {item.identity for item in active}
    if not observed <= required_ids:
        raise RequiredSetCoverageError("②に要求外の被覆がある")

    row_schema = _document(root, "state_transition_contract_schema_v1.json")

    def explicit_bound_row(layer: str, row: dict[str, Any]) -> bool:
        """別layer自身の明示入力を、既宣言へ束縛した合法行だけに認める。"""
        fields_by_layer = {
            "operationRows": ("operationKind", "payloadShape", "precondition"),
            "undoRows": ("targetKind", "precondition"),
        }
        if layer not in fields_by_layer:
            return False
        definition = "operationRow" if layer == "operationRows" else "undoRow"
        try:
            deriver.descriptor_checker._validate_instance(
                row, row_schema["$defs"][definition], row_schema, "$",
            )
        except deriver.descriptor_checker.DescriptorCheckError:
            return False
        if not representative_selection.predicate_axes(row["precondition"]) <= set(values_by_axis):
            return False
        kind = row.get("operationKind") if layer == "operationRows" else "undo"
        if kind not in values_by_axis["event.operationKind"]:
            return False
        coordinate = {field: row[field] for field in fields_by_layer[layer]}
        equal = deriver.descriptor_checker._json_equal
        references = [
            reference
            for mapping in contract["mustOperationCoverage"]["mappings"]
            if mapping.get("operationType") == kind
            for reference in mapping["rowRefs"]
            if reference.get("layer") == layer
            and equal(reference.get("coordinate"), coordinate)
        ]
        return len(references) == 1

    def row_accepts(item: deriver.InputCoordinateRequirement, layer: str,
                    row: dict[str, Any]) -> bool:
        axis_id = item.axis_id
        value = item.coverage_value
        if item.natural_key_role != "predicate-axis":
            if layer == "matrixRows":
                actual = {
                    "event.operationKind": "per-pitch",
                    "event.operationPayload": "not-applicable",
                    "event.perPitch.kind": row.get("eventKind"),
                    "event.perPitch.resultId": _result_display_name(
                        row.get("resultId"), display_names
                    ),
                }.get(axis_id)
            elif layer == "operationRows":
                actual = row.get("operationKind")
            else:
                actual = {"event.operationKind": "undo",
                          "event.operationPayload": "not-applicable"}.get(axis_id)
            return type(actual) is type(value) and actual == value
        if axis_id.startswith("history.topDifference.") and (
            layer != "undoRows"
            or row.get("targetKind") == "none"
            or row.get("guaranteeMode") != "full-equality"
            or not _row_fixed_input_values(row["precondition"], axis_id)
        ):
            # 先頭差分は保証範囲内の適用行が値を固定したときだけ到達する。
            return False
        identity = item.identity[1]
        fixed_values = _row_fixed_input_values(row["precondition"], axis_id)
        if fixed_values and fixed_values != {identity}:
            return False
        finite_values = _row_finite_input_values(row["precondition"], axis_id)
        if finite_values and identity not in finite_values:
            return False
        if axis_id in fixed_state_values and identity not in fixed_state_values[axis_id]:
            # matrixの固定範囲を他操作の自由値で埋めない。自身の明示値と
            # 既row束縛の両方がある別layerだけ、後段の全述語充足へ進める。
            if not (identity in fixed_values or identity in finite_values):
                return False
            if not explicit_bound_row(layer, row):
                return False
        if axis_id in unbound and layer == "matrixRows":
            explicitly_fixed = bool(fixed_values or finite_values)
            declared_binding = row.get("resultId") in value_bindings.get(
                axis_id, {}
            ).get(json.dumps(value, sort_keys=True, ensure_ascii=False), set())
            free_value = any(type(candidate) is type(value) and candidate == value
                             for candidate in unbound[axis_id])
            if not (explicitly_fixed or declared_binding or free_value):
                return False
        predicate = {
            "op": "and",
            "args": [row["precondition"], {"op": "eq", "axisId": axis_id, "value": value}],
        }
        axes = [axis for axis in values_by_axis
                if axis in representative_selection.predicate_axes(predicate)]
        try:
            representative_selection.select_coordinate(
                predicate, values_by_axis, axes, selection_policy
            )
        except representative_selection.RepresentativeSelectionError:
            return False
        return True

    reachable = {
        item.identity for item in active
        if any(
            row_accepts(item, layer, row)
            for layer in item.row_layers
            for row in rows_by_layer[layer]
        )
    }
    excluded = required_ids - reachable
    if observed != reachable:
        raise RequiredSetCoverageError(
            f"②の規則除外後の差分がexact-set不一致: "
            f"missing={sorted(reachable - observed)}; "
            f"unexpected={sorted(observed - reachable)}"
        )
    return len(required_ids), len(excluded), len(reachable - observed)


def _game_end_identity(value: Any) -> str:
    """導出器と同じRFC 8785の値identityを得る。"""
    return deriver.descriptor_checker._canonical_json_text(value)


def _game_end_display_names(root: Path) -> dict[str, str]:
    """状況判定の正規形とrawから終了判定の被覆用表示名を得る。"""
    state = _document(root, "state_transition_contract_v1.json")
    vocabulary = json.loads(
        (root / "contracts/vocabulary/input_vocabulary_v1.json").read_text(encoding="utf-8")
    )
    vocabulary_names = {
        entry["id"]: entry["initialDisplayName"]
        for axis in vocabulary["axes"] for entry in axis["entries"]
    }
    names: dict[str, str] = {}
    for case in state.get("cases", []):
        normalized = case.get("normalized")
        raw = case.get("raw")
        if not isinstance(normalized, dict) or not isinstance(raw, dict):
            raise RequiredSetCoverageError("状況判定ケースの正規化値が不正")
        result_id = normalized.get("resultId")
        if result_id is None:
            continue
        display_name = raw.get("resultId")
        # 閉入力のID表現は語彙正本から表示名へ解決する。純入力は書き換えない。
        if display_name == result_id:
            display_name = vocabulary_names.get(result_id)
        if (
            not isinstance(result_id, str) or not isinstance(display_name, str)
            or result_id in names and names[result_id] != display_name
        ):
            raise RequiredSetCoverageError("状況判定の結果IDと表示名が一意でない")
        names[result_id] = display_name
    if not names:
        raise RequiredSetCoverageError("状況判定の結果IDと表示名がない")
    return names


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
        raise RequiredSetCoverageError("decisionRowsが終了規則軸を固定しない")
    return fixed


def _fixed_game_end_alternatives(
    row: dict[str, Any], axis_ids: set[str]
) -> list[dict[str, str]]:
    """選言を含む行について、各分岐が固定する終了規則軸を列挙する。"""

    def visit(node: dict[str, Any]) -> list[dict[str, str]]:
        operation = node.get("op")
        if operation == "eq":
            axis = node.get("axisId")
            return [{axis: _game_end_identity(node["value"])}] if axis in axis_ids else [{}]
        if operation == "or":
            return [part for child in node["args"] for part in visit(child)]
        if operation != "and":
            return [{}]
        combined: list[dict[str, str]] = [{}]
        for child in node["args"]:
            next_values: list[dict[str, str]] = []
            for left in combined:
                for right in visit(child):
                    if any(axis in left and left[axis] != value for axis, value in right.items()):
                        continue
                    next_values.append({**left, **right})
            combined = next_values
        return combined

    alternatives = visit(row["precondition"])
    if not alternatives or any(set(item) != axis_ids for item in alternatives):
        raise RequiredSetCoverageError("decisionRowsの各選言が終了規則軸を固定しない")
    distinct = list({tuple(sorted(item.items())): item for item in alternatives}.values())
    if len(distinct) > 16:
        raise RequiredSetCoverageError("終了規則軸の選言が16件を超える")
    return distinct


def _game_end_requirement_impossible_pairs(
    descriptor: dict[str, Any],
) -> dict[tuple[str, ...], tuple[str, ...]]:
    """F-1の保存条件とdescriptorの上限から不成立の軸値ペアを列挙する。"""
    regulation = "gameEnd.regulationInnings"
    extension = "gameEnd.extensionLimit"
    tiebreak = "gameEnd.tiebreak"
    rules = (
        (regulation, 99, extension, "finite:R+1", ("req:F-1",)),
        (regulation, 99, tiebreak, "start:R+1", ("req:DRAW-03",)),
        (regulation, 99, tiebreak, "start:L", ("req:DRAW-03",)),
        (regulation, 99, tiebreak, "start:99", ("req:DRAW-03",)),
        (extension, "finite:R", tiebreak, "start:R+1", ("req:DRAW-03",)),
        (extension, "finite:R", tiebreak, "start:L", ("req:DRAW-03",)),
        (extension, "finite:R", tiebreak, "start:99", ("req:DRAW-03",)),
        (extension, "none", tiebreak, "start:L", ("req:F-1",)),
    )
    expected: dict[tuple[str, ...], tuple[str, ...]] = {
        (
            "rule-field-pairwise", left_axis, _game_end_identity(left_value),
            right_axis, _game_end_identity(right_value),
        ): clauses
        for left_axis, left_value, right_axis, right_value, clauses in rules
    }
    for pair in descriptor["gameEndCombinationRules"]["derivedUnreachablePairs"]:
        identity = (
            "rule-field-pairwise",
            pair["sourceAxisId"], _game_end_identity(pair["sourceValue"]),
            pair["derivedAxisId"], _game_end_identity(pair["derivedValue"]),
        )
        if identity in expected:
            raise RequiredSetCoverageError("DERIVED_UNREACHABLE: 宣言が重複")
        expected[identity] = tuple(pair["clauseIds"])
    for pair in descriptor["gameEndCombinationRules"]["unreachablePairs"]:
        identity = (
            "boundary-with-state-or-event-axis-value",
            pair["leftAxisId"], _game_end_identity(pair["leftValue"]),
            pair["rightAxisId"], _game_end_identity(pair["rightValue"]),
        )
        if identity in expected:
            raise RequiredSetCoverageError("UNREACHABLE_PAIR: 宣言が重複")
        expected[identity] = tuple(pair["clauseIds"])
    return expected


def _classify_game_end_unreachable(
    declaration: dict[str, Any],
    excluded: set[tuple[str, ...]],
    unfixed_values: set[tuple[str, str]],
    descriptor: dict[str, Any],
) -> dict[str, int]:
    """到達不可要求を典拠付き不成立・未固定値・適用行不在へ分割する。"""
    policy = declaration.get("step23Unreachability")
    if not isinstance(policy, dict) or set(policy) != {
        "classificationOrder", "requirementsImpossible", "countsByCause",
        "beforeUnreachableCount", "remainingUnreachableCount", "nextSteps",
    } or policy["classificationOrder"] != [
        "requirements-impossible", "unfixed-axis-value", "no-applicable-row"
    ]:
        raise RequiredSetCoverageError("S28の分類宣言が不正")
    axes = {item["axisId"]: item for item in descriptor["gameEndAxes"]}
    if (
        axes["gameEnd.regulationInnings"]["coverageBounds"][0]["maximum"] != 99
        or axes["gameEnd.extensionLimit"]["coverageBounds"][0]["maximum"] != 99
        or axes["gameEnd.tiebreak"]["coverageBounds"][0]["maximum"] != 99
        or "finite:100" not in axes["gameEnd.extensionLimit"]["invalidBoundaryValues"]
    ):
        raise RequiredSetCoverageError("S28の99回上限の典拠がdescriptorと不一致")
    expected = _game_end_requirement_impossible_pairs(descriptor)
    records = policy["requirementsImpossible"]
    if not isinstance(records, list) or not all(
        isinstance(item, dict) and set(item) == {"identity", "clauseIds", "basis"}
        and isinstance(item["identity"], list)
        and all(isinstance(part, str) for part in item["identity"])
        and isinstance(item["clauseIds"], list)
        and isinstance(item["basis"], str) and item["basis"]
        for item in records
    ):
        raise RequiredSetCoverageError("S28の要件上の到達不可宣言が不正")
    declared = {tuple(item["identity"]): tuple(item["clauseIds"]) for item in records}
    if len(declared) != len(records) or declared != expected or not set(expected) <= excluded:
        raise RequiredSetCoverageError("S28の要件上の到達不可が典拠・実測と不一致")
    groups: dict[str, set[tuple[str, ...]]] = {
        "noApplicableRow": set(),
        "unfixedAxisValue": set(),
        "requirementsImpossible": set(expected),
    }
    for identity in excluded - set(expected):
        targets = (
            ((identity[1], identity[2]), (identity[3], identity[4]))
            if identity[0] == "rule-field-pairwise"
            else ((identity[1], identity[2]),)
            if identity[0] == "boundary-with-state-or-event-axis-value"
            else ()
        )
        cause = "unfixedAxisValue" if any(
            target in unfixed_values for target in targets
        ) else "noApplicableRow"
        groups[cause].add(identity)

    kind_names = {
        "rule-field-pairwise": "pairwise",
        "boundary-with-state-or-event-axis-value": "boundaryCoordinate",
        "clause-branch": "clauseBranch",
    }
    measured = {
        cause: {
            **{label: sum(item[0] == kind for item in identities)
               for kind, label in kind_names.items()},
            "total": len(identities),
        }
        for cause, identities in groups.items()
    }
    future = policy["nextSteps"]
    # ステップ23の開始時2817件は履歴値として固定し、現在件数は再測定する。
    if (
        policy["countsByCause"] != measured
        or policy["beforeUnreachableCount"] != 2817
        or policy["remainingUnreachableCount"] != len(
            groups["noApplicableRow"] | groups["unfixedAxisValue"]
        )
        or not isinstance(future, dict)
        or set(future) != {"noApplicableRow", "unfixedAxisValue"}
        or not all(isinstance(note, str) and note for note in future.values())
    ):
        raise RequiredSetCoverageError("S28の原因別件数・後続ステップ宣言が実測と不一致")
    return {
        "unreachable": policy["remainingUnreachableCount"],
        "requirementsImpossible": len(expected),
    }


def _game_end_measure(
    root: Path, contract: dict[str, Any], declaration: dict[str, Any],
    *, classify: bool = True,
) -> tuple[dict[str, int], set[tuple[str, ...]], set[tuple[str, ...]], set[tuple[str, ...]]]:
    """終了判定行の到達性と実ケースからの直接充足を独立導出する。

    Args:
        root: リポジトリルート。
        contract: 検査する終了判定契約。
        declaration: 現行の被覆宣言。
        classify: 偽なら過去の行集合を試す際にS28の現行件数を適用しない。
    """
    required, _ = deriver.derive_repository_game_end_required_set(root)
    descriptor = _document(root, "input_axes_descriptor_v1.json")
    values = representative_selection.axis_values(
        descriptor, ("gameEndAxes", "stateTransitionAxes")
    )
    selection_policy = _document(root, "representative_selection_policy_v1.json")
    display_names = _game_end_display_names(root)
    game_axes = {axis["axisId"] for axis in descriptor["gameEndAxes"]}
    rows = contract.get("decisionRows")
    cases = contract.get("cases")
    if not isinstance(rows, list) or not isinstance(cases, list):
        raise RequiredSetCoverageError("終了判定の行またはケースが不正")
    row_by_branch = {row["branchId"]: row for row in rows}
    if len(row_by_branch) != len(rows):
        raise RequiredSetCoverageError("終了判定の行分岐が重複")
    historical_without_walk_off = not classify and "GAME-END-WALK-OFF" not in row_by_branch
    clause_requirements = tuple(
        item for item in required.clause_branch_requirements
        if not historical_without_walk_off or item.branch_id != "XMARK-01"
    )
    branch_register = _document(root, "clause_branch_register_v1.json")
    related_by_branch = {
        branch["branchId"]: set(branch["relatedClauseBranchIds"])
        for branch in branch_register["branches"]
    }
    x_mark_expectations = {
        item["branchId"]: item
        for item in declaration["step95DecisionProperties"]["xMark"]["expectedByBranch"]
    }

    def represented_related_branches(row: dict[str, Any]) -> set[str]:
        """台帳の下位分岐を規範行のX表記と典拠で照合する。"""
        branch_id = row["branchId"]
        expected = x_mark_expectations.get(branch_id)
        if expected is None or row["decision"]["xMark"] != expected["value"]:
            return set()
        return {
            related for related in related_by_branch.get(branch_id, set())
            if related.startswith("XMARK-")
            and f"req:{related}" in expected["clauseIds"]
        }
    fixed_by_row = [_fixed_game_end_alternatives(row, game_axes) for row in rows]
    fixed_values = {
        (axis, value)
        for alternatives in fixed_by_row
        for fixed in alternatives
        for axis, value in fixed.items()
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
    effective_missing = declared_values & missing_values if classify else missing_values
    if classify and effective_missing != missing_values:
        raise RequiredSetCoverageError("未固定の終了規則軸値がexact-set不一致")

    def rows_for(targets: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
        return [
            row for row, alternatives in zip(rows, fixed_by_row, strict=True)
            if any(
                all(fixed.get(axis) == value for axis, value in targets if axis in game_axes)
                for fixed in alternatives
            )
        ]

    def reachable_coordinate(
        row: dict[str, Any], game_axis: str, game_identity: str,
        axis: str, identity: str,
    ) -> bool:
        if axis not in values or game_axis not in values:
            return False
        target = next(
            (value for value in values[axis] if _game_end_identity(value) == identity),
            None,
        )
        game_target = next(
            (value for value in values[game_axis]
             if _game_end_identity(value) == game_identity),
            None,
        )
        if target is None or game_target is None:
            return False
        predicate = representative_selection.reachable_predicate({
            "op": "and",
            "args": [
                row["precondition"],
                {"op": "eq", "axisId": game_axis, "value": game_target},
                {"op": "eq", "axisId": axis, "value": target},
            ],
        }, descriptor["gameEndCombinationRules"]["unreachablePairs"])
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
    if historical_without_walk_off:
        required_ids.discard(("clause-branch", "XMARK-01"))
    reachable: set[tuple[str, ...]] = set()
    for item in required.pairwise_requirements:
        if rows_for(((item.left_axis_id, item.left_value_identity),
                     (item.right_axis_id, item.right_value_identity))):
            reachable.add(item.identity)
    for item in required.boundary_coordinate_requirements:
        candidates = rows_for(((item.game_end_axis_id, item.game_end_value_identity),))
        if any(reachable_coordinate(
            row, item.game_end_axis_id, item.game_end_value_identity,
            item.coordinate_axis_id, item.coordinate_value_identity,
        ) for row in candidates):
            reachable.add(item.identity)
    for item in clause_requirements:
        if item.branch_id in row_by_branch or any(
            item.branch_id in represented_related_branches(row) for row in rows
        ):
            reachable.add(item.identity)
    invalid_ids: set[tuple[str, ...]] = {
        tuple(item.identity) for item in required.invalid_boundary_requirements
    }
    transfer = declaration.get("deferredValidationErrors")
    if not isinstance(transfer, dict) or set(transfer) != {
        "requirementKind", "count", "ownerStep", "targetCollection",
        "status", "verification",
    } or any(transfer.get(key) != value for key, value in {
        "requirementKind": "invalid-boundary", "ownerStep": 96,
        "targetCollection": "validationErrors", "status": "materialized",
        "verification": "derived-exact-set",
    }.items()) or type(transfer.get("count")) is not int or transfer["count"] != len(
        invalid_ids
    ):
        raise RequiredSetCoverageError("不正値拒否の引受宣言と導出件数が不一致")

    raw_branches = declaration.get("uncoveredClauseBranches")
    if not isinstance(raw_branches, list):
        raise RequiredSetCoverageError("条文分岐の未充足宣言がない")
    if not all(
        isinstance(item, dict)
        and set(item) in ({"branchId", "gapId"}, {
            "branchId", "gapId", "crossLayerResolution"
        })
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
    cross_layer = [
        item for item in raw_branches if "crossLayerResolution" in item
    ]
    if len(cross_layer) != 1 or cross_layer[0]["branchId"] != "DRAW-05":
        raise RequiredSetCoverageError("DRAW-05の状況判定への結び付けが不正")
    resolution = cross_layer[0]["crossLayerResolution"]
    if resolution != {
        "layer": "operationRows",
        "caseId": "ST-OPERATION-e6c67c06707d5759",
        "mappingVersion": "branch_row_mapping_v1",
    }:
        raise RequiredSetCoverageError("DRAW-05の状況判定の行参照が不正")
    state_contract = _document(root, "state_transition_contract_v1.json")
    mapping = _document(root, "branch_row_mapping_v1.json")
    state_cases = [
        case for case in state_contract["cases"]
        if case["caseId"] == resolution["caseId"]
    ]
    mapped = [
        item for item in mapping["mappings"] if item["branchId"] == "DRAW-05"
    ]
    if (
        len(state_cases) != 1 or len(mapped) != 1
        or state_cases[0]["rowRef"] != mapped[0]["rowRef"]
        or state_cases[0]["inputCoordinate"].get("state.score") != "tie"
        or state_cases[0]["expected"].get("operationResult") != "applied"
    ):
        raise RequiredSetCoverageError("DRAW-05の状況判定ケースが不正")
    missing_branches = {
        item.branch_id for item in clause_requirements
        if item.identity not in reachable
    }
    if set(branch_gap) != missing_branches:
        raise RequiredSetCoverageError("条文分岐の未充足宣言がexact-set不一致")
    register = _document(root, "gap_register_v1.json")
    gaps = {gap["gapId"]: gap for gap in register["gaps"]}
    if len(gaps) != len(register["gaps"]):
        raise RequiredSetCoverageError("GAP IDが重複")
    requirement_by_branch = {
        item.branch_id: item for item in clause_requirements
    }
    for branch, gap_id in branch_gap.items():
        gap = gaps.get(gap_id)
        if (
            not isinstance(gap, dict)
            or branch not in gap.get("branchIds", [])
        ):
            raise RequiredSetCoverageError(f"GAPの分岐典拠がない: {branch}")
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
            reachable_coordinate(
                row, item.game_end_axis_id, item.game_end_value_identity,
                item.coordinate_axis_id, item.coordinate_value_identity,
            ) for row in candidates
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
    classified = (
        _classify_game_end_unreachable(
            declaration, actual_unreachable, effective_missing, descriptor
        ) if classify else {
            "unreachable": len(actual_unreachable), "requirementsImpossible": 0
        }
    )

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
        if not representative_selection.predicate_holds(row["precondition"], case["raw"]):
            raise RequiredSetCoverageError("終了判定ケースが行前提を満たさない")
        result_id = coordinate.get("event.perPitch.resultId")
        result_name = _result_display_name(result_id, display_names)
        if result_id is not None and result_name != case["raw"].get("event.perPitch.resultId"):
            raise RequiredSetCoverageError("終了判定ケースの結果IDと表示名が不一致")
        actual = {
            axis: _game_end_identity(
                _result_display_name(value, display_names)
                if axis == "event.perPitch.resultId" else value
            )
            for axis, value in coordinate.items()
        }
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
        for related in represented_related_branches(row):
            if ("clause-branch", related) in required_ids:
                observed.add(("clause-branch", related))
    if not observed <= reachable:
        raise RequiredSetCoverageError("終了判定ケースが到達不可要求を充足した")
    counts = {
        "total": len(required_ids), "reachable": len(reachable),
        **classified, "invalid": len(invalid_ids),
        "covered": len(observed), "cases": len(cases),
    }
    return counts, actual_unreachable, reachable, observed


def _check_game_end_decision_properties(
    root: Path, contract: dict[str, Any], declaration: dict[str, Any]
) -> None:
    """宣言した終了判定の出力を全ケースで照合する。"""
    policy = declaration.get("step95DecisionProperties")
    if not isinstance(policy, dict) or set(policy) != {
        "automaticTransition", "branchExpectations", "xMark"
    }:
        raise RequiredSetCoverageError("ステップ95の出力宣言が不正")
    automatic = policy["automaticTransition"]
    if not isinstance(automatic, dict) or set(automatic) != {
        "field", "expected", "clauseIds"
    } or automatic["field"] != "automaticallyEndsGame" or type(
        automatic["expected"]
    ) is not bool:
        raise RequiredSetCoverageError("自動遷移の宣言が不正")
    schema = _document(root, "game_end_contract_schema_v1.json")
    decision_schema = schema.get("$defs", {}).get("gameEndDecision", {})
    schema_fields = decision_schema.get("properties", {})
    if (
        not isinstance(schema_fields, dict)
        or set(decision_schema.get("required", [])) != set(schema_fields)
        or decision_schema.get("additionalProperties") is not False
        or automatic["field"] not in schema_fields
    ):
        raise RequiredSetCoverageError("終了判定decision schemaが不正")
    x_mark = policy["xMark"]
    if not isinstance(x_mark, dict) or set(x_mark) != {
        "status", "decisionField", "targetCell", "clauseIds", "enumValues",
        "observedDecisionFields", "expectedByBranch", "remainingGap"
    } or x_mark["status"] != "represented-in-decision" or x_mark[
        "decisionField"
    ] != "xMark" or x_mark["targetCell"] != "直近に完了した表に対応する裏の得点セル" or set(
        x_mark["observedDecisionFields"]
    ) != set(schema_fields) or x_mark["enumValues"] != [
        "recorded-score", "x-mark", "blank"
    ] or schema_fields.get("xMark", {}).get("enum") != x_mark[
        "enumValues"
    ] or not isinstance(x_mark["remainingGap"], str) or not x_mark["remainingGap"]:
        raise RequiredSetCoverageError("X表記の出力宣言がschemaと不一致")
    requirements = (root / "docs/requirements/requirements-pitchlog-2026-07-22.md").read_text(
        encoding="utf-8"
    )
    branches = policy["branchExpectations"]
    rows = contract.get("decisionRows", [])
    if not isinstance(branches, list) or not all(isinstance(item, dict) and set(item) == {
        "branchId", "lockFurtherPlayInput", "promptEndDeclaration", "clauseIds"
    } for item in branches):
        raise RequiredSetCoverageError("分岐別の出力宣言が不正")
    by_branch = {item["branchId"]: item for item in branches}
    if len(by_branch) != len(branches) or set(by_branch) != {
        row["branchId"] for row in rows
    }:
        raise RequiredSetCoverageError("分岐別の出力宣言がexact-set不一致")
    x_expectations = x_mark["expectedByBranch"]
    if not isinstance(x_expectations, list) or not all(
        isinstance(item, dict) and set(item) == {
            "branchId", "value", "clauseIds", "basis"
        } and isinstance(item["basis"], str) and item["basis"]
        and item["value"] in x_mark["enumValues"]
        for item in x_expectations
    ):
        raise RequiredSetCoverageError("X表記の分岐別期待値が不正")
    x_by_branch = {item["branchId"]: item for item in x_expectations}
    if len(x_by_branch) != len(x_expectations) or set(x_by_branch) != set(by_branch):
        raise RequiredSetCoverageError("X表記の分岐別期待値がexact-set不一致")
    for item in [automatic, x_mark, *branches, *x_expectations]:
        clause_ids = item.get("clauseIds")
        if not isinstance(clause_ids, list) or not clause_ids or not all(
            isinstance(source, str) and source.startswith("req:")
            and source[4:] in requirements for source in clause_ids
        ) or len(set(clause_ids)) != len(clause_ids):
            raise RequiredSetCoverageError("ステップ95の条文典拠が不正")
    for row in rows:
        branch = by_branch[row["branchId"]]
        x_expected = x_by_branch[row["branchId"]]
        if row["decision"]["xMark"] != x_expected["value"]:
            raise RequiredSetCoverageError(
                f"規範行のX表記が典拠別期待値と不一致: {row['branchId']}"
            )
        if not set(row["sourceClauseIds"]) <= set(branch["clauseIds"]):
            raise RequiredSetCoverageError("分岐別の出力宣言の典拠が規範行と不一致")
        for field in ("lockFurtherPlayInput", "promptEndDeclaration"):
            if type(branch[field]) is not bool:
                raise RequiredSetCoverageError(f"分岐別の{field}期待値が不正")
    for case in contract.get("cases", []):
        decision = case.get("decision")
        branch = by_branch.get(case.get("branchId"))
        if not isinstance(decision, dict) or branch is None or set(decision) != set(
            schema_fields
        ):
            raise RequiredSetCoverageError(
                f"終了判定decisionのフィールドが不正: {case.get('caseId')}"
            )
        if decision[automatic["field"]] is not automatic["expected"]:
            raise RequiredSetCoverageError(f"試合状態が自動遷移する: {case.get('caseId')}")
        if decision["xMark"] != x_by_branch[case["branchId"]]["value"]:
            raise RequiredSetCoverageError(f"X表記が分岐別期待値と不一致: {case.get('caseId')}")
        for field in ("lockFurtherPlayInput", "promptEndDeclaration"):
            if decision[field] is not branch[field]:
                raise RequiredSetCoverageError(
                    f"分岐別の{field}期待値と不一致: {case.get('caseId')}"
                )


def _check_game_end_validation_errors(
    root: Path, contract: dict[str, Any], declaration: dict[str, Any],
    state_contract: dict[str, Any] | None = None,
) -> None:
    """不正値拒否の引受と両契約の正常ケースをdescriptorに照合する。"""
    game_schema = _document(root, "game_end_contract_schema_v1.json")
    state_schema = _document(root, "state_transition_contract_schema_v1.json")
    current_state = (
        state_contract if state_contract is not None
        else _document(root, "state_transition_contract_v1.json")
    )
    try:
        for document, schema, name in (
            (contract, game_schema, "gameEnd"),
            (current_state, state_schema, "stateTransition"),
        ):
            deriver.descriptor_checker._validate_instance(document, schema, schema, name)
    except deriver.descriptor_checker.DescriptorCheckError as error:
        raise RequiredSetCoverageError(
            f"正常ケースまたは不正値拒否のschema違反: {error}"
        ) from error

    expected_counts = declaration.get("normalCaseCounts")
    if not isinstance(expected_counts, dict) or set(expected_counts) != {
        "stateTransition", "gameEnd"
    } or any(type(value) is not int or value < 1 for value in expected_counts.values()):
        raise RequiredSetCoverageError("正常ケースの件数宣言が不正")
    if len(contract["cases"]) != expected_counts["gameEnd"] or len(
        current_state["cases"]
    ) != expected_counts["stateTransition"]:
        raise RequiredSetCoverageError("正常ケースの件数が宣言と不一致")

    descriptor = _document(root, "input_axes_descriptor_v1.json")
    axes = {
        axis["axisId"]: axis
        for collection in ("stateTransitionAxes", "gameEndAxes")
        for axis in descriptor[collection]
    }
    legal = {
        axis_id: {
            _game_end_identity(value)
            for value in axis.get("values", axis.get("boundaryValues", []))
        }
        for axis_id, axis in axes.items()
    }
    display_names = _game_end_display_names(root)
    aliases = declaration.get("stateTransitionCaseAliases")
    schema_aliases = {
        field
        for layer in ("matrixRows", "operationRows", "undoRows")
        for field in state_schema["properties"][layer].get(
            "x-pitchlog-input-coordinate-fields", []
        )
    }
    if not isinstance(aliases, list) or not aliases or any(
        not isinstance(alias, str) or not alias for alias in aliases
    ) or len(set(aliases)) != len(aliases) or not set(aliases) <= schema_aliases:
        raise RequiredSetCoverageError("状況判定ケースの別名軸宣言が不正")
    seen_aliases: set[str] = set()
    for name, document in (("stateTransition", current_state), ("gameEnd", contract)):
        for case in document["cases"]:
            coordinate = case.get("inputCoordinate")
            if not isinstance(coordinate, dict):
                raise RequiredSetCoverageError(f"正常ケースの入力座標が不正: {name}")
            for axis_id, value in coordinate.items():
                coverage_value = (
                    _result_display_name(value, display_names)
                    if name == "gameEnd" and axis_id == "event.perPitch.resultId"
                    else value
                )
                if axis_id in legal and _game_end_identity(coverage_value) not in legal[axis_id]:
                    raise RequiredSetCoverageError(
                        f"正常ケースにschema外値がある: {name} {case.get('caseId')} {axis_id}"
                    )
                if name == "gameEnd" and axis_id not in legal:
                    raise RequiredSetCoverageError(
                        f"終了判定ケースに未知の入力軸がある: {case.get('caseId')} {axis_id}"
                    )
                if name == "stateTransition" and axis_id not in legal and axis_id not in aliases:
                    raise RequiredSetCoverageError(
                        f"状況判定ケースに未知の入力軸がある: {case.get('caseId')} {axis_id}"
                    )
                if name == "stateTransition" and axis_id in aliases:
                    seen_aliases.add(axis_id)
            if name == "stateTransition":
                if "eventKind" in coordinate and coordinate[
                    "eventKind"
                ] not in state_schema["$defs"]["eventKind"]["enum"]:
                    raise RequiredSetCoverageError(
                        f"正常ケースにschema外値がある: {name} {case.get('caseId')} eventKind"
                    )
                if "operationKind" in coordinate and _game_end_identity(
                    coordinate["operationKind"]
                ) not in legal["event.operationKind"]:
                    raise RequiredSetCoverageError(
                        f"正常ケースにschema外値がある: {name} {case.get('caseId')} operationKind"
                    )
                if "resultId" in coordinate and coordinate["resultId"] != case.get(
                    "rowRef", {}
                ).get("coordinate", {}).get("resultId"):
                    raise RequiredSetCoverageError(
                        f"正常ケースの結果IDが行参照と不一致: {case.get('caseId')}"
                    )
    if seen_aliases != set(aliases):
        raise RequiredSetCoverageError("状況判定ケースの別名軸宣言が実測と不一致")

    required, _ = deriver.derive_repository_game_end_required_set(root)
    expected = {item.identity: item for item in required.invalid_boundary_requirements}
    entries = contract.get("validationErrors")
    transfer = declaration["deferredValidationErrors"]
    if not isinstance(entries, list) or len(expected) != transfer["count"] or len(
        entries
    ) != transfer["count"]:
        raise RequiredSetCoverageError("validationErrorsの件数が導出要求と不一致")
    actual: set[tuple[str, str, str]] = set()
    for entry in entries:
        identity = ("invalid-boundary", entry["axisId"], entry["valueIdentity"])
        if entry["valueIdentity"] != _game_end_identity(entry["invalidValue"]):
            raise RequiredSetCoverageError("validationErrorsの不正値identityが値と不一致")
        boundary = entry["claimBoundary"]
        shown_value = str(entry["invalidValue"])
        if not all(
            entry["axisId"] in boundary[field] and shown_value in boundary[field]
            for field in ("guaranteed", "notGuaranteed")
        ) or "保証範囲外" not in boundary["notGuaranteed"]:
            raise RequiredSetCoverageError("validationErrorsの各件に保証範囲外の記述がない")
        requirement = expected.get(identity)
        if requirement is None or entry["sourceClauseIds"] != list(
            requirement.source_clause_ids
        ):
            raise RequiredSetCoverageError("validationErrorsが導出要求と不一致")
        if identity in actual:
            raise RequiredSetCoverageError("validationErrorsに重複がある")
        actual.add(identity)
    if actual != set(expected):
        raise RequiredSetCoverageError("validationErrorsが導出要求とexact-set不一致")


def check_derived_axis_cases(
    contract: dict[str, Any], descriptor: dict[str, Any]
) -> None:
    """具体入力の同値性と宣言済み到達不可だけを照合する。"""
    rules = descriptor["gameEndCombinationRules"]
    axes = {
        axis["axisId"]: axis
        for collection in ("stateTransitionAxes", "gameEndAxes")
        for axis in descriptor[collection]
    }
    observations: dict[tuple[str, str], str] = {}
    for case in contract["cases"]:
        raw = case.get("raw")
        source_input = case.get("derivedSourceInput")
        if not isinstance(raw, dict) or not isinstance(source_input, dict):
            raise RequiredSetCoverageError("DERIVED_INPUT: 具体入力がない")
        for axis_id in rules["derivedAxisIds"]:
            derived = axes[axis_id]
            source_ids = derived["derivedFrom"]["sourceAxisIds"]
            if set(source_input) != set(source_ids):
                raise RequiredSetCoverageError("DERIVED_INPUT: 導出元の完全な入力がない")
            if raw.get("state.half") != source_input.get("state.half"):
                raise RequiredSetCoverageError("DERIVED_INPUT: 表裏の入力が不一致")
            cold = source_input.get("gameEnd.coldConditions")
            label = raw.get("gameEnd.coldConditions")
            if not isinstance(cold, list) or label != f"tier-count:{len(cold)}":
                raise RequiredSetCoverageError("DERIVED_INPUT: コールド段の入力が不一致")
            if any(
                not isinstance(tier, dict)
                or set(tier) != {"pointDifference", "startInning"}
                or any(type(value) is not int or value < 1 for value in tier.values())
                for tier in cold
            ):
                raise RequiredSetCoverageError("DERIVED_INPUT: 段の具体入力が不正")
            regulation = raw.get("gameEnd.regulationInnings")
            if type(regulation) is not int or any(
                tier["startInning"] > regulation for tier in cold
            ):
                raise RequiredSetCoverageError(
                    "COLD_RULE_SAVE: 規定回を超えるコールド適用回は保存できない"
                )
            score = source_input.get("state.score")
            if (
                type(source_input.get("state.inning")) is not int
                or not isinstance(score, dict)
                or set(score) != {"home", "away"}
                or any(type(value) is not int or value < 0 for value in score.values())
            ):
                raise RequiredSetCoverageError("DERIVED_INPUT: 状態の具体入力が不正")
            if axis_id not in raw:
                raise RequiredSetCoverageError("DERIVED_INPUT: 派生値がない")
            full_input = {
                source_id: source_input[source_id] for source_id in source_ids
            }
            # 具体入力のキーはASCIIの固定フィールドと整数だけで構成される。
            key = (
                axis_id,
                json.dumps(full_input, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            )
            value = _game_end_identity(raw[axis_id])
            previous = observations.setdefault(key, value)
            if previous != value:
                raise RequiredSetCoverageError(
                    f"DERIVED_FUNCTION: 同じ完全入力から異なる派生値: {axis_id}"
                )
        for pair in rules["derivedUnreachablePairs"]:
            if (
                raw.get(pair["sourceAxisId"]) == pair["sourceValue"]
                and raw.get(pair["derivedAxisId"]) == pair["derivedValue"]
            ):
                raise RequiredSetCoverageError(
                    f"DERIVED_UNREACHABLE: 到達不可の組合せがcaseにある: {case['caseId']}"
                )
        for pair in rules["unreachablePairs"]:
            if (
                raw.get(pair["leftAxisId"]) == pair["leftValue"]
                and raw.get(pair["rightAxisId"]) == pair["rightValue"]
            ):
                raise RequiredSetCoverageError(
                    f"UNREACHABLE_PAIR: 到達不可の組合せがcaseにある: {case['caseId']}"
                )


def check_game_end_concrete_case_consistency(contract: dict[str, Any]) -> None:
    """具体入力が同じcaseの期待値と、終了局面の境界を照合する。

    Args:
        contract: 終了判定契約。

    Raises:
        RequiredSetCoverageError: ラベルの実値や期待値が矛盾する場合。
    """
    observations: dict[str, dict[str, Any]] = {}
    for case in contract["cases"]:
        coordinate = case.get("normalized")
        source = case.get("derivedSourceInput")
        decision = case.get("decision")
        if not isinstance(coordinate, dict) or not isinstance(source, dict):
            raise RequiredSetCoverageError("CONCRETE_INPUT: caseの具体入力がない")
        if coordinate.get("state.inning") == "L+1" and coordinate.get(
            "gameEnd.extensionLimit"
        ) == "finite:R+1":
            regulation = coordinate.get("gameEnd.regulationInnings")
            if type(regulation) is not int or source.get("state.inning") != regulation + 2:
                raise RequiredSetCoverageError("CONCRETE_INNING: L+1の実入力が不一致")
        if case.get("branchId") == "GAME-END-NORMAL" and coordinate.get(
            "state.score"
        ) not in {"away-lead:M+1", "away-lead:M", "away-lead:M-1"}:
            raise RequiredSetCoverageError("NORMAL_SCORE: 先攻リードでない通常終了")
        if case.get("branchId") in {
            "GAME-END-NORMAL", "GAME-END-EXTRA-CONTINUE", "GAME-END-LIMIT-DRAW"
        } and any(
            coordinate.get(axis) != value
            for axis, value in (
                ("state.outs", 0),
                ("state.runners", "empty"),
                ("state.count.strikes", 0),
                ("state.count.balls", 0),
            )
        ):
            raise RequiredSetCoverageError(
                "POST_TURN_STATE: 攻守交代直後の状態で判定しないcaseがある"
            )
        if case.get("branchId") == "XMARK-02" and coordinate.get(
            "gameEnd.extensionLimit"
        ) == "finite:R+1":
            raise RequiredSetCoverageError("XMARK_EXTENSION: 延長回の表で後攻はリードしない")
        if case.get("branchId") == "GAME-END-WALK-OFF" and any(
            coordinate.get(axis) != value
            for axis, value in (
                ("state.outs", 0),
                ("state.runners", "empty"),
                ("event.operationPayload", "not-applicable"),
                ("event.perPitch.pitchEventKind", "pitch-event"),
                ("event.perPitch.runnerEventPayload", "not-required"),
                ("event.perPitch.runnerAdvanceOverridesByRunner", "not-applied"),
                ("event.perPitch.thirdOutTimingByRunner", "not-required"),
                ("event.perPitch.interferenceRuling", "not-required"),
                ("event.perPitch.officialScoringPayload", "no-error"),
                ("event.perPitch.rbi.doublePlayRelayError", "not-required"),
                ("event.perPitch.rbi.runnerContinuityByRunner", "not-required"),
                ("event.perPitch.rbi.wouldScoreWithoutErrorByRunner", "not-required"),
            )
        ):
            raise RequiredSetCoverageError("WALKOFF_MODIFIERS: 得点が変わる修飾子を持つ")
        if isinstance(decision, dict) and decision.get("xMark") == "x-mark" and any(
            coordinate.get(axis) != value
            for axis, value in (
                ("state.outs", 0),
                ("state.runners", "empty"),
                ("state.count.strikes", 0),
                ("state.count.balls", 0),
            )
        ):
            raise RequiredSetCoverageError("XMARK_STARTED: 開始済みの裏にX表記")
        concrete = {**coordinate, **source}
        key = json.dumps(concrete, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        previous = observations.setdefault(key, decision)
        if previous != decision:
            raise RequiredSetCoverageError("CASE_FUNCTION: 同じ具体入力の期待値が不一致")


def check_state_derived_axis_cases(
    contract: dict[str, Any], descriptor: dict[str, Any]
) -> None:
    """状況判定の派生軸を具体入力の関数性と到達不可宣言で照合する。"""
    coverage = descriptor["inputCoordinateCoverage"]
    axes = {axis["axisId"]: axis for axis in descriptor["stateTransitionAxes"]}
    observations: dict[tuple[str, str], str] = {}
    for case in contract["cases"]:
        coordinate = case.get("inputCoordinate")
        if not isinstance(coordinate, dict):
            raise RequiredSetCoverageError("DERIVED_INPUT: 入力座標がない")
        for axis_id in coverage["derivedAxisIds"]:
            if axis_id not in coordinate:
                continue
            source_ids = axes[axis_id]["derivedFrom"]["sourceAxisIds"]
            history_input = case.get("historyInput")
            before = history_input.get("before") if isinstance(history_input, dict) else None
            state_fields = before.get("stateFields") if isinstance(before, dict) else None
            source_input = {}
            for source_id in source_ids:
                if source_id.startswith("state."):
                    if not isinstance(state_fields, dict) or source_id not in state_fields:
                        raise RequiredSetCoverageError("DERIVED_INPUT: 導出元の状態の実値がない")
                    source_input[source_id] = state_fields[source_id]
                elif source_id in coordinate:
                    source_input[source_id] = coordinate[source_id]
                else:
                    raise RequiredSetCoverageError("DERIVED_INPUT: 導出元の完全な入力がない")
            if set(source_input) != set(source_ids):
                raise RequiredSetCoverageError("DERIVED_INPUT: 導出元の完全な入力がない")
            if axis_id not in case.get("raw", {}):
                raise RequiredSetCoverageError("DERIVED_INPUT: 派生値がrawにない")
            key = (axis_id, json.dumps(
                source_input, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ))
            value = _game_end_identity(coordinate[axis_id])
            previous = observations.setdefault(key, value)
            if previous != value:
                raise RequiredSetCoverageError(
                    f"DERIVED_FUNCTION: 同じ完全入力から異なる派生値: {axis_id}"
                )
        for pair in coverage["derivedUnreachablePairs"]:
            if (
                coordinate.get(pair["sourceAxisId"]) == pair["sourceValue"]
                and coordinate.get(pair["derivedAxisId"]) == pair["derivedValue"]
            ):
                raise RequiredSetCoverageError(
                    f"DERIVED_UNREACHABLE: 到達不可の組合せがcaseにある: {case['caseId']}"
                )


def _check_game_end_documents(
    root: Path, contract: dict[str, Any], declaration: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, int]:
    """終了判定資産を独立導出結果と突合する。"""
    if (
        set(declaration) != {
            "schemaVersion", "version", "exclusionRule", "unfixedGameEndAxisValues",
            "uncoveredClauseBranches", "deferredValidationErrors", "checkerAllowedReadPaths",
            "step94Contraction", "step94UnmetCriteria", "step95DecisionProperties",
            "normalCaseCounts", "stateTransitionCaseAliases", "step23Unreachability",
            "unreachableRowSituations", "removedUnreachableCaseIds",
        }
        or declaration.get("schemaVersion") != 1
        or declaration.get("version") != "game_end_coverage_declaration_v1"
    ):
        raise RequiredSetCoverageError("終了判定の除外宣言が不正")
    row_situations = declaration["unreachableRowSituations"]
    expected_situation = {
        "branchId": "XMARK-02",
        "coordinate": {
            "gameEnd.extensionLimit": "finite:R+1",
            "state.inning": "L",
            "state.half": "bottom",
            "state.score": "home-lead:M+1",
        },
        "clauseIds": ["req:FR-005", "req:DRAW-08", "req:F-1"],
    }
    if (
        not isinstance(row_situations, list)
        or len(row_situations) != 1
        or not isinstance(row_situations[0], dict)
        or {key: row_situations[0].get(key) for key in expected_situation}
        != expected_situation
        or not isinstance(row_situations[0].get("basis"), str)
        or not row_situations[0]["basis"]
        or set(row_situations[0]) != {*expected_situation, "basis"}
    ):
        raise RequiredSetCoverageError("XMARK_EXTENSION: 到達不可局面の宣言が不正")
    if any(
        case.get("branchId") == "XMARK-02"
        and all(case.get("normalized", {}).get(axis) == value
                for axis, value in expected_situation["coordinate"].items())
        for case in contract["cases"]
    ):
        raise RequiredSetCoverageError("XMARK_EXTENSION: 到達不可局面がcaseにある")
    rows = contract.get("decisionRows", [])
    walk_off_rows = [row for row in rows if row["decision"]["outcome"] == "walk-off"]
    if len(walk_off_rows) != 1 or walk_off_rows[0]["branchId"] != "GAME-END-WALK-OFF":
        raise RequiredSetCoverageError("walk-off行が台帳の5つ目の役割と一致しない")
    if {row["branchId"] for row in rows if row["branchId"].startswith("COLD-")} != {
        "COLD-08", "COLD-09"
    }:
        raise RequiredSetCoverageError("ステップ94のCOLD行集合が不正")
    branch_register = _document(root, "clause_branch_register_v1.json")
    if (
        branch_register.get("branchCount") != 69
        or branch_register.get("gameEndOutcomeBranches", {}).get("walkOff")
        != walk_off_rows[0]["branchId"]
        or not any(
            branch["branchId"] == walk_off_rows[0]["branchId"]
            and branch["sourceClauseIds"] == walk_off_rows[0]["sourceClauseIds"]
            for branch in branch_register["branches"]
        )
    ):
        raise RequiredSetCoverageError("walk-off行の台帳役割が不正")
    descriptor = _document(root, "input_axes_descriptor_v1.json")
    axes = {axis["axisId"] for axis in descriptor["gameEndAxes"]}
    values = representative_selection.axis_values(descriptor, ("gameEndAxes",))
    all_values = {
        (axis, _game_end_identity(value)) for axis in axes for value in values[axis]
    }
    historical_axes = axes - {"gameEnd.satisfiedColdTierCount"}
    historical_values = all_values - {
        ("gameEnd.satisfiedColdTierCount", _game_end_identity(value))
        for value in values["gameEnd.satisfiedColdTierCount"]
    } - {("gameEnd.coldConditions", _game_end_identity("tier-count:2"))}
    first_four_fixed = {
        (axis, value)
        for row in rows[:4]
        for axis, value in _fixed_game_end_values(row, historical_axes).items()
    }
    current_fixed = {
        (axis, value)
        for row in rows[:5]
        for axis, value in _fixed_game_end_values(row, historical_axes).items()
    }
    before_unfixed = historical_values - first_four_fixed
    after_unfixed = historical_values - current_fixed
    removed = before_unfixed - after_unfixed
    if declaration.get("step94Contraction") != {
        "beforeRowCount": 4,
        "afterRowCount": 5,
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
        ("walkOff", "resolved-decision-row"),
        ("cold09", "resolved-decision-row"),
        ("walkOffScoring", "deferred-to-step32"),
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
    if (
        unmet["walkOff"].get("ownerStep") != 46
        or unmet["walkOff"].get("resolutionStep") != 25
        or unmet["walkOff"].get("resolvedBranchId") != walk_off_rows[0]["branchId"]
        or not any(case["branchId"] == walk_off_rows[0]["branchId"] for case in contract["cases"])
    ) or unmet["cold09"].get(
        "ownerStage"
    ) != 2 or unmet["walkOffScoring"].get("sourceClauseId") != "req:A-1":
        raise RequiredSetCoverageError("ステップ94の未達事項の典拠・送り先が不正")
    _check_game_end_decision_properties(root, contract, declaration)
    _check_game_end_validation_errors(root, contract, declaration)
    generated, trace = expand_game_end_cases.expand_coverage_traced(root)
    expander_policy = expand_game_end_cases.dependency_checker.load_policy(root)
    if trace.observed_read_paths != expander_policy.expanders["game-end-cases"].allowed_read_paths:
        raise RequiredSetCoverageError("終了判定展開器のallowedReadPathsが実測と不一致")
    normalization_fields = {
        "raw", "normalizationRuleId", "normalized", "derivedSourceInput"
    }
    if not isinstance(contract.get("cases"), list) or len(contract["cases"]) != len(generated):
        raise RequiredSetCoverageError("終了判定ケースが代表値展開と不一致")
    check_derived_axis_cases(contract, descriptor)
    check_game_end_concrete_case_consistency(contract)
    for case, expanded in zip(contract["cases"], generated, strict=True):
        if case["inputCoordinate"] != case["normalized"]:
            raise RequiredSetCoverageError("終了判定ケースが代表値展開の正規形と不一致")
        projection = {
            key: value for key, value in case.items()
            if key not in normalization_fields
        }
        projection["inputCoordinate"] = case["raw"]
        if set(case) != (set(expanded) | normalization_fields) or projection != expanded:
            raise RequiredSetCoverageError("終了判定ケースが代表値展開と不一致")
    counts, _, reachable, observed = _game_end_measure(root, contract, declaration)
    # 過去8件は受理済みの記録として保持し、この変更の測定だけを1件追記する。
    # 新軸の追加後に旧descriptorでの要求集合を現行軸へ再解釈しない。
    history = record.get("history") if isinstance(record, dict) else None
    if (
        not isinstance(history, list)
        or len(history) != 9
        or [entry.get("step") for entry in history if isinstance(entry, dict)]
        != [93, 94, 95, 96, 97, 98, 99, 100, 101]
        or record.get("currentStep") != 101
    ):
        raise RequiredSetCoverageError("終了判定の独立被覆履歴の件数・順序が不正")
    prior = history[-2]
    current = history[-1]
    if any(
        earlier.get("after") != later.get("before")
        for earlier, later in zip(history, history[1:])
    ):
        raise RequiredSetCoverageError("終了判定の独立被覆記録が連鎖しない")
    baseline_ids = current.get("baselineCaseIds")
    previous_baseline_ids = prior.get("baselineCaseIds")
    current_case_ids = {case["caseId"] for case in contract["cases"]}
    if (
        not isinstance(baseline_ids, list)
        or len(baseline_ids) != prior.get("after", {}).get("caseCount")
        or set(baseline_ids) != current_case_ids
        or not isinstance(previous_baseline_ids, list)
        or len(previous_baseline_ids) != history[-3].get("after", {}).get("caseCount")
        or not isinstance(declaration["removedUnreachableCaseIds"], list)
        or declaration["removedUnreachableCaseIds"] != [
            f"GE-XMARK-02-COVERAGE-{index:03d}" for index in range(34, 67)
        ]
        or set(previous_baseline_ids) - current_case_ids
        != set(declaration["removedUnreachableCaseIds"])
        or current.get("before") != prior.get("after")
    ):
        raise RequiredSetCoverageError("終了判定の独立被覆履歴が直前記録と連鎖しない")
    encoded = json.dumps(sorted(observed), ensure_ascii=False, separators=(",", ":"))
    expected_after = {
        "caseCount": counts["cases"],
        "coveredCount": len(observed),
        "coveredDigest": "sha256:" + hashlib.sha256(encoded.encode()).hexdigest(),
    }
    if current.get("after") != expected_after or set(current) != {
        "step", "baselineCaseIds", "before", "after"
    }:
        raise RequiredSetCoverageError("終了判定の独立被覆記録が実測と不一致")
    if observed != reachable:
        raise RequiredSetCoverageError("ステップ95の到達可能要求が未充足")
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


class CandidateNormalizationError(RequiredSetCoverageError):
    """既存handoffの拒否分類と候補境界の詳細理由を保持する。"""

    def __init__(self, code: str, detail: str) -> None:
        """拒否分類と理由を記録する。"""
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _candidate_object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    """要求の欠落と未知fieldを区別し、推測補完しない。"""
    if not isinstance(value, dict) or not keys <= set(value):
        raise CandidateNormalizationError("HANDOFF_SHAPE", f"{label}: missing-or-type")
    if set(value) != keys:
        raise CandidateNormalizationError("UNKNOWN_FIELD", label)
    return value


def _candidate_same(actual: object, expected: object, label: str) -> None:
    """boolと整数を混同せず投影との完全一致を検査する。"""
    if _game_end_identity(actual) != _game_end_identity(expected):
        raise CandidateNormalizationError("MAPPING", label)


def replay_p8_candidate_projection(
    projection: dict[str, Any], authorizations: list[dict[str, Any]],
) -> dict[str, Any]:
    """共有計算核の投影receipt列の整合性を検査し、最後の投影を返す。

    得点・終了条件を再計算しない。receiptのafterは信頼境界内の共有核投影器が
    供給し、本関数は順序・参照・採用済みphase/保持条件だけを検証する。

    Args:
        projection: 信頼された投影adapterが渡すscopeとreceipt列。
        authorizations: 同adapterが認可済み記録から解決した操作receipt。

    Returns:
        再生した末尾のafterと投影revision。

    Raises:
        CandidateNormalizationError: 投影列の順序・認可参照・phaseが不整合の場合。
    """
    _candidate_object(projection, {"scope", "receipts"}, "projection")
    scope = _candidate_object(projection["scope"], {"tenantId", "gameId"}, "scope")
    if any(not isinstance(value, str) or not value for value in scope.values()):
        raise CandidateNormalizationError("HANDOFF_SHAPE", "scope-id")
    decision_schema = _document(ROOT, "game_end_contract_schema_v1.json")
    if not isinstance(authorizations, list) or any(not isinstance(x, dict) for x in authorizations):
        raise CandidateNormalizationError("HANDOFF_SHAPE", "authorizations")
    for authorization in authorizations:
        _candidate_object(authorization, {
            "authorizationId", "scope", "eventRef", "action", "expectedRevision", "decision",
        }, "authorization")
        if type(authorization["expectedRevision"]) is not int:
            raise CandidateNormalizationError("HANDOFF_SHAPE", "authorization-revision")
    receipts = projection["receipts"]
    if not isinstance(receipts, list) or not receipts:
        raise CandidateNormalizationError("HANDOFF_SHAPE", "empty-projection")
    previous: dict[str, Any] | None = None
    final: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None
    seen: set[str] = set()
    version = 0
    for sequence, receipt in enumerate(receipts, 1):
        _candidate_object(receipt, {
            "sequence", "receiptId", "eventRef", "eventVersion", "kind", "timing",
            "thirdOut", "authorizationRef", "basedOnEvaluationRef", "after",
        }, "receipt")
        if type(receipt["sequence"]) is not int or receipt["sequence"] != sequence:
            raise CandidateNormalizationError("MAPPING", "projection-sequence")
        if not isinstance(receipt["receiptId"], str) or not receipt["receiptId"]:
            raise CandidateNormalizationError("HANDOFF_SHAPE", "receipt-id")
        if receipt["receiptId"] in seen:
            raise CandidateNormalizationError("MAPPING", "duplicate-receipt")
        seen.add(receipt["receiptId"])
        after = _candidate_object(receipt["after"], {
            "phase", "gameEnded", "decision", "evaluationRef",
        }, "after")
        decision = _candidate_object(after["decision"], {
            "outcome", "endConditionDetected", "lockFurtherPlayInput",
            "promptEndDeclaration", "automaticallyEndsGame", "xMark",
        }, "decision")
        try:
            deriver.descriptor_checker._validate_instance(
                decision, decision_schema["$defs"]["gameEndDecision"], decision_schema,
                "candidate.decision",
            )
        except deriver.descriptor_checker.DescriptorCheckError as error:
            raise CandidateNormalizationError("HANDOFF_SHAPE", "decision-schema") from error
        if any(type(decision[field]) is not bool for field in (
            "endConditionDetected", "lockFurtherPlayInput", "promptEndDeclaration",
            "automaticallyEndsGame",
        )) or type(after["gameEnded"]) is not bool or type(receipt["thirdOut"]) is not bool:
            raise CandidateNormalizationError("HANDOFF_SHAPE", "boolean-fields")
        if decision["automaticallyEndsGame"]:
            raise CandidateNormalizationError("MAPPING", "automatic-ending")
        if type(receipt["eventVersion"]) is not int:
            raise CandidateNormalizationError("HANDOFF_SHAPE", "event-version")
        if not isinstance(receipt["eventRef"], str) or not receipt["eventRef"]:
            raise CandidateNormalizationError("HANDOFF_SHAPE", "event-ref")
        kind = receipt["kind"]
        if kind == "evaluation":
            if (
                receipt["authorizationRef"] is not None
                or receipt["basedOnEvaluationRef"] is not None
            ):
                raise CandidateNormalizationError("HANDOFF_SHAPE", "evaluation-action-fields")
            if previous is not None and previous["phase"] == "declared":
                raise CandidateNormalizationError("MAPPING", "evaluation-before-reopen")
            timing = receipt["timing"]
            if timing == "post-turn":
                if pending is None or not receipt["thirdOut"]:
                    raise CandidateNormalizationError("MAPPING", "post-turn-without-third-out")
                _candidate_same(receipt["eventRef"], pending["eventRef"], "turn-event")
                _candidate_same(receipt["eventVersion"], version, "turn-version")
                pending = None
            elif timing == "post-play":
                if pending is not None or receipt["eventVersion"] != version + 1:
                    raise CandidateNormalizationError("MAPPING", "incomplete-or-skipped-prefix")
                version = receipt["eventVersion"]
                if receipt["thirdOut"]:
                    pending = receipt
            else:
                raise CandidateNormalizationError("HANDOFF_SHAPE", "evaluation-timing")
            if after["evaluationRef"] != receipt["receiptId"] or after["gameEnded"]:
                raise CandidateNormalizationError("MAPPING", "evaluation-state")
            if previous is not None and previous["phase"] == "reopened":
                expected_phase = "reopened"
            elif decision["endConditionDetected"] and decision["lockFurtherPlayInput"]:
                expected_phase = "condition-locked"
            else:
                expected_phase = "playing"
                if decision["endConditionDetected"] or decision["lockFurtherPlayInput"]:
                    raise CandidateNormalizationError("MAPPING", "playing-lock")
            _candidate_same(after["phase"], expected_phase, "evaluation-phase")
            if after["phase"] == "reopened" and (
                decision["lockFurtherPlayInput"]
                or (decision["endConditionDetected"] and not decision["promptEndDeclaration"])
            ):
                raise CandidateNormalizationError("MAPPING", "reopened-flags")
            if pending is None:
                final = after
        elif kind in {"declaration", "reopen"}:
            if pending is not None or final is None or receipt["eventVersion"] != version + 1:
                raise CandidateNormalizationError("MAPPING", "action-before-final-evaluation")
            if receipt["timing"] is not None or receipt["thirdOut"]:
                raise CandidateNormalizationError("HANDOFF_SHAPE", "action-timing")
            _candidate_same(receipt["basedOnEvaluationRef"], final["evaluationRef"], "latest-final")
            matches = [item for item in authorizations if (
                item.get("authorizationId") == receipt["authorizationRef"]
                and item.get("scope") == scope and item.get("eventRef") == receipt["eventRef"]
                and item.get("action") == kind and item.get("expectedRevision") == version
                and item.get("decision") == "allow"
            )]
            if len(matches) != 1:
                raise CandidateNormalizationError("MAPPING", "missing-authorized-action")
            if kind == "declaration":
                if previous is None or previous["phase"] == "declared":
                    raise CandidateNormalizationError("MAPPING", "already-declared")
                _candidate_same(
                    {key: decision[key] for key in (
                        "endConditionDetected", "lockFurtherPlayInput", "outcome",
                    )},
                    {key: final["decision"][key] for key in (
                        "endConditionDetected", "lockFurtherPlayInput", "outcome",
                    )}, "retained-before-declaration",
                )
                if after["phase"] != "declared" or not after["gameEnded"] or (
                    decision["promptEndDeclaration"]
                ):
                    raise CandidateNormalizationError("MAPPING", "declaration-state")
                _candidate_same(after["evaluationRef"], final["evaluationRef"], "retained-ref")
            else:
                if previous is None or previous["phase"] != "declared":
                    raise CandidateNormalizationError("MAPPING", "reopen-without-declaration")
                if after["phase"] != "reopened" or after["gameEnded"] or (
                    decision["lockFurtherPlayInput"]
                ) or (decision["endConditionDetected"] and not decision["promptEndDeclaration"]):
                    raise CandidateNormalizationError("MAPPING", "reopen-state")
                if after["evaluationRef"] != receipt["receiptId"]:
                    raise CandidateNormalizationError("MAPPING", "reopen-evaluation-ref")
                final = after
            version = receipt["eventVersion"]
        else:
            raise CandidateNormalizationError("HANDOFF_SHAPE", "unknown-receipt-kind")
        previous = after
    if pending is not None or previous is None:
        raise CandidateNormalizationError("MAPPING", "unfinished-evaluation")
    return {"scope": scope, "projectionRevision": version, **previous}


def normalize_p8_candidate_context(
    raw: object, *, projection: dict[str, Any], authorizations: list[dict[str, Any]],
) -> dict[str, Any]:
    """要求のphaseを信頼された投影列と照合する。入力権限は付与しない。"""
    request = _candidate_object(raw, {
        "scope", "projectionRevision", "phase", "gameEnded",
    }, "context-request")
    expected = replay_p8_candidate_projection(projection, authorizations)
    _candidate_same(request, {key: expected[key] for key in request}, "projection-context")
    return {**expected, "permissionSource": "existing-operation-authorization"}


def normalize_p8_candidate_score(
    raw: object, *, authoritative_observation: dict[str, Any],
) -> dict[str, Any]:
    """対象プレイ直前/直後の共有核観測へ照合し、得点を再計算しない。"""
    request = _candidate_object(raw, {
        "scope", "projectionRevision", "eventRef", "beforeScore", "afterScore",
    }, "score-request")
    source = _candidate_object(authoritative_observation, {
        "producer", "scope", "eventRef", "beforeAppliedVersion", "afterAppliedVersion",
        "beforeScore", "afterScore",
    }, "score-source")
    source_scope = _candidate_object(source["scope"], {"tenantId", "gameId"}, "score-scope")
    if any(not isinstance(value, str) or not value for value in source_scope.values()) or (
        not isinstance(source["eventRef"], str) or not source["eventRef"]
    ):
        raise CandidateNormalizationError("HANDOFF_SHAPE", "score-source-id")
    if source.get("producer") != "shared-state-transition-projection" or (
        type(source.get("beforeAppliedVersion")) is not int
        or type(source.get("afterAppliedVersion")) is not int
        or source["beforeAppliedVersion"] < 0
        or source["afterAppliedVersion"] != source["beforeAppliedVersion"] + 1
    ):
        raise CandidateNormalizationError("MAPPING", "score-projection-prefix")
    for field in ("beforeScore", "afterScore"):
        scores = _candidate_object(source[field], {"home", "away"}, field)
        if any(type(value) is not int or value < 0 for value in scores.values()):
            raise CandidateNormalizationError("HANDOFF_SHAPE", "score-value")
    expected = {key: source[key] for key in request if key != "projectionRevision"}
    expected["projectionRevision"] = source["afterAppliedVersion"]
    _candidate_same(request, expected, "authoritative-score-observation")
    return expected


def normalize_p8_candidate_operation(
    raw: object, *, descriptor: dict[str, Any], adopted_clauses: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """既存descriptorの操作種別とpayloadタグを正規化前に照合する。"""
    request = _candidate_object(raw, {"operationKind", "operationPayload"}, "operation")
    axes = {axis["axisId"]: axis for axis in descriptor["stateTransitionAxes"]}
    kind = request["operationKind"]
    tag = request["operationPayload"]
    if (
        not isinstance(kind, str) or kind not in axes["event.operationKind"]["values"]
        or not isinstance(tag, str) or tag not in axes["event.operationPayload"]["boundaryValues"]
    ):
        raise CandidateNormalizationError("HANDOFF_SHAPE", "unknown-kind-or-payload-tag")
    if kind == "state-correction" and "req:FR-040" not in adopted_clauses:
        raise CandidateNormalizationError("HANDOFF_SHAPE", "conditional-operation-not-active")
    expected_tag = "not-applicable" if kind in {"per-pitch", "undo"} else kind
    if tag != expected_tag:
        raise CandidateNormalizationError("HANDOFF_SHAPE", "operation-payload-kind-mismatch")
    return dict(request)


def compare_p8_candidate_display(expected: object, output: object) -> None:
    """表示oracleと出力の対象・投影版・表示を比較する。由来を認証しない。"""
    fields = {"scope", "projectionRevision", "targetCell", "display"}
    _candidate_object(expected, fields, "display-expected")
    _candidate_object(output, fields, "display-output")
    _candidate_same(output, expected, "display-comparison")


def _check_p8_boundary_evidence(root: Path, bundle: dict[str, Any]) -> dict[str, int]:
    """採用済み境界の人工fixtureを実行し、製品/P-6検証と区別する。"""
    path = root / "docs/features/t2-provenance-checker/candidates/p8_boundary_evidence_v1.json"
    content = path.read_bytes()
    if "sha256:" + hashlib.sha256(content).hexdigest() != bundle["boundaryEvidenceDigest"]:
        raise RequiredSetCoverageError("候補境界fixtureのdigestが不一致")
    evidence = json.loads(content)
    if (
        evidence["evidenceKind"] != "author-synthetic-fixtures"
        or evidence["independentVerification"] != "not-performed"
        or evidence["productOutputVerification"] != "not-performed"
    ):
        raise RequiredSetCoverageError("人工fixtureを独立/製品検証へ転用できない")
    for case in evidence["contextCases"]:
        result = normalize_p8_candidate_context(
            case["request"], projection=case["projection"], authorizations=case["authorizations"],
        )
        _candidate_same(result, case["expected"], "context-expected")
    for case in evidence["scoreObservationCases"]:
        result = normalize_p8_candidate_score(
            case["request"], authoritative_observation=case["source"],
        )
        _candidate_same(result, case["expected"], "score-expected")
    descriptor = _document(root, "input_axes_descriptor_v1.json")
    for case in evidence["operationCases"]:
        try:
            normalized = normalize_p8_candidate_operation(case["request"], descriptor=descriptor)
        except CandidateNormalizationError as error:
            if error.code != case["expected"]:
                raise RequiredSetCoverageError("操作拒否分類が候補と不一致") from error
        else:
            if case["expected"] != "accepted" or normalized != case["request"]:
                raise RequiredSetCoverageError("操作候補が拒否境界と不一致")
    display_by_id = {case["caseId"]: case for case in bundle["displayCases"]}
    for case in evidence["displayComparisons"]:
        compare_p8_candidate_display(case["expected"], case["syntheticOutput"])
        fixture = display_by_id[case["caseId"]]
        _candidate_same(
            {"sourceBranch": fixture["sourceBranch"], "input": fixture["input"]},
            {"sourceBranch": case["sourceBranch"], "input": case["input"]},
            "display-approved-input",
        )
        _candidate_same(
            case["expected"]["targetCell"], fixture["input"]["targetCell"], "display-cell",
        )
        token = {"blank": "", "x-mark": "X", "recorded-score": str(
            fixture["input"]["recordedScore"]
        )}[fixture["expected"]]
        _candidate_same(case["expected"]["display"], token, "display-token")
    return {key: len(evidence[key]) for key in (
        "contextCases", "scoreObservationCases", "operationCases", "displayComparisons",
    )}


def check_game_end_candidate(root: Path, candidate_path: Path) -> dict[str, object]:
    """未受理候補だけを検査し、正式被覆やP-6の成立とは区別して返す。

    Args:
        root: リポジトリルート。
        candidate_path: feature配下の候補bundle。

    Returns:
        相関要求、既承認出力の候補、未成立ゲートの件数と状態。

    Raises:
        RequiredSetCoverageError: schema、要求集合、実入力、期待値が不整合の場合。
    """
    import check_human_review_signature as signature_checker

    try:
        bundle = json.loads(candidate_path.read_text(encoding="utf-8"))
        schema = json.loads((root / (
            "docs/features/t2-provenance-checker/candidates/p8_candidate_schema_v1.json"
        )).read_text(encoding="utf-8"))
        deriver.descriptor_checker._validate_instance(bundle, schema, schema, "candidate")
        base = _document(root, "game_end_contract_v1.json")
        signature_schema = _document(root, "human_review_signature_schema_v1.json")
        limit = signature_schema["x-pitchlog-human-review-signature-policy"][
            "subjectDigest"
        ]["safeIntegerLimit"]
        if signature_checker.compute_subject_digest(base, limit) != bundle["baseContractDigest"]:
            raise RequiredSetCoverageError("候補の基準T2契約digestが現物と不一致")
        base_schema_path = root / ASSET_DIR / "game_end_contract_schema_v1.json"
        schema_digest = "sha256:" + hashlib.sha256(base_schema_path.read_bytes()).hexdigest()
        if schema_digest != bundle["baseSchemaDigest"]:
            raise RequiredSetCoverageError("候補の基準T2 schema digestが現物と不一致")
        base_schema = _document(root, "game_end_contract_schema_v1.json")
        if set(schema["$defs"]) != {
            "ruleSnapshot", "coldConditionTier", "tiebreakRule", "gameEndDecision",
            "normalizedCase",
        } or any(
            definition != base_schema["$defs"][name]
            for name, definition in schema["$defs"].items()
        ):
            raise RequiredSetCoverageError("候補schemaの参照閉包が基準T2 schemaと不一致")
        requirements = deriver.derive_game_end_rule_correlations(bundle["sourceDescriptor"])
        expected = {
            item.case_id: {
                "caseId": item.case_id,
                "ruleSnapshot": dict(item.rule_snapshot),
                "expected": item.expected,
                "sourceClauseIds": list(item.source_clause_ids),
            }
            for item in requirements
        }
        entries = bundle["ruleValidationCases"]
        actual = {item["caseId"]: item for item in entries}
        if len(actual) != len(entries) or actual != expected:
            raise RequiredSetCoverageError("相関候補が導出要求とexact-set不一致")

        rows = {row["branchId"]: row for row in base["decisionRows"]}
        expected_ids = {
            "GE-CANDIDATE-E08-COLD-PRIORITY", "GE-CANDIDATE-E06-ONE-OF-TWO",
            "GE-CANDIDATE-E06-NONE", "GE-CANDIDATE-E04-ORDER-A",
            "GE-CANDIDATE-E04-ORDER-B",
        }
        cases = bundle["decisionCases"]
        if len(cases) != len(expected_ids) or {case["caseId"] for case in cases} != expected_ids:
            raise RequiredSetCoverageError("裁定追随候補のcase集合が不一致")
        for case in cases:
            source_branch = case["branchId"]
            if case["caseId"] == "GE-CANDIDATE-E08-COLD-PRIORITY":
                source_branch = "GAME-END-NORMAL"
                expected_decision = dict(rows["GAME-END-NORMAL"]["decision"])
                expected_decision["outcome"] = rows["COLD-08"]["decision"]["outcome"]
            else:
                branch = rows.get(case["branchId"])
                if branch is None:
                    raise RequiredSetCoverageError("裁定追随候補の基準分岐が未知")
                expected_decision = branch["decision"]
            if case["decision"] != expected_decision:
                raise RequiredSetCoverageError("裁定追随候補の期待値が基準行と不一致")
            reference_case = next(
                item for item in base["cases"] if item["caseId"] == f"GE-{source_branch}"
            )
            if (
                set(case) != set(reference_case)
                or case["rowRef"] != {
                    "layer": "decisionRows", "coordinate": {"branchId": case["branchId"]}
                }
                or set(case["inputCoordinate"]) != set(reference_case["inputCoordinate"])
            ):
                raise RequiredSetCoverageError("裁定追随候補のキー集合または行参照が不一致")
            for field in ("raw", "normalized"):
                if case[field] != case["inputCoordinate"]:
                    raise RequiredSetCoverageError("裁定追随候補の正規化トリプルが不一致")
        descriptor = _document(root, "input_axes_descriptor_v1.json")
        check_derived_axis_cases({"cases": cases}, descriptor)
        check_game_end_concrete_case_consistency({"cases": cases})
        ordered = {case["caseId"]: case for case in cases}
        # 一般のコールド計算を複製せず、E06の「設定2段・成立1段」を示す固定入力を拘束する。
        # 5回裏7対0では7点差@5回だけが成立し、10点差@7回はまだ成立しない。
        if ordered["GE-CANDIDATE-E06-ONE-OF-TWO"]["derivedSourceInput"] != {
            "gameEnd.coldConditions": [
                {"pointDifference": 7, "startInning": 5},
                {"pointDifference": 10, "startInning": 7},
            ],
            "state.inning": 5,
            "state.half": "bottom",
            "state.score": {"home": 7, "away": 0},
        }:
            raise RequiredSetCoverageError("E06候補の設定2段・成立1段の固定入力が不一致")
        overlap = ordered["GE-CANDIDATE-E08-COLD-PRIORITY"]
        overlap_input = overlap["inputCoordinate"]
        if (
            overlap["branchId"] != "COLD-NORMAL-OVERLAP"
            or overlap_input["gameEnd.extensionLimit"] != "finite:R"
            or overlap_input["state.inning"] != "L+1"
            or overlap_input["state.half"] != "top"
            or overlap["derivedSourceInput"]["state.inning"]
            != overlap_input["gameEnd.regulationInnings"] + 1
            or overlap["derivedSourceInput"]["gameEnd.coldConditions"] != [
                {"pointDifference": 10, "startInning": 9}
            ]
            or overlap["derivedSourceInput"]["state.score"] != {"home": 0, "away": 10}
        ):
            raise RequiredSetCoverageError("E08候補が規定最終回裏完了の競合を保持していない")
        for case_id, branch, satisfied in (
            ("GE-CANDIDATE-E06-ONE-OF-TWO", "COLD-08", 1),
            ("GE-CANDIDATE-E06-NONE", "GAME-END-EXTRA-CONTINUE", 0),
            ("GE-CANDIDATE-E04-ORDER-A", "COLD-09", 2),
            ("GE-CANDIDATE-E04-ORDER-B", "COLD-09", 2),
        ):
            case = ordered[case_id]
            if (
                case["branchId"] != branch
                or case["inputCoordinate"]["gameEnd.coldConditions"] != "tier-count:2"
                or case["inputCoordinate"]["gameEnd.satisfiedColdTierCount"] != satisfied
            ):
                raise RequiredSetCoverageError("コールド設定段数と成立段数の候補が不一致")
        left = ordered["GE-CANDIDATE-E04-ORDER-A"]
        right = ordered["GE-CANDIDATE-E04-ORDER-B"]
        left_source = left["derivedSourceInput"]
        right_source = right["derivedSourceInput"]
        if (
            left["inputCoordinate"] != right["inputCoordinate"]
            or left["decision"] != right["decision"]
            or {k: v for k, v in left_source.items() if k != "gameEnd.coldConditions"}
            != {k: v for k, v in right_source.items() if k != "gameEnd.coldConditions"}
            or left_source["gameEnd.coldConditions"]
            != list(reversed(right_source["gameEnd.coldConditions"]))
        ):
            raise RequiredSetCoverageError("段配列逆順の候補入力または期待値が不一致")
        for collection, expected_case_ids in (
            ("lifecycleCases", {
                "GE-CANDIDATE-E02-DECLARED", "GE-CANDIDATE-E10-REOPENED",
                "GE-CANDIDATE-E09-LOCKED",
            }),
            ("displayCases", {
                "DISPLAY-COLD-AFTER-TOP", "DISPLAY-FUTURE", "DISPLAY-STARTED-BOTTOM",
                "DISPLAY-DECLARED-UNSTARTED", "DISPLAY-STARTED-BEFORE-FIRST-PITCH",
            }),
        ):
            entries_by_id = {case["caseId"]: case for case in bundle[collection]}
            if (
                len(bundle[collection]) != len(expected_case_ids)
                or set(entries_by_id) != expected_case_ids
            ):
                raise RequiredSetCoverageError(f"{collection}の候補集合がexact-set不一致")
        boundary_counts = _check_p8_boundary_evidence(root, bundle)
    except (
        OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError,
        deriver.descriptor_checker.DescriptorCheckError,
    ) as error:
        raise RequiredSetCoverageError(f"候補を検査できない: {error}") from error
    return {
        "publication": "candidate-only",
        "independentVerification": "not-performed",
        "ruleCorrelations": len(entries),
        "decisionCases": len(cases),
        "lifecycleCases": len(bundle["lifecycleCases"]),
        "displayCases": len(bundle["displayCases"]),
        **boundary_counts,
        "runtimeOutputsCompared": False,
        "formalCoverageUpdated": False,
    }


def main(argv: list[str] | None = None) -> int:
    """実資産に状況判定と終了判定の検査を適用する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, help="未受理のP-8候補のみを検査する")
    args = parser.parse_args(argv)
    try:
        if args.candidate is not None:
            result = check_game_end_candidate(ROOT, args.candidate)
            print(f"P-8候補検査（正式被覆・P-6未成立）: {result}")
            return 0
        sizes = check_contract_sizes(ROOT)
        rows = check_row_requirements(ROOT)
        coverage = check_input_coverage(ROOT)
        exact = check_input_coverage_exact(ROOT)
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
    print(
        f"requiredSet被覆: PASS: rows={rows}; input={coverage}; "
        f"inputExact={exact}; gameEnd={game_end}; contractBytes={sizes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
