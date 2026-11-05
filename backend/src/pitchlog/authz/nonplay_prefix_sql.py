"""非play private関数の閉SQL候補。DDL/正式登録はrootだけが行う。"""

from pitchlog.authz.ordinary_pitch_write_stamp import _writer_equal
from pitchlog.authz.sync_right_sql import _ASSERT, _COMMON, render_stamped_function_sql

_REJECT = "RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501';"

# この表は0042案。未導入の関数を登録済み/実提供として扱わない。
_ADMISSION = "sync_fence.nonplay_write_admissions"


def _head():
    """既実writer/nonce/assertを保ち、印の同top-level xminを要求する。"""
    return f"""{_ASSERT}
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT s.* INTO STRICT stamp FROM {_ADMISSION} s
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
 AND {_writer_equal()} FOR UPDATE OF s;
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
 AND g.recovery_generation=stamp.recovery_generation) THEN {_REJECT} END IF;
"""


def _function(name, body, result="record_json text", extra=""):
    """任意caller名を受けず、内部閉宣言だけを描画する。"""
    return f"""CREATE FUNCTION sync_right_api.{name}({_COMMON},p_request_json text)
RETURNS TABLE({result}) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $nonplay$
DECLARE stamp {_ADMISSION}%ROWTYPE; own_xid text; p jsonb;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; {extra}
BEGIN
{_head()}
 IF p_request_json IS NULL THEN {_REJECT} END IF;
 p:=p_request_json::jsonb;
{body}
END;
$nonplay$;
"""


