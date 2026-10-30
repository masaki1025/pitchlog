"""通常投球の独立qualification/frame/DB印の閉SQL候補。適用は正式登録側が行う。"""

from pitchlog.authz.sync_right_sql import _ASSERT, _COMMON, _STAMP_COLS

_OWNER = "pitchlog_sync_right_fn_owner"
_REJECT = "RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501';"
_EXTRA = (
    "state",
    "checkpoint_id",
    "checkpoint_revision",
    "checkpoint_digest",
    "prefix_length",
    "frame_id",
    "frame_digest",
    "artifact_sha256",
    "source_event_id",
    "source_d1",
    "source_d2",
    "play_row_id",
    "consumed_at",
    "checkpoint_content",
    "next_checkpoint_content",
    "roster_snapshot",
    "history_entry",
)


def _writer_equal(left="s", right="b"):
    """既writer identity全列の比較を単一の列宣言から描画する。"""
    return " AND ".join(
        f"{left}.{name} IS NOT DISTINCT FROM {right}.{name}"
        for name in _STAMP_COLS.split(",")
    )


PREPARE_IDENTITY = "uuid, uuid, uuid, bytea, uuid, uuid, text"
PREPARE_SQL = f"""CREATE FUNCTION sync_right_api.prepare_ordinary_projection(
{_COMMON},p_preparation_json text)
RETURNS TABLE(prepared boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $ordinary$
DECLARE p jsonb; before_cp jsonb; after_cp jsonb; source_row record;
 stamp sync_fence.ordinary_pitch_write_admissions%ROWTYPE;
 current_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 own_xid text; row_xmin text; previous_d1 bigint;
BEGIN
{_ASSERT}
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF p_preparation_json IS NULL THEN {_REJECT} END IF;
 p:=p_preparation_json::jsonb;
 IF pg_catalog.jsonb_typeof(p) IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(p) k)
 IS DISTINCT FROM ARRAY['artifact_sha256','checkpoint','frame_digest','frame_id',
 'history_entry','next_checkpoint','play_row','roster','source']::text[]
 THEN {_REJECT} END IF;
 before_cp:=p->'checkpoint'; after_cp:=p->'next_checkpoint';
 SELECT s.* INTO STRICT stamp FROM sync_fence.ordinary_pitch_write_admissions s
 JOIN sync_fence.writer_bindings b
 ON (b.tenant_id,b.attempt_id,b.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 JOIN sync_fence.writer_admissions a
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND s.state='right_verified' AND s.transaction_id=own_xid
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND b.transaction_id=own_xid AND a.transaction_id=own_xid AND a.lease_id=b.lease_id
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND {_writer_equal()} FOR UPDATE OF s;
 SELECT e.* INTO STRICT source_row FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.id=(p->'source'->>'id')::uuid AND e.d5=stamp.d5
 AND e.generation=stamp.internal_generation AND e.ledger_kind='accepted'
 AND e.event_kind='play_input' AND NOT e.is_tombstone AND e.d1>0 AND e.d2 IS NOT NULL
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified;
 previous_d1:=source_row.d1-1;
 IF source_row.payload->>'formatVersion' IS DISTINCT FROM 'ordinary-pitch-play-v1'
 OR source_row.payload->'calculation'->>'formatVersion' IS DISTINCT FROM
'ordinary-pitch-calculation-v1'
 OR source_row.payload->'calculation'->>'artifactSha256' IS DISTINCT FROM
p->>'artifact_sha256'
 OR p->'source' IS DISTINCT FROM pg_catalog.jsonb_build_object(
 'id',source_row.id::text,'tenant_id',p_tenant_id::text,'game_id',p_game_id::text,
 'generation',source_row.generation::text,'d1',source_row.d1::text,
 'd2',source_row.d2::text,'d5',source_row.d5::text,
'source_fingerprint',stamp.event_fingerprint,'event_fingerprint',stamp.event_fingerprint)
 OR after_cp->'last_source' IS DISTINCT FROM p->'source'
 OR before_cp->>'state' IS DISTINCT FROM 'current' OR after_cp->>'state' IS
DISTINCT FROM 'current'
 OR before_cp->>'wire_d4' IS DISTINCT FROM stamp.wire_d4 OR after_cp->>'wire_d4'
IS DISTINCT FROM stamp.wire_d4
 OR (before_cp->>'confirmed_watermark')::bigint IS DISTINCT FROM previous_d1
 OR (before_cp->>'applied_watermark')::bigint IS DISTINCT FROM previous_d1
 OR (after_cp->>'confirmed_watermark')::bigint IS DISTINCT FROM source_row.d1
 OR (after_cp->>'applied_watermark')::bigint IS DISTINCT FROM source_row.d1
 OR (before_cp->>'internal_generation')::bigint IS DISTINCT FROM
stamp.internal_generation
 OR (after_cp->>'internal_generation')::bigint IS DISTINCT FROM
stamp.internal_generation
 OR (before_cp->>'recovery_generation')::bigint IS DISTINCT FROM
stamp.recovery_generation
 OR (after_cp->>'recovery_generation')::bigint IS DISTINCT FROM
stamp.recovery_generation
 OR after_cp->>'id' IS DISTINCT FROM before_cp->>'id'
 OR (after_cp->>'revision')::bigint IS DISTINCT FROM
(before_cp->>'revision')::bigint+1
 OR after_cp->>'history_version' IS DISTINCT FROM before_cp->>'history_version'
 OR after_cp->'prefix_ref'->>'generation' IS DISTINCT FROM stamp.wire_d4
 OR before_cp->'prefix_ref'->>'generation' IS DISTINCT FROM stamp.wire_d4
 OR after_cp->'prefix_ref'->>'tenantId' IS DISTINCT FROM p_tenant_id::text
 OR before_cp->'prefix_ref'->>'tenantId' IS DISTINCT FROM p_tenant_id::text
 OR after_cp->'prefix_ref'->>'gameId' IS DISTINCT FROM p_game_id::text
 OR before_cp->'prefix_ref'->>'gameId' IS DISTINCT FROM p_game_id::text
 OR (after_cp->'prefix_ref'->>'length')::bigint IS DISTINCT FROM
(before_cp->'prefix_ref'->>'length')::bigint+1
 OR before_cp->'after' IS DISTINCT FROM
source_row.payload->'calculation'->'request'->'t1'->'before'
 OR before_cp->'rules' IS DISTINCT FROM
source_row.payload->'calculation'->'request'->'rules'
 OR before_cp->'t2' IS DISTINCT FROM
source_row.payload->'calculation'->'request'->'prior'->'t2'
 OR before_cp->'prefix_ref' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'previousPrefixRef'
 OR after_cp->'prefix_ref' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'nextPrefixRef'
 OR after_cp->'after' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'t1'->'after'
 OR after_cp->'rules' IS DISTINCT FROM before_cp->'rules'
 OR after_cp->'t2' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'t2'
 OR p->'history_entry' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'newHistoryEntry'
 OR p->'play_row'->>'source_event_id' IS DISTINCT FROM source_row.id::text
 OR p->'play_row'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'play_row'->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
 OR NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l WHERE l.tenant_id=p_tenant_id
 AND l.d5=stamp.d5 AND l.kind='accepted' AND
l.source_fingerprint=stamp.event_fingerprint
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r WHERE
r.tenant_id=p_tenant_id
 AND r.game_id=p_game_id AND r.generation=stamp.internal_generation AND
r.kind='normal'
 AND r.holder_device=stamp.device_id::text AND r.revoked_at IS NULL AND
r.retired_at IS NULL
 AND r.recovery_generation=stamp.recovery_generation
 AND r.confirmed_watermark=source_row.d1 AND r.applied_prefix=source_row.d1)
 THEN {_REJECT} END IF;
 SELECT c.* INTO current_cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation FOR UPDATE;
 IF FOUND THEN
  IF current_cp.content IS DISTINCT FROM before_cp OR current_cp.roster IS
DISTINCT FROM p->'roster'
  OR current_cp.state IS DISTINCT FROM 'current' OR current_cp.content_digest IS
DISTINCT FROM before_cp->>'content_digest'
  THEN {_REJECT} END IF;
 ELSE
  IF previous_d1 NOT IN (0,1) THEN {_REJECT} END IF;
  IF previous_d1=0 AND EXISTS(SELECT 1 FROM public.operation_events e
   WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.id IS DISTINCT
FROM source_row.id)
   THEN {_REJECT} END IF;
  IF previous_d1=1 AND NOT EXISTS(SELECT 1 FROM public.operation_events e
   JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.source_event_id=e.id
   WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
   AND e.id=(before_cp->'last_source'->>'id')::uuid AND
e.generation=stamp.internal_generation
   AND e.d1=1 AND e.ledger_kind='accepted' AND NOT e.is_tombstone
   AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
   AND e.payload->>'formatVersion'='first-ball-play-v1'
   AND before_cp->'after'=e.payload->'calculation'->'response'->'value'->'t1'->'after'
   AND before_cp->'t2'=e.payload->'calculation'->'response'->'value'->'t2')
   THEN {_REJECT} END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM sync_fence.first_ball_write_admissions f
 WHERE f.tenant_id=p_tenant_id AND f.game_id=p_game_id AND f.d5=stamp.d5
 AND f.state IN ('device_verified','right_verified','consumed')) THEN {_REJECT}
END IF;
 UPDATE sync_fence.ordinary_pitch_write_admissions s SET state='evaluated',
checkpoint_id=(before_cp->>'id')::uuid,checkpoint_revision=(before_cp->>'revision')::bigint,
checkpoint_digest=before_cp->>'content_digest',prefix_length=(before_cp->'prefix_ref'->>'length')::bigint,
frame_id=(p->>'frame_id')::uuid,frame_digest=p->>'frame_digest',artifact_sha256=p->>'artifact_sha256',
 source_event_id=source_row.id,source_d1=source_row.d1,source_d2=source_row.d2,
 play_row_id=(p->'play_row'->>'id')::uuid,checkpoint_content=before_cp,
next_checkpoint_content=after_cp,roster_snapshot=p->'roster',history_entry=p->'history_entry',
 expected_play_row=p->'play_row'
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND s.state='right_verified' AND s.transaction_id=own_xid
 RETURNING s.xmin::text INTO row_xmin;
 IF NOT FOUND OR row_xmin::numeric IS DISTINCT FROM
pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 THEN {_REJECT} END IF;
 RETURN QUERY SELECT true;
END;
$ordinary$;
"""

