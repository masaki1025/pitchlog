"""裁定済み import 名を except as で上書きする条件 2 の負例。"""

from pitchlog.domaingen.core import GenerationError  # noqa: F401  # ty: ignore


def use():
    """例外値を裁定済み import と同名へ束縛する。"""
    try:
        raise RuntimeError
    except RuntimeError as GenerationError:  # noqa: F811
        return GenerationError
