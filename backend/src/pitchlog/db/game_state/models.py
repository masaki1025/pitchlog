"""試合・スタメン・出場区間の状況計算領域モデルを定義する。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
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
    Lifecycle,
    MigrationRetirement,
)


class Game(TenantMixin, ImportBatchMixin, LifecycleMixin, Base):
    """試合と開始時に確定した適用規則を保持する。"""

    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(
            "status IN ('preparing', 'in_progress', 'finished', 'trashed', 'hidden')"
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
        deletion=DeletionLifecycle.DISABLED,
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
    )


class GameTypeRuleDefault(LifecycleMixin, Base):
    """試合区分ごとの既定規則セットを保持する。"""

    __tablename__ = "game_type_rule_defaults"
    __table_args__ = (
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
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset({"rule_set_id"}),
    )


class TournamentRuleAssignment(TenantMixin, LifecycleMixin, Base):
    """テナント内の大会名へ規則セットを割り当てる。"""

    __tablename__ = "tournament_rule_assignments"
    __table_args__ = (
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
    )
