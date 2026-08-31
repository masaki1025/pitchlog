"""PostgreSQL 実接続テストの共通フィクスチャ。"""

from __future__ import annotations

import os
import secrets
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from .environment_contract import load_expectations

_COLLECTED_DB_TESTS: set[str] = set()
_EXECUTED_DB_TESTS: set[str] = set()


def _required_dsn(variable_name: str) -> str:
    """必須 DSN を環境変数だけから取得する。

    Args:
        variable_name: 期待値資産が定める環境変数名。

    Returns:
        空でない DSN。
    """
    value = os.environ.get(variable_name)
    if not value:
        pytest.fail(f"必須 DSN 環境変数が未設定: {variable_name}")
    return value


def _dsn_names() -> tuple[str, str]:
    """管理接続と被検査ロール接続の変数名を資産から得る。

    Returns:
        管理接続用と被検査ロール接続用の環境変数名。
    """
    variables = load_expectations()["dsn_environment_variables"]
    admin_name = variables["admin_connection"]["expected_name"]
    role_name = variables["tested_role_connection"]["expected_name"]
    if not isinstance(admin_name, str) or not isinstance(role_name, str):
        raise AssertionError("DSN 環境変数名は文字列である必要がある")
    if admin_name == role_name:
        raise AssertionError("管理接続と被検査ロール接続は別変数である必要がある")
    return admin_name, role_name


def _dsn_identity(dsn: str) -> tuple[str, str]:
    """DSN から認証ユーザーとパスワードを取り出す。

    Args:
        dsn: psycopg が解釈できる接続文字列。

    Returns:
        認証ユーザー名とパスワード。
    """
    parameters = conninfo_to_dict(dsn)
    username = parameters.get("user")
    password = parameters.get("password")
    if not username or not password:
        pytest.fail("被検査ロール DSN には user と password が必要")
    return str(username), str(password)


@pytest.fixture(scope="session")
def admin_connection() -> Iterator[psycopg.Connection[Any]]:
    """管理ユーザーとして実際に認証した接続を供給する。

    Yields:
        autocommit を有効にした管理接続。
    """
    admin_name, _ = _dsn_names()
    connection = psycopg.connect(_required_dsn(admin_name), autocommit=True)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(scope="session")
def tested_role_connection(
    admin_connection: psycopg.Connection[Any],
) -> Iterator[psycopg.Connection[Any]]:
    """被検査ロールで新規認証した接続を供給し、ロールを後始末する。

    Args:
        admin_connection: ロール作成と削除に用いる管理接続。

    Yields:
        被検査ロール自身を認証ユーザーとする接続。
    """
    _, role_variable_name = _dsn_names()
    role_dsn = _required_dsn(role_variable_name)
    role_name, role_password = _dsn_identity(role_dsn)

    with admin_connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
        if cursor.fetchone() is not None:
            pytest.fail(f"被検査ロールがテスト開始前から存在する: {role_name}")
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role_name), sql.Literal(role_password)
            )
        )

    connection: psycopg.Connection[Any] | None = None
    try:
        connection = psycopg.connect(role_dsn)
        yield connection
    finally:
        if connection is not None:
            connection.close()
        with admin_connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name)))


def _authenticated_identity(
    connection: psycopg.Connection[Any],
) -> tuple[str, str]:
    """接続のセッションユーザーと現在ユーザーを取得する。

    Args:
        connection: 検査対象の接続。

    Returns:
        ``session_user`` と ``current_user``。
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT session_user, current_user")
        row = cursor.fetchone()
    if row is None:
        raise AssertionError("接続ロールの識別結果がない")
    return str(row[0]), str(row[1])


@pytest.fixture(autouse=True)
def verify_connection_identities(
    request: pytest.FixtureRequest,
) -> None:
    """DB 必須テスト冒頭で両接続の認証ユーザーを照合する。

    Args:
        request: 現在のテストとフィクスチャへアクセスする pytest 要求。
    """
    if request.node.get_closest_marker("requires_db") is None:
        return
    admin = request.getfixturevalue("admin_connection")
    tested = request.getfixturevalue("tested_role_connection")
    assert isinstance(admin, psycopg.Connection)
    assert isinstance(tested, psycopg.Connection)

    admin_name, role_name = _dsn_names()
    expected_admin, _ = _dsn_identity(_required_dsn(admin_name))
    expected_role, _ = _dsn_identity(_required_dsn(role_name))
    assert expected_admin != expected_role, "管理接続と被検査ロールは別ユーザーが必要"
    assert _authenticated_identity(admin) == (expected_admin, expected_admin)
    assert _authenticated_identity(tested) == (expected_role, expected_role)


@dataclass(frozen=True)
class DisposablePostgres:
    """使い捨て PostgreSQL クラスタの実行情報。"""

    container_name: str
    admin_dsn: str


def _run_docker(
    *arguments: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Docker CLI を固定した入出力条件で実行する。

    Args:
        *arguments: ``docker`` に渡す引数。
        check: 非 0 終了を例外にするか。

    Returns:
        完了したプロセスの情報。
    """
    return subprocess.run(
        ["docker", *arguments],
        check=check,
        capture_output=True,
        text=True,
        timeout=90,
    )


def _wait_for_postgres(dsn: str) -> None:
    """使い捨てクラスタが TCP 接続を受け付けるまで待つ。

    Args:
        dsn: 待機対象の管理 DSN。
    """
    deadline = time.monotonic() + 60
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=2):
                return
        except psycopg.Error as error:
            last_error = error
            time.sleep(0.25)
    raise AssertionError("使い捨て PostgreSQL が 60 秒以内に起動しない") from last_error


@pytest.fixture
def disposable_postgres_cluster():
    """実クラスタを起動し、利用後にコンテナごと破棄する factory を返す。

    Returns:
        context manager を生成する引数なし factory。
    """

    @contextmanager
    def factory() -> Iterator[DisposablePostgres]:
        asset = load_expectations()
        image = asset["database_environment"]["image"]["expected"]
        initdb_args = asset["database_environment"]["initdb_args"]["expected"]
        if not isinstance(image, str) or not isinstance(initdb_args, str):
            raise AssertionError("クラスタ用イメージと initdb 引数は文字列が必要")

        token = secrets.token_hex(8)
        container_name = f"pitchlog-authz-{token}"
        username = f"pitchlog_disposable_{token}"
        password = secrets.token_urlsafe(24)
        database = "pitchlog_disposable"
        _run_docker(
            "run",
            "--detach",
            "--pull=never",
            "--name",
            container_name,
            "--publish",
            "127.0.0.1::5432",
            "--env",
            f"POSTGRES_USER={username}",
            "--env",
            f"POSTGRES_PASSWORD={password}",
            "--env",
            f"POSTGRES_DB={database}",
            "--env",
            f"POSTGRES_INITDB_ARGS={initdb_args}",
            image,
        )
        try:
            port_output = _run_docker("port", container_name, "5432/tcp").stdout.strip()
            host_port = port_output.rsplit(":", maxsplit=1)[-1]
            dsn = make_conninfo(
                host="127.0.0.1",
                port=host_port,
                dbname=database,
                user=username,
                password=password,
            )
            _wait_for_postgres(dsn)
            yield DisposablePostgres(container_name=container_name, admin_dsn=dsn)
        finally:
            _run_docker("rm", "--force", container_name, check=False)

    return factory


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
