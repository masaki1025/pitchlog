"""条件 1 の can_* と 3 つの構文形を表す負例。"""

from pitchlog.authz.rules import can_manage_team as can_manage_decorator  # ty: ignore


@can_manage_decorator
def decorated() -> None:
    pass


class _Gate:
    """メソッド形を保持する。"""

    def can_manage_team(self) -> bool:
        """認可を独自に判定する。"""
        return True


def can_manage_team() -> bool:
    return True
