-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_groups:app_role

REVOKE ALL PRIVILEGES ON TABLE probe_data.probe_groups FROM app_role;
GRANT SELECT ON TABLE probe_data.probe_groups TO app_role;
