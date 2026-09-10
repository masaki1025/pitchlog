-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:authorized_shared_rows:app_role

-- PostgreSQL 17 の function object に定義される権限は 1 種だけなので、ALL は
-- 資産が指定する権限集合と一致する。
REVOKE ALL PRIVILEGES
    ON FUNCTION authz_private.authorized_shared_rows(BIGINT, BIGINT[], TEXT)
    FROM app_role;
GRANT ALL PRIVILEGES
    ON FUNCTION authz_private.authorized_shared_rows(BIGINT, BIGINT[], TEXT)
    TO app_role;
