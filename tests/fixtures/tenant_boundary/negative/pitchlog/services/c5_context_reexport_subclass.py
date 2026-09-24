"""façade の別名 Context を通じてサブクラス化する負例。"""

from pitchlog.services.c5_context_in_class_base import (
    TenantContext as Context,
)


class ForgedContext(Context):
    """再輸出された TenantContext を不正に継承する。"""
