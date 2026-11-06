-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_nonplay_active_history(uuid, uuid, bigint, uuid, bigint, bigint, bigint, bigint, bigint, bigint, uuid, integer)

CREATE FUNCTION sync_right_api.read_nonplay_active_history(
 p_tenant_id uuid,p_game_id uuid,p_generation bigint,p_checkpoint_id uuid,
 p_revision bigint,p_epoch bigint,p_d3 bigint,p_logical_version bigint,
 p_after_order bigint,p_after_d1 bigint,p_after_id uuid,p_page_size integer)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $dispatch$
BEGIN
 IF EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_checkpoints c WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id AND c.internal_generation=p_generation AND c.id=p_checkpoint_id AND c.content->>'version'='3') THEN
DECLARE cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; x record; j jsonb;
 items jsonb:='[]'::jsonb; total bigint; chain jsonb; physical_xmin xid;
BEGIN

 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_generation IS NULL OR p_generation<=0 THEN
 RAISE EXCEPTION 'ordinary prefix read rejected' USING ERRCODE='42501';
 END IF;

 IF p_checkpoint_id IS NULL OR p_revision IS NULL OR p_epoch IS NULL OR p_d3 IS NULL
 OR p_logical_version IS NULL OR p_page_size IS NULL OR p_after_order IS NULL
 OR p_after_d1 IS NULL OR p_revision<1 OR p_epoch<1 OR p_d3<1
 OR p_logical_version<1 OR p_page_size NOT BETWEEN 1 AND 100
 OR p_after_order<0 OR p_after_d1<0 OR p_after_id IS NULL
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.recording_generations g ON (g.tenant_id,g.game_id,g.generation)=
 (c.tenant_id,c.game_id,c.internal_generation)
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation AND c.id=p_checkpoint_id
 AND c.revision=p_revision AND c.history_version=p_epoch AND c.state='current'
 AND c.confirmed_watermark=p_d3 AND c.applied_watermark=p_d3
 AND g.recovery_generation=c.recovery_generation
 AND g.confirmed_watermark=p_d3 AND g.applied_prefix=p_d3 AND g.kind='normal'
 AND g.revoked_at IS NULL AND g.retired_at IS NULL AND g.import_batch_id IS NULL
 AND c.content->>'version'='3'
 AND c.content->>'id'=c.id::text AND c.content->>'revision'=p_revision::text
 AND c.content->>'content_digest'=c.content_digest
 AND c.content->>'internal_generation'=p_generation::text
 AND c.content->>'recovery_generation'=c.recovery_generation::text
 AND c.content->>'history_version'=p_epoch::text
 AND c.content->'storage_anchor'->>'history_epoch'=p_epoch::text
 AND c.content->>'confirmed_watermark'=p_d3::text
 AND c.content->>'applied_watermark'=p_d3::text
 AND c.content->'prefix_ref'->>'historyVersion'=p_logical_version::text
 AND c.content->'prefix_ref'->>'tenantId'=p_tenant_id::text
 AND c.content->'prefix_ref'->>'gameId'=p_game_id::text
 FOR SHARE OF c;
 -- JOINで形成したROWTYPEのtuple headerを保存行xminとして使わない。
 -- 直前のCP行lockを保持した同TXで、物理表のsystem列を明示取得する。
 SELECT c.xmin INTO STRICT physical_xmin
 FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation AND c.id=cp.id AND c.revision=cp.revision;
 -- 最新CPも全raw event/ledger/slot/全physicalと同じ受理取引の保存印へ束縛する。
 IF NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id
 AND e.game_id=a.game_id AND e.id=a.source_event_id
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)=
 (e.tenant_id,e.game_id,e.generation,e.d1)
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id
 AND a.internal_generation=p_generation AND a.source_d1=p_d3
 AND a.state='consumed' AND a.consumed_at=cp.saved_at
 AND a.checkpoint_id=cp.id AND a.checkpoint_revision+1=cp.revision
 AND a.next_checkpoint_content=cp.content AND a.roster_snapshot=cp.roster
 AND a.xmin=physical_xmin AND e.xmin=a.xmin AND l.xmin=a.xmin AND es.xmin=a.xmin
 AND a.xmin::text::numeric=pg_catalog.mod(a.transaction_id::numeric,4294967296)
 AND e.generation=p_generation AND e.d1=p_d3 AND e.d2=a.source_d2
 AND e.d5=a.d5 AND e.event_kind='play_input' AND e.ledger_kind='accepted'
 AND e.payload->>'formatVersion'='play-prefix-play-v3'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 AND e.legacy_row_identifier IS NULL AND es.confirmed_version=1
 AND l.kind='accepted' AND l.source_fingerprint=a.event_fingerprint
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND cp.content->'last_source'->>'id'=e.id::text
 AND cp.content->'last_source'->>'d5'=e.d5::text
 AND cp.content->'last_source'->>'source_fingerprint'=l.source_fingerprint
 AND cp.content->>'wire_d4'=a.wire_d4)
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 -- v3はplay-only原典だけ。非play/gap/墓標を抜いて新版に偽装しない。
 IF EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.generation=p_generation
 AND e.d1<=p_d3 AND (e.event_kind<>'play_input' OR e.ledger_kind<>'accepted'
 OR e.is_tombstone OR e.replaced_at IS NOT NULL OR e.retired_at IS NOT NULL
 OR e.import_batch_id IS NOT NULL OR e.migration_unverified
 OR e.legacy_row_identifier IS NOT NULL))
 OR (SELECT pg_catalog.count(*) FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.generation=p_generation
 AND e.d1<=p_d3)<>p_d3 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 SELECT pg_catalog.jsonb_agg(chain_row.wire_d4 ORDER BY chain_row.issuance_order)
 INTO chain
 FROM (SELECT r.issuance_order,b.wire_d4 FROM public.recording_generations r
 JOIN sync_fence.writer_bindings b ON b.tenant_id=r.tenant_id
 AND b.game_id=r.game_id AND b.internal_generation=r.generation
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND r.kind='normal'
 AND r.issuance_order<=(SELECT own.issuance_order
 FROM public.recording_generations own WHERE own.tenant_id=p_tenant_id
 AND own.game_id=p_game_id AND own.generation=p_generation)
 GROUP BY r.issuance_order,b.wire_d4) chain_row;
 WITH active AS (SELECT h.tenant_id,h.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 CASE WHEN e.payload->>'formatVersion'='first-ball-play-v1' THEN
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 ELSE pg_catalog.jsonb_build_object('kind','accepted-ordinary-admission-v1',
 'qualified',COALESCE((
 a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.tenant_id=e.tenant_id AND a.game_id=e.game_id
 AND a.source_event_id=e.id AND a.internal_generation=e.generation
 AND a.d5=e.d5 AND a.play_row_id=pr.id
 AND a.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND a.xmin::text::numeric=
 pg_catalog.mod(a.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=a.xmin AND l.xmin=a.xmin AND pr.xmin=a.xmin
 AND es.xmin=a.xmin AND a.source_d1=e.d1 AND a.source_d2=e.d2 AND h.internal_generation=e.generation AND h.d1=e.d1 AND h.d2=e.d2 AND h.entry=a.history_entry AND a.next_checkpoint_content->'projection_snapshot' IS NOT NULL ),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',a.xmin::text,'play',pr.xmin::text),'frame',pg_catalog.jsonb_build_object(
 'play',pg_catalog.jsonb_build_object('source',pg_catalog.jsonb_build_object('eventId',e.id::text,
 'gameId',e.game_id::text,'generation',a.wire_d4,'d1',e.d1::text,
 'd5',e.d5::text,'fingerprint',l.source_fingerprint,'eventKind','play_input'),'playId',pr.id::text,
 'd2',e.d2::text,'physicalPlayNumber',pr.play_number::text),
 'historyEntry',h.entry,'beforeContext',pg_catalog.jsonb_build_object(
 'current',CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'current'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'after' END,'rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rosterDigest','lineup',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lineup',
 'participants',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'participants','runners',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'runners',
 'responsibility',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'responsibility','lastPlayEvaluation',
 CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lastPlayEvaluation'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'t2' END),'afterContext',pg_catalog.jsonb_build_object(
 'current',e.payload->'calculation'->'response'->'value'->'t1'->'after','rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',e.payload->'calculation'->'response'->'value'->'rosterDigest','lineup',e.payload->'calculation'->'response'->'value'->'lineup',
 'participants',e.payload->'calculation'->'response'->'value'->'participants','runners',e.payload->'calculation'->'response'->'value'->'runners',
 'responsibility',e.payload->'calculation'->'response'->'value'->'nextResponsibility','lastPlayEvaluation',e.payload->'calculation'->'response'->'value'->'t2')),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'storedEvent',pg_catalog.jsonb_build_object('d5',e.d5::text,'d1',e.d1,
 'd4',a.wire_d4,'game_id',e.game_id::text,'event_kind','play_input',
 'd2',e.d2,'payload',e.payload,'state_diff',e.state_diff),
 'storedFingerprint',l.source_fingerprint,
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(a),
 'physical',pg_catalog.jsonb_build_object('play_row',pg_catalog.to_jsonb(pr),
 'play_runners',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr)
 ORDER BY rr.base,rr.id),'[]'::jsonb) FROM public.play_runners rr
 WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id)),
 'expectedPhysical',a.next_checkpoint_content->'projection_snapshot') END AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN sync_fence.ordinary_pitch_history h ON h.tenant_id=c.tenant_id
 AND h.game_id=c.game_id AND h.history_version=c.history_version
 LEFT JOIN public.operation_events e ON e.tenant_id=h.tenant_id
 AND e.game_id=h.game_id AND e.id=h.source_event_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions a ON a.tenant_id=e.tenant_id
 AND a.game_id=e.game_id AND a.source_event_id=e.id AND a.state='consumed'
 AND a.event_fingerprint=l.source_fingerprint
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id
 AND u.game_id=n.game_id AND u.id=n.source_event_id AND u.event_kind='undo'
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id
 AND n.target_event_id=e.id AND n.state='consumed'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)

