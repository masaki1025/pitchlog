-- ELEMENT-TYPE: schema
-- ELEMENT-ID: authn

CREATE SCHEMA IF NOT EXISTS authn;
ALTER SCHEMA authn OWNER TO pitchlog_owner;
REVOKE ALL PRIVILEGES ON SCHEMA authn FROM PUBLIC;
GRANT USAGE ON SCHEMA authn TO pitchlog_app, pitchlog_management_fn_owner, pitchlog_auth_fn_owner;
GRANT USAGE ON SCHEMA authn TO pitchlog_initial_auth_verifier;
REVOKE CREATE ON SCHEMA authn FROM pitchlog_initial_auth_verifier;
