"""共有行読み取り関数の正例を実 PostgreSQL で検証する。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import psycopg
import pytest

from .conftest import ProvisionedCatalog

pytestmark = pytest.mark.requires_db

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_CLAIM_MUTANT_MAP_PATH = _REPOSITORY_ROOT / "contracts/authz/claim-mutant-map.json"
_HTTP_ROUTE_MATRIX_PATH = _REPOSITORY_ROOT / "contracts/authz/http-route-matrix.json"
_DDL_ELEMENTS_PATH = _REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
_AUTHORIZED_SHARED_ROWS_PATH = (
    _REPOSITORY_ROOT
    / "contracts/authz/function-bodies/functions/authorized_shared_rows.sql"
)
_POSITIVE_SCOPE_ID = "POSITIVE-CASE-SCOPE:ALL-ALLOW-CELLS"
_POSITIVE_POPULATION_RULE = "all_http_matrix_cells_with_expected_result_allow"
_POSITIVE_OWNER_PREFIX = "TSK-270.group2.runtime-positive."
_SELF_EXEMPTION_CELL_ID = "CELL:shared_screen:team_metrics:screen"

# 正本 3-6 節で接地済みの HTTP 語彙から probe 語彙への写像。
_HTTP_RESOURCE_TO_PROBE_GRANULARITY: Final[dict[str, str]] = {
    "team_metrics": "team_statistics",
    "team_summary": "team_overview",
    "player_metrics": "player_individual",
}
_HTTP_CHANNEL_TO_PROBE_SUFFIX: Final[dict[str, str]] = {
    "screen": "",
    "export": "_export",
}
_HTTP_GRANT_TO_PROBE_GRANT: Final[dict[str, str]] = {
    "metrics": "performance",
    "player": "player_individual",
    "export": "export",
}

_AUTHORIZATION_VALUES_RE = re.compile(
    r"authorization_matrix\s*\([^)]*\)\s*AS\s*\(\s*VALUES"
    r"(?P<rows>.*?)\)\s*,\s*request_context\s+AS",
    re.DOTALL,
)
_AUTHORIZATION_ROW_RE = re.compile(
    r"\(\s*'(?P<granularity>[a-z_]+)'::TEXT\s*,"
    r"\s*'(?P<resource_kind>[a-z_]+)'::TEXT\s*,"
    r"\s*ARRAY\[(?P<grant_kinds>[^]]*)\]::TEXT\[\]\s*\)",
    re.DOTALL,
)
_GRANT_KIND_RE = re.compile(r"'(?P<grant_kind>[a-z_]+)'")

_MAIN_INVOCATION = "main"
_NO_RECIPROCITY_INVOCATION = "requester_grant_incomplete"
_INACTIVE_GROUP_INVOCATION = "inactive_group"
_SELF_EXEMPTION_INVOCATION = "self_tenant_exemption"
_REQUIRED_EXCLUSION_KINDS: Final[frozenset[str]] = frozenset(
    {
        "outside_group",
        "inactive_membership",
        "target_grant_incomplete",
        "requester_grant_incomplete",
        "non_self_ownership",
        "inactive_group",
    }
)


@dataclass(frozen=True, slots=True)
class _ProbeAuthorization:
    """封印済み body の認可行列 1 行。"""

    resource_kind: str
    required_grant_kinds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PositiveCase:
    """HTTP allow セルを probe 呼び出しへ変換した正例。"""

    cell_id: str
    granularity: str
    resource_kind: str
    required_grant_kinds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReturnedRow:
    """関数の型付き返却行を exact-set 比較できる形で保持する。"""

    tenant_id: int
    resource_kind: str
    ownership_kind: str
    payload_json: str


@dataclass(frozen=True, slots=True)
class _BusinessFixtureRow:
    """業務行と、それを返すべき fixture 呼び出しを定義する。"""

    tenant_id: int
    resource_kind: str
    ownership_kind: str
    marker: str
    expected_invocation_ids: frozenset[str]
    exclusion_kind: str | None = None

    def returned_row(self) -> _ReturnedRow:
        """DB 出力と比較する期待行へ変換する。

        Returns:
            payload を正規化した期待行。
        """
        payload_json = json.dumps(
            {"fixture_row": self.marker},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return _ReturnedRow(
            tenant_id=self.tenant_id,
            resource_kind=self.resource_kind,
            ownership_kind=self.ownership_kind,
            payload_json=payload_json,
        )

    def database_row(self) -> tuple[int, str, str, str]:
        """INSERT 用の業務行を返す。

        Returns:
            ``probe_business_rows`` の列順に並べた値。
        """
        return (
            self.tenant_id,
            self.resource_kind,
            self.ownership_kind,
            json.dumps({"fixture_row": self.marker}, ensure_ascii=False),
        )


@dataclass(frozen=True, slots=True)
class _ProbeInvocation:
    """1 回の関数呼び出しと fixture 由来の期待集合。"""

    invocation_id: str
    group_id: int
    target_tenant_ids: tuple[int, ...]
    expected_rows: frozenset[_ReturnedRow]
    exclusion_kind: str | None = None


@dataclass(frozen=True, slots=True)
class _PositiveRuntimeFixture:
    """正例 1 セルを検査する DB fixture の全定義。"""

    requester_tenant_id: int
    granularity: str
    groups: tuple[tuple[int, str], ...]
    memberships: tuple[tuple[int, int, str, str], ...]
    grants: tuple[tuple[int, int, str, bool], ...]
    business_rows: tuple[_BusinessFixtureRow, ...]
    invocations: tuple[_ProbeInvocation, ...]


def _read_json_object(path: Path) -> dict[str, object]:
    """JSON object の凍結資産を読む。

    Args:
        path: 読み取る資産パス。

    Returns:
        JSON object。
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AssertionError(f"凍結資産を読めない: {path}: {error}") from error
    if not isinstance(value, dict):
        raise AssertionError(f"凍結資産がJSON objectでない: {path}")
    return value


