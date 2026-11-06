-- N1-U2: 製品migrationが作成するsecurity補助2表にだけ権限を与える。
-- 同版の固定属性・membership0だけを受理し、既存roleを変更しない。
DO $roles$ DECLARE r record; role_name text; actor boolean;
BEGIN
 FOREACH role_name IN ARRAY ARRAY['pitchlog_sync_binding_fn_owner','pitchlog_sync_binding_actor'] LOOP
  actor:=role_name='pitchlog_sync_binding_actor';
  SELECT * INTO r FROM pg_roles WHERE rolname=role_name;
  IF NOT FOUND THEN
   IF actor THEN CREATE ROLE pitchlog_sync_binding_actor LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION;
   ELSE CREATE ROLE pitchlog_sync_binding_fn_owner NOLOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION; END IF;
  ELSIF r.rolcanlogin IS DISTINCT FROM actor OR r.rolsuper OR r.rolinherit OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication OR r.rolconnlimit<>-1 OR r.rolvaliduntil IS NOT NULL
   OR EXISTS(SELECT FROM pg_auth_members m WHERE m.member=r.oid OR m.roleid=r.oid) THEN RAISE EXCEPTION 'binding role configuration rejected' USING ERRCODE='42501'; END IF;
 END LOOP;
 IF EXISTS(SELECT FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='sync_fence_api' AND r.rolname<>'pitchlog_sync_binding_fn_owner') THEN RAISE EXCEPTION 'binding schema owner rejected' USING ERRCODE='42501'; END IF;
END;$roles$;
CREATE SCHEMA IF NOT EXISTS sync_fence_api AUTHORIZATION pitchlog_sync_binding_fn_owner;
REVOKE ALL ON SCHEMA sync_fence,sync_fence_api FROM PUBLIC;
GRANT USAGE ON SCHEMA sync_fence TO pitchlog_sync_binding_fn_owner;
GRANT USAGE ON SCHEMA sync_fence_api TO pitchlog_app,pitchlog_sync_binding_actor;
GRANT SELECT,INSERT ON sync_fence.writer_bindings TO pitchlog_sync_binding_fn_owner;
GRANT UPDATE(state,close_id) ON sync_fence.writer_bindings TO pitchlog_sync_binding_fn_owner;
GRANT SELECT,INSERT ON sync_fence.writer_admissions TO pitchlog_sync_binding_fn_owner;
GRANT SELECT,INSERT ON sync_fence.attempt_retirements TO pitchlog_sync_binding_fn_owner;
GRANT USAGE ON SCHEMA public TO pitchlog_sync_binding_fn_owner;
GRANT SELECT(singleton_id,state,recovery_generation) ON public.rg1_restore_gate TO pitchlog_sync_binding_fn_owner;
GRANT SELECT(tenant_id,d5,source_fingerprint) ON public.idempotency_ledger TO pitchlog_sync_binding_fn_owner;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO pitchlog_sync_binding_fn_owner;
ALTER TABLE sync_fence.writer_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.writer_bindings FORCE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.writer_admissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.writer_admissions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON sync_fence.writer_bindings,sync_fence.writer_admissions,sync_fence.attempt_retirements FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;
CREATE POLICY binding_owner ON sync_fence.writer_bindings TO pitchlog_sync_binding_fn_owner USING(true) WITH CHECK(true);
CREATE POLICY admission_owner ON sync_fence.writer_admissions TO pitchlog_sync_binding_fn_owner USING(true) WITH CHECK(true);
CREATE POLICY attempt_retirement_owner ON sync_fence.attempt_retirements TO pitchlog_sync_binding_fn_owner USING(true) WITH CHECK(true);
CREATE POLICY binding_gate ON public.rg1_restore_gate FOR SELECT TO pitchlog_sync_binding_fn_owner USING(singleton_id=1);
CREATE POLICY binding_d5_read ON public.idempotency_ledger FOR SELECT TO pitchlog_sync_binding_fn_owner USING(true);

