"""定義の穴9件を追跡するgap registerの骨格と状態述語を検証する。"""

from __future__ import annotations

import argparse
import json
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


@dataclass(frozen=True)
class GapPredicatePolicy:
    """schema資産が宣言する段ごとの参照検査方式。"""

    existence_only_stages: frozenset[str]
    bidirectional_stages: frozenset[str]
    resolved_additional_bidirectional_stages: frozenset[str]


@dataclass(frozen=True)
class StageReferenceIndex:
    """所有資産から得た参照の実在集合とgapへの逆方向帰属。"""

    existing_references: frozenset[str]
    gap_ids_by_reference: Mapping[str, frozenset[str]]


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
    return GapPredicatePolicy(
        existence_only_stages=existence_set,
        bidirectional_stages=bidirectional_set,
        resolved_additional_bidirectional_stages=resolved_additional_set,
    )


def _expect_object(value: object, label: str) -> dict[str, Any]:
    """JSON objectを検証して返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GapRegisterError(f"{label}は文字列キーのobjectでなければならない")
    return value


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


def check_repository(root: Path) -> None:
    """リポジトリ内のgap registerを検証する。"""
    path = root / REGISTER_PATH
    if (
        len(REGISTER_PATH.parts) != 3
        or REGISTER_PATH.parts[:2] != ("contracts", "state-transition")
        or parity_checker.CONTRACT_FILENAME_PATTERN.fullmatch(path.name) is None
    ):
        raise GapRegisterError("gap registerがD-12の配置・命名規則に適合しない")
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
    validate_gap_register_document(
        document,
        load_requirement_clause_ids(root),
        criteria,
        policy,
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
