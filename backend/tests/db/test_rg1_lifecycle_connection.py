"""実PGでRG1制御primitiveの境界を検査する。fresh/UI成功証拠ではない。"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from .conftest import DisposablePostgres
from .rg1_lifecycle_support import (
    ACTOR,
    APP,
    NAMESPACE,
    LifecycleDatabase,
    lifecycle_database,
    observed_identity,
    wait_until,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture
def lifecycle_pg(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[LifecycleDatabase]:
    """外部DSNを使わず所有Disposableだけを起動する。"""
    monkeypatch.delenv("PITCHLOG_TEST_ADMIN_DSN", raising=False)
    monkeypatch.setenv(
        "PITCHLOG_TEST_ROLE_DSN", "dbname=unused user=unused password=unused"
    )
    with lifecycle_database(disposable_postgres_cluster, monkeypatch) as database:
        yield database


@pytest.fixture(autouse=True)
def verify_connection_identities(lifecycle_pg: LifecycleDatabase) -> None:
    """共通外部DSN検査の代わりに所有DBの実admin/app/actor認証を全て照合する。"""
    with psycopg.connect(lifecycle_pg.admin_dsn) as admin:
        expected = conninfo_to_dict(lifecycle_pg.admin_dsn)["user"]
        assert admin.execute("SELECT session_user, current_user").fetchone() == (
            expected,
            expected,
        )
    for role in (APP, ACTOR):
        with lifecycle_pg.peer(role) as peer:
            assert peer.query("SELECT session_user, current_user") == (
                f"{role}|{role}",
            )


def test_rg1_real_peer_sql_acl_commit_and_liveness_boundaries(
    lifecycle_pg: LifecycleDatabase,
) -> None:
    """正規peerと製品ACLで制御SQLを検査し、freshや作成成功へ拡張しない。"""
    database = lifecycle_pg
    with (
        psycopg.connect(database.admin_dsn, autocommit=True) as admin,
        database.peer() as controller,
        database.peer() as contender,
        database.peer(APP) as app,
    ):
        control_functions = (
            "try_controller_lease",
            "release_controller_lease",
            "close_gate",
            "open_fresh_gate",
            "controller_lease_alive",
            "read_closed_gate",
        )
        for name in control_functions:
            assert app.execute(f"SELECT rg1_control.{name}()")[1] == "42501"
        for statement in (
            "SELECT * FROM public.rg1_restore_gate",
            "UPDATE public.rg1_restore_gate SET state='open' WHERE singleton_id=1",
            "SET ROLE pitchlog_rg1_control_owner",
            "SET ROLE pitchlog_rg1_control_actor",
            "CREATE TEMP TABLE rg1_forbidden (id integer)",
        ):
            assert app.execute(statement)[1] == "42501"
        assert controller.execute("SELECT * FROM public.rg1_restore_gate")[1] == "42501"

        tenant = uuid4()
        assert (
            app.execute(f"SELECT rg1_control.scope_binding('{tenant}'::uuid)")[1]
            == "42501"
        )
        app.query("BEGIN")
        # tenant contextは入力整合専用。任意GUCをlease/freshのproofにしない。
        app.query(f"SELECT set_config('app.tenant_id','{tenant}',true)")
        pid = int(app.query("SELECT pg_catalog.pg_backend_pid()")[0])
        binding = json.loads(
            app.query(f"SELECT rg1_control.scope_binding('{tenant}'::uuid)")[0]
        )
        assert binding == observed_identity(admin, pid)
        assert (
            app.execute(f"SELECT rg1_control.scope_binding('{uuid4()}'::uuid)")[1]
            == "42501"
        )
        app.query("ROLLBACK")

        # 旧open行、appの同key、異なるPIDへ分散したlockは生存でない。
        admin.execute("UPDATE public.rg1_restore_gate SET state='open'")
        assert contender.query("SELECT rg1_control.controller_lease_alive()") == ("f",)
        admin.execute("UPDATE public.rg1_restore_gate SET state='closed'")
        app.query(f"SELECT pg_catalog.pg_advisory_lock({NAMESPACE},1)")
        app.query(f"SELECT pg_catalog.pg_advisory_lock({NAMESPACE},2)")
        assert contender.query("SELECT rg1_control.controller_lease_alive()") == ("f",)
        app.query("SELECT pg_catalog.pg_advisory_unlock_all()")
        assert controller.query("SELECT rg1_control.try_controller_lease()") == ("t",)
        assert controller.query("SELECT rg1_control.try_controller_lease()") == ("t",)
        assert contender.query("SELECT rg1_control.try_controller_lease()") == ("f",)
        assert contender.query("SELECT rg1_control.open_fresh_gate()") == ("f",)
        assert contender.execute("SELECT rg1_control.read_closed_gate()")[1] == "55000"
        contender.query(f"SELECT pg_catalog.pg_advisory_lock({NAMESPACE},2)")
        assert contender.query("SELECT rg1_control.controller_lease_alive()") == ("f",)
        contender.query("SELECT pg_catalog.pg_advisory_unlock_all()")

        controller_pid = int(controller.query("SELECT pg_backend_pid()")[0])
        closed = json.loads(
            controller.query("SELECT rg1_control.read_closed_gate()")[0]
        )
        assert closed == {
            **observed_identity(admin, controller_pid),
            "gate_state": "closed",
        }
        # SQL primitiveのみ。実DurableLedger.fresh_activation証明を代用しない。
        assert controller.query("SELECT rg1_control.open_fresh_gate()") == ("t",)
        assert contender.query("SELECT rg1_control.controller_lease_alive()") == ("t",)
        controller.query("BEGIN")
        assert controller.query("SELECT rg1_control.close_gate()") == ("t",)
        assert controller.query("SELECT rg1_control.open_fresh_gate()") == ("f",)
        assert controller.query("SELECT rg1_control.release_controller_lease()") == (
            "f",
        )
        assert controller.execute("SELECT rg1_control.read_closed_gate()")[1] == "55000"
        controller.query("ROLLBACK")
        assert contender.query("SELECT rg1_control.controller_lease_alive()") == ("t",)
        assert admin.execute(
            "SELECT state FROM public.rg1_restore_gate"
        ).fetchone() == ("open",)

        # 旧read2は常falseを保持。共有lockの排出は既存read ownerの実列ACLで検査。
        app.query("BEGIN")
        app.query(f"SELECT set_config('app.tenant_id','{tenant}',true)")
        assert app.query(f"SELECT rg1_api.rg1_read_open('{tenant}'::uuid)") == ("f",)
        app.query("ROLLBACK")
        with psycopg.connect(database.admin_dsn) as reader:
            reader.execute("SET ROLE pitchlog_rg1_fn_owner")
            assert reader.execute(
                "SELECT state FROM public.rg1_restore_gate "
                "WHERE singleton_id=1 FOR SHARE"
            ).fetchone() == ("open",)
            controller.query("BEGIN")
            controller.query("SET LOCAL lock_timeout='5s'")
            with ThreadPoolExecutor(max_workers=1) as pool:
                closing = pool.submit(
                    controller.query, "SELECT rg1_control.close_gate()"
                )
                wait_until(
                    lambda: (
                        admin.execute(
                            "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_locks "
                            "WHERE pid=%s AND NOT granted)",
                            (controller_pid,),
                        ).fetchone()
                        == (True,)
                    )
                )
                assert not closing.done()
                reader.rollback()
                assert closing.result(timeout=6) == ("t",)
            controller.query("COMMIT")
        assert contender.query("SELECT rg1_control.controller_lease_alive()") == ("t",)
        assert controller.query("SELECT rg1_control.release_controller_lease()") == (
            "t",
        )
        # 再入2回でも1回解放でcontrollerを取得可能。open→controller両方が消える。
        assert contender.query("SELECT rg1_control.controller_lease_alive()") == ("f",)
        assert contender.query("SELECT rg1_control.try_controller_lease()") == ("t",)
        assert contender.query("SELECT rg1_control.release_controller_lease()") == (
            "t",
        )

        # 同clusterの別DBで同actor/PIDが両keyを保持しても元DBのleaseではない。
        admin.execute("CREATE DATABASE rg1_other_database")
        with database.peer(database="rg1_other_database") as other_database:
            other_database.query(f"SELECT pg_catalog.pg_advisory_lock({NAMESPACE},1)")
            other_database.query(f"SELECT pg_catalog.pg_advisory_lock({NAMESPACE},2)")
            assert contender.query("SELECT rg1_control.controller_lease_alive()") == (
                "f",
            )

        assert controller.query("SELECT rg1_control.try_controller_lease()") == ("t",)
        assert controller.query("SELECT rg1_control.open_fresh_gate()") == ("t",)
        assert contender.query("SELECT rg1_control.controller_lease_alive()") == ("t",)

        # 全server再起動では行openが残ってもsession leaseは復元されない。
        database = database.restart()

        def restarted() -> bool:
            try:
                with psycopg.connect(
                    database.admin_dsn, connect_timeout=1
                ) as connection:
                    return connection.execute("SELECT 1").fetchone() == (1,)
            except psycopg.OperationalError:
                return False

        wait_until(restarted)
        with psycopg.connect(database.admin_dsn, autocommit=True) as after_admin:
            assert after_admin.execute(
                "SELECT state FROM public.rg1_restore_gate"
            ).fetchone() == ("open",)
        with database.peer() as after_restart:
            assert after_restart.query(
                "SELECT rg1_control.controller_lease_alive()"
            ) == ("f",)
            assert after_restart.query("SELECT rg1_control.open_fresh_gate()") == ("f",)
            assert after_restart.query("SELECT rg1_control.try_controller_lease()") == (
                "t",
            )
            assert (
                after_restart.execute("SELECT rg1_control.read_closed_gate()")[1]
                == "55000"
            )
            assert after_restart.query("SELECT rg1_control.close_gate()") == ("t",)
            assert after_restart.query(
                "SELECT rg1_control.release_controller_lease()"
            ) == ("t",)
