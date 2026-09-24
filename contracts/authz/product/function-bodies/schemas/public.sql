-- ELEMENT-TYPE: schema
-- ELEMENT-ID: public

ALTER SCHEMA public OWNER TO pg_database_owner;
REVOKE ALL PRIVILEGES ON SCHEMA public
    FROM PUBLIC, pitchlog_app, pitchlog_shared_fn_owner, pitchlog_management_fn_owner;
GRANT USAGE ON SCHEMA public TO pitchlog_app, pitchlog_shared_fn_owner;
