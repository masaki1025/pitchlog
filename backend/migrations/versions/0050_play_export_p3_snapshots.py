"""訂正capsuleのCSV監査原本をdefault-denyで配置する。"""

from alembic import op

revision = "0050_play_export_p3_snapshots"
down_revision = "0049_pitcher_entry_sources"
branch_labels = None
depends_on = None

# 初版型元から描画したDDLを固定する。upgradeは将来の型元に依存しない。
_STATEMENTS = (
    """
CREATE TABLE sync_fence.play_export_p3_snapshots (
tenant_id UUID NOT NULL,
game_id UUID NOT NULL,
internal_generation BIGINT NOT NULL,
capsule_id UUID NOT NULL,
d1 BIGINT NOT NULL,
original_play_row_id UUID NOT NULL,
effective_event_id UUID NOT NULL,
effective_play_row_id UUID NOT NULL,
play_row_version BIGINT NOT NULL,
item_digest TEXT NOT NULL,
capsule_source_set_digest TEXT NOT NULL,
capsule_stats_version_id UUID NOT NULL,
plays_csv_json JSONB NOT NULL,
full_innings_json JSONB NOT NULL,
runner_rows_json JSONB NOT NULL,
reference_json JSONB,
captured_at TIMESTAMP WITH TIME ZONE DEFAULT pg_catalog.clock_timestamp() NOT
NULL,
CONSTRAINT play_export_p3_snapshots_pkey PRIMARY KEY (tenant_id, game_id,
internal_generation, capsule_id, d1),
CONSTRAINT fk_play_export_p3_item FOREIGN KEY(tenant_id, game_id,
internal_generation, capsule_id, d1) REFERENCES
sync_fence.p3_projection_capsule_items (tenant_id, game_id, internal_generation,
capsule_id, d1) ON DELETE NO ACTION,
CONSTRAINT fk_play_export_p3_original FOREIGN KEY(tenant_id,
original_play_row_id) REFERENCES play_rows (tenant_id, id) ON DELETE NO ACTION,
CONSTRAINT fk_play_export_p3_effective FOREIGN KEY(tenant_id,
effective_play_row_id) REFERENCES play_rows (tenant_id, id) ON DELETE NO ACTION,
CONSTRAINT fk_play_export_p3_event FOREIGN KEY(tenant_id, effective_event_id)
REFERENCES operation_events (tenant_id, id) ON DELETE NO ACTION,
CONSTRAINT fk_play_export_p3_stats FOREIGN KEY(tenant_id, game_id,
capsule_stats_version_id) REFERENCES sync_fence.stats_fact_versions (tenant_id,
game_id, id) ON DELETE NO ACTION,
CONSTRAINT ck_play_export_p3_generation CHECK (internal_generation > 0),
CONSTRAINT ck_play_export_p3_d1 CHECK (d1 > 0),
CONSTRAINT ck_play_export_p3_version CHECK (play_row_version > 0),
CONSTRAINT ck_play_export_p3_item_digest CHECK (item_digest ~ '^[a-f0-9]{64}$'),
CONSTRAINT ck_play_export_p3_source_digest CHECK (capsule_source_set_digest ~
'^[a-f0-9]{64}$'),
CONSTRAINT ck_play_export_p3_plays CHECK (jsonb_typeof(plays_csv_json) =
'object'),
CONSTRAINT ck_play_export_p3_innings CHECK (jsonb_typeof(full_innings_json) =
'array'),
CONSTRAINT ck_play_export_p3_runners CHECK (jsonb_typeof(runner_rows_json) =
'array'),
CONSTRAINT ck_play_export_p3_reference CHECK (reference_json IS NULL OR
jsonb_typeof(reference_json) = 'object')
)
""",
    """
ALTER TABLE sync_fence.play_export_p3_snapshots OWNER TO pitchlog_owner
""",
    """
ALTER TABLE sync_fence.play_export_p3_snapshots ENABLE ROW LEVEL SECURITY
""",
    """
ALTER TABLE sync_fence.play_export_p3_snapshots FORCE ROW LEVEL SECURITY
""",
    """
REVOKE ALL ON TABLE sync_fence.play_export_p3_snapshots FROM PUBLIC,
pitchlog_app,
pitchlog_initial_actor, pitchlog_initial_fn_owner,
pitchlog_sync_right_fn_owner, pitchlog_sync_binding_actor,
pitchlog_rg1_control_actor
""",
)


def upgrade() -> None:
    """正式ACL適用前には誰にも公開せず、所有と強制RLSを配置する。"""
    for statement in _STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    """取消訂正を含む出力原本の物理削除を拒否する。"""
    raise RuntimeError("訂正CSVの監査原本を物理削除できません")
