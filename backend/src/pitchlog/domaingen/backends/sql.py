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
    if "typedProgram" in source.declaration:
        from pitchlog.domaingen.pregen_checks import validate_typed_program

        program = source.declaration["typedProgram"]
        if not isinstance(program, dict):
            raise ValueError("typedProgramの閉型が不正です")
        validate_typed_program(program)
        if (source.target_class, source.stage) != ("beta-1-5", "sql"):
            raise BackendGenerationError(
                f"typed SQLの対象外段: {source.target_class}/{source.stage}"
            )
        return artifact(
            source,
            Language.SQL,
            generate_typed_queries(program, source.source_hash)["grouped"],
        )
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


def generate_typed_queries(program, source_hash: str) -> dict[str, str]:
    """受理済みT5寄与factだけをDB集計するSQLを生成する。

    Args:
        program: 共通primitiveとDBの閉binding宣言。
        source_hash: 唯一modelのhash。

    Returns:
        版付き事実のGROUP BYとwindowのSQL。
    """
    import re

    binding = program["sql"]
    if set(binding) != {
        "facts",
        "versions",
        "games",
        "events",
        "plays",
        "amountColumn",
        "metricColumn",
        "slots",
    }:
        raise BackendGenerationError("SQL bindingの閉キー違反")
    for table in (
        binding[k] for k in ("facts", "versions", "games", "events", "plays", "slots")
    ):
        if not isinstance(table, str) or not re.fullmatch(
            r"public\.[a-z][a-z0-9_]*", table
        ):
            raise BackendGenerationError("SQL relation名が不正")
    for column in (binding["amountColumn"], binding["metricColumn"]):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", column):
            raise BackendGenerationError("SQL column bindingが不正")
    names = [m["id"] for m in program["metrics"]]
    values = ", ".join("('" + name + "')" for name in names)
    header = f"-- 自動生成 model={source_hash}\n-- relation/DDL/provider receiptは後段で正式接合。DB実在成功の主張ではない。\n"  # noqa: E501 — 生成targetのliteral
    common = f"""WITH requested_metrics(metric_id) AS (VALUES {values}),
selected AS (
 SELECT f.tenant_id, f.game_id, f.player_id, f.{binding["metricColumn"]} AS metric_id,
        f.{binding["amountColumn"]} AS amount, f.state, f.source_event_id, e.d2
 FROM {binding["facts"]} f
 JOIN {binding["versions"]} v ON v.tenant_id=f.tenant_id AND v.game_id=f.game_id
    AND v.id=f.fact_version_id AND v.source_set_sha256=f.source_set_sha256
 JOIN {binding["games"]} g ON g.tenant_id=f.tenant_id AND g.id=f.game_id
 JOIN {binding["events"]} e ON e.tenant_id=f.tenant_id AND e.game_id=f.game_id
    AND e.id=f.source_event_id AND e.generation=f.recording_generation AND e.d1=f.d1
 JOIN {binding["slots"]} slot ON slot.tenant_id=e.tenant_id AND slot.game_id=e.game_id
    AND slot.generation=e.generation AND slot.d1=e.d1 AND slot.confirmed_version=f.slot_version
 JOIN {binding["plays"]} p ON p.tenant_id=e.tenant_id AND p.game_id=e.game_id
    AND p.source_event_id=e.id AND p.version=f.play_row_version
 WHERE f.tenant_id=:tenant_id AND f.player_id=:player_id
    AND v.model_sha256=:model_sha256 AND v.is_current=true
    AND p.hidden_at IS NULL AND g.hidden_at IS NULL AND g.trashed_at IS NULL
    AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.is_tombstone=false
"""  # noqa: E501 — 生成targetのliteral
    grouped = (
        common
        + """    AND v.completion_state='confirmed_ended'
    AND v.completion_receipt_id IS NOT NULL AND v.public_pointer_receipt_id IS NOT NULL
    AND g.scheduled_at>=:year_start_jst AND g.scheduled_at<:year_end_jst
    AND g.game_type_key=ANY(:raw_game_type_keys)
), aggregate_facts AS (
 SELECT player_id, metric_id,
    CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL)>0 THEN NULL ELSE SUM(amount) END AS value,
    CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL)>0 THEN 'source_unavailable' ELSE 'available' END AS state
 FROM selected GROUP BY player_id, metric_id
)
SELECT m.metric_id,
 CASE WHEN EXISTS (
    SELECT 1 FROM public.stats_fact_versions coverage
    JOIN public.games scope_game ON scope_game.tenant_id=coverage.tenant_id AND scope_game.id=coverage.game_id
    WHERE coverage.tenant_id=:tenant_id AND coverage.is_current=true
      AND coverage.completion_state='confirmed_ended'
      AND coverage.model_sha256=:model_sha256
      AND scope_game.hidden_at IS NULL AND scope_game.trashed_at IS NULL
      AND scope_game.scheduled_at>=:year_start_jst AND scope_game.scheduled_at<:year_end_jst
      AND scope_game.game_type_key=ANY(:raw_game_type_keys)
      AND NOT (m.metric_id=ANY(coverage.computed_metric_keys))
 ) THEN 'source_unavailable'
 WHEN NOT (m.metric_id=ANY(:computed_metric_keys)) THEN 'source_unavailable'
      ELSE COALESCE(a.state,'available') END AS state,
 CASE WHEN EXISTS (
    SELECT 1 FROM public.stats_fact_versions coverage
    JOIN public.games scope_game ON scope_game.tenant_id=coverage.tenant_id AND scope_game.id=coverage.game_id
    WHERE coverage.tenant_id=:tenant_id AND coverage.is_current=true
      AND coverage.completion_state='confirmed_ended'
      AND coverage.model_sha256=:model_sha256
      AND scope_game.hidden_at IS NULL AND scope_game.trashed_at IS NULL
      AND scope_game.scheduled_at>=:year_start_jst AND scope_game.scheduled_at<:year_end_jst
      AND scope_game.game_type_key=ANY(:raw_game_type_keys)
      AND NOT (m.metric_id=ANY(coverage.computed_metric_keys))
 ) THEN NULL
 WHEN NOT (m.metric_id=ANY(:computed_metric_keys)) THEN NULL
      WHEN a.state='source_unavailable' THEN NULL ELSE COALESCE(a.value,0) END AS value
FROM requested_metrics m LEFT JOIN aggregate_facts a ON a.metric_id=m.metric_id
ORDER BY m.metric_id;
"""  # noqa: E501 — 生成targetのliteral
    )
    window = (
        common
        + """    AND f.game_id=:game_id
), accumulated AS (
 SELECT *,
    CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL) OVER w > 0 THEN NULL
         ELSE SUM(amount) OVER w END AS value,
    CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL) OVER w > 0 THEN 'source_unavailable' ELSE 'available' END AS result_state
 FROM selected
 WINDOW w AS (PARTITION BY tenant_id,game_id,player_id,metric_id
              ORDER BY d2,source_event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT metric_id,result_state AS state,value,d2,source_event_id
FROM accumulated
WHERE (:after_d2 IS NULL OR
       (d2,source_event_id,metric_id)>(:after_d2,:after_source_event_id,:after_metric_id))
ORDER BY d2,source_event_id,metric_id LIMIT :page_size;
"""  # noqa: E501 — 生成targetのliteral
    )
    return {
        "grouped": header
        + grouped.replace(
            "public.stats_fact_versions coverage", binding["versions"] + " coverage"
        ).replace("public.games scope_game", binding["games"] + " scope_game"),
        "window": header + window,
    }
