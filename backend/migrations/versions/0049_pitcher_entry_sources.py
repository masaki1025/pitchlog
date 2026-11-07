"""D03投手出場の17列監査原本だけをdefault-denyで配置する。"""

from alembic import op

revision = "0049_pitcher_entry_sources"
down_revision = "0048_p3_projection_storage"
branch_labels = None
depends_on = None

# 型元初版から一回描画した全DDLを固定し、後発modelを実行時にimportしない。
_STATEMENTS = (
    """
CREATE TABLE sync_fence.pitcher_entry_sources (
tenant_id UUID NOT NULL,
game_id UUID NOT NULL,
proof_sha256 TEXT NOT NULL,
origin_kind TEXT NOT NULL,
start_attempt_id UUID,
source_event_id UUID,
generation BIGINT NOT NULL,
d1 BIGINT,
slot_version BIGINT,
player_id UUID NOT NULL,
defending_side TEXT NOT NULL,
inning BIGINT NOT NULL,
half TEXT NOT NULL,
proof_kind TEXT NOT NULL,
source_fingerprint TEXT NOT NULL,
artifact_sha256 TEXT NOT NULL,
context_sha256 TEXT NOT NULL,
PRIMARY KEY (tenant_id, game_id, proof_sha256),
CONSTRAINT fk_pitcher_entry_game FOREIGN KEY(tenant_id, game_id) REFERENCES
games (tenant_id, id) MATCH FULL ON DELETE NO ACTION,
CONSTRAINT fk_pitcher_entry_player FOREIGN KEY(tenant_id, player_id)
REFERENCES players (tenant_id, id) MATCH FULL ON DELETE NO ACTION,
CONSTRAINT fk_pitcher_entry_start FOREIGN KEY(tenant_id, start_attempt_id)
REFERENCES game_start_attempts (tenant_id, attempt_id) ON DELETE NO ACTION,
CONSTRAINT fk_pitcher_entry_event FOREIGN KEY(tenant_id, source_event_id)
REFERENCES operation_events (tenant_id, id) ON DELETE NO ACTION DEFERRABLE
INITIALLY DEFERRED,
CONSTRAINT ck_pitcher_entry_origin CHECK ((origin_kind='start' AND
start_attempt_id IS NOT NULL AND source_event_id IS NULL AND d1 IS NULL AND
slot_version IS NULL AND inning=1 AND half='top') OR (origin_kind IN
('play','substitution','reopen') AND start_attempt_id IS NULL AND
source_event_id IS NOT NULL AND d1 IS NOT NULL AND slot_version IS NOT NULL
AND d1>0 AND slot_version>0)),
CONSTRAINT fk_pitcher_entry_generation FOREIGN KEY(tenant_id, game_id,
generation) REFERENCES recording_generations (tenant_id, game_id, generation)
MATCH FULL ON DELETE NO ACTION,
CONSTRAINT ck_pitcher_entry_reason CHECK ((origin_kind='substitution' AND
proof_kind='pitcher-defensive-entry') OR (origin_kind IN
('start','play','reopen') AND proof_kind='defensive-half-entry')),
CONSTRAINT ck_pitcher_entry_half CHECK (generation>0 AND inning>0 AND
((half='top' AND defending_side='home') OR (half='bottom' AND
defending_side='away'))),
CONSTRAINT ck_pitcher_entry_hashes CHECK (proof_kind IN
('defensive-half-entry','pitcher-defensive-entry') AND proof_sha256 ~
'^[a-f0-9]{64}$' AND context_sha256 ~ '^[a-f0-9]{64}$' AND artifact_sha256 ~
'^[a-f0-9]{64}$' AND source_fingerprint<>'')
)
""",
    """
ALTER TABLE sync_fence.pitcher_entry_sources OWNER TO pitchlog_owner
""",
    """
ALTER TABLE sync_fence.pitcher_entry_sources ENABLE ROW LEVEL SECURITY
""",
    """
ALTER TABLE sync_fence.pitcher_entry_sources FORCE ROW LEVEL SECURITY
""",
    """
REVOKE ALL ON TABLE sync_fence.pitcher_entry_sources FROM
PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_initial_fn_owner,pitchlog_sync_right_fn_owner,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor
""",
    """
CREATE INDEX ix_pitcher_entry_source_player ON
sync_fence.pitcher_entry_sources (tenant_id, game_id, player_id)
""",
)


def upgrade() -> None:
    """所有・全構造とRLSを配置し、別段の正式認可適用までは公開しない。"""
    for statement in _STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    """出場原本と取消訂正の監査証拠の物理削除を拒否する。"""
    raise RuntimeError("投手出場の監査原本を物理削除できません")
