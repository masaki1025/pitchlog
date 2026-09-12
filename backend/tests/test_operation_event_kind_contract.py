"""操作イベント種別の正本・コード・manifest 契約を照合する。"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import replace
from itertools import product
from pathlib import Path

import pytest
from type_boundary_contract import (
    _markdown_tables,
    _plain_markdown_cell,
    _section_body,
)

from pitchlog.db.model_metadata import is_task_handoff_id
from pitchlog.db.sync_protocol.event_kinds import (
    C12_CHECK_EXPRESSIONS,
    C12_REQUIREMENT_MATRIX,
    C12_VALUES,
    CHANGE_EVENT_KIND_LITERALS,
    CONDITIONAL_EVENT_KIND_LITERALS,
    EVENT_KIND_LITERALS,
    OPERATION_EVENT_PARTICIPATIONS,
    STATE_CORRECTION_EVENT_KIND,
    C12Requirement,
    C12Value,
    ParticipationBinding,
    c12_cell_check_expression,
    generate_c12_check_expressions,
    validate_c12_requirement_matrix,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DATA_MODEL_PATH = _REPOSITORY_ROOT / "docs" / "design" / "data-model.md"
_DESIGN_PATH = (
    _REPOSITORY_ROOT / "docs" / "features" / "orm-schema-migration" / "design.md"
)
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_CANONICAL_D2_REQUIREMENT_BY_TEXT = {
    "必須": C12Requirement.REQUIRED,
    "持たない": C12Requirement.FORBIDDEN,
    "採用時のみ必須": C12Requirement.UNREPRESENTABLE,
    "元が論理位置を持つ場合だけ元の D2 を引き継ぐ": (C12Requirement.UNREPRESENTABLE),
}


def _canonical_participation_rows(
    document: str,
) -> tuple[tuple[int, str, str], ...]:
    """正本 5-3 節から番号・種別名・自身の D2 を文書順に抽出する。"""
    body = _section_body(document, "5-3")
    candidates: list[tuple[tuple[int, str, str], ...]] = []
    for headers, rows in _markdown_tables(body):
        plain_headers = [_plain_markdown_cell(header) for header in headers]
        if not {"参加区分", "種別", "自身の D2"} <= set(plain_headers):
            continue
        number_index = plain_headers.index("参加区分")
        kind_index = plain_headers.index("種別")
        d2_index = plain_headers.index("自身の D2")
        contracts: list[tuple[int, str, str]] = []
        for row in rows:
            number_text = _plain_markdown_cell(row[number_index])
            number_match = re.fullmatch(r"#(?P<number>\d+)", number_text)
            if number_match is None:
                raise ValueError(f"参加区分番号を解決できない: {number_text}")
            contracts.append(
                (
                    int(number_match.group("number")),
                    _plain_markdown_cell(row[kind_index]),
                    _plain_markdown_cell(row[d2_index]),
                )
            )
        candidates.append(tuple(contracts))
    if len(candidates) != 1:
        raise ValueError(f"参加区分表を一意に解決できない: {len(candidates)} 件")
    return candidates[0]


def _canonical_participation_kinds(document: str) -> tuple[tuple[int, str], ...]:
    """既存パーサの土台から番号と種別名だけを文書順に返す。"""
    return tuple(
        (number, kind)
        for number, kind, _d2_requirement in _canonical_participation_rows(document)
    )


def _canonical_v6_requirements(
    document: str,
) -> dict[tuple[int, C12Value], C12Requirement]:
    """正本の自身の D2 文言を C12 の V6 要求へ写す。

    ``data-model.md:5-3`` の4表現を一元的に写し、必須・持たないはそれぞれ
    必須・禁止、採用判断待ちは表現不能へ写す。元種別を継承する改訂版も、
    それ自身を名指す物理列がないため表現不能とする。
    """
    requirements: dict[tuple[int, C12Value], C12Requirement] = {}
    for number, _kind, d2_text in _canonical_participation_rows(document):
        try:
            requirement = _CANONICAL_D2_REQUIREMENT_BY_TEXT[d2_text]
        except KeyError as error:
            raise ValueError(
                f"自身の D2 の要求区分を解決できない: {d2_text}"
            ) from error
        requirements[(number, C12Value.V6)] = requirement
    return requirements


def _assert_canonical_v6_matches_matrix(document: str) -> None:
    """正本の D2 要求とマトリクスの V6 行を exact-set 照合する。"""
    matrix_requirements = {
        key: cell.requirement
        for key, cell in C12_REQUIREMENT_MATRIX.items()
        if cell.value is C12Value.V6
    }
    assert matrix_requirements == _canonical_v6_requirements(document)


def _design_event_kind_contracts(
    document: str,
) -> tuple[tuple[int, str, str, str | None], ...]:
    """詳細設計 3-6 節から番号・種別名・対応・リテラルを抽出する。"""
    body = _section_body(document, "3-6")
    for headers, rows in _markdown_tables(body):
        plain_headers = [_plain_markdown_cell(header) for header in headers]
        if plain_headers[:4] != [
            "#",
            "正本 5-3 節の参加区分",
            "対応",
            "V5 リテラル",
        ]:
            continue
        contracts: list[tuple[int, str, str, str | None]] = []
        for row in rows:
            number = _plain_markdown_cell(row[0])
            match = re.fullmatch(r"#(?P<number>\d+)", number)
            if match is None:
                raise ValueError(f"詳細設計の参加区分番号を解決できない: {number}")
            literal = _plain_markdown_cell(row[3])
            contracts.append(
                (
                    int(match.group("number")),
                    _plain_markdown_cell(row[1]),
                    _plain_markdown_cell(row[2]),
                    None if literal == "—" else literal,
                )
            )
        return tuple(contracts)
    raise ValueError("詳細設計 3-6 節の操作イベント種別対応表がない")


def test_event_kind_mapping_exactly_covers_canonical_participation_kinds() -> None:
    """対応表が正本の全参加区分だけを文書順に覆うと示す。"""
    canonical = _canonical_participation_kinds(
        _DATA_MODEL_PATH.read_text(encoding="utf-8")
    )
    code_contract = tuple(
        (participation.participation_number, participation.canonical_name)
        for participation in OPERATION_EVENT_PARTICIPATIONS
    )

    assert code_contract == canonical
    assert len(EVENT_KIND_LITERALS) == len(set(EVENT_KIND_LITERALS))
    assert len(EVENT_KIND_LITERALS) == 9
    assert CONDITIONAL_EVENT_KIND_LITERALS == (STATE_CORRECTION_EVENT_KIND,)
    assert {"state_correction", "tombstone", "revision"}.isdisjoint(EVENT_KIND_LITERALS)
    assert all(
        participation.event_kind_literal is None
        for participation in OPERATION_EVENT_PARTICIPATIONS
        if participation.binding
        in {ParticipationBinding.TOMBSTONE_STATE, ParticipationBinding.REVISION_STATE}
    )


def test_manifest_event_kind_check_literals_match_the_mapping() -> None:
    """列挙 CHECK のリテラル集合がコード側の対応表と一致すると示す。"""
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    operation_events = next(
        table for table in manifest["tables"] if table["name"] == "operation_events"
    )
    enum_checks = [
        check
        for check in operation_events["checks"]
        if re.fullmatch(r"event_kind IN \((?:'[^']+'(?:, )?)+\)", check)
    ]

    assert len(enum_checks) == 1
    assert tuple(re.findall(r"'([^']+)'", enum_checks[0])) == EVENT_KIND_LITERALS


def test_design_event_kind_table_matches_the_code_contract() -> None:
    """跨ぐ契約として記録した詳細設計の対応表がコードと一致すると示す。"""
    design_contract = _design_event_kind_contracts(
        _DESIGN_PATH.read_text(encoding="utf-8")
    )
    code_contract = tuple(
        (
            participation.participation_number,
            participation.canonical_name,
            participation.binding.value,
            participation.event_kind_literal,
        )
        for participation in OPERATION_EVENT_PARTICIPATIONS
    )

    assert design_contract == code_contract


def test_c12_matrix_exactly_covers_participation_value_product() -> None:
    """C12 の全セルが参加区分と値の直積を過不足なく覆うと示す。"""
    expected_keys = {
        (participation.participation_number, value)
        for participation, value in product(OPERATION_EVENT_PARTICIPATIONS, C12_VALUES)
    }

    validate_c12_requirement_matrix(C12_REQUIREMENT_MATRIX)
    assert set(C12_REQUIREMENT_MATRIX) == expected_keys
    assert len(expected_keys) == 84
    assert all(
        cell.requirement in C12Requirement for cell in C12_REQUIREMENT_MATRIX.values()
    )


def test_c12_unrepresentable_cells_have_explicit_handoffs() -> None:
    """全84セルを走査し、射程外セルの理由と実タスク ID を検査する。"""
    cells = tuple(
        cell
        for cell in C12_REQUIREMENT_MATRIX.values()
        if cell.requirement is C12Requirement.UNREPRESENTABLE
    )
    ordinary_v10 = {
        participation.participation_number
        for participation in OPERATION_EVENT_PARTICIPATIONS
        if participation.event_kind_literal is not None
        and participation.event_kind_literal not in CHANGE_EVENT_KIND_LITERALS
        and participation.canonical_name != "undo"
    }
    expected_keys = {(number, C12Value.V10) for number in ordinary_v10} | {
        (
            next(
                participation.participation_number
                for participation in OPERATION_EVENT_PARTICIPATIONS
                if participation.binding is ParticipationBinding.TOMBSTONE_STATE
            ),
            C12Value.V10,
        ),
        (
            next(
                participation.participation_number
                for participation in OPERATION_EVENT_PARTICIPATIONS
                if participation.binding is ParticipationBinding.CONDITIONAL_EVENT_KIND
            ),
            C12Value.V6,
        ),
    }
    revision_number = next(
        participation.participation_number
        for participation in OPERATION_EVENT_PARTICIPATIONS
        if participation.binding is ParticipationBinding.REVISION_STATE
    )
    expected_keys |= {(revision_number, value) for value in C12_VALUES}

    assert {
        (cell.participation.participation_number, cell.value) for cell in cells
    } == (expected_keys)
    assert all(cell.unrepresentable_reason for cell in cells)
    assert all(cell.unrepresentable_handoff for cell in cells)
    assert all(
        cell.unrepresentable_handoff is None
        or is_task_handoff_id(cell.unrepresentable_handoff)
        for cell in C12_REQUIREMENT_MATRIX.values()
    )


def test_c12_first_seven_kind_predicates_exclude_tombstones() -> None:
    """D-1 により通常の種別条件が同じ種別を持つ墓標へ効かないと示す。"""
    queued_kind_participations = tuple(
        participation
        for participation in OPERATION_EVENT_PARTICIPATIONS
        if participation.event_kind_literal is not None
        and participation.event_kind_literal not in CHANGE_EVENT_KIND_LITERALS
    )

    assert len(queued_kind_participations) == 7
    assert all(
        C12_REQUIREMENT_MATRIX[
            (participation.participation_number, value)
        ].row_predicate.endswith("AND NOT is_tombstone")
        for participation, value in product(queued_kind_participations, C12_VALUES)
    )


def test_c12_matrix_covers_the_known_missing_guards() -> None:
    """P0-3 の D2・状態差分・対象参照の分類を固定する。"""
    number_by_name = {
        participation.canonical_name: participation.participation_number
        for participation in OPERATION_EVENT_PARTICIPATIONS
    }

    assert all(
        C12_REQUIREMENT_MATRIX[(number_by_name[name], C12Value.V6)].requirement
        is C12Requirement.REQUIRED
        for name in ("選手交代", "タイブレーク開始", "試合終了宣言")
    )
    assert (
        C12_REQUIREMENT_MATRIX[(number_by_name["undo"], C12Value.V8)].requirement
        is C12Requirement.FORBIDDEN
    )
    assert (
        C12_REQUIREMENT_MATRIX[(number_by_name["undo"], C12Value.V10)].requirement
        is C12Requirement.REQUIRED
    )
    state_correction_v8 = C12_REQUIREMENT_MATRIX[
        (number_by_name["状態補正"], C12Value.V8)
    ]
    assert state_correction_v8.requirement is C12Requirement.REQUIRED
    assert state_correction_v8.source == "sync-protocol.md:4-6"


def test_c12_v6_requirements_exactly_match_the_canonical_d2_column() -> None:
    """正本 5-3 表の自身の D2 と V6 の要求区分を exact-set 照合する。"""
    _assert_canonical_v6_matches_matrix(_DATA_MODEL_PATH.read_text(encoding="utf-8"))


def test_c12_check_expressions_are_derived_from_enforceable_cells() -> None:
    """CHECK 式が golden ではなくセルの述語・担い手から生成されると示す。"""
    generated = generate_c12_check_expressions(C12_REQUIREMENT_MATRIX)

    assert generated == C12_CHECK_EXPRESSIONS
    for value in C12_VALUES:
        expected_parts = tuple(
            expression
            for participation in OPERATION_EVENT_PARTICIPATIONS
            if (
                expression := c12_cell_check_expression(
                    C12_REQUIREMENT_MATRIX[(participation.participation_number, value)]
                )
            )
            is not None
        )
        assert generated[value] == (" AND ".join(expected_parts) or "TRUE")
        for participation in OPERATION_EVENT_PARTICIPATIONS:
            cell = C12_REQUIREMENT_MATRIX[(participation.participation_number, value)]
            expression = c12_cell_check_expression(cell)
            if expression is None:
                continue
            assert cell.row_predicate in expression
            assert all(column in expression for column in cell.carrier_columns)


def test_c12_tautological_v9_cells_are_omitted_from_generation() -> None:
    """D-1 で恒真になる通常行と墓標自身の V9 項を生成しない。"""
    cells = (
        C12_REQUIREMENT_MATRIX[(participation.participation_number, C12Value.V9)]
        for participation in OPERATION_EVENT_PARTICIPATIONS
        if participation.binding
        in {
            ParticipationBinding.EVENT_KIND,
            ParticipationBinding.CONDITIONAL_EVENT_KIND,
            ParticipationBinding.TOMBSTONE_STATE,
        }
        and participation.event_kind_literal not in CHANGE_EVENT_KIND_LITERALS
    )

    assert all(c12_cell_check_expression(cell) is None for cell in cells)


def test_c12_missing_cell_negative_case_is_red() -> None:
    """N-6: 直積からセルを 1 件落とすと網羅性検査が拒否する。"""
    matrix = dict(C12_REQUIREMENT_MATRIX)
    matrix.pop(next(iter(matrix)))

    with pytest.raises(ValueError, match="C12 セルの母集団が不一致"):
        validate_c12_requirement_matrix(matrix)


def test_c12_unrepresentable_metadata_negative_cases_are_red() -> None:
    """N-9: #9 セルの理由・受け取り先の片落ちを拒否する。"""
    cell = next(
        cell
        for cell in C12_REQUIREMENT_MATRIX.values()
        if cell.participation.binding is ParticipationBinding.REVISION_STATE
    )

    with pytest.raises(ValueError, match="理由が必要"):
        replace(cell, unrepresentable_reason=None)
    with pytest.raises(ValueError, match="受け取り先 ID が必要"):
        replace(cell, unrepresentable_handoff=None)
    with pytest.raises(ValueError, match=r"TSK-<数字> 形式"):
        replace(cell, unrepresentable_handoff="follow-up-A")


