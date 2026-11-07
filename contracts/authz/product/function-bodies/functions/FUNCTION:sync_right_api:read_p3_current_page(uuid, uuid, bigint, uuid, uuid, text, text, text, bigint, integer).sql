-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_p3_current_page(uuid, uuid, bigint, uuid, uuid, text, text, text, bigint, integer)

CREATE FUNCTION sync_right_api.read_p3_current_page(
p_tenant_id uuid,p_game_id uuid,p_generation bigint,p_capsule_id uuid,
p_stats_version_id uuid,p_checkpoint_digest text,p_head_digest text,
p_kind text,p_after_d1 bigint,p_page_size integer)
RETURNS TABLE(record_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_page_read$
#variable_conflict use_variable
DECLARE h jsonb; c jsonb; cp jsonb; v jsonb;
 rows jsonb; row_count bigint; last_d1 bigint; upper_d1 bigint;
BEGIN
 IF p_kind NOT IN ('capsule','suffix') OR p_after_d1 IS NULL
 OR p_after_d1<0 OR p_page_size NOT BETWEEN 1 AND 25
 OR p_capsule_id IS NULL OR p_stats_version_id IS NULL
 OR p_checkpoint_digest IS NULL OR p_head_digest IS NULL
 THEN RAISE EXCEPTION 'P3 page read rejected' USING ERRCODE='42501'; END IF;
 SELECT x.record_json::jsonb INTO STRICT h
 FROM sync_right_api.read_p3_current_header(
 p_tenant_id,p_game_id,p_generation) x;
 IF h->>'kind' IS DISTINCT FROM 'p3-paged-header'
 OR h->'capsule'->>'id' IS DISTINCT FROM p_capsule_id::text
 OR h->'stats'->>'id' IS DISTINCT FROM p_stats_version_id::text
 OR h->'checkpoint'->>'content_digest' IS DISTINCT FROM p_checkpoint_digest
 OR h->'head'->>'source_set_digest' IS DISTINCT FROM p_head_digest
 THEN RAISE EXCEPTION 'P3 page read rejected' USING ERRCODE='42501'; END IF;
 c:=h->'capsule';cp:=h->'checkpoint';v:=h->'stats';
 upper_d1:=CASE WHEN p_kind='capsule' THEN (c->>'watermark')::bigint
 ELSE (v->>'source_count')::bigint END;
 IF (p_kind='capsule' AND p_after_d1>=upper_d1)
 OR (p_kind='suffix' AND (p_after_d1<(c->>'watermark')::bigint
 OR p_after_d1>=upper_d1))
 THEN RAISE EXCEPTION 'P3 page read rejected' USING ERRCODE='42501'; END IF;
 IF p_kind='capsule' THEN
 SELECT pg_catalog.count(*),COALESCE(pg_catalog.jsonb_agg(x.member ORDER BY x.d1),
 '[]'::jsonb),MAX(x.d1) INTO row_count,rows,last_d1 FROM (
 SELECT i.d1,pg_catalog.jsonb_build_object(
 'item',pg_catalog.to_jsonb(i),'original_event',pg_catalog.to_jsonb(e),
 'original_ledger',pg_catalog.to_jsonb(ol),
 'original_history',pg_catalog.to_jsonb(hi),
 'original_play_row',pg_catalog.to_jsonb(op),
 'original_play_runners',original_runners.rows,
 'effective_play_row',pg_catalog.to_jsonb(ep),
 'effective_play_runners',effective_runners.rows,
 'stats_source',pg_catalog.to_jsonb(s)) member
 FROM sync_fence.p3_projection_capsule_items i
 LEFT JOIN public.operation_events e ON
 (e.tenant_id,e.id)=(i.tenant_id,i.original_event_id)
 LEFT JOIN public.idempotency_ledger ol ON
 (ol.tenant_id,ol.d5)=(e.tenant_id,e.d5)
 LEFT JOIN sync_fence.ordinary_pitch_history hi ON
 (hi.tenant_id,hi.game_id,hi.internal_generation,hi.source_event_id,hi.d1)=
 (i.tenant_id,i.game_id,i.internal_generation,i.original_event_id,i.d1)
 AND hi.history_version=(cp->>'history_version')::bigint
 LEFT JOIN public.play_rows op ON
 (op.tenant_id,op.id)=(i.tenant_id,i.original_play_row_id)
 LEFT JOIN public.play_rows ep ON
 (ep.tenant_id,ep.id)=(i.tenant_id,i.effective_play_row_id)
 LEFT JOIN sync_fence.stats_primitive_sources s ON
 (s.tenant_id,s.game_id,s.fact_version_id,s.d1)=
 (i.tenant_id,i.game_id,(v->>'id')::uuid,i.d1)
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(r) ORDER BY r.base),'[]'::jsonb) rows
 FROM public.play_runners r WHERE r.tenant_id=i.tenant_id
 AND r.play_id=i.original_play_row_id) original_runners
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(r) ORDER BY r.base),'[]'::jsonb) rows
 FROM public.play_runners r WHERE r.tenant_id=i.tenant_id
 AND r.play_id=i.effective_play_row_id) effective_runners
 WHERE (i.tenant_id,i.game_id,i.internal_generation,i.capsule_id)=
 (p_tenant_id,p_game_id,p_generation,p_capsule_id)
 AND i.d1>p_after_d1 ORDER BY i.d1 LIMIT p_page_size
 ) x;
 ELSE
 SELECT pg_catalog.count(*),COALESCE(pg_catalog.jsonb_agg(x.member ORDER BY x.d1),
 '[]'::jsonb),MAX(x.d1) INTO row_count,rows,last_d1 FROM (
 SELECT slot.d1,pg_catalog.jsonb_build_object(
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'history',pg_catalog.to_jsonb(hi),'play_row',pg_catalog.to_jsonb(p),
 'play_runners',r.rows,'stats_source',pg_catalog.to_jsonb(s)) member
 FROM public.event_slots slot
 JOIN public.operation_events e ON
 (e.tenant_id,e.game_id,e.generation,e.d1)=
 (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 AND e.event_kind='play_input' AND e.ledger_kind='accepted'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 JOIN public.idempotency_ledger l ON
 (l.tenant_id,l.d5)=(e.tenant_id,e.d5)
 AND l.kind='accepted' AND l.retired_at IS NULL
 JOIN sync_fence.ordinary_pitch_history hi ON
 (hi.tenant_id,hi.game_id,hi.internal_generation,hi.d1,hi.source_event_id)=
 (e.tenant_id,e.game_id,e.generation,e.d1,e.id)
 AND hi.history_version=(cp->>'history_version')::bigint
 JOIN public.play_rows p ON
 (p.tenant_id,p.game_id,p.source_event_id)=(e.tenant_id,e.game_id,e.id)
 AND p.hidden_at IS NULL
 LEFT JOIN sync_fence.stats_primitive_sources s ON
 (s.tenant_id,s.game_id,s.fact_version_id,s.d1)=
 (e.tenant_id,e.game_id,(v->>'id')::uuid,e.d1)
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(pr) ORDER BY pr.base),'[]'::jsonb) rows
 FROM public.play_runners pr WHERE pr.tenant_id=p.tenant_id
 AND pr.play_id=p.id) r
 WHERE (slot.tenant_id,slot.game_id,slot.generation)=
 (p_tenant_id,p_game_id,p_generation)
 AND slot.d1>(c->>'watermark')::bigint
 AND slot.d1>p_after_d1 AND slot.d1<=upper_d1
 AND slot.confirmed_version=1 ORDER BY slot.d1 LIMIT p_page_size
 ) x;
 END IF;
 IF row_count<1 OR last_d1 IS DISTINCT FROM p_after_d1+row_count
 THEN RAISE EXCEPTION 'P3 page read rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'kind','p3-paged-page','page_kind',p_kind,
 'tenant_id',p_tenant_id,'game_id',p_game_id,
 'internal_generation',p_generation,'capsule_id',p_capsule_id,
 'stats_version_id',p_stats_version_id,'checkpoint_digest',p_checkpoint_digest,
 'head_digest',p_head_digest,'after_d1',p_after_d1,
 'last_d1',last_d1,'upper_d1',upper_d1,'items',rows,
 'next_after_d1',CASE WHEN last_d1<upper_d1 THEN last_d1 ELSE NULL END)::text;
END;
$p3_page_read$;
ALTER FUNCTION sync_right_api.read_p3_current_page(
 uuid,uuid,bigint,uuid,uuid,text,text,text,bigint,integer)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_p3_current_page(
 uuid,uuid,bigint,uuid,uuid,text,text,text,bigint,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.read_p3_current_page(
 uuid,uuid,bigint,uuid,uuid,text,text,text,bigint,integer) TO pitchlog_app;
