"""裁定済み import 名を module 代入で上書きする条件 2 の負例。"""

from pitchlog.domaingen.core import GenerationError  # noqa: F401  # ty: ignore

GenerationError = object()  # noqa: F811
