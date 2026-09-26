"""テナントトランザクション単位の失敗契約を実 PostgreSQL で固定する。"""

from __future__ import annotations

import importlib
import inspect
import secrets
from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, cast, get_type_hints
from uuid import UUID

import db_fixtures
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy import (
    Engine,
    Result,
    ScalarResult,
    String,
    Uuid,
    bindparam,
    column,
    create_engine,
    event,
    select,
    table,
    text,
    update,
)
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Query, Session, mapped_column
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement
from test_authz_tenant_context import make_tenant_context

from pitchlog.authz.runtime_contract import APPLICATION_ROLE_NAME
from pitchlog.repositories import base as repository_base
from pitchlog.repositories.base import (
    _TenantOperationError,
    _TenantScopedOperation,
)
from pitchlog.repositories.tokens import (
    TenantOperationResult,
    TenantOperationToken,
)

from .conftest import DisposablePostgres

pytestmark = pytest.mark.requires_db

_TENANT_ID = UUID("00000000-0000-0000-0000-000000000444")
_BINDING_STATEMENT = "SELECT set_config('app.tenant_id', :tenant_id, true)"
_PROBE_TABLE = table(
    "tenant_transaction_probe",
    column("tenant_id"),
    column("marker"),
    schema="public",
)
_READ_STATEMENT = select(_PROBE_TABLE.c.marker).where(
    _PROBE_TABLE.c.tenant_id == bindparam("tenant_id")
)
_WRITE_STATEMENT = (
    update(_PROBE_TABLE)
    .where(_PROBE_TABLE.c.tenant_id == bindparam("tenant_id"))
    .values(marker="changed")
    .returning(_PROBE_TABLE.c.marker)
)


class _ProbeOrmBase(DeclarativeBase):
    """接続中 ORM instance の流出負例に使うテスト専用基底。"""


class _ProbeOrmRow(_ProbeOrmBase):
    """テスト専用表を ORM instance として読み出す写像。"""

    __tablename__ = "tenant_transaction_probe"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    marker: Mapped[str] = mapped_column(String)


_ORM_READ_STATEMENT = select(_ProbeOrmRow).where(
    _ProbeOrmRow.tenant_id == bindparam("tenant_id")
)


@dataclass(frozen=True, slots=True)
class _ReadProbeToken(TenantOperationToken):
    """登録済み読み取り operation のテスト専用 token。"""

    claimed_capability_id: str = "test.tenant-transaction.read"

    @property
    def capability_id(self) -> str:
        """Token が申告する capability ID を返す。"""
        return self.claimed_capability_id


@dataclass(frozen=True, slots=True)
class _WriteProbeToken(TenantOperationToken):
    """登録済み更新 operation のテスト専用 token。"""

    @property
    def capability_id(self) -> str:
        """テスト専用 capability ID を返す。"""
        return "test.tenant-transaction.write"


@dataclass(frozen=True, slots=True)
class _OrmReadProbeToken(TenantOperationToken):
    """ORM instance の流出を試す登録済み token。"""

    @property
    def capability_id(self) -> str:
        """テスト専用 capability ID を返す。"""
        return "test.tenant-transaction.orm-read"


@dataclass(frozen=True, slots=True)
class _UnregisteredProbeToken(TenantOperationToken):
    """registry に存在しない正規形のテスト専用 token。"""

    @property
    def capability_id(self) -> str:
        """未登録の capability ID を返す。"""
        return "test.tenant-transaction.unregistered"


@dataclass(frozen=True, slots=True)
class _TransactionDatabase:
    """トランザクション試験用の管理 engine とアプリ接続 URL。"""

    admin_engine: Engine
    application_url: str


class _AbortTransaction(RuntimeError):
    """呼び出し側が前段結果を見て処理を中止する例外。"""


def _transaction_module() -> ModuleType:
    """ステップ 3 で追加される製品モジュールを読み込む。

    Returns:
        テナントトランザクション単位を公開するモジュール。
    """
    return importlib.import_module("pitchlog.repositories.transaction")


