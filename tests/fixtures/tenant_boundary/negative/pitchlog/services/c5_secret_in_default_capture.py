"""許可シンボルのデフォルト引数で発行証跡の秘密を捕捉する負例。"""

import pitchlog.repositories.context as context_module  # ty: ignore


def _tenant_context_proof(value=context_module._TENANT_CONTEXT_SECRET):
    """関数本体へ入る前の外側スコープから秘密を捕捉する。"""
    return value
