"""0048過去訂正原本の明示型元。配備・公開・認可成功は発行しない。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from pitchlog.db.base import Base


class P3ProjectionCapsule(Base):
    """過去訂正のcapsules原本。途中成功の証明として使わない。"""

    __table__ = Table(
        "p3_projection_capsules",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        CheckConstraint("internal_generation > 0", name="ck_p3_capsules_01"),
        Column("id", Uuid, nullable=False),
        Column("change_event_id", Uuid, nullable=False),
        Column("d5", Uuid, nullable=False),
        Column("target_d1", BigInteger, nullable=False),
        CheckConstraint("target_d1 > 0", name="ck_p3_capsules_02"),
        Column("expected_version", BigInteger, nullable=False),
        CheckConstraint("expected_version > 0", name="ck_p3_capsules_03"),
        Column("prior_checkpoint_id", Uuid, nullable=False),
        Column("prior_checkpoint_revision", BigInteger, nullable=False),
        CheckConstraint("prior_checkpoint_revision > 0", name="ck_p3_capsules_04"),
        Column("prior_checkpoint_digest", Text, nullable=False),
        CheckConstraint(
            "prior_checkpoint_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_capsules_05"
        ),
        Column("prior_checkpoint_content", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(prior_checkpoint_content) = 'object'",
            name="ck_p3_capsules_06",
        ),
        Column("next_checkpoint_id", Uuid, nullable=False),
        Column("next_checkpoint_revision", BigInteger, nullable=False),
        CheckConstraint("next_checkpoint_revision > 0", name="ck_p3_capsules_07"),
        Column("next_checkpoint_digest", Text, nullable=False),
        CheckConstraint(
            "next_checkpoint_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_capsules_08"
        ),
        Column("next_checkpoint_content", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(next_checkpoint_content) = 'object'", name="ck_p3_capsules_09"
        ),
        Column("source_set_digest", Text, nullable=False),
        CheckConstraint(
            "source_set_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_capsules_10"
        ),
        Column("stats_evaluation_set_digest", Text, nullable=False),
        CheckConstraint(
            "stats_evaluation_set_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_capsules_11"
        ),
        Column("stats_model_sha256", Text, nullable=False),
        CheckConstraint(
            "stats_model_sha256 ~ '^sha256:[a-f0-9]{64}$'", name="ck_p3_capsules_12"
        ),
        Column("stats_version_id", Uuid, nullable=False),
        Column("watermark", BigInteger, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column(
            "digest_format",
            Text,
            nullable=False,
            server_default=text("'p3-full-v1'::text"),
        ),
        PrimaryKeyConstraint(
            "tenant_id", "game_id", "internal_generation", "id", name="pk_p3_capsules"
        ),
        UniqueConstraint("tenant_id", "change_event_id", name="uq_p3_capsules_01"),
        UniqueConstraint(
            "tenant_id",
            "game_id",
            "internal_generation",
            "next_checkpoint_id",
            name="uq_p3_capsules_02",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "internal_generation", "target_d1"],
            [
                "event_slots.tenant_id",
                "event_slots.game_id",
                "event_slots.generation",
                "event_slots.d1",
            ],
            name="fk_p3_capsules_01",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "change_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_p3_capsules_02",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "prior_checkpoint_id"],
            [
                "sync_fence.ordinary_pitch_checkpoints.tenant_id",
                "sync_fence.ordinary_pitch_checkpoints.id",
            ],
            name="fk_p3_capsules_03",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "stats_version_id"],
            [
                "sync_fence.stats_fact_versions.tenant_id",
                "sync_fence.stats_fact_versions.game_id",
                "sync_fence.stats_fact_versions.id",
            ],
            name="fk_p3_capsules_04",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(watermark BETWEEN 1 AND 25 AND digest_format='p3-full-v1') OR "
            "(watermark > 25 AND digest_format='p3-page-chain-v2')",
            name="ck_p3_capsules_13",
        ),
        schema="sync_fence",
        info={"storage_owner": "pitchlog_sync_right_fn_owner"},
    )


class P3ProjectionCapsuleItem(Base):
    """過去訂正のcapsule_items原本。途中成功の証明として使わない。"""

    __table__ = Table(
        "p3_projection_capsule_items",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        Column("capsule_id", Uuid, nullable=False),
        Column("d1", BigInteger, nullable=False),
        CheckConstraint("d1 > 0", name="ck_p3_capsule_items_01"),
        Column("d2", BigInteger, nullable=False),
        CheckConstraint("d2 > 0", name="ck_p3_capsule_items_02"),
        Column("state", Text, nullable=False),
        CheckConstraint(
            "state IN ('unchanged', 'corrected')", name="ck_p3_capsule_items_03"
        ),
        Column("original_event_id", Uuid, nullable=False),
        Column("effective_event_id", Uuid, nullable=False),
        Column("original_play_row_id", Uuid, nullable=False),
        Column("effective_play_row_id", Uuid, nullable=False),
        Column("original_payload", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(original_payload) = 'object'", name="ck_p3_capsule_items_04"
        ),
        Column("original_history_entry", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(original_history_entry) = 'object'",
            name="ck_p3_capsule_items_05",
        ),
        Column("original_play_row", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(original_play_row) = 'object'", name="ck_p3_capsule_items_06"
        ),
        Column("original_play_runners", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(original_play_runners) = 'array'",
            name="ck_p3_capsule_items_07",
        ),
        Column("payload", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_p3_capsule_items_08"
        ),
        Column("history_entry", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(history_entry) = 'object'", name="ck_p3_capsule_items_09"
        ),
        Column("play_row", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(play_row) = 'object'", name="ck_p3_capsule_items_10"
        ),
        Column("play_runners", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(play_runners) = 'array'", name="ck_p3_capsule_items_11"
        ),
        Column("item_digest", Text, nullable=False),
        CheckConstraint(
            "item_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_capsule_items_12"
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            "d1",
            name="pk_p3_capsule_items",
        ),
        UniqueConstraint(
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            "effective_event_id",
            name="uq_p3_capsule_items_01",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "internal_generation", "capsule_id"],
            [
                "sync_fence.p3_projection_capsules.tenant_id",
                "sync_fence.p3_projection_capsules.game_id",
                "sync_fence.p3_projection_capsules.internal_generation",
                "sync_fence.p3_projection_capsules.id",
            ],
            name="fk_p3_capsule_items_01",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "original_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_p3_capsule_items_02",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "effective_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_p3_capsule_items_03",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "original_play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="fk_p3_capsule_items_04",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "effective_play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="fk_p3_capsule_items_05",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        schema="sync_fence",
        info={"storage_owner": "pitchlog_sync_right_fn_owner"},
    )


class P3ProjectionHead(Base):
    """過去訂正のheads原本。途中成功の証明として使わない。"""

    __table__ = Table(
        "p3_projection_heads",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        CheckConstraint("internal_generation > 0", name="ck_p3_heads_01"),
        Column("capsule_id", Uuid, nullable=False),
        Column("revision", BigInteger, nullable=False),
        CheckConstraint("revision > 0", name="ck_p3_heads_02"),
        Column("source_set_digest", Text, nullable=False),
        CheckConstraint("source_set_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_heads_03"),
        Column("stats_version_id", Uuid, nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        PrimaryKeyConstraint(
            "tenant_id", "game_id", "internal_generation", name="pk_p3_heads"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "internal_generation", "capsule_id"],
            [
                "sync_fence.p3_projection_capsules.tenant_id",
                "sync_fence.p3_projection_capsules.game_id",
                "sync_fence.p3_projection_capsules.internal_generation",
                "sync_fence.p3_projection_capsules.id",
            ],
            name="fk_p3_heads_01",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "stats_version_id"],
            [
                "sync_fence.stats_fact_versions.tenant_id",
                "sync_fence.stats_fact_versions.game_id",
                "sync_fence.stats_fact_versions.id",
            ],
            name="fk_p3_heads_02",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        schema="sync_fence",
        info={"storage_owner": "pitchlog_sync_right_fn_owner"},
    )


class P3ProjectionWriteAdmission(Base):
    """過去訂正のwrite_admissions原本。途中成功の証明として使わない。"""

    __table__ = Table(
        "p3_projection_write_admissions",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("attempt_id", Uuid, nullable=False),
        Column("phase_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        CheckConstraint("internal_generation > 0", name="ck_p3_write_admissions_01"),
        Column("capsule_id", Uuid, nullable=False),
        Column("change_event_id", Uuid, nullable=False),
        Column("play_row_id", Uuid, nullable=False),
        Column("ledger_fingerprint", Text, nullable=False),
        CheckConstraint(
            "ledger_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_p3_write_admissions_02"
        ),
        Column("expected_play_row", JSONB, nullable=False),
        CheckConstraint(
            "jsonb_typeof(expected_play_row) = 'object'",
            name="ck_p3_write_admissions_03",
        ),
        Column("transaction_id", Text, nullable=False),
        CheckConstraint(
            "transaction_id ~ '^[1-9][0-9]{0,19}$'", name="ck_p3_write_admissions_04"
        ),
        Column("state", Text, nullable=False),
        CheckConstraint(
            "state IN ('ready','consumed')", name="ck_p3_write_admissions_05"
        ),
        PrimaryKeyConstraint(
            "tenant_id", "attempt_id", "phase_id", name="pk_p3_write_admissions"
        ),
        UniqueConstraint("tenant_id", "play_row_id", name="uq_p3_write_admissions_01"),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                "sync_fence.writer_bindings.tenant_id",
                "sync_fence.writer_bindings.attempt_id",
                "sync_fence.writer_bindings.phase_id",
            ],
            name="fk_p3_write_admissions_01",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_p3_write_admissions_02",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "change_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_p3_write_admissions_03",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "internal_generation", "capsule_id"],
            [
                "sync_fence.p3_projection_capsules.tenant_id",
                "sync_fence.p3_projection_capsules.game_id",
                "sync_fence.p3_projection_capsules.internal_generation",
                "sync_fence.p3_projection_capsules.id",
            ],
            name="fk_p3_write_admissions_04",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        schema="sync_fence",
        info={"storage_owner": "pitchlog_sync_right_fn_owner"},
    )


class P3ProjectionPageProgress(Base):
    """過去訂正のpage_progress原本。途中成功の証明として使わない。"""

    __table__ = Table(
        "p3_projection_page_progress",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        CheckConstraint("internal_generation > 0", name="ck_p3_page_progress_01"),
        Column("capsule_id", Uuid, nullable=False),
        Column("attempt_id", Uuid, nullable=False),
        Column("phase_id", Uuid, nullable=False),
        Column("device_id", Uuid, nullable=False),
        Column("binding_nonce", LargeBinary, nullable=False),
        CheckConstraint(
            "pg_catalog.octet_length(binding_nonce)=32", name="ck_p3_page_progress_02"
        ),
        Column("transaction_id", Text, nullable=False),
        CheckConstraint("transaction_id ~ '^[0-9]+$'", name="ck_p3_page_progress_03"),
        Column("watermark", BigInteger, nullable=False),
        CheckConstraint("watermark > 25", name="ck_p3_page_progress_04"),
        Column("digest_format", Text, nullable=False),
        CheckConstraint(
            "digest_format IN ('p3-page-chain-v2')", name="ck_p3_page_progress_05"
        ),
        Column("target_d1", BigInteger, nullable=False),
        CheckConstraint(
            "target_d1 > 0 AND target_d1 <= watermark", name="ck_p3_page_progress_06"
        ),
        Column("d5", Uuid, nullable=False),
        Column("old_stats_version_id", Uuid, nullable=False),
        Column("capsule_header", JSONB, nullable=False),
        CheckConstraint(
            "pg_catalog.jsonb_typeof(capsule_header)='object'",
            name="ck_p3_page_progress_07",
        ),
        Column("stats_header", JSONB, nullable=False),
        CheckConstraint(
            "pg_catalog.jsonb_typeof(stats_header)='object'",
            name="ck_p3_page_progress_08",
        ),
        Column("state", Text, nullable=False),
        CheckConstraint(
            "state IN ('building','finalized')", name="ck_p3_page_progress_09"
        ),
        Column("item_count", BigInteger, nullable=False, server_default=text("0")),
        CheckConstraint("item_count >= 0", name="ck_p3_page_progress_10"),
        Column("last_d1", BigInteger, nullable=False, server_default=text("0")),
        CheckConstraint("last_d1 >= 0", name="ck_p3_page_progress_11"),
        Column("last_d2", BigInteger, nullable=False, server_default=text("0")),
        CheckConstraint("last_d2 >= 0", name="ck_p3_page_progress_12"),
        Column("page_count", BigInteger, nullable=False, server_default=text("0")),
        CheckConstraint("page_count >= 0", name="ck_p3_page_progress_13"),
        Column("source_page_seal", Text, nullable=False),
        CheckConstraint(
            "source_page_seal ~ '^[a-f0-9]{64}$'", name="ck_p3_page_progress_14"
        ),
        Column("evaluation_page_seal", Text, nullable=False),
        CheckConstraint(
            "evaluation_page_seal ~ '^[a-f0-9]{64}$'", name="ck_p3_page_progress_15"
        ),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("finalized_at", DateTime(timezone=True), nullable=True),
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            name="pk_p3_page_progress",
        ),
        UniqueConstraint(
            "tenant_id", "attempt_id", "phase_id", name="uq_p3_page_progress_01"
        ),
        CheckConstraint("item_count <= watermark", name="ck_p3_page_progress_16"),
        CheckConstraint("item_count=last_d1", name="ck_p3_page_progress_17"),
        CheckConstraint(
            "(item_count=0 AND last_d2=0 AND page_count=0) OR (item_count>0 "
            "AND last_d2>0 AND page_count>0)",
            name="ck_p3_page_progress_18",
        ),
        CheckConstraint(
            "(state='building' AND finalized_at IS NULL) OR (state='finalized'"
            " AND finalized_at IS NOT NULL AND item_count=watermark)",
            name="ck_p3_page_progress_19",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "internal_generation", "capsule_id"],
            [
                "sync_fence.p3_projection_capsules.tenant_id",
                "sync_fence.p3_projection_capsules.game_id",
                "sync_fence.p3_projection_capsules.internal_generation",
                "sync_fence.p3_projection_capsules.id",
            ],
            name="fk_p3_page_progress_01",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        schema="sync_fence",
        info={"storage_owner": "pitchlog_owner"},
    )


class P3ProjectionPageRow(Base):
    """過去訂正のpage_rows原本。途中成功の証明として使わない。"""

    __table__ = Table(
        "p3_projection_page_rows",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        CheckConstraint("internal_generation > 0", name="ck_p3_page_rows_01"),
        Column("capsule_id", Uuid, nullable=False),
        Column("attempt_id", Uuid, nullable=False),
        Column("phase_id", Uuid, nullable=False),
        Column("device_id", Uuid, nullable=False),
        Column("binding_nonce", LargeBinary, nullable=False),
        CheckConstraint(
            "pg_catalog.octet_length(binding_nonce)=32", name="ck_p3_page_rows_02"
        ),
        Column("transaction_id", Text, nullable=False),
        CheckConstraint("transaction_id ~ '^[0-9]+$'", name="ck_p3_page_rows_03"),
        Column("d5", Uuid, nullable=False),
        Column("ledger_fingerprint", Text, nullable=False),
        CheckConstraint(
            "ledger_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_p3_page_rows_04"
        ),
        Column("d1", BigInteger, nullable=False),
        CheckConstraint("d1 > 0", name="ck_p3_page_rows_05"),
        Column("d2", BigInteger, nullable=False),
        CheckConstraint("d2 > 0", name="ck_p3_page_rows_06"),
        Column("original_event_id", Uuid, nullable=False),
        Column("effective_event_id", Uuid, nullable=False),
        Column("effective_play_row_id", Uuid, nullable=False),
        Column("item", JSONB, nullable=False),
        CheckConstraint(
            "pg_catalog.jsonb_typeof(item)='object'", name="ck_p3_page_rows_07"
        ),
        Column("original_evaluation", JSONB, nullable=False),
        CheckConstraint(
            "pg_catalog.jsonb_typeof(original_evaluation)='object'",
            name="ck_p3_page_rows_08",
        ),
        Column("original_evaluation_digest", Text, nullable=False),
        CheckConstraint(
            "original_evaluation_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_page_rows_09"
        ),
        Column("evaluation", JSONB, nullable=False),
        CheckConstraint(
            "pg_catalog.jsonb_typeof(evaluation)='object'", name="ck_p3_page_rows_10"
        ),
        Column("evaluation_digest", Text, nullable=False),
        CheckConstraint(
            "evaluation_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_page_rows_11"
        ),
        Column("item_digest", Text, nullable=False),
        CheckConstraint("item_digest ~ '^[a-f0-9]{64}$'", name="ck_p3_page_rows_12"),
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            "d1",
            name="pk_p3_page_rows",
        ),
        UniqueConstraint(
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            "effective_event_id",
            name="uq_p3_page_rows_01",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "internal_generation", "capsule_id"],
            [
                "sync_fence.p3_projection_page_progress.tenant_id",
                "sync_fence.p3_projection_page_progress.game_id",
                "sync_fence.p3_projection_page_progress.internal_generation",
                "sync_fence.p3_projection_page_progress.capsule_id",
            ],
            name="fk_p3_page_rows_01",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                "sync_fence.writer_bindings.tenant_id",
                "sync_fence.writer_bindings.attempt_id",
                "sync_fence.writer_bindings.phase_id",
            ],
            name="fk_p3_page_rows_02",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "original_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_p3_page_rows_03",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "effective_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_p3_page_rows_04",
            ondelete="NO ACTION",
        ),
        schema="sync_fence",
        info={"storage_owner": "pitchlog_owner"},
    )


ix_p3_capsule_items_current_page = Index(
    "ix_p3_capsule_items_current_page",
    P3ProjectionCapsuleItem.__table__.c.tenant_id,
    P3ProjectionCapsuleItem.__table__.c.game_id,
    P3ProjectionCapsuleItem.__table__.c.internal_generation,
    P3ProjectionCapsuleItem.__table__.c.capsule_id,
    P3ProjectionCapsuleItem.__table__.c.d1,
    P3ProjectionCapsuleItem.__table__.c.d2,
)
ix_p3_page_progress_attempt = Index(
    "ix_p3_page_progress_attempt",
    P3ProjectionPageProgress.__table__.c.tenant_id,
    P3ProjectionPageProgress.__table__.c.attempt_id,
    P3ProjectionPageProgress.__table__.c.phase_id,
    P3ProjectionPageProgress.__table__.c.state,
)
ix_p3_page_stats_stage_order = Index(
    "ix_p3_page_stats_stage_order",
    P3ProjectionPageRow.__table__.c.tenant_id,
    P3ProjectionPageRow.__table__.c.game_id,
    P3ProjectionPageRow.__table__.c.internal_generation,
    P3ProjectionPageRow.__table__.c.capsule_id,
    P3ProjectionPageRow.__table__.c.d1,
)

P3_STORAGE_MODELS = (
    P3ProjectionCapsule,
    P3ProjectionCapsuleItem,
    P3ProjectionHead,
    P3ProjectionWriteAdmission,
    P3ProjectionPageProgress,
    P3ProjectionPageRow,
)
