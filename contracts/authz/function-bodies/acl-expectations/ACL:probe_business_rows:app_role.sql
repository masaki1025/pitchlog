-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:probe_business_rows:app_role

REVOKE ALL PRIVILEGES ON TABLE probe_data.probe_business_rows FROM app_role;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE probe_data.probe_business_rows TO app_role;