@pytest.fixture(autouse=True)
def verify_connection_identities(request: pytest.FixtureRequest) -> None:
    """製品モジュール確認後に既存の DB 接続真正性 fixture を実行する。

    ``requires_db`` の共通 autouse fixture より先にステップ 3 の未実装を
    顕在化させる一方、モジュール追加後は既存 fixture の検査を省略しない。

    Args:
        request: 現在のテストと既存 fixture へアクセスする要求。
    """
    _transaction_module()
    original_fixture = cast(Any, db_fixtures.verify_connection_identities)
    original_fixture.__wrapped__(request)


def _sqlalchemy_url(dsn: str) -> str:
    """Libpq DSN を SQLAlchemy の psycopg URL へ変換する。

    Args:
        dsn: 使い捨てクラスタの接続 DSN。

    Returns:
        パスワードを省略しないテスト専用 URL。
    """
    values = conninfo_to_dict(dsn)
    username = values.get("user")
    password = values.get("password")
    host = values.get("host")
    port = values.get("port")
    database = values.get("dbname")
    return URL.create(
        "postgresql+psycopg",
        username=None if username is None else str(username),
        password=None if password is None else str(password),
        host=None if host is None else str(host),
        port=None if port is None else int(port),
        database=None if database is None else str(database),
    ).render_as_string(hide_password=False)


@contextmanager
def _transaction_database(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> Iterator[_TransactionDatabase]:
    """使い捨て DB にアプリロールとテスト専用表を構成する。

    Args:
        disposable_postgres_cluster: 隔離 PostgreSQL の生成 factory。

    Yields:
        管理観測用 engine とアプリ接続 URL。
    """
    with disposable_postgres_cluster() as cluster:
        application_password = secrets.token_urlsafe(24)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            with admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE {} WITH LOGIN PASSWORD {} NOSUPERUSER "
                        "NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION NOINHERIT"
                    ).format(
                        sql.Identifier(APPLICATION_ROLE_NAME),
                        sql.Literal(application_password),
                    )
                )
                cursor.execute(
                    """
                    CREATE TABLE public.tenant_transaction_probe (
                        tenant_id uuid PRIMARY KEY,
                        marker text NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO public.tenant_transaction_probe (tenant_id, marker)
                    VALUES (%s, %s)
                    """,
                    (_TENANT_ID, "original"),
                )
                cursor.execute(
                    sql.SQL(
                        "GRANT SELECT, UPDATE ON public.tenant_transaction_probe TO {}"
                    ).format(sql.Identifier(APPLICATION_ROLE_NAME))
                )

        application_dsn = make_conninfo(
            cluster.role_dsn_template,
            user=APPLICATION_ROLE_NAME,
            password=application_password,
        )
        admin_engine = create_engine(_sqlalchemy_url(cluster.admin_dsn))
        try:
            yield _TransactionDatabase(
                admin_engine=admin_engine,
                application_url=_sqlalchemy_url(application_dsn),
            )
        finally:
            admin_engine.dispose()


def _configure_application_database(
    monkeypatch: pytest.MonkeyPatch,
    database: _TransactionDatabase,
) -> None:
    """製品の単一 engine 生成経路へテスト用 URL を設定する。

    Args:
        monkeypatch: 環境設定を試験内に閉じる fixture。
        database: 設定済み使い捨て DB。
    """
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", database.application_url)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")


def _read_operation() -> _TenantScopedOperation:
    """テスト専用読み取り operation を返す。"""
    token = _ReadProbeToken()
    return _TenantScopedOperation(
        capability_id=token.capability_id,
        statement=cast(Select[tuple[object, ...]], _READ_STATEMENT),
        tenant_column=_PROBE_TABLE.c.tenant_id,
    )


def _write_operation() -> _TenantScopedOperation:
    """テスト専用更新 operation を返す。"""
    token = _WriteProbeToken()
    return _TenantScopedOperation(
        capability_id=token.capability_id,
        statement=cast(Select[tuple[object, ...]], _WRITE_STATEMENT),
        tenant_column=_PROBE_TABLE.c.tenant_id,
    )


def _orm_read_operation() -> _TenantScopedOperation:
    """ORM instance を生成するテスト専用読み取り operation を返す。"""
    token = _OrmReadProbeToken()
    return _TenantScopedOperation(
        capability_id=token.capability_id,
        statement=cast(Select[tuple[object, ...]], _ORM_READ_STATEMENT),
        tenant_column=cast(ColumnElement[object], _ProbeOrmRow.tenant_id),
    )