def candidate_function_bodies():
    """登録未了なら通常run_functionは閉拒否する有限関数集合。"""
    result = {}
    for name, sql in render_stamped_function_sql().items():
        new_name = {
            "bind_device": "bind_nonplay_device",
            "check_current_right": "check_nonplay_right",
        }[name]
        result[new_name] = sql.replace(
            "sync_right_api." + name + "(", "sync_right_api." + new_name + "("
        ).replace("sync_fence.first_ball_write_admissions", _ADMISSION)
    result["lock_nonplay_checkpoint"] = _function(
        "lock_nonplay_checkpoint",
        f"""
 IF stamp.state<>'right_verified' THEN {_REJECT} END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 AND c.recovery_generation=stamp.recovery_generation FOR UPDATE;
 -- 旧v3からの真正導出はroot bootstrap adapterを要する。JSON形を偽装しない。
 IF cp.content->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 AND cp.content->>'version' IS DISTINCT FROM '3'
 THEN {_REJECT} END IF;
 IF cp.content->>'version'='3' AND EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.d1<=cp.confirmed_watermark
 AND e.event_kind<>'play_input') THEN {_REJECT} END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'checkpoint',cp.content,'storage',pg_catalog.jsonb_build_object('row',pg_catalog.to_jsonb(cp),
 'nextPhysicalPlayNumber',(SELECT (pg_catalog.max(pr.play_number)+1)::text
 FROM public.play_rows pr WHERE pr.tenant_id=p_tenant_id AND pr.game_id=p_game_id)),
 'generationChain',(SELECT pg_catalog.jsonb_agg(x.wire_d4 ORDER BY x.issuance_order)
 FROM (SELECT r.issuance_order, b.wire_d4
 FROM public.recording_generations r
 JOIN sync_fence.writer_bindings b ON b.tenant_id=r.tenant_id
 AND b.game_id=r.game_id AND b.internal_generation=r.generation
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND r.kind='normal'
 AND r.issuance_order<=(SELECT own.issuance_order
 FROM public.recording_generations own WHERE own.tenant_id=p_tenant_id
 AND own.game_id=p_game_id AND own.generation=stamp.internal_generation)
 GROUP BY r.issuance_order,b.wire_d4) x))::text;
""",
    )
    result["read_nonplay_history_page"] = _function(
        "read_nonplay_history_page",
        f"""
 IF stamp.state<>'right_verified' OR (p->>'limit')::integer<>100
 THEN {_REJECT} END IF;
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
 FROM ({_active_evidence_query()}) v
 WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id
 AND v.checkpoint_id=cp.id AND v.checkpoint_revision=cp.revision
 AND (p->'cursor'='null'::jsonb OR
 (v.issuance_order,v.d1,v.source_event_id)<
 ((p->'cursor'->>0)::bigint,(p->'cursor'->>1)::bigint,(p->'cursor'->>2)::uuid))
 ORDER BY v.issuance_order DESC,v.d1 DESC,v.source_event_id DESC LIMIT 100;
""",
    )
    result["prepare_nonplay_undo"] = _function(
        "prepare_nonplay_undo",
        f"""
 IF stamp.state<>'right_verified' OR p->'frame_id' IS NULL
 OR p->'before_source'->'checkpoint'->'ref' IS NULL
 OR p->'after_source'->'checkpoint'->'ref' IS NULL THEN {_REJECT} END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 FOR UPDATE;
 before_cp:=p->'before_source'->'checkpoint';
 after_cp:=p->'after_source'->'checkpoint';
 target_id:=(p->'target'->'source'->>'eventId')::uuid;
 SELECT e.* INTO STRICT own_event FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots s ON (s.tenant_id,s.game_id,s.generation,s.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.id=(p->>'event_id')::uuid AND e.d5=stamp.d5
 AND e.generation=stamp.internal_generation AND e.event_kind='undo'
 AND e.ledger_kind='accepted' AND l.kind='accepted'
 AND l.source_fingerprint=stamp.event_fingerprint AND l.retired_at IS NULL
 AND l.import_batch_id IS NULL AND e.d2 IS NULL AND e.state_diff IS NULL
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified FOR SHARE OF e;
 SELECT e.* INTO STRICT target_event FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.id=target_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input'
 AND l.kind='accepted' AND l.source_fingerprint=p->'target'->'source'->>'fingerprint'
 AND e.generation=own_event.target_generation AND e.d1=own_event.target_d1
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL AND NOT e.is_tombstone
 AND NOT e.migration_unverified FOR SHARE OF e;
 IF (cp.content->>'version' IS DISTINCT FROM '3' AND cp.content IS DISTINCT FROM
before_cp)
 OR pg_catalog.to_jsonb(cp) IS DISTINCT FROM p->'storage'->'row'
 OR own_event.payload->'calculation'->'response' IS DISTINCT FROM p->'response'
 OR own_event.payload->'expectedCheckpoint' IS DISTINCT FROM before_cp->'ref'
 OR own_event.payload->>'artifactSha256' IS DISTINCT FROM p->>'artifact_sha256'
 OR own_event.d1 IS DISTINCT FROM (before_cp->'content'->>'d3')::bigint+1
 OR own_event.payload->'calculation'->'request'->'current' IS DISTINCT FROM
 before_cp->'content'->'restored'->'current'
 OR p->'target' IS DISTINCT FROM before_cp->'content'->'activeHead'
 OR p->'after_source'->'activeStack' IS DISTINCT FROM
 (p->'before_source'->'activeStack')-0
 OR after_cp->'content'->'restored' IS DISTINCT FROM
 p->'before_source'->'activeStack'->0->'beforeContext'
 OR after_cp->'content'->'nextPhysicalPlayNumber' IS DISTINCT FROM
 before_cp->'content'->'nextPhysicalPlayNumber'
 OR (after_cp->'ref'->>'revision')::bigint<>cp.revision+1
 OR (after_cp->'content'->>'activeDepth')::bigint<>
 (before_cp->'content'->>'activeDepth')::bigint-1
 THEN {_REJECT} END IF;
 SELECT r.* INTO STRICT target_play FROM public.play_rows r
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id
 AND r.id=(p->'target'->>'playId')::uuid AND r.source_event_id=target_event.id
 AND r.hidden_at IS NULL AND r.import_batch_id IS NULL
 AND NOT r.migration_unverified FOR UPDATE;
 IF target_play.play_number IS DISTINCT FROM
(p->'target'->>'physicalPlayNumber')::bigint
 OR (SELECT pg_catalog.max(r.play_number)+1 FROM public.play_rows r
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id) IS DISTINCT FROM
 (before_cp->'content'->>'nextPhysicalPlayNumber')::bigint
 OR EXISTS(SELECT 1 FROM {_ADMISSION} n WHERE n.tenant_id=p_tenant_id
 AND n.game_id=p_game_id AND n.state='consumed' AND n.target_event_id=target_id)
 THEN {_REJECT} END IF;
 -- 新版の全metaは元contentから閉じた変更集合だけで構成する。
 expected_content:=(before_cp->'content')||pg_catalog.jsonb_build_object(
 'd3',own_event.d1::text,'d1Head',pg_catalog.jsonb_build_object(
 'kind','accepted-event','source',after_cp->'content'->'projectionHead'->'source'),
 'projectionHead',pg_catalog.jsonb_build_object('kind','d1-event','source',
 pg_catalog.jsonb_build_object('eventId',own_event.id::text,'gameId',p_game_id::text,
 'generation',stamp.wire_d4,'d1',own_event.d1::text,'d5',own_event.d5::text,
 'fingerprint',stamp.event_fingerprint,'eventKind','undo')),
 'activeHead',CASE WHEN pg_catalog.jsonb_array_length(
 p->'after_source'->'activeStack')=0 THEN 'null'::jsonb ELSE
 p->'after_source'->'activeStack'->0->'play' END,
 'activeDepth',pg_catalog.jsonb_array_length(p->'after_source'->'activeStack')::text,
 'historyVersion',((before_cp->'content'->>'historyVersion')::bigint+1)::text,
 'restored',p->'before_source'->'activeStack'->0->'beforeContext');
 IF after_cp->'content' IS DISTINCT FROM expected_content
 OR after_cp->'ref'->>'id' IS DISTINCT FROM before_cp->'ref'->>'id'
 OR p->>'source_fingerprint' IS DISTINCT FROM stamp.event_fingerprint
 OR p->'event_original'->'payload' IS DISTINCT FROM own_event.payload
 OR p->'event_original'->>'d4' IS DISTINCT FROM stamp.wire_d4
 OR p->'event_original'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'event_original'->>'d5' IS DISTINCT FROM own_event.d5::text
 OR (p->'event_original'->>'d1')::bigint IS DISTINCT FROM own_event.d1
 OR p->'event_original'->'target_reference'->>'game' IS DISTINCT FROM p_game_id::text
 OR (p->'event_original'->'target_reference'->>'d1')::bigint IS DISTINCT FROM
 target_event.d1
 OR p->'event_original'->'target_reference'->>'d4' IS DISTINCT FROM
 p->'target'->'source'->>'generation'
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations old
 JOIN public.recording_generations cur ON cur.tenant_id=old.tenant_id
 AND cur.game_id=old.game_id WHERE old.tenant_id=p_tenant_id AND old.game_id=p_game_id
 AND old.generation=target_event.generation AND old.kind='normal' AND cur.kind='normal'
 AND cur.generation=stamp.internal_generation
 AND old.issuance_order<=cur.issuance_order)
 THEN {_REJECT} END IF;
 IF cp.content->>'version'='3' AND (
 before_cp->'content'->'restored'->'current' IS DISTINCT FROM cp.content->'after'
 OR before_cp->'content'->'restored'->'rules' IS DISTINCT FROM cp.content->'rules'
 OR before_cp->'content'->'restored'->'lineup' IS DISTINCT FROM cp.content->'lineup'
 OR before_cp->'content'->'restored'->'participants' IS DISTINCT FROM
 cp.content->'participants'
 OR before_cp->'content'->'restored'->'runners' IS DISTINCT FROM cp.content->'runners'
 OR before_cp->'content'->'restored'->'lastPlayEvaluation' IS DISTINCT FROM
 cp.content->'t2'
 OR cp.content->'last_source'->>'id' IS DISTINCT FROM target_event.id::text
 OR (before_cp->'ref'->>'id')::uuid IS DISTINCT FROM cp.id
 OR (before_cp->'ref'->>'revision')::bigint IS DISTINCT FROM cp.revision
 ) THEN {_REJECT} END IF;
 UPDATE {_ADMISSION} SET state='evaluated',frame_id=(p->>'frame_id')::uuid,
 frame_digest=p->>'frame_digest',artifact_sha256=p->>'artifact_sha256',
 source_event_id=own_event.id,source_d1=own_event.d1,target_event_id=target_id,
 target_generation=target_event.generation,target_d1=target_event.d1,
 target_play_id=target_play.id,checkpoint_digest=cp.content_digest,
 checkpoint_id=cp.id,checkpoint_revision=cp.revision,
 preparation_json=p_request_json,preparation=p
 WHERE (tenant_id,attempt_id,phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND state='right_verified' AND transaction_id=own_xid;
 IF NOT FOUND THEN {_REJECT} END IF;
 RETURN QUERY SELECT true;
""",
        "prepared boolean",
        (
            "before_cp jsonb; after_cp jsonb; expected_content jsonb; "
            "target_id uuid; own_event "
            "public.operation_events%ROWTYPE; target_event "
            "public.operation_events%ROWTYPE; target_play "
            "public.play_rows%ROWTYPE;"
        ),
    )
    result["consume_nonplay_undo"] = _function(
        "consume_nonplay_undo",
        f"""
 IF stamp.state<>'evaluated' OR stamp.preparation_json IS DISTINCT FROM p_request_json
 OR stamp.preparation IS DISTINCT FROM p OR stamp.frame_id IS DISTINCT FROM
 (p->>'frame_id')::uuid OR stamp.frame_digest IS DISTINCT FROM p->>'frame_digest'
 THEN {_REJECT} END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 AND c.id=stamp.checkpoint_id AND c.revision=stamp.checkpoint_revision
 AND c.content=p->'storage'->'row'->'content' FOR UPDATE;
 UPDATE public.play_rows SET hidden_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id
 AND id=(p->'target'->>'playId')::uuid AND source_event_id=stamp.target_event_id
 AND hidden_at IS NULL;
 IF NOT FOUND THEN {_REJECT} END IF;
 -- 物理play/runner/history原本は削除も再採番もしない。
 UPDATE sync_fence.ordinary_pitch_checkpoints SET
 revision=(p->'after_source'->'checkpoint'->'ref'->>'revision')::bigint,
 confirmed_watermark=(p->'after_source'->'checkpoint'->'content'->>'d3')::bigint,
 applied_watermark=(p->'after_source'->'checkpoint'->'content'->>'d3')::bigint,
 content_digest=p->'after_source'->'checkpoint'->'ref'->>'digest',
 content=p->'after_source'->'checkpoint',saved_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id
 AND internal_generation=stamp.internal_generation
 AND id=cp.id AND revision=cp.revision;
 IF NOT FOUND THEN {_REJECT} END IF;
 UPDATE {_ADMISSION} SET state='consumed',consumed_at=pg_catalog.clock_timestamp()
 WHERE (tenant_id,attempt_id,phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND state='evaluated' AND transaction_id=own_xid;
 IF NOT FOUND THEN {_REJECT} END IF;
 RETURN QUERY SELECT stats_api.rebuild_after_nonplay_undo(
 p_tenant_id,p_attempt_id,p_phase_id,p_binding_nonce,p_device_id,p_game_id,p_request_json);
""",
        "receipt_json text",
    )
    prepare = result["prepare_nonplay_undo"]
    start = prepare.index(" SELECT c.* INTO STRICT cp")
    end = prepare.index(
        " UPDATE sync_fence.nonplay_write_admissions SET state='evaluated'"
    )
    source_guard = prepare[start:end]
    consume = result["consume_nonplay_undo"]
    start = consume.index(" SELECT c.* INTO STRICT cp")
    end = consume.index(" UPDATE public.play_rows SET hidden_at=")
    consume = consume[:start] + source_guard + consume[end:]
    declarations = (
        "before_cp jsonb; after_cp jsonb; expected_content jsonb; target_id uuid; "
        "own_event public.operation_events%ROWTYPE; "
        "target_event public.operation_events%ROWTYPE; "
        "target_play public.play_rows%ROWTYPE;"
    )
    consume = consume.replace(
        "cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; ",
        "cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; " + declarations,
    )
    result["consume_nonplay_undo"] = consume
    return result


