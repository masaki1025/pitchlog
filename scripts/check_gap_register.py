"""定義の穴9件を追跡するgap registerの骨格と状態述語を検証する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from scripts import check_input_axes_descriptor as clause_id_source
    from scripts import check_input_axes_three_way_parity as parity_checker
    from scripts import state_transition_freeze as freeze_checker
except ModuleNotFoundError:  # pragma: no cover - scriptを直接実行する経路
    import check_input_axes_descriptor as clause_id_source  # type: ignore[no-redef]
    import check_input_axes_three_way_parity as parity_checker  # type: ignore[no-redef]
    import state_transition_freeze as freeze_checker  # type: ignore[no-redef]

REGISTER_PATH = PurePosixPath(
    "contracts/state-transition/gap_register_v1.json"
)
SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/gap_register_schema_v1.json"
)
CLAUSE_BRANCH_REGISTER_PATH = PurePosixPath(
    "contracts/state-transition/clause_branch_register_v1.json"
)
CLAUSE_BRANCH_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/clause_branch_register_schema_v1.json"
)
ROW_RULES_PATH = PurePosixPath(
    "contracts/state-transition/required_set_row_rules_v1.json"
)
MANUAL_FIXTURE_PATHS = (
    PurePosixPath("contracts/state-transition/state_transition_manual_fixtures_v1.json"),
    PurePosixPath("contracts/state-transition/game_end_manual_fixtures_v1.json"),
)
REQUIREMENTS_PATH = parity_checker.REQUIREMENTS_PATH

# JSON Schema の語彙・member 名は凍結する判断値ではなく、汎用文法のnavigationに使う。
I_REQUIRED = "required"
I_PROPERTIES = "properties"
I_ITEMS = "items"
I_STATE = "state"
I_ENUM = "enum"
I_SCHEMA_VERSION = "schemaVersion"
I_VERSION = "version"
I_CONST = "const"
I_ADDITIONAL_PROPERTIES = "additionalProperties"
I_GAPS = "gaps"
I_PREDICATE_POLICY = "x-pitchlog-gap-register-predicates"
I_CRITERIA_SOURCE = "criteriaSource"
I_EXISTENCE_ONLY_STAGES = "existenceOnlyStages"
I_BIDIRECTIONAL_STAGES = "bidirectionalStages"
I_RESOLVED_ADDITIONAL_BIDIRECTIONAL_STAGES = (
    "resolvedAdditionalBidirectionalStages"
)
L_SCHEMA_REQUIRED = "schema.required"
L_SCHEMA_PROPERTIES = "schema.properties"
L_SCHEMA_GAPS = "schema.properties.gaps"
L_SCHEMA_GAP = "schema gaps.items"
L_SCHEMA_GAP_REQUIRED = "schema gaps.items.required"
L_SCHEMA_GAP_PROPERTIES = "schema gaps.items.properties"
L_SCHEMA_STATE = "schema gaps.items.properties.state"
L_SCHEMA_STATE_ENUM = "schema state.enum"
L_SCHEMA_VERSION = "schema properties.schemaVersion"
L_SCHEMA_DOCUMENT_VERSION = "schema properties.version"
L_SCHEMA_POLICY = "schemaの状態別述語宣言"
L_SCHEMA_EXISTENCE_STAGES = "schema predicate.existenceOnlyStages"
L_SCHEMA_BIDIRECTIONAL_STAGES = "schema predicate.bidirectionalStages"
L_SCHEMA_RESOLVED_ADDITIONAL_STAGES = (
    "schema predicate.resolvedAdditionalBidirectionalStages"
)
L_SCHEMA_ASSET = "gap register schema"


class GapRegisterError(Exception):
    """gap registerの構造・参照・状態遷移が不正な場合を表す。"""


@dataclass(frozen=True)
class GapCriteria:
    """資産側宣言から読み込んだgap register検査の凍結基準。"""

    top_level_fields: frozenset[str]
    gap_fields: frozenset[str]
    gap_ids: frozenset[str]
    list_stage_fields: tuple[str, ...]
    stage_fields: tuple[str, ...]
    states: frozenset[str]
    initial_state: str
    terminal_state: str
    schema_version: int
    row_layers: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class GapPredicatePolicy:
    """schema資産が宣言する段ごとの参照検査方式。"""

    existence_only_stages: frozenset[str]
    bidirectional_stages: frozenset[str]
    resolved_additional_bidirectional_stages: frozenset[str]
    clause_gap_ownership: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class StageReferenceIndex:
    """所有資産から得た参照の実在集合とgapへの逆方向帰属。"""

    existing_references: frozenset[str]
    gap_ids_by_reference: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class ClauseBranchPolicy:
    """schema資産が宣言する条文分岐台帳の抽出・分類規則。"""

    requirements_source_path: PurePosixPath
    requirement_branch_kind: str
    game_end_outcome_kind: str
    game_end_outcome_roles: tuple[str, ...]
    source_clause_namespace: str
    intentional_unassigned_branch_ids: frozenset[str]
    intentional_unassigned_reason: str
    top_level_fields: frozenset[str]
    branch_fields: frozenset[str]
    coverage_kinds: frozenset[str]
    schema_version: int
    requirements_version: str
    requirements_status: str
    author_statement: str


def _criteria_string_list(value: object, label: str) -> list[str]:
    """凍結基準の重複のない文字列配列を返す。"""
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise GapRegisterError(f"凍結基準{label}が空でない文字列配列でない")
    if len(value) != len(set(value)):
        raise GapRegisterError(f"凍結基準{label}に重複がある")
    return value


def load_gap_criteria(descriptor: Mapping[str, Any]) -> GapCriteria:
    """descriptor内の資産側宣言からgap register基準を読み込む。"""
    try:
        declaration = freeze_checker.validate_declaration(
            descriptor.get(freeze_checker.FREEZE_FIELD)
        )
        raw = freeze_checker.checker_criteria(declaration, __file__)
    except freeze_checker.FreezeBaselineError as error:
        raise GapRegisterError(f"凍結基準宣言を検証できない: {error}") from error
    top_level = _criteria_string_list(raw.get("topLevelFields"), ".topLevelFields")
    gap_fields = _criteria_string_list(raw.get("gapFields"), ".gapFields")
    gap_ids = _criteria_string_list(raw.get("gapIds"), ".gapIds")
    list_stages = _criteria_string_list(
        raw.get("listStageFields"), ".listStageFields"
    )
    stages = _criteria_string_list(raw.get("stageFields"), ".stageFields")
    states = _criteria_string_list(raw.get("states"), ".states")
    row_layers = raw.get("rowLayers")
    if not isinstance(row_layers, list) or len(row_layers) != 4:
        raise GapRegisterError("rowLayersは規範行4層の宣言でなければならない")
    seen_layers: set[str] = set()
    for layer in row_layers:
        if not isinstance(layer, dict) or set(layer) != {
            "layer", "sourcePath", "keyPaths", "ownershipPath"
        }:
            raise GapRegisterError("rowLayersの宣言が不正")
        if not all(isinstance(layer[key], str) and layer[key] for key in (
            "layer", "sourcePath", "ownershipPath"
        )):
            raise GapRegisterError("rowLayersの文字列宣言が不正")
        _criteria_string_list(layer["keyPaths"], "rowLayers.keyPaths")
        if layer["layer"] in seen_layers:
            raise GapRegisterError("rowLayersの層が重複している")
        seen_layers.add(layer["layer"])
    initial_state = raw.get("initialState")
    terminal_state = raw.get("terminalState")
    expected_values = raw.get("checkerExpectedValues")
    if (
        not isinstance(initial_state, str)
        or initial_state not in states
        or not isinstance(terminal_state, str)
        or terminal_state not in states
        or initial_state == terminal_state
    ):
        raise GapRegisterError("初期・終端stateの凍結基準が不正")
    if stages[:-1] != list_stages:
        raise GapRegisterError("stageFieldsがlistStageFieldsの連続prefixでない")
    if (
        not isinstance(expected_values, dict)
        or not isinstance(expected_values.get("schemaVersion"), int)
        or isinstance(expected_values["schemaVersion"], bool)
    ):
        raise GapRegisterError("checkerExpectedValues.schemaVersionが整数でない")
    return GapCriteria(
        top_level_fields=frozenset(top_level),
        gap_fields=frozenset(gap_fields),
        gap_ids=frozenset(gap_ids),
        list_stage_fields=tuple(list_stages),
        stage_fields=tuple(stages),
        states=frozenset(states),
        initial_state=initial_state,
        terminal_state=terminal_state,
        schema_version=expected_values["schemaVersion"],
        row_layers=tuple(row_layers),
    )


def load_gap_schema_policy(
    schema: Mapping[str, Any], criteria: GapCriteria
) -> GapPredicatePolicy:
    """JSON Schemaと状態述語宣言のcriteriaとの整合を検証して返す。"""
    required = _criteria_string_list(schema.get(I_REQUIRED), L_SCHEMA_REQUIRED)
    properties = _expect_object(schema.get(I_PROPERTIES), L_SCHEMA_PROPERTIES)
    gaps_schema = _expect_object(properties.get(I_GAPS), L_SCHEMA_GAPS)
    gap_schema = _expect_object(gaps_schema.get(I_ITEMS), L_SCHEMA_GAP)
    gap_required = _criteria_string_list(
        gap_schema.get(I_REQUIRED), L_SCHEMA_GAP_REQUIRED
    )
    gap_properties = _expect_object(
        gap_schema.get(I_PROPERTIES), L_SCHEMA_GAP_PROPERTIES
    )
    state_schema = _expect_object(
        gap_properties.get(I_STATE), L_SCHEMA_STATE
    )
    states = _criteria_string_list(state_schema.get(I_ENUM), L_SCHEMA_STATE_ENUM)
    schema_version = _expect_object(
        properties.get(I_SCHEMA_VERSION), L_SCHEMA_VERSION
    ).get(I_CONST)
    version = _expect_object(
        properties.get(I_VERSION), L_SCHEMA_DOCUMENT_VERSION
    ).get(I_CONST)
    top_additional_properties = schema.get(I_ADDITIONAL_PROPERTIES)
    gap_additional_properties = gap_schema.get(I_ADDITIONAL_PROPERTIES)
    if frozenset(required) != criteria.top_level_fields:
        raise GapRegisterError("schemaのトップレベルrequiredが凍結基準と一致しない")
    if frozenset(properties) != criteria.top_level_fields:
        raise GapRegisterError("schemaのトップレベルpropertiesが凍結基準と一致しない")
    if top_additional_properties is not False:
        raise GapRegisterError("schemaのトップレベルは未知フィールドを許している")
    if frozenset(gap_required) != criteria.gap_fields:
        raise GapRegisterError("schemaのgap requiredが凍結基準と一致しない")
    if frozenset(gap_properties) != criteria.gap_fields:
        raise GapRegisterError("schemaのgap propertiesが凍結基準と一致しない")
    if gap_additional_properties is not False:
        raise GapRegisterError("schemaのgap entryは未知フィールドを許している")
    if frozenset(states) != criteria.states:
        raise GapRegisterError("schemaのstate enumが凍結基準と一致しない")
    if schema_version != criteria.schema_version or version != REGISTER_PATH.stem:
        raise GapRegisterError("schemaの版がgap registerの凍結基準と一致しない")

    policy = _expect_object(
        schema.get(I_PREDICATE_POLICY),
        L_SCHEMA_POLICY,
    )
    criteria_source = policy.get(I_CRITERIA_SOURCE)
    if not isinstance(criteria_source, str) or not criteria_source:
        raise GapRegisterError("schemaの状態別述語宣言にcriteriaSourceがない")
    existence_only = _criteria_string_list(
        policy.get(I_EXISTENCE_ONLY_STAGES),
        L_SCHEMA_EXISTENCE_STAGES,
    )
    bidirectional = _criteria_string_list(
        policy.get(I_BIDIRECTIONAL_STAGES),
        L_SCHEMA_BIDIRECTIONAL_STAGES,
    )
    resolved_additional = _criteria_string_list(
        policy.get(I_RESOLVED_ADDITIONAL_BIDIRECTIONAL_STAGES),
        L_SCHEMA_RESOLVED_ADDITIONAL_STAGES,
    )
    existence_set = frozenset(existence_only)
    bidirectional_set = frozenset(bidirectional)
    resolved_additional_set = frozenset(resolved_additional)
    if existence_set & bidirectional_set:
        raise GapRegisterError("参照検査方式が複数の段へ重複している")
    if existence_set | bidirectional_set != frozenset(criteria.stage_fields):
        raise GapRegisterError("参照検査方式が5段のexact-setを覆っていない")
    if not resolved_additional_set <= existence_set:
        raise GapRegisterError("resolvedで追加する双方向段がopenの実在検査段でない")
    if bidirectional_set | resolved_additional_set != frozenset(
        criteria.stage_fields
    ):
        raise GapRegisterError("resolvedの双方向検査が5段のexact-setを覆っていない")
    raw_ownership = _expect_object(policy.get("clauseGapOwnership"), "clauseGapOwnership")
    clause_gap_ownership: dict[str, frozenset[str]] = {}
    for clause_id, raw_gap_ids in raw_ownership.items():
        owned_gap_ids = _criteria_string_list(
            raw_gap_ids, f"clauseGapOwnership.{clause_id}"
        )
        if not _is_subset(frozenset(owned_gap_ids), criteria.gap_ids):
            raise GapRegisterError(f"{clause_id}: 未知のGAPへの条文帰属がある")
        clause_gap_ownership[clause_id] = frozenset(owned_gap_ids)
    return GapPredicatePolicy(
        existence_only_stages=existence_set,
        bidirectional_stages=bidirectional_set,
        resolved_additional_bidirectional_stages=resolved_additional_set,
        clause_gap_ownership=clause_gap_ownership,
    )


def _expect_object(value: object, label: str) -> dict[str, Any]:
    """JSON objectを検証して返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GapRegisterError(f"{label}は文字列キーのobjectでなければならない")
    return value


