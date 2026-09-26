"""裁定済み import 名を match capture で上書きする条件 2 の負例。"""

from pitchlog.domaingen.core import GenerationError  # noqa: F401  # ty: ignore


def use(value):
    """capture pattern を裁定済み import と同名へ束縛する。"""
    match value:
        case GenerationError:  # noqa: F811
            return GenerationError