def _object_rows(value: object, label: str) -> tuple[dict[str, object], ...]:
    """資産値を object 行列として検証する。

    Args:
        value: 検証対象の値。
        label: エラーに示す資産位置。

    Returns:
        順序を維持した object 行列。
    """
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise AssertionError(f"{label}はobject配列でなければならない")
    return tuple(row for row in value if isinstance(row, dict))


def _string(value: object, label: str) -> str:
    """資産値から空でない文字列を得る。

    Args:
        value: 検証対象の値。
        label: エラーに示す資産位置。

    Returns:
        空でない文字列。
    """
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{label}は空でない文字列でなければならない")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    """資産値から重複のない文字列列を得る。

    Args:
        value: 検証対象の値。
        label: エラーに示す資産位置。

    Returns:
        順序を維持した文字列列。
    """
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise AssertionError(f"{label}は空でない文字列の配列でなければならない")
    values = tuple(item for item in value if isinstance(item, str))
    if len(values) != len(set(values)):
        raise AssertionError(f"{label}に重複がある")
    return values


def _identifier_set_digest(values: set[str]) -> str:
    """識別子集合の順序非依存 digest を返す。

    Args:
        values: digest 化する識別子集合。

    Returns:
        ソート済み集合の SHA-256。
    """
    canonical = "\n".join(sorted(values)).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _authorization_matrix_from_body() -> dict[str, _ProbeAuthorization]:
    """封印済み関数 body の VALUES 節から認可行列を導出する。

    Returns:
        probe granularity から資源種別・必須付与への対応。
    """
    body = _AUTHORIZED_SHARED_ROWS_PATH.read_text(encoding="utf-8")
    values_match = _AUTHORIZATION_VALUES_RE.search(body)
    if values_match is None:
        raise AssertionError("authorized_shared_rows の authorization_matrix がない")
    values_source = values_match.group("rows")
    row_matches = tuple(_AUTHORIZATION_ROW_RE.finditer(values_source))
    if not row_matches:
        raise AssertionError("authorization_matrix の VALUES 行がない")
    unmatched_rows = _AUTHORIZATION_ROW_RE.sub("", values_source)
    if re.sub(r"[\s,]", "", unmatched_rows):
        raise AssertionError("authorization_matrix の VALUES 節を全行解釈できない")

    matrix: dict[str, _ProbeAuthorization] = {}
    for row_match in row_matches:
        granularity = row_match.group("granularity")
        if granularity in matrix:
            raise AssertionError(f"probe granularity が重複している: {granularity}")
        grants_source = row_match.group("grant_kinds")
        grant_kinds = tuple(
            match.group("grant_kind")
            for match in _GRANT_KIND_RE.finditer(grants_source)
        )
        unmatched_grants = _GRANT_KIND_RE.sub("", grants_source)
        if (
            not grant_kinds
            or len(grant_kinds) != len(set(grant_kinds))
            or re.sub(r"[\s,]", "", unmatched_grants)
        ):
            raise AssertionError(
                f"required_grant_kindsをexact-set導出できない: {granularity}"
            )
        matrix[granularity] = _ProbeAuthorization(
            resource_kind=row_match.group("resource_kind"),
            required_grant_kinds=grant_kinds,
        )
    return matrix


def _assert_return_contract_is_business_rows() -> None:
    """DDL 資産が集計ではなく型付き業務行を返す契約であることを要求する。"""
    asset = _read_json_object(_DDL_ELEMENTS_PATH)
    functions = _object_rows(asset.get("functions"), "ddl-elements.functions")
    matches = [
        row for row in functions if row.get("function_id") == "authorized_shared_rows"
    ]
    if len(matches) != 1:
        raise AssertionError("authorized_shared_rows の関数資産が一意でない")
    function = matches[0]
    if function.get("aggregation_contract") != "none":
        raise AssertionError("正例 probe は集計を模さない契約でなければならない")
    if function.get("return_contract") != "typed_authorized_business_rows":
        raise AssertionError("正例 probe の型付き業務行返却契約が一致しない")


def _positive_cases_from_assets() -> tuple[_PositiveCase, ...]:
    """正例母集合を allow セルおよび body 行列と exact-set 照合する。

    Returns:
        ``positive_cases.cases`` 順の probe 正例。
    """
    claim_mutant_map = _read_json_object(_CLAIM_MUTANT_MAP_PATH)
    positive_cases_value = claim_mutant_map.get("positive_cases")
    if not isinstance(positive_cases_value, dict):
        raise AssertionError("claim-mutant-map.positive_casesがobjectでない")
    if positive_cases_value.get("scope_id") != _POSITIVE_SCOPE_ID:
        raise AssertionError("positive case の scope_id が一致しない")
    if positive_cases_value.get("population_rule") != _POSITIVE_POPULATION_RULE:
        raise AssertionError("positive case の population_rule が一致しない")
    positive_rows = _object_rows(
        positive_cases_value.get("cases"),
        "claim-mutant-map.positive_cases.cases",
    )

    http_matrix = _read_json_object(_HTTP_ROUTE_MATRIX_PATH)
    http_cells = _object_rows(http_matrix.get("cells"), "http-route-matrix.cells")
    allow_rows = tuple(
        cell for cell in http_cells if cell.get("expected_result") == "allow"
    )
    positive_cell_ids = tuple(
        _string(row.get("cell_id"), "positive case cell_id") for row in positive_rows
    )
    allow_cell_ids = tuple(
        _string(row.get("cell_id"), "allow cell_id") for row in allow_rows
    )
    if len(positive_cell_ids) != len(set(positive_cell_ids)):
        raise AssertionError("positive_cases.cases の cell_id が重複している")
    if len(allow_cell_ids) != len(set(allow_cell_ids)):
        raise AssertionError("allow セルの cell_id が重複している")
    positive_cell_set = set(positive_cell_ids)
    allow_cell_set = set(allow_cell_ids)
    if positive_cell_set != allow_cell_set or _identifier_set_digest(
        positive_cell_set
    ) != _identifier_set_digest(allow_cell_set):
        raise AssertionError("positive case と allow セルが exact-set 一致しない")
    if _SELF_EXEMPTION_CELL_ID not in positive_cell_set:
        raise AssertionError("自テナント例外を担当する positive case が母集合にない")

    positive_by_cell = dict(zip(positive_cell_ids, positive_rows, strict=True))
    allow_by_cell = dict(zip(allow_cell_ids, allow_rows, strict=True))
    authorization_matrix = _authorization_matrix_from_body()
    converted_cases: list[_PositiveCase] = []
    mapped_granularities: set[str] = set()

    for cell_id in positive_cell_ids:
        positive_row = positive_by_cell[cell_id]
        if positive_row.get("expected_result") != "allow":
            raise AssertionError(f"positive case が allow でない: {cell_id}")
        test_owner = positive_row.get("test_owner")
        if not isinstance(test_owner, dict) or test_owner.get("id") != (
            f"{_POSITIVE_OWNER_PREFIX}{cell_id}"
        ):
            raise AssertionError(f"positive case の test_owner が一致しない: {cell_id}")

        allow_row = allow_by_cell[cell_id]
        http_resource_kind = _string(
            allow_row.get("resource_kind"), f"{cell_id}.resource_kind"
        )
        http_channel = _string(allow_row.get("channel"), f"{cell_id}.channel")
        http_grants = _string_tuple(
            allow_row.get("required_grant_ids"), f"{cell_id}.required_grant_ids"
        )
        try:
            base_granularity = _HTTP_RESOURCE_TO_PROBE_GRANULARITY[http_resource_kind]
            suffix = _HTTP_CHANNEL_TO_PROBE_SUFFIX[http_channel]
            converted_grants = tuple(
                _HTTP_GRANT_TO_PROBE_GRANT[grant_id] for grant_id in http_grants
            )
        except KeyError as error:
            raise AssertionError(
                f"allow セルを probe 語彙へ写像できない: {cell_id}: {error.args[0]}"
            ) from error

        granularity = f"{base_granularity}{suffix}"
        probe_authorization = authorization_matrix.get(granularity)
        if probe_authorization is None:
            raise AssertionError(
                f"写像先が body の authorization_matrix にない: {cell_id}"
            )
        if probe_authorization.resource_kind != base_granularity:
            raise AssertionError(
                f"写像先の probe resource_kind が一致しない: {cell_id}"
            )
        if frozenset(converted_grants) != frozenset(
            probe_authorization.required_grant_kinds
        ):
            raise AssertionError(f"HTTP と probe の必須付与集合が一致しない: {cell_id}")
        mapped_granularities.add(granularity)
        converted_cases.append(
            _PositiveCase(
                cell_id=cell_id,
                granularity=granularity,
                resource_kind=probe_authorization.resource_kind,
                required_grant_kinds=probe_authorization.required_grant_kinds,
            )
        )

    if mapped_granularities != set(authorization_matrix):
        raise AssertionError("allow セルから probe 認可行列への写像が全射でない")
    _assert_return_contract_is_business_rows()
    return tuple(converted_cases)


def _grant_rows(
    group_id: int,
    tenant_ids: tuple[int, ...],
    grant_kinds: tuple[str, ...],
    *,
    disabled_grant_kind: str | None = None,
) -> tuple[tuple[int, int, str, bool], ...]:
    """Fixture 定義から付与行を直積で作る。

    Args:
        group_id: 付与対象グループ。
        tenant_ids: 付与を出すテナント列。
        grant_kinds: 当該粒度が要求する付与種別列。
        disabled_grant_kind: 無効として混ぜる付与種別。

    Returns:
        ``probe_grants`` の列順に並べた行列。
    """
    return tuple(
        (
            group_id,
            tenant_id,
            grant_kind,
            grant_kind != disabled_grant_kind,
        )
        for tenant_id in tenant_ids
        for grant_kind in grant_kinds
    )


def _expected_rows(
    business_rows: tuple[_BusinessFixtureRow, ...], invocation_id: str
) -> frozenset[_ReturnedRow]:
    """Fixture 定義だけから呼び出しの期待集合を導出する。

    Args:
        business_rows: DB へ投入する業務行定義。
        invocation_id: 期待集合を作る呼び出し ID。

    Returns:
        関数出力を参照せずに作った exact-set oracle。
    """
    return frozenset(
        row.returned_row()
        for row in business_rows
        if invocation_id in row.expected_invocation_ids
    )


def _runtime_fixture_definition(case: _PositiveCase) -> _PositiveRuntimeFixture:
    """正例と全除外種別を持つ fixture 定義を組み立てる。

    Args:
        case: 資産から導出した正例セル。

    Returns:
        INSERT 行と呼び出しごとの期待集合。
    """
    requester = 7000
    authorized_target = 7001
    outside_group_target = 7002
    inactive_member_target = 7003
    unshared_target = 7004
    no_reciprocity_target = 7005
    inactive_group_target = 7006
    main_group = 7100
    no_reciprocity_group = 7101
    inactive_group = 7102
    self_exemption_group = 7103

    groups: list[tuple[int, str]] = [
        (main_group, "active"),
        (no_reciprocity_group, "active"),
        (inactive_group, "inactive"),
    ]
    memberships: list[tuple[int, int, str, str]] = [
        (main_group, requester, "active", "member"),
        (main_group, authorized_target, "active", "member"),
        (main_group, inactive_member_target, "inactive", "member"),
        (main_group, unshared_target, "active", "member"),
        (no_reciprocity_group, requester, "active", "member"),
        (no_reciprocity_group, no_reciprocity_target, "active", "member"),
        (inactive_group, requester, "active", "member"),
        (inactive_group, inactive_group_target, "active", "member"),
    ]
    required_grants = case.required_grant_kinds
    if not required_grants:
        raise AssertionError(f"必須付与がない positive case: {case.cell_id}")
    grants = list(
        _grant_rows(
            main_group,
            (
                requester,
                authorized_target,
                outside_group_target,
                inactive_member_target,
            ),
            required_grants,
        )
    )
    grants.extend(
        _grant_rows(
            main_group,
            (unshared_target,),
            required_grants,
            disabled_grant_kind=required_grants[0],
        )
    )
    # 相互性の負例では対象だけが全付与を出し、要求元は一つも出さない。
    grants.extend(
        _grant_rows(
            no_reciprocity_group,
            (no_reciprocity_target,),
            required_grants,
        )
    )
    grants.extend(
        _grant_rows(
            inactive_group,
            (requester, inactive_group_target),
            required_grants,
        )
    )

    business_rows: list[_BusinessFixtureRow] = [
        _BusinessFixtureRow(
            authorized_target,
            case.resource_kind,
            "self",
            "authorized-target",
            frozenset({_MAIN_INVOCATION}),
        ),
        _BusinessFixtureRow(
            outside_group_target,
            case.resource_kind,
            "self",
            "outside-group",
            frozenset(),
            "outside_group",
        ),
        _BusinessFixtureRow(
            inactive_member_target,
            case.resource_kind,
            "self",
            "inactive-membership",
            frozenset(),
            "inactive_membership",
        ),
        _BusinessFixtureRow(
            unshared_target,
            case.resource_kind,
            "self",
            "target-grant-disabled",
            frozenset(),
            "target_grant_incomplete",
        ),
        _BusinessFixtureRow(
            no_reciprocity_target,
            case.resource_kind,
            "self",
            "requester-grant-missing",
            frozenset(),
        ),
        _BusinessFixtureRow(
            inactive_group_target,
            case.resource_kind,
            "self",
            "inactive-group",
            frozenset(),
        ),
        _BusinessFixtureRow(
            authorized_target,
            case.resource_kind,
            "third_party",
            "non-self-ownership",
            frozenset(),
            "non_self_ownership",
        ),
    ]

    invocation_definitions: list[tuple[str, int, tuple[int, ...], str | None]] = [
        (
            _MAIN_INVOCATION,
            main_group,
            (
                authorized_target,
                outside_group_target,
                inactive_member_target,
                unshared_target,
            ),
            None,
        ),
        (
            _NO_RECIPROCITY_INVOCATION,
            no_reciprocity_group,
            (no_reciprocity_target,),
            "requester_grant_incomplete",
        ),
        (
            _INACTIVE_GROUP_INVOCATION,
            inactive_group,
            (inactive_group_target,),
            "inactive_group",
        ),
    ]

    if case.cell_id == _SELF_EXEMPTION_CELL_ID:
        # 自テナントだけのグループには付与を置かず、前提⑤の例外を独立に示す。
        groups.append((self_exemption_group, "active"))
        memberships.append((self_exemption_group, requester, "active", "member"))
        business_rows.append(
            _BusinessFixtureRow(
                requester,
                case.resource_kind,
                "self",
                "self-without-grants",
                frozenset({_SELF_EXEMPTION_INVOCATION}),
            )
        )
        invocation_definitions.append(
            (
                _SELF_EXEMPTION_INVOCATION,
                self_exemption_group,
                (requester,),
                None,
            )
        )

    business_row_tuple = tuple(business_rows)
    invocations = tuple(
        _ProbeInvocation(
            invocation_id=invocation_id,
            group_id=group_id,
            target_tenant_ids=target_tenant_ids,
            expected_rows=_expected_rows(business_row_tuple, invocation_id),
            exclusion_kind=exclusion_kind,
        )
        for invocation_id, group_id, target_tenant_ids, exclusion_kind in (
            invocation_definitions
        )
    )
    actual_exclusion_kinds = {
        exclusion_kind
        for exclusion_kind in (
            *(row.exclusion_kind for row in business_row_tuple),
            *(invocation.exclusion_kind for invocation in invocations),
        )
        if exclusion_kind is not None
    }
    if actual_exclusion_kinds != _REQUIRED_EXCLUSION_KINDS:
        raise AssertionError("fixture が返却禁止行の全種別を exact-set 被覆していない")

    return _PositiveRuntimeFixture(
        requester_tenant_id=requester,
        granularity=case.granularity,
        groups=tuple(groups),
        memberships=tuple(memberships),
        grants=tuple(grants),
        business_rows=business_row_tuple,
        invocations=invocations,
    )


_POSITIVE_CASES = _positive_cases_from_assets()


def _insert_runtime_fixture(
    provisioned_catalog: ProvisionedCatalog,
    fixture: _PositiveRuntimeFixture,
) -> None:
    """正例と拒否例で共有する業務行 fixture を投入する。

    Args:
        provisioned_catalog: 共通の適用済み使い捨て構成。
        fixture: 関数出力とは独立に期待集合を持つ fixture 定義。
    """
    with provisioned_catalog.admin.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO probe_data.probe_groups (group_id, status) VALUES (%s, %s)",
            fixture.groups,
        )
        cursor.executemany(
            """
            INSERT INTO probe_data.probe_memberships
                (group_id, tenant_id, status, group_role)
            VALUES (%s, %s, %s, %s)
            """,
            fixture.memberships,
        )
        cursor.executemany(
            """
            INSERT INTO probe_data.probe_grants
                (group_id, tenant_id, grant_kind, enabled)
            VALUES (%s, %s, %s, %s)
            """,
            fixture.grants,
        )
        cursor.executemany(
            """
            INSERT INTO probe_data.probe_business_rows
                (tenant_id, resource_kind, ownership_kind, payload)
            VALUES (%s, %s, %s, %s::JSONB)
            """,
            tuple(row.database_row() for row in fixture.business_rows),
        )
    provisioned_catalog.admin.commit()


@pytest.fixture
def positive_runtime_fixture(
    provisioned_catalog: ProvisionedCatalog,
    case: _PositiveCase,
) -> _PositiveRuntimeFixture:
    """資産駆動の正例と返却禁止行を適用済み構成へ投入する。

    Args:
        provisioned_catalog: 共通の適用済み使い捨て構成。
        case: 現在の allow セルから導出した probe 正例。

    Returns:
        関数出力とは独立に期待集合を持つ fixture 定義。
    """
    fixture = _runtime_fixture_definition(case)
    _insert_runtime_fixture(provisioned_catalog, fixture)
    return fixture


def _normalize_returned_rows(rows: list[tuple[Any, ...]]) -> frozenset[_ReturnedRow]:
    """DB の返却行を exact-set 比較用の型へ変換する。

    Args:
        rows: ``authorized_shared_rows`` の取得結果。

    Returns:
        payload を canonical JSON にした返却行集合。
    """
    normalized: set[_ReturnedRow] = set()
    for row in rows:
        if (
            len(row) != len(_ReturnedRow.__dataclass_fields__)
            or not isinstance(row[0], int)
            or not isinstance(row[1], str)
            or not isinstance(row[2], str)
        ):
            raise AssertionError(f"関数の型付き返却契約に一致しない: {row!r}")
        normalized.add(
            _ReturnedRow(
                tenant_id=row[0],
                resource_kind=row[1],
                ownership_kind=row[2],
                payload_json=json.dumps(
                    row[3],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
    return frozenset(normalized)


def _fetch_authorized_shared_rows(
    connection: psycopg.Connection[Any],
    fixture: _PositiveRuntimeFixture,
    invocation: _ProbeInvocation,
) -> frozenset[_ReturnedRow]:
    """共通 fixture の文脈で共有関数を呼び出し、返却集合を正規化する。

    Args:
        connection: アプリ用ロール自身で認証した接続。
        fixture: 要求元テナントと粒度を持つ共通 fixture。
        invocation: グループと対象集合を持つ呼び出し定義。

    Returns:
        exact-set 比較用に正規化した関数返却集合。
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
            (str(fixture.requester_tenant_id),),
        )

    return _fetch_authorized_shared_rows_in_current_context(
        connection,
        fixture,
        invocation,
    )


