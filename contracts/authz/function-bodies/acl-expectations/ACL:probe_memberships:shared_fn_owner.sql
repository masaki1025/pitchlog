-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_memberships:shared_fn_owner

REVOKE ALL PRIVILEGES
    ON TABLE probe_data.probe_memberships FROM shared_fn_owner;
GRANT SELECT ON TABLE probe_data.probe_memberships TO shared_fn_owner;
