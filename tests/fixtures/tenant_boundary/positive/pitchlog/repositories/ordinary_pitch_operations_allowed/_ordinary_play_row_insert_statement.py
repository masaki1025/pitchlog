"""全41列INSERTのSQL窓口だけを許す字句正例。実保存の代替ではない。"""
from __future__ import annotations

from typing import cast

from sqlalchemy import Table, bindparam, insert  # ty: ignore[unresolved-import]
from sqlalchemy.sql.dml import Insert  # ty: ignore[unresolved-import]

_PLAY = cast(Table, object())


class ordinary_pitch_operations:
    """正式symbolに対応する閉じたfixture namespace。"""
    @staticmethod
    def _ordinary_play_row_insert_statement() -> Insert:
        """実sourceと同じ全列bindを持ち、接続/実行を許さない。"""
        return insert(_PLAY).values({name: bindparam(name) for name in _PLAY.c.keys()})
