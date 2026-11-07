"""過去訂正の完成capsuleと未完了page原本を不可分に配置する。"""

from alembic import op

revision = "0048_p3_projection_storage"
down_revision = "0047_play_export_snapshots"
branch_labels = None
depends_on = None

# 型元の初版から凍結したDDL。後発モデルをmigration実行時にimportしない。
_STATEMENTS = (
    """
CREATE TABLE sync_fence.p3_projection_capsules (
  tenant_id UUID NOT NULL,
  game_id UUID NOT NULL,
  internal_generation BIGINT NOT NULL,
  id UUID NOT NULL,
  change_event_id UUID NOT NULL,
  d5 UUID NOT NULL,
  target_d1 BIGINT NOT NULL,
  expected_version BIGINT NOT NULL,
  prior_checkpoint_id UUID NOT NULL,
  prior_checkpoint_revision BIGINT NOT NULL,
  prior_checkpoint_digest TEXT NOT NULL,
  prior_checkpoint_content JSONB NOT NULL,
  next_checkpoint_id UUID NOT NULL,
  next_checkpoint_revision BIGINT NOT NULL,
  next_checkpoint_digest TEXT NOT NULL,
  next_checkpoint_content JSONB NOT NULL,
  source_set_digest TEXT NOT NULL,
  stats_evaluation_set_digest TEXT NOT NULL,
  stats_model_sha256 TEXT NOT NULL,
  stats_version_id UUID NOT NULL,
  watermark BIGINT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  digest_format TEXT DEFAULT 'p3-full-v1'::text NOT NULL,
  CONSTRAINT pk_p3_capsules PRIMARY KEY (tenant_id, game_id,
internal_generation, id),
  CONSTRAINT ck_p3_capsules_01 CHECK (internal_generation > 0),
  CONSTRAINT ck_p3_capsules_02 CHECK (target_d1 > 0),
  CONSTRAINT ck_p3_capsules_03 CHECK (expected_version > 0),
  CONSTRAINT ck_p3_capsules_04 CHECK (prior_checkpoint_revision > 0),
  CONSTRAINT ck_p3_capsules_05 CHECK (prior_checkpoint_digest ~
'^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_capsules_06 CHECK (jsonb_typeof(prior_checkpoint_content) =
'object'),
  CONSTRAINT ck_p3_capsules_07 CHECK (next_checkpoint_revision > 0),
  CONSTRAINT ck_p3_capsules_08 CHECK (next_checkpoint_digest ~
'^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_capsules_09 CHECK (jsonb_typeof(next_checkpoint_content) =
'object'),
  CONSTRAINT ck_p3_capsules_10 CHECK (source_set_digest ~ '^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_capsules_11 CHECK (stats_evaluation_set_digest ~
'^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_capsules_12 CHECK (stats_model_sha256 ~
'^sha256:[a-f0-9]{64}$'),
  CONSTRAINT uq_p3_capsules_01 UNIQUE (tenant_id, change_event_id),
  CONSTRAINT uq_p3_capsules_02 UNIQUE (tenant_id, game_id,
internal_generation, next_checkpoint_id),
  CONSTRAINT fk_p3_capsules_01 FOREIGN KEY(tenant_id, game_id,
internal_generation, target_d1) REFERENCES event_slots (tenant_id, game_id,
generation, d1) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_capsules_02 FOREIGN KEY(tenant_id, change_event_id)
REFERENCES operation_events (tenant_id, id) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_capsules_03 FOREIGN KEY(tenant_id, prior_checkpoint_id)
REFERENCES sync_fence.ordinary_pitch_checkpoints (tenant_id, id) ON DELETE NO
ACTION,
  CONSTRAINT fk_p3_capsules_04 FOREIGN KEY(tenant_id, game_id,
stats_version_id) REFERENCES sync_fence.stats_fact_versions (tenant_id,
game_id, id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT ck_p3_capsules_13 CHECK ((watermark >= 1 AND watermark <= 25 AND
digest_format='p3-full-v1') OR (watermark > 25 AND
digest_format='p3-page-chain-v2'))
)
""",
    """
ALTER TABLE sync_fence.p3_projection_capsules OWNER TO pitchlog_owner
""",
    """
ALTER TABLE sync_fence.p3_projection_capsules ENABLE ROW LEVEL SECURITY
""",
    """
ALTER TABLE sync_fence.p3_projection_capsules FORCE ROW LEVEL SECURITY
""",
    """
REVOKE ALL ON TABLE sync_fence.p3_projection_capsules FROM
PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor
""",
    """
CREATE TABLE sync_fence.p3_projection_capsule_items (
  tenant_id UUID NOT NULL,
  game_id UUID NOT NULL,
  internal_generation BIGINT NOT NULL,
  capsule_id UUID NOT NULL,
  d1 BIGINT NOT NULL,
  d2 BIGINT NOT NULL,
  state TEXT NOT NULL,
  original_event_id UUID NOT NULL,
  effective_event_id UUID NOT NULL,
  original_play_row_id UUID NOT NULL,
  effective_play_row_id UUID NOT NULL,
  original_payload JSONB NOT NULL,
  original_history_entry JSONB NOT NULL,
  original_play_row JSONB NOT NULL,
  original_play_runners JSONB NOT NULL,
  payload JSONB NOT NULL,
  history_entry JSONB NOT NULL,
  play_row JSONB NOT NULL,
  play_runners JSONB NOT NULL,
  item_digest TEXT NOT NULL,
  CONSTRAINT pk_p3_capsule_items PRIMARY KEY (tenant_id, game_id,
internal_generation, capsule_id, d1),
  CONSTRAINT ck_p3_capsule_items_01 CHECK (d1 > 0),
  CONSTRAINT ck_p3_capsule_items_02 CHECK (d2 > 0),
  CONSTRAINT ck_p3_capsule_items_03 CHECK (state IN ('unchanged',
'corrected')),
  CONSTRAINT ck_p3_capsule_items_04 CHECK (jsonb_typeof(original_payload) =
'object'),
  CONSTRAINT ck_p3_capsule_items_05 CHECK
(jsonb_typeof(original_history_entry) = 'object'),
  CONSTRAINT ck_p3_capsule_items_06 CHECK (jsonb_typeof(original_play_row) =
'object'),
  CONSTRAINT ck_p3_capsule_items_07 CHECK (jsonb_typeof(original_play_runners)
= 'array'),
  CONSTRAINT ck_p3_capsule_items_08 CHECK (jsonb_typeof(payload) = 'object'),
  CONSTRAINT ck_p3_capsule_items_09 CHECK (jsonb_typeof(history_entry) =
'object'),
  CONSTRAINT ck_p3_capsule_items_10 CHECK (jsonb_typeof(play_row) = 'object'),
  CONSTRAINT ck_p3_capsule_items_11 CHECK (jsonb_typeof(play_runners) =
'array'),
  CONSTRAINT ck_p3_capsule_items_12 CHECK (item_digest ~ '^[a-f0-9]{64}$'),
  CONSTRAINT uq_p3_capsule_items_01 UNIQUE (tenant_id, game_id,
internal_generation, capsule_id, effective_event_id),
  CONSTRAINT fk_p3_capsule_items_01 FOREIGN KEY(tenant_id, game_id,
internal_generation, capsule_id) REFERENCES sync_fence.p3_projection_capsules
(tenant_id, game_id, internal_generation, id) ON DELETE NO ACTION DEFERRABLE
INITIALLY DEFERRED,
  CONSTRAINT fk_p3_capsule_items_02 FOREIGN KEY(tenant_id, original_event_id)
REFERENCES operation_events (tenant_id, id) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_capsule_items_03 FOREIGN KEY(tenant_id, effective_event_id)
REFERENCES operation_events (tenant_id, id) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_capsule_items_04 FOREIGN KEY(tenant_id,
original_play_row_id) REFERENCES play_rows (tenant_id, id) ON DELETE NO
ACTION,
  CONSTRAINT fk_p3_capsule_items_05 FOREIGN KEY(tenant_id,
effective_play_row_id) REFERENCES play_rows (tenant_id, id) ON DELETE NO
ACTION DEFERRABLE INITIALLY DEFERRED
)
""",
    """
CREATE INDEX ix_p3_capsule_items_current_page ON
sync_fence.p3_projection_capsule_items (tenant_id, game_id,
internal_generation, capsule_id, d1, d2)
""",
    """
ALTER TABLE sync_fence.p3_projection_capsule_items OWNER TO pitchlog_owner
""",
    """
ALTER TABLE sync_fence.p3_projection_capsule_items ENABLE ROW LEVEL SECURITY
""",
    """
ALTER TABLE sync_fence.p3_projection_capsule_items FORCE ROW LEVEL SECURITY
""",
    """
REVOKE ALL ON TABLE sync_fence.p3_projection_capsule_items FROM
PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor
""",
    """
CREATE TABLE sync_fence.p3_projection_heads (
  tenant_id UUID NOT NULL,
  game_id UUID NOT NULL,
  internal_generation BIGINT NOT NULL,
  capsule_id UUID NOT NULL,
  revision BIGINT NOT NULL,
  source_set_digest TEXT NOT NULL,
  stats_version_id UUID NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
  CONSTRAINT pk_p3_heads PRIMARY KEY (tenant_id, game_id,
internal_generation),
  CONSTRAINT ck_p3_heads_01 CHECK (internal_generation > 0),
  CONSTRAINT ck_p3_heads_02 CHECK (revision > 0),
  CONSTRAINT ck_p3_heads_03 CHECK (source_set_digest ~ '^[a-f0-9]{64}$'),
  CONSTRAINT fk_p3_heads_01 FOREIGN KEY(tenant_id, game_id,
internal_generation, capsule_id) REFERENCES sync_fence.p3_projection_capsules
(tenant_id, game_id, internal_generation, id) ON DELETE NO ACTION DEFERRABLE
INITIALLY DEFERRED,
  CONSTRAINT fk_p3_heads_02 FOREIGN KEY(tenant_id, game_id, stats_version_id)
REFERENCES sync_fence.stats_fact_versions (tenant_id, game_id, id) ON DELETE
NO ACTION DEFERRABLE INITIALLY DEFERRED
)
""",
    """
ALTER TABLE sync_fence.p3_projection_heads OWNER TO pitchlog_owner
""",
    """
ALTER TABLE sync_fence.p3_projection_heads ENABLE ROW LEVEL SECURITY
""",
    """
ALTER TABLE sync_fence.p3_projection_heads FORCE ROW LEVEL SECURITY
""",
    """
REVOKE ALL ON TABLE sync_fence.p3_projection_heads FROM
PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor
""",
    """
CREATE TABLE sync_fence.p3_projection_write_admissions (
  tenant_id UUID NOT NULL,
  attempt_id UUID NOT NULL,
  phase_id UUID NOT NULL,
  game_id UUID NOT NULL,
  internal_generation BIGINT NOT NULL,
  capsule_id UUID NOT NULL,
  change_event_id UUID NOT NULL,
  play_row_id UUID NOT NULL,
  ledger_fingerprint TEXT NOT NULL,
  expected_play_row JSONB NOT NULL,
  transaction_id TEXT NOT NULL,
  state TEXT NOT NULL,
  CONSTRAINT pk_p3_write_admissions PRIMARY KEY (tenant_id, attempt_id,
phase_id),
  CONSTRAINT ck_p3_write_admissions_01 CHECK (internal_generation > 0),
  CONSTRAINT ck_p3_write_admissions_02 CHECK (ledger_fingerprint ~
'^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_write_admissions_03 CHECK (jsonb_typeof(expected_play_row)
= 'object'),
  CONSTRAINT ck_p3_write_admissions_04 CHECK (transaction_id ~
'^[1-9][0-9]{0,19}$'),
  CONSTRAINT ck_p3_write_admissions_05 CHECK (state IN ('ready','consumed')),
  CONSTRAINT uq_p3_write_admissions_01 UNIQUE (tenant_id, play_row_id),
  CONSTRAINT fk_p3_write_admissions_01 FOREIGN KEY(tenant_id, attempt_id,
phase_id) REFERENCES sync_fence.writer_bindings (tenant_id, attempt_id,
phase_id) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_write_admissions_02 FOREIGN KEY(tenant_id, game_id)
REFERENCES games (tenant_id, id) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_write_admissions_03 FOREIGN KEY(tenant_id, change_event_id)
REFERENCES operation_events (tenant_id, id) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_write_admissions_04 FOREIGN KEY(tenant_id, game_id,
internal_generation, capsule_id) REFERENCES sync_fence.p3_projection_capsules
(tenant_id, game_id, internal_generation, id) ON DELETE NO ACTION DEFERRABLE
INITIALLY DEFERRED
)
""",
    """
ALTER TABLE sync_fence.p3_projection_write_admissions OWNER TO pitchlog_owner
""",
    """
ALTER TABLE sync_fence.p3_projection_write_admissions ENABLE ROW LEVEL
SECURITY
""",
    """
ALTER TABLE sync_fence.p3_projection_write_admissions FORCE ROW LEVEL SECURITY
""",
    """
REVOKE ALL ON TABLE sync_fence.p3_projection_write_admissions FROM
PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor
""",
    """
CREATE TABLE sync_fence.p3_projection_page_progress (
  tenant_id UUID NOT NULL,
  game_id UUID NOT NULL,
  internal_generation BIGINT NOT NULL,
  capsule_id UUID NOT NULL,
  attempt_id UUID NOT NULL,
  phase_id UUID NOT NULL,
  device_id UUID NOT NULL,
  binding_nonce BYTEA NOT NULL,
  transaction_id TEXT NOT NULL,
  watermark BIGINT NOT NULL,
  digest_format TEXT NOT NULL,
  target_d1 BIGINT NOT NULL,
  d5 UUID NOT NULL,
  old_stats_version_id UUID NOT NULL,
  capsule_header JSONB NOT NULL,
  stats_header JSONB NOT NULL,
  state TEXT NOT NULL,
  item_count BIGINT DEFAULT 0 NOT NULL,
  last_d1 BIGINT DEFAULT 0 NOT NULL,
  last_d2 BIGINT DEFAULT 0 NOT NULL,
  page_count BIGINT DEFAULT 0 NOT NULL,
  source_page_seal TEXT NOT NULL,
  evaluation_page_seal TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  finalized_at TIMESTAMP WITH TIME ZONE,
  CONSTRAINT pk_p3_page_progress PRIMARY KEY (tenant_id, game_id,
internal_generation, capsule_id),
  CONSTRAINT ck_p3_page_progress_01 CHECK (internal_generation > 0),
  CONSTRAINT ck_p3_page_progress_02 CHECK (octet_length(binding_nonce)=32),
  CONSTRAINT ck_p3_page_progress_03 CHECK (transaction_id ~ '^[0-9]+$'),
  CONSTRAINT ck_p3_page_progress_04 CHECK (watermark > 25),
  CONSTRAINT ck_p3_page_progress_05 CHECK (digest_format='p3-page-chain-v2'),
  CONSTRAINT ck_p3_page_progress_06 CHECK (target_d1 > 0 AND target_d1 <=
watermark),
  CONSTRAINT ck_p3_page_progress_07 CHECK
(jsonb_typeof(capsule_header)='object'),
  CONSTRAINT ck_p3_page_progress_08 CHECK
(jsonb_typeof(stats_header)='object'),
  CONSTRAINT ck_p3_page_progress_09 CHECK (state IN ('building','finalized')),
  CONSTRAINT ck_p3_page_progress_10 CHECK (item_count >= 0),
  CONSTRAINT ck_p3_page_progress_11 CHECK (last_d1 >= 0),
  CONSTRAINT ck_p3_page_progress_12 CHECK (last_d2 >= 0),
  CONSTRAINT ck_p3_page_progress_13 CHECK (page_count >= 0),
  CONSTRAINT ck_p3_page_progress_14 CHECK (source_page_seal ~
'^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_page_progress_15 CHECK (evaluation_page_seal ~
'^[a-f0-9]{64}$'),
  CONSTRAINT uq_p3_page_progress_01 UNIQUE (tenant_id, attempt_id, phase_id),
  CONSTRAINT ck_p3_page_progress_16 CHECK (item_count <= watermark),
  CONSTRAINT ck_p3_page_progress_17 CHECK (item_count=last_d1),
  CONSTRAINT ck_p3_page_progress_18 CHECK ((item_count=0 AND last_d2=0 AND
page_count=0) OR (item_count>0 AND last_d2>0 AND page_count>0)),
  CONSTRAINT ck_p3_page_progress_19 CHECK ((state='building' AND finalized_at
IS NULL) OR (state='finalized' AND finalized_at IS NOT NULL AND
item_count=watermark)),
  CONSTRAINT fk_p3_page_progress_01 FOREIGN KEY(tenant_id, game_id,
internal_generation, capsule_id) REFERENCES sync_fence.p3_projection_capsules
(tenant_id, game_id, internal_generation, id) ON DELETE NO ACTION DEFERRABLE
INITIALLY DEFERRED
)
""",
    """
CREATE INDEX ix_p3_page_progress_attempt ON
sync_fence.p3_projection_page_progress (tenant_id, attempt_id, phase_id,
state)
""",
    """
ALTER TABLE sync_fence.p3_projection_page_progress OWNER TO pitchlog_owner
""",
    """
ALTER TABLE sync_fence.p3_projection_page_progress ENABLE ROW LEVEL SECURITY
""",
    """
ALTER TABLE sync_fence.p3_projection_page_progress FORCE ROW LEVEL SECURITY
""",
    """
REVOKE ALL ON TABLE sync_fence.p3_projection_page_progress FROM
PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor
""",
    """
CREATE TABLE sync_fence.p3_projection_page_rows (
  tenant_id UUID NOT NULL,
  game_id UUID NOT NULL,
  internal_generation BIGINT NOT NULL,
  capsule_id UUID NOT NULL,
  attempt_id UUID NOT NULL,
  phase_id UUID NOT NULL,
  device_id UUID NOT NULL,
  binding_nonce BYTEA NOT NULL,
  transaction_id TEXT NOT NULL,
  d5 UUID NOT NULL,
  ledger_fingerprint TEXT NOT NULL,
  d1 BIGINT NOT NULL,
  d2 BIGINT NOT NULL,
  original_event_id UUID NOT NULL,
  effective_event_id UUID NOT NULL,
  effective_play_row_id UUID NOT NULL,
  item JSONB NOT NULL,
  original_evaluation JSONB NOT NULL,
  original_evaluation_digest TEXT NOT NULL,
  evaluation JSONB NOT NULL,
  evaluation_digest TEXT NOT NULL,
  item_digest TEXT NOT NULL,
  CONSTRAINT pk_p3_page_rows PRIMARY KEY (tenant_id, game_id,
internal_generation, capsule_id, d1),
  CONSTRAINT ck_p3_page_rows_01 CHECK (internal_generation > 0),
  CONSTRAINT ck_p3_page_rows_02 CHECK (octet_length(binding_nonce)=32),
  CONSTRAINT ck_p3_page_rows_03 CHECK (transaction_id ~ '^[0-9]+$'),
  CONSTRAINT ck_p3_page_rows_04 CHECK (ledger_fingerprint ~ '^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_page_rows_05 CHECK (d1 > 0),
  CONSTRAINT ck_p3_page_rows_06 CHECK (d2 > 0),
  CONSTRAINT ck_p3_page_rows_07 CHECK (jsonb_typeof(item)='object'),
  CONSTRAINT ck_p3_page_rows_08 CHECK
(jsonb_typeof(original_evaluation)='object'),
  CONSTRAINT ck_p3_page_rows_09 CHECK (original_evaluation_digest ~
'^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_page_rows_10 CHECK (jsonb_typeof(evaluation)='object'),
  CONSTRAINT ck_p3_page_rows_11 CHECK (evaluation_digest ~ '^[a-f0-9]{64}$'),
  CONSTRAINT ck_p3_page_rows_12 CHECK (item_digest ~ '^[a-f0-9]{64}$'),
  CONSTRAINT uq_p3_page_rows_01 UNIQUE (tenant_id, game_id,
internal_generation, capsule_id, effective_event_id),
  CONSTRAINT fk_p3_page_rows_01 FOREIGN KEY(tenant_id, game_id,
internal_generation, capsule_id) REFERENCES
sync_fence.p3_projection_page_progress (tenant_id, game_id,
internal_generation, capsule_id) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_page_rows_02 FOREIGN KEY(tenant_id, attempt_id, phase_id)
REFERENCES sync_fence.writer_bindings (tenant_id, attempt_id, phase_id) ON
DELETE NO ACTION,
  CONSTRAINT fk_p3_page_rows_03 FOREIGN KEY(tenant_id, original_event_id)
REFERENCES operation_events (tenant_id, id) ON DELETE NO ACTION,
  CONSTRAINT fk_p3_page_rows_04 FOREIGN KEY(tenant_id, effective_event_id)
REFERENCES operation_events (tenant_id, id) ON DELETE NO ACTION
)
""",
    """
CREATE INDEX ix_p3_page_stats_stage_order ON
sync_fence.p3_projection_page_rows (tenant_id, game_id, internal_generation,
capsule_id, d1)
""",
    """
ALTER TABLE sync_fence.p3_projection_page_rows OWNER TO pitchlog_owner
""",
    """
ALTER TABLE sync_fence.p3_projection_page_rows ENABLE ROW LEVEL SECURITY
""",
    """
ALTER TABLE sync_fence.p3_projection_page_rows FORCE ROW LEVEL SECURITY
""",
    """
REVOKE ALL ON TABLE sync_fence.p3_projection_page_rows FROM
PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor
""",
    """
ALTER TABLE sync_fence.stats_primitive_sources DROP CONSTRAINT
ck_stats_source_provider, ADD CONSTRAINT ck_stats_source_provider CHECK
(provider_kind IN ('first_ball','ordinary','past_correction'))
""",
)


def upgrade() -> None:
    """6原本表/全制約/3索引を作り、認可適用まではapp経路を閉じる。"""
    for statement in _STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    """監査原本と世代履歴の物理削除を拒否する。"""
    raise RuntimeError("過去訂正の監査原本を物理削除できません")
