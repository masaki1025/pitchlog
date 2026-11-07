"""受理済みT5原本・credit・版をdefault-denyで保持する候補モデル。"""

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from pitchlog.db.base import Base
from pitchlog.db.mixins import LifecycleMixin
from pitchlog.db.model_metadata import (
    AppendMode,
    DeletionLifecycle,
    Immutability,
    ImmutabilityCoverage,
    Lifecycle,
    MigrationRetirement,
)
from pitchlog.stats.generated.receiver import METRIC_IDS

_SCHEMA = "sync_fence"
_METRIC_SQL = "ARRAY[" + ",".join(repr(x) for x in METRIC_IDS) + "]::text[]"


def _fk(local, remote, name):
    """tenantを含む原本参照を物理cascadeなしで作る。"""
    return ForeignKeyConstraint(
        local, remote, name=name, ondelete="NO ACTION", info={"cross_tenant": False}
    )


def _lifecycle(mutable=False):
    """保存原本を物理削除せず、失効は版の状態だけに閉じる。"""
    return Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE if mutable else AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )


def _immutability(table, mutable=frozenset()):
    """条件付き更新列を除く全列を不変とする。"""
    return Immutability(
        protected_columns=frozenset(table.c.keys()) - mutable,
        allowed_update_columns=frozenset(),
        conditional_update_columns=mutable,
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )


class StatsFactVersion(LifecycleMixin, Base):
    """source集合と生成model/rule/artifactに束縛された追記版。"""

    __table__ = Table(
        "stats_fact_versions",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("id", Uuid, nullable=False),
        Column("model_sha256", Text, nullable=False),
        Column("rule_sha256", Text, nullable=False),
        Column("t5_artifact_set_sha256", Text, nullable=False),
        Column("source_set_sha256", Text, nullable=False),
        Column("source_count", BigInteger, nullable=False),
        Column("revision", BigInteger, nullable=False),
        Column("last_generation", BigInteger, nullable=True),
        Column("last_d1", BigInteger, nullable=True),
        Column("last_d2", BigInteger, nullable=True),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Column("computed_metric_keys", ARRAY(Text), nullable=False),
        Column("is_current", Boolean, nullable=False),
        Column("completion_state", Text, nullable=False),
        Column("completion_receipt_id", Uuid, nullable=True),
        Column("public_pointer_receipt_id", Uuid, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("invalidated_at", DateTime(timezone=True), nullable=True),
        PrimaryKeyConstraint("tenant_id", "game_id", "id"),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "game_id", "id", "rule_sha256"),
        _fk(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            "fk_stats_version_game",
        ),
        CheckConstraint(
            "model_sha256 ~ '^sha256:[a-f0-9]{64}$' AND "
            "rule_sha256 ~ '^[a-f0-9]{64}$' AND "
            "t5_artifact_set_sha256 ~ '^[a-f0-9]{64}$' AND "
            "source_set_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_stats_version_hashes",
        ),
        CheckConstraint(
            "source_count>=0 AND revision>0", name="ck_stats_version_count"
        ),
        CheckConstraint(
            "(source_count=0 AND last_generation IS NULL AND "
            "last_d1 IS NULL AND last_d2 IS NULL) OR "
            "(last_generation IS NOT NULL AND last_d1 IS NOT NULL AND "
            "last_d2 IS NOT NULL "
            "AND last_generation>0 AND last_d1>0)",
            name="ck_stats_version_position",
        ),
        CheckConstraint(
            "array_position(computed_metric_keys,NULL) IS NULL AND "
            "cardinality(computed_metric_keys)<=27 AND "
            f"computed_metric_keys <@ {_METRIC_SQL}",
            name="ck_stats_version_metric_keys",
        ),
        CheckConstraint(
            "completion_state IN ('current_open','confirmed_ended') AND "
            "(completion_state<>'confirmed_ended' OR "
            "(completion_receipt_id IS NOT NULL AND "
            "public_pointer_receipt_id IS NOT NULL))",
            name="ck_stats_version_completion_shape",
        ),
        CheckConstraint(
            "NOT is_current OR invalidated_at IS NULL", name="ck_stats_version_current"
        ),
        schema=_SCHEMA,
    )
    lifecycle = _lifecycle(True)
    # 内容更新はrootのcurrent_open同frame CASだけ。終了確定後は内容を凍結する。
    immutability = _immutability(
        __table__,
        frozenset(
            {
                "is_current",
                "invalidated_at",
                "revision",
                "source_set_sha256",
                "source_count",
                "computed_metric_keys",
                "last_generation",
                "last_d1",
                "last_d2",
                "updated_at",
            }
        ),
    )


