"""star import がモジュール callable を上書きし得る条件 5 の負例。"""

from external.first import safe  # ty: ignore
from external.second import *  # noqa: F403  # ty: ignore


def build(tenant_id):
    """起源が star import で不確定な裸名を呼び出す。"""
    return safe(tenant_id)  # noqa: F405
