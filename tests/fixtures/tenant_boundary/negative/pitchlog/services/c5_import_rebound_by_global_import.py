"""別関数の global import writer で既知 import を上書きする負例。"""

from external.first import safe  # ty: ignore


def replace():
    """モジュール束縛を別の import へ差し替える。"""
    global safe  # noqa: PLW0603
    from external.second import safe  # noqa: F811  # ty: ignore


def build(tenant_id):
    """差し替え可能なモジュール束縛を呼び出す。"""
    return safe(tenant_id)
