-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_management_effects:management_fn_owner

REVOKE ALL PRIVILEGES
    ON TABLE probe_data.probe_management_effects FROM management_fn_owner;
GRANT INSERT
    ON TABLE probe_data.probe_management_effects TO management_fn_owner;
