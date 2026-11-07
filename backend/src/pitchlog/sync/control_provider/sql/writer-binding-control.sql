-- 専用control PG。既F2先頭3表へ固定操作だけを供給し、未知列を加えない。
-- 既存roleは修復しない。両主体の固定属性・両向membership0をGRANT前に確認する。
DO $roles$ DECLARE r record; role_name text; actor boolean;
BEGIN
 FOREACH role_name IN ARRAY ARRAY['pitchlog_sync_binding_fn_owner','pitchlog_sync_binding_actor'] LOOP
  actor:=role_name='pitchlog_sync_binding_actor';
  SELECT * INTO r FROM pg_roles WHERE rolname=role_name;
  IF NOT FOUND THEN
   IF actor THEN CREATE ROLE pitchlog_sync_binding_actor LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION;
   ELSE CREATE ROLE pitchlog_sync_binding_fn_owner NOLOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION; END IF;
  ELSIF r.rolcanlogin IS DISTINCT FROM actor OR r.rolsuper OR r.rolinherit OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication OR r.rolconnlimit<>-1 OR r.rolvaliduntil IS NOT NULL
   OR EXISTS(SELECT FROM pg_auth_members m WHERE m.member=r.oid OR m.roleid=r.oid) THEN RAISE EXCEPTION 'binding control role configuration rejected' USING ERRCODE='42501'; END IF;
 END LOOP;
END;$roles$;
GRANT USAGE ON SCHEMA sync_control TO pitchlog_sync_binding_actor,pitchlog_sync_binding_fn_owner;
REVOKE ALL ON sync_control.authorities,sync_control.attempts,sync_control.event_phases,sync_control.attempt_retirements FROM PUBLIC,pitchlog_sync_binding_actor;
GRANT SELECT ON sync_control.authorities TO pitchlog_sync_binding_fn_owner;
GRANT SELECT,INSERT ON sync_control.attempts,sync_control.event_phases,sync_control.attempt_retirements TO pitchlog_sync_binding_fn_owner;
CREATE POLICY binding_owner ON sync_control.authorities FOR SELECT TO pitchlog_sync_binding_fn_owner USING(true);
CREATE POLICY binding_owner ON sync_control.attempts TO pitchlog_sync_binding_fn_owner USING(true) WITH CHECK(true);
CREATE POLICY binding_owner ON sync_control.event_phases TO pitchlog_sync_binding_fn_owner USING(true) WITH CHECK(true);
CREATE POLICY binding_retirement_read ON sync_control.attempt_retirements FOR SELECT TO pitchlog_sync_binding_fn_owner USING(true);
CREATE POLICY binding_retirement_insert ON sync_control.attempt_retirements FOR INSERT TO pitchlog_sync_binding_fn_owner WITH CHECK(true);

CREATE FUNCTION sync_control.register_first_ball_phase(p_tenant_id uuid,p_context jsonb)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE au sync_control.authorities%ROWTYPE; at sync_control.attempts%ROWTYPE; ph sync_control.event_phases%ROWTYPE;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL OR jsonb_typeof(p_context) IS DISTINCT FROM 'object'
 OR ARRAY(SELECT key FROM jsonb_object_keys(p_context) AS keys(key) WHERE key<>'body_fingerprint' ORDER BY 1) IS DISTINCT FROM ARRAY['attempt_id','authority_id','business_instance','codec_version','control_instance','control_version','d5','device_id','event_fingerprint','game_id','internal_generation','phase_id','request_fingerprint','restore_epoch','wire_d4']::text[] THEN RAISE EXCEPTION 'control phase registration rejected' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext(p_tenant_id::text),hashtext(p_context->>'attempt_id'));
 IF EXISTS(SELECT FROM sync_control.attempt_retirements r WHERE r.tenant_id=p_tenant_id AND r.attempt_id=(p_context->>'attempt_id')::uuid) THEN RAISE EXCEPTION 'attempt retired' USING ERRCODE='42501'; END IF;
 au:=jsonb_populate_record(NULL::sync_control.authorities,p_context); au.state:='active';
 IF NOT EXISTS(SELECT FROM sync_control.authorities a WHERE a=au) THEN RAISE EXCEPTION 'authority conflict' USING ERRCODE='42501'; END IF;
 IF p_context ? 'body_fingerprint' AND (jsonb_typeof(p_context->'body_fingerprint') IS DISTINCT FROM 'string' OR (p_context->>'body_fingerprint') !~ '^[a-f0-9]{64}$') THEN RAISE EXCEPTION 'body fingerprint rejected' USING ERRCODE='42501'; END IF;
 at:=jsonb_populate_record(NULL::sync_control.attempts,p_context); at.tenant_id:=p_tenant_id; at.event_count:=1; at.record_version:=1;
 INSERT INTO sync_control.attempts SELECT at.* ON CONFLICT DO NOTHING;
 IF NOT EXISTS(SELECT FROM sync_control.attempts a WHERE a=at) THEN RAISE EXCEPTION 'attempt conflict' USING ERRCODE='42501'; END IF;
 ph:=jsonb_populate_record(NULL::sync_control.event_phases,p_context); ph.tenant_id:=p_tenant_id; ph.event_position:=1; ph.d1:=1;
 INSERT INTO sync_control.event_phases SELECT ph.* ON CONFLICT DO NOTHING;
 IF NOT EXISTS(SELECT FROM sync_control.event_phases p WHERE p=ph) THEN RAISE EXCEPTION 'phase conflict' USING ERRCODE='42501'; END IF;
