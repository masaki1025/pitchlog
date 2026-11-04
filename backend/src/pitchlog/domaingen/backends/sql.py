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
    from pitchlog.domaingen.pregen_checks import validate_primitive_sql_binding

    binding = program["sql"]
    try:
        validate_primitive_sql_binding(binding)
    except ValueError as error:
        raise BackendGenerationError(str(error)) from error
    names = [m["id"] for m in program["metrics"]]
    values = ", ".join("('" + name + "')" for name in names)
    header = f"-- 自動生成 model={source_hash}\n-- 正式operation/receiptはroot binding、実DB実行前は成功を主張しない。\n"  # noqa: E501 — 生成targetのliteral

    def canonical_selection(game_scope):
        """実slot/原本/D5台帳から独立したSと未解決行を一度だけ生成する。"""
        return f"""canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM {binding["games"]} g
 WHERE g.tenant_id=:tenant_id AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   {game_scope}
), canonical_raw AS (
 SELECT slot.tenant_id,slot.game_id,slot.generation AS recording_generation,
   slot.d1,e.d2,slot.confirmed_version AS slot_version,e.id AS base_event_id,
   CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   current_event.payload->>'formatVersion' AS native_variant,
   current_event.payload#>>'{{calculation,artifactSha256}}' AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR p.hidden_at IS NOT NULL THEN 'source_unavailable'
     ELSE 'included' END AS preliminary_state
 FROM {binding["slots"]} slot JOIN canonical_scope g
   ON g.tenant_id=slot.tenant_id AND g.game_id=slot.game_id
 JOIN {binding["generations"]} gen ON gen.tenant_id=slot.tenant_id
   AND gen.game_id=slot.game_id AND gen.generation=slot.generation
 LEFT JOIN {binding["events"]} e ON e.tenant_id=slot.tenant_id AND e.game_id=slot.game_id
   AND e.generation=slot.generation AND e.d1=slot.d1
   AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.ledger_kind='accepted'
 LEFT JOIN {binding["events"]} change ON change.tenant_id=slot.tenant_id AND change.game_id=slot.game_id
   AND change.target_generation=slot.generation AND change.target_d1=slot.d1
   AND change.expected_version=slot.confirmed_version-1 AND slot.confirmed_version>1
   AND change.ledger_kind='accepted' AND change.replaced_at IS NULL AND change.retired_at IS NULL
 LEFT JOIN {binding["events"]} current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END
 LEFT JOIN {binding["ledger"]} ledger ON ledger.tenant_id=current_event.tenant_id
   AND ledger.d5=current_event.d5
 LEFT JOIN {binding["plays"]} p ON p.tenant_id=current_event.tenant_id
   AND p.game_id=current_event.game_id AND p.source_event_id=current_event.id
), canonical_s AS (
 SELECT *,CASE WHEN match_count<>1 THEN 'source_unavailable'
               ELSE preliminary_state END AS source_state FROM canonical_raw
), canonical_health AS (
 SELECT g.tenant_id,g.game_id,1::bigint AS game_count,
   COUNT(*) FILTER (WHERE c.source_state='included') AS canonical_source_count,
   COUNT(*) FILTER (WHERE c.source_state='source_unavailable') AS unavailable_count,
   encode(sha256(convert_to(COALESCE(string_agg(
     jsonb_build_array(c.tenant_id,c.game_id,c.recording_generation,c.d1,c.d2,c.source_event_id,
       c.slot_version,c.play_row_id,c.play_row_version,c.source_fingerprint)::text,
     E'\\n' ORDER BY c.tenant_id,c.game_id,c.d2,c.source_event_id)
     FILTER (WHERE c.source_state='included'),'accepted-play-slot-v1:empty'),'UTF8')),'hex')
     AS canonical_source_set_sha256
 FROM canonical_scope g LEFT JOIN canonical_s c
   ON c.tenant_id=g.tenant_id AND c.game_id=g.game_id
 GROUP BY g.tenant_id,g.game_id
)
"""  # noqa: E501 — 生成targetのliteral

    unhealthy = """EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL)"""

    def selection(scope):
        """版/Sと生存source集合を一度だけ宣言する。"""
        game_scope = (
            "AND g.id=:game_id"
            if "v.game_id=:game_id" in scope
            else (
                "AND g.status='finished' AND g.scheduled_at>=:year_start_jst "
                "AND g.scheduled_at<:year_end_jst AND g.game_type_key=ANY(:raw_game_type_keys)"  # noqa: E501 — 生成targetのliteral
            )
        )
        return f"""WITH requested_metrics(metric_id) AS (VALUES {values}),
{canonical_selection(game_scope)}, version_scope AS (
 SELECT v.* FROM {binding["versions"]} v
 JOIN {binding["games"]} g ON g.tenant_id=v.tenant_id AND g.id=v.game_id
 JOIN canonical_scope visible_game ON visible_game.tenant_id=v.tenant_id
   AND visible_game.game_id=v.game_id
 WHERE v.tenant_id=:tenant_id AND v.model_sha256=:model_sha256
   AND v.is_current=true AND v.invalidated_at IS NULL
   AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   {scope}
), source_members AS (
 SELECT s.* FROM {binding["sources"]} s
 JOIN version_scope v ON v.tenant_id=s.tenant_id AND v.game_id=s.game_id
   AND v.id=s.fact_version_id
 JOIN canonical_s c ON c.tenant_id=s.tenant_id AND c.game_id=s.game_id
   AND c.source_event_id=s.source_event_id AND c.recording_generation=s.recording_generation
   AND c.d1=s.d1 AND c.d2=s.d2 AND c.slot_version=s.slot_version
   AND c.play_row_id=s.play_row_id AND c.play_row_version=s.play_row_version
   AND c.source_fingerprint=s.source_fingerprint AND c.artifact_sha256=s.artifact_sha256
   AND c.source_state='included'
), scope_health AS (
 SELECT v.tenant_id,v.game_id,v.id,v.source_count,
   COUNT(s.source_event_id) AS actual_source_count
 FROM version_scope v LEFT JOIN source_members s ON s.tenant_id=v.tenant_id
   AND s.game_id=v.game_id AND s.fact_version_id=v.id
 GROUP BY v.tenant_id,v.game_id,v.id,v.source_count
), binding_health AS (
 SELECT h.*,
   (ch.game_id IS NULL OR h.source_count<>h.actual_source_count
    OR ch.unavailable_count>0 OR ch.canonical_source_count<>h.actual_source_count
    OR v.source_set_sha256<>ch.canonical_source_set_sha256) AS invalid
 FROM scope_health h JOIN version_scope v
   ON v.tenant_id=h.tenant_id AND v.game_id=h.game_id AND v.id=h.id
 LEFT JOIN canonical_health ch ON ch.tenant_id=h.tenant_id AND ch.game_id=h.game_id
), selected AS (
 SELECT s.tenant_id,s.game_id,CAST(:player_id AS uuid) AS player_id,m.metric_id,
   CASE WHEN {unhealthy}
     OR NOT (m.metric_id=ANY(s.computed_metric_keys))
     OR COUNT(*) FILTER (WHERE f.source_event_id IS NOT NULL AND (f.state<>'available' OR f.{binding["amountColumn"]} IS NULL))>0
     THEN NULL ELSE COALESCE(SUM(f.{binding["amountColumn"]}),0) END AS amount,
   CASE WHEN {unhealthy}
     OR NOT (m.metric_id=ANY(s.computed_metric_keys))
     OR COUNT(*) FILTER (WHERE f.source_event_id IS NOT NULL AND (f.state<>'available' OR f.{binding["amountColumn"]} IS NULL))>0
     THEN 'source_unavailable' ELSE 'available' END AS state,
   s.source_event_id,s.d2
 FROM source_members s CROSS JOIN requested_metrics m
 LEFT JOIN {binding["facts"]} f ON f.tenant_id=s.tenant_id AND f.game_id=s.game_id
   AND f.fact_version_id=s.fact_version_id AND f.source_event_id=s.source_event_id
   AND f.{binding["metricColumn"]}=m.metric_id AND f.player_id=:player_id
 GROUP BY s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id,s.d2,
   s.computed_metric_keys,m.metric_id
)
"""  # noqa: E501 — 生成targetのliteral

    current_scope = """AND v.game_id=:game_id AND v.id=:fact_version_id
   AND v.source_set_sha256=:source_set_sha256 AND v.revision=:revision"""
    official_scope = """AND v.completion_state='confirmed_ended'
   AND v.completion_receipt_id IS NOT NULL AND v.public_pointer_receipt_id IS NOT NULL
   AND g.scheduled_at>=:year_start_jst AND g.scheduled_at<:year_end_jst
   AND g.game_type_key=ANY(:raw_game_type_keys)"""

    def totals(common, require_version=False):
        """同じsource集合の欠測・空0とSUMを生成する。"""
        return (
            common
            + f""", aggregate_facts AS (
 SELECT player_id, metric_id,
   CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL)>0 THEN NULL
        ELSE SUM(amount) END AS value,
   BOOL_AND(state='available' AND amount IS NOT NULL) AS complete
 FROM selected GROUP BY player_id, metric_id
)
SELECT m.metric_id,
 CASE WHEN {"NOT EXISTS (SELECT 1 FROM version_scope) OR " if require_version else ""}{unhealthy}
     OR EXISTS (SELECT 1 FROM version_scope coverage
                WHERE NOT (m.metric_id=ANY(coverage.computed_metric_keys)))
     OR a.complete=false THEN 'source_unavailable' ELSE 'available' END AS state,
 CASE WHEN {"NOT EXISTS (SELECT 1 FROM version_scope) OR " if require_version else ""}{unhealthy}
     OR EXISTS (SELECT 1 FROM version_scope coverage
                WHERE NOT (m.metric_id=ANY(coverage.computed_metric_keys)))
     OR a.complete=false THEN NULL ELSE COALESCE(a.value,0) END AS value
FROM requested_metrics m LEFT JOIN aggregate_facts a ON a.metric_id=m.metric_id
ORDER BY m.metric_id;
"""  # noqa: E501 — 生成targetのliteral
        )

    current = selection(current_scope)
    window = (
        current
        + """, accumulated AS (
 SELECT *,
   CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL) OVER w>0
        THEN NULL ELSE SUM(amount) OVER w END AS value,
   CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL) OVER w>0
        THEN 'source_unavailable' ELSE 'available' END AS result_state
 FROM selected
 WINDOW w AS (PARTITION BY tenant_id,game_id,player_id,metric_id
   ORDER BY d2,source_event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT metric_id,result_state AS state,value,d2,source_event_id FROM accumulated
WHERE (:after_d2 IS NULL OR
 (d2,source_event_id,metric_id)>(:after_d2,:after_source_event_id,:after_metric_id))
ORDER BY d2,source_event_id,metric_id LIMIT :page_size;
"""
    )
    count = (
        current
        + """SELECT v.id AS fact_version_id,v.revision,v.source_set_sha256,v.model_sha256,
 v.source_count,(SELECT COUNT(*) FROM selected) AS row_count,
 pg_current_snapshot()::text AS transaction_id,v.completion_state,
 h.actual_source_count,ch.canonical_source_count,ch.unavailable_count,
 ch.canonical_source_set_sha256
FROM version_scope v JOIN scope_health h
 ON h.tenant_id=v.tenant_id AND h.game_id=v.game_id AND h.id=v.id
JOIN canonical_health ch ON ch.tenant_id=v.tenant_id AND ch.game_id=v.game_id;
"""  # noqa: E501 — 生成targetのliteral
    )
    # 区切りは固定。rootが正式関数へ同じ生成sectionを組み込み、別の式を書かない。
    return {
        "grouped": header + totals(selection(official_scope)),
        "window": header
        + "-- pitchlog-query: window\n"
        + window
        + "-- pitchlog-query: count\n"
        + count
        + "-- pitchlog-query: current_totals\n"
        + totals(current, True)
        + "-- pitchlog-query: canonical_members\nWITH "
        + canonical_selection("AND g.id=:game_id")
        + "SELECT * FROM canonical_s\n"
        + "WHERE (:canonical_after_generation IS NULL OR "
        + "(recording_generation,d1)>(:canonical_after_generation,:canonical_after_d1))\n"  # noqa: E501 — 生成targetのliteral
        + "ORDER BY recording_generation,d1 LIMIT :canonical_page_size;\n"
        + "-- pitchlog-query: canonical_health\nWITH "
        + canonical_selection("AND g.id=:game_id")
        + "SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,"  # noqa: E501 — 固定SQL literal
        + "COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,"  # noqa: E501 — 固定SQL literal
        + "encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) "
        + "AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) "
        + "LEFT JOIN canonical_health ch ON true;\n",
    }
