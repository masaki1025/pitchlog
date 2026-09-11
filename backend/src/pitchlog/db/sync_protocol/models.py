"""イベントスロットと操作イベントの同期プロトコルモデルを定義する。

不変性の所有判定:
- 正本が禁じているのは「既存イベントの書き換え」= イベントの確定内容の改変である。
- `d2` は採番・`replaced_at` は置換・`retired_at` は退役であり、いずれも
  ライフサイクルの記録であってイベントの内容ではない。これらまで拒否すると訂正イベントによる
  置換や移行の退役が実行できなくなる。
- アプリ層所有にしなかった理由は、アプリ側の全経路が正しく書くことに依存し、
  1 経路の漏れで不変条件が破れるためである(NFR-015)。詳細設計 5-1 節と同じ理由で
  DB トリガが所有する。
- `N3` の受入証跡がこの判定を拾い、manifest の `immutability` が証跡の入力になる。

D5 台帳と原本の対応が保証するのは高々 1 件であり、ちょうど 1 件ではない。
台帳行と原本行の原子書き込みの責務はアプリ層にある。
"""

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


class EventSlot(TenantMixin, LifecycleMixin, Base):
    """試合・記録権世代・D1 で一意なイベント受入スロット。"""

    __tablename__ = "event_slots"
    __table_args__ = (
        CheckConstraint("d1 > 0"),
        CheckConstraint("confirmed_version > 0"),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_event_slots_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "generation"],
            [
                "recording_generations.tenant_id",
                "recording_generations.game_id",
                "recording_generations.generation",
            ],
            name="fk_event_slots_generation",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "generation",
            "d1",
            name="pk_event_slots",
            info={"roles": ("business_unique", "primary_key", "fk_target")},
        ),
    )

    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    d1: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confirmed_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"tenant_id", "game_id", "generation", "d1"}),
        allowed_update_columns=frozenset({"confirmed_version"}),
    )


class OperationEvent(
    TenantMixin, ImportBatchMixin, RetirementMixin, LifecycleMixin, Base
):
    """確定内容を保護しつつ採番・置換・退役を記録できる操作イベント。"""

    __tablename__ = "operation_events"
    __table_args__ = (
        CheckConstraint("ledger_kind = 'accepted'"),
        CheckConstraint("(d1 IS NULL) = (generation IS NULL)"),
        CheckConstraint(
            "event_kind NOT IN ('play_change', 'play_delete', "
            "'substitution_change') OR (d1 IS NULL AND d2 IS NULL AND "
            "generation IS NULL AND target_generation IS NOT NULL AND "
            "target_d1 IS NOT NULL AND expected_version IS NOT NULL)"
        ),
        CheckConstraint(
            "event_kind IN ('play_change', 'play_delete', "
            "'substitution_change') OR d1 IS NOT NULL"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_operation_events_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "generation", "d1"],
            [
                "event_slots.tenant_id",
                "event_slots.game_id",
                "event_slots.generation",
                "event_slots.d1",
            ],
            name="fk_operation_events_slot",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "target_generation", "target_d1"],
            [
                "event_slots.tenant_id",
                "event_slots.game_id",
                "event_slots.generation",
                "event_slots.d1",
            ],
            name="fk_operation_events_target",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "d5", "ledger_kind"],
            [
                "idempotency_ledger.tenant_id",
                "idempotency_ledger.d5",
                "idempotency_ledger.kind",
            ],
            name="fk_operation_events_ledger",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_operation_events",
            info={"roles": ("primary_key", "fk_target")},
        ),
        UniqueConstraint(
            "tenant_id",
            "d5",
            name="uq_operation_events_d5",
            info={"roles": ("business_unique",)},
        ),
        Index(
            "uq_operation_events_active_slot",
            "tenant_id",
            "game_id",
            "generation",
            "d1",
            unique=True,
            postgresql_where=text("d1 IS NOT NULL AND replaced_at IS NULL"),
            info={"roles": ("business_unique",)},
        ),
        Index(
            "uq_operation_events_active_d2",
            "tenant_id",
            "game_id",
            "d2",
            unique=True,
            postgresql_where=text(
                "d2 IS NOT NULL AND replaced_at IS NULL AND retired_at IS NULL"
            ),
            info={"roles": ("business_unique",)},
        ),
        Index(
            "ix_operation_events_replay",
            "tenant_id",
            "game_id",
            "d2",
            "id",
            postgresql_where=text("replaced_at IS NULL AND retired_at IS NULL"),
            info={"purpose": "range_sort"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    d1: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    d2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    d5: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ledger_kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'accepted'")
    )
    event_kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    state_diff: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    replaced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    target_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_d1: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expected_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    change_order: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    legacy_row_identifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    migration_unverified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.HAS_PREDICATE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {
                "tenant_id",
                "id",
                "game_id",
                "generation",
                "d1",
                "d5",
                "event_kind",
                "payload",
                "state_diff",
            }
        ),
        allowed_update_columns=frozenset({"d2", "replaced_at", "retired_at"}),
    )


class TemporaryPlayerIdMapping(TenantMixin, LifecycleMixin, Base):
    """クライアントの一時選手 ID と確定した選手 ID の対応を保持する。"""

    __tablename__ = "temporary_player_id_mappings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_temporary_player_id_mappings_player",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_temporary_player_id_mappings",
            info={"roles": ("primary_key", "fk_target")},
        ),
        UniqueConstraint(
            "tenant_id",
            "temporary_id",
            name="uq_temporary_player_id_mappings_temporary",
            info={"roles": ("business_unique",)},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    temporary_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(
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
        protected_columns=frozenset({"temporary_id", "player_id"}),
        allowed_update_columns=frozenset(),
    )


class IdempotencyLedger(TenantMixin, ImportBatchMixin, LifecycleMixin, Base):
    """D5 ごとの確定結果と原本種別を一意に保持する台帳。"""

    __tablename__ = "idempotency_ledger"
    __table_args__ = (
        CheckConstraint("kind IN ('accepted', 'rejected', 'evacuated')"),
        PrimaryKeyConstraint(
            "tenant_id",
            "d5",
            name="pk_idempotency_ledger",
            info={"roles": ("business_unique", "primary_key")},
        ),
        UniqueConstraint(
            "tenant_id",
            "d5",
            "kind",
            name="uq_idempotency_ledger_kind",
            info={"roles": ("fk_target",)},
        ),
    )

    d5: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"kind", "source_fingerprint", "result", "reason"}),
        allowed_update_columns=frozenset({"retired_at"}),
    )


class RejectedEventOriginal(TenantMixin, LifecycleMixin, Base):
    """拒否された操作イベントの原本を D5 台帳へ結び付けて保持する。"""

    __tablename__ = "rejected_event_originals"
    __table_args__ = (
        CheckConstraint("kind = 'rejected'"),
        ForeignKeyConstraint(
            ["tenant_id", "d5", "kind"],
            [
                "idempotency_ledger.tenant_id",
                "idempotency_ledger.d5",
                "idempotency_ledger.kind",
            ],
            name="fk_rejected_event_originals_ledger",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_rejected_event_originals",
            info={"roles": ("primary_key", "fk_target")},
        ),
        UniqueConstraint(
            "tenant_id",
            "d5",
            name="uq_rejected_event_originals_d5",
            info={"roles": ("business_unique",)},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    d5: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'rejected'")
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
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
        protected_columns=frozenset({"d5", "kind", "payload"}),
        allowed_update_columns=frozenset(),
    )
