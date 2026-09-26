"""star import で裁定済み import 名を上書きし得る条件 2 の負例。"""

from external.overrides import *  # noqa: F403  # ty: ignore
from pitchlog.domaingen.core import GenerationError  # ty: ignore

observed = GenerationError
