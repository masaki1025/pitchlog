-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_management_effects:app_role

REVOKE ALL PRIVILEGES
    ON TABLE probe_data.probe_management_effects FROM app_role;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE probe_data.probe_management_effects TO app_role;
