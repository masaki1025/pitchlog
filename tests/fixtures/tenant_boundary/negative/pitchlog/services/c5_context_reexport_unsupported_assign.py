"""未対応の静的代入で再輸出名を作る負例。"""

from external.factories import make_alias  # ty: ignore

Context = make_alias()


def run() -> object:
    """起源を静的に解決できない代入結果を呼び出す。"""
    return Context("other-tenant")
