"""循環する再輸出別名を解決済みとして扱わせない負例。"""

Context = OtherContext  # type: ignore  # noqa: F821
OtherContext = Context


def run() -> object:
    """循環再輸出で起源不明の名前を呼び出す。"""
    return Context("other-tenant")
