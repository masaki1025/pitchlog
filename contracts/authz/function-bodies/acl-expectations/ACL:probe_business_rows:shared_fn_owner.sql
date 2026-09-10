-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_business_rows:shared_fn_owner

REVOKE ALL PRIVILEGES
    ON TABLE probe_data.probe_business_rows FROM shared_fn_owner;
GRANT SELECT ON TABLE probe_data.probe_business_rows TO shared_fn_owner;
