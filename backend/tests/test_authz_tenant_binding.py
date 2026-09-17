"""テナント境界試験の平場エントリーポイント。

後続ステップでは、構成検査・DB 統合・故障注入・変異検査を本モジュールへ追加する。
現段階では、通常モジュールから明示 import した DB fixture の解決、接続 identity、
複数の登録経路によるセッション資源の共有だけを検証する。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from db_fixtures import (
    _authenticated_identity,
    _SessionResourceRegistry,
    admin_connection,
    tested_role_connection,
    verify_connection_identities,
)

# DB fixture は backend/tests/conftest.py を経由せず、平場へ明示的に再公開する。
__all__ = (
    "admin_connection",
    "tested_role_connection",
    "verify_connection_identities",
)


def _assert_duplicate_fixture_registrations_share_one_session_resource() -> None:
    """二つの登録経路が単一資源を共有し、最後の解放時だけ破棄する。"""
    registry = _SessionResourceRegistry()
    resource_key = object()
    expected_resource = object()
    setup_count = 0
    teardown_count = 0

    @contextmanager
    def create_resource() -> Iterator[object]:
        nonlocal setup_count, teardown_count
        setup_count += 1
        try:
            yield expected_resource
        finally:
            teardown_count += 1

    db_conftest_registration = registry.acquire(resource_key, create_resource)
    flat_module_registration = registry.acquire(resource_key, create_resource)
    with db_conftest_registration as db_resource:
        with flat_module_registration as flat_resource:
            assert db_resource is flat_resource
            assert setup_count == 1
            assert teardown_count == 0
        assert teardown_count == 0
    assert teardown_count == 1


@pytest.mark.requires_db
def test_explicit_database_fixtures_preserve_connection_identities(
    admin_connection: psycopg.Connection[Any],
    tested_role_connection: psycopg.Connection[Any],
    verify_connection_identities: None,
) -> None:
    """平場から解決した接続が別々の認証主体を保つことを確認する。"""
    _assert_duplicate_fixture_registrations_share_one_session_resource()
    assert verify_connection_identities is None
    admin_identity = _authenticated_identity(admin_connection)
    tested_role_identity = _authenticated_identity(tested_role_connection)
    assert admin_identity[0] == admin_identity[1]
    assert tested_role_identity[0] == tested_role_identity[1]
    assert admin_identity != tested_role_identity
