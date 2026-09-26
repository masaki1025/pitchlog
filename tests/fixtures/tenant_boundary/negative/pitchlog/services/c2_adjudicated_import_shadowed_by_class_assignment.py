"""裁定済み import 名を class 代入で上書きする条件 2 の負例。"""

from pitchlog.domaingen.core import GenerationError  # noqa: F401  # ty: ignore


class Shadow:
    """裁定済みシンボルとは無関係な同名クラス属性を持つ。"""

    GenerationError = object()