Index(
    "uq_stats_current_game_model",
    StatsFactVersion.__table__.c.tenant_id,
    StatsFactVersion.__table__.c.game_id,
    StatsFactVersion.__table__.c.model_sha256,
    unique=True,
    postgresql_where=text("is_current"),
)


class StatsPrimitiveSource(LifecycleMixin, Base):
    """寄与0を含む実source一件と計算済み群を版へ保存する。"""

    __table__ = Table(
        "stats_primitive_sources",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("fact_version_id", Uuid, nullable=False),
        Column("source_event_id", Uuid, nullable=False),
        Column("play_row_id", Uuid, nullable=False),
        Column("recording_generation", BigInteger, nullable=False),
        Column("d1", BigInteger, nullable=False),
        Column("d2", BigInteger, nullable=False),
        Column("slot_version", BigInteger, nullable=False),
        Column("play_row_version", BigInteger, nullable=False),
        Column("provider_kind", Text, nullable=False),
        Column("attempt_id", Uuid, nullable=False),
        Column("phase_id", Uuid, nullable=False),
        Column("wire_d4", Text, nullable=False),
        Column("source_fingerprint", Text, nullable=False),
        Column("checkpoint_id", Uuid, nullable=True),
        Column("checkpoint_revision", BigInteger, nullable=True),
        Column("checkpoint_digest", Text, nullable=True),
        Column("frame_digest", Text, nullable=True),
        Column("evaluation_sha256", Text, nullable=False),
        Column("artifact_sha256", Text, nullable=False),
        Column("rule_sha256", Text, nullable=False),
        Column("metric_states", JSONB, nullable=False),
        Column("computed_metric_keys", ARRAY(Text), nullable=False),
        Column("saved_at", DateTime(timezone=True), nullable=False),
        PrimaryKeyConstraint(
            "tenant_id", "game_id", "fact_version_id", "source_event_id"
        ),
        UniqueConstraint(
            "tenant_id",
            "game_id",
            "fact_version_id",
            "recording_generation",
            "d1",
            "slot_version",
        ),
        _fk(
            ["tenant_id", "game_id", "fact_version_id", "rule_sha256"],
            [
                f"{_SCHEMA}.stats_fact_versions.{x}"
                for x in ("tenant_id", "game_id", "id", "rule_sha256")
            ],
            "fk_stats_source_version",
        ),
        _fk(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            "fk_stats_source_event",
        ),
        _fk(
            ["tenant_id", "play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            "fk_stats_source_play",
        ),
        _fk(
            ["tenant_id", "game_id", "recording_generation", "d1"],
            [f"event_slots.{x}" for x in ("tenant_id", "game_id", "generation", "d1")],
            "fk_stats_source_slot",
        ),
        _fk(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                f"{_SCHEMA}.writer_bindings.{x}"
                for x in ("tenant_id", "attempt_id", "phase_id")
            ],
            "fk_stats_source_binding",
        ),
        CheckConstraint(
            "recording_generation>0 AND d1>0 AND slot_version>0 AND play_row_version>0",
            name="ck_stats_source_positions",
        ),
        CheckConstraint(
            "provider_kind IN ('first_ball','ordinary','past_correction')",
            name="ck_stats_source_provider",
        ),
        CheckConstraint(
            "source_fingerprint ~ '^(wire-v1:)?[a-f0-9]{64}$' AND length(wire_d4)>0",
            name="ck_stats_source_fingerprint",
        ),
        CheckConstraint(
            "(checkpoint_id IS NULL AND checkpoint_revision IS NULL AND "
            "checkpoint_digest IS NULL) OR "
            "(checkpoint_id IS NOT NULL AND checkpoint_revision IS NOT NULL AND "
            "checkpoint_digest IS NOT NULL AND checkpoint_revision>0 AND "
            "checkpoint_digest ~ '^[a-f0-9]{64}$')",
            name="ck_stats_source_checkpoint",
        ),
        CheckConstraint(
            "provider_kind<>'ordinary' OR (checkpoint_id IS NOT NULL AND "
            "frame_digest IS NOT NULL)",
            name="ck_stats_source_ordinary_proof",
        ),
        CheckConstraint(
            "evaluation_sha256 ~ '^[a-f0-9]{64}$' AND "
            "artifact_sha256 ~ '^[a-f0-9]{64}$' AND "
            "rule_sha256 ~ '^[a-f0-9]{64}$' AND "
            "jsonb_typeof(metric_states)='object'",
            name="ck_stats_source_evaluation",
        ),
        CheckConstraint(
            "frame_digest IS NULL OR frame_digest ~ '^[a-f0-9]{64}$'",
            name="ck_stats_source_frame",
        ),
        CheckConstraint(
            "array_position(computed_metric_keys,NULL) IS NULL AND "
            "cardinality(computed_metric_keys)<=27 AND "
            f"computed_metric_keys <@ {_METRIC_SQL}",
            name="ck_stats_source_metric_keys",
        ),
        schema=_SCHEMA,
    )
    lifecycle = _lifecycle()
    immutability = _immutability(__table__)


