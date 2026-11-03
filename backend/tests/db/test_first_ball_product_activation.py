"""正式installerだけを使う初球印のowned PG受入。共有DSNへ接続しない。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from pitchlog.authz.product_provisioning import apply_product_authz_ddl

from . import test_initial_recording_right_scope as _initial_scope
from .first_ball_stamp_support import exec_text, peer
from .sync_writer_binding_support import APP
from .test_first_ball_stamp_issuance import (
    _bind,
    _insert,
    _make_env,
    _new_attempt,
    _right,
)

pytestmark = pytest.mark.requires_db
admin_connection = _initial_scope.admin_connection
tested_role_connection = _initial_scope.tested_role_connection


@pytest.fixture
def activated() -> Iterator[Any]:
    """正規installerを実適用した自己所有PGを、後付けcandidate DDLなしで得る。"""
    with pytest.MonkeyPatch.context() as patch:
        with contextmanager(_make_env)(patch, apply=True) as env:
            yield env


@pytest.fixture
def initial_scope_database(activated: Any) -> Any:
    """既identity autouseへ同じ自己所有primaryの実接続を委譲する。"""
    return activated.owner


def test_formal_installer_issues_and_consumes_without_manual_stamp(
    activated: Any,
) -> None:
    """実appのbind/right成功だけから印を発行しINSERT1回で消費する。"""
    env = activated
    row = uuid4()
    with peer(env.db, APP) as writer:
        event, binding = _new_attempt(env, writer)
        assert _bind(writer, env, binding)[:2] == (("t",), "00000")
        assert _right(writer, env, binding)[:2] == (("t|t",), "00000")
        assert _insert(writer, env, event, row)[1] == "00000"
        assert writer.run("COMMIT")[1] == "00000"
    assert env.ctx.stamp_row(binding) == [
        ["consumed", str(event["id"]), str(row), True]
    ]


@pytest.mark.parametrize(
    "statement",
    (
        "ALTER TABLE public.play_rows DISABLE TRIGGER trg_first_ball_10_lock",
        "DROP TRIGGER trg_first_ball_10_lock ON public.play_rows",
        "DROP TRIGGER trg_first_ball_20_admit ON public.play_rows",
        "ALTER TRIGGER trg_first_ball_10_lock ON public.play_rows RENAME TO bad_order",
        "CREATE TRIGGER extra_stamp BEFORE INSERT ON public.play_rows FOR "
        "EACH ROW EXECUTE FUNCTION sync_right_api.guard_first_ball_projection_lock()",
        "ALTER FUNCTION sync_right_api.guard_first_ball_projection_lock() "
        "SECURITY DEFINER",
        "GRANT EXECUTE ON FUNCTION "
        "sync_right_api.guard_first_ball_projection_lock() TO pitchlog_app",
        "GRANT EXECUTE ON FUNCTION "
        "sync_right_api.guard_first_ball_projection_admission() TO PUBLIC",
    ),
)
def test_reapply_rejects_trigger_or_function_collision(
    activated: Any, statement: str
) -> None:
    """再適用で欠損/余剰/無効/改変を自動修復せず、transactionを取消す。"""
    with psycopg.connect(activated.ctx.admin_dsn) as conn:
        try:
            exec_text(conn, statement)
            conn.commit()  # installerはIDLE接続だけを受ける。改変済みのowned DBを渡す。
            with pytest.raises(psycopg.Error):
                apply_product_authz_ddl(conn)
        finally:
            conn.rollback()
        # 改変済みDBを自動修復しない。fixtureの自己所有DBを試験後に破棄する。


def test_old_body_is_not_upgraded_in_place(activated: Any) -> None:
    """旧0037本文へ正式installerを適用しても黙って置換しない。"""
    from .test_first_ball_stamp_issuance import _old_bind_replace_sql

    with psycopg.connect(activated.ctx.admin_dsn) as conn:
        try:
            exec_text(conn, _old_bind_replace_sql())
            before = conn.execute(
                "SELECT md5(prosrc) FROM pg_proc WHERE "
                "oid='sync_right_api.bind_device(uuid,uuid,uuid,bytea,uuid,uuid,bytea)'::regprocedure"
            ).fetchone()
            assert before is not None
            conn.commit()
            with pytest.raises(psycopg.Error):
                apply_product_authz_ddl(conn)
            after = conn.execute(
                "SELECT md5(prosrc) FROM pg_proc WHERE "
                "oid='sync_right_api.bind_device(uuid,uuid,uuid,bytea,uuid,uuid,bytea)'::regprocedure"
            ).fetchone()
            assert after == before, "拒否時に旧本文を黙って置換しない"
        finally:
            conn.rollback()
        # このDBはfixture終了時に破棄し、共有環境へ適用しない。