END;$f$;
CREATE FUNCTION sync_control.read_first_ball_phase(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid)
RETURNS TABLE(context_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL THEN RAISE EXCEPTION 'control read rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT (CASE WHEN at.body_fingerprint IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('body_fingerprint',at.body_fingerprint) END || jsonb_build_object('authority_id',au.authority_id,'control_instance',au.control_instance,'business_instance',au.business_instance,'restore_epoch',au.restore_epoch,'control_version',au.control_version,'attempt_id',at.attempt_id,'device_id',at.device_id,'game_id',at.game_id,'wire_d4',at.wire_d4,'internal_generation',at.internal_generation,'codec_version',at.codec_version,'request_fingerprint',at.request_fingerprint,'phase_id',ph.phase_id,'d5',ph.d5,'event_fingerprint',ph.event_fingerprint))::text
 FROM sync_control.authorities au JOIN sync_control.attempts at USING(authority_id) JOIN sync_control.event_phases ph USING(tenant_id,attempt_id)
 WHERE au.state='active' AND at.tenant_id=p_tenant_id AND at.attempt_id=p_attempt_id AND ph.phase_id=p_phase_id AND at.event_count=1 AND ph.event_position=1 AND ph.d1=1;
END;$f$;
CREATE FUNCTION sync_control.retire_sync_attempt(p_tenant_id uuid,p_attempt_id uuid,p_device_id uuid,p_game_id uuid,p_wire_d4 text,p_codec_version bigint,p_request_fingerprint text,p_authority_id uuid,p_recovery_generation bigint,p_body_fingerprint text)
RETURNS text LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE observed sync_control.attempts%ROWTYPE; retired sync_control.attempt_retirements%ROWTYPE; expected sync_control.attempt_retirements%ROWTYPE;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_device_id IS NULL OR p_game_id IS NULL OR p_wire_d4 IS NULL OR p_wire_d4='' OR p_codec_version IS NULL OR p_codec_version<=0 OR p_request_fingerprint IS NULL OR p_request_fingerprint='' OR p_authority_id IS NULL OR p_recovery_generation IS NULL OR p_recovery_generation<=0 OR p_body_fingerprint IS NULL OR p_body_fingerprint !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'attempt retirement rejected' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext(p_tenant_id::text),hashtext(p_attempt_id::text));
 IF NOT EXISTS(SELECT FROM sync_control.authorities a WHERE a.authority_id=p_authority_id AND a.state='active') THEN RAISE EXCEPTION 'attempt authority rejected' USING ERRCODE='42501'; END IF;
 SELECT a.* INTO observed FROM sync_control.attempts a WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id;
 IF FOUND AND (observed.device_id IS DISTINCT FROM p_device_id OR observed.game_id IS DISTINCT FROM p_game_id OR observed.authority_id IS DISTINCT FROM p_authority_id OR observed.wire_d4 IS DISTINCT FROM p_wire_d4 OR observed.codec_version IS DISTINCT FROM p_codec_version OR observed.request_fingerprint IS DISTINCT FROM p_request_fingerprint OR observed.event_count IS DISTINCT FROM 1 OR observed.body_fingerprint IS DISTINCT FROM p_body_fingerprint) THEN RAISE EXCEPTION 'attempt identity rejected' USING ERRCODE='42501'; END IF;
 expected.tenant_id:=p_tenant_id; expected.attempt_id:=p_attempt_id; expected.device_id:=p_device_id; expected.game_id:=p_game_id; expected.authority_id:=p_authority_id; expected.wire_d4:=p_wire_d4; expected.codec_version:=p_codec_version; expected.request_fingerprint:=p_request_fingerprint; expected.recovery_generation:=p_recovery_generation; expected.body_fingerprint:=p_body_fingerprint;
 SELECT r.* INTO retired FROM sync_control.attempt_retirements r WHERE r.tenant_id=p_tenant_id AND r.attempt_id=p_attempt_id;
 IF FOUND THEN
  IF retired IS DISTINCT FROM expected THEN RAISE EXCEPTION 'attempt retirement identity rejected' USING ERRCODE='42501'; END IF;
  RETURN 'retired';
 END IF;
 INSERT INTO sync_control.attempt_retirements (tenant_id,attempt_id,device_id,game_id,authority_id,wire_d4,codec_version,request_fingerprint,recovery_generation,body_fingerprint)
 VALUES (expected.tenant_id,expected.attempt_id,expected.device_id,expected.game_id,expected.authority_id,expected.wire_d4,expected.codec_version,expected.request_fingerprint,expected.recovery_generation,expected.body_fingerprint);
 RETURN 'retired';
