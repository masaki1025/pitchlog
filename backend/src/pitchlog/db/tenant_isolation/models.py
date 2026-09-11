"""テナント分離領域のテナント・チーム・選手モデルを定義する。"""

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


class Tenant(ImportBatchMixin, LifecycleMixin, Base):
    """データ所有と有効状態の単位となるテナント。"""

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("enabled OR disabled_at IS NOT NULL"),
        PrimaryKeyConstraint(
            "id",
            name="pk_tenants",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(),
        allowed_update_columns=frozenset({"name", "enabled", "disabled_at"}),
    )


class TeamRecord(TenantMixin, ImportBatchMixin, LifecycleMixin, Base):
    """自テナントまたは対戦相手を表すチームレコード。"""

    __tablename__ = "team_records"
    __table_args__ = (
        CheckConstraint("kind IN ('self', 'opponent')"),
        CheckConstraint("kind <> 'self' OR hidden_at IS NULL"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_team_records_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_team_records",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "uq_team_records_self",
            "tenant_id",
            unique=True,
            postgresql_where=text("kind = 'self'"),
            info={"roles": ("business_unique",)},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    hidden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.HIDDEN,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"kind"}),
        allowed_update_columns=frozenset({"name", "hidden_at"}),
    )


class Player(TenantMixin, ImportBatchMixin, LifecycleMixin, Base):
    """テナント内の選手と現在の在籍区分を表す。"""

    __tablename__ = "players"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_players_team",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_players",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_players_team",
            "tenant_id",
            "team_record_id",
            "id",
            postgresql_where=text("hidden_at IS NULL"),
            info={"purpose": "lookup"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    team_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    throws: Mapped[str | None] = mapped_column(Text, nullable=True)
    bats: Mapped[str | None] = mapped_column(Text, nullable=True)
    uniform_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    roster_status_key: Mapped[str] = mapped_column(Text, nullable=False)
    roster_label_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.HIDDEN,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id"}),
        allowed_update_columns=frozenset(
            {
                "name",
                "throws",
                "bats",
                "uniform_number",
                "roster_status_key",
                "roster_label_key",
                "hidden_at",
            }
        ),
    )


class MedicalNote(TenantMixin, ImportBatchMixin, RetirementMixin, LifecycleMixin, Base):
    """選手ごとの投手・打者カルテ所見を保持する。"""

    __tablename__ = "medical_notes"
    __table_args__ = (
        CheckConstraint("note_kind IN ('pitcher', 'batter')"),
        CheckConstraint("version > 0"),
        ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_medical_notes_player",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_medical_notes",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "uq_medical_notes_active",
            "tenant_id",
            "player_id",
            "note_kind",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
            info={"roles": ("business_unique",)},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    note_kind: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    hidden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.HIDDEN,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.HAS_PREDICATE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"player_id", "note_kind"}),
        allowed_update_columns=frozenset(
            {"content", "version", "hidden_at", "retired_at"}
        ),
    )


class MedicalNoteVersion(TenantMixin, LifecycleMixin, Base):
    """カルテ所見の復元可能な変更履歴を保持する。"""

    __tablename__ = "medical_note_versions"
    __table_args__ = (
        CheckConstraint("origin IN ('user_edit', 'merge')"),
        CheckConstraint("version > 0"),
        CheckConstraint("origin <> 'merge' OR retained_for_restore"),
        ForeignKeyConstraint(
            ["tenant_id", "medical_note_id"],
            ["medical_notes.tenant_id", "medical_notes.id"],
            name="fk_medical_note_versions_note",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_medical_note_versions",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    medical_note_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'user_edit'")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    retained_for_restore: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"medical_note_id", "version", "content", "origin", "recorded_at"}
        ),
        allowed_update_columns=frozenset({"retained_for_restore"}),
    )


class PdfExportRecord(TenantMixin, LifecycleMixin, Base):
    """PDF 出力時点の対象と適用フィルタを追記専用で記録する。"""

    __tablename__ = "pdf_export_records"
    __table_args__ = (
        CheckConstraint("team_record_id IS NOT NULL OR player_id IS NOT NULL"),
        ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_pdf_export_records_team",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_pdf_export_records_player",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_pdf_export_records",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    team_record_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    player_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    applied_filters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {
                "tenant_id",
                "id",
                "exported_at",
                "team_record_id",
                "player_id",
                "applied_filters",
            }
        ),
        allowed_update_columns=frozenset(),
    )


Index(
    "ix_medical_note_versions_history",
    MedicalNoteVersion.__table__.c.tenant_id,
    MedicalNoteVersion.__table__.c.medical_note_id,
    MedicalNoteVersion.__table__.c.version.desc(),
    info={"purpose": "range_sort"},
)

Index(
    "ix_pdf_export_records_time",
    PdfExportRecord.__table__.c.tenant_id,
    PdfExportRecord.__table__.c.exported_at.desc(),
    PdfExportRecord.__table__.c.id.desc(),
    info={"purpose": "range_sort"},
)
