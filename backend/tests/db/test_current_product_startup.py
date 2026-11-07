"""current起動を所有隔離PGで検査し、旧0039と故障原子性を保つ。"""

from typing import Any, LiteralString, cast

import psycopg
import pytest
from sqlalchemy import Engine, event

from pitchlog.db import current_product_startup as current

from .test_stage_a_rule_candidates import _fresh_schema_database

pytestmark = pytest.mark.requires_db


def _marker(dsn: str) -> str:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchall()
        assert len(rows) == 1
        return rows[0][0]


def test_actual_current_s0_and_current_resume_keep_all_structure_and_catalog(
    disposable_postgres_cluster: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S0から実currentへ配置し、同版再開のmigration0と全catalogを確認する。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        assert _marker(admin) == "0033_game_rules_immutable"
        result = current.advance_current_product_from_s0(
            owner_dsn=owner, applicator_dsn=admin
        )
        assert result == current.CurrentProductStartupResult()
        assert _marker(admin) == current.CURRENT_REVISION
        with psycopg.connect(admin) as connection:
            current._check_current_structure(connection)
            current._check_current_indexes(connection)
            current._check_current_rules(connection)
            assert current._catalog(connection).ok
        with monkeypatch.context() as patch:
            patch.setattr(
                current.command,
                "upgrade",
                lambda *a, **kw: pytest.fail("current再開でmigrationを呼出した"),
            )
            resumed = current.resume_current_product_after_placement(
                owner_dsn=owner,
                applicator_dsn=admin,
            )
        assert resumed == result and resumed.publishable is False


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE INDEX ix_admin_vocabularies_batted_ball_key_c",
        "CREATE TABLE sync_fence.stats_fact_versions",
        "CREATE TABLE sync_fence.stats_primitive_sources",
        "CREATE TABLE sync_fence.pitcher_entry_sources",
        "CREATE INDEX ix_stats_fact_player_metric",
        "CREATE TABLE sync_fence.nonplay_write_admissions",
        "CREATE FUNCTION public.protect_nonplay_admission()",
        "CREATE TRIGGER trg_nonplay_admission_guard",
        "CREATE TRIGGER trg_nonplay_admission_no_truncate",
        "CREATE TABLE sync_fence.substitution_write_receipts",
        "CREATE TABLE sync_fence.attempt_retirements",
        "CREATE TABLE public.play_export_snapshots",
        "CREATE INDEX ix_operation_events_export_audit",
        (
            "ALTER TABLE sync_fence.stats_primitive_facts "
            "DROP CONSTRAINT ck_stats_fact_metric"
        ),
        (
            "ALTER TABLE sync_fence.stats_primitive_sources "
            "DROP CONSTRAINT ck_stats_source_metric_keys"
        ),
    ],
)
def test_actual_current_migration_fault_rolls_back_to_real0039(
    disposable_postgres_cluster: Any,
    monkeypatch: pytest.MonkeyPatch,
    statement: str,
) -> None:
    """currentまでの途中故障は追加表/制約/revisionを同時に0039へ戻す。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        reached = []

        def fail(_connection: Any, _cursor: Any, sql: str, *_args: Any) -> None:
            if statement in sql:
                reached.append(statement)
                raise RuntimeError("current migration fault")

        event.listen(Engine, "after_cursor_execute", fail)
        try:
            with pytest.raises(RuntimeError, match="current migration fault"):
                current.advance_current_product_from_s0(
                    owner_dsn=owner, applicator_dsn=admin
                )
        finally:
            event.remove(Engine, "after_cursor_execute", fail)
        assert reached == [statement]
        assert _marker(admin) == "0039_ordinary_pitch_storage"
        with psycopg.connect(admin) as connection:
            current.legacy._check_writer_storage(
                connection, current.legacy._WRITER_REVISION
            )
            assert (
                connection.execute(
                    "SELECT to_regclass('sync_fence.stats_fact_versions'),"
                    "to_regclass('sync_fence.stats_primitive_sources'),"
                    "to_regclass('sync_fence.stats_primitive_facts'),"
                    "to_regclass('public.ix_admin_vocabularies_batted_ball_key_c'),"
                    "to_regclass('sync_fence.nonplay_write_admissions'),"
                    "to_regprocedure('public.protect_nonplay_admission()'),"
                    "to_regclass('sync_fence.substitution_write_receipts'),"
                    "to_regclass('sync_fence.attempt_retirements'),"
                    "to_regclass('public.play_export_snapshots'),"
                    "to_regclass('public.ix_play_export_snapshots_game_captured'),"
                    "to_regclass('public.ix_play_rows_export_audit'),"
                    "to_regclass('public.ix_operation_events_export_audit')"
                ).fetchone()
                == (None,) * 12
            )
        # 旧0039からの実再開で同じ固定currentを完了する。
        result = current.resume_current_product_after_placement(
            owner_dsn=owner,
            applicator_dsn=admin,
        )
        assert result.completed_revision == current.CURRENT_REVISION


@pytest.mark.parametrize(
    "tamper",
    [
        (
            "REVOKE SELECT (xmin) ON public.event_slots "
            "FROM pitchlog_sync_right_fn_owner"
        ),
        "GRANT SELECT (xmin) ON public.event_slots TO pitchlog_app",
        (
            "GRANT SELECT (xmin) ON sync_fence.pitcher_entry_sources "
            "TO pitchlog_initial_fn_owner"
        ),
        (
            "GRANT SELECT (xmin) ON sync_fence.pitcher_entry_sources "
            "TO pitchlog_sync_right_fn_owner"
        ),
        (
            "GRANT SELECT (xmin) ON public.event_slots TO "
            "pitchlog_sync_right_fn_owner WITH GRANT OPTION"
        ),
        "ALTER TABLE sync_fence.stats_primitive_facts NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE sync_fence.attempt_retirements NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE public.play_export_snapshots NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE public.play_export_snapshots ADD COLUMN unexpected bigint",
        (
            "ALTER TABLE public.play_export_snapshots "
            "ALTER COLUMN captured_at DROP DEFAULT"
        ),
        "GRANT UPDATE ON public.play_export_snapshots TO pitchlog_app",
        "DROP INDEX public.ix_operation_events_export_audit",
        "ALTER TABLE sync_fence.attempt_retirements ADD COLUMN unexpected bigint",
        "GRANT UPDATE ON sync_fence.attempt_retirements TO pitchlog_sync_binding_actor",
        (
            "ALTER TABLE sync_fence.attempt_retirements DISABLE TRIGGER "
            "sync_attempt_retirement_immutable"
        ),
        (
            "DROP TRIGGER sync_attempt_retirement_no_truncate "
            "ON sync_fence.attempt_retirements"
        ),
        "ALTER TABLE sync_fence.nonplay_write_admissions NO FORCE ROW LEVEL SECURITY",
        (
            "ALTER TABLE sync_fence.nonplay_write_admissions ADD CO"
            "LUMN unknown_value bigint"
        ),
        "ALTER TABLE sync_fence.nonplay_write_admissions OWNER TO pitchlog_app",
        (
            "ALTER TABLE sync_fence.nonplay_write_admissions DROP C"
            "ONSTRAINT fk_nonplay_admission_binding"
        ),
        "GRANT EXECUTE ON FUNCTION public.protect_nonplay_admission() TO PUBLIC",
        "GRANT EXECUTE ON FUNCTION public.protect_nonplay_admission() TO pitchlog_app",
        "ALTER FUNCTION public.protect_nonplay_admission() SECURITY DEFINER",
        "ALTER TABLE sync_fence.nonplay_write_admissions "
        "ALTER CONSTRAINT fk_nonplay_admission_event NOT DEFERRABLE",
        "DROP INDEX sync_fence.uq_nonplay_consumed_target",
        (
            "ALTER TABLE sync_fence.nonplay_write_admissions DISABL"
            "E TRIGGER trg_nonplay_admission_guard"
        ),
        (
            "DROP TRIGGER trg_nonplay_admission_no_truncate ON sync"
            "_fence.nonplay_write_admissions"
        ),
        "ALTER TABLE sync_fence.stats_primitive_facts ADD COLUMN unknown_value bigint",
        "ALTER TABLE sync_fence.stats_primitive_facts "
        "DROP CONSTRAINT ck_stats_fact_ordinal",
        "DROP INDEX public.ix_admin_vocabularies_batted_ball_key_c",
        "ALTER TABLE public.rg1_restore_gate "
        "ALTER COLUMN recovery_generation TYPE integer",
        "ALTER TABLE public.recording_generations DROP CONSTRAINT "
        "ck_recording_generations_proof_digest",
        "GRANT SELECT ON sync_fence.stats_primitive_facts TO pitchlog_app",
        "DROP POLICY IF EXISTS unknown_partial ON sync_fence.stats_primitive_facts; "
        "CREATE POLICY unknown_partial ON sync_fence.stats_primitive_facts "
        "TO PUBLIC USING (true)",
    ],
)
def test_actual_current_resume_rejects_structure_or_acl_tamper_without_repair(
    disposable_postgres_cluster: Any,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    """改変後の再適用を成功補修にせず、検査で止める。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        current.advance_current_product_from_s0(owner_dsn=owner, applicator_dsn=admin)
        with psycopg.connect(admin) as connection:
            connection.execute(cast(LiteralString, tamper))
        with monkeypatch.context() as patch:
            patch.setattr(
                current,
                "apply_product_authz_ddl",
                lambda *a: pytest.fail("不正currentを補修した"),
            )
            with pytest.raises(current.CurrentProductStartupError):
                current.resume_current_product_after_placement(
                    owner_dsn=owner,
                    applicator_dsn=admin,
                )


