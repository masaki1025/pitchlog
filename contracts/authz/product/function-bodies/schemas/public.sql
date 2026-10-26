-- ELEMENT-TYPE: schema
-- ELEMENT-ID: public

ALTER SCHEMA public OWNER TO pg_database_owner;
REVOKE ALL PRIVILEGES ON SCHEMA public
    FROM PUBLIC, pitchlog_app, pitchlog_shared_fn_owner, pitchlog_management_fn_owner, pitchlog_auth_fn_owner, pitchlog_rg1_fn_owner, pitchlog_rule_resolution_fn_owner;
GRANT USAGE ON SCHEMA public TO pitchlog_app, pitchlog_shared_fn_owner, pitchlog_auth_fn_owner, pitchlog_rg1_fn_owner, pitchlog_rule_resolution_fn_owner;
GRANT USAGE ON SCHEMA public TO pitchlog_rg1_control_owner;
GRANT USAGE ON SCHEMA public TO pitchlog_initial_fn_owner;
REVOKE CREATE ON SCHEMA public FROM pitchlog_initial_fn_owner;
GRANT USAGE ON SCHEMA public TO pitchlog_initial_actor;
REVOKE CREATE ON SCHEMA public FROM pitchlog_initial_actor;
