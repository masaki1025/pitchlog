"""取消の独立印だけをdefault-denyで追加する。"""

from alembic import op

revision = "0042_nonplay_write_admission"
down_revision = "0041_stats_fact_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """既表/CHECK/権限を変えず同TX印を配置する。"""
    op.execute(
        """
        CREATE TABLE sync_fence.nonplay_write_admissions (
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
                frame_id UUID,
                frame_digest TEXT,
                artifact_sha256 TEXT,
                source_event_id UUID,
                source_d1 BIGINT,
                target_event_id UUID,
                target_generation BIGINT,
                target_d1 BIGINT,
                target_play_id UUID,
                checkpoint_id UUID,
                checkpoint_revision BIGINT,
                checkpoint_digest TEXT,
                preparation_json TEXT,
                preparation JSONB,
                consumed_at TIMESTAMP WITH TIME ZONE,
                PRIMARY KEY (tenant_id, attempt_id, phase_id),
                UNIQUE (tenant_id, frame_id),
                UNIQUE (tenant_id, source_event_id),
                CONSTRAINT fk_nonplay_admission_binding FOREIGN KEY(tenant_id,
        attempt_id, phase_id) REFERENCES sync_fence.writer_bindings (tenant_id,
        attempt_id, phase_id) MATCH FULL ON DELETE NO ACTION,
                CONSTRAINT fk_nonplay_admission_game FOREIGN KEY(tenant_id, game_id)
        REFERENCES public.games (tenant_id, id) ON DELETE NO ACTION,
                CONSTRAINT fk_nonplay_admission_event FOREIGN KEY(tenant_id,
        source_event_id) REFERENCES public.operation_events (tenant_id, id) ON
        DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
                CONSTRAINT fk_nonplay_admission_target FOREIGN KEY(tenant_id,
        target_event_id) REFERENCES public.operation_events (tenant_id, id) ON
        DELETE NO ACTION,
                CONSTRAINT fk_nonplay_admission_target_play FOREIGN KEY(tenant_id,
        target_play_id) REFERENCES public.play_rows (tenant_id, id) ON DELETE NO
        ACTION,
                CONSTRAINT fk_nonplay_admission_checkpoint FOREIGN KEY(tenant_id,
        checkpoint_id) REFERENCES sync_fence.ordinary_pitch_checkpoints (tenant_id,
        id) ON DELETE NO ACTION,
                CONSTRAINT fk_nonplay_admission_source_slot FOREIGN KEY(tenant_id,
        game_id, internal_generation, source_d1) REFERENCES public.event_slots
        (tenant_id, game_id, generation, d1) ON DELETE NO ACTION,
                CONSTRAINT fk_nonplay_admission_target_slot FOREIGN KEY(tenant_id,
        game_id, target_generation, target_d1) REFERENCES public.event_slots
        (tenant_id, game_id, generation, d1) ON DELETE NO ACTION,
                CONSTRAINT ck_nonplay_admission_state CHECK (state IN
        ('device_verified','right_verified','evaluated','consumed','invalid')),
                CONSTRAINT ck_nonplay_admission_identity CHECK (control_version>0
        AND internal_generation>0 AND recovery_generation>0 AND codec_version=1 AND
        backend_pid>0),
                CONSTRAINT ck_nonplay_admission_nonce CHECK
        (octet_length(nonce_digest)=32),
                CONSTRAINT ck_nonplay_admission_xid8 CHECK (transaction_id ~
        '^[1-9][0-9]{0,19}$' AND transaction_id !~ '[^0-9]' AND
        transaction_id::numeric<=18446744073709551615),
                CONSTRAINT ck_nonplay_admission_fingerprints CHECK
        (request_fingerprint ~ '^(wire-request-v1:)?[a-f0-9]{64}$' AND
        octet_length(request_fingerprint) IN (64,80) AND event_fingerprint ~
        '^(wire-v1:)?[a-f0-9]{64}$' AND octet_length(event_fingerprint) IN (64,72)),
                CONSTRAINT ck_nonplay_admission_consumed CHECK
        ((state='consumed')=(consumed_at IS NOT NULL)),
                CONSTRAINT ck_nonplay_admission_evaluated CHECK (state NOT IN
        ('evaluated','consumed') OR (frame_id IS NOT NULL AND frame_digest IS NOT
        NULL AND artifact_sha256 IS NOT NULL AND source_event_id IS NOT NULL AND
        source_d1 IS NOT NULL AND source_d1>0 AND target_event_id IS NOT NULL AND
        target_generation IS NOT NULL AND target_generation>0 AND target_d1 IS NOT
        NULL AND target_d1>0 AND target_play_id IS NOT NULL AND checkpoint_id IS NOT
        NULL AND checkpoint_revision IS NOT NULL AND checkpoint_revision>0 AND
        checkpoint_digest IS NOT NULL AND preparation_json IS NOT NULL AND
        preparation IS NOT NULL)),
                CONSTRAINT ck_nonplay_admission_values CHECK (state NOT IN
        ('evaluated','consumed') OR (frame_digest ~ '^[a-f0-9]{64}$' AND
        octet_length(frame_digest)=64 AND artifact_sha256 ~ '^[a-f0-9]{64}$' AND
        octet_length(artifact_sha256)=64 AND checkpoint_digest ~ '^[a-f0-9]{64}$'
        AND octet_length(checkpoint_digest)=64 AND
        jsonb_typeof(preparation)='object'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_nonplay_consumed_target ON
        sync_fence.nonplay_write_admissions (tenant_id, game_id, target_event_id)
        WHERE state = 'consumed'
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.nonplay_write_admissions OWNER TO pitchlog_owner
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.nonplay_write_admissions ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.nonplay_write_admissions FORCE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL ON TABLE sync_fence.nonplay_write_admissions FROM PUBLIC,
        pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor,
        pitchlog_sync_right_fn_owner
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.protect_nonplay_admission()
        RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS
        $guard$
        BEGIN
         IF TG_OP IN ('DELETE','TRUNCATE') OR
         current_user<>'pitchlog_sync_right_fn_owner' THEN
         RAISE EXCEPTION 'nonplay admission protected' USING ERRCODE='42501';
         END IF;
         IF TG_OP='INSERT' THEN
         IF NEW.state NOT IN ('device_verified','invalid') OR NEW.preparation IS NOT
        NULL
         THEN RAISE EXCEPTION 'nonplay initial state' USING ERRCODE='42501'; END IF;
         RETURN NEW;
         END IF;
         IF
        (pg_catalog.to_jsonb(NEW)-'artifact_sha256'-'checkpoint_digest'-'checkpoint_id'-'checkpoint_revision'-'consumed_at'-'frame_digest'-'frame_id'-'preparation'-'preparation_json'-'source_d1'-'source_event_id'-'state'-'target_d1'-'target_event_id'-'target_generation'-'target_play_id')
        IS DISTINCT FROM
        (pg_catalog.to_jsonb(OLD)-'artifact_sha256'-'checkpoint_digest'-'checkpoint_id'-'checkpoint_revision'-'consumed_at'-'frame_digest'-'frame_id'-'preparation'-'preparation_json'-'source_d1'-'source_event_id'-'state'-'target_d1'-'target_event_id'-'target_generation'-'target_play_id')
         OR OLD.state IN ('consumed','invalid')
         OR (OLD.state='device_verified' AND NEW.state NOT IN
         ('device_verified','right_verified','invalid'))
         OR (OLD.state='right_verified' AND NEW.state NOT IN
         ('right_verified','evaluated','invalid'))
         OR (OLD.state='evaluated' AND NEW.state NOT IN ('consumed','invalid'))
         OR (OLD.preparation IS NOT NULL AND
         (pg_catalog.to_jsonb(NEW)-'state'-'consumed_at') IS DISTINCT FROM
         (pg_catalog.to_jsonb(OLD)-'state'-'consumed_at'))
         OR (NEW.state NOT IN ('evaluated','consumed','invalid') AND
         NEW.preparation IS NOT NULL)
         THEN RAISE EXCEPTION 'nonplay state transition' USING ERRCODE='42501'; END
        IF;
         RETURN NEW;
        END;
        $guard$;
        """
    )
    op.execute(
        "ALTER FUNCTION public.protect_nonplay_admission() OWNER TO pitchlog_owner"
    )
    op.execute(
        """
        REVOKE ALL ON FUNCTION public.protect_nonplay_admission() FROM
        PUBLIC,pitchlog_app
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_nonplay_admission_guard BEFORE INSERT OR UPDATE OR DELETE
        ON sync_fence.nonplay_write_admissions FOR EACH ROW EXECUTE FUNCTION
        public.protect_nonplay_admission()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_nonplay_admission_no_truncate BEFORE TRUNCATE ON
        sync_fence.nonplay_write_admissions FOR EACH STATEMENT EXECUTE FUNCTION
        public.protect_nonplay_admission()
        """
    )


def downgrade() -> None:
    """監査原本を物理削除しない。"""
    raise RuntimeError("非play admissionの降格は監査原本を保持する別手順が必要です")
