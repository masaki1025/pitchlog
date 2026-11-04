"""binding制御の固定文実行だけの正例。"""

from __future__ import annotations

from typing import Any, Literal, LiteralString


class _BindingAuthority:
    """製品クラスの登録methodを表す。"""

    _connection: Any

    def _call(
        self,
        which: str,
        statement: LiteralString,
        params: tuple[object, ...],
        *,
        write: bool = False,
        confirmed_rejection: Literal["register", "publish"] | None = None,
    ) -> tuple[Any, ...]:
        """固定文の実行だけを表す。"""
        del which, params, write, confirmed_rejection
        return (self._connection.execute(statement).fetchone(),)
