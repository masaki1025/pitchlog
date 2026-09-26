"""裁定済み import 名を局所代入で shadow する条件 2 の負例。"""

from pitchlog.domaingen.core import GenerationError  # noqa: F401  # ty: ignore


def use(other):
    """裁定対象ではない値を同名の局所変数へ束縛する。"""
    GenerationError = other  # noqa: F811
    return GenerationError
