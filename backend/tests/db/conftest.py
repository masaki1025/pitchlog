"""DB fixture の再エクスポートと pytest hook を提供する。"""

from __future__ import annotations

import pytest
from db_fixtures import (
    _VERIFIED_AUTHZ_ROLE_IDS,
    DisposablePostgres,
    ProductCatalogSnapshot,
    ProvisionedCatalog,
    ProvisionedProductCatalog,
    _assert_authenticated_identity,
    _asset_rows,
    _authenticated_identity,
    _authz_login_role_connections,
    _authz_login_role_ids,
    _connect_provisioned_authz_login_roles,
    _load_ddl_asset,
    _required_dsn,
    _role_id,
    admin_connection,
    app_role_connection,
    disposable_postgres_cluster,
    management_caller_connection,
    outsider_role_connection,
    provisioned_catalog,
    provisioned_product_catalog,
    table_owner_connection,
    tested_role_connection,
    verify_connection_identities,
)

__all__ = (
    "DisposablePostgres",
    "ProductCatalogSnapshot",
    "ProvisionedCatalog",
    "ProvisionedProductCatalog",
    "_VERIFIED_AUTHZ_ROLE_IDS",
    "_assert_authenticated_identity",
    "_asset_rows",
    "_authenticated_identity",
    "_authz_login_role_connections",
    "_authz_login_role_ids",
    "_connect_provisioned_authz_login_roles",
    "_load_ddl_asset",
    "_required_dsn",
    "_role_id",
    "admin_connection",
    "app_role_connection",
    "disposable_postgres_cluster",
    "management_caller_connection",
    "outsider_role_connection",
    "provisioned_catalog",
    "provisioned_product_catalog",
    "table_owner_connection",
    "tested_role_connection",
    "verify_connection_identities",
)

_COLLECTED_DB_TESTS: set[str] = set()
_EXECUTED_DB_TESTS: set[str] = set()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """DB 必須テストの収集集合を記録する。

    Args:
        items: pytest が収集した全テスト項目。
    """
    _COLLECTED_DB_TESTS.clear()
    _EXECUTED_DB_TESTS.clear()
    _COLLECTED_DB_TESTS.update(
        item.nodeid
        for item in items
        if item.get_closest_marker("requires_db") is not None
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """DB 必須テストが call フェーズまで到達したことを記録する。

    Args:
        report: 各テストフェーズの実行結果。
    """
    if report.when == "call" and "requires_db" in report.keywords:
        _EXECUTED_DB_TESTS.add(report.nodeid)


def _required_db_execution_error(collected: set[str], executed: set[str]) -> str | None:
    """DB 必須テストの 0 件収集・0 件実行を判定する。

    Args:
        collected: 収集された DB 必須テスト ID。
        executed: call フェーズまで到達した DB 必須テスト ID。

    Returns:
        失敗理由。DB テストが実行済みなら ``None``。
    """
    if not collected:
        return "DB 必須テストが 1 件も収集されなかった"
    if not executed:
        return "DB 必須テストが 1 件も実行されなかった"
    return None


def pytest_sessionfinish(
    session: pytest.Session,
    exitstatus: int | pytest.ExitCode,
) -> None:
    """通常の全件実行で DB テストが 0 件なら失敗にする。

    Args:
        session: 完了する pytest セッション。
        exitstatus: フック開始時点の終了状態。
    """
    del exitstatus
    error = _required_db_execution_error(
        _COLLECTED_DB_TESTS,
        _EXECUTED_DB_TESTS,
    )
    if error is not None:
        terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal_reporter is not None:
            terminal_reporter.write_line(error, red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
