"""API層がDB例外の型名を持たずにゲートするための閉じた例外集合。"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

# SERVICE_UNAVAILABLEへ閉じる対象。APIはこの名前だけを参照する。
DATABASE_ERRORS: tuple[type[Exception], ...] = (SQLAlchemyError,)
