"""初球書込印の未適用private表だけをdefault-denyで配置する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_first_ball_write_admission"
down_revision: str | Sequence[str] | None = "0037_sync_writer_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """表以外のprofile/guard/発行口を有効化しない。"""
    op.create_table(
        "first_ball_write_admissions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("phase_id", sa.Uuid(), nullable=False),
        sa.Column("authority_id", sa.Uuid(), nullable=False),
        sa.Column("control_instance", sa.Uuid(), nullable=False),
        sa.Column("business_instance", sa.Uuid(), nullable=False),
        sa.Column("restore_epoch", sa.Uuid(), nullable=False),
        sa.Column("control_version", sa.BigInteger(), nullable=False),
        sa.Column("issuer", sa.Uuid(), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("wire_d4", sa.Text(), nullable=False),
        sa.Column("internal_generation", sa.BigInteger(), nullable=False),
        sa.Column("recovery_generation", sa.BigInteger(), nullable=False),
        sa.Column("codec_version", sa.BigInteger(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("d5", sa.Uuid(), nullable=False),
        sa.Column("event_fingerprint", sa.Text(), nullable=False),
        sa.Column("system_identifier", sa.Text(), nullable=False),
        sa.Column("database_oid", sa.Text(), nullable=False),
        sa.Column("postmaster_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("backend_pid", sa.Integer(), nullable=False),
        sa.Column("backend_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.Column("nonce_digest", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("play_row_id", sa.Uuid(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(nonce_digest)=32", name="ck_first_ball_write_nonce"
        ),
        sa.CheckConstraint(
            "control_version>0 AND internal_generation>0 AND recovery"
            "_generation>0 AND codec_version>0 AND backend_pid>0",
            name="ck_first_ball_write_positive",
        ),
        sa.CheckConstraint(
            "state IN ('device_verified','right_verified','invalid','"
            "consumed') AND ((state='consumed' AND source_event_id IS"
            " NOT NULL AND play_row_id IS NOT NULL AND consumed_at IS"
            " NOT NULL) OR (state<>'consumed' AND source_event_id IS "
            "NULL AND play_row_id IS NULL AND consumed_at IS NULL))",
            name="ck_first_ball_write_state",
        ),
        sa.CheckConstraint(
            "wire_d4<>'' AND request_fingerprint<>'' AND event_finger"
            "print<>'' AND system_identifier<>'' AND database_oid<>''",
            name="ck_first_ball_write_text",
        ),
        sa.CheckConstraint(
            "transaction_id ~ '^[1-9][0-9]{0,19}$' AND transaction_id"
            "::numeric <= 18446744073709551615",
            name="ck_first_ball_write_xid8",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                "sync_fence.writer_bindings.tenant_id",
                "sync_fence.writer_bindings.attempt_id",
                "sync_fence.writer_bindings.phase_id",
            ],
            name="fk_first_ball_write_admission_binding",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_first_ball_write_admission_event",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="fk_first_ball_write_admission_projection",
            match="SIMPLE",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint(
            *["tenant_id", "attempt_id", "phase_id"],
            name="pk_first_ball_write_admissions",
        ),
        schema="sync_fence",
    )
    op.execute(
        "ALTER TABLE sync_fence.first_ball_write_admissions OWNER TO pitchlog_owner"
    )
    op.execute(
        "ALTER TABLE sync_fence.first_ball_write_admissions ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE sync_fence.first_ball_write_admissions FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "REVOKE ALL ON TABLE sync_fence.first_ball_write_admissio"
        "ns FROM PUBLIC, pitchlog_app, pitchlog_sync_binding_acto"
        "r, pitchlog_rg1_control_actor, pitchlog_sync_right_fn_ow"
        "ner"
    )


def downgrade() -> None:
    """資格履歴の物理削除を認めない。"""
    raise RuntimeError("初球書込印の履歴は削除できません")