UNION ALL
SELECT c.tenant_id,c.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.operation_events e ON e.tenant_id=c.tenant_id AND e.game_id=c.game_id
 AND e.event_kind='play_input' AND e.payload->>'formatVersion'='first-ball-play-v1'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND e.d1<=r.confirmed_watermark
 AND NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=e.tenant_id AND h.game_id=e.game_id
 AND h.source_event_id=e.id AND h.history_version=c.history_version)
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id AND u.id=n.source_event_id
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id AND n.state='consumed'
 AND n.target_event_id=e.id AND u.event_kind='undo'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)
) SELECT pg_catalog.count(*) INTO total FROM active;
 IF total<1 OR total::text IS DISTINCT FROM cp.content->>'history_depth'
 OR cp.content->'prefix_ref'->>'length' IS DISTINCT FROM total::text
 OR (p_after_order=0 AND (p_after_d1<>0 OR
 p_after_id<>'00000000-0000-0000-0000-000000000000'::uuid))
 OR (p_after_order>0 AND NOT EXISTS(WITH active AS (SELECT h.tenant_id,h.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 CASE WHEN e.payload->>'formatVersion'='first-ball-play-v1' THEN
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 ELSE pg_catalog.jsonb_build_object('kind','accepted-ordinary-admission-v1',
 'qualified',COALESCE((
 a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.tenant_id=e.tenant_id AND a.game_id=e.game_id
 AND a.source_event_id=e.id AND a.internal_generation=e.generation
 AND a.d5=e.d5 AND a.play_row_id=pr.id
 AND a.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND a.xmin::text::numeric=
 pg_catalog.mod(a.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=a.xmin AND l.xmin=a.xmin AND pr.xmin=a.xmin
 AND es.xmin=a.xmin AND a.source_d1=e.d1 AND a.source_d2=e.d2 AND h.internal_generation=e.generation AND h.d1=e.d1 AND h.d2=e.d2 AND h.entry=a.history_entry AND a.next_checkpoint_content->'projection_snapshot' IS NOT NULL ),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',a.xmin::text,'play',pr.xmin::text),'frame',pg_catalog.jsonb_build_object(
 'play',pg_catalog.jsonb_build_object('source',pg_catalog.jsonb_build_object('eventId',e.id::text,
 'gameId',e.game_id::text,'generation',a.wire_d4,'d1',e.d1::text,
 'd5',e.d5::text,'fingerprint',l.source_fingerprint,'eventKind','play_input'),'playId',pr.id::text,
 'd2',e.d2::text,'physicalPlayNumber',pr.play_number::text),
 'historyEntry',h.entry,'beforeContext',pg_catalog.jsonb_build_object(
 'current',CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'current'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'after' END,'rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rosterDigest','lineup',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lineup',
 'participants',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'participants','runners',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'runners',
 'responsibility',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'responsibility','lastPlayEvaluation',
 CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lastPlayEvaluation'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'t2' END),'afterContext',pg_catalog.jsonb_build_object(
 'current',e.payload->'calculation'->'response'->'value'->'t1'->'after','rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',e.payload->'calculation'->'response'->'value'->'rosterDigest','lineup',e.payload->'calculation'->'response'->'value'->'lineup',
 'participants',e.payload->'calculation'->'response'->'value'->'participants','runners',e.payload->'calculation'->'response'->'value'->'runners',
 'responsibility',e.payload->'calculation'->'response'->'value'->'nextResponsibility','lastPlayEvaluation',e.payload->'calculation'->'response'->'value'->'t2')),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'storedEvent',pg_catalog.jsonb_build_object('d5',e.d5::text,'d1',e.d1,
 'd4',a.wire_d4,'game_id',e.game_id::text,'event_kind','play_input',
 'd2',e.d2,'payload',e.payload,'state_diff',e.state_diff),
 'storedFingerprint',l.source_fingerprint,
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(a),
 'physical',pg_catalog.jsonb_build_object('play_row',pg_catalog.to_jsonb(pr),
 'play_runners',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr)
 ORDER BY rr.base,rr.id),'[]'::jsonb) FROM public.play_runners rr
 WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id)),
 'expectedPhysical',a.next_checkpoint_content->'projection_snapshot') END AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN sync_fence.ordinary_pitch_history h ON h.tenant_id=c.tenant_id
 AND h.game_id=c.game_id AND h.history_version=c.history_version
 LEFT JOIN public.operation_events e ON e.tenant_id=h.tenant_id
 AND e.game_id=h.game_id AND e.id=h.source_event_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions a ON a.tenant_id=e.tenant_id
 AND a.game_id=e.game_id AND a.source_event_id=e.id AND a.state='consumed'
 AND a.event_fingerprint=l.source_fingerprint
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id
 AND u.game_id=n.game_id AND u.id=n.source_event_id AND u.event_kind='undo'
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id
 AND n.target_event_id=e.id AND n.state='consumed'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)

