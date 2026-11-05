"""受理T5の版/source/credit原本をdefault-denyで配置する。"""

from alembic import op

revision = "0041_stats_fact_versions"
down_revision = "0040_batted_vocabulary_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """型付き保存先だけを配置し、任意receiptや業務権限を発行しない。"""
    op.execute(
        """
        CREATE TABLE sync_fence.stats_fact_versions (
        tenant_id UUID NOT NULL,
        game_id UUID NOT NULL,
        id UUID NOT NULL,
        model_sha256 TEXT NOT NULL,
        rule_sha256 TEXT NOT NULL,
        t5_artifact_set_sha256 TEXT NOT NULL,
        source_set_sha256 TEXT NOT NULL,
        source_count BIGINT NOT NULL,
        revision BIGINT NOT NULL,
        last_generation BIGINT,
        last_d1 BIGINT,
        last_d2 BIGINT,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        computed_metric_keys TEXT[] NOT NULL,
        is_current BOOLEAN NOT NULL,
        completion_state TEXT NOT NULL,
        completion_receipt_id UUID,
        public_pointer_receipt_id UUID,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        invalidated_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (tenant_id, game_id, id),
        UNIQUE (tenant_id, id),
        UNIQUE (tenant_id, game_id, id, rule_sha256),
        CONSTRAINT fk_stats_version_game FOREIGN KEY(tenant_id, game_id) REFERENCES
        public.games (tenant_id, id) ON DELETE NO ACTION,
        CONSTRAINT ck_stats_version_hashes CHECK (model_sha256 ~
        '^sha256:[a-f0-9]{64}$' AND rule_sha256 ~ '^[a-f0-9]{64}$' AND
        t5_artifact_set_sha256 ~ '^[a-f0-9]{64}$' AND source_set_sha256 ~
        '^[a-f0-9]{64}$'),
        CONSTRAINT ck_stats_version_count CHECK (source_count>=0 AND revision>0),
        CONSTRAINT ck_stats_version_position CHECK ((source_count=0 AND
        last_generation IS NULL AND last_d1 IS NULL AND last_d2 IS NULL) OR
        (last_generation IS NOT NULL AND last_d1 IS NOT NULL AND last_d2 IS NOT NULL
        AND last_generation>0 AND last_d1>0)),
        CONSTRAINT ck_stats_version_metric_keys CHECK
        (array_position(computed_metric_keys,NULL) IS NULL AND
        cardinality(computed_metric_keys)<=26 AND computed_metric_keys <@
        ARRAY['pitch_count','pa','ab','h','hr','bb','hbp','k','sh','sf','catcher_interference_reached','runner_interference_reached','doubles','triples','total_bases','runs','rbi','stolen_bases','pitching_outs','pitcher_k','pitcher_bb','pitcher_hbp','hits_allowed','home_runs_allowed','fielding_errors','runs_allowed']::text[]),
        CONSTRAINT ck_stats_version_completion_shape CHECK (completion_state IN
        ('current_open','confirmed_ended') AND (completion_state<>'confirmed_ended'
        OR (completion_receipt_id IS NOT NULL AND public_pointer_receipt_id IS NOT
        NULL))),
        CONSTRAINT ck_stats_version_current CHECK (NOT is_current OR invalidated_at
        IS NULL)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_stats_current_game_model ON
        sync_fence.stats_fact_versions (tenant_id, game_id, model_sha256) WHERE
        is_current
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_fact_versions OWNER TO pitchlog_owner
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_fact_versions ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_fact_versions FORCE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL ON TABLE sync_fence.stats_fact_versions FROM PUBLIC,
        pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor,
        pitchlog_sync_right_fn_owner
        """
    )
    op.execute(
        """
        CREATE TABLE sync_fence.stats_primitive_sources (
        tenant_id UUID NOT NULL,
        game_id UUID NOT NULL,
        fact_version_id UUID NOT NULL,
        source_event_id UUID NOT NULL,
        play_row_id UUID NOT NULL,
        recording_generation BIGINT NOT NULL,
        d1 BIGINT NOT NULL,
        d2 BIGINT NOT NULL,
        slot_version BIGINT NOT NULL,
        play_row_version BIGINT NOT NULL,
        provider_kind TEXT NOT NULL,
        attempt_id UUID NOT NULL,
        phase_id UUID NOT NULL,
        wire_d4 TEXT NOT NULL,
        source_fingerprint TEXT NOT NULL,
        checkpoint_id UUID,
        checkpoint_revision BIGINT,
        checkpoint_digest TEXT,
        frame_digest TEXT,
        evaluation_sha256 TEXT NOT NULL,
        artifact_sha256 TEXT NOT NULL,
        rule_sha256 TEXT NOT NULL,
        metric_states JSONB NOT NULL,
        computed_metric_keys TEXT[] NOT NULL,
        saved_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (tenant_id, game_id, fact_version_id, source_event_id),
        UNIQUE (tenant_id, game_id, fact_version_id, recording_generation, d1,
        slot_version),
        CONSTRAINT fk_stats_source_version FOREIGN KEY(tenant_id, game_id,
        fact_version_id, rule_sha256) REFERENCES sync_fence.stats_fact_versions
        (tenant_id, game_id, id, rule_sha256) ON DELETE NO ACTION,
        CONSTRAINT fk_stats_source_event FOREIGN KEY(tenant_id, source_event_id)
        REFERENCES public.operation_events (tenant_id, id) ON DELETE NO ACTION,
        CONSTRAINT fk_stats_source_play FOREIGN KEY(tenant_id, play_row_id)
        REFERENCES public.play_rows (tenant_id, id) ON DELETE NO ACTION,
        CONSTRAINT fk_stats_source_slot FOREIGN KEY(tenant_id, game_id,
        recording_generation, d1) REFERENCES public.event_slots (tenant_id, game_id,
        generation, d1) ON DELETE NO ACTION,
        CONSTRAINT fk_stats_source_binding FOREIGN KEY(tenant_id, attempt_id,
        phase_id) REFERENCES sync_fence.writer_bindings (tenant_id, attempt_id,
        phase_id) ON DELETE NO ACTION,
        CONSTRAINT ck_stats_source_positions CHECK (recording_generation>0 AND d1>0
        AND slot_version>0 AND play_row_version>0),
        CONSTRAINT ck_stats_source_provider CHECK (provider_kind IN
        ('first_ball','ordinary')),
        CONSTRAINT ck_stats_source_fingerprint CHECK (source_fingerprint ~
        '^(wire-v1:)?[a-f0-9]{64}$' AND length(wire_d4)>0),
        CONSTRAINT ck_stats_source_checkpoint CHECK ((checkpoint_id IS NULL AND
        checkpoint_revision IS NULL AND checkpoint_digest IS NULL) OR (checkpoint_id
        IS NOT NULL AND checkpoint_revision IS NOT NULL AND checkpoint_digest IS NOT
        NULL AND checkpoint_revision>0 AND checkpoint_digest ~ '^[a-f0-9]{64}$')),
        CONSTRAINT ck_stats_source_ordinary_proof CHECK (provider_kind<>'ordinary'
        OR (checkpoint_id IS NOT NULL AND frame_digest IS NOT NULL)),
        CONSTRAINT ck_stats_source_evaluation CHECK (evaluation_sha256 ~
        '^[a-f0-9]{64}$' AND artifact_sha256 ~ '^[a-f0-9]{64}$' AND rule_sha256 ~
        '^[a-f0-9]{64}$' AND jsonb_typeof(metric_states)='object'),
        CONSTRAINT ck_stats_source_frame CHECK (frame_digest IS NULL OR frame_digest
        ~ '^[a-f0-9]{64}$'),
        CONSTRAINT ck_stats_source_metric_keys CHECK
        (array_position(computed_metric_keys,NULL) IS NULL AND
        cardinality(computed_metric_keys)<=26 AND computed_metric_keys <@
        ARRAY['pitch_count','pa','ab','h','hr','bb','hbp','k','sh','sf','catcher_interference_reached','runner_interference_reached','doubles','triples','total_bases','runs','rbi','stolen_bases','pitching_outs','pitcher_k','pitcher_bb','pitcher_hbp','hits_allowed','home_runs_allowed','fielding_errors','runs_allowed']::text[])
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_stats_source_logical ON sync_fence.stats_primitive_sources
        (tenant_id, game_id, fact_version_id, d2, source_event_id)
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_primitive_sources OWNER TO pitchlog_owner
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_primitive_sources ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_primitive_sources FORCE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL ON TABLE sync_fence.stats_primitive_sources FROM PUBLIC,
        pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor,
        pitchlog_sync_right_fn_owner
        """
    )
    op.execute(
        """
        CREATE TABLE sync_fence.stats_primitive_facts (
        tenant_id UUID NOT NULL,
        game_id UUID NOT NULL,
        fact_version_id UUID NOT NULL,
        source_event_id UUID NOT NULL,
        metric_id TEXT NOT NULL,
        player_id UUID NOT NULL,
        credit_ordinal BIGINT NOT NULL,
        state TEXT NOT NULL,
        amount NUMERIC,
        PRIMARY KEY (tenant_id, game_id, fact_version_id, source_event_id,
        metric_id, player_id, credit_ordinal),
        CONSTRAINT fk_stats_fact_source FOREIGN KEY(tenant_id, game_id,
        fact_version_id, source_event_id) REFERENCES
        sync_fence.stats_primitive_sources (tenant_id, game_id, fact_version_id,
        source_event_id) ON DELETE NO ACTION,
        CONSTRAINT fk_stats_fact_player FOREIGN KEY(tenant_id, player_id) REFERENCES
        public.players (tenant_id, id) ON DELETE NO ACTION,
        CONSTRAINT ck_stats_fact_ordinal CHECK (credit_ordinal>=0 AND
        credit_ordinal<4),
        CONSTRAINT ck_stats_fact_metric CHECK
        (metric_id=ANY(ARRAY['pitch_count','pa','ab','h','hr','bb','hbp','k','sh','sf','catcher_interference_reached','runner_interference_reached','doubles','triples','total_bases','runs','rbi','stolen_bases','pitching_outs','pitcher_k','pitcher_bb','pitcher_hbp','hits_allowed','home_runs_allowed','fielding_errors','runs_allowed']::text[])),
        CONSTRAINT ck_stats_fact_value CHECK ((state='source_unavailable' AND amount
        IS NULL) OR (state='available' AND amount IS NOT NULL AND amount>=0 AND
        amount=trunc(amount) AND amount NOT IN
        ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_stats_fact_player_metric ON sync_fence.stats_primitive_facts
        (tenant_id, game_id, fact_version_id, player_id, metric_id, source_event_id)
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_primitive_facts OWNER TO pitchlog_owner
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_primitive_facts ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE sync_fence.stats_primitive_facts FORCE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL ON TABLE sync_fence.stats_primitive_facts FROM PUBLIC,
        pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor,
        pitchlog_sync_right_fn_owner
        """
    )


def downgrade() -> None:
    """確定factとsource原本の物理削除を許可しない。"""
    raise RuntimeError("T5原本のdowngradeは許可しません")
