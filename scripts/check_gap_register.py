"""定義の穴9件を追跡するgap registerの骨格と状態述語を検証する。"""

from __future__ import annotations

import argparse
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
REQUIREMENTS_PATH = parity_checker.REQUIREMENTS_PATH


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
    validate_gap_register_document(
        document, load_requirement_clause_ids(root), criteria
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