UNION ALL
SELECT c.tenant_id,c.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.operation_events e ON e.tenant_id=c.tenant_id AND e.game_id=c.game_id
 AND e.event_kind='play_input' AND e.payload->>'formatVersion'='first-ball-play-v1'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND e.d1<=r.confirmed_watermark
 AND NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=e.tenant_id AND h.game_id=e.game_id
 AND h.source_event_id=e.id AND h.history_version=c.history_version)
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id AND u.id=n.source_event_id
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id AND n.state='consumed'
 AND n.target_event_id=e.id AND u.event_kind='undo'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)
) SELECT 1 FROM active
 WHERE (issuance_order,d1,source_event_id)=(p_after_order,p_after_d1,p_after_id)))
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 FOR x IN WITH active AS (SELECT h.tenant_id,h.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 CASE WHEN e.payload->>'formatVersion'='first-ball-play-v1' THEN
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 ELSE pg_catalog.jsonb_build_object('kind','accepted-ordinary-admission-v1',
 'qualified',COALESCE((
 a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.tenant_id=e.tenant_id AND a.game_id=e.game_id
 AND a.source_event_id=e.id AND a.internal_generation=e.generation
 AND a.d5=e.d5 AND a.play_row_id=pr.id
 AND a.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND a.xmin::text::numeric=
 pg_catalog.mod(a.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=a.xmin AND l.xmin=a.xmin AND pr.xmin=a.xmin
 AND es.xmin=a.xmin AND a.source_d1=e.d1 AND a.source_d2=e.d2 AND h.internal_generation=e.generation AND h.d1=e.d1 AND h.d2=e.d2 AND h.entry=a.history_entry AND a.next_checkpoint_content->'projection_snapshot' IS NOT NULL ),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',a.xmin::text,'play',pr.xmin::text),'frame',pg_catalog.jsonb_build_object(
 'play',pg_catalog.jsonb_build_object('source',pg_catalog.jsonb_build_object('eventId',e.id::text,
 'gameId',e.game_id::text,'generation',a.wire_d4,'d1',e.d1::text,
 'd5',e.d5::text,'fingerprint',l.source_fingerprint,'eventKind','play_input'),'playId',pr.id::text,
 'd2',e.d2::text,'physicalPlayNumber',pr.play_number::text),
 'historyEntry',h.entry,'beforeContext',pg_catalog.jsonb_build_object(
 'current',CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'current'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'after' END,'rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rosterDigest','lineup',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lineup',
 'participants',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'participants','runners',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'runners',
 'responsibility',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'responsibility','lastPlayEvaluation',
 CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lastPlayEvaluation'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'t2' END),'afterContext',pg_catalog.jsonb_build_object(
 'current',e.payload->'calculation'->'response'->'value'->'t1'->'after','rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',e.payload->'calculation'->'response'->'value'->'rosterDigest','lineup',e.payload->'calculation'->'response'->'value'->'lineup',
 'participants',e.payload->'calculation'->'response'->'value'->'participants','runners',e.payload->'calculation'->'response'->'value'->'runners',
 'responsibility',e.payload->'calculation'->'response'->'value'->'nextResponsibility','lastPlayEvaluation',e.payload->'calculation'->'response'->'value'->'t2')),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'storedEvent',pg_catalog.jsonb_build_object('d5',e.d5::text,'d1',e.d1,
 'd4',a.wire_d4,'game_id',e.game_id::text,'event_kind','play_input',
 'd2',e.d2,'payload',e.payload,'state_diff',e.state_diff),
 'storedFingerprint',l.source_fingerprint,
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(a),
 'physical',pg_catalog.jsonb_build_object('play_row',pg_catalog.to_jsonb(pr),
 'play_runners',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr)
 ORDER BY rr.base,rr.id),'[]'::jsonb) FROM public.play_runners rr
 WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id)),
 'expectedPhysical',a.next_checkpoint_content->'projection_snapshot') END AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN sync_fence.ordinary_pitch_history h ON h.tenant_id=c.tenant_id
 AND h.game_id=c.game_id AND h.history_version=c.history_version
 LEFT JOIN public.operation_events e ON e.tenant_id=h.tenant_id
 AND e.game_id=h.game_id AND e.id=h.source_event_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions a ON a.tenant_id=e.tenant_id
 AND a.game_id=e.game_id AND a.source_event_id=e.id AND a.state='consumed'
 AND a.event_fingerprint=l.source_fingerprint
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id
 AND u.game_id=n.game_id AND u.id=n.source_event_id AND u.event_kind='undo'
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id
 AND n.target_event_id=e.id AND n.state='consumed'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)

