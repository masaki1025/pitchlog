-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_nonplay_history_page(uuid, uuid, uuid, bytea, uuid, uuid, text)

CREATE FUNCTION sync_right_api.read_nonplay_history_page(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_request_json text)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $nonplay$
DECLARE stamp sync_fence.nonplay_write_admissions%ROWTYPE; own_xid text; p jsonb;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; 
BEGIN

IF session_user <> 'pitchlog_app' OR current_user <> 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_device_id IS NULL
 OR p_game_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce) <> 32 THEN
 RAISE EXCEPTION 'sync writer binding rejected' USING ERRCODE='42501';
END IF;
-- 実関数未供給なら例外で閉じる。callerのnonceだけでは成功しない。
PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,
 p_phase_id,p_binding_nonce,p_device_id,p_game_id);

 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT s.* INTO STRICT stamp FROM sync_fence.nonplay_write_admissions s
 JOIN sync_fence.writer_bindings b
 ON (b.tenant_id,b.attempt_id,b.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 JOIN sync_fence.writer_admissions a
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(b.tenant_id,b.attempt_id,b.phase_id)
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND s.transaction_id=own_xid AND b.transaction_id=own_xid
 AND a.transaction_id=own_xid AND a.lease_id=b.lease_id
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at FOR UPDATE OF s;
 IF NOT EXISTS(SELECT 1 FROM public.trusted_devices d
 WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id AND d.revoked_at IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id
 AND r.generation=stamp.internal_generation AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.import_batch_id IS NULL
 AND r.recovery_generation=stamp.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g
 WHERE g.singleton_id=1 AND g.state='open'
 AND g.recovery_generation=stamp.recovery_generation) THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;

 IF p_request_json IS NULL THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 p:=p_request_json::jsonb;

 IF stamp.state<>'right_verified' OR (p->>'limit')::integer<>100
 THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 AND c.id=(p->'checkpoint'->>'id')::uuid
 AND c.revision=(p->'checkpoint'->>'revision')::bigint
 AND c.content_digest=p->'checkpoint'->>'digest' FOR SHARE;
 -- framesは0042 admissionへ押し込む第二正本ではない。
 -- 実event/history/確定play印をこの固定CTE内で結ぶ。
 -- 欠落はLEFT JOINとqualified=falseで保持し、空pageへ補修しない。
 RETURN QUERY SELECT v.record_json::text
 FROM (SELECT h.tenant_id,h.game_id,c.id AS checkpoint_id,
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
 AND c.internal_generation=stamp.internal_generation
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
 AND c.internal_generation=stamp.internal_generation
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
) v
 WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id
 AND v.checkpoint_id=cp.id AND v.checkpoint_revision=cp.revision
 AND (p->'cursor'='null'::jsonb OR
 (v.issuance_order,v.d1,v.source_event_id)<
 ((p->'cursor'->>0)::bigint,(p->'cursor'->>1)::bigint,(p->'cursor'->>2)::uuid))
 ORDER BY v.issuance_order DESC,v.d1 DESC,v.source_event_id DESC LIMIT 100;

END;
$nonplay$;

ALTER FUNCTION sync_right_api.read_nonplay_history_page(uuid, uuid, uuid, bytea, uuid, uuid, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_nonplay_history_page(uuid, uuid, uuid, bytea, uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.read_nonplay_history_page(uuid, uuid, uuid, bytea, uuid, uuid, text) TO pitchlog_app;
