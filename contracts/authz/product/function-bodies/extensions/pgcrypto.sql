-- ELEMENT-TYPE: extension
-- ELEMENT-ID: pgcrypto

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA authn_crypto;
DO $authn_extension$
DECLARE
    member_name text;
BEGIN
    FOR member_name IN
        SELECT pg_catalog.format('%I.%I(%s)', namespace.nspname,
                                 routine.proname,
                                 pg_catalog.pg_get_function_identity_arguments(routine.oid))
        FROM pg_catalog.pg_extension AS extension
        JOIN pg_catalog.pg_depend AS dependency
          ON dependency.refobjid = extension.oid
         AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
         AND dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
         AND dependency.deptype = 'e'
        JOIN pg_catalog.pg_proc AS routine ON routine.oid = dependency.objid
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        WHERE extension.extname = 'pgcrypto'
    LOOP
        EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || member_name || ' FROM PUBLIC';
        EXECUTE 'GRANT EXECUTE ON FUNCTION ' || member_name || ' TO pitchlog_auth_fn_owner';
    END LOOP;
END;
$authn_extension$;
