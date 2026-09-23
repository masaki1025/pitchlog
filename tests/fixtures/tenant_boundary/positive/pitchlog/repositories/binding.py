"""テナント文脈束縛シンボルの将来契約を表す正例。"""

from collections.abc import Iterator
from contextlib import contextmanager

from pitchlog.repositories.context import TenantContext
from sqlalchemy import text  # ty: ignore
from sqlalchemy.orm import Session  # ty: ignore


@contextmanager
def _tenant_transaction(
    session: Session,
    context: TenantContext,
) -> Iterator[None]:
    """トランザクションの先頭で transaction-local な文脈を束縛する。"""
    with session.begin():
        session.connection()
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(context.tenant_id)},
        )
        yield