def _active_evidence_query():
    """原本/history/既消費play印を有限id参照で結び、view表を新設しない。"""
    before = "e.payload->'calculation'->'request'->'source'"
    native_before = f"{before}->'checkpoint'->'content'->'restored'"
    is_nonplay = (
        "e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1'"
    )
    before = f"(CASE WHEN {is_nonplay} THEN {native_before} ELSE {before} END)"
    value = "e.payload->'calculation'->'response'->'value'"
    context_before = f"""pg_catalog.jsonb_build_object(
 'current',CASE WHEN {is_nonplay} THEN {before}->'current'
 ELSE {before}->'after' END,'rules',{before}->'rules',
 'rulesDigest',{before}->'rulesDigest','layoutDigest',{before}->'layoutDigest',
 'rosterDigest',{before}->'rosterDigest','lineup',{before}->'lineup',
 'participants',{before}->'participants','runners',{before}->'runners',
 'responsibility',{before}->'responsibility','lastPlayEvaluation',
 CASE WHEN {is_nonplay} THEN {before}->'lastPlayEvaluation'
 ELSE {before}->'t2' END)"""
    context_after = f"""pg_catalog.jsonb_build_object(
 'current',{value}->'t1'->'after','rules',{before}->'rules',
 'rulesDigest',{before}->'rulesDigest','layoutDigest',{before}->'layoutDigest',
 'rosterDigest',{value}->'rosterDigest','lineup',{value}->'lineup',
 'participants',{value}->'participants','runners',{value}->'runners',
 'responsibility',{value}->'nextResponsibility','lastPlayEvaluation',{value}->'t2')"""
    source = """pg_catalog.jsonb_build_object('eventId',e.id::text,
 'gameId',e.game_id::text,'generation',a.wire_d4,'d1',e.d1::text,
 'd5',e.d5::text,'fingerprint',l.source_fingerprint,'eventKind','play_input')"""
    ordinary_proof = _saved_evidence_sql("a", history=True)
    first_proof = _saved_evidence_sql("f", history=False)
    ordinary = f"""SELECT h.tenant_id,h.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 CASE WHEN e.payload->>'formatVersion'='first-ball-play-v1' THEN
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1',{first_proof},
 'cursor',pg_catalog.jsonb_build_array(r.issuance_order,e.d1,e.id::text),
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'slot',pg_catalog.to_jsonb(es),'admission',pg_catalog.to_jsonb(f),
 'play',pg_catalog.to_jsonb(pr),'runners',(SELECT COALESCE(
 pg_catalog.jsonb_agg(pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id AND rr.play_id=pr.id))
 ELSE pg_catalog.jsonb_build_object('kind','accepted-ordinary-admission-v1',
 {ordinary_proof},'frame',pg_catalog.jsonb_build_object(
 'play',pg_catalog.jsonb_build_object('source',{source},'playId',pr.id::text,
 'd2',e.d2::text,'physicalPlayNumber',pr.play_number::text),
 'historyEntry',h.entry,'beforeContext',{context_before},'afterContext',{context_after}),
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
"""

    return ordinary + "\nUNION ALL\n" + _first_ball_without_history_query()


