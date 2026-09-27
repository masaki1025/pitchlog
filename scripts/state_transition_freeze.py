"""状態遷移契約の凍結基準宣言と追記専用の受理履歴を検証する。"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

FREEZE_FIELD = "freezeBaseline"
ACCEPTANCE_ID_PATTERN = re.compile(r"^[^/#\s]+/[^/#\s]+#[1-9][0-9]*$")


class FreezeBaselineError(Exception):
    """凍結基準宣言を検証できない、または不一致の場合を表す。"""


def canonicalize(value: object) -> bytes:
    """基準識別値用の決定的な JSON 表現を返す。

    基準値は整数・文字列・真偽値・null・配列・object に限定し、object の
    キーを Unicode コードポイント順に並べ、空白なし・UTF-8 で符号化する。
    """
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise FreezeBaselineError(f"基準値を正規化できない: {error}") from error
    return encoded.encode("utf-8")


def criterion_identity(section: object) -> str:
    """checker 単位の基準 object の SHA-256 識別値を返す。"""
    return f"sha256:{hashlib.sha256(canonicalize(section)).hexdigest()}"


def _scope_criterion_order(scope: Mapping[str, Any]) -> tuple[str, ...]:
    """宣言された凍結基準の順序を返す。"""
    order = scope.get("criterionOrder")
    bindings = scope.get("criterionBindings")
    if (
        not isinstance(order, list)
        or not order
        or not all(isinstance(item, str) and item for item in order)
        or len(order) != len(set(order))
        or not isinstance(bindings, dict)
        or set(order) != set(bindings)
    ):
        raise FreezeBaselineError(
            "freezeBaseline.scopeのcriterionOrderとcriterionBindingsがexact-set不一致"
        )
    return tuple(order)


def current_identities(declaration: Mapping[str, Any]) -> list[dict[str, str]]:
    """宣言自身と全基準の識別値を宣言順で返す。"""
    scope = declaration.get("scope")
    criteria = declaration.get("criteria")
    if not isinstance(scope, dict) or not isinstance(criteria, dict):
        raise FreezeBaselineError("凍結基準のscopeまたはcriteriaがobjectでない")
    scope_identity_id = _require_non_empty_string(
        scope.get("identityCriterionId"), "scope.identityCriterionId"
    )
    criterion_order = _scope_criterion_order(scope)
    if scope_identity_id in criterion_order:
        raise FreezeBaselineError("scope identityのIDがcriterion IDと重複している")
    return [
        {
            "criterionId": scope_identity_id,
            "identity": criterion_identity(scope),
        },
        *(
        {
            "criterionId": section_name,
            "identity": criterion_identity(criteria[section_name]),
        }
        for section_name in criterion_order
        ),
    ]


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    """object のキー集合を exact-set で検査する。"""
    actual = set(value)
    if actual != expected:
        raise FreezeBaselineError(
            f"{label}のキーがexact-set不一致: "
            f"missing={sorted(expected - actual)!r}; "
            f"unexpected={sorted(actual - expected)!r}"
        )


def _require_non_empty_string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise FreezeBaselineError(f"{label}は空でない文字列でなければならない")
    return value


def validate_declaration(value: object) -> dict[str, Any]:
    """資産側の凍結基準宣言と履歴の内部整合を fail-closed で検証する。"""
    if not isinstance(value, dict):
        raise FreezeBaselineError(f"{FREEZE_FIELD}はJSON objectでなければならない")
    _require_exact_keys(
        value,
        {
            "schemaVersion",
            "series",
            "acceptance",
            "identitySpec",
            "scope",
            "criteria",
            "history",
        },
        FREEZE_FIELD,
    )
    series = _require_non_empty_string(value.get("series"), "freezeBaseline.series")

    scope = value.get("scope")
    if not isinstance(scope, dict):
        raise FreezeBaselineError("freezeBaseline.scopeがobjectでない")
    _require_exact_keys(
        scope,
        {
            "identityCriterionId",
            "criterionOrder",
            "criterionBindings",
            "assuranceBoundary",
            "selectionRule",
            "sourceLiteralAudit",
            "engineExpectedValues",
        },
        "freezeBaseline.scope",
    )
    engine_expected = scope.get("engineExpectedValues")
    if not isinstance(engine_expected, dict):
        raise FreezeBaselineError("scope.engineExpectedValuesがobjectでない")
    _require_exact_keys(
        engine_expected,
        {
            "schemaVersion",
            "acceptance",
            "identitySpec",
            "criterionBindingKind",
        },
        "scope.engineExpectedValues",
    )
    expected_schema_version = engine_expected.get("schemaVersion")
    if not isinstance(expected_schema_version, int) or isinstance(
        expected_schema_version, bool
    ):
        raise FreezeBaselineError("engineExpectedValues.schemaVersionが整数でない")
    if value.get("schemaVersion") != engine_expected["schemaVersion"]:
        raise FreezeBaselineError("freezeBaseline.schemaVersionが凍結基準と一致しない")

    acceptance = value.get("acceptance")
    if not isinstance(acceptance, dict):
        raise FreezeBaselineError("freezeBaseline.acceptanceがobjectでない")
    _require_exact_keys(
        acceptance,
        {
            "unit",
            "acceptanceIdSource",
            "baseRef",
            "baseCommit",
            "posteriorState",
        },
        "freezeBaseline.acceptance",
    )
    acceptance_expected = engine_expected.get("acceptance")
    if not isinstance(acceptance_expected, dict) or not acceptance_expected:
        raise FreezeBaselineError("engineExpectedValues.acceptanceが不正")
    _require_exact_keys(
        acceptance_expected,
        {"unit", "acceptanceIdSource", "posteriorState"},
        "engineExpectedValues.acceptance",
    )
    for key, expected in acceptance_expected.items():
        if acceptance.get(key) != expected:
            raise FreezeBaselineError(
                f"freezeBaseline.acceptance.{key}が凍結基準と一致しない"
            )
    _require_non_empty_string(acceptance.get("baseRef"), "acceptance.baseRef")
    base_commit = _require_non_empty_string(
        acceptance.get("baseCommit"), "acceptance.baseCommit"
    )
    if re.fullmatch(r"[0-9a-f]{40}", base_commit) is None:
        raise FreezeBaselineError("acceptance.baseCommitが40桁のcommit SHAでない")
    identity_spec = value.get("identitySpec")
    if not isinstance(identity_spec, dict):
        raise FreezeBaselineError("freezeBaseline.identitySpecがobjectでない")
    _require_exact_keys(
        identity_spec,
        {"granularity", "algorithm", "canonicalization", "encoding"},
        "freezeBaseline.identitySpec",
    )
    expected_identity_spec = engine_expected.get("identitySpec")
    if not isinstance(expected_identity_spec, dict):
        raise FreezeBaselineError("engineExpectedValues.identitySpecがobjectでない")
    _require_exact_keys(
        expected_identity_spec,
        {"granularity", "algorithm", "canonicalization", "encoding"},
        "engineExpectedValues.identitySpec",
    )
    if identity_spec != expected_identity_spec:
        raise FreezeBaselineError(
            "freezeBaseline.identitySpecが凍結基準と一致しない"
        )
    _require_non_empty_string(
        scope.get("identityCriterionId"), "scope.identityCriterionId"
    )
    criterion_order = _scope_criterion_order(scope)
    bindings = scope["criterionBindings"]
    binding_kind = _require_non_empty_string(
        engine_expected.get("criterionBindingKind"),
        "engineExpectedValues.criterionBindingKind",
    )
    for criterion_id in criterion_order:
        binding = bindings[criterion_id]
        if (
            not isinstance(binding, dict)
            or set(binding) != {"kind", "sourcePath"}
            or binding.get("kind") != binding_kind
        ):
            raise FreezeBaselineError(
                f"scope.criterionBindings.{criterion_id}の型が不正"
            )
        _require_non_empty_string(
            binding.get("sourcePath"),
            f"scope.criterionBindings.{criterion_id}.sourcePath",
        )
    source_paths = [bindings[item]["sourcePath"] for item in criterion_order]
    if len(source_paths) != len(set(source_paths)):
        raise FreezeBaselineError("criterionBindingsのsourcePathが重複している")

    assurance = scope.get("assuranceBoundary")
    if not isinstance(assurance, dict):
        raise FreezeBaselineError("scope.assuranceBoundaryがobjectでない")
    _require_exact_keys(
        assurance,
        {"mechanicallyGuaranteed", "notMechanicallyGuaranteed"},
        "scope.assuranceBoundary",
    )
    guaranteed = assurance.get("mechanicallyGuaranteed")
    if not isinstance(guaranteed, dict):
        raise FreezeBaselineError("assuranceBoundary.mechanicallyGuaranteedがobjectでない")
    _require_exact_keys(
        guaranteed,
        {
            "subjectJsonPointers",
            "identitySource",
            "changeWithoutAcceptanceRecord",
        },
        "assuranceBoundary.mechanicallyGuaranteed",
    )
    subject_pointers = guaranteed.get("subjectJsonPointers")
    expected_subject_pointers = {
        f"/{FREEZE_FIELD}/scope",
        f"/{FREEZE_FIELD}/criteria",
    }
    if (
        not isinstance(subject_pointers, list)
        or set(subject_pointers) != expected_subject_pointers
        or len(subject_pointers) != len(expected_subject_pointers)
    ):
        raise FreezeBaselineError("機械保証対象がscopeとcriteriaのexact-setでない")
    for key in ("identitySource", "changeWithoutAcceptanceRecord"):
        _require_non_empty_string(
            guaranteed.get(key), f"assuranceBoundary.mechanicallyGuaranteed.{key}"
        )
    not_guaranteed = assurance.get("notMechanicallyGuaranteed")
    if not isinstance(not_guaranteed, dict):
        raise FreezeBaselineError(
            "assuranceBoundary.notMechanicallyGuaranteedがobjectでない"
        )
    _require_exact_keys(
        not_guaranteed,
        {"propertyId", "reason", "normativeStatus", "reviewControl"},
        "assuranceBoundary.notMechanicallyGuaranteed",
    )
    for key in ("propertyId", "reason", "normativeStatus", "reviewControl"):
        _require_non_empty_string(
            not_guaranteed.get(key),
            f"assuranceBoundary.notMechanicallyGuaranteed.{key}",
        )

    selection_rule = scope.get("selectionRule")
    if not isinstance(selection_rule, dict) or not selection_rule:
        raise FreezeBaselineError("scope.selectionRuleが空でないobjectでない")
    _require_exact_keys(
        selection_rule,
        {
            "includedComparison",
            "requiredRepresentation",
            "excludedOperandRoles",
            "knownDirectComparisonDispositions",
        },
        "scope.selectionRule",
    )
    included_comparison = selection_rule.get("includedComparison")
    if not isinstance(included_comparison, dict):
        raise FreezeBaselineError("selectionRule.includedComparisonがobjectでない")
    _require_exact_keys(
        included_comparison,
        {"leftOperandOrigin", "operatorKinds", "rightOperandOrigin"},
        "selectionRule.includedComparison",
    )
    _require_non_empty_string(
        included_comparison.get("leftOperandOrigin"),
        "includedComparison.leftOperandOrigin",
    )
    _require_non_empty_string(
        included_comparison.get("rightOperandOrigin"),
        "includedComparison.rightOperandOrigin",
    )
    operators = included_comparison.get("operatorKinds")
    excluded_roles = selection_rule.get("excludedOperandRoles")
    if (
        not isinstance(operators, list)
        or not operators
        or not all(isinstance(item, str) and item for item in operators)
        or len(operators) != len(set(operators))
        or not isinstance(excluded_roles, list)
        or not excluded_roles
        or not all(isinstance(item, str) and item for item in excluded_roles)
        or len(excluded_roles) != len(set(excluded_roles))
    ):
        raise FreezeBaselineError("selectionRuleの列挙が閉じていない")
    _require_non_empty_string(
        selection_rule.get("requiredRepresentation"),
        "selectionRule.requiredRepresentation",
    )
    known_dispositions = selection_rule.get("knownDirectComparisonDispositions")
    if not isinstance(known_dispositions, list) or not known_dispositions:
        raise FreezeBaselineError(
            "selectionRule.knownDirectComparisonDispositionsが空でない配列でない"
        )
    finding_ids: set[str] = set()
    for index, disposition in enumerate(known_dispositions):
        label = f"selectionRule.knownDirectComparisonDispositions[{index}]"
        if not isinstance(disposition, dict):
            raise FreezeBaselineError(f"{label}がobjectでない")
        _require_exact_keys(
            disposition,
            {
                "findingId",
                "sourcePath",
                "construct",
                "observedValue",
                "disposition",
                "selectionRuleRole",
                "reason",
            },
            label,
        )
        finding_id = _require_non_empty_string(
            disposition.get("findingId"), f"{label}.findingId"
        )
        if finding_id in finding_ids:
            raise FreezeBaselineError(f"既知比較のfindingIdが重複している: {finding_id}")
        finding_ids.add(finding_id)
        for key in (
            "sourcePath",
            "construct",
            "disposition",
            "selectionRuleRole",
            "reason",
        ):
            _require_non_empty_string(disposition.get(key), f"{label}.{key}")
        if disposition.get("selectionRuleRole") not in excluded_roles:
            raise FreezeBaselineError(f"{label}.selectionRuleRoleが宣言済み役割でない")
        if not isinstance(disposition.get("observedValue"), (int, str)) or isinstance(
            disposition.get("observedValue"), bool
        ):
            raise FreezeBaselineError(f"{label}.observedValueの型が不正")
    source_audit = scope.get("sourceLiteralAudit")
    if not isinstance(source_audit, dict) or not source_audit:
        raise FreezeBaselineError("scope.sourceLiteralAuditが空でないobjectでない")
    _require_exact_keys(
        source_audit,
        {
            "engineSourcePath",
            "forbiddenImplementationSetNames",
            "excludedComparisonFunctionsBySource",
            "permittedComparisonLiteralsBySource",
            "assuranceLevel",
            "coveredConstructs",
            "notCoveredConstructs",
            "occurrenceRoleValidation",
        },
        "scope.sourceLiteralAudit",
    )
    _require_non_empty_string(
        source_audit.get("assuranceLevel"), "sourceLiteralAudit.assuranceLevel"
    )
    _require_non_empty_string(
        source_audit.get("occurrenceRoleValidation"),
        "sourceLiteralAudit.occurrenceRoleValidation",
    )
    for key in ("coveredConstructs", "notCoveredConstructs"):
        constructs = source_audit.get(key)
        if (
            not isinstance(constructs, list)
            or not constructs
            or not all(isinstance(item, str) and item for item in constructs)
            or len(constructs) != len(set(constructs))
        ):
            raise FreezeBaselineError(f"sourceLiteralAudit.{key}が閉じた文字列配列でない")

    criteria = value.get("criteria")
    if not isinstance(criteria, dict):
        raise FreezeBaselineError("freezeBaseline.criteriaがobjectでない")
    if set(criteria) != set(criterion_order):
        raise FreezeBaselineError(
            "freezeBaseline.criteriaのchecker集合がexact-set不一致: "
            f"expected={sorted(criterion_order)!r}; actual={sorted(criteria)!r}"
        )
    for section_name in criterion_order:
        section = criteria.get(section_name)
        if not isinstance(section, dict) or not section:
            raise FreezeBaselineError(
                f"criteria.{section_name}は空でないobjectでなければならない"
            )

    history = value.get("history")
    if not isinstance(history, list) or not history:
        raise FreezeBaselineError("freezeBaseline.historyは空でない配列でなければならない")
    _validate_history_chain(history, series)
    expected_new = current_identities(value)
    last = history[-1]
    if last["newIdentity"] != {"present": True, "values": expected_new}:
        raise FreezeBaselineError(
            "最新受理記録のnewIdentityが現行基準の識別値と一致しない"
        )
    return value


def checker_criteria(
    declaration: Mapping[str, Any], checker_source_path: str | Path
) -> dict[str, Any]:
    """検証済み宣言のsourcePath対応から checker 単位の基準を返す。"""
    validated = validate_declaration(dict(declaration))
    normalized_source = Path(checker_source_path).as_posix()
    bindings = validated["scope"]["criterionBindings"]
    matches = [
        criterion_id
        for criterion_id, binding in bindings.items()
        if normalized_source.endswith(binding["sourcePath"])
    ]
    if len(matches) != 1:
        raise FreezeBaselineError(
            "checker sourcePathを凍結基準へ一意に対応づけられない: "
            f"{normalized_source}: {matches!r}"
        )
    section = validated["criteria"].get(matches[0])
    if not isinstance(section, dict):
        raise FreezeBaselineError(f"checker基準を取得できない: {matches[0]}")
    return section


def _validate_identity_state(value: object, label: str) -> None:
    """履歴の直前・直後識別値を検証する。"""
    if not isinstance(value, dict):
        raise FreezeBaselineError(f"{label}がobjectでない")
    _require_exact_keys(value, {"present", "values"}, label)
    present = value.get("present")
    values = value.get("values")
    if not isinstance(present, bool) or not isinstance(values, list):
        raise FreezeBaselineError(f"{label}の型が不正である")
    if not present and values:
        raise FreezeBaselineError(f"{label}は基準なしの場合valuesを空にする")
    if present and not values:
        raise FreezeBaselineError(f"{label}は基準ありの場合valuesを空にできない")
    seen: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise FreezeBaselineError(f"{label}.values[{index}]がobjectでない")
        _require_exact_keys(item, {"criterionId", "identity"}, f"{label}.values[{index}]")
        criterion_id = _require_non_empty_string(
            item.get("criterionId"), f"{label}.values[{index}].criterionId"
        )
        identity = _require_non_empty_string(
            item.get("identity"), f"{label}.values[{index}].identity"
        )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
            raise FreezeBaselineError(f"{label}の識別値がSHA-256形式でない")
        if criterion_id in seen:
            raise FreezeBaselineError(f"{label}でcriterionIdが重複している: {criterion_id}")
        seen.add(criterion_id)


def _validate_history_chain(history: Sequence[object], series: str) -> None:
    """履歴レコードの型と内部の片方向連鎖を検証する。"""
    previous_new: object | None = None
    acceptance_ids: set[str] = set()
    for index, record in enumerate(history):
        label = f"freezeBaseline.history[{index}]"
        if not isinstance(record, dict):
            raise FreezeBaselineError(f"{label}がobjectでない")
        _require_exact_keys(
            record,
            {
                "acceptanceId",
                "series",
                "priorIdentity",
                "newIdentity",
                "changes",
                "fact",
                "reason",
                "approvedBy",
                "approvedDate",
            },
            label,
        )
        acceptance_id = _require_non_empty_string(
            record.get("acceptanceId"), f"{label}.acceptanceId"
        )
        if ACCEPTANCE_ID_PATTERN.fullmatch(acceptance_id) is None:
            raise FreezeBaselineError(f"{label}.acceptanceIdの形式が不正である")
        if acceptance_id in acceptance_ids:
            raise FreezeBaselineError(f"acceptanceIdが重複している: {acceptance_id}")
        acceptance_ids.add(acceptance_id)
        if record.get("series") != series:
            raise FreezeBaselineError(f"{label}.seriesが宣言の系列名と一致しない")
        _validate_identity_state(record.get("priorIdentity"), f"{label}.priorIdentity")
        _validate_identity_state(record.get("newIdentity"), f"{label}.newIdentity")
        if previous_new is not None and record.get("priorIdentity") != previous_new:
            raise FreezeBaselineError(f"{label}のpriorIdentityが直前レコードと連鎖しない")
        previous_new = record.get("newIdentity")

        changes = record.get("changes")
        if not isinstance(changes, list) or not changes:
            raise FreezeBaselineError(f"{label}.changesを空にできない")
        changed_ids: set[str] = set()
        for change_index, change in enumerate(changes):
            change_label = f"{label}.changes[{change_index}]"
            if not isinstance(change, dict):
                raise FreezeBaselineError(f"{change_label}がobjectでない")
            _require_exact_keys(
                change,
                {"criterionId", "before", "after", "changedAspects"},
                change_label,
            )
            criterion_id = _require_non_empty_string(
                change.get("criterionId"), f"{change_label}.criterionId"
            )
            if criterion_id in changed_ids:
                raise FreezeBaselineError(
                    f"{label}.changesでcriterionIdが重複している: {criterion_id}"
                )
            changed_ids.add(criterion_id)
            for state_name in ("before", "after"):
                state = change.get(state_name)
                if not isinstance(state, dict) or set(state) not in (
                    {"present"},
                    {"present", "value"},
                ):
                    raise FreezeBaselineError(f"{change_label}.{state_name}の型が不正")
                if state.get("present") is False and set(state) != {"present"}:
                    raise FreezeBaselineError(
                        f"{change_label}.{state_name}は基準なしの場合valueを持てない"
                    )
                if state.get("present") is True and "value" not in state:
                    raise FreezeBaselineError(
                        f"{change_label}.{state_name}は基準ありの場合valueが必須"
                    )
            aspects = change.get("changedAspects")
            if not isinstance(aspects, list) or not aspects or not all(
                isinstance(item, str) and item for item in aspects
            ):
                raise FreezeBaselineError(f"{change_label}.changedAspectsが不正")
        for field in ("fact", "reason", "approvedBy", "approvedDate"):
            _require_non_empty_string(record.get(field), f"{label}.{field}")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["approvedDate"]) is None:
            raise FreezeBaselineError(f"{label}.approvedDateの形式が不正")


def _git(root: Path, arguments: Sequence[str]) -> str:
    """gitを実行し、失敗を基準未検証として拒否する。"""
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise FreezeBaselineError(f"gitを実行できない: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FreezeBaselineError(
            f"git {' '.join(arguments)}を実行できない: {detail}"
        )
    return result.stdout


def load_base_declaration(
    root: Path, descriptor_path: PurePosixPath, base_ref: str
) -> dict[str, Any] | None:
    """受理単位の比較元から直前の宣言を取得する。"""
    _git(root, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"])
    listed = _git(
        root,
        ["ls-tree", "-r", "--name-only", base_ref, "--", str(descriptor_path)],
    )
    paths = [line for line in listed.splitlines() if line]
    if not paths:
        return None
    if paths != [str(descriptor_path)]:
        raise FreezeBaselineError(
            f"比較元のdescriptor配置を一意に解決できない: {paths!r}"
        )
    raw = _git(root, ["show", f"{base_ref}:{descriptor_path}"])
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise FreezeBaselineError(
            f"比較元descriptorをJSONとして読めない: {error}"
        ) from error
    if not isinstance(document, dict) or FREEZE_FIELD not in document:
        raise FreezeBaselineError(
            "比較元descriptorは存在するが凍結基準宣言を取得できない"
        )
    return validate_declaration(document[FREEZE_FIELD])


def validate_append_only_transition(
    current: Mapping[str, Any], base: Mapping[str, Any] | None
) -> None:
    """比較元から現行への1受理分の追記だけを許す。"""
    current_value = validate_declaration(dict(current))
    current_history = current_value["history"]
    current_scope = current_value["scope"]
    current_criteria = current_value["criteria"]
    if base is None:
        base_history: list[object] = []
        base_scope: Mapping[str, Any] | None = None
        base_criteria: Mapping[str, Any] = {}
        expected_prior = {"present": False, "values": []}
    else:
        base_value = validate_declaration(dict(base))
        base_history = base_value["history"]
        base_scope = base_value["scope"]
        base_criteria = base_value["criteria"]
        expected_prior = {
            "present": True,
            "values": current_identities(base_value),
        }

    if current_history[: len(base_history)] != base_history:
        raise FreezeBaselineError(
            "既存の凍結基準受理履歴が書き換えまたは削除されている"
        )
    definition_id = current_scope["identityCriterionId"]
    changed_ids: list[str] = []
    if base_scope != current_scope:
        changed_ids.append(definition_id)
    current_order = _scope_criterion_order(current_scope)
    base_order = _scope_criterion_order(base_scope) if base_scope is not None else ()
    criterion_order = (*base_order, *(item for item in current_order if item not in base_order))
    changed_ids.extend(
        section
        for section in criterion_order
        if base_criteria.get(section) != current_criteria.get(section)
    )
    expected_added = 1 if changed_ids else 0
    if len(current_history) != len(base_history) + expected_added:
        raise FreezeBaselineError(
            "基準遷移1回につき受理記録はちょうど1件でなければならない"
        )
    if not changed_ids:
        return

    record = current_history[-1]
    if record["priorIdentity"] != expected_prior:
        raise FreezeBaselineError("追加レコードのpriorIdentityが直前基準と一致しない")
    expected_changes = []
    for section in changed_ids:
        if section == definition_id:
            before_value = base_scope
            after_value = current_scope
        else:
            before_value = base_criteria.get(section)
            after_value = current_criteria.get(section)
        before = (
            {"present": False}
            if before_value is None
            else {"present": True, "value": before_value}
        )
        after = (
            {"present": False}
            if after_value is None
            else {"present": True, "value": after_value}
        )
        expected_changes.append(
            {
                "criterionId": section,
                "before": before,
                "after": after,
                "changedAspects": [
                    "set",
                    "value",
                    "placement",
                    "frozen-target-correspondence",
                    "identity-granularity-and-interpretation",
                ],
            }
        )
    if record["changes"] != expected_changes:
        raise FreezeBaselineError(
            "受理記録のchangesが比較元から導出した変更前後と一致しない"
        )


def _parse_source(root: Path, relative_path: str) -> ast.Module:
    """宣言された検査器sourceを読み、ASTへ変換する。"""
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
        return ast.parse(text, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as error:
        raise FreezeBaselineError(
            f"凍結基準の実装対応sourceを解析できない: {relative_path}: {error}"
        ) from error


def _string_literals(tree: ast.AST) -> frozenset[str]:
    """ASTに現れる文字列literalを返す。"""
    return frozenset(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _comparison_string_literals(
    tree: ast.Module, excluded_functions: frozenset[str]
) -> frozenset[str]:
    """除外関数外の比較式に現れる文字列literal・参照定数を返す。"""
    values: set[str] = set()
    assigned_values: dict[str, set[str]] = {}

    def literal_strings(node: ast.AST) -> set[str]:
        return {
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        }

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            assigned = literal_strings(node.value) if node.value is not None else set()
            for target in targets:
                if isinstance(target, ast.Name) and assigned:
                    assigned_values.setdefault(target.id, set()).update(assigned)

    class Visitor(ast.NodeVisitor):
        """関数名を追跡して比較式だけを収集する。"""

        def __init__(self) -> None:
            self.function_stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.function_stack.append(node.name)
            self.generic_visit(node)
            self.function_stack.pop()

        def visit_Compare(self, node: ast.Compare) -> None:
            current = self.function_stack[-1] if self.function_stack else ""
            if current not in excluded_functions:
                values.update(literal_strings(node))
                for child in ast.walk(node):
                    if isinstance(child, ast.Name):
                        values.update(assigned_values.get(child.id, set()))
            self.generic_visit(node)

    Visitor().visit(tree)
    return frozenset(values)


def validate_implementation_correspondence(
    root: Path, declaration: Mapping[str, Any]
) -> None:
    """宣言したsourceの直接文字列比較を補助的・非網羅に監査する。"""
    validated = validate_declaration(dict(declaration))
    scope = validated["scope"]
    audit = scope["sourceLiteralAudit"]
    engine_path = _require_non_empty_string(
        audit.get("engineSourcePath"), "sourceLiteralAudit.engineSourcePath"
    )
    forbidden_names_value = audit.get("forbiddenImplementationSetNames")
    exclusions_value = audit.get("excludedComparisonFunctionsBySource")
    permitted_value = audit.get("permittedComparisonLiteralsBySource")
    if (
        not isinstance(forbidden_names_value, list)
        or not forbidden_names_value
        or not all(isinstance(item, str) and item for item in forbidden_names_value)
        or not isinstance(exclusions_value, dict)
        or not isinstance(permitted_value, dict)
    ):
        raise FreezeBaselineError("sourceLiteralAuditの型が不正")

    bindings = scope["criterionBindings"]
    criterion_ids = frozenset(bindings)
    source_to_criterion = {
        binding["sourcePath"]: criterion_id
        for criterion_id, binding in bindings.items()
    }
    audited_sources = {engine_path, *source_to_criterion}
    if set(exclusions_value) != audited_sources or set(permitted_value) != audited_sources:
        raise FreezeBaselineError(
            "sourceLiteralAuditのsource集合がengineとcriterionBindingsのexact-setでない"
        )
    permitted_roles = scope["selectionRule"].get("excludedOperandRoles")
    if not isinstance(permitted_roles, list) or not all(
        isinstance(item, str) and item for item in permitted_roles
    ):
        raise FreezeBaselineError("selectionRule.excludedOperandRolesの型が不正")

    for source_path in sorted(audited_sources):
        tree = _parse_source(root, source_path)
        engine_names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        forbidden_names = sorted(set(forbidden_names_value) & engine_names)
        if forbidden_names:
            raise FreezeBaselineError(
                f"凍結基準集合を実装側へ再定義している: "
                f"{source_path}: {forbidden_names!r}"
            )
        duplicated_ids = sorted(criterion_ids & _string_literals(tree))
        if duplicated_ids:
            raise FreezeBaselineError(
                f"criterion IDを検査器sourceへ直書きしている: "
                f"{source_path}: {duplicated_ids!r}"
            )
        excluded_value = exclusions_value.get(source_path, [])
        if not isinstance(excluded_value, list) or not all(
            isinstance(item, str) and item for item in excluded_value
        ):
            raise FreezeBaselineError(
                f"比較literal除外関数の宣言が不正: {source_path}"
            )
        function_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        missing_excluded_functions = sorted(set(excluded_value) - function_names)
        if missing_excluded_functions:
            raise FreezeBaselineError(
                "比較literal除外関数がsourceに実在しない: "
                f"{source_path}: {missing_excluded_functions!r}"
            )
        role_map = permitted_value.get(source_path)
        if not isinstance(role_map, dict) or not all(
            isinstance(role, str)
            and role in permitted_roles
            and isinstance(items, list)
            and all(isinstance(item, str) for item in items)
            for role, items in role_map.items()
        ):
            raise FreezeBaselineError(
                f"許可された比較literalの役割宣言が不正: {source_path}"
            )
        declared_literals = {
            item for items in role_map.values() for item in items
        }
        declared_literal_count = sum(len(items) for items in role_map.values())
        if declared_literal_count != len(declared_literals):
            raise FreezeBaselineError(
                f"許可された比較literalが複数の役割へ重複している: {source_path}"
            )
        actual_literals = _comparison_string_literals(
            tree, frozenset(excluded_value)
        )
        if actual_literals != declared_literals:
            raise FreezeBaselineError(
                "比較literalが資産側の線引き宣言とexact-set不一致: "
                f"{source_path}: "
                f"missing={sorted(declared_literals - actual_literals)!r}; "
                f"unexpected={sorted(actual_literals - declared_literals)!r}"
            )


def validate_repository_history(
    root: Path,
    descriptor_path: PurePosixPath,
    declaration: Mapping[str, Any],
) -> None:
    """宣言したPR比較元と実リポジトリから追記専用遷移を検査する。"""
    current = validate_declaration(dict(declaration))
    validate_implementation_correspondence(root, current)
    base_ref = current["acceptance"]["baseRef"]
    base_commit = current["acceptance"]["baseCommit"]
    resolved = _git(root, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"])
    if resolved.strip() != base_commit:
        raise FreezeBaselineError(
            "受理記録のbaseCommitがbaseRefの実測値と一致しない: "
            f"{base_commit} != {resolved.strip()}"
        )
    base = load_base_declaration(root, descriptor_path, base_commit)
    validate_append_only_transition(current, base)
