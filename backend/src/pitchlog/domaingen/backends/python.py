"""中間表現から Python のラッパー専用 fragment を生成する。"""

from __future__ import annotations

from pitchlog.domaingen.backends.common import (
    BackendInput,
    GeneratedArtifact,
    Language,
    artifact,
)

_WRAPPER_MODULE_NAME = "__pitchlog_generated_wrapper__"


def generate(source: BackendInput) -> GeneratedArtifact:
    """一つの中間表現段から Python fragment を生成する。

    Args:
        source: 計算宣言とコア由来の段別 hash。

    Returns:
        直接 import を拒否する Python fragment。
    """
    lines = [
        f"if __name__ != {_WRAPPER_MODULE_NAME!r}:",
        "    raise ImportError('生成物はラッパー経由でのみ使用できます')",
        f"_PITCHLOG_SOURCE_HASH = {source.source_hash!r}",
        "",
    ]
    if source.target_class == "beta-7":
        lines.extend(
            [
                "def _pitchlog_generated(row, enum_display_map):",
                "    value = row['value']",
                "    return enum_display_map[value]",
            ]
        )
    else:
        lines.extend(
            [
                "def _pitchlog_generated(context):",
                "    return {",
                f"        'calculationId': {source.calculation_id!r},",
                "        'context': dict(context),",
                "    }",
            ]
        )
    return artifact(source, Language.PYTHON, "\n".join(lines) + "\n")