def _first_ball_without_history_query():
    """旧firstball原本がhistoryへ未派生でも、raw参照だけをhookへ渡す。"""
    first_proof = _saved_evidence_sql("f", history=False)
    return f"""SELECT c.tenant_id,c.game_id,c.id AS checkpoint_id,
 c.revision AS checkpoint_revision,r.issuance_order,e.d1,e.id AS source_event_id,
 pg_catalog.jsonb_build_object('kind','legacy-first-ball-v1',{first_proof},
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
"""


def _saved_evidence_sql(alias, *, history):
    """保存指紋は再hashせず、immutable受理行と同原取引の消費印へ束縛する。"""
    assert alias in {"a", "f"}
    history_guard = (
        "AND a.source_d1=e.d1 AND a.source_d2=e.d2 "
        "AND h.internal_generation=e.generation AND h.d1=e.d1 AND h.d2=e.d2 "
        "AND h.entry=a.history_entry "
        "AND a.next_checkpoint_content->'projection_snapshot' IS NOT NULL "
        ""
        if history
        else "AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1'"
    )
    return f"""'qualified',COALESCE((
 {alias}.state='consumed' AND {alias}.consumed_at IS NOT NULL
 AND {alias}.tenant_id=e.tenant_id AND {alias}.game_id=e.game_id
 AND {alias}.source_event_id=e.id AND {alias}.internal_generation=e.generation
 AND {alias}.d5=e.d5 AND {alias}.play_row_id=pr.id
 AND {alias}.event_fingerprint=l.source_fingerprint
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
 AND {alias}.xmin::text::numeric=
 pg_catalog.mod({alias}.transaction_id::numeric,4294967296::numeric)
 AND e.xmin={alias}.xmin AND l.xmin={alias}.xmin AND pr.xmin={alias}.xmin
 AND es.xmin={alias}.xmin {history_guard}),false),
 'xmins',pg_catalog.jsonb_build_object('event',e.xmin::text,'ledger',l.xmin::text,
 'slot',es.xmin::text,'admission',{alias}.xmin::text,'play',pr.xmin::text)"""
