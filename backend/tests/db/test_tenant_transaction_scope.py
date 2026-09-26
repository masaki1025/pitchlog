"""テナントトランザクション単位の失敗契約を実 PostgreSQL で固定する。"""

from __future__ import annotations

import importlib
import inspect
import secrets
from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, ModuleType, TracebackType
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
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.context import TenantContext
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


class _ScopeEntryFailure(RuntimeError):
    """ハンドル生成後の scope 開始失敗を表すテスト専用例外。"""


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


def _instance_state_graph(*roots: object) -> Iterator[object]:
    """非公開名を除外せず、インスタンス状態から到達できる値を列挙する。

    Args:
        *roots: 到達グラフの起点にするインスタンス。

    Yields:
        ``__dict__`` と全 MRO の ``__slots__``、組み込み container から
        到達できる値。class・関数・module の大域状態は辿らない。
    """
    pending = list(roots)
    visited: set[int] = set()
    while pending:
        value = pending.pop()
        identity = id(value)
        if identity in visited:
            continue
        visited.add(identity)
        yield value

        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)

        instance_values = getattr(value, "__dict__", None)
        if isinstance(instance_values, dict):
            pending.extend(instance_values.values())
        for class_type in type(value).__mro__:
            raw_slots = vars(class_type).get("__slots__", ())
            slots = (raw_slots,) if isinstance(raw_slots, str) else raw_slots
            for slot in slots:
                if slot in {"__dict__", "__weakref__"}:
                    continue
                try:
                    pending.append(getattr(value, slot))
                except AttributeError:
                    pass


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


