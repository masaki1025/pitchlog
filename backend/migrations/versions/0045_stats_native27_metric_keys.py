"""BFを含む27個のT5保存キーを既表の閉制約へ追加する。"""

from alembic import op

revision = "0045_stats_native27_metric_keys"
down_revision = "0044_substitution_write_receipt"
branch_labels = None
depends_on = None

_KEYS = (
    "ARRAY['pitch_count','pa','ab','h','hr','bb','hbp','k','sh','sf',"
    "'catcher_interference_reached','runner_interference_reached',"
    "'doubles','triples','total_bases','runs','rbi','stolen_bases',"
    "'pitching_outs','pitcher_k','pitcher_bb','batters_faced','pitcher_hbp',"
    "'hits_allowed','home_runs_allowed','fielding_errors','runs_allowed']::text[]"
)


def upgrade() -> None:
    """旧保存値を再刻印せず、source・版・creditの27閉集合を揃える。"""
    for table, constraint in (
        ("stats_fact_versions", "ck_stats_version_metric_keys"),
        ("stats_primitive_sources", "ck_stats_source_metric_keys"),
    ):
        op.execute(
            f"ALTER TABLE sync_fence.{table} DROP CONSTRAINT {constraint}, "
            f"ADD CONSTRAINT {constraint} CHECK "
            "(array_position(computed_metric_keys,NULL) IS NULL AND "
            "cardinality(computed_metric_keys)<=27 AND "
            f"computed_metric_keys <@ {_KEYS})"
        )
    op.execute(
        "ALTER TABLE sync_fence.stats_primitive_facts "
        "DROP CONSTRAINT ck_stats_fact_metric, "
        "ADD CONSTRAINT ck_stats_fact_metric CHECK "
        f"(metric_id=ANY({_KEYS}))"
    )


def downgrade() -> None:
    """27項目の保存原本を物理除去・26へ暗黙変換しない。"""
    raise RuntimeError("27項目の保存原本を26項目へ暗黙変換できません")
