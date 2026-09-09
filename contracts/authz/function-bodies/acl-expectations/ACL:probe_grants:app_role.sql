-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_grants:app_role

REVOKE ALL PRIVILEGES ON TABLE probe_data.probe_grants FROM app_role;
GRANT SELECT ON TABLE probe_data.probe_grants TO app_role;
