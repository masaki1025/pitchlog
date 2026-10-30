"""通常投球の独立private原本をdefault-denyで配置する。"""

from alembic import op

revision = "0039_ordinary_pitch_storage"
down_revision = "0038_first_ball_write_admission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """表だけを配置し、資格発行や業務権限を開放しない。"""
    op.execute(
        """
        CREATE TABLE sync_fence.ordinary_pitch_checkpoints (
        tenant_id UUID NOT NULL,
        game_id UUID NOT NULL,
        internal_generation BIGINT NOT NULL,
        id UUID NOT NULL,
        revision BIGINT NOT NULL,
        history_version BIGINT NOT NULL,
        recovery_generation BIGINT NOT NULL,
        confirmed_watermark BIGINT NOT NULL,
        applied_watermark BIGINT NOT NULL,
        content_digest TEXT NOT NULL,
        content JSONB NOT NULL,
        roster JSONB NOT NULL,
        state TEXT NOT NULL,
        saved_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (tenant_id, game_id, internal_generation),
        UNIQUE (tenant_id, id),
        FOREIGN KEY(tenant_id, game_id) REFERENCES public.games (tenant_id, id) ON
        DELETE NO ACTION,
        CONSTRAINT ck_ordinary_checkpoint_positions CHECK (internal_generation>0 AND
        revision>0 AND history_version>0 AND recovery_generation>0 AND
        confirmed_watermark>=0 AND confirmed_watermark=applied_watermark),
        CONSTRAINT ck_ordinary_checkpoint_state CHECK (state IN
        ('current','invalidated')),
        CONSTRAINT ck_ordinary_checkpoint_digest CHECK (content_digest ~
        '^[a-f0-9]{64}$' AND octet_length(content_digest)=64),
        CONSTRAINT ck_ordinary_checkpoint_json CHECK (jsonb_typeof(content)='object'
        AND jsonb_typeof(roster)='object')
        )
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_checkpoints OWNER TO pitchlog_owner
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_checkpoints ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_checkpoints FORCE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL ON TABLE sync_fence.ordinary_pitch_checkpoints FROM PUBLIC,
        pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor,
        pitchlog_sync_right_fn_owner
        """
    )
    op.execute(
        """
        CREATE TABLE sync_fence.ordinary_pitch_write_admissions (
        tenant_id UUID NOT NULL,
        attempt_id UUID NOT NULL,
        phase_id UUID NOT NULL,
        authority_id UUID NOT NULL,
        control_instance UUID NOT NULL,
        business_instance UUID NOT NULL,
        restore_epoch UUID NOT NULL,
        control_version BIGINT NOT NULL,
        issuer UUID NOT NULL,
        lease_id UUID NOT NULL,
        device_id UUID NOT NULL,
        game_id UUID NOT NULL,
        wire_d4 TEXT NOT NULL,
        internal_generation BIGINT NOT NULL,
        recovery_generation BIGINT NOT NULL,
        codec_version BIGINT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        d5 UUID NOT NULL,
        event_fingerprint TEXT NOT NULL,
        system_identifier TEXT NOT NULL,
        database_oid TEXT NOT NULL,
        postmaster_started_at TIMESTAMP WITH TIME ZONE NOT NULL,
        backend_pid INTEGER NOT NULL,
        backend_start TIMESTAMP WITH TIME ZONE NOT NULL,
        transaction_id TEXT NOT NULL,
        nonce_digest BYTEA NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        state TEXT NOT NULL,
        checkpoint_id UUID,
        frame_id UUID,
        source_event_id UUID,
        play_row_id UUID,
        checkpoint_revision BIGINT,
        prefix_length BIGINT,
        source_d1 BIGINT,
        source_d2 BIGINT,
        checkpoint_digest TEXT,
        frame_digest TEXT,
        artifact_sha256 TEXT,
        checkpoint_content JSONB,
        next_checkpoint_content JSONB,
        roster_snapshot JSONB,
        history_entry JSONB,
        expected_play_row JSONB,
        consumed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (tenant_id, attempt_id, phase_id),
        UNIQUE (tenant_id, frame_id),
        UNIQUE (tenant_id, source_event_id),
        UNIQUE (tenant_id, play_row_id),
        FOREIGN KEY(tenant_id, checkpoint_id) REFERENCES
        sync_fence.ordinary_pitch_checkpoints (tenant_id, id) ON DELETE NO ACTION
        DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY(tenant_id, attempt_id, phase_id) REFERENCES
        sync_fence.writer_bindings (tenant_id, attempt_id, phase_id) MATCH FULL ON
        DELETE NO ACTION,
        FOREIGN KEY(tenant_id, source_event_id) REFERENCES public.operation_events
        (tenant_id, id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY(tenant_id, play_row_id) REFERENCES public.play_rows (tenant_id,
        id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT ck_ordinary_admission_state CHECK (state IN
        ('device_verified','right_verified','evaluated','consumed','invalid')),
        CONSTRAINT ck_ordinary_admission_xid8 CHECK (transaction_id ~
        '^[1-9][0-9]{0,19}$' AND transaction_id !~ '[^0-9]' AND
        transaction_id::numeric<=18446744073709551615),
        CONSTRAINT ck_ordinary_admission_nonce CHECK
        (octet_length(nonce_digest)=32),
        CONSTRAINT ck_ordinary_admission_fingerprints CHECK (request_fingerprint ~
        '^(wire-request-v1:)?[a-f0-9]{64}$' AND octet_length(request_fingerprint) IN
        (64,80) AND event_fingerprint ~ '^(wire-v1:)?[a-f0-9]{64}$' AND
        octet_length(event_fingerprint) IN (64,72)),
        CONSTRAINT ck_ordinary_admission_evaluated CHECK (state NOT IN
        ('evaluated','consumed') OR (checkpoint_id IS NOT NULL AND
        checkpoint_revision IS NOT NULL AND checkpoint_revision>0 AND prefix_length
        IS NOT NULL AND prefix_length>=0 AND frame_id IS NOT NULL AND frame_digest
        IS NOT NULL AND checkpoint_digest IS NOT NULL AND artifact_sha256 IS NOT
        NULL AND source_event_id IS NOT NULL AND source_d1 IS NOT NULL AND
        source_d1>0 AND source_d2 IS NOT NULL AND source_d2>=0 AND play_row_id IS
        NOT NULL AND checkpoint_content IS NOT NULL AND next_checkpoint_content IS
        NOT NULL AND roster_snapshot IS NOT NULL AND history_entry IS NOT NULL AND
        expected_play_row IS NOT NULL)),
        CONSTRAINT ck_ordinary_admission_consumed CHECK
        ((state='consumed')=(consumed_at IS NOT NULL)),
        CONSTRAINT ck_ordinary_admission_values CHECK (state NOT IN
        ('evaluated','consumed') OR (checkpoint_digest ~ '^[a-f0-9]{64}$' AND
        octet_length(checkpoint_digest)=64 AND frame_digest ~ '^[a-f0-9]{64}$' AND
        octet_length(frame_digest)=64 AND artifact_sha256 ~ '^[a-f0-9]{64}$' AND
        octet_length(artifact_sha256)=64 AND
        jsonb_typeof(checkpoint_content)='object' AND
        jsonb_typeof(next_checkpoint_content)='object' AND
        jsonb_typeof(roster_snapshot)='object' AND
        jsonb_typeof(history_entry)='object' AND
        jsonb_typeof(expected_play_row)='object'))
        )
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_write_admissions OWNER TO
        pitchlog_owner
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_write_admissions ENABLE ROW LEVEL
        SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_write_admissions FORCE ROW LEVEL
        SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL ON TABLE sync_fence.ordinary_pitch_write_admissions FROM PUBLIC,
        pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor,
        pitchlog_sync_right_fn_owner
        """
    )
    op.execute(
        """
        CREATE TABLE sync_fence.ordinary_pitch_history (
        tenant_id UUID NOT NULL,
        game_id UUID NOT NULL,
        internal_generation BIGINT NOT NULL,
        history_version BIGINT NOT NULL,
        source_event_id UUID NOT NULL,
        d1 BIGINT NOT NULL,
        d2 BIGINT NOT NULL,
        entry JSONB NOT NULL,
        PRIMARY KEY (tenant_id, source_event_id, history_version),
        UNIQUE (tenant_id, game_id, internal_generation, history_version, d1),
        FOREIGN KEY(tenant_id, source_event_id) REFERENCES public.operation_events
        (tenant_id, id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT ck_ordinary_history_positive CHECK (internal_generation>0 AND
        history_version>0 AND d1>0 AND d2>=0),
        CONSTRAINT ck_ordinary_history_entry CHECK (jsonb_typeof(entry)='object')
        )
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_history OWNER TO pitchlog_owner
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_history ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.ordinary_pitch_history FORCE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL ON TABLE sync_fence.ordinary_pitch_history FROM PUBLIC,
        pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor,
        pitchlog_sync_right_fn_owner
        """
    )


def downgrade() -> None:
    """確定原本・資格履歴の物理削除を許可しない。"""
    raise RuntimeError("通常投球保存原本のdowngradeは許可しません")
