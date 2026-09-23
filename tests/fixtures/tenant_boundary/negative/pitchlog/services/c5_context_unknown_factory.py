"""由来を解決できない callable から文脈を作る負例。"""


def forge_context(factory, tenant_id):
    """未解決 callable を TenantContext の生成器として呼ぶ。"""
    return factory(tenant_id)
