"""非play現在原本の有限readonly関数。秘密印は内部照合にだけ使う。"""

from pitchlog.authz.game_lifecycle_sql import control_bridge_guard
from pitchlog.authz.nonplay_prefix_sql import _active_evidence_query
from pitchlog.authz.ordinary_prefix_sql import _READ_ASSERT

IDENTITY_ARGS = (
    "uuid, uuid, bigint, uuid, bigint, bigint, bigint, bigint, "
    "bigint, bigint, uuid, integer"
)


def candidate_read_function_bodies():
    """実CPを同一anchorで固定し、100件と次page存在確認だけを返す。"""
    query = _active_evidence_query().replace(
        "stamp.internal_generation", "p_generation"
    )
    reject = "RAISE EXCEPTION 'nonplay read rejected' USING ERRCODE='42501';"
    result = {
        "read_nonplay_active_history": f"""CREATE FUNCTION
sync_right_api.read_nonplay_active_history(
 p_tenant_id uuid,p_game_id uuid,p_generation bigint,p_checkpoint_id uuid,
 p_revision bigint,p_epoch bigint,p_d3 bigint,p_logical_version bigint,
 p_after_order bigint,p_after_d1 bigint,p_after_id uuid,p_page_size integer)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $nonplayread$
DECLARE cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; x record; j jsonb;
 items jsonb:='[]'::jsonb; total bigint;
BEGIN
{_READ_ASSERT}
 IF p_checkpoint_id IS NULL OR p_revision IS NULL OR p_epoch IS NULL OR p_d3 IS NULL
 OR p_logical_version IS NULL OR p_page_size IS NULL OR p_after_order IS NULL
 OR p_after_d1 IS NULL OR p_revision<1 OR p_epoch<1 OR p_d3<1
 OR p_logical_version<1 OR p_page_size NOT BETWEEN 1 AND 100
 OR p_after_order<0 OR p_after_d1<0 OR p_after_id IS NULL
 THEN {reject} END IF;
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
 AND l.xmin=a.xmin AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 UNION ALL SELECT 1 FROM sync_fence.lifecycle_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id
 AND e.game_id=a.game_id AND e.id=a.source_event_id
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN sync_fence.ordinary_pitch_checkpoints c ON c.tenant_id=a.tenant_id
 AND c.game_id=a.game_id AND c.internal_generation=a.internal_generation
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id
 AND a.internal_generation=p_generation AND a.source_d1=p_d3 AND a.source_d2=e.d2
 AND a.state='consumed' AND a.consumed_at IS NOT NULL AND slot.confirmed_version=1
 AND a.preparation->'storage'->'row'->'roster'=cp.roster
 AND a.preparation->'after_source'->'checkpoint'=cp.content
 AND c.id=cp.id AND c.content=cp.content AND c.xmin=a.xmin
 AND e.event_kind=CASE WHEN a.action='end' THEN 'game_end_declaration' ELSE
 'game_reopen' END
 AND a.action IN ('end','reopen') AND e.ledger_kind='accepted' AND e.xmin=a.xmin
 AND l.kind='accepted' AND l.source_fingerprint=a.event_fingerprint
 AND l.xmin=a.xmin AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 UNION ALL SELECT 1 FROM sync_fence.substitution_write_receipts sr
 JOIN sync_fence.nonplay_write_admissions n ON
 (n.tenant_id,n.attempt_id,n.phase_id)=(sr.tenant_id,sr.attempt_id,sr.phase_id)
 JOIN public.operation_events e ON e.tenant_id=sr.tenant_id
 AND e.id=sr.source_event_id AND e.game_id=sr.game_id
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)=
 (e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN sync_fence.ordinary_pitch_checkpoints c ON
 (c.tenant_id,c.game_id,c.internal_generation)=
 (sr.tenant_id,sr.game_id,n.internal_generation)
 WHERE sr.tenant_id=p_tenant_id AND sr.game_id=p_game_id
 AND sr.source_d1=p_d3 AND sr.checkpoint_id=cp.id
 AND sr.after_revision=cp.revision AND sr.after_digest=cp.content_digest
 AND c.id=cp.id AND c.revision=cp.revision AND c.content=cp.content
 AND c.xmin=sr.xmin AND n.xmin=sr.xmin AND e.xmin=sr.xmin
 AND l.xmin=sr.xmin AND es.xmin=sr.xmin AND es.confirmed_version=1
 AND n.internal_generation=p_generation AND n.state='right_verified'
 AND n.d5=e.d5 AND n.event_fingerprint=l.source_fingerprint
 AND e.generation=p_generation AND e.d1=p_d3
 AND e.event_kind='substitution' AND e.ledger_kind='accepted'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 UNION ALL SELECT 1 FROM sync_fence.tiebreak_start_write_receipts tr
 JOIN sync_fence.nonplay_write_admissions n ON
 (n.tenant_id,n.attempt_id,n.phase_id)=(tr.tenant_id,tr.attempt_id,tr.phase_id)
 JOIN public.operation_events e ON e.tenant_id=tr.tenant_id
 AND e.id=tr.source_event_id AND e.game_id=tr.game_id
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)=
 (e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN sync_fence.ordinary_pitch_checkpoints c ON
 (c.tenant_id,c.game_id,c.internal_generation)=
 (tr.tenant_id,tr.game_id,n.internal_generation)
 WHERE tr.tenant_id=p_tenant_id AND tr.game_id=p_game_id
 AND tr.source_d1=p_d3 AND tr.checkpoint_id=cp.id
 AND tr.after_revision=cp.revision AND tr.after_digest=cp.content_digest
 AND c.id=cp.id AND c.revision=cp.revision AND c.content=cp.content
 AND c.xmin=tr.xmin AND n.xmin=tr.xmin AND e.xmin=tr.xmin
 AND l.xmin=tr.xmin AND es.xmin=tr.xmin AND es.confirmed_version=1
 AND n.internal_generation=p_generation AND n.state='right_verified'
 AND n.d5=e.d5 AND n.event_fingerprint=l.source_fingerprint
 AND e.generation=p_generation AND e.d1=p_d3
 AND e.event_kind='tiebreak_start' AND e.ledger_kind='accepted'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL)
 THEN {reject} END IF;
{control_bridge_guard(generation="p_generation")}
 -- 非playを欠番として捨てず、真正受理印の完全参照だけを除外根拠にする。
 IF EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.generation=p_generation
 AND e.d1<=p_d3 AND (e.ledger_kind<>'accepted' OR e.is_tombstone
 OR e.replaced_at IS NOT NULL OR e.retired_at IS NOT NULL OR e.import_batch_id IS NOT
 NULL
 OR e.migration_unverified OR e.legacy_row_identifier IS NOT NULL
 OR e.event_kind NOT IN ('play_input','undo','substitution','tiebreak_start',
 'game_end_declaration','game_reopen')))
 THEN {reject} END IF;
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
 AND ul.import_batch_id IS NULL))
 OR pg_catalog.jsonb_array_length(COALESCE(
 cp.content->'content'->'substitutionFrames','[]'::jsonb))<>
 (SELECT pg_catalog.count(*) FROM public.operation_events se
 WHERE se.tenant_id=p_tenant_id AND se.game_id=p_game_id
 AND se.generation=p_generation AND se.d1<=p_d3
 AND se.event_kind='substitution')
 OR EXISTS(SELECT 1 FROM public.operation_events se
 WHERE se.tenant_id=p_tenant_id AND se.game_id=p_game_id
 AND se.generation=p_generation AND se.d1<=p_d3
 AND se.event_kind='substitution' AND NOT EXISTS(
 SELECT 1 FROM sync_fence.substitution_write_receipts sr
 JOIN sync_fence.nonplay_write_admissions n ON
 (n.tenant_id,n.attempt_id,n.phase_id)=(sr.tenant_id,sr.attempt_id,sr.phase_id)
 JOIN public.idempotency_ledger sl ON sl.tenant_id=se.tenant_id AND sl.d5=se.d5
 JOIN public.event_slots ss ON (ss.tenant_id,ss.game_id,ss.generation,ss.d1)=
 (se.tenant_id,se.game_id,se.generation,se.d1)
 WHERE sr.tenant_id=se.tenant_id AND sr.game_id=se.game_id
 AND sr.source_event_id=se.id AND sr.source_d1=se.d1
 AND sr.checkpoint_id=cp.id AND sr.xmin=se.xmin
 AND n.xmin=se.xmin AND sl.xmin=se.xmin AND ss.xmin=se.xmin
 AND n.internal_generation=se.generation AND n.state='right_verified'
 AND n.d5=se.d5 AND n.event_fingerprint=sl.source_fingerprint
 AND sl.kind='accepted' AND sl.retired_at IS NULL AND sl.import_batch_id IS NULL
 AND ss.confirmed_version=1 AND se.ledger_kind='accepted'
 AND NOT se.is_tombstone AND se.replaced_at IS NULL AND se.retired_at IS NULL
 AND se.import_batch_id IS NULL AND NOT se.migration_unverified
 AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 COALESCE(cp.content->'content'->'substitutionFrames','[]'::jsonb)) sf
 WHERE sf->'source'->>'eventId'=se.id::text
 AND sf->'source'->>'gameId'=se.game_id::text
 AND sf->'source'->>'generation'=n.wire_d4
 AND sf->'source'->>'d1'=se.d1::text
 AND sf->'source'->>'d5'=se.d5::text
 AND sf->'source'->>'fingerprint'=sl.source_fingerprint
 AND sf->'source'->>'eventKind'='substitution')))
 OR pg_catalog.jsonb_array_length(COALESCE(
 cp.content->'content'->'tiebreakFrames','[]'::jsonb))<>
 (SELECT pg_catalog.count(*) FROM public.operation_events te
 WHERE te.tenant_id=p_tenant_id AND te.game_id=p_game_id
 AND te.generation=p_generation AND te.d1<=p_d3
 AND te.event_kind='tiebreak_start')
 OR EXISTS(SELECT 1 FROM public.operation_events te
 WHERE te.tenant_id=p_tenant_id AND te.game_id=p_game_id
 AND te.generation=p_generation AND te.d1<=p_d3
 AND te.event_kind='tiebreak_start' AND NOT EXISTS(
 SELECT 1 FROM sync_fence.tiebreak_start_write_receipts tr
 JOIN sync_fence.nonplay_write_admissions n ON
 (n.tenant_id,n.attempt_id,n.phase_id)=(tr.tenant_id,tr.attempt_id,tr.phase_id)
 JOIN public.idempotency_ledger tl ON tl.tenant_id=te.tenant_id AND tl.d5=te.d5
 JOIN public.event_slots ts ON (ts.tenant_id,ts.game_id,ts.generation,ts.d1)=
 (te.tenant_id,te.game_id,te.generation,te.d1)
 WHERE tr.tenant_id=te.tenant_id AND tr.game_id=te.game_id
 AND tr.source_event_id=te.id AND tr.source_d1=te.d1
 AND tr.checkpoint_id=cp.id AND tr.xmin=te.xmin
 AND n.xmin=te.xmin AND tl.xmin=te.xmin AND ts.xmin=te.xmin
 AND n.internal_generation=te.generation AND n.state='right_verified'
 AND n.d5=te.d5 AND n.event_fingerprint=tl.source_fingerprint
 AND tl.kind='accepted' AND tl.retired_at IS NULL AND tl.import_batch_id IS NULL
 AND ts.confirmed_version=1 AND te.ledger_kind='accepted'
 AND NOT te.is_tombstone AND te.replaced_at IS NULL AND te.retired_at IS NULL
 AND te.import_batch_id IS NULL AND NOT te.migration_unverified
 AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 COALESCE(cp.content->'content'->'tiebreakFrames','[]'::jsonb)) tf
 WHERE tf->'source'->>'eventId'=te.id::text
 AND tf->'source'->>'gameId'=te.game_id::text
 AND tf->'source'->>'generation'=n.wire_d4
 AND tf->'source'->>'d1'=te.d1::text
 AND tf->'source'->>'d5'=te.d5::text
 AND tf->'source'->>'fingerprint'=tl.source_fingerprint
 AND tf->'source'->>'eventKind'='tiebreak_start')))
 THEN {reject} END IF;
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
 AND a.wire_d4=head->>'generation'
 UNION ALL SELECT 1 FROM sync_fence.lifecycle_write_admissions a
 WHERE a.tenant_id=e.tenant_id AND a.game_id=e.game_id AND a.source_event_id=e.id
 AND a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.internal_generation=e.generation AND a.source_d1=e.d1 AND a.source_d2=e.d2
 AND a.d5=e.d5 AND a.event_fingerprint=l.source_fingerprint
 AND a.wire_d4=head->>'generation'
 UNION ALL SELECT 1 FROM sync_fence.substitution_write_receipts sr
 JOIN sync_fence.nonplay_write_admissions n ON
 (n.tenant_id,n.attempt_id,n.phase_id)=(sr.tenant_id,sr.attempt_id,sr.phase_id)
 WHERE sr.tenant_id=e.tenant_id AND sr.source_event_id=e.id
 AND sr.checkpoint_id=cp.id AND sr.source_d1=e.d1
 AND n.internal_generation=e.generation AND n.d5=e.d5
 AND n.wire_d4=head->>'generation' AND n.state='right_verified'
 AND n.event_fingerprint=l.source_fingerprint
 AND sr.xmin=e.xmin AND n.xmin=e.xmin AND l.xmin=e.xmin)))
 OR cp.content->'content'->'d1Head'->'source'->>'d1' IS DISTINCT FROM p_d3::text
 OR (cp.content->'content'->>'nextPhysicalPlayNumber')::bigint IS DISTINCT FROM
 (SELECT COALESCE(pg_catalog.max(pr.play_number),0)+1 FROM public.play_rows pr
 WHERE pr.tenant_id=p_tenant_id AND pr.game_id=p_game_id)
 THEN {reject} END IF;
 WITH active AS ({query}) SELECT pg_catalog.count(*) INTO total FROM active;
 IF (p_after_order=0 AND (p_after_d1<>0 OR
 p_after_id<>'00000000-0000-0000-0000-000000000000'::uuid))
 OR (p_after_order>0 AND NOT EXISTS(WITH active AS ({query}) SELECT 1 FROM active
 WHERE (issuance_order,d1,source_event_id)=(p_after_order,p_after_d1,p_after_id)))
 THEN {reject} END IF;
 IF total::text IS DISTINCT FROM cp.content->'content'->>'activeDepth'
 THEN {reject} END IF;
 FOR x IN WITH active AS ({query}) SELECT * FROM active
 WHERE p_after_order=0 OR (issuance_order,d1,source_event_id)<
 (p_after_order,p_after_d1,p_after_id)
 ORDER BY issuance_order DESC,d1 DESC,source_event_id DESC LIMIT p_page_size+1 LOOP
 j:=x.record_json;
 IF j->'qualified' IS DISTINCT FROM 'true'::jsonb
 OR j->>'kind' NOT IN ('legacy-first-ball-v1','accepted-ordinary-admission-v1')
 OR (j->>'kind'='accepted-ordinary-admission-v1' AND
 j->'physical' IS DISTINCT FROM j->'expectedPhysical')
 THEN {reject} END IF;
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
$nonplayread$;
"""
    }

    from pitchlog.authz.terminal_pitch_write_stamp import _dispatch_sql

    result["read_nonplay_active_history"] = _dispatch_sql(
        result["read_nonplay_active_history"],
        _legacy_read_sql(query, reject),
        "EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_checkpoints c "
        "WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id "
        "AND c.internal_generation=p_generation AND c.id=p_checkpoint_id "
        "AND c.content->>'version'='3')",
    )
    return result


