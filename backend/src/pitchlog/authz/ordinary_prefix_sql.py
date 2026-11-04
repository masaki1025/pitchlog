"""private prefixの限定read bridge。appの表直接権限は開けない。"""

from pitchlog.authz.sync_right_sql import _ASSERT, _COMMON

_READ_ASSERT = """
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_generation IS NULL OR p_generation<=0 THEN
 RAISE EXCEPTION 'ordinary prefix read rejected' USING ERRCODE='42501';
 END IF;
"""


def candidate_read_function_bodies():
    """readonly二関数と実writer限定lock一関数を別宣言で返す。"""
    result = {}
    for name, locked in (
        ("read_ordinary_checkpoint", False),
        ("lock_ordinary_checkpoint", True),
    ):
        arguments = (
            (_COMMON + ",p_generation bigint")
            if locked
            else ("p_tenant_id uuid,p_game_id uuid,p_generation bigint")
        )
        assertion = _ASSERT + _READ_ASSERT if locked else _READ_ASSERT
        suffix = " FOR UPDATE OF c" if locked else ""
        value = (
            "pg_catalog.to_jsonb(c) || "
            "pg_catalog.jsonb_build_object('last_play_row',s.expected_play_row)"
        )
        if not locked:
            value = f"pg_catalog.jsonb_build_object('kind','checkpoint','row',{value})"
        fallback = (
            ""
            if locked
            else """
 IF NOT FOUND THEN
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('kind','first-ball-save',
 'source_event_id',f.source_event_id::text,'saved_at',f.consumed_at)::text
 FROM sync_fence.first_ball_write_admissions f
 WHERE f.tenant_id=p_tenant_id AND f.game_id=p_game_id
 AND f.internal_generation=p_generation AND f.state='consumed'
 AND f.source_event_id IS NOT NULL AND f.consumed_at IS NOT NULL LIMIT 2;
 END IF;
"""
        )
        result[name] = f"""CREATE FUNCTION sync_right_api.{name}({arguments})
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $prefix$
BEGIN
{assertion}
 RETURN QUERY SELECT ({value})::text
 FROM sync_fence.ordinary_pitch_checkpoints c
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions s
 ON s.tenant_id=c.tenant_id AND s.game_id=c.game_id
 AND s.internal_generation=c.internal_generation AND s.checkpoint_id=c.id
 AND s.source_event_id=(c.content->'last_source'->>'id')::uuid
 AND s.state='consumed' AND s.consumed_at=c.saved_at
 AND s.checkpoint_revision+1=c.revision AND s.next_checkpoint_content=c.content
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation LIMIT 2{suffix};
{fallback}
END;
$prefix$;
"""
    result["read_ordinary_history_page"] = (
        """CREATE FUNCTION
sync_right_api.read_ordinary_history_page(p_tenant_id uuid,p_game_id uuid,
p_generation bigint,p_history_version bigint,p_checkpoint_id uuid,
p_checkpoint_revision bigint,p_upper_watermark bigint,p_after_d1 bigint,
p_after_d2 bigint,p_after_id uuid,p_page_size integer)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $prefix$
DECLARE item record; next_d1 bigint; seen_count integer:=0;
BEGIN
"""
        + _READ_ASSERT
        + """
 IF p_page_size IS NULL OR p_page_size<1 OR p_page_size>100
 OR p_history_version IS NULL OR p_history_version<=0 OR p_checkpoint_id IS NULL
 OR p_checkpoint_revision IS NULL OR p_checkpoint_revision<=0
 OR p_upper_watermark IS NULL OR p_upper_watermark<0
 OR p_after_d1 IS NULL OR p_after_d1<0 OR p_after_d1>p_upper_watermark
 OR p_after_d2 IS NULL OR p_after_d2<0 OR p_after_id IS NULL THEN
 RAISE EXCEPTION 'ordinary prefix page rejected' USING ERRCODE='42501';
 END IF;
 -- cursorを権限にせず、版/水位を実point原本へ束縛する。
 PERFORM 1 FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation AND c.id=p_checkpoint_id
 AND c.revision=p_checkpoint_revision AND c.history_version=p_history_version
 AND c.confirmed_watermark=p_upper_watermark AND c.applied_watermark=p_upper_watermark
 AND c.state='current' FOR SHARE;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'ordinary prefix page anchor rejected' USING ERRCODE='42501';
 END IF;
 IF (p_after_d1=0 AND (p_after_d2<>0 OR p_after_id<>
 '00000000-0000-0000-0000-000000000000'::uuid))
 OR (p_after_d1>0 AND NOT EXISTS(
 SELECT 1 FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=p_tenant_id AND h.game_id=p_game_id
 AND h.internal_generation=p_generation AND h.history_version=p_history_version
 AND (h.d1,h.d2,h.source_event_id)=(p_after_d1,p_after_d2,p_after_id))) THEN
 RAISE EXCEPTION 'ordinary prefix page cursor rejected' USING ERRCODE='42501';
 END IF;
 -- ordinary-only版のD1連続性を有限page内で照合。h自体の欠落も隠さない。
 next_d1:=p_after_d1;
 -- 有限pageを一度のqueryで取得。欠落をINNER JOINで隠さない。
 FOR item IN
 SELECT pg_catalog.to_jsonb(h) AS history,
 ev.rows AS events,ev.n AS event_count,pr.rows AS plays,pr.n AS play_count,
 ad.rows AS admissions,ad.n AS admission_count,fb.n AS first_count
 FROM (SELECT * FROM sync_fence.ordinary_pitch_history x
 WHERE x.tenant_id=p_tenant_id AND x.game_id=p_game_id
 AND x.internal_generation=p_generation AND x.history_version=p_history_version
 AND x.d1<=p_upper_watermark
 AND (x.d1,x.d2,x.source_event_id)>(p_after_d1,p_after_d2,p_after_id)
 ORDER BY x.d1,x.d2,x.source_event_id LIMIT p_page_size+1) h
 CROSS JOIN LATERAL (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(e)) rows,
 pg_catalog.count(*) n FROM public.operation_events e
 WHERE e.tenant_id=h.tenant_id AND e.game_id=h.game_id AND e.id=h.source_event_id
 AND e.generation=h.internal_generation AND e.d1=h.d1 AND e.d2=h.d2
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified) ev
 CROSS JOIN LATERAL (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(p)) rows,
 pg_catalog.count(*) n FROM public.play_rows p
 WHERE p.tenant_id=h.tenant_id AND p.game_id=h.game_id
 AND p.source_event_id=h.source_event_id AND p.import_batch_id IS NULL
 AND p.legacy_row_identifier IS NULL AND NOT p.migration_unverified) pr
 CROSS JOIN LATERAL (SELECT pg_catalog.jsonb_agg(a.expected_play_row) rows,
 pg_catalog.count(*) n FROM sync_fence.ordinary_pitch_write_admissions a
 WHERE a.tenant_id=h.tenant_id AND a.game_id=h.game_id
 AND a.internal_generation=h.internal_generation
 AND a.source_event_id=h.source_event_id
 AND a.source_d1=h.d1 AND a.source_d2=h.d2 AND a.state='consumed'
 AND a.history_entry=h.entry AND a.consumed_at IS NOT NULL) ad
 CROSS JOIN LATERAL (SELECT pg_catalog.count(*) n
 FROM sync_fence.first_ball_write_admissions f
 WHERE f.tenant_id=h.tenant_id AND f.game_id=h.game_id
 AND f.internal_generation=h.internal_generation
 AND f.source_event_id=h.source_event_id
 AND f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.play_row_id=(pr.rows->0->>'id')::uuid) fb
 ORDER BY h.d1,h.d2,h.source_event_id
 LOOP
 IF (item.history->>'d1')::bigint-next_d1<>1
 OR item.event_count<>1 OR item.play_count<>1
 OR NOT COALESCE((item.admission_count=1 AND item.first_count=0
 AND item.events->0->'payload'->>'formatVersion'='ordinary-pitch-play-v1'
 AND item.admissions->0=item.plays->0)
 OR (item.admission_count=0 AND item.first_count=1
 AND (item.history->>'d1')::bigint=1
 AND item.events->0->'payload'->>'formatVersion'='first-ball-play-v1'),false) THEN
 RAISE EXCEPTION 'ordinary prefix history origin rejected' USING ERRCODE='42501';
 END IF;
 next_d1:=(item.history->>'d1')::bigint;
 seen_count:=seen_count+1;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('history',item.history,
 'event',item.events->0,'play_row',item.plays->0,
 'expected_play_row',item.admissions->0)::text;
 END LOOP;
 IF seen_count<=p_page_size AND next_d1<>p_upper_watermark THEN
 RAISE EXCEPTION 'ordinary prefix history tail rejected' USING ERRCODE='42501';
 END IF;
END;
$prefix$;
"""
    )
    return result
