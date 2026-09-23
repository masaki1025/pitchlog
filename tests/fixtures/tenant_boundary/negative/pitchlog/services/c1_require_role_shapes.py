"""条件 1 の require_role と 3 つの構文形を表す負例。"""

from pitchlog.authz.rules import require_role as require_role_decorator  # ty: ignore


@require_role_decorator
def decorated() -> None:
    pass


class _Gate:
    """メソッド形を保持する。"""

    def require_role(self) -> bool:
        """認可を独自に判定する。"""
        return True


def require_role() -> bool:
    return True
