-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_invitations:shared_fn_owner

REVOKE ALL PRIVILEGES
    ON TABLE probe_data.probe_invitations FROM shared_fn_owner;
GRANT SELECT ON TABLE probe_data.probe_invitations TO shared_fn_owner;
