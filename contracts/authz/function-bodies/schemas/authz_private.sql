-- ELEMENT-TYPE: schema
-- ELEMENT-ID: authz_private

CREATE SCHEMA authz_private AUTHORIZATION shared_fn_owner;

REVOKE ALL PRIVILEGES ON SCHEMA authz_private FROM PUBLIC;
GRANT USAGE ON SCHEMA authz_private TO app_role;
