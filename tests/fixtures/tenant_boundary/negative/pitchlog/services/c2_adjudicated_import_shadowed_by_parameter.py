"""裁定済み import 名を引数で shadow する条件 2 の負例。"""

from pitchlog.domaingen.core import GenerationError  # noqa: F401  # ty: ignore


def use(GenerationError):  # noqa: F811
    """import と無関係な同名引数を返す。"""
    return GenerationError
