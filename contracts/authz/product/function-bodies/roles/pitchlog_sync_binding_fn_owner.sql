-- ELEMENT-TYPE: role
-- ELEMENT-ID: pitchlog_sync_binding_fn_owner

DO $authz$
BEGIN
 IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='pitchlog_sync_binding_fn_owner') THEN
  IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname='pitchlog_sync_binding_fn_owner'
   AND r.rolcanlogin IS FALSE AND NOT r.rolsuper AND NOT r.rolbypassrls AND NOT r.rolinherit
   AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT r.rolreplication
   AND r.rolconnlimit=-1 AND r.rolvaliduntil IS NULL
   AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.roleid=r.oid OR m.member=r.oid)) THEN
    RAISE EXCEPTION 'sync role collision: pitchlog_sync_binding_fn_owner';
  END IF;
 ELSE
  CREATE ROLE pitchlog_sync_binding_fn_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION;
 END IF;
END;$authz$;
