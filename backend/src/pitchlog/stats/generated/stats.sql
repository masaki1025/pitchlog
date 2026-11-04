-- 自動生成 model=sha256:db0c52f2df92ddd76a9681a940e1bae83f29fb7ff7f9e988b23a76cd5b52b40d
-- relation/DDL/provider receiptは後段で正式接合。DB実在成功の主張ではない。
WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
selected AS (
 SELECT f.tenant_id, f.game_id, f.player_id, f.metric_id AS metric_id,
        f.amount AS amount, f.state, f.source_event_id, e.d2
 FROM public.stats_primitive_facts f
 JOIN public.stats_fact_versions v ON v.tenant_id=f.tenant_id AND v.game_id=f.game_id
    AND v.id=f.fact_version_id AND v.source_set_sha256=f.source_set_sha256
 JOIN public.games g ON g.tenant_id=f.tenant_id AND g.id=f.game_id
 JOIN public.operation_events e ON e.tenant_id=f.tenant_id AND e.game_id=f.game_id
    AND e.id=f.source_event_id AND e.generation=f.recording_generation AND e.d1=f.d1
 JOIN public.event_slots slot ON slot.tenant_id=e.tenant_id AND slot.game_id=e.game_id
    AND slot.generation=e.generation AND slot.d1=e.d1 AND slot.confirmed_version=f.slot_version
 JOIN public.play_rows p ON p.tenant_id=e.tenant_id AND p.game_id=e.game_id
    AND p.source_event_id=e.id AND p.version=f.play_row_version
 WHERE f.tenant_id=:tenant_id AND f.player_id=:player_id
    AND v.model_sha256=:model_sha256 AND v.is_current=true
    AND p.hidden_at IS NULL AND g.hidden_at IS NULL AND g.trashed_at IS NULL
    AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.is_tombstone=false
    AND v.completion_state='confirmed_ended'
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
