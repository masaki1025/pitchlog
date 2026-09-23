"""条件 1 の has_permission と 3 つの構文形を表す負例。"""

from pitchlog.authz.rules import has_permission as has_permission_decorator  # ty: ignore


@has_permission_decorator
def decorated() -> None:
    pass


class _Gate:
    """メソッド形を保持する。"""

    def has_permission(self) -> bool:
        """認可を独自に判定する。"""
        return True


def has_permission() -> bool:
    return True
