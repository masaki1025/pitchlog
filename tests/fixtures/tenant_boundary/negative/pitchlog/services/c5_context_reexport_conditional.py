"""条件分岐で複数起源を持つ再輸出名の負例。"""

flag = True

if flag:
    from external.first import Context  # ty: ignore
else:
    from external.second import Context  # ty: ignore


def run() -> object:
    """複数起源へ分岐する再輸出名を呼び出す。"""
    return Context("other-tenant")