def _values_equal(left: object, right: object) -> bool:
    """比較値を呼出側のliteral監査へ混ぜずに同値比較する。"""
    return left == right


def _value_in(
    value: object, candidates: set[Any] | frozenset[Any]
) -> bool:
    """比較値を呼出側のliteral監査へ混ぜずに包含判定する。"""
    return value in candidates


def _is_subset(values: frozenset[Any], container: frozenset[Any]) -> bool:
    """比較値を呼出側のliteral監査へ混ぜずに部分集合を判定する。"""
    return values <= container


def _source_clause_exists(
    source_id: str, prefix: str, clause_ids: frozenset[str]
) -> bool:
    """名前空間付き由来条文IDが要件書の抽出集合にあるか判定する。"""
    return source_id.startswith(prefix) and source_id.removeprefix(prefix) in clause_ids


def load_clause_branch_schema_policy(
    schema: Mapping[str, Any],
) -> ClauseBranchPolicy:
    """条文分岐台帳schemaと抽出方針を検証して返す。"""
    policy = _expect_object(
        schema.get("x-pitchlog-clause-branch-register-policy"),
        "clause branch register policy",
    )
    expected_policy_fields = {
        "requirementsSourcePath",
        "requirementBranchExtraction",
        "requirementBranchKind",
        "gameEndOutcomeKind",
        "gameEndOutcomeRoles",
        "sourceClauseNamespace",
        "gapOwnership",
        "intentionalUnassignedBranchIds",
        "intentionalUnassignedReason",
        "assuranceBoundary",
    }
    if not _values_equal(set(policy), expected_policy_fields):
        raise GapRegisterError("clause branch register policyがexact-set不一致")
    source_path = policy.get("requirementsSourcePath")
    extraction = policy.get("requirementBranchExtraction")
    requirement_kind = policy.get("requirementBranchKind")
    outcome_kind = policy.get("gameEndOutcomeKind")
    namespace = policy.get("sourceClauseNamespace")
    roles = _criteria_string_list(
        policy.get("gameEndOutcomeRoles"), "gameEndOutcomeRoles"
    )
    intentional_unassigned = _criteria_string_list(
        policy.get("intentionalUnassignedBranchIds"),
        "intentionalUnassignedBranchIds",
    )
    intentional_unassigned_reason = policy.get("intentionalUnassignedReason")
    if (
        not isinstance(source_path, str)
        or not source_path
        or not isinstance(extraction, str)
        or not extraction
        or not isinstance(requirement_kind, str)
        or not requirement_kind
        or not isinstance(outcome_kind, str)
        or not outcome_kind
        or not isinstance(namespace, str)
        or not namespace
        or not isinstance(policy.get("gapOwnership"), str)
        or not policy["gapOwnership"]
        or not isinstance(intentional_unassigned_reason, str)
        or not intentional_unassigned_reason
    ):
        raise GapRegisterError("clause branch register policyの文字列宣言が不正")
    if not _values_equal(PurePosixPath(source_path), REQUIREMENTS_PATH):
        raise GapRegisterError("分岐抽出元が承認済み要件書のpathと一致しない")
    if not _values_equal(
        extraction, "normative-table-first-cell-machine-readable-id"
    ):
        raise GapRegisterError("未対応の要件分岐抽出規則である")
    assurance = _expect_object(
        policy.get("assuranceBoundary"), "clause branch assuranceBoundary"
    )
    if not _values_equal(
        set(assurance), {"mechanicallyGuaranteed", "humanControls"}
    ):
        raise GapRegisterError("分岐台帳の保証境界がexact-set不一致")
    _criteria_string_list(
        assurance.get("mechanicallyGuaranteed"),
        "assuranceBoundary.mechanicallyGuaranteed",
    )
    _criteria_string_list(
        assurance.get("humanControls"), "assuranceBoundary.humanControls"
    )

    branch_document_required = _criteria_string_list(
        schema.get(I_REQUIRED), "branch schema.required"
    )
    branch_document_properties = _expect_object(
        schema.get(I_PROPERTIES), "branch schema.properties"
    )
    if not _values_equal(
        frozenset(branch_document_required), frozenset(branch_document_properties)
    ):
        raise GapRegisterError("分岐台帳schemaのrequiredとpropertiesが一致しない")
    if not _values_equal(schema.get(I_ADDITIONAL_PROPERTIES), False):
        raise GapRegisterError("分岐台帳schemaが未知のトップレベルfieldを許している")
    clause_branch_schema_version = _expect_object(
        branch_document_properties.get(I_SCHEMA_VERSION),
        "branch schema.schemaVersion",
    ).get(I_CONST)
    clause_branch_version = _expect_object(
        branch_document_properties.get(I_VERSION), "branch schema.version"
    ).get(I_CONST)
    if (
        not isinstance(clause_branch_schema_version, int)
        or isinstance(clause_branch_schema_version, bool)
        or not _values_equal(clause_branch_schema_version, 1)
        or not _values_equal(
            clause_branch_version, CLAUSE_BRANCH_REGISTER_PATH.stem
        )
    ):
        raise GapRegisterError("分岐台帳schemaの版が配置・命名と一致しない")
    source_schema = _expect_object(
        branch_document_properties.get("requirementsSource"),
        "branch schema.requirementsSource",
    )
    source_required = _criteria_string_list(
        source_schema.get(I_REQUIRED), "requirementsSource.required"
    )
    source_properties = _expect_object(
        source_schema.get(I_PROPERTIES), "requirementsSource.properties"
    )
    if (
        not _values_equal(frozenset(source_required), frozenset(source_properties))
        or not _values_equal(source_schema.get(I_ADDITIONAL_PROPERTIES), False)
    ):
        raise GapRegisterError("requirementsSourceのschemaが閉じていない")
    requirements_version = _expect_object(
        source_properties.get("version"), "requirementsSource.version"
    ).get(I_CONST)
    requirements_status = _expect_object(
        source_properties.get("status"), "requirementsSource.status"
    ).get(I_CONST)
    declared_source_path = _expect_object(
        source_properties.get("path"), "requirementsSource.path"
    ).get(I_CONST)
    if (
        not _values_equal(declared_source_path, source_path)
        or not isinstance(requirements_version, str)
        or not requirements_version
        or not isinstance(requirements_status, str)
        or not requirements_status
    ):
        raise GapRegisterError("requirementsSourceの宣言が方針と一致しない")
    author_schema = _expect_object(
        branch_document_properties.get("authorSignature"),
        "branch schema.authorSignature",
    )
    author_required = _criteria_string_list(
        author_schema.get(I_REQUIRED), "authorSignature.required"
    )
    author_properties = _expect_object(
        author_schema.get(I_PROPERTIES), "authorSignature.properties"
    )
    if (
        not _values_equal(frozenset(author_required), frozenset(author_properties))
        or not _values_equal(author_schema.get(I_ADDITIONAL_PROPERTIES), False)
    ):
        raise GapRegisterError("authorSignatureのschemaが閉じていない")
    author_statement = _expect_object(
        author_properties.get("statement"), "authorSignature.statement"
    ).get(I_CONST)
    if not isinstance(author_statement, str) or not author_statement:
        raise GapRegisterError("authorSignature.statementの宣言が不正")
    outcome_schema = _expect_object(
        branch_document_properties.get("gameEndOutcomeBranches"),
        "branch schema.gameEndOutcomeBranches",
    )
    outcome_required = _criteria_string_list(
        outcome_schema.get(I_REQUIRED), "gameEndOutcomeBranches.required"
    )
    outcome_properties = _expect_object(
        outcome_schema.get(I_PROPERTIES), "gameEndOutcomeBranches.properties"
    )
    if (
        not _values_equal(tuple(outcome_required), tuple(roles))
        or not _values_equal(set(outcome_properties), set(roles))
        or not _values_equal(outcome_schema.get(I_ADDITIONAL_PROPERTIES), False)
    ):
        raise GapRegisterError("終了判定4役割とschemaのfieldが一致しない")
    branches_schema = _expect_object(
        branch_document_properties.get("branches"), "branch schema.branches"
    )
    branch_ref = _expect_object(
        branches_schema.get(I_ITEMS), "branch schema.branches.items"
    ).get("$ref")
    definitions = _expect_object(schema.get("$defs"), "branch schema.$defs")
    branch_schema = _expect_object(definitions.get("branch"), "branch schema.$defs.branch")
    branch_required = _criteria_string_list(
        branch_schema.get(I_REQUIRED), "branch schema.$defs.branch.required"
    )
    branch_properties = _expect_object(
        branch_schema.get(I_PROPERTIES), "branch schema.$defs.branch.properties"
    )
    if (
        not _values_equal(branch_ref, "#/$defs/branch")
        or not _values_equal(
            frozenset(branch_required), frozenset(branch_properties)
        )
        or not _values_equal(branch_schema.get(I_ADDITIONAL_PROPERTIES), False)
    ):
        raise GapRegisterError("分岐entryのschemaが閉じていない")
    branch_kind_schema = _expect_object(
        branch_properties.get("branchKind"), "branch schema.branchKind"
    )
    branch_kinds = frozenset(
        _criteria_string_list(branch_kind_schema.get(I_ENUM), "branchKind.enum")
    )
    if not _values_equal(branch_kinds, {requirement_kind, outcome_kind}):
        raise GapRegisterError("branchKindが方針宣言と一致しない")
    coverage_schema = _expect_object(
        branch_properties.get("coverageKind"), "branch schema.coverageKind"
    )
    coverage_kinds = frozenset(
        _criteria_string_list(coverage_schema.get(I_ENUM), "coverageKind.enum")
    )
    return ClauseBranchPolicy(
        requirements_source_path=PurePosixPath(source_path),
        requirement_branch_kind=requirement_kind,
        game_end_outcome_kind=outcome_kind,
        game_end_outcome_roles=tuple(roles),
        source_clause_namespace=namespace,
        intentional_unassigned_branch_ids=frozenset(intentional_unassigned),
        intentional_unassigned_reason=intentional_unassigned_reason,
        top_level_fields=frozenset(branch_document_properties),
        branch_fields=frozenset(branch_properties),
        coverage_kinds=coverage_kinds,
        schema_version=clause_branch_schema_version,
        requirements_version=requirements_version,
        requirements_status=requirements_status,
        author_statement=author_statement,
    )


