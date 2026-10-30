"""通常投球private原本のmigrationと非公開境界をowned PGで検証する。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from db_fixtures import _dsn_names
from psycopg.conninfo import conninfo_to_dict

from pitchlog.db.writer_binding.ordinary_models import (
    OrdinaryPitchCheckpoint,
    OrdinaryPitchHistory,
    OrdinaryPitchWriteAdmission,
)

from .first_ball_stamp_support import StderrPeer
from .sync_writer_binding_support import owned_binding_database

pytestmark = pytest.mark.requires_db


@pytest.fixture(scope="module")
def storage_owner() -> Iterator[Any]:
    """共有DSNを使わない既所有fixtureで実migration headへ進める。"""
    with pytest.MonkeyPatch.context() as patch:
        with owned_binding_database(patch) as owner:
            admin_name, role_name = _dsn_names()
            patch.setenv(admin_name, owner.authority.database.primary_admin)
            patch.setenv(role_name, owner.authority.database.endpoints.primary_dsn)
            yield owner


@pytest.fixture
def admin_connection(storage_owner: Any) -> Iterator[psycopg.Connection]:
    """既identity検査へ同じ所有primaryの実管理接続を渡す。"""
    with psycopg.connect(storage_owner.authority.database.primary_admin) as conn:
        yield conn


@pytest.fixture
def tested_role_connection(storage_owner: Any) -> Iterator[psycopg.Connection]:
    """既identity検査へ同じ所有primaryの実限定role接続を渡す。"""
    with psycopg.connect(
        storage_owner.authority.database.endpoints.primary_dsn
    ) as conn:
        yield conn


def test_storage_schema_matches_models(storage_owner: Any) -> None:
    """列とPKの差を検出し、履歴版ごとの原本保持を確認する。"""
    with psycopg.connect(storage_owner.authority.database.business_admin) as conn:
        for model in (
            OrdinaryPitchCheckpoint,
            OrdinaryPitchHistory,
            OrdinaryPitchWriteAdmission,
        ):
            table = model.__table__
            columns = conn.execute(
                "SELECT column_name,is_nullable FROM information_schema.columns "
                "WHERE table_schema='sync_fence' AND table_name=%s "
                "ORDER BY ordinal_position",
                (table.name,),
            ).fetchall()
            assert columns == [
                (column.name, "YES" if column.nullable else "NO")
                for column in table.columns
            ]
            primary = conn.execute(
                "SELECT a.attname FROM pg_catalog.pg_constraint c "
                "JOIN pg_catalog.pg_class t ON t.oid=c.conrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace "
                "CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum,i) "
                "JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid "
                "AND a.attnum=k.attnum "
                "WHERE n.nspname='sync_fence' AND t.relname=%s "
                "AND c.contype='p' ORDER BY k.i",
                (table.name,),
            ).fetchall()
            assert [row[0] for row in primary] == [
                column.name for column in table.primary_key
            ]


def test_storage_is_forced_rls_without_direct_app_access(storage_owner: Any) -> None:
    """migration自体ではappへ表権限・policy・default権限を開けない。"""
    with psycopg.connect(storage_owner.authority.database.business_admin) as conn:
        for name in (
            "ordinary_pitch_checkpoints",
            "ordinary_pitch_history",
            "ordinary_pitch_write_admissions",
        ):
            qualified = f"sync_fence.{name}"
            assert conn.execute(
                "SELECT c.relrowsecurity,c.relforcerowsecurity,r.rolname "
                "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles r "
                "ON r.oid=c.relowner WHERE c.oid=%s::regclass",
                (qualified,),
            ).fetchone() == (True, True, "pitchlog_owner")
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                assert conn.execute(
                    "SELECT pg_catalog.has_table_privilege('pitchlog_app',%s,%s)",
                    (qualified, privilege),
                ).fetchone() == (False,)


def test_history_page_rejects_missing_originals_and_bad_cursor(
    storage_owner: Any,
) -> None:
    """管理者による故障注入を実app関数が拒否する。保存成功の証拠ではない。"""
    cluster = storage_owner.authority.database
    checkpoint_id = uuid4()
    with psycopg.connect(cluster.business_admin) as conn:
        # claimed水位3に対して履歴原本0という破損。正常イベントの代用には使わない。
        conn.execute(
            "INSERT INTO sync_fence.ordinary_pitch_checkpoints "
            "(tenant_id,game_id,internal_generation,id,revision,history_version,"
            "recovery_generation,confirmed_watermark,applied_watermark,"
            "content_digest,content,roster,state,saved_at) "
            "VALUES(%s,%s,1,%s,1,1,1,3,3,%s,'{}','{}','current',"
            "pg_catalog.clock_timestamp())",
            (storage_owner.tenant_id, storage_owner.game_id, checkpoint_id, "a" * 64),
        )
    database = conninfo_to_dict(cluster.business_admin)["dbname"]
    assert isinstance(database, str)
    with StderrPeer(cluster.business, database, "pitchlog_app") as app:
        app.query(f"SET app.tenant_id TO '{storage_owner.tenant_id}'")
        for after_d2, message in (
            (0, "ordinary prefix history tail rejected"),
            (1, "ordinary prefix page cursor rejected"),
        ):
            rows, state, error = app.run(
                "SELECT * FROM sync_right_api.read_ordinary_history_page("
                f"'{storage_owner.tenant_id}','{storage_owner.game_id}',1,1,"
                f"'{checkpoint_id}',1,3,0,{after_d2},"
                "'00000000-0000-0000-0000-000000000000',100)"
            )
            assert rows == ()
            assert state == "42501"
            assert message in error
        rows, state, _ = app.run(
            "SELECT sync_right_api.consume_ordinary_projection('{}'::jsonb)"
        )
        assert rows == ()
        assert state == "42501"
