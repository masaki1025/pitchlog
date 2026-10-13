"""無効化意図の INSERT 文の組み立てだけを許可する正例。"""

from sqlalchemy import (  # ty: ignore[unresolved-import]
    Column,
    Integer,
    MetaData,
    Table,
    insert,
)
from sqlalchemy.sql.dml import Insert  # ty: ignore[unresolved-import]

_INTENTS = Table("invalidation_intents", MetaData(), Column("tenant_id", Integer))


def _build_invalidation_intent_statement() -> Insert:
    """無効化意図の単一表 INSERT 文を作る。"""
    return insert(_INTENTS)
