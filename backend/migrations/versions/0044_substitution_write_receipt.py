"""交代の独立同TX印を default-deny で配置する。"""

from alembic import op

revision = "0044_substitution_write_receipt"
down_revision = "0043_game_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """取消の対象列を改変せず、交代印を新設する。"""
    op.execute(
        """CREATE TABLE sync_fence.substitution_write_receipts (
 tenant_id uuid NOT NULL,attempt_id uuid NOT NULL,phase_id uuid NOT NULL,
 game_id uuid NOT NULL,source_event_id uuid NOT NULL,source_d1 bigint NOT NULL,
 checkpoint_id uuid NOT NULL,before_revision bigint NOT NULL,
 after_revision bigint NOT NULL,after_digest text NOT NULL,
 PRIMARY KEY (tenant_id,attempt_id,phase_id),
 UNIQUE (tenant_id,source_event_id),
 FOREIGN KEY (tenant_id,attempt_id,phase_id) REFERENCES
 sync_fence.nonplay_write_admissions(tenant_id,attempt_id,phase_id),
 FOREIGN KEY (tenant_id,game_id) REFERENCES public.games(tenant_id,id),
 FOREIGN KEY (tenant_id,source_event_id) REFERENCES
 public.operation_events(tenant_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY (tenant_id,checkpoint_id) REFERENCES
 sync_fence.ordinary_pitch_checkpoints(tenant_id,id),
 CONSTRAINT ck_substitution_receipt_sequence CHECK
 (source_d1>0 AND before_revision>0 AND after_revision=before_revision+1),
 CONSTRAINT ck_substitution_receipt_digest CHECK
 (after_digest ~ '^[a-f0-9]{64}$')
)"""
    )
    op.execute(
        "ALTER TABLE sync_fence.substitution_write_receipts OWNER TO pitchlog_owner"
    )
    op.execute(
        "ALTER TABLE sync_fence.substitution_write_receipts ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE sync_fence.substitution_write_receipts FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "REVOKE ALL ON TABLE sync_fence.substitution_write_receipts "
        "FROM PUBLIC,pitchlog_app,pitchlog_sync_right_fn_owner"
    )


def downgrade() -> None:
    """論理削除原則により保存済み印を物理除去しない。"""
    raise RuntimeError("交代receiptの物理削除は禁止")
