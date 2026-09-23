"""条件 1 の assert_*_owner と 3 つの構文形を表す負例。"""

from pitchlog.authz.rules import assert_team_owner as assert_owner_decorator  # ty: ignore


@assert_owner_decorator
def decorated() -> None:
    pass


class _Gate:
    """メソッド形を保持する。"""

    def assert_team_owner(self) -> bool:
        """認可を独自に判定する。"""
        return True


def assert_team_owner() -> bool:
    return True