UNION ALL
SELECT c.tenant_id,c.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.operation_events e ON e.tenant_id=c.tenant_id AND e.game_id=c.game_id
 AND e.event_kind='play_input' AND e.payload->>'formatVersion'='first-ball-play-v1'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND e.d1<=r.confirmed_watermark
 AND NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=e.tenant_id AND h.game_id=e.game_id
 AND h.source_event_id=e.id AND h.history_version=c.history_version)
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id AND u.id=n.source_event_id
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id AND n.state='consumed'
 AND n.target_event_id=e.id AND u.event_kind='undo'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)
) SELECT * FROM active
 WHERE p_after_order=0 OR (issuance_order,d1,source_event_id)<
 (p_after_order,p_after_d1,p_after_id)
 ORDER BY issuance_order DESC,d1 DESC,source_event_id DESC LIMIT p_page_size+1 LOOP
 j:=x.record_json;
 IF j->'qualified' IS DISTINCT FROM 'true'::jsonb
 OR j->>'kind' NOT IN ('legacy-first-ball-v1','accepted-ordinary-admission-v1')
 OR (j->>'kind'='accepted-ordinary-admission-v1' AND
 j->'physical' IS DISTINCT FROM j->'expectedPhysical')
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 items:=items||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
 'kind',j->'kind','cursor',j->'cursor','frame',j->'frame',
 'event',j->'event','fingerprint',j->'ledger'->'source_fingerprint',
 'wireD4',j->'admission'->'wire_d4',
 'physical',CASE WHEN j->>'kind'='legacy-first-ball-v1' THEN
 pg_catalog.jsonb_build_object('play_row',j->'play','play_runners',j->'runners')
 ELSE j->'physical' END));
 END LOOP;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('checkpoint',cp.content,
 'total',total,'items',items,'storage',pg_catalog.jsonb_build_object(
 'row',pg_catalog.to_jsonb(cp),'nextPhysicalPlayNumber',
 (SELECT (pg_catalog.max(pr.play_number)+1)::text FROM public.play_rows pr
 WHERE pr.tenant_id=p_tenant_id AND pr.game_id=p_game_id)),
 'generationChain',chain)::text;
END;

 ELSE
DECLARE cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; x record; j jsonb;
 items jsonb:='[]'::jsonb; total bigint;
