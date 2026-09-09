-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_grants:shared_fn_owner

REVOKE ALL PRIVILEGES
    ON TABLE probe_data.probe_grants FROM shared_fn_owner;
GRANT SELECT ON TABLE probe_data.probe_grants TO shared_fn_owner;