def _fetch_authorized_shared_rows_in_current_context(
    connection: psycopg.Connection[Any],
    fixture: _PositiveRuntimeFixture,
    invocation: _ProbeInvocation,
) -> frozenset[_ReturnedRow]:
    """現在のテナント文脈を変更せず共有関数の返却集合を取得する。

    Args:
        connection: アプリ用ロール自身で認証した接続。
        fixture: 粒度を持つ共通 fixture。
        invocation: グループと対象集合を持つ呼び出し定義。

    Returns:
        exact-set 比較用に正規化した関数返却集合。
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tenant_id, resource_kind, ownership_kind, payload
            FROM authz_private.authorized_shared_rows(
                %s::BIGINT,
                %s::BIGINT[],
                %s::TEXT
            )
            """,
            (
                invocation.group_id,
                list(invocation.target_tenant_ids),
                fixture.granularity,
            ),
        )
        return _normalize_returned_rows(cursor.fetchall())


@pytest.mark.parametrize(
    "case",
    _POSITIVE_CASES,
    ids=tuple(case.cell_id for case in _POSITIVE_CASES),
)
def test_authorized_shared_rows_returns_only_fixture_authorized_rows(
    case: _PositiveCase,
    positive_runtime_fixture: _PositiveRuntimeFixture,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """各 allow セルで fixture が許可した業務行だけを exact-set 取得する。"""
    assert positive_runtime_fixture.granularity == case.granularity
    try:
        for invocation in positive_runtime_fixture.invocations:
            actual_rows = _fetch_authorized_shared_rows(
                app_role_connection,
                positive_runtime_fixture,
                invocation,
            )
            assert actual_rows == invocation.expected_rows, invocation.invocation_id
    finally:
        app_role_connection.rollback()
