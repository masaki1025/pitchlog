"""テナント GUC に残る信頼境界の残余リスクを実 PostgreSQL で示す。

アプリ用ロールが任意のテナント文脈を設定できてしまうことを期待値にする。
偽装先と対象が同じグループへの参加と相互付与を持つ場合は行が返る一方、
参加していても要求元側の付与がないテナント文脈では行が返らないことも示す。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import psycopg
import pytest

from .conftest import ProvisionedCatalog
from .test_authz_precondition_matrix import (
    _enabled_grants,
    _invocation_by_exclusion,
    _only,
)
from .test_authz_runtime_negative import _shared_runtime_scenario_definition
from .test_authz_runtime_positive import (
    _POSITIVE_CASES,
    _BusinessFixtureRow,
    _expected_rows,
    _fetch_authorized_shared_rows_in_current_context,
    _grant_rows,
    _insert_runtime_fixture,
    _PositiveRuntimeFixture,
    _ProbeInvocation,
)

pytestmark = pytest.mark.requires_db


def _next_tenant_id(fixture: _PositiveRuntimeFixture) -> int:
    """共通 fixture 内で未使用のテナント ID を返す。

    Args:
        fixture: ステップ 7 由来の共通 fixture。

    Returns:
        fixture の最大テナント ID より 1 大きい値。
    """
    tenant_ids = {
        fixture.requester_tenant_id,
        *(tenant_id for _group_id, tenant_id, _status, _role in fixture.memberships),
        *(tenant_id for _group_id, tenant_id, _kind, _enabled in fixture.grants),
        *(row.tenant_id for row in fixture.business_rows),
    }
    return max(tenant_ids) + 1


def _set_and_read_tenant_context(
    connection: psycopg.Connection[Any], tenant_id: int
) -> tuple[str, str]:
    """アプリ用実接続から任意のテナント文脈を設定し読み戻す。

    Args:
        connection: アプリ用ロール自身で認証した接続。
        tenant_id: DB が接続主体との対応を検証せず受け入れる値。

    Returns:
        ``set_config`` の返却値と ``current_setting`` の読み戻し値。
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
            (str(tenant_id),),
        )
        configured_row = cursor.fetchone()
        cursor.execute("SELECT pg_catalog.current_setting('app.tenant_id', true)")
        observed_row = cursor.fetchone()
    if (
        configured_row is None
        or len(configured_row) != 1
        or not isinstance(configured_row[0], str)
        or observed_row is None
        or len(observed_row) != 1
        or not isinstance(observed_row[0], str)
    ):
        raise AssertionError("テナント文脈の設定値と読み戻し値を取得できない")
    return configured_row[0], observed_row[0]


def test_app_role_can_spoof_tenant_context_only_with_matching_grants(
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
) -> None:
    """app_role が他テナントを設定でき、その付与を利用できてしまう。"""
    fixture, _main_invocation = _shared_runtime_scenario_definition()
    no_requester_grant = _invocation_by_exclusion(
        fixture,
        "requester_grant_incomplete",
    )
    forged_tenant_id = _only(
        no_requester_grant.target_tenant_ids,
        "偽装先テナント",
    )
    target_tenant_id = _next_tenant_id(fixture)
    ungranted_tenant_id = target_tenant_id + 1
    case = _only(
        tuple(
            case for case in _POSITIVE_CASES if case.granularity == fixture.granularity
        ),
        "fixture 粒度の認可行列",
    )
    target_row = _BusinessFixtureRow(
        tenant_id=target_tenant_id,
        resource_kind=case.resource_kind,
        ownership_kind="self",
        marker="reachable-only-from-forged-context",
        expected_invocation_ids=frozenset({"forged-context"}),
    )
    target_grants = _grant_rows(
        no_requester_grant.group_id,
        (target_tenant_id,),
        case.required_grant_kinds,
    )
    extended_fixture = replace(
        fixture,
        memberships=(
            *fixture.memberships,
            (
                no_requester_grant.group_id,
                target_tenant_id,
                "active",
                "member",
            ),
            (
                no_requester_grant.group_id,
                ungranted_tenant_id,
                "active",
                "member",
            ),
        ),
        grants=(*fixture.grants, *target_grants),
        business_rows=(*fixture.business_rows, target_row),
    )
    invocation = _ProbeInvocation(
        invocation_id="forged-context",
        group_id=no_requester_grant.group_id,
        target_tenant_ids=(target_tenant_id,),
        expected_rows=_expected_rows(
            extended_fixture.business_rows,
            "forged-context",
        ),
    )
    required_grants = frozenset(case.required_grant_kinds)
    nominal_tenant_id = extended_fixture.requester_tenant_id

    assert forged_tenant_id != nominal_tenant_id
    assert (
        no_requester_grant.group_id,
        ungranted_tenant_id,
        "active",
        "member",
    ) in extended_fixture.memberships
    assert (
        _enabled_grants(
            extended_fixture,
            no_requester_grant.group_id,
            forged_tenant_id,
        )
        == required_grants
    )
    assert (
        _enabled_grants(
            extended_fixture,
            no_requester_grant.group_id,
            target_tenant_id,
        )
        == required_grants
    )
    assert not _enabled_grants(
        extended_fixture,
        no_requester_grant.group_id,
        nominal_tenant_id,
    )
    assert not _enabled_grants(
        extended_fixture,
        no_requester_grant.group_id,
        ungranted_tenant_id,
    )

    _insert_runtime_fixture(provisioned_catalog, extended_fixture)
    try:
        nominal_setting = _set_and_read_tenant_context(
            app_role_connection,
            nominal_tenant_id,
        )
        assert nominal_setting == (str(nominal_tenant_id), str(nominal_tenant_id))
        rows_in_nominal_context = _fetch_authorized_shared_rows_in_current_context(
            app_role_connection,
            extended_fixture,
            invocation,
        )
        assert rows_in_nominal_context == frozenset()

        forged_setting = _set_and_read_tenant_context(
            app_role_connection,
            forged_tenant_id,
        )
        assert forged_setting == (str(forged_tenant_id), str(forged_tenant_id))
        forged_rows = _fetch_authorized_shared_rows_in_current_context(
            app_role_connection,
            extended_fixture,
            invocation,
        )
        ungranted_setting = _set_and_read_tenant_context(
            app_role_connection,
            ungranted_tenant_id,
        )
        assert ungranted_setting == (
            str(ungranted_tenant_id),
            str(ungranted_tenant_id),
        )
        rows_without_requester_grants = (
            _fetch_authorized_shared_rows_in_current_context(
                app_role_connection,
                extended_fixture,
                invocation,
            )
        )

        assert forged_rows == invocation.expected_rows
        assert invocation.expected_rows == frozenset({target_row.returned_row()})
        assert rows_without_requester_grants == frozenset()
    finally:
        app_role_connection.rollback()
