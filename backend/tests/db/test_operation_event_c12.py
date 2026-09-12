"""C12 の生成 CHECK を PostgreSQL の真理値表とセル負例で検査する。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from itertools import product
from typing import Any, LiteralString, cast

import psycopg
import pytest
from alembic import command
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy import CheckConstraint, Table

from pitchlog.db.sync_protocol.event_kinds import (
    C12_CHECK_EXPRESSIONS,
    C12_REQUIREMENT_MATRIX,
    C12_TOMBSTONE_CHECK_EXPRESSION,
    CHANGE_EVENT_KIND_LITERALS,
    EVENT_KIND_CHECK_EXPRESSION,
    EVENT_KIND_LITERALS,
    OPERATION_EVENT_PARTICIPATIONS,
    PLAY_INPUT_EVENT_KIND,
    STATE_DIFF_BY_EVENT_KIND_CHECK_EXPRESSION,
    TOMBSTONE_CHECK_EXPRESSION,
    C12Cell,
    C12Requirement,
    C12Value,
    OperationEventParticipation,
    ParticipationBinding,
    c12_cell_check_expression,
)
from pitchlog.db.sync_protocol.models import OperationEvent

from .conftest import DisposablePostgres
from .test_alembic_migrations import _alembic_config, _sqlalchemy_url

pytestmark = pytest.mark.requires_db

_REVISION = "0026_operation_event_c12"
_PARENT_REVISION = "0025_operation_event_immutable"
_CONNECTED_C12_CHECKS = {
    "ck_operation_events_d2_by_kind": C12_CHECK_EXPRESSIONS[C12Value.V6],
    "ck_operation_events_state_diff_by_kind": C12_CHECK_EXPRESSIONS[C12Value.V8],
    "ck_operation_events_tombstone": C12_TOMBSTONE_CHECK_EXPRESSION,
    "ck_operation_events_target_by_kind": C12_CHECK_EXPRESSIONS[C12Value.V10],
    "ck_operation_events_expected_version_by_kind": C12_CHECK_EXPRESSIONS[C12Value.V11],
}
_CONNECTED_CONSTRAINT_BY_VALUE = {
    C12Value.V6: "ck_operation_events_d2_by_kind",
    C12Value.V8: "ck_operation_events_state_diff_by_kind",
    C12Value.V9: "ck_operation_events_tombstone",
    C12Value.V10: "ck_operation_events_target_by_kind",
    C12Value.V11: "ck_operation_events_expected_version_by_kind",
}
_LEGACY_NAMED_CHECKS = {
    "ck_operation_events_state_diff_by_kind": (
        STATE_DIFF_BY_EVENT_KIND_CHECK_EXPRESSION
    ),
    "ck_operation_events_tombstone": TOMBSTONE_CHECK_EXPRESSION,
}
_UNNAMED_0005_CHECKS = (
    "ledger_kind = 'accepted'",
    "(d1 IS NULL) = (generation IS NULL)",
    "event_kind NOT IN ('play_change', 'play_delete', 'substitution_change') OR "
    "(d1 IS NULL AND d2 IS NULL AND generation IS NULL AND target_generation IS "
    "NOT NULL AND target_d1 IS NOT NULL AND expected_version IS NOT NULL)",
    "event_kind IN ('play_change', 'play_delete', 'substitution_change') OR d1 IS "
    "NOT NULL",
)
_LEGACY_CHECK_EXPRESSIONS = (
    *_UNNAMED_0005_CHECKS,
    "(target_generation IS NULL) = (target_d1 IS NULL)",
    EVENT_KIND_CHECK_EXPRESSION,
    STATE_DIFF_BY_EVENT_KIND_CHECK_EXPRESSION,
    TOMBSTONE_CHECK_EXPRESSION,
)
_ORM_CHECK_EXPRESSIONS = tuple(
    sorted(
        str(constraint.sqltext)
        for constraint in cast(Table, OperationEvent.__table__).constraints
        if isinstance(constraint, CheckConstraint)
    )
)
# 通常行の V9 禁止 7 セルと墓標の V9 必須 1 セルは、担い手を反転すると
# 同時に行述語も偽になる恒真含意であり、違反行を構成できない。ステップ 5 の
# 生成器が明示的に落とすこの 8 セル以外を DB 負例へ自動展開する。
_ENFORCEABLE_CELLS = tuple(
    cell
    for cell in C12_REQUIREMENT_MATRIX.values()
    if cell.requirement in {C12Requirement.REQUIRED, C12Requirement.FORBIDDEN}
    and c12_cell_check_expression(cell) is not None
)


@dataclass(frozen=True, order=True)
class _TruthCase:
    """N-8 の 1 行を一意に識別する 6 軸。"""

    event_kind: str
    is_tombstone: bool
    d2_present: bool
    state_diff_present: bool
    target_present: bool
    expected_version_present: bool


def _truth_cases() -> tuple[_TruthCase, ...]:
    """9 種別と 5 個の真偽軸の直積 288 行を機械生成する。"""
    return tuple(
        _TruthCase(event_kind, *flags)
        for event_kind in EVENT_KIND_LITERALS
        for flags in product((False, True), repeat=5)
    )


def _check_conjunction(expressions: Iterable[str]) -> str:
    """CHECK 式群を個別に括って 1 個の評価式へまとめる。"""
    return " AND ".join(f"({expression})" for expression in expressions)


def _trusted_sql(expression: str) -> sql.SQL:
    """製品コードかテスト定数だけから得た CHECK 式を SQL fragment にする。"""
    return sql.SQL(cast(LiteralString, expression))


def _evaluate_truth_table(
    cursor: psycopg.Cursor[Any], cases: tuple[_TruthCase, ...]
) -> dict[_TruthCase, tuple[bool, bool]]:
    """旧式と新式を VALUES 由来の全行について PostgreSQL に評価させる。"""
    value_rows = sql.SQL(", ").join(sql.SQL("(%s, %s, %s, %s, %s, %s)") for _ in cases)
    query = sql.SQL(
        """
        WITH case_flags (
            event_kind,
            is_tombstone,
            d2_present,
            state_diff_present,
            target_present,
            expected_version_present
        ) AS (
            VALUES {value_rows}
        ),
        cases AS (
            SELECT
                case_flags.*,
                CASE
                    WHEN event_kind = ANY(CAST(%s AS text[])) THEN NULL::bigint
                    ELSE 1::bigint
                END AS d1,
                CASE
                    WHEN event_kind = ANY(CAST(%s AS text[])) THEN NULL::bigint
                    ELSE 1::bigint
                END AS generation,
                CASE WHEN d2_present THEN 1::bigint ELSE NULL::bigint END AS d2,
                CASE
                    WHEN state_diff_present THEN '{{}}'::jsonb
                    ELSE NULL::jsonb
                END AS state_diff,
                CASE
                    WHEN target_present THEN 1::bigint
                    ELSE NULL::bigint
                END AS target_generation,
                CASE
                    WHEN target_present THEN 1::bigint
                    ELSE NULL::bigint
                END AS target_d1,
                CASE
                    WHEN expected_version_present THEN 1::bigint
                    ELSE NULL::bigint
                END AS expected_version,
                'accepted'::text AS ledger_kind,
                '{{}}'::jsonb AS payload
            FROM case_flags
        )
        SELECT
            event_kind,
            is_tombstone,
            d2_present,
            state_diff_present,
            target_present,
            expected_version_present,
            ({legacy_checks}) IS NOT FALSE AS legacy_passes,
            ({c12_checks}) IS NOT FALSE AS c12_passes
        FROM cases
        ORDER BY 1, 2, 3, 4, 5, 6
        """
    ).format(
        value_rows=value_rows,
        legacy_checks=_trusted_sql(_check_conjunction(_LEGACY_CHECK_EXPRESSIONS)),
        c12_checks=_trusted_sql(_check_conjunction(_ORM_CHECK_EXPRESSIONS)),
    )
    parameters: list[object] = [
        item
        for case in cases
        for item in (
            case.event_kind,
            case.is_tombstone,
            case.d2_present,
            case.state_diff_present,
            case.target_present,
            case.expected_version_present,
        )
    ]
    parameters.extend((list(CHANGE_EVENT_KIND_LITERALS),) * 2)
    cursor.execute(query, parameters)
    return {
        _TruthCase(
            str(event_kind),
            bool(is_tombstone),
            bool(d2_present),
            bool(state_diff_present),
            bool(target_present),
            bool(expected_version_present),
        ): (bool(legacy_passes), bool(c12_passes))
        for (
            event_kind,
            is_tombstone,
            d2_present,
            state_diff_present,
            target_present,
            expected_version_present,
            legacy_passes,
            c12_passes,
        ) in cursor.fetchall()
    }


def _applicable_participations(
    case: _TruthCase,
) -> tuple[OperationEventParticipation, ...]:
    """物理行が満たす C12 行述語を参加区分の宣言から導く。"""
    applicable: list[OperationEventParticipation] = []
    for participation in OPERATION_EVENT_PARTICIPATIONS:
        if participation.binding is ParticipationBinding.TOMBSTONE_STATE:
            if case.is_tombstone:
                applicable.append(participation)
            continue
        if participation.event_kind_literal != case.event_kind:
            continue
        if (
            participation.event_kind_literal in CHANGE_EVENT_KIND_LITERALS
            or not case.is_tombstone
        ):
            applicable.append(participation)
    return tuple(applicable)


def _value_is_present(case: _TruthCase, value: C12Value) -> bool:
    """真理値表 1 行について C12 値の担い手が存在するか返す。"""
    if value in {C12Value.V2, C12Value.V3}:
        return case.event_kind not in CHANGE_EVENT_KIND_LITERALS
    if value is C12Value.V6:
        return case.d2_present
    if value is C12Value.V8:
        return case.state_diff_present
    if value is C12Value.V9:
        return case.is_tombstone
    if value is C12Value.V10:
        return case.target_present
    return case.expected_version_present


def _violated_matrix_cells(case: _TruthCase) -> tuple[C12Cell, ...]:
    """真理値表の行が違反する強制可能なセルをマトリクスから返す。"""
    violations: list[C12Cell] = []
    for participation in _applicable_participations(case):
        for value in C12Value:
            cell = C12_REQUIREMENT_MATRIX[(participation.participation_number, value)]
            present = _value_is_present(case, value)
            if (
                cell.requirement is C12Requirement.REQUIRED
                and not present
                or cell.requirement is C12Requirement.FORBIDDEN
                and present
            ):
                violations.append(cell)
    return tuple(violations)


def _matrix_accepts(case: _TruthCase) -> bool:
    """手書きの期待行を持たず、84 セルの意図だけから新式の期待を返す。"""
    return not _violated_matrix_cells(case)


def _format_truth_table_diff(
    legacy_only: set[_TruthCase], c12_only: set[_TruthCase]
) -> str:
    """対称差を PR 本文へ貼れる Markdown 表にする。"""
    lines = [
        "|方向|event_kind|tombstone|d2|state_diff|target_*|expected_version|",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for direction, rows in (
        ("旧のみ", legacy_only),
        ("新のみ", c12_only),
    ):
        lines.extend(
            "|{}|{}|{}|{}|{}|{}|{}|".format(
                direction,
                case.event_kind,
                int(case.is_tombstone),
                int(case.d2_present),
                int(case.state_diff_present),
                int(case.target_present),
                int(case.expected_version_present),
            )
            for case in sorted(rows)
        )
    return "\n".join(lines)


def _catalog_named_checks(
    cursor: psycopg.Cursor[Any], names: Iterable[str]
) -> dict[str, str]:
    """操作イベントの指定 CHECK 名と PostgreSQL 正規化済み式を返す。"""
    name_list = sorted(names)
    cursor.execute(
        """
        SELECT conname, pg_get_expr(conbin, conrelid, true)
        FROM pg_constraint
        WHERE conrelid = 'operation_events'::regclass
          AND contype = 'c'
          AND conname = ANY(%s)
        ORDER BY conname
        """,
        (name_list,),
    )
    return {str(name): str(expression) for name, expression in cursor.fetchall()}


def _catalog_all_check_expressions(cursor: psycopg.Cursor[Any]) -> set[str]:
    """操作イベントの CHECK 全式を PostgreSQL の正規形で返す。"""
    cursor.execute(
        """
        SELECT pg_get_expr(conbin, conrelid, true)
        FROM pg_constraint
        WHERE conrelid = 'operation_events'::regclass
          AND contype = 'c'
        """
    )
    return {str(row[0]) for row in cursor.fetchall()}


def _postgres_normalized_checks(
    cursor: psycopg.Cursor[Any], checks: Mapping[str, str]
) -> dict[str, str]:
    """期待式を一時表で PostgreSQL 自身にパースさせて正規化する。"""
    cursor.execute("DROP TABLE IF EXISTS c12_expected_checks")
    cursor.execute(
        """
        CREATE TEMP TABLE c12_expected_checks (
            ledger_kind text,
            event_kind text,
            d1 bigint,
            generation bigint,
            d2 bigint,
            state_diff jsonb,
            is_tombstone boolean,
            payload jsonb,
            target_generation bigint,
            target_d1 bigint,
            expected_version bigint
        )
        """
    )
    try:
        for name, expression in checks.items():
            cursor.execute(
                sql.SQL(
                    "ALTER TABLE c12_expected_checks ADD CONSTRAINT {} CHECK ({})"
                ).format(sql.Identifier(name), _trusted_sql(expression))
            )
        cursor.execute(
            """
            SELECT conname, pg_get_expr(conbin, conrelid, true)
            FROM pg_constraint
            WHERE conrelid = 'c12_expected_checks'::regclass
              AND contype = 'c'
            ORDER BY conname
            """
        )
        return {str(name): str(expression) for name, expression in cursor.fetchall()}
    finally:
        cursor.execute("DROP TABLE c12_expected_checks")


def _assert_head_check_contract(cursor: psycopg.Cursor[Any]) -> None:
    """Head の 5 本が ORM の生成式と exact-set 一致すると示す。"""
    assert _catalog_named_checks(cursor, _CONNECTED_C12_CHECKS) == (
        _postgres_normalized_checks(cursor, _CONNECTED_C12_CHECKS)
    )


def test_c12_truth_table_and_migration_round_trip(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N-8 の 288 行、CHECK 全文、0026 の downgrade・upgrade を検査する。"""
    cases = _truth_cases()
    assert len(cases) == 9 * 2 * 2 * 2 * 2 * 2 == 288

    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        config = _alembic_config()
        command.upgrade(config, "head")

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _assert_head_check_contract(cursor)
                expected_unnamed = set(
                    _postgres_normalized_checks(
                        cursor,
                        {
                            f"ck_expected_unnamed_{number}": expression
                            for number, expression in enumerate(_UNNAMED_0005_CHECKS)
                        },
                    ).values()
                )
                assert expected_unnamed <= _catalog_all_check_expressions(cursor)

                evaluations = _evaluate_truth_table(cursor, cases)
                matrix_outcomes = {case: _matrix_accepts(case) for case in cases}
                actual_legacy_only = {
                    case
                    for case, (legacy, c12) in evaluations.items()
                    if legacy and not c12
                }
                actual_c12_only = {
                    case
                    for case, (legacy, c12) in evaluations.items()
                    if c12 and not legacy
                }
                # 期待行は書き下さない。旧集合は PostgreSQL の旧式評価、新集合は
                # 84 セルの要求区分から導き、その集合差だけを期待値とする。
                expected_legacy_only = {
                    case
                    for case, (legacy, _) in evaluations.items()
                    if legacy and not matrix_outcomes[case]
                }
                expected_c12_only = {
                    case
                    for case, (legacy, _) in evaluations.items()
                    if not legacy and matrix_outcomes[case]
                }
                report = _format_truth_table_diff(actual_legacy_only, actual_c12_only)
                print(f"\nC12 N-8 対称差 ({len(cases)} 行評価)\n{report}")

                assert {case for case, (_, c12) in evaluations.items() if c12} == {
                    case for case, accepts in matrix_outcomes.items() if accepts
                }
                assert actual_legacy_only == expected_legacy_only
                assert actual_c12_only == expected_c12_only
                assert actual_legacy_only
                assert actual_c12_only
                assert all(_violated_matrix_cells(case) for case in actual_legacy_only)
                assert all(
                    case.event_kind == PLAY_INPUT_EVENT_KIND and case.is_tombstone
                    for case in actual_c12_only
                )

            command.downgrade(config, _PARENT_REVISION)
            with connection.cursor() as cursor:
                assert _catalog_named_checks(
                    cursor,
                    set(_CONNECTED_C12_CHECKS) | set(_LEGACY_NAMED_CHECKS),
                ) == _postgres_normalized_checks(cursor, _LEGACY_NAMED_CHECKS)
                assert expected_unnamed <= _catalog_all_check_expressions(cursor)

            command.upgrade(config, _REVISION)
            with connection.cursor() as cursor:
                _assert_head_check_contract(cursor)
                assert expected_unnamed <= _catalog_all_check_expressions(cursor)

        command.current(config, check_heads=True)
        command.check(config)