BEGIN

 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_generation IS NULL OR p_generation<=0 THEN
 RAISE EXCEPTION 'ordinary prefix read rejected' USING ERRCODE='42501';
 END IF;

 IF p_checkpoint_id IS NULL OR p_revision IS NULL OR p_epoch IS NULL OR p_d3 IS NULL
 OR p_logical_version IS NULL OR p_page_size IS NULL OR p_after_order IS NULL
 OR p_after_d1 IS NULL OR p_revision<1 OR p_epoch<1 OR p_d3<1
 OR p_logical_version<1 OR p_page_size NOT BETWEEN 1 AND 100
 OR p_after_order<0 OR p_after_d1<0 OR p_after_id IS NULL
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.recording_generations g ON (g.tenant_id,g.game_id,g.generation)=
 (c.tenant_id,c.game_id,c.internal_generation)
 WHERE g.recovery_generation=c.recovery_generation
 AND c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation AND c.id=p_checkpoint_id
 AND c.revision=p_revision AND c.history_version=p_epoch AND c.state='current'
 AND c.confirmed_watermark=p_d3 AND c.applied_watermark=p_d3
 AND g.confirmed_watermark=p_d3 AND g.applied_prefix=p_d3 AND g.kind='normal'
 AND g.revoked_at IS NULL AND g.retired_at IS NULL AND g.import_batch_id IS NULL
 AND c.content->>'formatVersion'='nonplay-prefix-checkpoint-v1'
 AND c.content_digest=c.content->'ref'->>'digest'
 AND c.content->'ref'->>'id'=c.id::text
 AND c.content->'ref'->>'revision'=c.revision::text
 AND c.content->'content'->>'d3'=p_d3::text
 AND c.content->'content'->>'storageHistoryEpoch'=p_epoch::text
 AND c.content->'content'->>'historyVersion'=p_logical_version::text
 AND c.content->'content'->'scope'->>'tenantId'=p_tenant_id::text
 AND c.content->'content'->'scope'->>'gameId'=p_game_id::text
 FOR SHARE OF c;
 -- CP全文は最新受理印の実after原本へ束縛する。自己digestだけでは資格にしない。
 IF NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events e ON e.tenant_id=n.tenant_id
 AND e.game_id=n.game_id AND e.id=n.source_event_id
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN sync_fence.ordinary_pitch_checkpoints c ON c.tenant_id=n.tenant_id
 AND c.game_id=n.game_id AND c.internal_generation=n.internal_generation
 WHERE n.tenant_id=p_tenant_id AND n.game_id=p_game_id
 AND n.internal_generation=p_generation AND n.source_d1=p_d3
 AND n.state='consumed' AND n.consumed_at IS NOT NULL
 AND n.preparation->'storage'->'row'->'roster'=cp.roster
 AND n.preparation->'after_source'->'checkpoint'=cp.content
 AND c.id=cp.id AND c.content=cp.content AND c.xmin=n.xmin
 AND e.event_kind='undo' AND e.ledger_kind='accepted' AND e.xmin=n.xmin
 AND l.kind='accepted' AND l.source_fingerprint=n.event_fingerprint
 AND l.xmin=n.xmin AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 UNION ALL SELECT 1 FROM sync_fence.ordinary_pitch_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id
 AND e.game_id=a.game_id AND e.id=a.source_event_id
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN sync_fence.ordinary_pitch_checkpoints c ON c.tenant_id=a.tenant_id
 AND c.game_id=a.game_id AND c.internal_generation=a.internal_generation
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id
 AND a.internal_generation=p_generation AND a.source_d1=p_d3
 AND a.state='consumed' AND a.consumed_at=cp.saved_at
 AND a.next_checkpoint_content->>'formatVersion'='nonplay-normal-storage-v1'
 AND a.next_checkpoint_content->'checkpoint'=cp.content AND a.roster_snapshot=cp.roster
 AND c.id=cp.id AND c.content=cp.content AND c.xmin=a.xmin
 AND e.event_kind='play_input' AND e.ledger_kind='accepted' AND e.xmin=a.xmin
 AND l.kind='accepted' AND l.source_fingerprint=a.event_fingerprint
 AND l.xmin=a.xmin AND l.retired_at IS NULL AND l.import_batch_id IS NULL)
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 -- 非playを欠番として捨てず、真正受理印の完全参照だけを除外根拠にする。
 IF EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.generation=p_generation
 AND e.d1<=p_d3 AND (e.ledger_kind<>'accepted' OR e.is_tombstone
 OR e.replaced_at IS NOT NULL OR e.retired_at IS NOT NULL OR e.import_batch_id IS NOT
 NULL
 OR e.migration_unverified OR e.legacy_row_identifier IS NOT NULL
 OR e.event_kind NOT IN ('play_input','undo')))
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 IF (SELECT pg_catalog.count(*) FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.generation=p_generation
 AND e.d1<=p_d3 AND e.replaced_at IS NULL AND e.retired_at IS NULL)<>p_d3
 OR EXISTS(SELECT 1 FROM public.operation_events u
 WHERE u.tenant_id=p_tenant_id AND u.game_id=p_game_id AND u.generation=p_generation
 AND u.d1<=p_d3 AND u.event_kind='undo' AND NOT EXISTS(
 SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.idempotency_ledger ul ON ul.tenant_id=n.tenant_id AND ul.d5=n.d5
 JOIN public.event_slots us ON (us.tenant_id,us.game_id,us.generation,us.d1)=
 (u.tenant_id,u.game_id,u.generation,u.d1)
 WHERE us.confirmed_version=1 AND us.xmin=n.xmin AND u.xmin=n.xmin
 AND ul.xmin=n.xmin AND n.tenant_id=u.tenant_id AND n.game_id=u.game_id
 AND n.source_event_id=u.id
 AND n.internal_generation=u.generation AND n.d5=u.d5 AND n.state='consumed'
 AND n.consumed_at IS NOT NULL AND n.target_generation=u.target_generation
 AND n.target_d1=u.target_d1 AND ul.kind='accepted'
 AND ul.source_fingerprint=n.event_fingerprint AND ul.retired_at IS NULL
 AND ul.import_batch_id IS NULL)) THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(pg_catalog.jsonb_build_array(
 cp.content->'content'->'d1Head'->'source',
 cp.content->'content'->'projectionHead'->'source',
 cp.content->'content'->'activeHead'->'source')) head
 WHERE pg_catalog.jsonb_typeof(head)<>'null' AND NOT EXISTS(
 SELECT 1 FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.id::text=head->>'eventId'
 AND e.d5::text=head->>'d5' AND e.d1::text=head->>'d1'
 AND e.game_id::text=head->>'gameId' AND e.event_kind=head->>'eventKind'
 AND e.ledger_kind='accepted' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND NOT e.migration_unverified AND l.kind='accepted'
 AND l.source_fingerprint=head->>'fingerprint' AND l.retired_at IS NULL
 AND l.import_batch_id IS NULL AND EXISTS(
 SELECT 1 FROM sync_fence.first_ball_write_admissions a WHERE a.tenant_id=e.tenant_id
 AND a.source_event_id=e.id AND a.state='consumed' AND a.wire_d4=head->>'generation'
 UNION ALL SELECT 1 FROM sync_fence.ordinary_pitch_write_admissions a
 WHERE a.tenant_id=e.tenant_id AND a.source_event_id=e.id AND a.state='consumed'
 AND a.wire_d4=head->>'generation'
 UNION ALL SELECT 1 FROM sync_fence.nonplay_write_admissions a
 WHERE a.tenant_id=e.tenant_id AND a.source_event_id=e.id AND a.state='consumed'
 AND a.wire_d4=head->>'generation')))
 OR cp.content->'content'->'d1Head'->'source'->>'d1' IS DISTINCT FROM p_d3::text
 OR (cp.content->'content'->>'nextPhysicalPlayNumber')::bigint IS DISTINCT FROM
 (SELECT COALESCE(pg_catalog.max(pr.play_number),0)+1 FROM public.play_rows pr
 WHERE pr.tenant_id=p_tenant_id AND pr.game_id=p_game_id)
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 WITH active AS (SELECT h.tenant_id,h.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 CASE WHEN e.payload->>'formatVersion'='first-ball-play-v1' THEN
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 ELSE pg_catalog.jsonb_build_object('kind','accepted-ordinary-admission-v1',
 'qualified',COALESCE((
 a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.tenant_id=e.tenant_id AND a.game_id=e.game_id
 AND a.source_event_id=e.id AND a.internal_generation=e.generation
 AND a.d5=e.d5 AND a.play_row_id=pr.id
 AND a.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND a.xmin::text::numeric=
 pg_catalog.mod(a.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=a.xmin AND l.xmin=a.xmin AND pr.xmin=a.xmin
 AND es.xmin=a.xmin AND a.source_d1=e.d1 AND a.source_d2=e.d2 AND h.internal_generation=e.generation AND h.d1=e.d1 AND h.d2=e.d2 AND h.entry=a.history_entry AND a.next_checkpoint_content->'projection_snapshot' IS NOT NULL ),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',a.xmin::text,'play',pr.xmin::text),'frame',pg_catalog.jsonb_build_object(
 'play',pg_catalog.jsonb_build_object('source',pg_catalog.jsonb_build_object('eventId',e.id::text,
 'gameId',e.game_id::text,'generation',a.wire_d4,'d1',e.d1::text,
 'd5',e.d5::text,'fingerprint',l.source_fingerprint,'eventKind','play_input'),'playId',pr.id::text,
 'd2',e.d2::text,'physicalPlayNumber',pr.play_number::text),
 'historyEntry',h.entry,'beforeContext',pg_catalog.jsonb_build_object(
 'current',CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'current'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'after' END,'rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rosterDigest','lineup',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lineup',
 'participants',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'participants','runners',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'runners',
 'responsibility',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'responsibility','lastPlayEvaluation',
 CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lastPlayEvaluation'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'t2' END),'afterContext',pg_catalog.jsonb_build_object(
 'current',e.payload->'calculation'->'response'->'value'->'t1'->'after','rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',e.payload->'calculation'->'response'->'value'->'rosterDigest','lineup',e.payload->'calculation'->'response'->'value'->'lineup',
 'participants',e.payload->'calculation'->'response'->'value'->'participants','runners',e.payload->'calculation'->'response'->'value'->'runners',
 'responsibility',e.payload->'calculation'->'response'->'value'->'nextResponsibility','lastPlayEvaluation',e.payload->'calculation'->'response'->'value'->'t2')),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'storedEvent',pg_catalog.jsonb_build_object('d5',e.d5::text,'d1',e.d1,
 'd4',a.wire_d4,'game_id',e.game_id::text,'event_kind','play_input',
 'd2',e.d2,'payload',e.payload,'state_diff',e.state_diff),
 'storedFingerprint',l.source_fingerprint,
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(a),
 'physical',pg_catalog.jsonb_build_object('play_row',pg_catalog.to_jsonb(pr),
 'play_runners',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr)
 ORDER BY rr.base,rr.id),'[]'::jsonb) FROM public.play_runners rr
 WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id)),
 'expectedPhysical',a.next_checkpoint_content->'projection_snapshot') END AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN sync_fence.ordinary_pitch_history h ON h.tenant_id=c.tenant_id
 AND h.game_id=c.game_id AND h.history_version=c.history_version
 LEFT JOIN public.operation_events e ON e.tenant_id=h.tenant_id
 AND e.game_id=h.game_id AND e.id=h.source_event_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions a ON a.tenant_id=e.tenant_id
 AND a.game_id=e.game_id AND a.source_event_id=e.id AND a.state='consumed'
 AND a.event_fingerprint=l.source_fingerprint
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id
 AND u.game_id=n.game_id AND u.id=n.source_event_id AND u.event_kind='undo'
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id
 AND n.target_event_id=e.id AND n.state='consumed'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)