-- backend_startはapp自己観測の相関値。権威条件は実instance/PID/full xid8。
CREATE FUNCTION sync_fence_api.read_writer_database_identity(p_tenant_id uuid)
RETURNS TABLE(system_identifier text,database_oid text,postmaster_started_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
 IF session_user<>'pitchlog_app' OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid THEN
  RAISE EXCEPTION 'writer database identity rejected' USING ERRCODE='42501';
 END IF;
 RETURN QUERY SELECT c.system_identifier::text,d.oid::text,pg_postmaster_start_time()
 FROM pg_control_system() c CROSS JOIN pg_database d WHERE d.datname=current_database();
END;$f$;
CREATE FUNCTION sync_fence_api.read_writer_identity(p_tenant_id uuid)
RETURNS TABLE(system_identifier text,database_oid text,postmaster_started_at timestamptz,backend_pid integer,backend_start timestamptz,transaction_id text)
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_app' OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid THEN
  RAISE EXCEPTION 'writer identity rejected' USING ERRCODE='42501';
 END IF;
 RETURN QUERY SELECT c.system_identifier,c.database_oid,c.postmaster_started_at,pg_backend_pid(),a.backend_start,pg_current_xact_id()::text
 FROM sync_fence_api.read_writer_database_identity(p_tenant_id) c CROSS JOIN pg_stat_activity a WHERE a.pid=pg_backend_pid();
END;$f$;

CREATE FUNCTION sync_fence_api.publish_writer_binding(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding jsonb,p_nonce_digest bytea)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE r sync_fence.writer_bindings%ROWTYPE; observed_system text; observed_oid text;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_nonce_digest IS NULL OR octet_length(p_nonce_digest)<>32
 OR jsonb_typeof(p_binding) IS DISTINCT FROM 'object' OR ARRAY(SELECT jsonb_object_keys(p_binding) ORDER BY 1) IS DISTINCT FROM ARRAY['authority_id','backend_pid','backend_start','business_instance','codec_version','control_instance','control_version','d5','database_oid','device_id','event_fingerprint','expires_at','game_id','internal_generation','issuer','lease_id','postmaster_started_at','recovery_generation','request_fingerprint','restore_epoch','system_identifier','transaction_id','wire_d4']::text[] THEN
  RAISE EXCEPTION 'writer publication rejected' USING ERRCODE='42501';
 END IF;
 -- retire と publish は別PGのcontrol registerに依存せず同じ業務鍵で直列化する。
 PERFORM pg_advisory_xact_lock(hashtext(p_tenant_id::text),hashtext(p_attempt_id::text));
 IF EXISTS(SELECT FROM sync_fence.attempt_retirements t WHERE t.tenant_id=p_tenant_id AND t.attempt_id=p_attempt_id) THEN
  RAISE EXCEPTION 'binding attempt retired' USING ERRCODE='42501';
 END IF;
 -- JSONは固定関数の閉じた内部形式。欠損/nullはNOT NULL/有限CHECKでも拒否する。
 r:=jsonb_populate_record(NULL::sync_fence.writer_bindings,p_binding);
 SELECT c.system_identifier::text,d.oid::text INTO STRICT observed_system,observed_oid FROM pg_control_system() c CROSS JOIN pg_database d WHERE d.datname=current_database();
 IF r.system_identifier IS DISTINCT FROM observed_system OR r.database_oid IS DISTINCT FROM observed_oid OR r.postmaster_started_at IS DISTINCT FROM pg_postmaster_start_time()
 OR r.expires_at IS NULL OR r.expires_at<=clock_timestamp() OR r.expires_at>clock_timestamp()+interval '30 seconds'
 OR NOT EXISTS(SELECT FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open' AND g.recovery_generation=r.recovery_generation) THEN
  RAISE EXCEPTION 'writer publication identity rejected' USING ERRCODE='42501';
 END IF;
 r.tenant_id:=p_tenant_id; r.attempt_id:=p_attempt_id; r.phase_id:=p_phase_id; r.nonce_digest:=p_nonce_digest; r.state:='open'; r.close_id:=NULL;
 INSERT INTO sync_fence.writer_bindings SELECT r.*;
END;$f$;

CREATE FUNCTION sync_fence_api.assert_writer_binding(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE r sync_fence.writer_bindings%ROWTYPE; own_xid text; row_xmin text;
BEGIN
 IF session_user<>'pitchlog_app' OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid
 OR p_binding_nonce IS NULL OR octet_length(p_binding_nonce)<>32 THEN
  RAISE EXCEPTION 'writer assertion rejected' USING ERRCODE='42501';
 END IF;
 SELECT b.* INTO STRICT r FROM sync_fence.writer_bindings b WHERE b.tenant_id=p_tenant_id AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id FOR SHARE;
 own_xid:=pg_current_xact_id()::text;
 IF r.state<>'open' OR r.expires_at<=clock_timestamp() OR r.nonce_digest<>sha256(p_binding_nonce)
 OR r.device_id IS DISTINCT FROM p_device_id OR r.game_id IS DISTINCT FROM p_game_id OR r.backend_pid<>pg_backend_pid() OR r.transaction_id<>own_xid
 OR r.postmaster_started_at<>pg_postmaster_start_time()

 OR NOT EXISTS(SELECT FROM pg_control_system() c CROSS JOIN pg_database d WHERE d.datname=current_database() AND c.system_identifier::text=r.system_identifier AND d.oid::text=r.database_oid)
 OR NOT EXISTS(SELECT FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open' AND g.recovery_generation=r.recovery_generation) THEN
  RAISE EXCEPTION 'writer binding rejected' USING ERRCODE='42501';
 END IF;
 INSERT INTO sync_fence.writer_admissions(tenant_id,attempt_id,phase_id,lease_id,transaction_id)
 VALUES(p_tenant_id,p_attempt_id,p_phase_id,r.lease_id,own_xid) ON CONFLICT DO NOTHING;
 SELECT a.xmin::text INTO STRICT row_xmin FROM sync_fence.writer_admissions a WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id AND a.phase_id=p_phase_id AND a.lease_id=r.lease_id AND a.transaction_id=own_xid;
 -- xid8は十進numericで扱う。INSERTがsubxidで起きた初回savepoint進入を拒否する。
 IF row_xmin::numeric<>mod(own_xid::numeric,4294967296::numeric) THEN
  RAISE EXCEPTION 'writer admission requires top-level transaction' USING ERRCODE='42501';
 END IF;
END;$f$;

CREATE FUNCTION sync_fence_api.close_writer_binding(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_lease_id uuid,p_close_id uuid)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE r sync_fence.writer_bindings%ROWTYPE;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_close_id IS NULL THEN RAISE EXCEPTION 'writer close rejected' USING ERRCODE='42501'; END IF;
 SELECT b.* INTO STRICT r FROM sync_fence.writer_bindings b WHERE b.tenant_id=p_tenant_id AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id AND b.lease_id=p_lease_id FOR UPDATE;
 IF r.state='closed' THEN
  IF r.close_id IS DISTINCT FROM p_close_id THEN RAISE EXCEPTION 'writer close identity rejected' USING ERRCODE='42501'; END IF;
  RETURN;
 END IF;
 UPDATE sync_fence.writer_bindings b SET state='closed',close_id=p_close_id WHERE b.tenant_id=p_tenant_id AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id;
END;$f$;

CREATE FUNCTION sync_fence_api.observe_writer_binding(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_lease_id uuid,p_close_id uuid)
RETURNS TABLE(outcome text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE r sync_fence.writer_bindings%ROWTYPE; admission_count bigint; matching_count bigint; xid_status text;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'writer observation rejected' USING ERRCODE='42501'; END IF;
 SELECT b.* INTO STRICT r FROM sync_fence.writer_bindings b WHERE b.tenant_id=p_tenant_id AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id AND b.lease_id=p_lease_id;
 IF r.state<>'closed' OR r.close_id IS DISTINCT FROM p_close_id OR r.postmaster_started_at<>pg_postmaster_start_time()
 OR NOT EXISTS(SELECT FROM pg_control_system() c CROSS JOIN pg_database d WHERE d.datname=current_database() AND c.system_identifier::text=r.system_identifier AND d.oid::text=r.database_oid)
 OR NOT EXISTS(SELECT FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open' AND g.recovery_generation=r.recovery_generation) THEN RETURN QUERY SELECT 'UNKNOWN'::text; RETURN; END IF;
 SELECT count(*),count(*) FILTER(WHERE a.lease_id=r.lease_id AND a.transaction_id=r.transaction_id) INTO admission_count,matching_count FROM sync_fence.writer_admissions a WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id AND a.phase_id=p_phase_id;
 -- statusは保存済み実xidだけを照会する。caller提供の任意xid照会口を作らない。
 xid_status:=pg_xact_status(r.transaction_id::xid8);
 RETURN QUERY SELECT CASE WHEN admission_count=1 AND matching_count=1 AND (xid_status IS NULL OR xid_status='committed') THEN 'COMMITTED'
 WHEN admission_count=0 AND xid_status='aborted' THEN 'ROLLBACK_CONFIRMED'
 WHEN admission_count=0 AND xid_status IN ('in progress','committed') THEN 'ENTRY_CLOSED_UNADMITTED' ELSE 'UNKNOWN' END;
END;$f$;

-- 旧attemptの実TX終結と別にD5確定原本を照合する。結果本文は外へ渡さない。
CREATE FUNCTION sync_fence_api.read_attempt_d5(p_tenant_id uuid,p_d5 uuid,p_event_fingerprint text)
RETURNS text LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE stored_fingerprint text;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL OR p_d5 IS NULL OR p_event_fingerprint IS NULL OR p_event_fingerprint='' OR current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'attempt D5 observation rejected' USING ERRCODE='42501'; END IF;
 SELECT l.source_fingerprint INTO stored_fingerprint FROM public.idempotency_ledger l WHERE l.tenant_id=p_tenant_id AND l.d5=p_d5;
 IF NOT FOUND THEN RETURN 'absent'; END IF;
 IF stored_fingerprint IS DISTINCT FROM p_event_fingerprint THEN RETURN 'conflict'; END IF;
 RETURN 'matching';
END;$f$;

-- publishと同じ業務鍵で遮断し、旧bindingの全実xid終結をSQL側でも要求する。
CREATE FUNCTION sync_fence_api.retire_sync_attempt(p_tenant_id uuid,p_attempt_id uuid,p_device_id uuid,p_game_id uuid,p_d5 uuid,p_wire_d4 text,p_codec_version bigint,p_request_fingerprint text,p_event_fingerprint text,p_authority_id uuid,p_recovery_generation bigint)
RETURNS text LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE b sync_fence.writer_bindings%ROWTYPE; existing sync_fence.attempt_retirements%ROWTYPE; observed text;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR current_setting('transaction_isolation')<>'read committed'
 OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_device_id IS NULL OR p_game_id IS NULL OR p_d5 IS NULL
 OR p_wire_d4 IS NULL OR p_wire_d4='' OR p_codec_version IS NULL OR p_codec_version<=0
 OR p_request_fingerprint IS NULL OR p_request_fingerprint='' OR p_event_fingerprint IS NULL OR p_event_fingerprint='' OR p_authority_id IS NULL
 OR p_recovery_generation IS NULL OR p_recovery_generation<=0 THEN
  RAISE EXCEPTION 'attempt retirement rejected' USING ERRCODE='42501';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtext(p_tenant_id::text),hashtext(p_attempt_id::text));
 IF NOT EXISTS(SELECT FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open' AND g.recovery_generation=p_recovery_generation) THEN
  RETURN 'unresolved';
 END IF;
 FOR b IN SELECT w.* FROM sync_fence.writer_bindings w WHERE w.tenant_id=p_tenant_id AND w.attempt_id=p_attempt_id LOOP
  IF b.device_id IS DISTINCT FROM p_device_id OR b.game_id IS DISTINCT FROM p_game_id OR b.d5 IS DISTINCT FROM p_d5
  OR b.wire_d4 IS DISTINCT FROM p_wire_d4 OR b.codec_version IS DISTINCT FROM p_codec_version
  OR b.request_fingerprint IS DISTINCT FROM p_request_fingerprint OR b.event_fingerprint IS DISTINCT FROM p_event_fingerprint
  OR b.authority_id IS DISTINCT FROM p_authority_id OR b.issuer IS DISTINCT FROM p_authority_id
  OR b.recovery_generation IS DISTINCT FROM p_recovery_generation OR b.state<>'closed' OR b.close_id IS NULL THEN
   RETURN 'unresolved';
  END IF;
  SELECT o.outcome INTO observed FROM sync_fence_api.observe_writer_binding(p_tenant_id,p_attempt_id,b.phase_id,b.lease_id,b.close_id) o;
  IF observed NOT IN ('COMMITTED','ROLLBACK_CONFIRMED') OR observed IS NULL THEN RETURN 'unresolved'; END IF;
 END LOOP;
 SELECT t.* INTO existing FROM sync_fence.attempt_retirements t WHERE t.tenant_id=p_tenant_id AND t.attempt_id=p_attempt_id;
 IF FOUND THEN
  IF existing.device_id IS DISTINCT FROM p_device_id OR existing.game_id IS DISTINCT FROM p_game_id OR existing.d5 IS DISTINCT FROM p_d5
  OR existing.wire_d4 IS DISTINCT FROM p_wire_d4 OR existing.codec_version IS DISTINCT FROM p_codec_version
  OR existing.request_fingerprint IS DISTINCT FROM p_request_fingerprint OR existing.event_fingerprint IS DISTINCT FROM p_event_fingerprint
  OR existing.authority_id IS DISTINCT FROM p_authority_id
  OR existing.recovery_generation IS DISTINCT FROM p_recovery_generation THEN
   RAISE EXCEPTION 'attempt retirement identity rejected' USING ERRCODE='42501';
  END IF;
  RETURN 'retired';
 END IF;
 INSERT INTO sync_fence.attempt_retirements
 (tenant_id,attempt_id,device_id,game_id,d5,authority_id,wire_d4,codec_version,request_fingerprint,event_fingerprint,recovery_generation)
 VALUES (p_tenant_id,p_attempt_id,p_device_id,p_game_id,p_d5,p_authority_id,p_wire_d4,p_codec_version,p_request_fingerprint,p_event_fingerprint,p_recovery_generation);
 RETURN 'retired';
END;$f$;

-- 私有guard。呼出可能な業務APIにせず、旧値→一回closeだけを許す。
CREATE FUNCTION sync_fence_api.guard_writer_records()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
 IF TG_TABLE_SCHEMA<>'sync_fence' OR TG_TABLE_NAME NOT IN ('writer_bindings','writer_admissions','attempt_retirements') OR TG_OP IN ('DELETE','TRUNCATE') OR TG_TABLE_NAME IN ('writer_admissions','attempt_retirements') THEN
  RAISE EXCEPTION 'writer security original is immutable' USING ERRCODE='42501';
 END IF;
 IF TG_OP<>'UPDATE' OR OLD.state<>'open' OR OLD.close_id IS NOT NULL OR NEW.state<>'closed' OR NEW.close_id IS NULL
 OR (to_jsonb(NEW)-'state'-'close_id') IS DISTINCT FROM (to_jsonb(OLD)-'state'-'close_id') THEN
  RAISE EXCEPTION 'writer security transition rejected' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END;$f$;
ALTER FUNCTION sync_fence_api.guard_writer_records() OWNER TO pitchlog_sync_binding_fn_owner;
CREATE TRIGGER sync_writer_binding_immutable BEFORE UPDATE OR DELETE ON sync_fence.writer_bindings FOR EACH ROW EXECUTE FUNCTION sync_fence_api.guard_writer_records();
CREATE TRIGGER sync_writer_binding_no_truncate BEFORE TRUNCATE ON sync_fence.writer_bindings FOR EACH STATEMENT EXECUTE FUNCTION sync_fence_api.guard_writer_records();
CREATE TRIGGER sync_writer_admission_immutable BEFORE UPDATE OR DELETE ON sync_fence.writer_admissions FOR EACH ROW EXECUTE FUNCTION sync_fence_api.guard_writer_records();
CREATE TRIGGER sync_writer_admission_no_truncate BEFORE TRUNCATE ON sync_fence.writer_admissions FOR EACH STATEMENT EXECUTE FUNCTION sync_fence_api.guard_writer_records();
CREATE TRIGGER sync_attempt_retirement_immutable BEFORE UPDATE OR DELETE ON sync_fence.attempt_retirements FOR EACH ROW EXECUTE FUNCTION sync_fence_api.guard_writer_records();
CREATE TRIGGER sync_attempt_retirement_no_truncate BEFORE TRUNCATE ON sync_fence.attempt_retirements FOR EACH STATEMENT EXECUTE FUNCTION sync_fence_api.guard_writer_records();
ALTER FUNCTION sync_fence_api.read_writer_database_identity(uuid) OWNER TO pitchlog_sync_binding_fn_owner;

ALTER FUNCTION sync_fence_api.read_writer_identity(uuid) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_fence_api.publish_writer_binding(uuid,uuid,uuid,jsonb,bytea) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_fence_api.assert_writer_binding(uuid,uuid,uuid,bytea,uuid,uuid) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_fence_api.close_writer_binding(uuid,uuid,uuid,uuid,uuid) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_fence_api.observe_writer_binding(uuid,uuid,uuid,uuid,uuid) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_fence_api.read_attempt_d5(uuid,uuid,text) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_fence_api.retire_sync_attempt(uuid,uuid,uuid,uuid,uuid,text,bigint,text,text,uuid,bigint) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sync_fence_api FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_fence_api.read_writer_database_identity(uuid),sync_fence_api.read_writer_identity(uuid),sync_fence_api.assert_writer_binding(uuid,uuid,uuid,bytea,uuid,uuid) TO pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_fence_api.publish_writer_binding(uuid,uuid,uuid,jsonb,bytea),sync_fence_api.close_writer_binding(uuid,uuid,uuid,uuid,uuid),sync_fence_api.observe_writer_binding(uuid,uuid,uuid,uuid,uuid),sync_fence_api.read_attempt_d5(uuid,uuid,text),sync_fence_api.retire_sync_attempt(uuid,uuid,uuid,uuid,uuid,text,bigint,text,text,uuid,bigint) TO pitchlog_sync_binding_actor;
