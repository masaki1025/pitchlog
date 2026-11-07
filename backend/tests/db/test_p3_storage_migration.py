"""0048の実配置と全構造改変拒否を所有隔離PGで検証する。"""

from typing import Any, LiteralString, cast

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from pitchlog.db import current_product_startup as current
from pitchlog.db.past_correction.startup import check_p3_storage

from .test_stage_a_rule_candidates import _fresh_schema_database

pytestmark = pytest.mark.requires_db


def _upgrade(owner: str) -> None:
    """通常47を経て固定migrationだけで48構造を配置する。"""
    engine = create_engine(current.legacy._owner_url(owner))
    try:
        with engine.begin() as connection:
            config = Config(str(current.legacy._BACKEND_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0048_p3_projection_storage")
    finally:
        engine.dispose()


def test_owned_p3_migration_and_all_structure_tamper_refusals(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """全型/制約/indexを確認し、部分欠落を正規配置と混同しない。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        current.advance_current_product_from_s0(owner_dsn=owner, applicator_dsn=admin)
        _upgrade(owner)
        with psycopg.connect(admin) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.alembic_version"
            ).fetchall() == [("0048_p3_projection_storage",)]
            check_p3_storage(connection)
            changes = (
                "ALTER TABLE sync_fence.p3_projection_capsules NO FORCE "
                "ROW LEVEL SECURITY",
                "ALTER TABLE sync_fence.p3_projection_capsules "
                "OWNER TO pitchlog_sync_right_fn_owner",
                "ALTER TABLE sync_fence.p3_projection_heads ADD COLUMN extra text",
                "ALTER TABLE sync_fence.p3_projection_page_progress "
                "ALTER COLUMN last_d2 TYPE numeric",
                "ALTER TABLE sync_fence.p3_projection_capsules "
                "ALTER COLUMN digest_format SET DEFAULT 'unknown'",
                "ALTER TABLE sync_fence.p3_projection_capsules "
                "DROP CONSTRAINT ck_p3_capsules_13",
                "ALTER TABLE sync_fence.p3_projection_capsule_items "
                "DROP CONSTRAINT fk_p3_capsule_items_01",
                "DROP INDEX sync_fence.ix_p3_capsule_items_current_page",
                "DROP INDEX sync_fence.ix_p3_page_progress_attempt; "
                "CREATE INDEX ix_p3_page_progress_attempt ON "
                "sync_fence.p3_projection_page_progress "
                '(tenant_id,attempt_id,phase_id,state COLLATE "C")',
                "CREATE INDEX extra_p3_index ON "
                "sync_fence.p3_projection_heads(updated_at)",
                "CREATE TABLE sync_fence.p3_projection_unknown(value text)",
            )
            for statement in changes:
                with connection.transaction(force_rollback=True):
                    connection.execute(cast(LiteralString, statement))
                    with pytest.raises(current.CurrentProductStartupError):
                        check_p3_storage(connection)
                check_p3_storage(connection)


def test_owned_p3_migration_fault_keeps_prior_revision_and_no_partial_tables(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """第6表後の例外で全6表と旧provider制約の変更を全部戻す。"""
    from sqlalchemy import Engine, event

    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        current.advance_current_product_from_s0(owner_dsn=owner, applicator_dsn=admin)

        def fail_after_last_table(
            _conn: Any, _cursor: Any, statement: str, *_args: Any
        ) -> None:
            if statement.lstrip().startswith(
                "CREATE TABLE sync_fence.p3_projection_page_rows "
            ):
                raise RuntimeError("owned P3 migration fault")

        event.listen(Engine, "after_cursor_execute", fail_after_last_table)
        try:
            with pytest.raises(RuntimeError, match="owned P3 migration fault"):
                _upgrade(owner)
        finally:
            event.remove(Engine, "after_cursor_execute", fail_after_last_table)
        with psycopg.connect(admin) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.alembic_version"
            ).fetchall() == [("0047_play_export_snapshots",)]
            assert (
                connection.execute(
                    "SELECT c.relname FROM pg_catalog.pg_class c "
                    "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='sync_fence' "
                    "AND pg_catalog.starts_with(c.relname,'p3_projection_')"
                ).fetchall()
                == []
            )
            current._check_current_structure(connection)
