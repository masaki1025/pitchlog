"""条件 1 の is_allowed と 3 つの構文形を表す負例。"""

from pitchlog.authz.rules import is_allowed as is_allowed_decorator  # ty: ignore


@is_allowed_decorator
def decorated() -> None:
    pass


class _Gate:
    """メソッド形を保持する。"""

    def is_allowed(self) -> bool:
        """認可を独自に判定する。"""
        return True


def is_allowed() -> bool:
    return True