CONSUME_IDENTITY = "jsonb"
CONSUME_SQL = f"""CREATE FUNCTION
sync_right_api.consume_ordinary_projection(p_row jsonb)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $ordinary$
DECLARE s sync_fence.ordinary_pitch_write_admissions%ROWTYPE;
 own_xid text; row_xmin text; after_cp jsonb; source_row record; bootstrap boolean;
 saved_clock timestamptz;
BEGIN
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT
FROM '{_OWNER}'
 OR pg_catalog.pg_trigger_depth()<>1
 OR p_row->>'tenant_id' IS DISTINCT FROM
NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')
 THEN {_REJECT} END IF;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 saved_clock:=pg_catalog.clock_timestamp();
 SELECT a.* INTO STRICT s FROM sync_fence.ordinary_pitch_write_admissions a
 JOIN sync_fence.writer_bindings b
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(b.tenant_id,b.attempt_id,b.phase_id)
 JOIN sync_fence.writer_admissions wa
 ON (wa.tenant_id,wa.attempt_id,wa.phase_id)=(b.tenant_id,b.attempt_id,b.phase_id)
 WHERE a.tenant_id=(p_row->>'tenant_id')::uuid AND a.game_id=(p_row->>'game_id')::uuid
 AND a.source_event_id=(p_row->>'source_event_id')::uuid AND
a.play_row_id=(p_row->>'id')::uuid
 AND a.state='evaluated' AND a.consumed_at IS NULL AND a.transaction_id=own_xid
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND b.transaction_id=own_xid AND wa.transaction_id=own_xid
 AND wa.lease_id=b.lease_id
 AND wa.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND b.backend_pid=pg_catalog.pg_backend_pid()
 AND b.postmaster_started_at=pg_catalog.pg_postmaster_start_time()
 AND b.database_oid=(SELECT d.oid::text FROM pg_catalog.pg_database d
 WHERE d.datname=pg_catalog.current_database())
 AND {_writer_equal("a", "b")} FOR UPDATE OF a;
 SELECT e.* INTO STRICT source_row FROM public.operation_events e
 WHERE e.tenant_id=s.tenant_id AND e.game_id=s.game_id AND e.id=s.source_event_id
 AND e.generation=s.internal_generation AND e.d1=s.source_d1 AND e.d2=s.source_d2
 AND e.d5=s.d5 AND e.ledger_kind='accepted' AND NOT e.is_tombstone
 AND e.event_kind='play_input'
 AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND e.legacy_row_identifier IS NULL
 AND NOT e.migration_unverified
 AND e.payload->>'formatVersion'='ordinary-pitch-play-v1';
 IF EXISTS(SELECT 1 FROM sync_fence.first_ball_write_admissions f
 WHERE f.tenant_id=s.tenant_id AND f.game_id=s.game_id AND f.d5=s.d5
 AND f.state IN ('device_verified','right_verified','consumed'))
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g WHERE g.singleton_id=1
 AND g.state='open' AND g.recovery_generation=s.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r WHERE
r.tenant_id=s.tenant_id
 AND r.game_id=s.game_id AND r.generation=s.internal_generation AND r.kind='normal'
 AND r.holder_device=s.device_id::text AND r.revoked_at IS NULL AND r.retired_at
IS NULL
 AND r.recovery_generation=s.recovery_generation AND r.confirmed_watermark=s.source_d1
 AND r.applied_prefix=s.source_d1)
 OR NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l
 WHERE l.tenant_id=s.tenant_id AND l.d5=s.d5 AND l.kind='accepted'
 AND l.source_fingerprint=s.event_fingerprint AND l.retired_at IS NULL
 AND l.import_batch_id IS NULL) THEN {_REJECT} END IF;
 PERFORM 1 FROM public.trusted_devices d WHERE d.tenant_id=s.tenant_id
 AND d.device_id=s.device_id AND d.revoked_at IS NULL FOR SHARE;
 IF NOT FOUND THEN {_REJECT} END IF;
 IF s.expected_play_row IS DISTINCT FROM p_row THEN {_REJECT} END IF;
 bootstrap:=NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=s.tenant_id AND c.game_id=s.game_id
 AND c.internal_generation=s.internal_generation);
 after_cp:=s.next_checkpoint_content;
 INSERT INTO
sync_fence.ordinary_pitch_checkpoints(tenant_id,game_id,internal_generation,id,
 revision,history_version,recovery_generation,confirmed_watermark,applied_watermark,
 content_digest,content,roster,state,saved_at)
 VALUES(s.tenant_id,s.game_id,s.internal_generation,s.checkpoint_id,
(after_cp->>'revision')::bigint,(after_cp->>'history_version')::bigint,s.recovery_generation,
s.source_d1,s.source_d1,after_cp->>'content_digest',after_cp,s.roster_snapshot,
'current',saved_clock)
 ON CONFLICT(tenant_id,game_id,internal_generation) DO UPDATE
 SET revision=EXCLUDED.revision,confirmed_watermark=EXCLUDED.confirmed_watermark,
 applied_watermark=EXCLUDED.applied_watermark,content_digest=EXCLUDED.content_digest,
 content=EXCLUDED.content,roster=EXCLUDED.roster,saved_at=EXCLUDED.saved_at
 WHERE ordinary_pitch_checkpoints.id=s.checkpoint_id
 AND ordinary_pitch_checkpoints.revision=s.checkpoint_revision
 AND ordinary_pitch_checkpoints.content_digest=s.checkpoint_digest
 AND ordinary_pitch_checkpoints.content=s.checkpoint_content
 AND ordinary_pitch_checkpoints.state='current';
 IF NOT FOUND THEN {_REJECT} END IF;
 IF bootstrap AND s.source_d1=2 AND s.prefix_length=1 THEN
 INSERT INTO sync_fence.ordinary_pitch_history(tenant_id,game_id,internal_generation,
 history_version,source_event_id,d1,d2,entry)
 SELECT e.tenant_id,e.game_id,e.generation,(after_cp->>'history_version')::bigint,
e.id,e.d1,e.d2,pg_catalog.jsonb_build_object('kind','confirmed-play','difference',e.state_diff)
 FROM public.operation_events e
 WHERE e.tenant_id=s.tenant_id AND e.game_id=s.game_id
 AND e.id=(s.checkpoint_content->'last_source'->>'id')::uuid
 AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1';
 IF NOT FOUND THEN {_REJECT} END IF;
 END IF;
 INSERT INTO sync_fence.ordinary_pitch_history(tenant_id,game_id,internal_generation,
 history_version,source_event_id,d1,d2,entry)
VALUES(s.tenant_id,s.game_id,s.internal_generation,(after_cp->>'history_version')::bigint,
 s.source_event_id,s.source_d1,s.source_d2,s.history_entry);
 UPDATE sync_fence.ordinary_pitch_write_admissions a SET state='consumed',
 consumed_at=saved_clock
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 AND a.transaction_id=own_xid AND a.state='evaluated' AND a.frame_id=s.frame_id
 RETURNING a.xmin::text INTO row_xmin;
 IF NOT FOUND OR row_xmin::numeric IS DISTINCT FROM
pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 THEN {_REJECT} END IF;
END;
$ordinary$;
"""


def candidate_function_bodies():
    """適用せず、独立レビューと正式登録側へ渡す有限2関数。"""
    return {
        "prepare_ordinary_projection": PREPARE_SQL,
        "consume_ordinary_projection": CONSUME_SQL,
    }
