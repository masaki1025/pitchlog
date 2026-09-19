"""中間表現から SQL のラッパー専用 expression fragment を生成する。"""

from __future__ import annotations

from pitchlog.domaingen.backends.common import (
    BackendGenerationError,
    BackendInput,
    GeneratedArtifact,
    Language,
    artifact,
)


def generate(source: BackendInput) -> GeneratedArtifact:
    """一つの中間表現段から SQL expression を生成する。

    Args:
        source: 計算宣言とコア由来の段別 hash。

    Returns:
        ラッパーが埋め込む SQL expression fragment。

    Raises:
        BackendGenerationError: SQL 対象でない区分を渡した場合。
    """
    header = f"/* pitchlog-wrapper-only source-hash={source.source_hash} */"
    if source.target_class == "beta-1-5":
        expression = "COALESCE(SUM(:pitchlog_value), 0)"
    elif source.target_class == "beta-7":
        expression = (
            "CASE WHEN :pitchlog_row_value IS NULL "
            "THEN NULL ELSE :pitchlog_row_value END"
        )
    else:
        raise BackendGenerationError(
            f"SQL を生成しない target class: {source.target_class}"
        )
    return artifact(source, Language.SQL, f"{header}\n{expression}\n")
