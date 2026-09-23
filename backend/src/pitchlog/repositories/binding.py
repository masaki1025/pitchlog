"""業務トランザクションへテナント文脈を束縛する。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from pitchlog.repositories.context import TenantContext

_BOUND_TENANT_INFO_KEY = "pitchlog.tenant_binding.tenant_id"


class TenantBindingError(RuntimeError):
    """テナント文脈を安全な業務トランザクションへ束縛できない。"""


def _is_autocommit_connection(connection: Connection) -> bool:
    """SQLAlchemy 接続または psycopg 物理接続の autocommit を判定する。

    Args:
        connection: ``Session`` が取得した SQLAlchemy 接続。

    Returns:
        transaction-local な設定を維持できない接続なら ``True``。
    """
    isolation_level = connection.get_execution_options().get("isolation_level")
    if isinstance(isolation_level, str) and isolation_level.upper() == "AUTOCOMMIT":
        return True
    driver_connection: Any = connection.connection.driver_connection
    return getattr(driver_connection, "autocommit", False) is True


@contextmanager
def _tenant_transaction(
    session: Session,
    context: TenantContext,
) -> Iterator[None]:
    """新しい業務トランザクションの先頭へテナント文脈を束縛する。

    この非公開境界は任意 SQL の実行口を公開しない。後続ステップの
    リポジトリ基底が内部利用し、呼び出し元には ``Session`` を渡さない。

    Args:
        session: リクエスト専用の未使用 SQLAlchemy Session。
        context: API 層が認証済み主体から引き渡したテナント文脈。

    Yields:
        束縛済みトランザクションの有効期間。値は返さない。

    Raises:
        TenantBindingError: 文脈欠落、既存トランザクション、Session の再利用、
            または autocommit 接続を検出した場合。
    """
    if not isinstance(context, TenantContext):
        raise TenantBindingError("TenantContext が無いため業務 SQL を開始できない")
    if _BOUND_TENANT_INFO_KEY in session.info:
        raise TenantBindingError("同一 Session へテナント文脈を再束縛できない")
    if session.in_transaction():
        raise TenantBindingError("未束縛の既存トランザクションへ参加できない")

    session.info[_BOUND_TENANT_INFO_KEY] = context.tenant_id
    with session.begin():
        connection = session.connection()
        if _is_autocommit_connection(connection):
            raise TenantBindingError("autocommit 接続へテナント文脈を束縛できない")
        configured_tenant_id = session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(context.tenant_id)},
        ).scalar_one()
        if configured_tenant_id != str(context.tenant_id):
            raise TenantBindingError("テナント文脈の束縛結果が要求値と一致しない")
        yield