def _legacy_read_sql(query, reject):
    """既v3の真正保存印を同anchorへ固定し、数学や書込資格を追加しない。"""
    return f"""CREATE FUNCTION
sync_right_api.read_nonplay_active_history(
 p_tenant_id uuid,p_game_id uuid,p_generation bigint,p_checkpoint_id uuid,
 p_revision bigint,p_epoch bigint,p_d3 bigint,p_logical_version bigint,
 p_after_order bigint,p_after_d1 bigint,p_after_id uuid,p_page_size integer)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $nonplayread$
DECLARE cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; x record; j jsonb;
 items jsonb:='[]'::jsonb; total bigint; chain jsonb; physical_xmin xid;
BEGIN
{_READ_ASSERT}
 IF p_checkpoint_id IS NULL OR p_revision IS NULL OR p_epoch IS NULL OR p_d3 IS NULL
 OR p_logical_version IS NULL OR p_page_size IS NULL OR p_after_order IS NULL
 OR p_after_d1 IS NULL OR p_revision<1 OR p_epoch<1 OR p_d3<1
 OR p_logical_version<1 OR p_page_size NOT BETWEEN 1 AND 100
 OR p_after_order<0 OR p_after_d1<0 OR p_after_id IS NULL
 THEN {reject} END IF;
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
 THEN {reject} END IF;
 -- v3はplay-only原典だけ。非play/gap/墓標を抜いて新版に偽装しない。
 IF EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.generation=p_generation
 AND e.d1<=p_d3 AND (e.event_kind<>'play_input' OR e.ledger_kind<>'accepted'
 OR e.is_tombstone OR e.replaced_at IS NOT NULL OR e.retired_at IS NOT NULL
 OR e.import_batch_id IS NOT NULL OR e.migration_unverified
 OR e.legacy_row_identifier IS NOT NULL))
 OR (SELECT pg_catalog.count(*) FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.generation=p_generation
 AND e.d1<=p_d3)<>p_d3 THEN {reject} END IF;
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
 WITH active AS ({query}) SELECT pg_catalog.count(*) INTO total FROM active;
 IF total<1 OR total::text IS DISTINCT FROM cp.content->>'history_depth'
 OR cp.content->'prefix_ref'->>'length' IS DISTINCT FROM total::text
 OR (p_after_order=0 AND (p_after_d1<>0 OR
 p_after_id<>'00000000-0000-0000-0000-000000000000'::uuid))
 OR (p_after_order>0 AND NOT EXISTS(WITH active AS ({query}) SELECT 1 FROM active
 WHERE (issuance_order,d1,source_event_id)=(p_after_order,p_after_d1,p_after_id)))
 THEN {reject} END IF;
 FOR x IN WITH active AS ({query}) SELECT * FROM active
 WHERE p_after_order=0 OR (issuance_order,d1,source_event_id)<
 (p_after_order,p_after_d1,p_after_id)
 ORDER BY issuance_order DESC,d1 DESC,source_event_id DESC LIMIT p_page_size+1 LOOP
 j:=x.record_json;
 IF j->'qualified' IS DISTINCT FROM 'true'::jsonb
 OR j->>'kind' NOT IN ('legacy-first-ball-v1','accepted-ordinary-admission-v1')
 OR (j->>'kind'='accepted-ordinary-admission-v1' AND
 j->'physical' IS DISTINCT FROM j->'expectedPhysical')
 THEN {reject} END IF;
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
$nonplayread$;
"""
