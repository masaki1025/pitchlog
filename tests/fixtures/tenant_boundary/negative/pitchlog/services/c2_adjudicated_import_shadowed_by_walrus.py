"""裁定済み import 名を walrus で shadow する条件 2 の負例。"""

from pitchlog.domaingen.core import GenerationError  # noqa: F401  # ty: ignore


def use(other):
    """裁定対象ではない値を同名の walrus target へ束縛する。"""
    return (GenerationError := other)  # noqa: F811, F841
