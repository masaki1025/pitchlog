-- ELEMENT-TYPE: schema
-- ELEMENT-ID: management_private

CREATE SCHEMA management_private AUTHORIZATION management_fn_owner;

REVOKE ALL PRIVILEGES ON SCHEMA management_private FROM PUBLIC;
GRANT USAGE ON SCHEMA management_private TO management_caller;
