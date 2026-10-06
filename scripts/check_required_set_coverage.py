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
    fixed_state_values: dict[str, set[str]] = {}
    for axis in descriptor.get("stateTransitionAxes", []):
        axis_id = axis.get("axisId") if isinstance(axis, dict) else None
        if not isinstance(axis_id, str) or not axis_id.startswith("state."):
            continue
        fixed = set().union(*(
            _row_fixed_input_values(row["precondition"], axis_id)
            for row in matrix_rows
        ))
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
    observed = observed_input_coverage(cases, active, contract, display_names)
    required_ids = {item.identity for item in active}
    if not observed <= required_ids:
        raise RequiredSetCoverageError("②に要求外の被覆がある")

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
        identity = item.identity[1]
        if axis_id in fixed_state_values and identity not in fixed_state_values[axis_id]:
            return False
        fixed_values = _row_fixed_input_values(row["precondition"], axis_id)
        if fixed_values and fixed_values != {identity}:
            return False
        if axis_id in unbound and layer == "matrixRows":
            explicitly_fixed = bool(fixed_values)
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
    display_names = _game_end_display_names(root)
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
    if not observed <= reachable:
        raise RequiredSetCoverageError("終了判定ケースが到達不可要求を充足した")
    counts = {
        "total": len(required_ids), "reachable": len(reachable),
        "unreachable": len(actual_unreachable), "invalid": len(invalid_ids),
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
        "status", "decisionField", "clauseIds", "searchedScope",
        "observedDecisionFields", "reason"
    } or x_mark["status"] != "not-represented-in-decision" or x_mark[
        "decisionField"
    ] is not None or set(x_mark["observedDecisionFields"]) != set(
        schema_fields
    ) or not isinstance(x_mark["reason"], str) or not x_mark["reason"]:
        raise RequiredSetCoverageError("X表記の出力不在宣言が実測と不一致")
    if not isinstance(x_mark["searchedScope"], list) or not x_mark[
        "searchedScope"
    ] or not all(isinstance(item, str) and item for item in x_mark["searchedScope"]):
        raise RequiredSetCoverageError("X表記の調査範囲が不正")
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
    for item in [automatic, x_mark, *branches]:
        clause_ids = item.get("clauseIds")
        if not isinstance(clause_ids, list) or not clause_ids or not all(
            isinstance(source, str) and source.startswith("req:")
            and source[4:] in requirements for source in clause_ids
        ) or len(set(clause_ids)) != len(clause_ids):
            raise RequiredSetCoverageError("ステップ95の条文典拠が不正")
    for row in rows:
        branch = by_branch[row["branchId"]]
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
            "normalCaseCounts", "stateTransitionCaseAliases",
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
    _check_game_end_decision_properties(root, contract, declaration)
    _check_game_end_validation_errors(root, contract, declaration)
    generated, trace = expand_game_end_cases.expand_coverage_traced(root)
    expander_policy = expand_game_end_cases.dependency_checker.load_policy(root)
    if trace.observed_read_paths != expander_policy.expanders["game-end-cases"].allowed_read_paths:
        raise RequiredSetCoverageError("終了判定展開器のallowedReadPathsが実測と不一致")
    normalization_fields = {"raw", "normalizationRuleId", "normalized"}
    if not isinstance(contract.get("cases"), list) or len(contract["cases"]) != len(generated):
        raise RequiredSetCoverageError("終了判定ケースが代表値展開と不一致")
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
