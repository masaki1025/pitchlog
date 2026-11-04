"""所有隔離PGの実migrationとdefault-deny T5保存先を検証する。"""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from pitchlog.db.game_state.stats import (
    StatsFactVersion,
    StatsPrimitiveFact,
    StatsPrimitiveSource,
)

from .sync_writer_binding_support import owned_binding_database

pytestmark = pytest.mark.requires_db


@pytest.fixture(scope="module")
def stats_owner() -> Iterator[Any]:
    """rootが割り当てた時間内にだけ所有隔離PGを起動する。"""
    with pytest.MonkeyPatch.context() as patch:
        with owned_binding_database(patch) as owner:
            yield owner


@pytest.mark.parametrize(
    "model", [StatsFactVersion, StatsPrimitiveSource, StatsPrimitiveFact]
)
def test_stats_real_migration_matches_typed_columns_and_default_deny(
    stats_owner, model
):
    """実migrationの列/FORCE RLS/所有者/無権限を独立catalogで照合する。"""
    table = model.__table__
    with psycopg.connect(stats_owner.authority.database.business_admin) as conn:
        columns = conn.execute(
            "SELECT column_name,is_nullable FROM information_schema.columns "
            "WHERE table_schema='sync_fence' AND table_name=%s "
            "ORDER BY ordinal_position",
            (table.name,),
        ).fetchall()
        assert columns == [(c.name, "YES" if c.nullable else "NO") for c in table.c]
        assert conn.execute(
            "SELECT c.relrowsecurity,c.relforcerowsecurity,r.rolname "
            "FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner "
            "WHERE c.oid=%s::regclass",
            (table.fullname,),
        ).fetchone() == (True, True, "pitchlog_owner")
        policies = conn.execute(
            "SELECT roles FROM pg_policies WHERE schemaname='sync_fence' "
            "AND tablename=%s",
            (table.name,),
        ).fetchall()
        # 正式関数owner向けpolicy追加後も、app/PUBLICへ表を開かない。
        assert all(
            "public" not in roles and "pitchlog_app" not in roles
            for (roles,) in policies
        )
        for role in (
            "pitchlog_app",
            "pitchlog_sync_binding_actor",
            "pitchlog_rg1_control_actor",
        ):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert conn.execute(
                    "SELECT has_table_privilege(%s,%s,%s)",
                    (role, table.fullname, privilege),
                ).fetchone() == (False,)


def test_stats_downgrade_never_physically_deletes():
    """確定原本のmigration downgradeを直接呼んでも削除できない。"""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[2] / "migrations/versions/0040_stats_fact_versions.py"
    spec = importlib.util.spec_from_file_location("stats_storage_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError):
        module.downgrade()
