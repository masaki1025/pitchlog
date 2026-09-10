-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_groups:shared_fn_owner

REVOKE ALL PRIVILEGES
    ON TABLE probe_data.probe_groups FROM shared_fn_owner;
GRANT SELECT ON TABLE probe_data.probe_groups TO shared_fn_owner;