Index(
    "ix_stats_source_logical",
    StatsPrimitiveSource.__table__.c.tenant_id,
    StatsPrimitiveSource.__table__.c.game_id,
    StatsPrimitiveSource.__table__.c.fact_version_id,
    StatsPrimitiveSource.__table__.c.d2,
    StatsPrimitiveSource.__table__.c.source_event_id,
)


class StatsPrimitiveFact(LifecycleMixin, Base):
    """共通T5で形成した選手別creditの整数amountだけを保持する。"""

    __table__ = Table(
        "stats_primitive_facts",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("fact_version_id", Uuid, nullable=False),
        Column("source_event_id", Uuid, nullable=False),
        Column("metric_id", Text, nullable=False),
        Column("player_id", Uuid, nullable=False),
        Column("credit_ordinal", BigInteger, nullable=False),
        Column("state", Text, nullable=False),
        Column("amount", Numeric(asdecimal=True), nullable=True),
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "fact_version_id",
            "source_event_id",
            "metric_id",
            "player_id",
            "credit_ordinal",
        ),
        _fk(
            ["tenant_id", "game_id", "fact_version_id", "source_event_id"],
            [
                f"{_SCHEMA}.stats_primitive_sources.{x}"
                for x in ("tenant_id", "game_id", "fact_version_id", "source_event_id")
            ],
            "fk_stats_fact_source",
        ),
        _fk(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            "fk_stats_fact_player",
        ),
        CheckConstraint(
            "credit_ordinal>=0 AND credit_ordinal<4", name="ck_stats_fact_ordinal"
        ),
        CheckConstraint(f"metric_id=ANY({_METRIC_SQL})", name="ck_stats_fact_metric"),
        CheckConstraint(
            "(state='source_unavailable' AND amount IS NULL) OR "
            "(state='available' AND amount IS NOT NULL AND amount>=0 AND "
            "amount=trunc(amount) "
            "AND amount NOT IN "
            "('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))",
            name="ck_stats_fact_value",
        ),
        schema=_SCHEMA,
    )
    lifecycle = _lifecycle()
    immutability = _immutability(__table__)


Index(
    "ix_stats_fact_player_metric",
    StatsPrimitiveFact.__table__.c.tenant_id,
    StatsPrimitiveFact.__table__.c.game_id,
    StatsPrimitiveFact.__table__.c.fact_version_id,
    StatsPrimitiveFact.__table__.c.player_id,
    StatsPrimitiveFact.__table__.c.metric_id,
    StatsPrimitiveFact.__table__.c.source_event_id,
)
