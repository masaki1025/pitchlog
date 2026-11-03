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
REVOKE ALL ON sync_control.authorities,sync_control.attempts,sync_control.event_phases FROM PUBLIC,pitchlog_sync_binding_actor;
GRANT SELECT ON sync_control.authorities TO pitchlog_sync_binding_fn_owner;
GRANT SELECT,INSERT ON sync_control.attempts,sync_control.event_phases TO pitchlog_sync_binding_fn_owner;
CREATE POLICY binding_owner ON sync_control.authorities FOR SELECT TO pitchlog_sync_binding_fn_owner USING(true);
CREATE POLICY binding_owner ON sync_control.attempts TO pitchlog_sync_binding_fn_owner USING(true) WITH CHECK(true);
CREATE POLICY binding_owner ON sync_control.event_phases TO pitchlog_sync_binding_fn_owner USING(true) WITH CHECK(true);

CREATE FUNCTION sync_control.register_first_ball_phase(p_tenant_id uuid,p_context jsonb)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE au sync_control.authorities%ROWTYPE; at sync_control.attempts%ROWTYPE; ph sync_control.event_phases%ROWTYPE;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL OR jsonb_typeof(p_context) IS DISTINCT FROM 'object'
 OR ARRAY(SELECT jsonb_object_keys(p_context) ORDER BY 1) IS DISTINCT FROM ARRAY['attempt_id','authority_id','business_instance','codec_version','control_instance','control_version','d5','device_id','event_fingerprint','game_id','internal_generation','phase_id','request_fingerprint','restore_epoch','wire_d4']::text[] THEN RAISE EXCEPTION 'control phase registration rejected' USING ERRCODE='42501'; END IF;
 au:=jsonb_populate_record(NULL::sync_control.authorities,p_context); au.state:='active';
 IF NOT EXISTS(SELECT FROM sync_control.authorities a WHERE a=au) THEN RAISE EXCEPTION 'authority conflict' USING ERRCODE='42501'; END IF;
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
 RETURN QUERY SELECT jsonb_build_object('authority_id',au.authority_id,'control_instance',au.control_instance,'business_instance',au.business_instance,'restore_epoch',au.restore_epoch,'control_version',au.control_version,'attempt_id',at.attempt_id,'device_id',at.device_id,'game_id',at.game_id,'wire_d4',at.wire_d4,'internal_generation',at.internal_generation,'codec_version',at.codec_version,'request_fingerprint',at.request_fingerprint,'phase_id',ph.phase_id,'d5',ph.d5,'event_fingerprint',ph.event_fingerprint)::text
 FROM sync_control.authorities au JOIN sync_control.attempts at USING(authority_id) JOIN sync_control.event_phases ph USING(tenant_id,attempt_id)
 WHERE au.state='active' AND at.tenant_id=p_tenant_id AND at.attempt_id=p_attempt_id AND ph.phase_id=p_phase_id AND at.event_count=1 AND ph.event_position=1 AND ph.d1=1;
END;$f$;
ALTER FUNCTION sync_control.register_first_ball_phase(uuid,jsonb) OWNER TO pitchlog_sync_binding_fn_owner;
ALTER FUNCTION sync_control.read_first_ball_phase(uuid,uuid,uuid) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_control.register_first_ball_phase(uuid,jsonb),sync_control.read_first_ball_phase(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_control.register_first_ball_phase(uuid,jsonb),sync_control.read_first_ball_phase(uuid,uuid,uuid) TO pitchlog_sync_binding_actor;