UNION ALL
SELECT c.tenant_id,c.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.operation_events e ON e.tenant_id=c.tenant_id AND e.game_id=c.game_id
 AND e.event_kind='play_input' AND e.payload->>'formatVersion'='first-ball-play-v1'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND e.d1<=r.confirmed_watermark
 AND NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=e.tenant_id AND h.game_id=e.game_id
 AND h.source_event_id=e.id AND h.history_version=c.history_version)
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id AND u.id=n.source_event_id
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id AND n.state='consumed'
 AND n.target_event_id=e.id AND u.event_kind='undo'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)
) SELECT pg_catalog.count(*) INTO total FROM active;
 IF (p_after_order=0 AND (p_after_d1<>0 OR
 p_after_id<>'00000000-0000-0000-0000-000000000000'::uuid))
 OR (p_after_order>0 AND NOT EXISTS(WITH active AS (SELECT h.tenant_id,h.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 CASE WHEN e.payload->>'formatVersion'='first-ball-play-v1' THEN
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 ELSE pg_catalog.jsonb_build_object('kind','accepted-ordinary-admission-v1',
 'qualified',COALESCE((
 a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.tenant_id=e.tenant_id AND a.game_id=e.game_id
 AND a.source_event_id=e.id AND a.internal_generation=e.generation
 AND a.d5=e.d5 AND a.play_row_id=pr.id
 AND a.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND a.xmin::text::numeric=
 pg_catalog.mod(a.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=a.xmin AND l.xmin=a.xmin AND pr.xmin=a.xmin
 AND es.xmin=a.xmin AND a.source_d1=e.d1 AND a.source_d2=e.d2 AND h.internal_generation=e.generation AND h.d1=e.d1 AND h.d2=e.d2 AND h.entry=a.history_entry AND a.next_checkpoint_content->'projection_snapshot' IS NOT NULL ),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',a.xmin::text,'play',pr.xmin::text),'frame',pg_catalog.jsonb_build_object(
 'play',pg_catalog.jsonb_build_object('source',pg_catalog.jsonb_build_object('eventId',e.id::text,
 'gameId',e.game_id::text,'generation',a.wire_d4,'d1',e.d1::text,
 'd5',e.d5::text,'fingerprint',l.source_fingerprint,'eventKind','play_input'),'playId',pr.id::text,
 'd2',e.d2::text,'physicalPlayNumber',pr.play_number::text),
 'historyEntry',h.entry,'beforeContext',pg_catalog.jsonb_build_object(
 'current',CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'current'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'after' END,'rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rosterDigest','lineup',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lineup',
 'participants',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'participants','runners',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'runners',
 'responsibility',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'responsibility','lastPlayEvaluation',
 CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lastPlayEvaluation'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'t2' END),'afterContext',pg_catalog.jsonb_build_object(
 'current',e.payload->'calculation'->'response'->'value'->'t1'->'after','rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',e.payload->'calculation'->'response'->'value'->'rosterDigest','lineup',e.payload->'calculation'->'response'->'value'->'lineup',
 'participants',e.payload->'calculation'->'response'->'value'->'participants','runners',e.payload->'calculation'->'response'->'value'->'runners',
 'responsibility',e.payload->'calculation'->'response'->'value'->'nextResponsibility','lastPlayEvaluation',e.payload->'calculation'->'response'->'value'->'t2')),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'storedEvent',pg_catalog.jsonb_build_object('d5',e.d5::text,'d1',e.d1,
 'd4',a.wire_d4,'game_id',e.game_id::text,'event_kind','play_input',
 'd2',e.d2,'payload',e.payload,'state_diff',e.state_diff),
 'storedFingerprint',l.source_fingerprint,
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(a),
 'physical',pg_catalog.jsonb_build_object('play_row',pg_catalog.to_jsonb(pr),
 'play_runners',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr)
 ORDER BY rr.base,rr.id),'[]'::jsonb) FROM public.play_runners rr
 WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id)),
 'expectedPhysical',a.next_checkpoint_content->'projection_snapshot') END AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN sync_fence.ordinary_pitch_history h ON h.tenant_id=c.tenant_id
 AND h.game_id=c.game_id AND h.history_version=c.history_version
 LEFT JOIN public.operation_events e ON e.tenant_id=h.tenant_id
 AND e.game_id=h.game_id AND e.id=h.source_event_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions a ON a.tenant_id=e.tenant_id
 AND a.game_id=e.game_id AND a.source_event_id=e.id AND a.state='consumed'
 AND a.event_fingerprint=l.source_fingerprint
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id
 AND u.game_id=n.game_id AND u.id=n.source_event_id AND u.event_kind='undo'
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id
 AND n.target_event_id=e.id AND n.state='consumed'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)

