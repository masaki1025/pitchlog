"""発行証跡の導出関数を多段の別名で参照する負例。"""

import pitchlog.repositories.context as context_module  # ty: ignore

module_alias = context_module
derive_alias = module_alias._tenant_context_proof
indirect_factory = derive_alias


def forge_proof(tenant_id):
    """モジュール横断の多段別名から発行証跡を作る。"""
    return indirect_factory(tenant_id)
