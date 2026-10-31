-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:guard_first_ball_projection_admission()

CREATE FUNCTION sync_right_api.guard_first_ball_projection_admission()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $stamp$
DECLARE own_xid text; row_xmin text;
 stamp sync_fence.first_ball_write_admissions%ROWTYPE;
 event_row record; binding sync_fence.writer_bindings%ROWTYPE;
 ordinary boolean:=false;
BEGIN
 -- 読取/照合だけをEXCEPTION付き内側blockへ閉じる。この内側はsubtransactionなので
 -- 印への書込とxmin照合は必ず外側(top-level)で行う。
 BEGIN
 IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'play_rows' OR TG_OP<>'INSERT'
 OR TG_WHEN<>'BEFORE' OR TG_LEVEL<>'ROW' OR TG_NARGS<>0
 OR session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR NEW.id IS NULL OR NEW.source_event_id IS NULL OR NEW.game_id IS NULL
 OR NEW.tenant_id IS NULL OR NEW.import_batch_id IS NOT NULL
 OR NEW.legacy_row_identifier IS NOT NULL
 OR NEW.migration_unverified IS DISTINCT FROM false
 OR NEW.tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT e.d5,e.generation,e.d1,e.payload INTO STRICT event_row
 FROM public.operation_events e
 WHERE e.tenant_id=NEW.tenant_id AND e.id=NEW.source_event_id AND e.game_id=NEW.game_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.generation IS NOT NULL AND e.d1>0 AND e.d2 IS NOT NULL
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified;
 ordinary:=event_row.payload->>'formatVersion' IN
 ('ordinary-pitch-play-v1','play-prefix-play-v2');
 IF ordinary IS DISTINCT FROM true THEN
 IF event_row.payload->>'formatVersion' IS DISTINCT FROM 'first-ball-play-v1'
 OR event_row.d1 IS DISTINCT FROM 1
 OR EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_write_admissions o
 WHERE o.tenant_id=NEW.tenant_id AND o.game_id=NEW.game_id AND o.d5=event_row.d5
 AND o.state IN ('device_verified','right_verified','evaluated','consumed')) THEN
 RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 SELECT s.* INTO STRICT stamp FROM sync_fence.first_ball_write_admissions s
 JOIN sync_fence.writer_bindings b
 ON (b.tenant_id,b.attempt_id,b.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 JOIN sync_fence.writer_admissions a
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 WHERE s.tenant_id=NEW.tenant_id AND s.game_id=NEW.game_id AND s.d5=event_row.d5
 AND s.internal_generation=event_row.generation AND s.state='right_verified'
 AND s.source_event_id IS NULL AND s.play_row_id IS NULL AND s.consumed_at IS NULL
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND b.transaction_id=own_xid AND b.backend_pid=pg_catalog.pg_backend_pid()
 AND b.postmaster_started_at=pg_catalog.pg_postmaster_start_time()
 AND b.database_oid=(SELECT d.oid::text FROM pg_catalog.pg_database d
                     WHERE d.datname=pg_catalog.current_database())
 AND a.lease_id=b.lease_id AND a.transaction_id=own_xid
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 -- 全binding不変列の照合。別phase/nonce/世代/instance/hashを合成しない。
 AND (pg_catalog.to_jsonb(s)-'state'-'source_event_id'-'play_row_id'-'consumed_at')
     =(pg_catalog.to_jsonb(b)-'state'-'close_id')
 FOR UPDATE OF s;
 -- 再lockしない。上のadmissionはxmin=own_xidで同top-level TXの既assert由来と
 -- 証明され、そのassertが同じbinding行のFOR SHAREをTX終了まで保持している。
 SELECT b.* INTO STRICT binding FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.attempt_id,b.phase_id)
 =(stamp.tenant_id,stamp.attempt_id,stamp.phase_id);
 -- admissionは実assertでinstance/system/xid/nonceを確認した入口証跡にすぎない。
 -- device/rightの実成功はBで順序付きstampを作り、ここでも現条件を照合する。
 IF NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l
   WHERE l.tenant_id=NEW.tenant_id AND l.d5=event_row.d5 AND l.kind='accepted'
   AND l.source_fingerprint=stamp.event_fingerprint AND l.retired_at IS NULL
   AND l.import_batch_id IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g WHERE g.singleton_id=1
   AND g.state='open' AND g.recovery_generation=stamp.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r
   WHERE r.tenant_id=NEW.tenant_id AND r.game_id=NEW.game_id
   AND r.generation=stamp.internal_generation AND r.kind='normal'
   AND r.holder_device=stamp.device_id::text AND r.revoked_at IS NULL
   AND r.retired_at IS NULL AND r.import_batch_id IS NULL
   AND r.recovery_generation=stamp.recovery_generation)
 THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 -- 同じdevice identityをFOR SHAREで再確認。元credential/proofは保存しない。
 PERFORM 1 FROM public.trusted_devices d WHERE d.tenant_id=NEW.tenant_id
 AND d.device_id=stamp.device_id AND d.revoked_at IS NULL FOR SHARE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 END IF;
 EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END;
 IF event_row.payload->>'formatVersion'='play-prefix-play-v2' THEN
 PERFORM sync_right_api.assert_play_prefix_projection(pg_catalog.to_jsonb(NEW));
 RETURN NEW;
 END IF;
 IF ordinary THEN
 PERFORM sync_right_api.consume_ordinary_projection(pg_catalog.to_jsonb(NEW));
 RETURN NEW;
 END IF;
 -- 外側: subtransactionなしで消費する。0行は固定42501、PKなので複数行はない。
 UPDATE sync_fence.first_ball_write_admissions s
 SET state='consumed',source_event_id=NEW.source_event_id,play_row_id=NEW.id,
     consumed_at=pg_catalog.clock_timestamp()
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)
 =(stamp.tenant_id,stamp.attempt_id,stamp.phase_id)
 AND s.state='right_verified' AND s.lease_id=binding.lease_id
 AND s.transaction_id=own_xid AND s.nonce_digest=binding.nonce_digest
 AND s.event_fingerprint=stamp.event_fingerprint
 AND s.source_event_id IS NULL AND s.play_row_id IS NULL AND s.consumed_at IS NULL
 RETURNING s.xmin::text INTO row_xmin;
 -- 毎回の書込xminでnested consumeを拒否。失敗は同statementのINSERTごとrollback。
 IF NOT FOUND OR row_xmin IS NULL
 OR row_xmin::numeric<>pg_catalog.mod(own_xid::numeric,4294967296::numeric) THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END;
$stamp$;
ALTER FUNCTION sync_right_api.guard_first_ball_projection_admission()
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.guard_first_ball_projection_admission()
 FROM PUBLIC, pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor;
