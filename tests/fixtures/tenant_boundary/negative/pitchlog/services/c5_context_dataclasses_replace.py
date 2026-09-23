"""dataclasses.replace による複製を表す負例。"""

import dataclasses


def forge(context, other_tenant_id):
    return dataclasses.replace(context, tenant_id=other_tenant_id)
