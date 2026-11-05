"""固定0041→0042だけの実owned migration/schema検査。実行はroot所有。"""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from db_fixtures import _dsn_names
from sqlalchemy.dialects import postgresql

from pitchlog.db.writer_binding.nonplay_models import NonplayWriteAdmission

from . import initial_recording_right_scope_support as initial_support
from .sync_writer_binding_support import BindingAuthorityDatabase

pytestmark = pytest.mark.requires_db


@pytest.fixture(scope="module")
def storage_owner() -> Iterator[Any]:
    """正規owned fixtureの固定0042へ、実parent0041を経由して進める。"""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            initial_support, "_INITIAL_REVISION", "0042_nonplay_write_admission"
        )
        patch.setattr(
            initial_support.ledger_support,
            "AuthorityDatabase",
            BindingAuthorityDatabase,
        )
        with initial_support.isolated_initial_grant_database(patch) as owner:
            admin_name, role_name = _dsn_names()
            patch.setenv(admin_name, owner.authority.database.primary_admin)
            patch.setenv(role_name, owner.authority.database.endpoints.primary_dsn)
            yield owner


@pytest.fixture
def admin_connection(storage_owner: Any) -> Iterator[psycopg.Connection]:
    """既identity autouseへ同じowned primaryを渡す。"""
    with psycopg.connect(storage_owner.authority.database.primary_admin) as conn:
        yield conn


@pytest.fixture
def tested_role_connection(storage_owner: Any) -> Iterator[psycopg.Connection]:
    """既identity検査を迂回しない。"""
    with psycopg.connect(
        storage_owner.authority.database.endpoints.primary_dsn
    ) as conn:
        yield conn


def test_nonplay_actual_schema_and_default_deny(storage_owner: Any) -> None:
    """全列nullable/PK/FK/RLS/owner/既role直権限の実値を検査する。"""
    table = NonplayWriteAdmission.__table__
    with psycopg.connect(storage_owner.authority.database.business_admin) as conn:
        assert conn.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchall() == [("0042_nonplay_write_admission",)]
        columns = conn.execute(
            (
                "SELECT column_name,is_nullable FROM information_schema.columns "
                "WHERE table_schema='sync_fence' AND "
                "table_name='nonplay_write_admissions' ORDER BY ordinal_position"
            )
        ).fetchall()
        assert columns == [
            (str(c.name), "YES" if c.nullable else "NO") for c in table.c
        ]
        assert len(columns) == 43
        actual_types = conn.execute(
            "SELECT a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod) "
            "FROM pg_catalog.pg_attribute a WHERE "
            "a.attrelid='sync_fence.nonplay_write_admissions'::regclass "
            "AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum"
        ).fetchall()
        assert actual_types == [
            (str(c.name), str(c.type.compile(dialect=postgresql.dialect())).lower())
            for c in table.c
        ]
        # 単なる件数ではなく、全FKの列順/参照先/退役方針/遅延を照合する。
        foreign_keys = conn.execute(
            "SELECT c.conname,ARRAY(SELECT a.attname::text FROM "
            "unnest(c.conkey) WITH ORDINALITY k(num,ord) JOIN "
            "pg_catalog.pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num "
            "ORDER BY k.ord),n.nspname,t.relname,ARRAY(SELECT a.attname::text FROM "
            "unnest(c.confkey) WITH ORDINALITY k(num,ord) JOIN "
            "pg_catalog.pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.num "
            "ORDER BY k.ord),c.confdeltype::text,c.confmatchtype::text,"
            "c.condeferrable,c.condeferred FROM pg_catalog.pg_constraint c JOIN "
            "pg_catalog.pg_class t ON t.oid=c.confrelid JOIN pg_catalog.pg_namespace n "
            "ON n.oid=t.relnamespace WHERE "
            "c.conrelid='sync_fence.nonplay_write_admissions'::regclass "
            "AND c.contype='f' "
            "ORDER BY c.conname"
        ).fetchall()
        assert foreign_keys == sorted(
            [
                (
                    str(fk.name),
                    [str(c.name) for c in fk.columns],
                    fk.elements[0].column.table.schema or "public",
                    fk.elements[0].column.table.name,
                    [str(e.column.name) for e in fk.elements],
                    "a",
                    "f" if fk.match == "FULL" else "s",
                    bool(fk.deferrable),
                    fk.initially == "DEFERRED",
                )
                for fk in table.foreign_key_constraints
            ]
        )
        assert conn.execute(
            "SELECT pg_catalog.pg_get_expr(i.indpred,i.indrelid),i.indisunique,"
            "ARRAY(SELECT a.attname::text FROM unnest(i.indkey) "
            "WITH ORDINALITY k(num,ord) "
            "JOIN pg_catalog.pg_attribute a ON a.attrelid=i.indrelid "
            "AND a.attnum=k.num "
            "ORDER BY k.ord) FROM pg_catalog.pg_index i WHERE "
            "i.indexrelid='sync_fence.uq_nonplay_consumed_target'::regclass"
        ).fetchone() == (
            "(state = 'consumed'::text)",
            True,
            ["tenant_id", "game_id", "target_event_id"],
        )
        assert conn.execute(
            (
                "SELECT c.relrowsecurity,c.relforcerowsecurity,r.rolname FROM "
                "pg_catalog.pg_class c JOIN pg_catalog.pg_roles r ON "
                "r.oid=c.relowner WHERE "
                "c.oid='sync_fence.nonplay_write_admissions'::regclass"
            )
        ).fetchone() == (True, True, "pitchlog_owner")
        assert conn.execute(
            (
                "SELECT count(*) FROM pg_catalog.pg_constraint WHERE "
                "conrelid='sync_fence.nonplay_write_admissions'::regclass AND "
                "contype='f'"
            )
        ).fetchone() == (8,)
        assert conn.execute(
            (
                "SELECT array_agg(a.attname::text ORDER BY k.ord) FROM "
                "pg_catalog.pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) "
                "WITH ORDINALITY k(num,ord) JOIN pg_catalog.pg_attribute a ON "
                "a.attrelid=c.conrelid AND a.attnum=k.num WHERE "
                "c.conrelid='sync_fence.nonplay_write_admissions'::regclass AND "
                "c.contype='p'"
            )
        ).fetchone() == (["tenant_id", "attempt_id", "phase_id"],)
        assert conn.execute(
            (
                "SELECT count(*) FROM pg_catalog.pg_trigger WHERE "
                "tgrelid='sync_fence.nonplay_write_admissions'::regclass AND NOT "
                "tgisinternal"
            )
        ).fetchone() == (2,)
        for role in [
            "pitchlog_app",
            "pitchlog_sync_binding_actor",
            "pitchlog_rg1_control_actor",
        ]:
            assert conn.execute(
                (
                    "SELECT "
                    "has_table_privilege(%s,'sync_fence.nonplay_write_admissions','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"
                ),
                (role,),
            ).fetchone() == (False,)
        # 関数ownerだけの有限DMLは正式profile側の別検査。
        # 監査原本のDELETE/TRUNCATEはどの版でも開けない。
        assert conn.execute(
            "SELECT has_table_privilege('pitchlog_sync_right_fn_owner',"
            "'sync_fence.nonplay_write_admissions','DELETE,TRUNCATE')"
        ).fetchone() == (False,)