UNION ALL
SELECT c.tenant_id,c.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.operation_events e ON e.tenant_id=c.tenant_id AND e.game_id=c.game_id
 AND e.event_kind='play_input' AND e.payload->>'formatVersion'='first-ball-play-v1'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND e.d1<=r.confirmed_watermark
 AND NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=e.tenant_id AND h.game_id=e.game_id
 AND h.source_event_id=e.id AND h.history_version=c.history_version)
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id AND u.id=n.source_event_id
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id AND n.state='consumed'
 AND n.target_event_id=e.id AND u.event_kind='undo'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)
) SELECT 1 FROM active
 WHERE (issuance_order,d1,source_event_id)=(p_after_order,p_after_d1,p_after_id)))
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 IF total::text IS DISTINCT FROM cp.content->'content'->>'activeDepth'
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 FOR x IN WITH active AS (SELECT h.tenant_id,h.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 CASE WHEN e.payload->>'formatVersion'='first-ball-play-v1' THEN
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 ELSE pg_catalog.jsonb_build_object('kind','accepted-ordinary-admission-v1',
 'qualified',COALESCE((
 a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.tenant_id=e.tenant_id AND a.game_id=e.game_id
 AND a.source_event_id=e.id AND a.internal_generation=e.generation
 AND a.d5=e.d5 AND a.play_row_id=pr.id
 AND a.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND a.xmin::text::numeric=
 pg_catalog.mod(a.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=a.xmin AND l.xmin=a.xmin AND pr.xmin=a.xmin
 AND es.xmin=a.xmin AND a.source_d1=e.d1 AND a.source_d2=e.d2 AND h.internal_generation=e.generation AND h.d1=e.d1 AND h.d2=e.d2 AND h.entry=a.history_entry AND a.next_checkpoint_content->'projection_snapshot' IS NOT NULL ),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',a.xmin::text,'play',pr.xmin::text),'frame',pg_catalog.jsonb_build_object(
 'play',pg_catalog.jsonb_build_object('source',pg_catalog.jsonb_build_object('eventId',e.id::text,
 'gameId',e.game_id::text,'generation',a.wire_d4,'d1',e.d1::text,
 'd5',e.d5::text,'fingerprint',l.source_fingerprint,'eventKind','play_input'),'playId',pr.id::text,
 'd2',e.d2::text,'physicalPlayNumber',pr.play_number::text),
 'historyEntry',h.entry,'beforeContext',pg_catalog.jsonb_build_object(
 'current',CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'current'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'after' END,'rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rosterDigest','lineup',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lineup',
 'participants',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'participants','runners',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'runners',
 'responsibility',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'responsibility','lastPlayEvaluation',
 CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'lastPlayEvaluation'
 ELSE (CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'t2' END),'afterContext',pg_catalog.jsonb_build_object(
 'current',e.payload->'calculation'->'response'->'value'->'t1'->'after','rules',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rules',
 'rulesDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'rulesDigest','layoutDigest',(CASE WHEN e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1' THEN e.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored' ELSE e.payload->'calculation'->'request'->'source' END)->'layoutDigest',
 'rosterDigest',e.payload->'calculation'->'response'->'value'->'rosterDigest','lineup',e.payload->'calculation'->'response'->'value'->'lineup',
 'participants',e.payload->'calculation'->'response'->'value'->'participants','runners',e.payload->'calculation'->'response'->'value'->'runners',
 'responsibility',e.payload->'calculation'->'response'->'value'->'nextResponsibility','lastPlayEvaluation',e.payload->'calculation'->'response'->'value'->'t2')),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'storedEvent',pg_catalog.jsonb_build_object('d5',e.d5::text,'d1',e.d1,
 'd4',a.wire_d4,'game_id',e.game_id::text,'event_kind','play_input',
 'd2',e.d2,'payload',e.payload,'state_diff',e.state_diff),
 'storedFingerprint',l.source_fingerprint,
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(a),
 'physical',pg_catalog.jsonb_build_object('play_row',pg_catalog.to_jsonb(pr),
 'play_runners',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr)
 ORDER BY rr.base,rr.id),'[]'::jsonb) FROM public.play_runners rr
 WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id)),
 'expectedPhysical',a.next_checkpoint_content->'projection_snapshot') END AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN sync_fence.ordinary_pitch_history h ON h.tenant_id=c.tenant_id
 AND h.game_id=c.game_id AND h.history_version=c.history_version
 LEFT JOIN public.operation_events e ON e.tenant_id=h.tenant_id
 AND e.game_id=h.game_id AND e.id=h.source_event_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions a ON a.tenant_id=e.tenant_id
 AND a.game_id=e.game_id AND a.source_event_id=e.id AND a.state='consumed'
 AND a.event_fingerprint=l.source_fingerprint
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id
 AND u.game_id=n.game_id AND u.id=n.source_event_id AND u.event_kind='undo'
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id
 AND n.target_event_id=e.id AND n.state='consumed'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)