def _marker(engine: Engine) -> str:
    """管理接続からテスト行の marker を返す。

    Args:
        engine: トランザクション外から観測する管理 engine。

    Returns:
        テスト行の現在値。
    """
    with engine.connect() as connection:
        return str(
            connection.execute(
                text(
                    "SELECT marker FROM public.tenant_transaction_probe "
                    "WHERE tenant_id = :tenant_id"
                ),
                {"tenant_id": _TENANT_ID},
            ).scalar_one()
        )


def _return_graph(value: object) -> Iterator[object]:
    """公開戻り値から到達できる値を再帰的に列挙する。

    Args:
        value: 公開境界を越えた戻り値。

    Yields:
        DTO 自体と immutable container 内の全要素。
    """
    yield value
    if type(value) is TenantOperationResult:
        yield from _return_graph(value.rows)
    elif type(value) in (tuple, frozenset):
        immutable_values = cast(tuple[object, ...] | frozenset[object], value)
        for item in immutable_values:
            yield from _return_graph(item)


def test_binding_statement_is_first_for_multiple_operations(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """複数 operation の発行 SQL 列でも束縛文が必ず先頭になる。"""
    transaction = _transaction_module()

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(
            repository_base,
            "_OPERATION_REGISTRY",
            MappingProxyType({_ReadProbeToken: _read_operation()}),
        )
        observed_statements: list[str] = []

        def observe_orm_sql(execute_state: object) -> None:
            observed_statements.append(str(getattr(execute_state, "statement", "")))

        event.listen(Session, "do_orm_execute", observe_orm_sql)
        try:
            with transaction.tenant_transaction_scope(
                make_tenant_context(_TENANT_ID)
            ) as tenant_transaction:
                tenant_transaction.run(_ReadProbeToken())
                tenant_transaction.run(_ReadProbeToken())
        finally:
            event.remove(Session, "do_orm_execute", observe_orm_sql)

    assert observed_statements == [
        _BINDING_STATEMENT,
        str(_READ_STATEMENT),
        str(_READ_STATEMENT),
    ]


def test_run_signature_has_no_second_tenant_context() -> None:
    """Run が operation だけを受け、別文脈を混ぜる口を公開しない。"""
    transaction = _transaction_module()

    signature = inspect.signature(transaction.TenantTransaction.run)
    hints = get_type_hints(transaction.TenantTransaction.run)
    public_methods = {
        name
        for name, value in vars(transaction.TenantTransaction).items()
        if not name.startswith("_") and inspect.isfunction(value)
    }

    assert tuple(signature.parameters) == ("self", "operation")
    assert hints == {
        "operation": TenantOperationToken,
        "return": TenantOperationResult,
    }
    assert public_methods == {"run"}
    assert transaction.TenantTransaction.__slots__ == ("_session", "_context")
    assert getattr(transaction.TenantTransaction, "__final__", False) is True


def test_unregistered_and_forged_tokens_use_existing_rejection_path(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未登録 token と capability 偽造を既存 resolver で拒否する。"""
    transaction = _transaction_module()

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(
            repository_base,
            "_OPERATION_REGISTRY",
            MappingProxyType({_ReadProbeToken: _read_operation()}),
        )
        cases = (
            (_UnregisteredProbeToken(), "未登録または偽造"),
            (_ReadProbeToken("forged"), "capability ID が不一致"),
        )

        for operation, expected_message in cases:
            with transaction.tenant_transaction_scope(
                make_tenant_context(_TENANT_ID)
            ) as tenant_transaction:
                with pytest.raises(
                    _TenantOperationError,
                    match=expected_message,
                ) as caught:
                    tenant_transaction.run(operation)

            assert any(
                entry.name == "_operation_spec" and Path(entry.path).name == "base.py"
                for entry in caught.traceback
            )


def test_abort_exception_rolls_back_and_closes(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """読み取り後の例外を伝播し、ロールバックして Session を閉じる。

    現行 registry は Select だけを扱い、insert / update の登録形式は本タスクの
    射程外であるため、書き込み結果ではなく Session event で rollback を観測する。
    """
    transaction = _transaction_module()
    created_sessions: list[_RollbackObservedSession] = []
    transaction_events: list[str] = []

    class _RollbackObservedSession(Session):
        """rollback と close の対象になった Session を識別する。"""

        close_calls: int

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """生成された Session を観測対象へ登録する。"""
            super().__init__(*args, **kwargs)
            self.close_calls = 0
            created_sessions.append(self)

        def close(self) -> None:
            """Close 呼び出しを記録して通常の解放処理へ委譲する。"""
            self.close_calls += 1
            super().close()

    def observe_rollback(session: Session) -> None:
        del session
        transaction_events.append("rollback")

    def observe_commit(session: Session) -> None:
        del session
        transaction_events.append("commit")

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(transaction, "Session", _RollbackObservedSession)
        monkeypatch.setattr(
            repository_base,
            "_OPERATION_REGISTRY",
            MappingProxyType({_ReadProbeToken: _read_operation()}),
        )
        event.listen(_RollbackObservedSession, "after_rollback", observe_rollback)
        event.listen(_RollbackObservedSession, "after_commit", observe_commit)
        try:
            with pytest.raises(_AbortTransaction, match="前段結果で中止"):
                with transaction.tenant_transaction_scope(
                    make_tenant_context(_TENANT_ID)
                ) as tenant_transaction:
                    result = tenant_transaction.run(_ReadProbeToken())
                    assert result.rows == (("original",),)
                    raise _AbortTransaction("前段結果で中止")
        finally:
            event.remove(
                _RollbackObservedSession,
                "after_rollback",
                observe_rollback,
            )
            event.remove(_RollbackObservedSession, "after_commit", observe_commit)

    assert transaction_events == ["rollback"]
    assert len(created_sessions) == 1
    assert created_sessions[0].close_calls == 1


def test_run_never_returns_database_backed_or_lazy_values(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Select の公開戻り値を close 後も読める exact DTO に閉じる。"""
    transaction = _transaction_module()
    created_sessions: list[_ResultObservedSession] = []

    class _ResultObservedSession(Session):
        """戻り値を読む前に close 済みであることを観測する Session。"""

        close_calls: int

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """生成された Session を観測対象へ登録する。"""
            super().__init__(*args, **kwargs)
            self.close_calls = 0
            created_sessions.append(self)

        def close(self) -> None:
            """Close 呼び出しを記録して通常の解放処理へ委譲する。"""
            self.close_calls += 1
            super().close()

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(transaction, "Session", _ResultObservedSession)
        monkeypatch.setattr(
            repository_base,
            "_OPERATION_REGISTRY",
            MappingProxyType({_ReadProbeToken: _read_operation()}),
        )

        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as tenant_transaction:
            result = tenant_transaction.run(_ReadProbeToken())

        assert len(created_sessions) == 1
        assert created_sessions[0].close_calls == 1
        assert type(result) is TenantOperationResult
        assert result.rows == (("original",),)
        assert not any(
            isinstance(
                value,
                (Result, ScalarResult, Query, _ProbeOrmRow, Generator),
            )
            for value in _return_graph(result)
        )


def test_scope_closes_session_after_success_and_exception(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正常終了と例外終了の双方で内部 Session を close する。"""
    transaction = _transaction_module()
    created_sessions: list[_CloseObservedSession] = []

    class _CloseObservedSession(Session):
        """close 呼び出し回数を観測する Session。"""

        close_calls: int

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """生成された Session を観測対象へ登録する。"""
            super().__init__(*args, **kwargs)
            self.close_calls = 0
            created_sessions.append(self)

        def close(self) -> None:
            """Close 呼び出しを記録して通常の解放処理へ委譲する。"""
            self.close_calls += 1
            super().close()

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(transaction, "Session", _CloseObservedSession)
        monkeypatch.setattr(
            repository_base,
            "_OPERATION_REGISTRY",
            MappingProxyType({_ReadProbeToken: _read_operation()}),
        )

        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as tenant_transaction:
            tenant_transaction.run(_ReadProbeToken())

        with pytest.raises(_AbortTransaction, match="例外終了"):
            with transaction.tenant_transaction_scope(
                make_tenant_context(_TENANT_ID)
            ) as tenant_transaction:
                tenant_transaction.run(_ReadProbeToken())
                raise _AbortTransaction("例外終了")

    assert len(created_sessions) == 2
    assert [session.close_calls for session in created_sessions] == [1, 1]
