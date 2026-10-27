"""RG1 の最小列権限と行ロックを隔離 PostgreSQL で確認する。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, LiteralString, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.rg1 import (
    RG1Unavailable,
    assert_rg1_open_before_commit,
    read_rg1_open,
)

if TYPE_CHECKING:
    from db_fixtures import DisposablePostgres

pytest_plugins = ("db_fixtures",)
_FUNCTION_BODY_DIR = (
    Path(__file__).resolve().parents[2]
    / "contracts/authz/product/function-bodies/functions"
)

_RG1_DEPENDENCY_ASSETS = (
    "roles/pitchlog_initial_actor.sql",
    "roles/pitchlog_rg1_control_owner.sql",
    "roles/pitchlog_rg1_control_actor.sql",
    "schemas/rg1_control.sql",
    "functions/FUNCTION:rg1_control:controller_lease_alive().sql",
)


def _create_rg1_fixture(connection: psycopg.Connection[Any]) -> None:
    """運用上の解除とは独立した一時DBに状態行と最小権限を作る。"""
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE ROLE pitchlog_rg1_fn_owner NOLOGIN NOSUPERUSER "
            "NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT"
        )
        cursor.execute(
            "CREATE TABLE public.rg1_restore_gate ("
            "singleton_id smallint PRIMARY KEY CHECK (singleton_id = 1), "
            "state text NOT NULL CHECK (state IN ('closed', 'open')))"
        )
        cursor.execute("INSERT INTO public.rg1_restore_gate VALUES (1, 'closed')")
        cursor.execute("ALTER TABLE public.rg1_restore_gate ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE public.rg1_restore_gate FORCE ROW LEVEL SECURITY")
        cursor.execute("GRANT USAGE ON SCHEMA public TO pitchlog_rg1_fn_owner")
        cursor.execute(
            "GRANT SELECT (singleton_id, state), UPDATE (singleton_id) "
            "ON public.rg1_restore_gate TO pitchlog_rg1_fn_owner"
        )
        cursor.execute(
            "CREATE POLICY rg1_fn_select_singleton ON public.rg1_restore_gate "
            "FOR SELECT TO pitchlog_rg1_fn_owner USING (singleton_id = 1)"
        )
        cursor.execute(
            "CREATE POLICY rg1_fn_lock_singleton ON public.rg1_restore_gate "
            "FOR UPDATE TO pitchlog_rg1_fn_owner "
            "USING (singleton_id = 1) WITH CHECK (singleton_id = 1)"
        )


def _install_rg1_product_functions(
    connection: psycopg.Connection[Any], body_dir: Path = _FUNCTION_BODY_DIR
) -> None:
    """製品候補の2関数を一時DBへ最小ACLで適用する。"""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            "CREATE ROLE pitchlog_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT"
        )
        cursor.execute(
            "CREATE ROLE pitchlog_outsider NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT"
        )
        for relative in _RG1_DEPENDENCY_ASSETS:
            body = (_FUNCTION_BODY_DIR.parent / relative).read_text(encoding="utf-8")
            cursor.execute(sql.SQL(cast(LiteralString, body)))
        cursor.execute("CREATE SCHEMA rg1_api")
        cursor.execute("REVOKE ALL ON SCHEMA rg1_api FROM PUBLIC")
        cursor.execute("GRANT USAGE ON SCHEMA rg1_api TO pitchlog_app")
        cursor.execute("GRANT USAGE ON SCHEMA rg1_api TO pitchlog_outsider")
        for function_name in (
            "rg1_read_open",
            "rg1_assert_open_before_commit",
        ):
            body = (body_dir / f"FUNCTION:rg1_api:{function_name}(uuid).sql").read_text(
                encoding="utf-8"
            )
            cursor.execute(sql.SQL(cast(LiteralString, body)))


@pytest.mark.parametrize("check", (read_rg1_open, assert_rg1_open_before_commit))
def test_rg1_real_scope_rejects_closed_and_rolls_back(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
    check: Callable[..., None],
) -> None:
    """Aの実行器と製品関数を通した拒否で同一scopeの変更を全取消する。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
            _install_rg1_product_functions(admin)
            admin.execute("CREATE TABLE public.rg1_rollback_probe (marker integer)")

        engine = create_engine(
            "postgresql+psycopg://", connect_args=conninfo_to_dict(cluster.admin_dsn)
        )
        original_binding = transaction._tenant_transaction

        @contextmanager
        def binding_with_probe(
            session: Session, context: TenantContext
        ) -> Iterator[None]:
            """検証用DMLを製品のテナント束縛済みtransactionへ置く。"""
            with original_binding(session, context):
                session.execute(
                    text("INSERT INTO public.rg1_rollback_probe VALUES (1)")
                )
                yield

        monkeypatch.setattr(transaction, "create_database_engine", lambda: engine)
        monkeypatch.setattr(transaction, "_tenant_transaction", binding_with_probe)
        try:
            with pytest.raises(RG1Unavailable, match="閉じている"):
                with transaction.tenant_transaction_scope(
                    make_tenant_context(uuid4())
                ) as scope:
                    check(scope)
            with psycopg.connect(cluster.admin_dsn, autocommit=True) as verify:
                assert verify.execute(
                    "SELECT count(*) FROM public.rg1_rollback_probe"
                ).fetchone() == (0,)
        finally:
            engine.dispose()


