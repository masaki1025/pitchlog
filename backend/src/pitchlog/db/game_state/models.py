"""試合・スタメン・出場区間・プレイ投影の状況計算モデルを定義する。

移行由来のプレイ投影 ID:
- 生成元イベント ID を UUIDv5 の名前空間、旧行識別子を名前として ID を導出する。
- 同じ正本イベントと旧行からの再投影は挿入順や乱数に依存せず同じ ID になり、
  サイドカーの結合先を安定させられるため、この形を採る。
- 旧行識別子が NULL の通常入力はこの導出関数の対象外であり、別途発行された ID を使う。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pitchlog.db.base import Base
from pitchlog.db.mixins import (
    ImportBatchMixin,
    LifecycleMixin,
    RetirementMixin,
    TenantMixin,
)
from pitchlog.db.model_metadata import (
    AppendMode,
    DeletionLifecycle,
    Immutability,
    ImmutabilityCoverage,
    Lifecycle,
    MigrationRetirement,
)


def derive_migrated_play_row_id(
    source_event_id: UUID, legacy_row_identifier: str
) -> UUID:
    """移行由来の投影行 ID を正本イベントと旧行識別子から導出する。

    Args:
        source_event_id: 投影を生成した正本イベント ID。
        legacy_row_identifier: 移行元で同じ行を識別する文字列。

    Returns:
        入力の組に対して決定的な UUIDv5。
    """
    return uuid5(source_event_id, legacy_row_identifier)


class Game(TenantMixin, ImportBatchMixin, LifecycleMixin, Base):
    """試合と開始時に確定した適用規則を保持する。"""

    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(
            "status IN ('preparing', 'in_progress', 'finished', 'trashed', 'hidden')"
        ),
        ForeignKeyConstraint(
            ["game_type_key"],
            ["system_vocabularies.key"],
            name="fk_games_game_type",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "tournament_key"],
            ["tenant_vocabularies.tenant_id", "tenant_vocabularies.key"],
            name="fk_games_tournament",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "away_team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_games_away_team",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "home_team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_games_home_team",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_games",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    game_type_key: Mapped[str] = mapped_column(Text, nullable=False)
    tournament_key: Mapped[str] = mapped_column(Text, nullable=False)
    away_team_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    home_team_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    plate_umpire: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    week_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    day_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    game_number_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'preparing'")
    )
    applied_rules: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    rule_override: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    trashed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hidden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.TRASH,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset(
            {"status", "started_at", "trashed_at", "hidden_at"}
        ),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


Index(
    "ix_games_list",
    Game.__table__.c.tenant_id,
    Game.__table__.c.scheduled_at.desc(),
    Game.__table__.c.id.desc(),
    postgresql_where=text("trashed_at IS NULL AND hidden_at IS NULL"),
    info={"purpose": "range_sort"},
)


class LineupMemory(
    TenantMixin, ImportBatchMixin, RetirementMixin, LifecycleMixin, Base
):
    """チームごとの直近スタメン記憶を保持する。"""

    __tablename__ = "lineup_memories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_lineup_memories_team",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_lineup_memories",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "uq_lineup_memories_active",
            "tenant_id",
            "team_record_id",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
            info={"roles": ("business_unique",)},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    team_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    lineup: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    migration_preserved_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.HAS_PREDICATE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset({"lineup", "retired_at"}),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


class GameLineup(TenantMixin, ImportBatchMixin, LifecycleMixin, Base):
    """先発選手と試合時点の背番号を不変スナップショットで保持する。"""

    __tablename__ = "game_lineups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_game_lineups_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_game_lineups_team",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_game_lineups",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_game_lineups_game",
            "tenant_id",
            "game_id",
            "team_record_id",
            info={"purpose": "lookup"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    team_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entries_with_uniform_number_snapshot: Mapped[list[dict[str, object]]] = (
        mapped_column(JSONB, nullable=False)
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"entries_with_uniform_number_snapshot"}),
        allowed_update_columns=frozenset(),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


class ParticipationInterval(
    TenantMixin, ImportBatchMixin, RetirementMixin, LifecycleMixin, Base
):
    """イベントから再生成する選手の出場区間投影を保持する。"""

    __tablename__ = "participation_intervals"
    __table_args__ = (
        CheckConstraint("slot_kind IN ('batting_order', 'fielding_position')"),
        CheckConstraint("valid_until_d2 IS NULL OR valid_until_d2 > valid_from_d2"),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_participation_intervals_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_participation_intervals_player",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_participation_intervals",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "uq_participation_intervals_active",
            "tenant_id",
            "game_id",
            "slot_kind",
            "slot",
            "valid_from_d2",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
            info={"roles": ("business_unique",)},
        ),
        Index(
            "ix_participation_intervals_range",
            "tenant_id",
            "game_id",
            "valid_from_d2",
            "valid_until_d2",
            postgresql_where=text("retired_at IS NULL"),
            info={"purpose": "range_sort"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    slot_kind: Mapped[str] = mapped_column(Text, nullable=False)
    slot: Mapped[str] = mapped_column(Text, nullable=False)
    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    valid_from_d2: Mapped[int] = mapped_column(BigInteger, nullable=False)
    valid_until_d2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uniform_number_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    unknown_for_migration: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.HAS_PREDICATE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset({"valid_until_d2", "retired_at"}),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


class RuleSet(LifecycleMixin, Base):
    """試合へ適用するシステム全体の規則定義を保持する。"""

    __tablename__ = "rule_sets"
    __table_args__ = (
        CheckConstraint("regulation_innings > 0"),
        CheckConstraint(
            "extra_innings_limit IS NULL OR extra_innings_limit >= regulation_innings"
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_rule_sets",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    regulation_innings: Mapped[int] = mapped_column(Integer, nullable=False)
    called_game_conditions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    extra_innings_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tiebreak_rule: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    uses_dh: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset(
            {
                "regulation_innings",
                "called_game_conditions",
                "extra_innings_limit",
                "tiebreak_rule",
                "uses_dh",
            }
        ),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


class GameTypeRuleDefault(LifecycleMixin, Base):
    """試合区分ごとの既定規則セットを保持する。"""

    __tablename__ = "game_type_rule_defaults"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_type_key"],
            ["system_vocabularies.key"],
            name="fk_game_type_rule_defaults_type",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name="fk_game_type_rule_defaults_rule",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "game_type_key",
            name="pk_game_type_rule_defaults",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    game_type_key: Mapped[str] = mapped_column(Text, nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset({"rule_set_id"}),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


class TournamentRuleAssignment(TenantMixin, LifecycleMixin, Base):
    """テナント内の大会名へ規則セットを割り当てる。"""

    __tablename__ = "tournament_rule_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "tournament_key"],
            ["tenant_vocabularies.tenant_id", "tenant_vocabularies.key"],
            name="fk_tournament_rule_assignments_tournament",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name="fk_tournament_rule_assignments_rule",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "tournament_key",
            name="pk_tournament_rule_assignments",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    tournament_key: Mapped[str] = mapped_column(Text, nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset({"rule_set_id"}),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


class PlayRow(TenantMixin, ImportBatchMixin, LifecycleMixin, Base):
    """操作イベントから再生成できる毎球データの投影行。"""

    __tablename__ = "play_rows"
    __table_args__ = (
        CheckConstraint("event_kind IN ('pitch', 'non_pitch')"),
        CheckConstraint("version > 0"),
        CheckConstraint("course_x IS NULL OR course_x BETWEEN 0 AND 1"),
        CheckConstraint("course_y IS NULL OR course_y BETWEEN 0 AND 1"),
        CheckConstraint(
            "hit_x IS NULL OR hit_x BETWEEN 0 AND 1",
            name="ck_play_rows_hit_x_range",
        ),
        CheckConstraint(
            "hit_y IS NULL OR hit_y BETWEEN 0 AND 1",
            name="ck_play_rows_hit_y_range",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_play_rows_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_play_rows_event",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "strategy_key"],
            ["tenant_vocabularies.tenant_id", "tenant_vocabularies.key"],
            name="fk_play_rows_strategy",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "strategy_detail_key"],
            ["tenant_vocabularies.tenant_id", "tenant_vocabularies.key"],
            name="fk_play_rows_strategy_detail",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "strategy_result_key"],
            ["tenant_vocabularies.tenant_id", "tenant_vocabularies.key"],
            name="fk_play_rows_strategy_result",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "pitch_type_key"],
            ["tenant_vocabularies.tenant_id", "tenant_vocabularies.key"],
            name="fk_play_rows_pitch_type",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["batting_result_key"],
            ["admin_vocabularies.key"],
            name="fk_play_rows_batting_result",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["secondary_batting_result_key"],
            ["admin_vocabularies.key"],
            name="fk_play_rows_secondary_batting_result",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["batted_ball_type"],
            ["admin_vocabularies.key"],
            name="fk_play_rows_batted_ball_type",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["batted_ball_strength"],
            ["admin_vocabularies.key"],
            name="fk_play_rows_batted_ball_strength",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_play_rows",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_play_rows_game_order",
            "tenant_id",
            "game_id",
            "play_number",
            "id",
            postgresql_where=text("hidden_at IS NULL"),
            info={"purpose": "range_sort"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    play_number: Mapped[int] = mapped_column(
        BigInteger, nullable=False, info={"legacy_source_columns": (9,)}
    )
    batting_order: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, info={"legacy_source_columns": (26,)}
    )
    batter_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, info={"legacy_source_columns": (27,)}
    )
    batting_side: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (28,)}
    )
    strategy_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (29,)}
    )
    strategy_detail_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (30,)}
    )
    strategy_result_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (31,)}
    )
    pitcher_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, info={"legacy_source_columns": (32,)}
    )
    catcher_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, info={"legacy_source_columns": (35,)}
    )
    batter_status: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (39,)}
    )
    event_kind: Mapped[str] = mapped_column(
        Text, nullable=False, info={"legacy_source_columns": (40,)}
    )
    stance: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (41,)}
    )
    course_x: Mapped[float | None] = mapped_column(
        Double, nullable=True, info={"legacy_source_columns": (42,)}
    )
    course_y: Mapped[float | None] = mapped_column(
        Double, nullable=True, info={"legacy_source_columns": (43,)}
    )
    pitch_type_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (44,)}
    )
    batting_result_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (45,)}
    )
    secondary_batting_result_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (46,)}
    )
    raw_fielder_position: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (47,)}
    )
    resolved_fielder_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    batted_ball_type: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (48,)}
    )
    batted_ball_strength: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (49,)}
    )
    hit_x: Mapped[float | None] = mapped_column(
        Double, nullable=True, info={"legacy_source_columns": (50,)}
    )
    hit_y: Mapped[float | None] = mapped_column(
        Double, nullable=True, info={"legacy_source_columns": (51,)}
    )
    pickoff_type: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (52,)}
    )
    pickoff_detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (53,)}
    )
    error_type: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (54,)}
    )
    raw_error_position: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (55,)}
    )
    resolved_error_player_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    pitch_speed: Mapped[float | None] = mapped_column(
        Double, nullable=True, info={"legacy_source_columns": (56,)}
    )
    press: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (57,)}
    )
    fake_run: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (58,)}
    )
    comment: Mapped[str | None] = mapped_column(
        Text, nullable=True, info={"legacy_source_columns": (60,)}
    )
    version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    hidden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    legacy_row_identifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    migration_unverified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.HIDDEN,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id", "source_event_id", "legacy_row_identifier"}),
        allowed_update_columns=frozenset({"version", "hidden_at"}),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


class PlayRunner(TenantMixin, ImportBatchMixin, RetirementMixin, LifecycleMixin, Base):
    """プレイ時点の各塁の走者と責任投手を1行ずつ保持する。"""

    __tablename__ = "play_runners"
    __table_args__ = (
        CheckConstraint("base IN (1, 2, 3)"),
        CheckConstraint(
            "status_source IN ('auto', 'manual')",
            name="ck_play_runners_status_source",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "play_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="fk_play_runners_play",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "runner_id"],
            ["players.tenant_id", "players.id"],
            name="fk_play_runners_runner",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "responsible_pitcher_id"],
            ["players.tenant_id", "players.id"],
            name="fk_play_runners_pitcher",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_play_runners",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "uq_play_runners_active",
            "tenant_id",
            "play_id",
            "base",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
            info={"roles": ("business_unique",)},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    play_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    base: Mapped[int] = mapped_column(Integer, nullable=False)
    runner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_source: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_pitcher_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.HAS_PREDICATE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset({"status", "status_source", "retired_at"}),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )
