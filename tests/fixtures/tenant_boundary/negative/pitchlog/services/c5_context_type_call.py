"""type(context) による複製を表す負例。"""


def forge(context, other_tenant_id):
    return type(context)(other_tenant_id)