def test_rg1_function_install_rolls_back_before_grants_on_failure(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    tmp_path: Path,
) -> None:
    """2関数目の失敗で関数作成から公開権限まで全体を戻す。"""
    for name in ("rg1_read_open", "rg1_assert_open_before_commit"):
        source = _FUNCTION_BODY_DIR / f"FUNCTION:rg1_api:{name}(uuid).sql"
        target = tmp_path / source.name
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid).sql").write_text(
        "INVALID SQL", encoding="utf-8"
    )
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
            with pytest.raises(psycopg.errors.SyntaxError):
                _install_rg1_product_functions(admin, tmp_path)
            assert admin.execute(
                "SELECT to_regprocedure('rg1_api.rg1_read_open(uuid)')"
            ).fetchone() == (None,)
            assert (
                admin.execute(
                    "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname IN "
                    "('pitchlog_app','pitchlog_outsider','pitchlog_initial_actor',"
                    "'pitchlog_rg1_control_owner','pitchlog_rg1_control_actor')"
                ).fetchall()
                == []
            )
            assert (
                admin.execute(
                    "SELECT nspname FROM pg_catalog.pg_namespace "
                    "WHERE nspname IN ('rg1_api','rg1_control')"
                ).fetchall()
                == []
            )
            assert admin.execute(
                "SELECT singleton_id, state FROM public.rg1_restore_gate"
            ).fetchall() == [(1, "closed")]