def test_scope_rejects_tampered_context_before_session_creation(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """改竄済み文脈を Session 生成と SQL 発行より前に拒否する。"""
    transaction = _transaction_module()
    created_sessions: list[Session] = []
    observed_statements: list[str] = []

    class _PreflightObservedSession(Session):
        """入口検査より前に Session が生成されないことを観測する。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """生成された Session を観測対象へ登録する。"""
            super().__init__(*args, **kwargs)
            created_sessions.append(self)

    def observe_orm_sql(execute_state: object) -> None:
        observed_statements.append(str(getattr(execute_state, "statement", "")))

    context = make_tenant_context(_TENANT_ID)
    object.__setattr__(
        context,
        "tenant_id",
        UUID("00000000-0000-0000-0000-000000000445"),
    )

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(transaction, "Session", _PreflightObservedSession)
        event.listen(Session, "do_orm_execute", observe_orm_sql)
        try:
            with pytest.raises(TenantBindingError, match="発行証跡が不一致"):
                with transaction.tenant_transaction_scope(context):
                    pytest.fail("改竄済み文脈で scope 本体へ到達した")
        finally:
            event.remove(Session, "do_orm_execute", observe_orm_sql)

    assert created_sessions == []
    assert observed_statements == []


def test_scope_rejects_non_exact_tenant_context_subclass(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TenantContext の派生型を exact 型検査で Session 生成前に拒否する。"""
    transaction = _transaction_module()
    created_sessions: list[Session] = []
    observed_statements: list[str] = []

    class _PreflightObservedSession(Session):
        """入口検査より前に Session が生成されないことを観測する。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """生成された Session を観測対象へ登録する。"""
            super().__init__(*args, **kwargs)
            created_sessions.append(self)

    def observe_orm_sql(execute_state: object) -> None:
        observed_statements.append(str(getattr(execute_state, "statement", "")))

    derived_type = type(
        "_DerivedTenantContext",
        (cast(type[Any], TenantContext),),
        {},
    )
    derived_context = cast(TenantContext, derived_type(_TENANT_ID))

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(transaction, "Session", _PreflightObservedSession)
        event.listen(Session, "do_orm_execute", observe_orm_sql)
        try:
            with pytest.raises(TenantBindingError, match="TenantContext が無い"):
                with transaction.tenant_transaction_scope(derived_context):
                    pytest.fail("TenantContext 派生型で scope 本体へ到達した")
        finally:
            event.remove(Session, "do_orm_execute", observe_orm_sql)

    assert created_sessions == []
    assert observed_statements == []


def test_run_rejects_context_changed_after_binding(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """束縛後に改竄された文脈を operation SQL の発行前に拒否する。"""
    transaction = _transaction_module()
    observed_statements: list[str] = []

    def observe_orm_sql(execute_state: object) -> None:
        observed_statements.append(str(getattr(execute_state, "statement", "")))

    context = make_tenant_context(_TENANT_ID)
    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(
            repository_base,
            "_OPERATION_REGISTRY",
            MappingProxyType({_ReadProbeToken: _read_operation()}),
        )
        event.listen(Session, "do_orm_execute", observe_orm_sql)
        try:
            with transaction.tenant_transaction_scope(context) as handle:
                statements_after_binding = len(observed_statements)
                object.__setattr__(
                    context,
                    "tenant_id",
                    UUID("00000000-0000-0000-0000-000000000445"),
                )
                with pytest.raises(TenantBindingError, match="発行証跡が不一致"):
                    handle.run(_ReadProbeToken())
        finally:
            event.remove(Session, "do_orm_execute", observe_orm_sql)

    assert observed_statements[:statements_after_binding] == [_BINDING_STATEMENT]
    assert observed_statements[statements_after_binding:] == []


def test_run_signature_has_no_second_tenant_context() -> None:
    """Run が operation だけを受け、別文脈を混ぜる口を公開しない。"""
    transaction = _transaction_module()
    handle_type = transaction._TenantTransaction

    signature = inspect.signature(handle_type.run)
    hints = get_type_hints(handle_type.run)
    declared_methods = {
        name for name, value in vars(handle_type).items() if inspect.isfunction(value)
    }

    assert tuple(signature.parameters) == ("self", "operation")
    assert hints == {
        "operation": TenantOperationToken,
        "return": TenantOperationResult,
    }
    assert declared_methods == {"__init__", "_expire", "run"}
    assert handle_type.__slots__ == (
        "_state_key",
        "_context",
        "_bound_tenant_id",
        "_bound_integrity_proof",
    )
    assert getattr(handle_type, "__final__", False) is True


def test_transaction_handle_is_not_publicly_constructible() -> None:
    """公開面から型を取得できず、私有型を得ても scope 外で生成できない。"""
    transaction = _transaction_module()
    handle_type = transaction._TenantTransaction
    context = make_tenant_context(_TENANT_ID)
    public_attributes = {
        name: value
        for name, value in vars(transaction).items()
        if not name.startswith("_")
    }

    assert transaction.__all__ == ("tenant_transaction_scope",)
    assert not hasattr(transaction, "TenantTransaction")
    assert handle_type not in public_attributes.values()

    constructor = cast(Callable[..., object], handle_type)
    arbitrary_session = Session()
    try:
        with pytest.raises(TypeError):
            constructor(arbitrary_session, context)
    finally:
        arbitrary_session.close()

    with pytest.raises(RuntimeError, match="scope だけが生成"):
        constructor(context, object(), _TENANT_ID, b"proof", object())
    with pytest.raises(RuntimeError, match="登録していない実行状態"):
        constructor(
            context,
            object(),
            _TENANT_ID,
            b"proof",
            transaction._HANDLE_CREATION_TOKEN,
        )


def test_transaction_handle_does_not_expose_session(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handle と scope の全 private 状態から Session へ到達できない。"""
    transaction = _transaction_module()

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        scope = transaction.tenant_transaction_scope(make_tenant_context(_TENANT_ID))
        assert not any(
            isinstance(value, Session) for value in _instance_state_graph(scope)
        )

        with scope as handle:
            assert not any(
                isinstance(value, Session)
                for value in _instance_state_graph(scope, handle)
            )

        assert not any(
            isinstance(value, Session) for value in _instance_state_graph(scope, handle)
        )


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


def test_handle_cannot_run_after_scope_exit(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scope 終了後の run を SQL 発行前に拒否する。"""
    transaction = _transaction_module()
    observed_statements: list[str] = []

    def observe_orm_sql(execute_state: object) -> None:
        observed_statements.append(str(getattr(execute_state, "statement", "")))

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(
            repository_base,
            "_OPERATION_REGISTRY",
            MappingProxyType({_ReadProbeToken: _read_operation()}),
        )
        event.listen(Session, "do_orm_execute", observe_orm_sql)
        try:
            with transaction.tenant_transaction_scope(
                make_tenant_context(_TENANT_ID)
            ) as handle:
                assert handle.run(_ReadProbeToken()).rows == (("original",),)

            statements_after_exit = len(observed_statements)
            with pytest.raises(RuntimeError, match="失効"):
                handle.run(_ReadProbeToken())
        finally:
            event.remove(Session, "do_orm_execute", observe_orm_sql)

    assert observed_statements[:statements_after_exit] == [
        _BINDING_STATEMENT,
        str(_READ_STATEMENT),
    ]
    assert observed_statements[statements_after_exit:] == []


def test_handle_is_invalidated_when_scope_entry_fails(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handle 生成後に scope 開始が失敗しても失効し、Session を閉じる。"""
    transaction = _transaction_module()
    real_handle_type = transaction._TenantTransaction
    created_handles: list[Any] = []
    created_sessions: list[_EntryFailureObservedSession] = []
    observed_statements: list[str] = []

    class _EntryFailureObservedSession(Session):
        """Scope 開始失敗時の close を観測する Session。"""

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

    class _FailingScope(AbstractContextManager[None]):
        """Enter で必ず失敗する transaction context。"""

        def __enter__(self) -> None:
            """Handle 生成後の開始失敗を発生させる。"""
            raise _ScopeEntryFailure("scope 開始失敗")

        def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            """Enter が失敗するため終了処理は行わない。"""
            del exception_type, exception, traceback

    def capture_handle(*args: Any, **kwargs: Any) -> Any:
        handle = real_handle_type(*args, **kwargs)
        created_handles.append(handle)
        return handle

    def fail_scope(session: object, context: object) -> AbstractContextManager[None]:
        del session, context
        return _FailingScope()

    def observe_orm_sql(execute_state: object) -> None:
        observed_statements.append(str(getattr(execute_state, "statement", "")))

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(transaction, "Session", _EntryFailureObservedSession)
        monkeypatch.setattr(transaction, "_TenantTransaction", capture_handle)
        monkeypatch.setattr(transaction, "_tenant_transaction", fail_scope)
        event.listen(Session, "do_orm_execute", observe_orm_sql)
        try:
            scope = transaction.tenant_transaction_scope(
                make_tenant_context(_TENANT_ID)
            )
            with pytest.raises(_ScopeEntryFailure, match="scope 開始失敗"):
                with scope:
                    pytest.fail("開始失敗後に scope 本体へ到達した")

            assert len(created_handles) == 1
            handle = created_handles[0]
            statements_after_failure = len(observed_statements)
            with pytest.raises(RuntimeError, match="失効"):
                handle.run(_ReadProbeToken())
        finally:
            event.remove(Session, "do_orm_execute", observe_orm_sql)

    assert len(created_sessions) == 1
    assert created_sessions[0].close_calls == 1
    assert observed_statements[statements_after_failure:] == []
    assert not any(
        isinstance(value, Session) for value in _instance_state_graph(scope, handle)
    )


def test_scope_factory_creates_distinct_sessions_for_each_context(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scope ごとに新しい Session を生成し、異なる文脈間で共有しない。"""
    transaction = _transaction_module()
    created_sessions: list[_FactoryObservedSession] = []
    lifecycle: list[tuple[str, Session]] = []

    class _FactoryObservedSession(Session):
        """生成順と close 順を強参照つきで観測する Session。"""

        close_calls: int

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """生成された Session を観測対象へ登録する。"""
            super().__init__(*args, **kwargs)
            self.close_calls = 0
            created_sessions.append(self)
            lifecycle.append(("created", self))

        def close(self) -> None:
            """Close 呼び出しを記録して通常の解放処理へ委譲する。"""
            self.close_calls += 1
            lifecycle.append(("closed", self))
            super().close()

    first_context = make_tenant_context(_TENANT_ID)
    second_context = make_tenant_context(UUID("00000000-0000-0000-0000-000000000445"))

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        monkeypatch.setattr(transaction, "Session", _FactoryObservedSession)

        with transaction.tenant_transaction_scope(first_context):
            assert len(created_sessions) == 1
            first_session = created_sessions[0]
            assert first_session.close_calls == 0

        assert first_session.close_calls == 1
        assert lifecycle == [
            ("created", first_session),
            ("closed", first_session),
        ]

        with transaction.tenant_transaction_scope(second_context):
            assert len(created_sessions) == 2
            second_session = created_sessions[1]
            assert second_session is not first_session
            assert first_session.close_calls == 1
            assert second_session.close_calls == 0

        assert second_session.close_calls == 1

    assert lifecycle == [
        ("created", first_session),
        ("closed", first_session),
        ("created", second_session),
        ("closed", second_session),
    ]