END;$f$;
ALTER FUNCTION sync_control.register_first_ball_phase(uuid,jsonb) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_control.read_first_ball_phase(uuid,uuid,uuid) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_control.retire_sync_attempt(uuid,uuid,uuid,uuid,text,bigint,text,uuid,bigint,text) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_control.register_first_ball_phase(uuid,jsonb),sync_control.read_first_ball_phase(uuid,uuid,uuid),sync_control.retire_sync_attempt(uuid,uuid,uuid,uuid,text,bigint,text,uuid,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_control.register_first_ball_phase(uuid,jsonb),sync_control.read_first_ball_phase(uuid,uuid,uuid),sync_control.retire_sync_attempt(uuid,uuid,uuid,uuid,text,bigint,text,uuid,bigint,text) TO pitchlog_sync_binding_actor;

CREATE FUNCTION sync_control.read_attempt_recovery_state(p_tenant_id uuid,p_attempt_id uuid,p_device_id uuid,p_game_id uuid,p_wire_d4 text,p_codec_version bigint,p_request_fingerprint text,p_authority_id uuid,p_d5 uuid,p_event_fingerprint text,p_body_fingerprint text)
RETURNS text LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE at sync_control.attempts%ROWTYPE; retired sync_control.attempt_retirements%ROWTYPE;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_device_id IS NULL OR p_game_id IS NULL OR p_wire_d4 IS NULL OR p_wire_d4='' OR p_codec_version IS NULL OR p_codec_version<=0 OR p_request_fingerprint IS NULL OR p_request_fingerprint='' OR p_authority_id IS NULL OR p_d5 IS NULL OR p_event_fingerprint IS NULL OR p_event_fingerprint='' OR p_body_fingerprint IS NULL OR p_body_fingerprint !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'attempt recovery read rejected' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext(p_tenant_id::text),hashtext(p_attempt_id::text));
 IF NOT EXISTS(SELECT FROM sync_control.authorities a WHERE a.authority_id=p_authority_id AND a.state='active') THEN RETURN 'unresolved'; END IF;
 SELECT r.* INTO retired FROM sync_control.attempt_retirements r WHERE r.tenant_id=p_tenant_id AND r.attempt_id=p_attempt_id;
 IF FOUND THEN
  IF retired.device_id IS DISTINCT FROM p_device_id OR retired.game_id IS DISTINCT FROM p_game_id OR retired.authority_id IS DISTINCT FROM p_authority_id OR retired.wire_d4 IS DISTINCT FROM p_wire_d4 OR retired.codec_version IS DISTINCT FROM p_codec_version OR retired.request_fingerprint IS DISTINCT FROM p_request_fingerprint OR retired.body_fingerprint IS DISTINCT FROM p_body_fingerprint THEN RETURN 'unresolved'; END IF;
  RETURN 'matching';
 END IF;
 SELECT a.* INTO at FROM sync_control.attempts a WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id;
 IF NOT FOUND THEN RETURN 'absent'; END IF;
 IF at.device_id IS DISTINCT FROM p_device_id OR at.game_id IS DISTINCT FROM p_game_id OR at.authority_id IS DISTINCT FROM p_authority_id OR at.wire_d4 IS DISTINCT FROM p_wire_d4 OR at.codec_version IS DISTINCT FROM p_codec_version OR at.request_fingerprint IS DISTINCT FROM p_request_fingerprint OR at.body_fingerprint IS DISTINCT FROM p_body_fingerprint OR at.event_count IS DISTINCT FROM 1 THEN RETURN 'unresolved'; END IF;
 IF NOT EXISTS(SELECT FROM sync_control.event_phases ph WHERE ph.tenant_id=p_tenant_id AND ph.attempt_id=p_attempt_id AND ph.event_position=1 AND ph.d1=1 AND ph.d5=p_d5 AND ph.event_fingerprint=p_event_fingerprint) THEN RETURN 'unresolved'; END IF;
 RETURN 'matching';
