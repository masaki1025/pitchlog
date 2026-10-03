"""再輸出の追跡深さ上限を超える負例。"""

from external.facade import Context as Origin  # ty: ignore

Alias0 = Origin
Alias1 = Alias0
Alias2 = Alias1
Alias3 = Alias2
Alias4 = Alias3
Alias5 = Alias4
Alias6 = Alias5
Alias7 = Alias6
Alias8 = Alias7
Alias9 = Alias8
Context = Alias9


def run() -> object:
    """深さ上限を超えた再輸出名を呼び出す。"""
    return Context("other-tenant")
