"""自己参照する再輸出別名を解決済みとして扱わせない負例。"""

Context = Context  # type: ignore  # noqa: F821


def run() -> object:
    """自己参照で起源不明の名前を呼び出す。"""
    return Context("other-tenant")
