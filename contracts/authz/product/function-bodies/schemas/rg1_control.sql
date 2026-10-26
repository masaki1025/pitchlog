-- ELEMENT-TYPE: schema
-- ELEMENT-ID: rg1_control

CREATE SCHEMA rg1_control AUTHORIZATION pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON SCHEMA rg1_control FROM PUBLIC;
GRANT USAGE ON SCHEMA rg1_control TO pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner, pitchlog_app, pitchlog_initial_actor;
