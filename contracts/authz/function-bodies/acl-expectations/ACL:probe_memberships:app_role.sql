-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_memberships:app_role

REVOKE ALL PRIVILEGES ON TABLE probe_data.probe_memberships FROM app_role;
GRANT SELECT ON TABLE probe_data.probe_memberships TO app_role;
