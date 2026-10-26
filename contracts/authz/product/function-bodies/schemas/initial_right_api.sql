-- ELEMENT-TYPE: schema
-- ELEMENT-ID: initial_right_api

CREATE SCHEMA initial_right_api AUTHORIZATION pitchlog_initial_fn_owner;
REVOKE USAGE ON SCHEMA initial_right_api FROM PUBLIC;
REVOKE CREATE ON SCHEMA initial_right_api FROM PUBLIC;
REVOKE USAGE ON SCHEMA initial_right_api FROM pitchlog_app;
REVOKE CREATE ON SCHEMA initial_right_api FROM pitchlog_app;
REVOKE CREATE ON SCHEMA initial_right_api FROM pitchlog_initial_actor;
GRANT USAGE ON SCHEMA initial_right_api TO pitchlog_initial_actor;
