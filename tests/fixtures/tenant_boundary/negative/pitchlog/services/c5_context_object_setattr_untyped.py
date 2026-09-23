"""型解決なしの object.__setattr__ 改竄を表す負例。"""


def forge(context, other_tenant_id):
    object.__setattr__(context, "tenant_id", other_tenant_id)
    return context
