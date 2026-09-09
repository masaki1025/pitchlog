-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:read_control_resources:app_role

-- PostgreSQL 17 の function object に定義される権限は 1 種だけなので、ALL は
-- 資産が指定する権限集合と一致する。
REVOKE ALL PRIVILEGES
    ON FUNCTION authz_private.read_control_resources(
        BIGINT,
        TEXT,
        INTEGER,
        BIGINT
    )
    FROM app_role;
GRANT ALL PRIVILEGES
    ON FUNCTION authz_private.read_control_resources(
        BIGINT,
        TEXT,
        INTEGER,
        BIGINT
    )
    TO app_role;
