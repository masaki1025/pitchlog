-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_invitations:app_role

REVOKE ALL PRIVILEGES ON TABLE probe_data.probe_invitations FROM app_role;
GRANT SELECT ON TABLE probe_data.probe_invitations TO app_role;
