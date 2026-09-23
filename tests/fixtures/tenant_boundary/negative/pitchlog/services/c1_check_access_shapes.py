"""条件 1 の check_*_access と 3 つの構文形を表す負例。"""

from pitchlog.authz.rules import check_team_access as check_access_decorator  # ty: ignore


@check_access_decorator
def decorated() -> None:
    pass


class _Gate:
    """メソッド形を保持する。"""

    def check_team_access(self) -> bool:
        """認可を独自に判定する。"""
        return True


def check_team_access() -> bool:
    return True