UNION ALL
SELECT c.tenant_id,c.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1','qualified',COALESCE((
 f.state='consumed' AND f.consumed_at IS NOT NULL
 AND f.tenant_id=e.tenant_id AND f.game_id=e.game_id
 AND f.source_event_id=e.id AND f.internal_generation=e.generation
 AND f.d5=e.d5 AND f.play_row_id=pr.id
 AND f.event_fingerprint=l.source_fingerprint
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND l.tenant_id=e.tenant_id AND l.d5=e.d5 AND l.kind='accepted'
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND es.tenant_id=e.tenant_id AND es.game_id=e.game_id
 AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1
 AND pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id AND pr.source_event_id=e.id
 AND pr.hidden_at IS NULL AND pr.import_batch_id IS NULL
 AND pr.legacy_row_identifier IS NULL AND NOT pr.migration_unverified
 AND f.xmin::text::numeric=
 pg_catalog.mod(f.transaction_id::numeric,4294967296::numeric)
 AND e.xmin=f.xmin AND l.xmin=f.xmin AND pr.xmin=f.xmin
 AND es.xmin=f.xmin AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',f.xmin::text,'play',pr.xmin::text),
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 AS record_json
 FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.operation_events e ON e.tenant_id=c.tenant_id AND e.game_id=c.game_id
 AND e.event_kind='play_input' AND e.payload->>'formatVersion'='first-ball-play-v1'
 LEFT JOIN public.recording_generations r ON r.tenant_id=e.tenant_id
 AND r.game_id=e.game_id AND r.generation=e.generation AND r.kind='normal'
 LEFT JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 LEFT JOIN sync_fence.first_ball_write_admissions f ON f.tenant_id=e.tenant_id
 AND f.game_id=e.game_id AND f.source_event_id=e.id AND f.state='consumed'
 LEFT JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.game_id=e.game_id
 AND pr.source_event_id=e.id AND pr.hidden_at IS NULL
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation
 AND e.d1<=r.confirmed_watermark
 AND NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=e.tenant_id AND h.game_id=e.game_id
 AND h.source_event_id=e.id AND h.history_version=c.history_version)
 AND NOT EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n
 JOIN public.operation_events u ON u.tenant_id=n.tenant_id AND u.id=n.source_event_id
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 AND ul.kind='accepted' AND ul.source_fingerprint=n.event_fingerprint
 WHERE n.tenant_id=e.tenant_id AND n.game_id=e.game_id AND n.state='consumed'
 AND n.target_event_id=e.id AND u.event_kind='undo'
 AND u.target_generation=e.generation AND u.target_d1=e.d1)
) SELECT * FROM active
 WHERE p_after_order=0 OR (issuance_order,d1,source_event_id)<
 (p_after_order,p_after_d1,p_after_id)
 ORDER BY issuance_order DESC,d1 DESC,source_event_id DESC LIMIT p_page_size+1 LOOP
 j:=x.record_json;
 IF j->'qualified' IS DISTINCT FROM 'true'::jsonb
 OR j->>'kind' NOT IN ('legacy-first-ball-v1','accepted-ordinary-admission-v1')
 OR (j->>'kind'='accepted-ordinary-admission-v1' AND
 j->'physical' IS DISTINCT FROM j->'expectedPhysical')
 THEN RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501'; END IF;
 -- nonce/lease/admission/ledger本体は実SQL外へ出さない。
 items:=items||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
 'kind',j->'kind','cursor',j->'cursor','frame',j->'frame',
 'event',j->'event','fingerprint',j->'ledger'->'source_fingerprint',
 'wireD4',j->'admission'->'wire_d4',
 'physical',CASE WHEN j->>'kind'='legacy-first-ball-v1' THEN
 pg_catalog.jsonb_build_object('play_row',j->'play','play_runners',j->'runners')
 ELSE j->'physical' END));
 END LOOP;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('checkpoint',cp.content,
 'total',total,'items',items)::text;
END;

 END IF;
END;
$dispatch$;

ALTER FUNCTION sync_right_api.read_nonplay_active_history(uuid, uuid, bigint, uuid, bigint, bigint, bigint, bigint, bigint, bigint, uuid, integer) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_nonplay_active_history(uuid, uuid, bigint, uuid, bigint, bigint, bigint, bigint, bigint, bigint, uuid, integer) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.read_nonplay_active_history(uuid, uuid, bigint, uuid, bigint, bigint, bigint, bigint, bigint, bigint, uuid, integer) TO pitchlog_app;
