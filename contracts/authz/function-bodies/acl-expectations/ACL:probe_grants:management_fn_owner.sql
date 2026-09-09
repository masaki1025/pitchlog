-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_grants:management_fn_owner

REVOKE ALL PRIVILEGES
    ON TABLE probe_data.probe_grants FROM management_fn_owner;
GRANT SELECT ON TABLE probe_data.probe_grants TO management_fn_owner;
