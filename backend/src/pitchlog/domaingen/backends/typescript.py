"""中間表現から TypeScript のラッパー専用 fragment を生成する。"""

from __future__ import annotations

import json

from pitchlog.domaingen.backends.common import (
    BackendInput,
    GeneratedArtifact,
    Language,
    artifact,
)


def generate(source: BackendInput) -> GeneratedArtifact:
    """一つの中間表現段から TypeScript fragment を生成する。

    Args:
        source: 計算宣言とコア由来の段別 hash。

    Returns:
        export を持たず、ラッパー印を要求する TypeScript fragment。
    """
    calculation_id = json.dumps(source.calculation_id, ensure_ascii=False)
    source_hash = json.dumps(source.source_hash)
    content = "\n".join(
        [
            "const wrapper = globalThis as "
            "{ __PITCHLOG_GENERATED_WRAPPER__?: boolean };",
            "if (wrapper.__PITCHLOG_GENERATED_WRAPPER__ !== true) {",
            '  throw new Error("生成物はラッパー経由でのみ使用できます");',
            "}",
            f"const PITCHLOG_SOURCE_HASH = {source_hash};",
            "function pitchlogGenerated(",
            "  context: Readonly<Record<string, unknown>>,",
            "): unknown {",
            f"  return {{ calculationId: {calculation_id}, context }};",
            "}",
            "",
        ]
    )
    return artifact(source, Language.TYPESCRIPT, content)
