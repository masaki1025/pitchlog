-- ELEMENT-TYPE: schema
-- ELEMENT-ID: authz_private

CREATE SCHEMA IF NOT EXISTS authz_private
    AUTHORIZATION pitchlog_shared_fn_owner;
ALTER SCHEMA authz_private OWNER TO pitchlog_shared_fn_owner;
REVOKE ALL PRIVILEGES ON SCHEMA authz_private
    FROM PUBLIC, pitchlog_owner, pitchlog_app, pitchlog_management_fn_owner;