def _validate_string_id_list(value: object, label: str) -> list[str]:
    """重複のない文字列ID配列を検証して返す。"""
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise GapRegisterError(f"{label}は空文字を含まない文字列ID配列でなければならない")
    if len(value) != len(set(value)):
        raise GapRegisterError(f"{label}に重複IDがある")
    return value


def _selector_is_filled(value: object) -> bool:
    """生成case selectorが充填済みかを判定する。"""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, (list, dict)):
        return bool(value)
    raise GapRegisterError(
        "generatedCaseSelectorはnullまたは空でない文字列・配列・objectでなければならない"
    )


def _filled_stage_flags(
    gap: Mapping[str, Any], criteria: GapCriteria
) -> tuple[bool, ...]:
    """5段を先頭から順に充填済み真偽へ変換する。"""
    list_flags = tuple(bool(gap[field]) for field in criteria.list_stage_fields)
    return (*list_flags, _selector_is_filled(gap[criteria.stage_fields[-1]]))


def canonical_reference_token(value: object) -> str:
    """構造を持つ参照を決定的なJSON tokenへ正規化する。"""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise GapRegisterError(f"参照を決定的に正規化できない: {error}") from error


def generated_case_selector(
    source_path: str, gap_id: str, case_count: int
) -> dict[str, str | int]:
    """規範行の逆方向帰属で生成caseを選ぶ述語を作る。"""
    return {
        "sourcePath": source_path,
        "rowOwnerGapId": gap_id,
        "caseCount": case_count,
    }


