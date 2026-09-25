"""既知 import 名を callable 引数で shadow する条件 5 の負例。"""

from external.helpers import safe  # noqa: F401  # ty: ignore


def build(safe, tenant_id):  # noqa: F811
    """実行時に任意の callable となる同名引数を呼び出す。"""
    return safe(tenant_id)
