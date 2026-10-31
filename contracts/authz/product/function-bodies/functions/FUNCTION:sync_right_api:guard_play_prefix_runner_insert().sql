-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:guard_play_prefix_runner_insert()

CREATE FUNCTION sync_right_api.guard_play_prefix_runner_insert()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $runner$
DECLARE a sync_fence.ordinary_pitch_write_admissions%ROWTYPE; own_xid text;
BEGIN
 IF session_user<>'pitchlog_app' THEN RETURN NEW; END IF;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF current_user<>'pitchlog_sync_right_fn_owner' OR pg_catalog.pg_trigger_depth()<>2
 OR TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'play_runners' OR TG_OP<>'INSERT'
 OR NEW.tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR NEW.import_batch_id IS NOT NULL OR NEW.retired_at IS NOT NULL
 THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;
 SELECT s.* INTO STRICT a FROM sync_fence.ordinary_pitch_write_admissions s
 JOIN sync_fence.writer_bindings b ON (b.tenant_id,b.attempt_id,b.phase_id)=
 (s.tenant_id,s.attempt_id,s.phase_id)
 WHERE s.tenant_id=NEW.tenant_id AND s.play_row_id=NEW.play_id
 AND s.state='evaluated' AND s.consumed_at IS NULL AND s.transaction_id=own_xid
 AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND b.state='open' AND b.transaction_id=own_xid
 AND b.expires_at>pg_catalog.clock_timestamp() AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at
 FOR UPDATE OF s;
 IF a.next_checkpoint_content->>'version' IS DISTINCT FROM '2'
 OR NOT EXISTS(SELECT 1 FROM public.play_rows p WHERE p.tenant_id=NEW.tenant_id
 AND p.id=NEW.play_id AND pg_catalog.to_jsonb(p)=a.expected_play_row)
 OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_array_elements(
 a.next_checkpoint_content->'projection_snapshot'->'play_runners') x
 WHERE x=pg_catalog.to_jsonb(NEW))<>1 THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END;
$runner$;

ALTER FUNCTION sync_right_api.guard_play_prefix_runner_insert() OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.guard_play_prefix_runner_insert() FROM PUBLIC,pitchlog_app;
CREATE TRIGGER trg_play_prefix_runner_10_admit BEFORE INSERT ON public.play_runners FOR EACH ROW EXECUTE FUNCTION sync_right_api.guard_play_prefix_runner_insert();
