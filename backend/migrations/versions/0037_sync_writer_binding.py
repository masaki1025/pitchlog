"""同期writer資格とadmissionをdefault-denyで配置する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_sync_writer_binding"
down_revision: str | Sequence[str] | None = "0036_initial_right_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """固定2表を配置し、正式ACL供給前のアクセスを拒否する。"""
    op.execute("CREATE SCHEMA sync_fence AUTHORIZATION pitchlog_owner")
    op.execute("REVOKE ALL ON SCHEMA sync_fence FROM PUBLIC")
    op.create_table(
        "writer_bindings",
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
        sa.Column("close_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "octet_length(nonce_digest)=32", name="ck_sync_writer_binding_nonce"
        ),
        sa.CheckConstraint(
            "control_version>0 AND internal_generation>0 AND "
            "recovery_generation>0 AND codec_version>0 AND backend_pid>0",
            name="ck_sync_writer_binding_positive",
        ),
        sa.CheckConstraint(
            "state IN ('open','closed') AND ((state='open' AND close_id IS "
            "NULL) OR (state='closed' AND close_id IS NOT NULL))",
            name="ck_sync_writer_binding_state",
        ),
        sa.CheckConstraint(
            "wire_d4<>'' AND request_fingerprint<>'' AND event_fingerprint<>''"
            " AND system_identifier<>'' AND database_oid<>''",
            name="ck_sync_writer_binding_text",
        ),
        sa.CheckConstraint(
            "transaction_id ~ '^[1-9][0-9]{0,19}$' AND transaction_id::numeric"
            " <= 18446744073709551615",
            name="ck_sync_writer_binding_xid8",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_sync_writer_binding_game",
            ondelete="NO ACTION",
            match="FULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_sync_writer_binding_tenant",
            ondelete="NO ACTION",
            match="FULL",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "attempt_id", "phase_id", name="pk_sync_writer_bindings"
        ),
        sa.UniqueConstraint("lease_id", name="uq_sync_writer_binding_lease"),
        sa.UniqueConstraint("nonce_digest", name="uq_sync_writer_binding_nonce"),
        schema="sync_fence",
    )
    op.execute("ALTER TABLE sync_fence.writer_bindings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sync_fence.writer_bindings FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE sync_fence.writer_bindings FROM PUBLIC")
    op.create_table(
        "writer_admissions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("phase_id", sa.Uuid(), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "transaction_id ~ '^[1-9][0-9]{0,19}$' AND transaction_id::numeric"
            " <= 18446744073709551615",
            name="ck_sync_writer_admission_xid8",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                "sync_fence.writer_bindings.tenant_id",
                "sync_fence.writer_bindings.attempt_id",
                "sync_fence.writer_bindings.phase_id",
            ],
            name="fk_sync_writer_admission_binding",
            ondelete="NO ACTION",
            match="FULL",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "attempt_id", "phase_id", name="pk_sync_writer_admissions"
        ),
        schema="sync_fence",
    )
    op.execute("ALTER TABLE sync_fence.writer_admissions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sync_fence.writer_admissions FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE sync_fence.writer_admissions FROM PUBLIC")


def downgrade() -> None:
    """writer資格・終結証拠を失う逆適用を拒否する。"""
    raise RuntimeError("writer資格の履歴を消す逆適用は許可しない")