def clause_reference_index(policy: GapPredicatePolicy) -> StageReferenceIndex:
    """schema側の独立した条文帰属宣言を逆方向indexへ変換する。"""
    return StageReferenceIndex(
        frozenset(policy.clause_gap_ownership), policy.clause_gap_ownership
    )


def _row_key_value(row: Mapping[str, Any], key_path: str) -> str:
    """規範行の自然キーを宣言済みのpathから取得する。"""
    value: Any = row
    for part in key_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise GapRegisterError(f"規範行に自然キーがない: {key_path}")
        value = value[part]
    if isinstance(value, str) and value and ":" not in value:
        return value
    if isinstance(value, (bool, int)):
        return json.dumps(value)
    raise GapRegisterError(f"規範行の自然キーがIDに使えない: {key_path}")


def _normative_row_id(layer: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    """宣言済みの層名と自然キーから行IDを組み立てる。"""
    return ":".join((layer["layer"], *(
        _row_key_value(row, path) for path in layer["keyPaths"]
    )))


def _mentions_id(remarks: str, identifier: str) -> bool:
    """備考内の完全な識別子だけを帰属の証拠にする。"""
    return re.search(
        rf"(?<![A-Za-z0-9-]){re.escape(identifier)}(?![A-Za-z0-9-])",
        remarks,
    ) is not None


def row_reference_index(
    criteria: GapCriteria,
    gaps: Sequence[Mapping[str, Any]],
    documents: Mapping[str, Mapping[str, Any]],
) -> StageReferenceIndex:
    """規範行4層の自然キーと明記されたGAP・分岐から逆方向帰属を作る。"""
    existing: set[str] = set()
    owners_by_reference: dict[str, frozenset[str]] = {}
    for layer in criteria.row_layers:
        document = documents.get(layer["sourcePath"])
        rows = document.get(layer["layer"]) if document is not None else None
        if not isinstance(rows, list):
            raise GapRegisterError(f"規範行層が実在しない: {layer['layer']}")
        for row in rows:
            if not isinstance(row, dict):
                raise GapRegisterError(f"規範行がobjectでない: {layer['layer']}")
            row_id = _normative_row_id(layer, row)
            if row_id in existing:
                raise GapRegisterError(f"規範行の自然キーが重複している: {row_id}")
            existing.add(row_id)
            evidence = row.get(layer["ownershipPath"])
            if not isinstance(evidence, str):
                raise GapRegisterError(f"規範行の帰属根拠が文字列でない: {row_id}")
            source_clauses = row.get("sourceClauseIds")
            owners: set[str] = set()
            for gap in gaps:
                if source_clauses is not None and not any(
                    f"req:{clause}" in source_clauses
                    for clause in gap["clauseIds"]
                ):
                    continue
                if _mentions_id(evidence, gap["gapId"]) or any(
                    _mentions_id(evidence, branch_id)
                    for branch_id in gap["branchIds"]
                ):
                    owners.add(gap["gapId"])
            owners_by_reference[row_id] = frozenset(owners)
    return StageReferenceIndex(frozenset(existing), owners_by_reference)


def orphan_normative_row_ids(
    criteria: GapCriteria,
    documents: Mapping[str, Mapping[str, Any]],
    branch_register: Mapping[str, Any],
    requirement_clause_ids: frozenset[str],
    row_rules: Mapping[str, Any],
) -> list[str]:
    """規範行から実在する分岐または典拠条文へ辿れない行IDを返す。

    Args:
        criteria: 規範行4層と自然キーの宣言。
        documents: 規範行を含む契約資産。
        branch_register: 分岐台帳。
        requirement_clause_ids: 要件書から抽出した条文ID。
        row_rules: matrix行の語彙軸・語彙IDと典拠条文の対応宣言。

    Returns:
        帰属先を持たない行ID。
    """
    branches = {branch["branchId"]: branch for branch in branch_register["branches"]}
    branch_clauses = {
        clause for branch in branches.values() for clause in branch["sourceClauseIds"]
    }
    valid_branch_clauses = branch_clauses & {
        f"req:{clause}" for clause in requirement_clause_ids
    }
    assignments = {
        assignment["axisId"]: assignment
        for assignment in row_rules["axisAssignments"]
        if _values_equal(assignment["role"], "result-id-source")
    }
    partitions_by_result: dict[str, list[Mapping[str, Any]]] = {}
    for partition in row_rules["partitionRules"]:
        for result_id in partition["vocabularyIds"]:
            partitions_by_result.setdefault(result_id, []).append(partition)
    orphans: list[str] = []
    for layer in criteria.row_layers:
        for row in documents[layer["sourcePath"]][layer["layer"]]:
            row_id = _normative_row_id(layer, row)
            linked = False
            if _values_equal(layer["layer"], "matrixRows"):
                axis_id = row["resultId"].partition(".")[0]
                assignment = assignments.get(axis_id)
                partitions = partitions_by_result.get(row["resultId"], [])
                linked = bool(
                    assignment
                    and _values_equal(assignment.get("eventKind"), row["eventKind"])
                    and set(assignment["sourceClauseIds"]) & valid_branch_clauses
                    and _values_equal(len(partitions), 1)
                    and set(partitions[0]["sourceClauseIds"]) & valid_branch_clauses
                )
            elif _values_equal(layer["layer"], "operationRows"):
                linked = _value_in(row.get("clauseId"), requirement_clause_ids)
            elif _values_equal(layer["layer"], "undoRows"):
                provenance_text = row.get("remarks", "")
                linked = isinstance(provenance_text, str) and (
                    any(_mentions_id(provenance_text, clause) for clause in requirement_clause_ids)
                    or any(_mentions_id(provenance_text, branch_id) for branch_id in branches)
                )
            elif _values_equal(layer["layer"], "decisionRows"):
                branch = branches.get(row.get("branchId"))
                linked = bool(
                    branch
                    and set(row.get("sourceClauseIds", []))
                    & set(branch["sourceClauseIds"])
                )
            if not linked:
                orphans.append(row_id)
    return orphans


def assert_no_orphan_normative_rows(orphans: Sequence[str]) -> None:
    """分岐または典拠条文に結び付かない行を拒否する。"""
    if orphans:
        raise GapRegisterError(f"孤立した規範行がある: {list(orphans)!r}")


def unresolved_row_references(
    criteria: GapCriteria,
    gaps: Sequence[Mapping[str, Any]],
    documents: Mapping[str, Mapping[str, Any]],
    row_index: StageReferenceIndex,
) -> list[str]:
    """gapと生成caseの行参照で一意の規範行に解決できない箇所を返す。"""
    layers = {layer["layer"]: layer for layer in criteria.row_layers}
    rows_by_id = {
        _normative_row_id(layer, row): row
        for layer in criteria.row_layers
        for row in documents[layer["sourcePath"]][layer["layer"]]
    }
    unresolved = [
        f"{gap['gapId']}.rowIds: {row_id}"
        for gap in gaps for row_id in gap["rowIds"]
        if not _value_in(row_id, row_index.existing_references)
    ]
    for source_path, document in documents.items():
        for case in document["cases"]:
            case_row_reference = case["rowRef"]
            layer = layers.get(case_row_reference["layer"])
            coordinate = case_row_reference["coordinate"]
            if not layer or not _values_equal(layer["sourcePath"], source_path):
                unresolved.append(f"{case['caseId']}.rowRef: 層と資産pathが不一致")
                continue
            try:
                row_id = _normative_row_id(layer, coordinate)
            except GapRegisterError:
                unresolved.append(f"{case['caseId']}.rowRef: 自然キーが不正")
                continue
            row = rows_by_id.get(row_id)
            if not row or any(
                not _values_equal(row.get(key), value) for key, value in coordinate.items()
            ):
                unresolved.append(f"{case['caseId']}.rowRef: {row_id}")
    return unresolved


def assert_row_ids_resolve(unresolved: Sequence[str]) -> None:
    """一意の規範行へ解決できない参照を拒否する。"""
    if unresolved:
        raise GapRegisterError(f"行IDを一意に解決できない: {list(unresolved)!r}")


def _stage_reference_tokens(
    gap: Mapping[str, Any], field: str, criteria: GapCriteria
) -> frozenset[str]:
    """gapの1段を所有資産との突合に使う参照token集合へ変換する。"""
    value = gap[field]
    if field in criteria.list_stage_fields:
        return frozenset(value)
    if not _selector_is_filled(value):
        return frozenset()
    return frozenset((canonical_reference_token(value),))


def _validate_reference_index(
    field: str,
    index: StageReferenceIndex,
    criteria: GapCriteria,
) -> None:
    """所有資産から組み立てた参照indexの内部整合を検証する。"""
    if not all(
        isinstance(reference, str) and reference
        for reference in index.existing_references
    ):
        raise GapRegisterError(f"{field}: 参照元の実在集合に不正な値がある")
    if not all(
        isinstance(reference, str)
        and reference in index.existing_references
        and isinstance(gap_ids, frozenset)
        and all(gap_id in criteria.gap_ids for gap_id in gap_ids)
        for reference, gap_ids in index.gap_ids_by_reference.items()
    ):
        raise GapRegisterError(f"{field}: 参照元の逆方向indexが不正")


def _validate_stage_references(
    gaps: Sequence[Mapping[str, Any]],
    criteria: GapCriteria,
    policy: GapPredicatePolicy,
    reference_indexes: Mapping[str, StageReferenceIndex],
) -> None:
    """充填済み参照の実在と、宣言対象段の双方向一致を検証する。"""
    for field, index in reference_indexes.items():
        if field not in criteria.stage_fields:
            raise GapRegisterError(f"未知の段に参照元indexがある: {field}")
        _validate_reference_index(field, index, criteria)

    for gap in gaps:
        gap_id = gap["gapId"]
        bidirectional_stages = policy.bidirectional_stages
        if gap["state"] == criteria.terminal_state:
            bidirectional_stages |= policy.resolved_additional_bidirectional_stages
        for field in criteria.stage_fields:
            actual = _stage_reference_tokens(gap, field, criteria)
            index = reference_indexes.get(field)
            if actual and index is None:
                raise GapRegisterError(
                    f"{gap_id}.{field}: 参照元が未整備のため実在を判定できない"
                )
            if index is not None:
                missing = sorted(actual - index.existing_references)
                if missing:
                    raise GapRegisterError(
                        f"{gap_id}.{field}: 存在しない参照がある: {missing!r}"
                    )
            if field not in bidirectional_stages or index is None:
                continue
            reverse = frozenset(
                reference
                for reference, owners in index.gap_ids_by_reference.items()
                if gap_id in owners
            )
            if actual != reverse:
                raise GapRegisterError(
                    f"{gap_id}.{field}: 既に埋めた段が所有資産と双方向一致しない: "
                    f"gapOnly={sorted(actual - reverse)!r}; "
                    f"assetOnly={sorted(reverse - actual)!r}"
                )


def _validate_stage_predicate(
    gap: Mapping[str, Any], criteria: GapCriteria
) -> None:
    """openの連続prefixとresolvedの全段必須を検証する。"""
    gap_id = gap["gapId"]
    state = gap["state"]
    filled = _filled_stage_flags(gap, criteria)
    stage_count = len(criteria.stage_fields)
    first_empty = next(
        (index for index, value in enumerate(filled) if not value), stage_count
    )
    if any(filled[first_empty + 1 :]):
        raise GapRegisterError(
            f"{gap_id}: 5段は先頭から連続したprefixでなければならない"
        )
    if not filled[0]:
        raise GapRegisterError(f"{gap_id}: clauseIdsは空にできない")
    if state == criteria.terminal_state and first_empty != stage_count:
        raise GapRegisterError(f"{gap_id}: resolvedは5段すべてを必要とする")


def validate_gap_register_document(
    document: Mapping[str, Any],
    requirement_clause_ids: frozenset[str],
    criteria: GapCriteria,
    policy: GapPredicatePolicy,
    reference_indexes: Mapping[str, StageReferenceIndex] | None = None,
) -> None:
    """gap registerの骨格・条文参照・状態別述語を検証する。"""
    if set(document) != criteria.top_level_fields:
        raise GapRegisterError(
            "トップレベルのフィールドがexact-set不一致: "
            f"expected={sorted(criteria.top_level_fields)!r}; "
            f"actual={sorted(document)!r}"
        )
    if document.get("schemaVersion") != criteria.schema_version:
        raise GapRegisterError("schemaVersionが凍結基準と一致しない")
    if document.get("version") != REGISTER_PATH.stem:
        raise GapRegisterError("versionはファイル名と一致しなければならない")

    gaps = document.get("gaps")
    if not isinstance(gaps, list):
        raise GapRegisterError("gapsは配列でなければならない")

    gap_ids: list[str] = []
    validated_gaps: list[Mapping[str, Any]] = []
    for index, raw_gap in enumerate(gaps):
        gap = _expect_object(raw_gap, f"gaps[{index}]")
        if set(gap) != criteria.gap_fields:
            raise GapRegisterError(
                f"gaps[{index}]のフィールドがexact-set不一致"
            )
        gap_id = gap.get("gapId")
        if not isinstance(gap_id, str):
            raise GapRegisterError(f"gaps[{index}].gapIdは文字列でなければならない")
        gap_ids.append(gap_id)
        validated_gaps.append(gap)
        if gap.get("state") not in criteria.states:
            raise GapRegisterError(
                f"{gap_id}: stateが凍結した値集合に含まれない"
            )

        for field in criteria.list_stage_fields:
            _validate_string_id_list(gap.get(field), f"{gap_id}.{field}")

        missing_clause_ids = sorted(set(gap["clauseIds"]) - requirement_clause_ids)
        if missing_clause_ids:
            raise GapRegisterError(
                f"{gap_id}: 要件書に実在しないclauseIdsがある: {missing_clause_ids!r}"
            )
        _validate_stage_predicate(gap, criteria)

    if len(gap_ids) != len(set(gap_ids)):
        raise GapRegisterError("gapIdが重複している")
    if frozenset(gap_ids) != criteria.gap_ids:
        raise GapRegisterError(
            "gapIdが9件のexact-setと一致しない: "
            f"expected={sorted(criteria.gap_ids)!r}; actual={sorted(gap_ids)!r}"
        )
    indexes = dict(reference_indexes or {})
    clause_reverse_index = indexes.get(criteria.stage_fields[0])
    if clause_reverse_index is not None:
        _validate_reference_index(
            criteria.stage_fields[0], clause_reverse_index, criteria
        )
        unknown_clause_references = (
            clause_reverse_index.existing_references - requirement_clause_ids
        )
        if unknown_clause_references:
            raise GapRegisterError(
                "clauseIdsの逆方向indexに要件書外の参照がある: "
                f"{sorted(unknown_clause_references)!r}"
            )
    clause_reverse = (
        clause_reverse_index.gap_ids_by_reference
        if clause_reverse_index is not None
        else {}
    )
    indexes[criteria.stage_fields[0]] = StageReferenceIndex(
        existing_references=requirement_clause_ids,
        gap_ids_by_reference=clause_reverse,
    )
    _validate_stage_references(validated_gaps, criteria, policy, indexes)


def validate_state_progression(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    criteria: GapCriteria,
) -> None:
    """gapのstateがresolvedからopenへ逆遷移していないことを検証する。"""
    previous_states = {
        gap["gapId"]: gap["state"]
        for gap in previous.get("gaps", [])
        if isinstance(gap, dict)
    }
    current_states = {
        gap["gapId"]: gap["state"]
        for gap in current.get("gaps", [])
        if isinstance(gap, dict)
    }
    if set(previous_states) != set(current_states):
        raise GapRegisterError("state遷移の前後でgapId集合を変更してはならない")
    regressed = sorted(
        gap_id
        for gap_id, previous_state in previous_states.items()
        if previous_state == criteria.terminal_state
        and current_states[gap_id] == criteria.initial_state
    )
    if regressed:
        raise GapRegisterError(f"resolvedからopenへの逆遷移がある: {regressed!r}")


def load_requirement_clause_ids(root: Path) -> frozenset[str]:
    """既存の条文ID抽出器を要件書だけへ適用する。"""
    return clause_id_source.load_clause_ids_from_paths(root, (REQUIREMENTS_PATH,))


def load_requirement_branch_ids(root: Path) -> frozenset[str]:
    """既存の規範表抽出器で要件書の分岐IDを得る。"""
    path = root / REQUIREMENTS_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GapRegisterError(f"要件書をUTF-8で読めない: {path}: {error}") from error
    try:
        return parity_checker.extract_requirement_branch_ids(text)
    except parity_checker.ThreeWayParityError as error:
        raise GapRegisterError(str(error)) from error


def validate_clause_branch_register_document(
    document: Mapping[str, Any],
    requirement_clause_ids: frozenset[str],
    requirement_branch_ids: frozenset[str],
    policy: ClauseBranchPolicy,
) -> None:
    """条文分岐台帳の構造・条文実在・分岐集合を検証する。"""
    if not _values_equal(set(document), policy.top_level_fields):
        raise GapRegisterError("条文分岐台帳のトップレベルfieldがexact-set不一致")
    if not _values_equal(document.get("schemaVersion"), policy.schema_version):
        raise GapRegisterError("条文分岐台帳のschemaVersionがschemaと一致しない")
    if not _values_equal(document.get("version"), CLAUSE_BRANCH_REGISTER_PATH.stem):
        raise GapRegisterError("条文分岐台帳のversionがファイル名と一致しない")

    source = _expect_object(document.get("requirementsSource"), "requirementsSource")
    if not _values_equal(set(source), {"path", "version", "status"}):
        raise GapRegisterError("requirementsSourceのfieldがexact-set不一致")
    if (
        not _values_equal(
            source.get("path"), policy.requirements_source_path.as_posix()
        )
        or not _values_equal(source.get("version"), policy.requirements_version)
        or not _values_equal(source.get("status"), policy.requirements_status)
    ):
        raise GapRegisterError("requirementsSourceがschema宣言と一致しない")

    author = _expect_object(document.get("authorSignature"), "authorSignature")
    if not _values_equal(
        set(author), {"authorId", "recordedOn", "statement"}
    ):
        raise GapRegisterError("authorSignatureのfieldがexact-set不一致")
    if not isinstance(author.get("authorId"), str) or not author["authorId"]:
        raise GapRegisterError("authorSignature.authorIdが空である")
    if not isinstance(author.get("recordedOn"), str) or not author["recordedOn"]:
        raise GapRegisterError("authorSignature.recordedOnが空である")
    if not _values_equal(author.get("statement"), policy.author_statement):
        raise GapRegisterError("authorSignature.statementがschema宣言と一致しない")

    branches = document.get("branches")
    if not isinstance(branches, list) or not branches:
        raise GapRegisterError("branchesは空でない配列でなければならない")
    validated: list[Mapping[str, Any]] = []
    branch_ids: list[str] = []
    source_namespace_prefix = f"{policy.source_clause_namespace}:"
    for index, raw_branch in enumerate(branches):
        branch = _expect_object(raw_branch, f"branches[{index}]")
        if not _values_equal(set(branch), policy.branch_fields):
            raise GapRegisterError(f"branches[{index}]のfieldがexact-set不一致")
        branch_id = branch.get("branchId")
        branch_kind = branch.get("branchKind")
        coverage_kind = branch.get("coverageKind")
        if not isinstance(branch_id, str) or not branch_id:
            raise GapRegisterError(f"branches[{index}].branchIdが空である")
        if not _value_in(
            branch_kind,
            {policy.requirement_branch_kind, policy.game_end_outcome_kind},
        ):
            raise GapRegisterError(f"{branch_id}: branchKindが宣言外である")
        if not _value_in(coverage_kind, policy.coverage_kinds):
            raise GapRegisterError(f"{branch_id}: coverageKindが宣言外である")
        source_ids = _validate_string_id_list(
            branch.get("sourceClauseIds"), f"{branch_id}.sourceClauseIds"
        )
        missing_sources = sorted(
            source_id
            for source_id in source_ids
            if not _source_clause_exists(
                source_id, source_namespace_prefix, requirement_clause_ids
            )
        )
        if missing_sources:
            raise GapRegisterError(
                f"{branch_id}: 要件書に実在しない由来条文IDがある: {missing_sources!r}"
            )
        _validate_string_id_list(
            branch.get("relatedClauseBranchIds"),
            f"{branch_id}.relatedClauseBranchIds",
        )
        _validate_string_id_list(branch.get("gapIds"), f"{branch_id}.gapIds")
        branch_ids.append(branch_id)
        validated.append(branch)

    if len(branch_ids) != len(set(branch_ids)):
        raise GapRegisterError("条文分岐台帳のbranchIdが重複している")
    if not _values_equal(document.get("branchCount"), len(branches)):
        raise GapRegisterError("branchCountがbranchesの実数と一致しない")
    actual_ids = frozenset(branch_ids)
    if not _is_subset(policy.intentional_unassigned_branch_ids, actual_ids):
        raise GapRegisterError(
            "意図的な非帰属分岐に台帳へ実在しないbranchIdがある"
        )
    actual_unassigned = frozenset(
        branch["branchId"] for branch in validated if not branch["gapIds"]
    )
    if not _values_equal(
        actual_unassigned, policy.intentional_unassigned_branch_ids
    ):
        assigned_despite_declaration = sorted(
            policy.intentional_unassigned_branch_ids - actual_unassigned
        )
        raise GapRegisterError(
            "gapへ帰属しない分岐が資産側のexact-set宣言と一致しない: "
            f"undeclared={sorted(actual_unassigned - policy.intentional_unassigned_branch_ids)!r}; "
            f"assignedDespiteDeclaration={assigned_despite_declaration!r}"
        )
    requirement_entries = frozenset(
        branch["branchId"]
        for branch in validated
        if _values_equal(branch["branchKind"], policy.requirement_branch_kind)
    )
    if not _values_equal(requirement_entries, requirement_branch_ids):
        raise GapRegisterError(
            "要件書の規範表分岐と台帳がexact-set不一致: "
            f"missing={sorted(requirement_branch_ids - requirement_entries)!r}; "
            f"extra={sorted(requirement_entries - requirement_branch_ids)!r}"
        )

    outcomes = _expect_object(
        document.get("gameEndOutcomeBranches"), "gameEndOutcomeBranches"
    )
    if not _values_equal(
        frozenset(outcomes), frozenset(policy.game_end_outcome_roles)
    ):
        raise GapRegisterError("終了判定4役割の集合がschema宣言と一致しない")
    outcome_ids = _validate_string_id_list(
        list(outcomes.values()), "gameEndOutcomeBranches"
    )
    declared_outcome_ids = frozenset(
        branch["branchId"]
        for branch in validated
        if _values_equal(branch["branchKind"], policy.game_end_outcome_kind)
    )
    if not _values_equal(frozenset(outcome_ids), declared_outcome_ids):
        raise GapRegisterError("終了判定4役割とgame-end-outcome entryがexact-set不一致")
    if not _is_subset(declared_outcome_ids, actual_ids):
        raise GapRegisterError("終了判定4役割に解決できないbranchIdがある")

    for branch in validated:
        related_ids = frozenset(branch["relatedClauseBranchIds"])
        missing_related = sorted(related_ids - actual_ids)
        if missing_related:
            raise GapRegisterError(
                f"{branch['branchId']}: 解決できない関連分岐がある: {missing_related!r}"
            )
        if _values_equal(branch["branchKind"], policy.game_end_outcome_kind):
            if not related_ids:
                raise GapRegisterError(
                    f"{branch['branchId']}: 終了判定結果に下位分岐参照がない"
                )
            if not _is_subset(related_ids, requirement_branch_ids):
                raise GapRegisterError(
                    f"{branch['branchId']}: 終了判定結果が要件書外の下位分岐を参照している"
                )


def clause_branch_reference_index(
    document: Mapping[str, Any],
) -> StageReferenceIndex:
    """条文分岐台帳をgap registerのbranch段の参照indexへ変換する。"""
    branches = document.get("branches")
    if not isinstance(branches, list):
        raise GapRegisterError("branchesを参照indexへ変換できない")
    owners: dict[str, frozenset[str]] = {}
    for index, raw_branch in enumerate(branches):
        branch = _expect_object(raw_branch, f"branches[{index}]")
        branch_id = branch.get("branchId")
        gap_ids = branch.get("gapIds")
        if not isinstance(branch_id, str) or not isinstance(gap_ids, list):
            raise GapRegisterError("branch参照indexのentryが不正")
        owners[branch_id] = frozenset(gap_ids)
    return StageReferenceIndex(
        existing_references=frozenset(owners), gap_ids_by_reference=owners
    )


def fixture_reference_index(
    branch_document: Mapping[str, Any],
    fixture_documents: Sequence[Mapping[str, Any]],
) -> StageReferenceIndex:
    """fixtureの分岐IDを分岐台帳のgapIdsへ結び付け逆方向帰属を作る。"""
    branch_index = clause_branch_reference_index(branch_document)
    owners: dict[str, frozenset[str]] = {}
    for document in fixture_documents:
        fixtures = document.get("fixtures")
        if not isinstance(fixtures, list):
            raise GapRegisterError("fixture資産にfixtures配列がない")
        for position, raw_fixture in enumerate(fixtures):
            fixture = _expect_object(raw_fixture, f"fixtures[{position}]")
            case = _expect_object(fixture.get("case"), f"fixtures[{position}].case")
            case_id = case.get("caseId")
            branch_id = case.get("branchId")
            if not isinstance(case_id, str) or not case_id:
                raise GapRegisterError("fixtureのcaseIdが不正")
            if not isinstance(branch_id, str) or not _value_in(
                branch_id, branch_index.existing_references
            ):
                raise GapRegisterError(f"{case_id}: fixtureのbranchIdが分岐台帳にない")
            if _value_in(case_id, frozenset(owners)):
                raise GapRegisterError(f"fixtureのcaseIdが重複している: {case_id}")
            owners[case_id] = branch_index.gap_ids_by_reference[branch_id]
    return StageReferenceIndex(
        existing_references=frozenset(owners), gap_ids_by_reference=owners
    )


def generated_case_reference_index(
    criteria: GapCriteria,
    row_index: StageReferenceIndex,
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[StageReferenceIndex, dict[str, frozenset[str]]]:
    """caseのrowRefを規範行へ結び、GAPごとの生成case集合を逆引きする。"""
    layers = {layer["layer"]: layer for layer in criteria.row_layers}
    owners: dict[str, frozenset[str]] = {}
    selected_by_group: dict[tuple[str, str], set[str]] = {}
    selected: dict[str, frozenset[str]] = {}
    seen_case_ids: set[str] = set()
    for source_path, document in documents.items():
        cases = document.get("cases")
        if not isinstance(cases, list):
            raise GapRegisterError(f"生成case資産にcases配列がない: {source_path}")
        for position, raw_case in enumerate(cases):
            case = _expect_object(raw_case, f"{source_path}.cases[{position}]")
            case_id = case.get("caseId")
            row_ref = _expect_object(case.get("rowRef"), f"{source_path}.{case_id}.rowRef")
            layer_name = row_ref.get("layer")
            if not isinstance(layer_name, str):
                raise GapRegisterError(f"{case_id}: rowRefの層が文字列でない")
            layer = layers.get(layer_name)
            if layer is None or not _values_equal(layer["sourcePath"], source_path):
                raise GapRegisterError(f"{case_id}: rowRefの層または資産pathが不正")
            coordinate = _expect_object(row_ref.get("coordinate"), f"{case_id}.coordinate")
            row_id = ":".join((layer_name, *(
                _row_key_value(coordinate, path) for path in layer["keyPaths"]
            )))
            if row_id not in row_index.existing_references:
                raise GapRegisterError(f"{case_id}: rowRefが規範行に存在しない: {row_id}")
            if not isinstance(case_id, str) or not case_id or _value_in(
                case_id, frozenset(seen_case_ids)
            ):
                raise GapRegisterError(f"生成caseIdが不正または重複: {case_id}")
            seen_case_ids.add(case_id)
            for gap_id in row_index.gap_ids_by_reference[row_id]:
                selected_by_group.setdefault((source_path, gap_id), set()).add(case_id)
    for (source_path, gap_id), case_ids in selected_by_group.items():
        selector = generated_case_selector(source_path, gap_id, len(case_ids))
        token = canonical_reference_token(selector)
        owners[token] = frozenset({gap_id})
        selected[token] = frozenset(case_ids)
    return (
        StageReferenceIndex(frozenset(owners), owners),
        selected,
    )


def check_repository(root: Path) -> None:
    """リポジトリ内の条文分岐台帳とgap registerを検証する。"""
    path = root / REGISTER_PATH
    if (
        len(REGISTER_PATH.parts) != 3
        or REGISTER_PATH.parts[:2] != ("contracts", "state-transition")
        or parity_checker.CONTRACT_FILENAME_PATTERN.fullmatch(path.name) is None
    ):
        raise GapRegisterError("gap registerがD-12の配置・命名規則に適合しない")
    branch_path = root / CLAUSE_BRANCH_REGISTER_PATH
    branch_schema_path = root / CLAUSE_BRANCH_SCHEMA_PATH
    for candidate, label in (
        (branch_path, "clause branch register"),
        (branch_schema_path, "clause branch register schema"),
    ):
        relative = candidate.relative_to(root)
        if (
            len(relative.parts) != 3
            or not _values_equal(
                relative.parts[:2], ("contracts", "state-transition")
            )
            or parity_checker.CONTRACT_FILENAME_PATTERN.fullmatch(candidate.name)
            is None
        ):
            raise GapRegisterError(f"{label}がD-12の配置・命名規則に適合しない")
    branch_schema = _expect_object(
        clause_id_source.load_json(branch_schema_path, "clause branch register schema"),
        "clause branch register schema",
    )
    branch_policy = load_clause_branch_schema_policy(branch_schema)
    branch_document = _expect_object(
        clause_id_source.load_json(branch_path, "clause branch register"),
        "clause branch register",
    )
    requirement_clause_ids = load_requirement_clause_ids(root)
    validate_clause_branch_register_document(
        branch_document,
        requirement_clause_ids,
        load_requirement_branch_ids(root),
        branch_policy,
    )
    document = _expect_object(
        clause_id_source.load_json(path, "gap register"), "gap register"
    )
    descriptor = _expect_object(
        clause_id_source.load_json(
            root / clause_id_source.DESCRIPTOR_PATH, "入力軸descriptor"
        ),
        "入力軸descriptor",
    )
    criteria = load_gap_criteria(descriptor)
    schema = _expect_object(
        clause_id_source.load_json(root / SCHEMA_PATH, L_SCHEMA_ASSET),
        L_SCHEMA_ASSET,
    )
    policy = load_gap_schema_policy(schema, criteria)
    row_documents: dict[str, Mapping[str, Any]] = {}
    for layer in criteria.row_layers:
        relative = PurePosixPath(layer["sourcePath"])
        if relative.is_absolute() or ".." in relative.parts:
            raise GapRegisterError(f"規範行資産のpathが不正: {relative}")
        if layer["sourcePath"] not in row_documents:
            row_documents[layer["sourcePath"]] = _expect_object(
                clause_id_source.load_json(root / relative, "規範行資産"),
                "規範行資産",
            )
    fixture_documents = [
        _expect_object(
            clause_id_source.load_json(root / relative, "手作業fixture"),
            "手作業fixture",
        )
        for relative in MANUAL_FIXTURE_PATHS
    ]
    row_index = row_reference_index(criteria, document["gaps"], row_documents)
    row_rules = _expect_object(
        clause_id_source.load_json(root / ROW_RULES_PATH, "規範行の語彙軸典拠"),
        "規範行の語彙軸典拠",
    )
    orphans = orphan_normative_row_ids(
        criteria, row_documents, branch_document, requirement_clause_ids, row_rules
    )
    assert_no_orphan_normative_rows(orphans)
    unresolved = unresolved_row_references(
        criteria, document["gaps"], row_documents, row_index
    )
    assert_row_ids_resolve(unresolved)
    generated_documents = {
        source_path: row_documents[source_path]
        for source_path in {layer["sourcePath"] for layer in criteria.row_layers}
    }
    generated_index, _ = generated_case_reference_index(
        criteria, row_index, generated_documents
    )
    validate_gap_register_document(
        document,
        requirement_clause_ids,
        criteria,
        policy,
        {
            "clauseIds": clause_reference_index(policy),
            "branchIds": clause_branch_reference_index(branch_document),
            "rowIds": row_index,
            "fixtureCaseIds": fixture_reference_index(
                branch_document, fixture_documents
            ),
            "generatedCaseSelector": generated_index,
        },
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """CLI引数を解析する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """gap register検査を実行する。"""
    args = _parse_args(argv)
    try:
        check_repository(args.root.resolve())
    except (GapRegisterError, clause_id_source.DescriptorCheckError) as error:
        print(f"gap-register: ERROR: {error}", file=sys.stderr)
        return 1
    print("gap-register: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