@pytest.mark.parametrize("partial", [False, True])
def test_actual_prefull0042_resume_has_no_migration_and_rejects_partial_acl(
    disposable_postgres_cluster: Any,
    monkeypatch: pytest.MonkeyPatch,
    partial: bool,
) -> None:
    """真0042/default-denyは再開し、canonicalの一部grantだけでも混合は拒否する。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):

        def stop_before_full(_connection):
            raise RuntimeError("before full")

        with monkeypatch.context() as patch:
            patch.setattr(current, "apply_product_authz_ddl", stop_before_full)
            with pytest.raises(RuntimeError, match="before full"):
                current.advance_current_product_from_s0(
                    owner_dsn=owner, applicator_dsn=admin
                )
        assert _marker(admin) == current.CURRENT_REVISION
        with psycopg.connect(admin) as connection:
            assert current._require_pre_or_full_catalog(connection) == "pre-full"
            if partial:
                connection.execute(
                    "GRANT SELECT(tenant_id) ON sync_fence.stats_primitive_facts "
                    "TO pitchlog_sync_binding_fn_owner"
                )
        with monkeypatch.context() as patch:
            patch.setattr(
                current.command,
                "upgrade",
                lambda *a, **kw: pytest.fail("0042再開migration"),
            )
            if partial:
                patch.setattr(
                    current,
                    "apply_product_authz_ddl",
                    lambda *a: pytest.fail("partialをfull補修"),
                )
                with pytest.raises(current.CurrentProductStartupError):
                    current.resume_current_product_after_placement(
                        owner_dsn=owner,
                        applicator_dsn=admin,
                    )
            else:
                assert (
                    current.resume_current_product_after_placement(
                        owner_dsn=owner,
                        applicator_dsn=admin,
                    )
                    == current.CurrentProductStartupResult()
                )