def test_c12_canonical_d2_mutation_negative_case_is_red() -> None:
    """N-10: 正本 fixture の自身の D2 を変えると exact-set 照合が拒否する。"""
    document = _DATA_MODEL_PATH.read_text(encoding="utf-8")
    original = "| **#3** | 選手交代 | 論理位置を持つ | **必須** |"
    mutated = "| **#3** | 選手交代 | 論理位置を持つ | **持たない** |"
    assert document.count(original) == 1

    with pytest.raises(AssertionError):
        _assert_canonical_v6_matches_matrix(document.replace(original, mutated))


@pytest.mark.parametrize(
    "replaced_at",
    ("2026-09-12T00:00:00+00:00", None),
    ids=("replaced-old-version", "unreplaced-version"),
)
def test_change_event_version_satisfies_generated_checks(
    replaced_at: str | None,
) -> None:
    """変更イベントの旧版と未置換版を生成式へ通して実測する。"""
    row = {
        "event_kind": "play_change",
        "is_tombstone": False,
        "replaced_at": replaced_at,
        "d1": None,
        "generation": None,
        "expected_version": 1,
    }
    with sqlite3.connect(":memory:") as connection:
        results = {
            value: bool(
                connection.execute(
                    f"""
                    SELECT {C12_CHECK_EXPRESSIONS[value]}
                    FROM (
                        SELECT
                            :event_kind AS event_kind,
                            :is_tombstone AS is_tombstone,
                            :replaced_at AS replaced_at,
                            :d1 AS d1,
                            :generation AS generation,
                            :expected_version AS expected_version
                    ) AS operation_event
                    """,
                    row,
                ).fetchone()[0]
            )
            for value in (C12Value.V2, C12Value.V3, C12Value.V11)
        }

    assert results == {
        C12Value.V2: True,
        C12Value.V3: True,
        C12Value.V11: True,
    }