def test_rg1_for_share_nowait_uses_only_singleton_column_update(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """承認した列UPDATEと2 policyで共有ロックし、他の変更権を拒む。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
            # 一時DBだけを開状態にし、行ロック機構の正常系を確認する。
            admin.execute(
                "UPDATE public.rg1_restore_gate "
                "SET state = 'open' WHERE singleton_id = 1"
            )
            with psycopg.connect(cluster.admin_dsn) as reader:
                reader.execute("SET ROLE pitchlog_rg1_fn_owner")
                row = reader.execute(
                    "SELECT state FROM public.rg1_restore_gate "
                    "WHERE singleton_id = 1 FOR SHARE NOWAIT"
                ).fetchone()
                assert row == ("open",)
                reader.commit()

                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    reader.execute(
                        "UPDATE public.rg1_restore_gate "
                        "SET state = 'open' WHERE singleton_id = 1"
                    )
                reader.rollback()
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    reader.execute(
                        "DELETE FROM public.rg1_restore_gate WHERE singleton_id = 1"
                    )
                reader.rollback()
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    reader.execute(
                        "INSERT INTO public.rg1_restore_gate VALUES (1, 'open')"
                    )
                reader.rollback()


def test_rg1_restore_first_rejects_nowait_without_waiting(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """復元側が先に状態行を更新したら通常側のNOWAITを拒否する。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
        with (
            psycopg.connect(cluster.admin_dsn) as restoration,
            psycopg.connect(cluster.admin_dsn) as writer,
        ):
            restoration.execute(
                "UPDATE public.rg1_restore_gate "
                "SET state = 'open' WHERE singleton_id = 1"
            )
            writer.execute("SET ROLE pitchlog_rg1_fn_owner")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                writer.execute(
                    "SELECT state FROM public.rg1_restore_gate "
                    "WHERE singleton_id = 1 FOR SHARE NOWAIT"
                )
            writer.rollback()
            restoration.rollback()


def test_rg1_writer_first_holds_share_lock_until_commit(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """通常側が先に共有ロックを取れば復元更新は確定まで待つ。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
        with (
            psycopg.connect(cluster.admin_dsn) as writer,
            psycopg.connect(cluster.admin_dsn) as restoration,
        ):
            writer.execute("SET ROLE pitchlog_rg1_fn_owner")
            assert writer.execute(
                "SELECT state FROM public.rg1_restore_gate "
                "WHERE singleton_id = 1 FOR SHARE NOWAIT"
            ).fetchone() == ("closed",)
            restoration.execute("SET LOCAL lock_timeout = '100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                restoration.execute(
                    "UPDATE public.rg1_restore_gate "
                    "SET state = 'open' WHERE singleton_id = 1"
                )
            restoration.rollback()
            writer.commit()
            restoration.execute(
                "UPDATE public.rg1_restore_gate "
                "SET state = 'open' WHERE singleton_id = 1"
            )
            restoration.commit()
            assert restoration.execute(
                "SELECT state FROM public.rg1_restore_gate WHERE singleton_id = 1"
            ).fetchone() == ("open",)


def test_rg1_product_functions_stay_closed_with_open_fixture(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """製品2関数は隔離DBのopen行でも成功を返さずtenant境界を保つ。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
            _install_rg1_product_functions(admin)
            assert admin.execute(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_catalog.pg_class "
                "WHERE oid = 'public.rg1_restore_gate'::regclass"
            ).fetchone() == (True, True)
            assert admin.execute(
                "SELECT rolcanlogin, rolbypassrls FROM pg_catalog.pg_roles "
                "WHERE rolname = 'pitchlog_rg1_fn_owner'"
            ).fetchone() == (False, False)
            assert admin.execute(
                "SELECT rolname, rolcanlogin, rolbypassrls, rolsuper, rolinherit "
                "FROM pg_catalog.pg_roles WHERE rolname IN "
                "('pitchlog_initial_actor','pitchlog_rg1_control_actor',"
                "'pitchlog_rg1_control_owner') ORDER BY rolname"
            ).fetchall() == [
                ("pitchlog_initial_actor", True, False, False, False),
                ("pitchlog_rg1_control_actor", True, False, False, False),
                ("pitchlog_rg1_control_owner", False, False, False, False),
            ]
            assert admin.execute(
                "SELECT count(*) FROM pg_catalog.pg_auth_members AS m "
                "JOIN pg_catalog.pg_roles AS r ON r.oid IN (m.roleid,m.member) "
                "WHERE r.rolname IN ('pitchlog_initial_actor',"
                "'pitchlog_rg1_control_actor','pitchlog_rg1_control_owner')"
            ).fetchone() == (0,)
            assert admin.execute(
                "SELECT has_function_privilege('pitchlog_app',"
                "'rg1_control.controller_lease_alive()','EXECUTE'), "
                "has_function_privilege('pitchlog_initial_actor',"
                "'rg1_control.controller_lease_alive()','EXECUTE')"
            ).fetchone() == (False, False)
            tenant_id = uuid4()
            with psycopg.connect(cluster.admin_dsn) as app:
                app.execute("SET ROLE pitchlog_app")
                app.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(tenant_id),),
                )
                for function_name in (
                    "rg1_read_open",
                    "rg1_assert_open_before_commit",
                ):
                    assert app.execute(
                        f"SELECT rg1_api.{function_name}(%s)", (tenant_id,)
                    ).fetchone() == (False,)
            admin.execute(
                "UPDATE public.rg1_restore_gate "
                "SET state = 'open' WHERE singleton_id = 1"
            )
            other_tenant_id = uuid4()
            with psycopg.connect(cluster.admin_dsn) as app:
                app.execute("SET ROLE pitchlog_app")
                for function_name in (
                    "rg1_read_open",
                    "rg1_assert_open_before_commit",
                ):
                    assert app.execute(
                        f"SELECT rg1_api.{function_name}(%s)", (tenant_id,)
                    ).fetchone() == (False,)
                    app.execute(
                        "SELECT set_config('app.tenant_id', %s, true)",
                        (str(tenant_id),),
                    )
                    assert app.execute(
                        f"SELECT rg1_api.{function_name}(%s)", (tenant_id,)
                    ).fetchone() == (False,)
                    assert app.execute(
                        f"SELECT rg1_api.{function_name}(%s)", (other_tenant_id,)
                    ).fetchone() == (False,)
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    app.execute("SELECT state FROM public.rg1_restore_gate")
                app.rollback()

            with psycopg.connect(cluster.admin_dsn) as outsider:
                outsider.execute("SET ROLE pitchlog_outsider")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    outsider.execute("SELECT rg1_api.rg1_read_open(%s)", (tenant_id,))
                outsider.rollback()


