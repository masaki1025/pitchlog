"""認可行列のLOGINロールが個別の認証接続を持つことを検証する。"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from .conftest import (
    _VERIFIED_AUTHZ_ROLE_IDS,
    _assert_authenticated_identity,
    _authenticated_identity,
    _authz_login_role_ids,
)

pytestmark = pytest.mark.requires_db


def test_authz_login_roles_use_distinct_authenticated_connections(
    request: pytest.FixtureRequest,
    table_owner_connection: psycopg.Connection[Any],
    app_role_connection: psycopg.Connection[Any],
    management_caller_connection: psycopg.Connection[Any],
    outsider_role_connection: psycopg.Connection[Any],
) -> None:
    """資産由来の全LOGINロールを別ユーザーとして実接続する。"""
    connections = (
        table_owner_connection,
        app_role_connection,
        management_caller_connection,
        outsider_role_connection,
    )
    expected_role_ids = _authz_login_role_ids()
    identities = tuple(
        _authenticated_identity(connection) for connection in connections
    )

    assert len(connections) == len(expected_role_ids)
    assert len({id(connection) for connection in connections}) == len(connections)
    assert {session_user for session_user, _ in identities} == set(expected_role_ids)
    assert all(
        session_user == current_user for session_user, current_user in identities
    )
    assert request.node.stash[_VERIFIED_AUTHZ_ROLE_IDS] == expected_role_ids


def test_identity_guard_rejects_connection_labeled_as_another_asset_role(
    table_owner_connection: psycopg.Connection[Any],
) -> None:
    """別の資産ロール名を期待値にした接続はidentity guardでredになる。"""
    session_user, _ = _authenticated_identity(table_owner_connection)
    wrong_role_id = next(
        role_id for role_id in _authz_login_role_ids() if role_id != session_user
    )

    with pytest.raises(AssertionError, match="認証主体が期待ロールと一致しない"):
        _assert_authenticated_identity(table_owner_connection, wrong_role_id)
