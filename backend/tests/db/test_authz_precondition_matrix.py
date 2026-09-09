"""共有 6 前提と認可行列 allow セルの直積を越境検証する。

母集合は ``shared-preconditions.json`` と ``http-route-matrix.json`` から導出し、
このモジュールに明記した disposition 表とは独立に照合する。probe にテナント
有効性の表がないセルと、選手の在籍区分を表す列がないことは ``TSK-344`` へ
引き渡す。チーム集計に在籍フィルタを掛けない要求は、probe に当該フィルタが
存在しない事実と矛盾しない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal

import psycopg
import pytest

from .conftest import ProvisionedCatalog
from .test_authz_runtime_positive import (
    _POSITIVE_CASES,
    _BusinessFixtureRow,
    _expected_rows,
    _fetch_authorized_shared_rows,
    _grant_rows,
    _identifier_set_digest,
    _insert_runtime_fixture,
    _object_rows,
    _PositiveCase,
    _PositiveRuntimeFixture,
    _ProbeInvocation,
    _read_json_object,
    _ReturnedRow,
    _runtime_fixture_definition,
    _string,
)

pytestmark = pytest.mark.requires_db

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SHARED_PRECONDITIONS_PATH = (
    _REPOSITORY_ROOT / "contracts/authz/shared-preconditions.json"
)
_HTTP_ROUTE_MATRIX_PATH = _REPOSITORY_ROOT / "contracts/authz/http-route-matrix.json"
_DDL_ELEMENTS_PATH = _REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
_REQUIREMENT_CLAIMS_PATH = _REPOSITORY_ROOT / "contracts/authz/requirement-claims.json"
_AUTHORIZED_SHARED_ROWS_PATH = (
    _REPOSITORY_ROOT
    / "contracts/authz/function-bodies/functions/authorized_shared_rows.sql"
)

_NORMAL_KIND = "通常"
_EXCEPTION_KIND = "例外"
_PROBE_EXECUTABLE = "probe_executable"
_UNREPRESENTABLE = "unrepresentable_in_probe"
_RECEIVING_TASK_ID = "TSK-344"
_TENANT_ACTIVE_MARKER = "-- UNCHECKABLE-PRECONDITION: BOTH_TENANTS_ACTIVE"
_TENANT_ACTIVE_REASON = (
    "authorized_shared_rows.sql の "
    "-- UNCHECKABLE-PRECONDITION: BOTH_TENANTS_ACTIVE が記録する通り、"
    "probe スキーマにテナント有効性を保持する表がない"
)
_COMPARISON_LIMIT_SOURCE_ID = "APPENDIX-C/table_row-010"
_COMPARISON_LIMIT_ROW_RE = re.compile(
    r"^\|\s*共同分析グループの同時比較表示上限\s*\|"
    r"\s*(?P<limit>[1-9][0-9]*)\s*\|"
)

_TEAM_METRICS_SCREEN = "CELL:shared_screen:team_metrics:screen"
_TEAM_SUMMARY_SCREEN = "CELL:shared_screen:team_summary:screen"
_PLAYER_METRICS_SCREEN = "CELL:shared_screen:player_metrics:screen"
_TEAM_METRICS_EXPORT = "CELL:shared_aggregate_export:team_metrics:export"
_TEAM_SUMMARY_EXPORT = "CELL:shared_aggregate_export:team_summary:export"
_PLAYER_METRICS_EXPORT = "CELL:shared_aggregate_export:player_metrics:export"

_REQUESTER_MEMBERSHIP_INACTIVE = "requester_membership_inactive"
_TARGET_MEMBERSHIP_INACTIVE = "target_membership_inactive"
_RECIPROCITY_NEGATIVE_SCENARIO = "requester_grant_incomplete"
_TARGET_NONSHARED_SCENARIO = "target_grant_incomplete"
_SELF_EXCEPTION_APPLIED = "self_tenant_exception_applied"
_SELF_EXCEPTION_OVER_LIMIT = "self_tenant_exception_counts_toward_limit"
_COMPARISON_LIMIT_EXCEEDED = "comparison_limit_exceeded"

_Disposition = Literal["probe_executable", "unrepresentable_in_probe"]


@dataclass(frozen=True, slots=True)
class _SharedPrecondition:
    """ステップ 9 資産から読んだ共有前提。"""

    precondition_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class _DispositionRow:
    """前提と allow セルの交点に対する閉じた disposition。"""

    crossing_id: str
    precondition_id: str
    allow_cell_id: str
    kind: str
    disposition: _Disposition
    test_id: str | None
    reason: str | None
    receiving_task_id: str | None


@dataclass(frozen=True, slots=True)
class _ProbeConceptRule:
    """前提を表現するため probe スキーマに必要な概念表。"""

    required_table_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ExecutableCase:
    """実行可能 disposition とステップ 7 の allow case の結合。"""

    disposition: _DispositionRow
    allow_case: _PositiveCase

    @property
    def test_id(self) -> str:
        """Pytest パラメータにも使う論理テスト ID を返す。"""
        if self.disposition.test_id is None:
            raise AssertionError("実行可能セルに test_id がない")
        return self.disposition.test_id


@dataclass(frozen=True, slots=True)
class _ProbeGapHandoff:
    """probe スキーマでは表現できない行フィルタの引き渡し記録。"""

    gap_id: str
    evidence_table_id: str
    reason: str
    receiving_task_id: str
    team_aggregation_note: str


def _crossing_id(precondition_id: str, allow_cell_id: str) -> str:
    """前提と allow セルから順序非依存照合用 ID を作る。"""
    return f"{precondition_id}|{allow_cell_id}"


def _executable(
    precondition_id: str,
    kind: str,
    allow_cell_id: str,
) -> _DispositionRow:
    """明記した交点を probe 実行可能 disposition にする。"""
    crossing_id = _crossing_id(precondition_id, allow_cell_id)
    return _DispositionRow(
        crossing_id=crossing_id,
        precondition_id=precondition_id,
        allow_cell_id=allow_cell_id,
        kind=kind,
        disposition=_PROBE_EXECUTABLE,
        test_id=crossing_id,
        reason=None,
        receiving_task_id=None,
    )


def _unrepresentable(
    precondition_id: str,
    kind: str,
    allow_cell_id: str,
) -> _DispositionRow:
    """明記した交点を probe 表現不能 disposition にする。"""
    return _DispositionRow(
        crossing_id=_crossing_id(precondition_id, allow_cell_id),
        precondition_id=precondition_id,
        allow_cell_id=allow_cell_id,
        kind=kind,
        disposition=_UNREPRESENTABLE,
        test_id=None,
        reason=_TENANT_ACTIVE_REASON,
        receiving_task_id=_RECEIVING_TASK_ID,
    )


# 母集合とは別に列挙する。資産側の前提または allow 行が落ちても、この表は縮まない。
_DISPOSITION_TABLE: Final[tuple[_DispositionRow, ...]] = (
    _executable("shared_group_active", _NORMAL_KIND, _TEAM_METRICS_SCREEN),
    _executable("shared_group_active", _NORMAL_KIND, _TEAM_SUMMARY_SCREEN),
    _executable("shared_group_active", _NORMAL_KIND, _PLAYER_METRICS_SCREEN),
    _executable("shared_group_active", _NORMAL_KIND, _TEAM_METRICS_EXPORT),
    _executable("shared_group_active", _NORMAL_KIND, _TEAM_SUMMARY_EXPORT),
    _executable("shared_group_active", _NORMAL_KIND, _PLAYER_METRICS_EXPORT),
    _executable("shared_both_memberships_active", _NORMAL_KIND, _TEAM_METRICS_SCREEN),
    _executable("shared_both_memberships_active", _NORMAL_KIND, _TEAM_SUMMARY_SCREEN),
    _executable("shared_both_memberships_active", _NORMAL_KIND, _PLAYER_METRICS_SCREEN),
    _executable("shared_both_memberships_active", _NORMAL_KIND, _TEAM_METRICS_EXPORT),
    _executable("shared_both_memberships_active", _NORMAL_KIND, _TEAM_SUMMARY_EXPORT),
    _executable("shared_both_memberships_active", _NORMAL_KIND, _PLAYER_METRICS_EXPORT),
    _unrepresentable("shared_both_tenants_enabled", _NORMAL_KIND, _TEAM_METRICS_SCREEN),
    _unrepresentable("shared_both_tenants_enabled", _NORMAL_KIND, _TEAM_SUMMARY_SCREEN),
    _unrepresentable(
        "shared_both_tenants_enabled", _NORMAL_KIND, _PLAYER_METRICS_SCREEN
    ),
    _unrepresentable("shared_both_tenants_enabled", _NORMAL_KIND, _TEAM_METRICS_EXPORT),
    _unrepresentable("shared_both_tenants_enabled", _NORMAL_KIND, _TEAM_SUMMARY_EXPORT),
    _unrepresentable(
        "shared_both_tenants_enabled", _NORMAL_KIND, _PLAYER_METRICS_EXPORT
    ),
    _executable("shared_reciprocal_grant", _NORMAL_KIND, _TEAM_METRICS_SCREEN),
    _executable("shared_reciprocal_grant", _NORMAL_KIND, _TEAM_SUMMARY_SCREEN),
    _executable("shared_reciprocal_grant", _NORMAL_KIND, _PLAYER_METRICS_SCREEN),
    _executable("shared_reciprocal_grant", _NORMAL_KIND, _TEAM_METRICS_EXPORT),
    _executable("shared_reciprocal_grant", _NORMAL_KIND, _TEAM_SUMMARY_EXPORT),
    _executable("shared_reciprocal_grant", _NORMAL_KIND, _PLAYER_METRICS_EXPORT),
    _executable("shared_self_tenant_exception", _EXCEPTION_KIND, _TEAM_METRICS_SCREEN),
    _executable("shared_self_tenant_exception", _EXCEPTION_KIND, _TEAM_SUMMARY_SCREEN),
    _executable(
        "shared_self_tenant_exception", _EXCEPTION_KIND, _PLAYER_METRICS_SCREEN
    ),
    _executable("shared_self_tenant_exception", _EXCEPTION_KIND, _TEAM_METRICS_EXPORT),
    _executable("shared_self_tenant_exception", _EXCEPTION_KIND, _TEAM_SUMMARY_EXPORT),
    _executable(
        "shared_self_tenant_exception", _EXCEPTION_KIND, _PLAYER_METRICS_EXPORT
    ),
    _executable("shared_comparison_limit", _NORMAL_KIND, _TEAM_METRICS_SCREEN),
    _executable("shared_comparison_limit", _NORMAL_KIND, _TEAM_SUMMARY_SCREEN),
    _executable("shared_comparison_limit", _NORMAL_KIND, _PLAYER_METRICS_SCREEN),
    _executable("shared_comparison_limit", _NORMAL_KIND, _TEAM_METRICS_EXPORT),
    _executable("shared_comparison_limit", _NORMAL_KIND, _TEAM_SUMMARY_EXPORT),
    _executable("shared_comparison_limit", _NORMAL_KIND, _PLAYER_METRICS_EXPORT),
)

# 判定根拠は body の実装有無ではなく、前提の状態概念を表す表が probe にあるか。
# 同時比較上限は要求配列そのものの性質なので、永続状態を表す概念表を必要としない。
_PROBE_CONCEPT_RULES: Final[dict[str, _ProbeConceptRule]] = {
    "shared_group_active": _ProbeConceptRule(frozenset({"probe_groups"})),
    "shared_both_memberships_active": _ProbeConceptRule(
        frozenset({"probe_memberships"})
    ),
    "shared_both_tenants_enabled": _ProbeConceptRule(frozenset({"probe_tenants"})),
    "shared_reciprocal_grant": _ProbeConceptRule(frozenset({"probe_grants"})),
    "shared_self_tenant_exception": _ProbeConceptRule(
        frozenset(
            {
                "probe_business_rows",
                "probe_groups",
                "probe_memberships",
                "probe_grants",
            }
        )
    ),
    "shared_comparison_limit": _ProbeConceptRule(frozenset()),
}

_PLAYER_ACTIVE_FILTER_HANDOFF = _ProbeGapHandoff(
    gap_id="player_individual_active_membership_filter",
    evidence_table_id="probe_business_rows",
    reason=(
        "probe_business_rows は tenant_id・resource_kind・ownership_kind・payload "
        "だけを持ち、選手の在籍区分を保持する列がないため probe では表現できない"
    ),
    receiving_task_id=_RECEIVING_TASK_ID,
    team_aggregation_note=(
        "probe に在籍フィルタが存在しないことは、チーム集計へ在籍フィルタを"
        "掛けない要求と矛盾しない"
    ),
)


def _load_preconditions() -> tuple[_SharedPrecondition, ...]:
    """ステップ 9 資産の前提次元を読む。

    Returns:
        資産順の共有前提。
    """
    asset = _read_json_object(_SHARED_PRECONDITIONS_PATH)
    rows = _object_rows(
        asset.get("preconditions"), "shared-preconditions.preconditions"
    )
    preconditions = tuple(
        _SharedPrecondition(
            precondition_id=_string(
                row.get("precondition_id"), "preconditions.precondition_id"
            ),
            kind=_string(row.get("kind"), "preconditions.kind"),
        )
        for row in rows
    )
    ids = tuple(row.precondition_id for row in preconditions)
    if len(ids) != len(set(ids)):
        raise AssertionError("precondition_id が重複している")
    if {row.kind for row in preconditions} != {_NORMAL_KIND, _EXCEPTION_KIND}:
        raise AssertionError("共有前提の kind が閉じていない")
    return preconditions


def _load_allow_cell_ids() -> tuple[str, ...]:
    """HTTP 判定値に触れず、認可行列の allow セル次元だけを読む。

    Returns:
        ``expected_result == allow`` のセル ID。
    """
    asset = _read_json_object(_HTTP_ROUTE_MATRIX_PATH)
    cells = _object_rows(asset.get("cells"), "http-route-matrix.cells")
    allow_cell_ids = tuple(
        _string(cell.get("cell_id"), "allow cell_id")
        for cell in cells
        if cell.get("expected_result") == "allow"
    )
    if len(allow_cell_ids) != len(set(allow_cell_ids)):
        raise AssertionError("allow cell_id が重複している")
    return allow_cell_ids


def _derive_mother_universe(
    preconditions: tuple[_SharedPrecondition, ...],
    allow_cell_ids: tuple[str, ...],
) -> frozenset[str]:
    """2 資産の次元から直積母集合を導出する。

    Args:
        preconditions: ステップ 9 資産から読んだ前提行。
        allow_cell_ids: HTTP 認可行列から読んだ allow セル ID。

    Returns:
        前提 ID と allow セル ID の直積。
    """
    return frozenset(
        _crossing_id(precondition.precondition_id, allow_cell_id)
        for precondition in preconditions
        for allow_cell_id in allow_cell_ids
    )


def _probe_table_ids() -> frozenset[str]:
    """DDL 資産の ``tables`` から probe の表 ID 集合を導出する。"""
    asset = _read_json_object(_DDL_ELEMENTS_PATH)
    rows = _object_rows(asset.get("tables"), "ddl-elements.tables")
    table_ids = tuple(
        _string(row.get("table_id"), "ddl-elements.tables.table_id") for row in rows
    )
    if len(table_ids) != len(set(table_ids)):
        raise AssertionError("probe table_id が重複している")
    return frozenset(table_ids)


def _schema_disposition(
    precondition_id: str, probe_table_ids: frozenset[str]
) -> _Disposition:
    """必要な概念表が probe スキーマにあるかだけで disposition を決める。"""
    try:
        rule = _PROBE_CONCEPT_RULES[precondition_id]
    except KeyError as error:
        raise AssertionError(
            f"probe 概念表の判定規則がない: {precondition_id}"
        ) from error
    if rule.required_table_ids.issubset(probe_table_ids):
        return _PROBE_EXECUTABLE
    return _UNREPRESENTABLE


def _assert_same_identifier_set(
    actual: frozenset[str], expected: frozenset[str], label: str
) -> None:
    """識別子集合を値と SHA-256 の双方で exact-set 比較する。"""
    if actual != expected or _identifier_set_digest(
        set(actual)
    ) != _identifier_set_digest(set(expected)):
        raise AssertionError(f"{label} が sha256 exact-set 一致しない")


def _assert_disposition_contract(
    preconditions: tuple[_SharedPrecondition, ...],
    allow_cell_ids: tuple[str, ...],
    rows: tuple[_DispositionRow, ...],
) -> None:
    """直積・disposition・論理テスト ID の閉包を検査する。"""
    mother_universe = _derive_mother_universe(preconditions, allow_cell_ids)
    row_ids = tuple(row.crossing_id for row in rows)
    if len(row_ids) != len(set(row_ids)):
        raise AssertionError("disposition 表の crossing_id が重複している")
    _assert_same_identifier_set(frozenset(row_ids), mother_universe, "disposition 表")

    precondition_by_id = {row.precondition_id: row for row in preconditions}
    probe_table_ids = _probe_table_ids()
    if frozenset(_PROBE_CONCEPT_RULES) != frozenset(precondition_by_id):
        raise AssertionError("probe 概念表の判定規則が前提 ID と exact-set 一致しない")

    executable_ids: set[str] = set()
    unrepresentable_ids: set[str] = set()
    test_ids: set[str] = set()
    for row in rows:
        source = precondition_by_id.get(row.precondition_id)
        if source is None or row.allow_cell_id not in allow_cell_ids:
            raise AssertionError(
                f"disposition 表に母集合外の交点がある: {row.crossing_id}"
            )
        if row.kind != source.kind:
            raise AssertionError(
                f"kind がステップ 9 資産と一致しない: {row.crossing_id}"
            )
        expected_disposition = _schema_disposition(row.precondition_id, probe_table_ids)
        if row.disposition != expected_disposition:
            raise AssertionError(
                f"probe の概念表から導出した disposition と違う: {row.crossing_id}"
            )
        if row.disposition == _PROBE_EXECUTABLE:
            if row.test_id != row.crossing_id:
                raise AssertionError(
                    f"実行可能セルに論理テスト ID がない: {row.crossing_id}"
                )
            if row.reason is not None or row.receiving_task_id is not None:
                raise AssertionError(
                    f"実行可能セルに引き渡し情報がある: {row.crossing_id}"
                )
            executable_ids.add(row.crossing_id)
            test_ids.add(row.test_id)
        elif row.disposition == _UNREPRESENTABLE:
            if row.test_id is not None:
                raise AssertionError(
                    f"表現不能セルがテスト ID を持つ: {row.crossing_id}"
                )
            if (
                not row.reason
                or _TENANT_ACTIVE_MARKER.removeprefix("-- ") not in row.reason
            ):
                raise AssertionError(
                    f"表現不能セルの理由が body 注記を引かない: {row.crossing_id}"
                )
            if row.receiving_task_id != _RECEIVING_TASK_ID:
                raise AssertionError(
                    f"表現不能セルの受け取り先が違う: {row.crossing_id}"
                )
            unrepresentable_ids.add(row.crossing_id)
        else:
            raise AssertionError(f"未知の disposition: {row.crossing_id}")

    _assert_same_identifier_set(
        frozenset(test_ids), frozenset(executable_ids), "実行可能セルのテスト ID"
    )
    _assert_same_identifier_set(
        frozenset(test_ids | unrepresentable_ids),
        mother_universe,
        "テスト ID と表現不能セルによる母集合被覆",
    )
    body = _AUTHORIZED_SHARED_ROWS_PATH.read_text(encoding="utf-8")
    if _TENANT_ACTIVE_MARKER not in body:
        raise AssertionError("表現不能理由が引用する body 注記が実在しない")


def _comparison_limit() -> int:
    """要件 claim の付録 C 行から同時比較表示上限を導出する。"""
    asset = _read_json_object(_REQUIREMENT_CLAIMS_PATH)
    claims = _object_rows(asset.get("claims"), "requirement-claims.claims")
    matches = tuple(
        row for row in claims if row.get("source_id") == _COMPARISON_LIMIT_SOURCE_ID
    )
    try:
        (claim,) = matches
    except ValueError as error:
        raise AssertionError("同時比較表示上限の要件 claim が一意でない") from error
    source_text = _string(claim.get("source_text"), "comparison limit source_text")
    match = _COMPARISON_LIMIT_ROW_RE.match(source_text)
    if match is None:
        raise AssertionError("要件 claim から同時比較表示上限を導出できない")
    return int(match.group("limit"))


_PRECONDITIONS = _load_preconditions()
_ALLOW_CELL_IDS = _load_allow_cell_ids()
_MOTHER_UNIVERSE = _derive_mother_universe(_PRECONDITIONS, _ALLOW_CELL_IDS)
_assert_disposition_contract(_PRECONDITIONS, _ALLOW_CELL_IDS, _DISPOSITION_TABLE)


def _join_executable_cases() -> tuple[_ExecutableCase, ...]:
    """明記した実行可能セルをステップ 7 の allow case と結合する。"""
    positive_by_cell = {case.cell_id: case for case in _POSITIVE_CASES}
    _assert_same_identifier_set(
        frozenset(positive_by_cell), frozenset(_ALLOW_CELL_IDS), "allow case"
    )
    return tuple(
        _ExecutableCase(row, positive_by_cell[row.allow_cell_id])
        for row in _DISPOSITION_TABLE
        if row.disposition == _PROBE_EXECUTABLE
    )


_EXECUTABLE_CASES = _join_executable_cases()
_NORMAL_CASES = tuple(
    case for case in _EXECUTABLE_CASES if case.disposition.kind == _NORMAL_KIND
)
_EXCEPTION_CASES = tuple(
    case for case in _EXECUTABLE_CASES if case.disposition.kind == _EXCEPTION_KIND
)


def _only(values: tuple[Any, ...], label: str) -> Any:
    """列から唯一の値を取得する。"""
    try:
        (value,) = values
    except ValueError as error:
        raise AssertionError(f"{label} を一意に導出できない") from error
    return value


def _invocation_by_exclusion(
    fixture: _PositiveRuntimeFixture, exclusion_kind: str
) -> _ProbeInvocation:
    """ステップ 7 fixture から呼び出し単位の拒否シナリオを選ぶ。"""
    return _only(
        tuple(
            invocation
            for invocation in fixture.invocations
            if invocation.exclusion_kind == exclusion_kind
        ),
        exclusion_kind,
    )


def _single_target_exclusion(
    fixture: _PositiveRuntimeFixture,
    exclusion_kind: str,
    invocation_id: str,
) -> _ProbeInvocation:
    """ステップ 7 fixture の行単位拒否を単独対象の呼び出しにする。"""
    business_row = _only(
        tuple(
            row for row in fixture.business_rows if row.exclusion_kind == exclusion_kind
        ),
        exclusion_kind,
    )
    source_invocation = _only(
        tuple(
            invocation
            for invocation in fixture.invocations
            if business_row.tenant_id in invocation.target_tenant_ids
        ),
        f"{exclusion_kind} の呼び出し",
    )
    return replace(
        source_invocation,
        invocation_id=invocation_id,
        target_tenant_ids=(business_row.tenant_id,),
        expected_rows=frozenset(),
        exclusion_kind=exclusion_kind,
    )


def _main_invocation(fixture: _PositiveRuntimeFixture) -> _ProbeInvocation:
    """対象側非共有行を含むステップ 7 の主呼び出しを得る。"""
    target_nonshared = _single_target_exclusion(
        fixture, _TARGET_NONSHARED_SCENARIO, _TARGET_NONSHARED_SCENARIO
    )
    return _only(
        tuple(
            invocation
            for invocation in fixture.invocations
            if invocation.group_id == target_nonshared.group_id
        ),
        "主呼び出し",
    )


def _authorized_target(fixture: _PositiveRuntimeFixture) -> _ReturnedRow:
    """主呼び出しの正当な対象行を期待集合から得る。"""
    return _only(tuple(_main_invocation(fixture).expected_rows), "正当な対象行")


def _next_group_id(fixture: _PositiveRuntimeFixture) -> int:
    """Fixture 内で未使用のグループ ID を返す。"""
    return max(group_id for group_id, _status in fixture.groups) + 1


def _over_limit_target_ids(
    fixture: _PositiveRuntimeFixture, included_tenant_id: int
) -> tuple[int, ...]:
    """要件資産由来の上限を一要素だけ超える対象集合を作る。"""
    requested_target_count = _comparison_limit() + 1
    all_tenant_ids = {row.tenant_id for row in fixture.business_rows} | {
        fixture.requester_tenant_id
    }
    next_tenant_id = max(all_tenant_ids) + 1
    filler_count = requested_target_count - len((included_tenant_id,))
    fillers = tuple(next_tenant_id + offset for offset in range(filler_count))
    target_tenant_ids = (included_tenant_id, *fillers)
    if len(target_tenant_ids) != requested_target_count:
        raise AssertionError("上限超過対象集合の要素数を導出できない")
    return target_tenant_ids


def _group_inactive_fixture(case: _PositiveCase) -> _PositiveRuntimeFixture:
    """グループ以外の前提を満たした inactive group シナリオを作る。"""
    fixture = _runtime_fixture_definition(case)
    invocation = _invocation_by_exclusion(fixture, "inactive_group")
    return replace(fixture, invocations=(invocation,))


def _memberships_inactive_fixture(case: _PositiveCase) -> _PositiveRuntimeFixture:
    """要求元・対象それぞれの参加だけを inactive にしたシナリオを作る。"""
    fixture = _runtime_fixture_definition(case)
    target_inactive = _single_target_exclusion(
        fixture,
        "inactive_membership",
        _TARGET_MEMBERSHIP_INACTIVE,
    )
    requester_inactive_group = _next_group_id(fixture)
    authorized_target = _authorized_target(fixture)
    requester_inactive = _ProbeInvocation(
        invocation_id=_REQUESTER_MEMBERSHIP_INACTIVE,
        group_id=requester_inactive_group,
        target_tenant_ids=(authorized_target.tenant_id,),
        expected_rows=frozenset(),
        exclusion_kind=_REQUESTER_MEMBERSHIP_INACTIVE,
    )
    required_grants = case.required_grant_kinds
    return replace(
        fixture,
        groups=(*fixture.groups, (requester_inactive_group, "active")),
        memberships=(
            *fixture.memberships,
            (
                requester_inactive_group,
                fixture.requester_tenant_id,
                "inactive",
                "member",
            ),
            (
                requester_inactive_group,
                authorized_target.tenant_id,
                "active",
                "member",
            ),
        ),
        grants=(
            *fixture.grants,
            *_grant_rows(
                requester_inactive_group,
                (fixture.requester_tenant_id, authorized_target.tenant_id),
                required_grants,
            ),
        ),
        invocations=(target_inactive, requester_inactive),
    )


def _enabled_grants(
    fixture: _PositiveRuntimeFixture, group_id: int, tenant_id: int
) -> frozenset[str]:
    """Fixture の指定グループ・テナントにある有効付与を得る。"""
    return frozenset(
        grant_kind
        for row_group_id, row_tenant_id, grant_kind, enabled in fixture.grants
        if row_group_id == group_id and row_tenant_id == tenant_id and enabled
    )


def _reciprocity_fixture(case: _PositiveCase) -> _PositiveRuntimeFixture:
    """相互性欠落と対象側非共有を別シナリオセルとして作る。"""
    fixture = _runtime_fixture_definition(case)
    requester_incomplete = _invocation_by_exclusion(
        fixture, _RECIPROCITY_NEGATIVE_SCENARIO
    )
    target_incomplete = _single_target_exclusion(
        fixture, _TARGET_NONSHARED_SCENARIO, _TARGET_NONSHARED_SCENARIO
    )
    requester_incomplete_target = _only(
        requester_incomplete.target_tenant_ids,
        "相互性欠落シナリオの対象",
    )
    target_incomplete_target = _only(
        target_incomplete.target_tenant_ids,
        "対象側非共有シナリオの対象",
    )
    required_grants = frozenset(case.required_grant_kinds)

    # 前提④は対象側が全付与・要求元が不足する組み合わせ。
    if (
        _enabled_grants(
            fixture, requester_incomplete.group_id, requester_incomplete_target
        )
        != required_grants
        or _enabled_grants(
            fixture, requester_incomplete.group_id, fixture.requester_tenant_id
        )
        == required_grants
    ):
        raise AssertionError("requester_grant_incomplete の組み合わせが崩れている")
    # 認可行列側は要求元が全付与・対象側が非共有の組み合わせ。
    if (
        _enabled_grants(
            fixture, target_incomplete.group_id, fixture.requester_tenant_id
        )
        != required_grants
        or _enabled_grants(
            fixture, target_incomplete.group_id, target_incomplete_target
        )
        == required_grants
    ):
        raise AssertionError("target_grant_incomplete の組み合わせが崩れている")
    if requester_incomplete.exclusion_kind == target_incomplete.exclusion_kind:
        raise AssertionError("相互性欠落と対象側非共有が同じシナリオセルになっている")
    return replace(
        fixture,
        invocations=(requester_incomplete, target_incomplete),
    )


def _comparison_limit_fixture(case: _PositiveCase) -> _PositiveRuntimeFixture:
    """他の前提を満たす行を含め、比較上限だけを超える要求を作る。"""
    fixture = _runtime_fixture_definition(case)
    main_invocation = _main_invocation(fixture)
    authorized_target = _authorized_target(fixture)
    over_limit = replace(
        main_invocation,
        invocation_id=_COMPARISON_LIMIT_EXCEEDED,
        target_tenant_ids=_over_limit_target_ids(fixture, authorized_target.tenant_id),
        expected_rows=frozenset(),
        exclusion_kind=_COMPARISON_LIMIT_EXCEEDED,
    )
    return replace(fixture, invocations=(over_limit,))


def _normal_fixture(executable_case: _ExecutableCase) -> _PositiveRuntimeFixture:
    """通常前提の ID に対応する単独不充足 fixture を選ぶ。"""
    precondition_id = executable_case.disposition.precondition_id
    case = executable_case.allow_case
    if precondition_id == "shared_group_active":
        return _group_inactive_fixture(case)
    if precondition_id == "shared_both_memberships_active":
        return _memberships_inactive_fixture(case)
    if precondition_id == "shared_reciprocal_grant":
        return _reciprocity_fixture(case)
    if precondition_id == "shared_comparison_limit":
        return _comparison_limit_fixture(case)
    raise AssertionError(
        f"probe 実行可能な通常前提の fixture がない: {precondition_id}"
    )


def _self_exception_fixture(case: _PositiveCase) -> _PositiveRuntimeFixture:
    """付与なしで自テナント例外を適用し、同時に上限計数も検査する。"""
    fixture = _runtime_fixture_definition(case)
    invocation_id = _SELF_EXCEPTION_APPLIED
    self_group = _next_group_id(fixture)
    # ステップ 7 が一つの代表セルだけに置いた自テナント行は除き、全 allow
    # セルを同じ一行の oracle で検査する。グループや付与の定義は再利用する。
    base_business_rows = tuple(
        row
        for row in fixture.business_rows
        if not (
            row.tenant_id == fixture.requester_tenant_id
            and row.resource_kind == case.resource_kind
            and row.ownership_kind == "self"
        )
    )
    self_row = _BusinessFixtureRow(
        tenant_id=fixture.requester_tenant_id,
        resource_kind=case.resource_kind,
        ownership_kind="self",
        marker=case.cell_id,
        expected_invocation_ids=frozenset({invocation_id}),
    )
    business_rows = (*base_business_rows, self_row)
    applied = _ProbeInvocation(
        invocation_id=invocation_id,
        group_id=self_group,
        target_tenant_ids=(fixture.requester_tenant_id,),
        expected_rows=_expected_rows(business_rows, invocation_id),
    )
    over_limit = replace(
        applied,
        invocation_id=_SELF_EXCEPTION_OVER_LIMIT,
        target_tenant_ids=_over_limit_target_ids(fixture, fixture.requester_tenant_id),
        expected_rows=frozenset(),
        exclusion_kind=_SELF_EXCEPTION_OVER_LIMIT,
    )
    if not applied.expected_rows:
        raise AssertionError("自テナント例外が適用される期待集合になっていない")
    return replace(
        fixture,
        groups=(*fixture.groups, (self_group, "active")),
        memberships=(
            *fixture.memberships,
            (self_group, fixture.requester_tenant_id, "active", "member"),
        ),
        business_rows=business_rows,
        invocations=(applied, over_limit),
    )


def _assert_fixture_results(
    connection: psycopg.Connection[Any],
    fixture: _PositiveRuntimeFixture,
) -> None:
    """ステップ 7 の呼び出し・正規化ヘルパで全期待集合を検査する。"""
    try:
        for invocation in fixture.invocations:
            actual = _fetch_authorized_shared_rows(connection, fixture, invocation)
            assert actual == invocation.expected_rows, invocation.invocation_id
    finally:
        connection.rollback()


def test_disposition_table_exactly_covers_asset_cartesian_product() -> None:
    """直積母集合を disposition と論理テスト ID が exact-set 被覆する。"""
    _assert_disposition_contract(_PRECONDITIONS, _ALLOW_CELL_IDS, _DISPOSITION_TABLE)
    assert _MOTHER_UNIVERSE


@pytest.mark.parametrize("dimension", ("preconditions", "allow_cells"))
def test_removing_one_source_dimension_row_is_red(dimension: str) -> None:
    """どちらかの入力資産から一行落ちると固定 disposition 表との照合が red になる。"""
    preconditions = _PRECONDITIONS
    allow_cell_ids = _ALLOW_CELL_IDS
    if dimension == "preconditions":
        _removed, *remaining = preconditions
        preconditions = tuple(remaining)
    elif dimension == "allow_cells":
        _removed, *remaining = allow_cell_ids
        allow_cell_ids = tuple(remaining)
    else:
        raise AssertionError(f"未知の母集合次元: {dimension}")
    with pytest.raises(AssertionError, match="exact-set"):
        _assert_disposition_contract(preconditions, allow_cell_ids, _DISPOSITION_TABLE)


def test_player_active_filter_gap_is_handed_to_product_schema_tests() -> None:
    """在籍区分列の不在と TSK-344 への引き渡しを資産へ接地する。"""
    asset = _read_json_object(_DDL_ELEMENTS_PATH)
    tables = _object_rows(asset.get("tables"), "ddl-elements.tables")
    table = _only(
        tuple(
            row
            for row in tables
            if row.get("table_id") == _PLAYER_ACTIVE_FILTER_HANDOFF.evidence_table_id
        ),
        "probe_business_rows",
    )
    row_shape_ids = frozenset(
        _string(value, "probe_business_rows.row_shape_ids")
        for value in table.get("row_shape_ids", [])
    )
    assert row_shape_ids == frozenset(
        {"tenant_id", "resource_kind", "ownership_kind", "payload"}
    )
    assert not any("status" in row_shape_id for row_shape_id in row_shape_ids)
    assert _PLAYER_ACTIVE_FILTER_HANDOFF.receiving_task_id == _RECEIVING_TASK_ID
    assert _PLAYER_ACTIVE_FILTER_HANDOFF.reason
    assert _PLAYER_ACTIVE_FILTER_HANDOFF.team_aggregation_note


@pytest.mark.parametrize(
    "executable_case",
    _NORMAL_CASES,
    ids=tuple(case.test_id for case in _NORMAL_CASES),
)
def test_normal_precondition_failure_excludes_element(
    executable_case: _ExecutableCase,
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """通常前提だけを崩すと、各 allow セルで該当要素が除外される。"""
    fixture = _normal_fixture(executable_case)
    if any(invocation.expected_rows for invocation in fixture.invocations):
        raise AssertionError("通常前提の不充足が除外期待になっていない")
    _insert_runtime_fixture(provisioned_catalog, fixture)
    _assert_fixture_results(app_role_connection, fixture)


@pytest.mark.parametrize(
    "executable_case",
    _EXCEPTION_CASES,
    ids=tuple(case.test_id for case in _EXCEPTION_CASES),
)
def test_self_tenant_exception_is_applied_and_counts_toward_limit(
    executable_case: _ExecutableCase,
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """自テナントは無付与でも返り、同時比較表示上限には数えられる。"""
    if executable_case.disposition.precondition_id != "shared_self_tenant_exception":
        raise AssertionError("例外テストへ通常前提が混入している")
    fixture = _self_exception_fixture(executable_case.allow_case)
    _insert_runtime_fixture(provisioned_catalog, fixture)
    _assert_fixture_results(app_role_connection, fixture)
