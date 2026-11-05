"""実PGで成績の同snapshot/READ ONLY/有限能力と終了失効を検査する。"""

from __future__ import annotations

import pytest
from psycopg.errors import ReadOnlySqlTransaction
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import transaction
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.play_export_primitives import (
    PrimitiveReadError,
    ReadPlayExportPrimitives,
)

from .test_tenant_transaction_scope import (
    _TENANT_ID,
    _configure_application_database,
    _transaction_database,
    _WriteProbeToken,
)

pytestmark = pytest.mark.requires_db


def test_real_stats_scope_is_rr_read_only_and_rejects_non_read_tokens(
    disposable_postgres_cluster,
    monkeypatch,
) -> None:
    """実driverのBEGIN設定と、既UPDATE権限でもDBが拒否することを確認する。"""
    observed = []

    def observe_begin(session, db_transaction, connection):
        observed.append(
            (
                connection.get_isolation_level(),
                connection.exec_driver_sql("SHOW transaction_read_only").scalar_one(),
            )
        )

    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        event.listen(Session, "after_begin", observe_begin)
        try:
            with transaction.stats_primitive_read_scope(
                make_tenant_context(_TENANT_ID)
            ) as handle:
                transaction._require_stats_primitive_read_scope(handle)
                reader = ReadPlayExportPrimitives(handle, maximum_integer_chars=20000)
                for method in (handle.run, handle.run_function):
                    with pytest.raises(TenantBindingError):
                        method(_WriteProbeToken())
                assert observed == [("REPEATABLE READ", "on")]
                # 試験だけがprivate runtimeを観測する。
                # 公開readerにSession/自由SQLは渡さない。
                session = transaction._TRANSACTION_RUNTIMES[handle._state_key][0]
                with pytest.raises(DBAPIError) as rejected:
                    session.execute(
                        text(
                            "UPDATE public.tenant_transaction_probe "
                            "SET marker='forbidden'"
                        )
                    )
                assert isinstance(rejected.value.orig, ReadOnlySqlTransaction)
                assert rejected.value.orig.sqlstate == "25006"
            with pytest.raises(TenantBindingError):
                transaction._require_stats_primitive_read_scope(handle)
            with pytest.raises(PrimitiveReadError) as expired:
                reader._live()
            assert isinstance(expired.value.__cause__, TenantBindingError)
        finally:
            event.remove(Session, "after_begin", observe_begin)
        with database.admin_engine.connect() as admin:
            assert (
                admin.execute(
                    text("SELECT marker FROM public.tenant_transaction_probe")
                ).scalar_one()
                == "original"
            )


def test_real_writable_scope_cannot_issue_stats_snapshot(
    disposable_postgres_cluster, monkeypatch
) -> None:
    """通常scopeの実handleを借用して同snapshotを名乗れない。"""
    with _transaction_database(disposable_postgres_cluster) as database:
        _configure_application_database(monkeypatch, database)
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as handle:
            with pytest.raises(TenantBindingError):
                transaction._require_stats_primitive_read_scope(handle)
            with pytest.raises(PrimitiveReadError) as unbound:
                ReadPlayExportPrimitives(handle, maximum_integer_chars=20000)
            assert isinstance(unbound.value.__cause__, TenantBindingError)
