-- ELEMENT-TYPE: schema
-- ELEMENT-ID: probe_data

CREATE SCHEMA probe_data AUTHORIZATION table_owner;

REVOKE ALL PRIVILEGES ON SCHEMA probe_data FROM PUBLIC;
GRANT USAGE ON SCHEMA probe_data
    TO app_role, shared_fn_owner, management_fn_owner;
