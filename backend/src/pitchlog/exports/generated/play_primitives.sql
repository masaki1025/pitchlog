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
    AND f.game_id=:game_id
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
