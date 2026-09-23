"""条件 1 の may_* と 3 つの構文形を表す負例。"""

from pitchlog.authz.rules import may_edit_game as may_edit_decorator  # ty: ignore


@may_edit_decorator
def decorated() -> None:
    pass


class _Gate:
    """メソッド形を保持する。"""

    def may_edit_game(self) -> bool:
        """認可を独自に判定する。"""
        return True


def may_edit_game() -> bool:
    return True
