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
    UniqueConstraint,
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
        ForeignKeyConstraint(
            ["roster_status_key"],
            ["system_vocabularies.key"],
            name="fk_players_roster_status",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "roster_label_key"],
            ["tenant_vocabularies.tenant_id", "tenant_vocabularies.key"],
            name="fk_players_roster_label",
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


class TenantAuthSubject(TenantMixin, LifecycleMixin, Base):
    """テナント利用者の認証主体を資格情報から分離して保持する。"""

    __tablename__ = "tenant_auth_subjects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_auth_subjects_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_tenant_auth_subjects",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_tenant_auth_subjects_tenant",
            "tenant_id",
            "id",
            info={"purpose": "lookup"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id", "tenant_id"}),
        allowed_update_columns=frozenset(),
    )


class TenantCredential(LifecycleMixin, Base):
    """テナント認証主体ごとの bcrypt ハッシュと資格情報世代を保持する。"""

    __tablename__ = "tenant_credentials"
    __table_args__ = (
        CheckConstraint("generation > 0"),
        ForeignKeyConstraint(
            ["auth_subject_id"],
            ["tenant_auth_subjects.id"],
            name="fk_tenant_credentials_subject",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "auth_subject_id",
            name="pk_tenant_credentials",
            info={"roles": ("business_unique", "primary_key", "fk_target")},
        ),
    )

    auth_subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"auth_subject_id"}),
        allowed_update_columns=frozenset(
            {"password_hash", "generation", "password_changed_at"}
        ),
    )


class AdminCredential(LifecycleMixin, Base):
    """テナントに属さない管理者資格情報を保持する。"""

    __tablename__ = "admin_credentials"
    __table_args__ = (
        CheckConstraint("generation > 0"),
        PrimaryKeyConstraint(
            "id",
            name="pk_admin_credentials",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id"}),
        allowed_update_columns=frozenset(
            {"password_hash", "generation", "password_changed_at"}
        ),
    )


class AdminSession(LifecycleMixin, Base):
    """管理者資格情報の世代へ結び付く管理者セッションを保持する。"""

    __tablename__ = "admin_sessions"
    __table_args__ = (
        CheckConstraint("credential_generation > 0"),
        CheckConstraint("expires_at >= last_used_at"),
        ForeignKeyConstraint(
            ["admin_credential_id"],
            ["admin_credentials.id"],
            name="fk_admin_sessions_credential",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_admin_sessions",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_admin_sessions_expiry",
            "expires_at",
            "id",
            info={"purpose": "range_sort"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    admin_credential_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    credential_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"id", "admin_credential_id", "credential_generation"}
        ),
        allowed_update_columns=frozenset({"expires_at", "last_used_at"}),
    )


class TenantToken(TenantMixin, LifecycleMixin, Base):
    """テナント認証主体の資格情報世代へ結び付く通常トークン。"""

    __tablename__ = "tenant_tokens"
    __table_args__ = (
        CheckConstraint("credential_generation > 0"),
        CheckConstraint("expires_at >= last_used_at"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_tokens_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["auth_subject_id"],
            ["tenant_auth_subjects.id"],
            name="fk_tenant_tokens_subject",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_tenant_tokens",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_tenant_tokens_expiry",
            "tenant_id",
            "expires_at",
            "id",
            info={"purpose": "range_sort"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    auth_subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    credential_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"id", "tenant_id", "auth_subject_id", "credential_generation"}
        ),
        allowed_update_columns=frozenset({"expires_at", "last_used_at"}),
    )


class AdminOperationLog(LifecycleMixin, Base):
    """管理者操作の監査記録を保持する。

    NFR-017 の一般ログとは別であり、この表は管理者操作の監査記録に限る。
    """

    __tablename__ = "admin_operation_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id"],
            ["analysis_groups.id"],
            name="fk_admin_operation_logs_group",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": True},
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_admin_operation_logs_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_admin_operation_logs",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    operation_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    group_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {
                "id",
                "occurred_at",
                "operation_kind",
                "target",
                "tenant_id",
                "group_id",
            }
        ),
        allowed_update_columns=frozenset(),
    )


Index(
    "ix_admin_operation_logs_time",
    AdminOperationLog.__table__.c.occurred_at.desc(),
    AdminOperationLog.__table__.c.id.desc(),
    info={"purpose": "range_sort"},
)