def _cell_test_id(cell: C12Cell) -> str:
    """自動展開したセル負例へ安定した pytest ID を付ける。"""
    return (
        f"p{cell.participation.participation_number}-"
        f"{cell.value.value}-{cell.requirement.value}"
    )


def _violating_cell_row(cell: C12Cell) -> dict[str, object | None]:
    """対象セルの行述語を真にし、担い手だけを要求と逆にした行を作る。"""
    participation = cell.participation
    is_tombstone = participation.binding is ParticipationBinding.TOMBSTONE_STATE
    event_kind = participation.event_kind_literal or PLAY_INPUT_EVENT_KIND
    row: dict[str, object | None] = {
        "event_kind": event_kind,
        "is_tombstone": is_tombstone,
        "payload": Jsonb({}),
        "d1": None,
        "generation": None,
        "d2": None,
        "state_diff": None,
        "target_generation": None,
        "target_d1": None,
        "expected_version": None,
    }
    make_present = cell.requirement is C12Requirement.FORBIDDEN
    for column in cell.carrier_columns:
        if column == "is_tombstone":
            row[column] = make_present
        elif column == "state_diff":
            row[column] = Jsonb({}) if make_present else None
        else:
            row[column] = 1 if make_present else None
    return row


@pytest.mark.parametrize("cell", _ENFORCEABLE_CELLS, ids=_cell_test_id)
def test_each_enforceable_c12_cell_violation_is_rejected_by_postgresql(
    admin_connection: psycopg.Connection[Any], cell: C12Cell
) -> None:
    """必須・禁止セルを機械展開し、対応する名前付き CHECK だけで拒否する。"""
    expression = c12_cell_check_expression(cell)
    assert expression is not None
    assert expression in C12_CHECK_EXPRESSIONS[cell.value]
    constraint_name = _CONNECTED_CONSTRAINT_BY_VALUE.get(
        cell.value, f"ck_c12_{cell.value.value.lower()}_cell_probe"
    )
    check_expression = (
        _CONNECTED_C12_CHECKS[constraint_name]
        if cell.value in _CONNECTED_CONSTRAINT_BY_VALUE
        else C12_CHECK_EXPRESSIONS[cell.value]
    )
    assert C12_CHECK_EXPRESSIONS[cell.value] in check_expression
    row = _violating_cell_row(cell)
    with admin_connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS c12_cell_violation_probe")
        cursor.execute(
            """
            CREATE TEMP TABLE c12_cell_violation_probe (
                event_kind text,
                is_tombstone boolean,
                payload jsonb,
                d1 bigint,
                generation bigint,
                d2 bigint,
                state_diff jsonb,
                target_generation bigint,
                target_d1 bigint,
                expected_version bigint
            )
            """
        )
        try:
            # 対応する 1 本だけを一時表へ載せ、別 CHECK による偶然の拒否を許さない。
            cursor.execute(
                sql.SQL(
                    "ALTER TABLE c12_cell_violation_probe ADD CONSTRAINT {} CHECK ({})"
                ).format(
                    sql.Identifier(constraint_name),
                    _trusted_sql(check_expression),
                )
            )
            with pytest.raises(
                psycopg.errors.CheckViolation,
                match=constraint_name,
            ) as error:
                cursor.execute(
                    """
                    INSERT INTO c12_cell_violation_probe (
                        event_kind,
                        is_tombstone,
                        payload,
                        d1,
                        generation,
                        d2,
                        state_diff,
                        target_generation,
                        target_d1,
                        expected_version
                    ) VALUES (
                        %(event_kind)s,
                        %(is_tombstone)s,
                        %(payload)s,
                        %(d1)s,
                        %(generation)s,
                        %(d2)s,
                        %(state_diff)s,
                        %(target_generation)s,
                        %(target_d1)s,
                        %(expected_version)s
                    )
                    """,
                    row,
                )
            assert error.value.sqlstate == "23514"
        finally:
            cursor.execute("DROP TABLE c12_cell_violation_probe")