END;$f$;
ALTER FUNCTION sync_control.read_attempt_recovery_state(uuid,uuid,uuid,uuid,text,bigint,text,uuid,uuid,text,text) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_control.read_attempt_recovery_state(uuid,uuid,uuid,uuid,text,bigint,text,uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_control.read_attempt_recovery_state(uuid,uuid,uuid,uuid,text,bigint,text,uuid,uuid,text,text) TO pitchlog_sync_binding_actor;

-- P3専用の閉D1less phase。旧EventPhaseのd1=1供給とは別関数にする。
CREATE FUNCTION sync_control.register_d1less_phase(p_tenant_id uuid,p_context jsonb)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE au sync_control.authorities%ROWTYPE; at sync_control.attempts%ROWTYPE; ph sync_control.event_phases%ROWTYPE;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL
 OR jsonb_typeof(p_context) IS DISTINCT FROM 'object'
 OR ARRAY(SELECT key FROM jsonb_object_keys(p_context) AS keys(key) WHERE key<>'body_fingerprint' ORDER BY 1) IS DISTINCT FROM ARRAY['attempt_id','authority_id','business_instance','codec_version','control_instance','control_version','d5','device_id','event_fingerprint','game_id','internal_generation','phase_id','phase_kind','request_fingerprint','restore_epoch','wire_d4']::text[]
 OR p_context->>'phase_kind' IS DISTINCT FROM 'd1less'
 THEN RAISE EXCEPTION 'control d1less phase registration rejected' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext(p_tenant_id::text),hashtext(p_context->>'attempt_id'));
 IF EXISTS(SELECT FROM sync_control.attempt_retirements r WHERE r.tenant_id=p_tenant_id AND r.attempt_id=(p_context->>'attempt_id')::uuid) THEN RAISE EXCEPTION 'attempt retired' USING ERRCODE='42501'; END IF;
 IF p_context ? 'body_fingerprint' AND (jsonb_typeof(p_context->'body_fingerprint') IS DISTINCT FROM 'string' OR (p_context->>'body_fingerprint') !~ '^[a-f0-9]{64}$') THEN RAISE EXCEPTION 'body fingerprint rejected' USING ERRCODE='42501'; END IF;
 au:=jsonb_populate_record(NULL::sync_control.authorities,p_context); au.state:='active';
 IF NOT EXISTS(SELECT FROM sync_control.authorities a WHERE a=au) THEN RAISE EXCEPTION 'authority conflict' USING ERRCODE='42501'; END IF;
 at:=jsonb_populate_record(NULL::sync_control.attempts,p_context); at.tenant_id:=p_tenant_id; at.event_count:=1; at.record_version:=1;
 INSERT INTO sync_control.attempts SELECT at.* ON CONFLICT DO NOTHING;
 IF NOT EXISTS(SELECT FROM sync_control.attempts a WHERE a=at) THEN RAISE EXCEPTION 'attempt conflict' USING ERRCODE='42501'; END IF;
 ph:=jsonb_populate_record(NULL::sync_control.event_phases,p_context); ph.tenant_id:=p_tenant_id; ph.event_position:=1; ph.d1:=NULL;
 INSERT INTO sync_control.event_phases SELECT ph.* ON CONFLICT DO NOTHING;
 IF NOT EXISTS(SELECT FROM sync_control.event_phases p WHERE p=ph) THEN RAISE EXCEPTION 'phase conflict' USING ERRCODE='42501'; END IF;
END;$f$;
CREATE FUNCTION sync_control.read_d1less_phase(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid)
RETURNS TABLE(context_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL THEN RAISE EXCEPTION 'control d1less read rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT (CASE WHEN at.body_fingerprint IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('body_fingerprint',at.body_fingerprint) END || jsonb_build_object('authority_id',au.authority_id,'control_instance',au.control_instance,'business_instance',au.business_instance,'restore_epoch',au.restore_epoch,'control_version',au.control_version,'attempt_id',at.attempt_id,'device_id',at.device_id,'game_id',at.game_id,'wire_d4',at.wire_d4,'internal_generation',at.internal_generation,'codec_version',at.codec_version,'request_fingerprint',at.request_fingerprint,'phase_id',ph.phase_id,'d5',ph.d5,'event_fingerprint',ph.event_fingerprint)||jsonb_build_object('phase_kind','d1less'))::text
 FROM sync_control.authorities au JOIN sync_control.attempts at USING(authority_id) JOIN sync_control.event_phases ph USING(tenant_id,attempt_id)
 WHERE au.state='active' AND at.tenant_id=p_tenant_id AND at.attempt_id=p_attempt_id AND ph.phase_id=p_phase_id AND at.event_count=1 AND ph.event_position=1 AND ph.d1 IS NULL;
END;$f$;
ALTER FUNCTION sync_control.register_d1less_phase(uuid,jsonb) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_control.read_d1less_phase(uuid,uuid,uuid) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_control.register_d1less_phase(uuid,jsonb),sync_control.read_d1less_phase(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_control.register_d1less_phase(uuid,jsonb),sync_control.read_d1less_phase(uuid,uuid,uuid) TO pitchlog_sync_binding_actor;