def test_rg1_product_functions_fail_closed_for_bad_context_and_missing_row(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """GUC不正と状態行欠損は2関数とも成功に変換しない。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
            _install_rg1_product_functions(admin)
            tenant_id = uuid4()
            with psycopg.connect(cluster.admin_dsn) as app:
                for function_name in (
                    "rg1_read_open",
                    "rg1_assert_open_before_commit",
                ):
                    app.execute("SET ROLE pitchlog_app")
                    app.execute("SELECT set_config('app.tenant_id', 'invalid', true)")
                    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
                        app.execute(f"SELECT rg1_api.{function_name}(%s)", (tenant_id,))
                    app.rollback()

                admin.execute(
                    "DELETE FROM public.rg1_restore_gate WHERE singleton_id = 1"
                )
                for function_name in (
                    "rg1_read_open",
                    "rg1_assert_open_before_commit",
                ):
                    app.execute("SET ROLE pitchlog_app")
                    app.execute(
                        "SELECT set_config('app.tenant_id', %s, true)",
                        (str(tenant_id),),
                    )
                    with pytest.raises(psycopg.Error) as error:
                        app.execute(f"SELECT rg1_api.{function_name}(%s)", (tenant_id,))
                    assert error.value.sqlstate == "P0002"
                    app.rollback()


def test_rg1_product_functions_fail_closed_for_unknown_state(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """隔離DBで状態制約を故意に壊しても製品関数は開かない。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
            _install_rg1_product_functions(admin)
            admin.execute(
                "ALTER TABLE public.rg1_restore_gate "
                "DROP CONSTRAINT rg1_restore_gate_state_check"
            )
            admin.execute(
                "UPDATE public.rg1_restore_gate "
                "SET state = 'unknown' WHERE singleton_id = 1"
            )
            tenant_id = uuid4()
            with psycopg.connect(cluster.admin_dsn) as app:
                app.execute("SET ROLE pitchlog_app")
                app.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(tenant_id),),
                )
                for function_name in (
                    "rg1_read_open",
                    "rg1_assert_open_before_commit",
                ):
                    assert app.execute(
                        f"SELECT rg1_api.{function_name}(%s)", (tenant_id,)
                    ).fetchone() == (False,)


def test_rg1_commit_function_rejects_restoration_lock_contention(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """復元更新が先行すれば製品関数の直前照合はNOWAITで拒否する。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            _create_rg1_fixture(admin)
            _install_rg1_product_functions(admin)
        with (
            psycopg.connect(cluster.admin_dsn) as restoration,
            psycopg.connect(cluster.admin_dsn) as app,
        ):
            restoration.execute(
                "UPDATE public.rg1_restore_gate "
                "SET state = 'open' WHERE singleton_id = 1"
            )
            app.execute("SET ROLE pitchlog_app")
            tenant_id = uuid4()
            app.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(tenant_id),),
            )
            with pytest.raises(psycopg.errors.LockNotAvailable):
                app.execute(
                    "SELECT rg1_api.rg1_assert_open_before_commit(%s)",
                    (tenant_id,),
                )
            app.rollback()
            restoration.rollback()
