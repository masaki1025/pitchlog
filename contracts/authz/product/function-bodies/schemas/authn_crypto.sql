-- ELEMENT-TYPE: schema
-- ELEMENT-ID: authn_crypto

CREATE SCHEMA IF NOT EXISTS authn_crypto;
ALTER SCHEMA authn_crypto OWNER TO pitchlog_owner;
REVOKE ALL PRIVILEGES ON SCHEMA authn_crypto FROM PUBLIC;
GRANT USAGE ON SCHEMA authn_crypto TO pitchlog_auth_fn_owner;