class PlayerMergeEvent(TenantMixin, LifecycleMixin, Base):
    """選手統合と取り消しの監査事実を保持する。"""

    __tablename__ = "player_merge_events"
    __table_args__ = (
        CheckConstraint("source_player_id <> target_player_id"),
        ForeignKeyConstraint(
            ["tenant_id", "source_player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_player_merge_events_source",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_player_merge_events_target",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_player_merge_events",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    executor: Mapped[str] = mapped_column(Text, nullable=False)
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"source_player_id", "target_player_id", "occurred_at", "executor"}
        ),
        allowed_update_columns=frozenset({"reverted_at"}),
    )


Index(
    "ix_player_merge_events_time",
    PlayerMergeEvent.__table__.c.tenant_id,
    PlayerMergeEvent.__table__.c.occurred_at.desc(),
    PlayerMergeEvent.__table__.c.id.desc(),
    info={"purpose": "range_sort"},
)


class PlayerMoveRecord(TenantMixin, LifecycleMixin, Base):
    """選手統合に伴う資源の移動先と移動元を記録する。"""

    __tablename__ = "player_move_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "merge_event_id"],
            ["player_merge_events.tenant_id", "player_merge_events.id"],
            name="fk_player_move_records_merge",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "original_player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_player_move_records_original_player",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "moved_player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_player_move_records_moved_player",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_player_move_records",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    merge_event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resource_kind: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    original_player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    moved_player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    medical_note_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {
                "tenant_id",
                "id",
                "merge_event_id",
                "resource_kind",
                "resource_id",
                "original_player_id",
                "moved_player_id",
                "medical_note_version_id",
            }
        ),
        allowed_update_columns=frozenset(),
    )


Index(
    "ix_player_move_records_merge",
    PlayerMoveRecord.__table__.c.tenant_id,
    PlayerMoveRecord.__table__.c.merge_event_id,
    PlayerMoveRecord.__table__.c.id,
    info={"purpose": "lookup"},
)


class RateLimitCounter(LifecycleMixin, Base):
    """認証主体の確定前に適用するレート制限の窓と回数を保持する。"""

    __tablename__ = "rate_limit_counters"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0"),
        PrimaryKeyConstraint(
            "id",
            name="pk_rate_limit_counters",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    scope_key: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id", "scope_key", "window_start"}),
        allowed_update_columns=frozenset({"attempt_count", "locked_until"}),
    )


Index(
    "ix_rate_limit_counters_window",
    RateLimitCounter.__table__.c.scope_key,
    RateLimitCounter.__table__.c.window_start.desc(),
    RateLimitCounter.__table__.c.id,
    info={"purpose": "range_sort"},
)


class AnalysisGroup(LifecycleMixin, Base):
    """複数テナントが参加できる分析グループを保持する。"""

    __tablename__ = "analysis_groups"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'terminated')"),
        CheckConstraint("(status = 'terminated') = (terminated_at IS NOT NULL)"),
        PrimaryKeyConstraint(
            "id",
            name="pk_analysis_groups",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'")
    )
    terminated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    termination_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.ENDED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id"}),
        allowed_update_columns=frozenset(
            {"status", "terminated_at", "termination_reason"}
        ),
    )


class GroupMembership(TenantMixin, LifecycleMixin, Base):
    """分析グループへのテナント参加と役割を保持する。"""

    __tablename__ = "group_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'member')"),
        CheckConstraint("status IN ('active', 'left')"),
        ForeignKeyConstraint(
            ["group_id"],
            ["analysis_groups.id"],
            name="fk_group_memberships_group",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": True},
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_group_memberships_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": True},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_group_memberships",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "uq_group_memberships_active",
            "group_id",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            info={"roles": ("business_unique",)},
        ),
        Index(
            "ix_group_memberships_tenant",
            "tenant_id",
            "status",
            "group_id",
            info={"purpose": "lookup"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'member'")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.ENDED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id", "group_id", "tenant_id", "joined_at"}),
        allowed_update_columns=frozenset({"role", "status", "left_at"}),
    )


class SharingGrant(LifecycleMixin, Base):
    """参加行ごとの共有権限を高々1件保持する。"""

    __tablename__ = "sharing_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["membership_id"],
            ["group_memberships.id"],
            name="fk_sharing_grants_membership",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": True},
        ),
        PrimaryKeyConstraint(
            "membership_id",
            name="pk_sharing_grants",
            info={"roles": ("business_unique", "primary_key", "fk_target")},
        ),
    )

    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    grant_flags: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"membership_id"}),
        allowed_update_columns=frozenset({"grant_flags"}),
    )


