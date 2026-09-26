"""別関数の global writer で既知 import を上書きする負例。"""

from external.helpers import safe  # ty: ignore


def replace(factory):
    """モジュール束縛を任意の callable へ差し替える。"""
    global safe  # noqa: PLW0603
    safe = factory


def build(tenant_id):
    """差し替え可能なモジュール束縛を呼び出す。"""
    global safe
    return safe(tenant_id)
