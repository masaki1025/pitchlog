"""欠落した pitchlog モジュールから再輸出する負例。"""

from pitchlog.missing_context import Context  # ty: ignore


def run() -> object:
    """内部の欠落モジュール由来の名前を呼び出す。"""
    return Context("other-tenant")