class GroupInvitation(LifecycleMixin, Base):
    """テナントを跨いで一意なハッシュを持つグループ招待。"""

    __tablename__ = "group_invitations"
    __table_args__ = (
        CheckConstraint("status IN ('unconsumed', 'consumed', 'revoked')"),
        CheckConstraint("initial_role IN ('admin', 'member')"),
        ForeignKeyConstraint(
            ["group_id"],
            ["analysis_groups.id"],
            name="fk_group_invitations_group",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": True},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_group_invitations",
            info={"roles": ("primary_key", "fk_target")},
        ),
        UniqueConstraint(
            "code_hash",
            name="uq_group_invitations_code_hash",
            info={"roles": ("business_unique",)},
        ),
        Index(
            "ix_group_invitations_expiry",
            "expires_at",
            "id",
            postgresql_where=text("status = 'unconsumed'"),
            info={"purpose": "range_sort"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'unconsumed'")
    )
    initial_role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'member'")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.ENDED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id", "group_id", "code_hash", "initial_role"}),
        allowed_update_columns=frozenset({"status"}),
    )


Index(
    "ix_medical_note_versions_history",
    MedicalNoteVersion.__table__.c.tenant_id,
    MedicalNoteVersion.__table__.c.medical_note_id,
    MedicalNoteVersion.__table__.c.version.desc(),
    info={"purpose": "range_sort"},
)


class SystemVocabulary(LifecycleMixin, Base):
    """試合区分と在籍区分の変更不可なシステム固定語彙。"""

    __tablename__ = "system_vocabularies"
    __table_args__ = (
        CheckConstraint("category IN ('game_type', 'roster_status')"),
        PrimaryKeyConstraint(
            "key",
            name="pk_system_vocabularies",
            info={"roles": ("business_unique", "primary_key", "fk_target")},
        ),
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"key", "category", "display_name", "disabled"}),
        allowed_update_columns=frozenset(),
    )


class AdminVocabulary(LifecycleMixin, Base):
    """システム管理者が表示と無効状態を管理する語彙。"""

    __tablename__ = "admin_vocabularies"
    __table_args__ = (
        CheckConstraint("category IN ('batting_result', 'batted_ball', 'season')"),
        PrimaryKeyConstraint(
            "key",
            name="pk_admin_vocabularies",
            info={"roles": ("business_unique", "primary_key", "fk_target")},
        ),
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"key", "category"}),
        allowed_update_columns=frozenset({"display_name", "disabled"}),
    )


class TenantVocabulary(TenantMixin, LifecycleMixin, Base):
    """テナントが拡張できる球種・戦術・大会・在籍ラベル語彙。"""

    __tablename__ = "tenant_vocabularies"
    __table_args__ = (
        CheckConstraint(
            "category IN ('pitch_type', 'strategy', 'tournament', 'roster_label')"
        ),
        CheckConstraint("category <> 'pitch_type' OR pitch_family IS NOT NULL"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_vocabularies_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "key",
            name="pk_tenant_vocabularies",
            info={"roles": ("business_unique", "primary_key", "fk_target")},
        ),
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    pitch_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    abbreviation: Mapped[str | None] = mapped_column(Text, nullable=True)
    disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.DISABLED,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"key", "category"}),
        allowed_update_columns=frozenset(
            {"display_name", "pitch_family", "abbreviation", "disabled"}
        ),
    )


class SystemSetting(LifecycleMixin, Base):
    """システム全体の設定値と更新日時を保持する。"""

    __tablename__ = "system_settings"
    __table_args__ = (
        PrimaryKeyConstraint(
            "key",
            name="pk_system_settings",
            info={"roles": ("business_unique", "primary_key", "fk_target")},
        ),
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"key"}),
        allowed_update_columns=frozenset({"value", "updated_at"}),
    )


Index(
    "ix_pdf_export_records_time",
    PdfExportRecord.__table__.c.tenant_id,
    PdfExportRecord.__table__.c.exported_at.desc(),
    PdfExportRecord.__table__.c.id.desc(),
    info={"purpose": "range_sort"},
)
