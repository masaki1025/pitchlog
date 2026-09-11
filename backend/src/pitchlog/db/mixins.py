"""複数領域の ORM モデルが共有する mixin を定義する。"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from pitchlog.db.model_metadata import Immutability, Lifecycle


class TenantMixin:
    """テナント所有表へ必須のテナント識別子を付与する。"""

    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class LifecycleMixin:
    """表単位のライフサイクル 3 軸と不変列マトリクスを宣言する。"""

    lifecycle: ClassVar[Lifecycle]
    immutability: ClassVar[Immutability]


class ImportBatchMixin:
    """通常作成行と移行作成行を区別する取り込みバッチ識別子を付与する。"""

    import_batch_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class RetirementMixin:
    """移行バッチ由来の行へ退役述語となる日時を付与する。"""

    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
