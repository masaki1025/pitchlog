-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:apply_representative_grant_change:management_caller

-- PostgreSQL 17 の function object に定義される権限は 1 種だけなので、ALL は
-- 資産が指定する権限集合と一致する。
REVOKE ALL PRIVILEGES
    ON FUNCTION management_private.apply_representative_grant_change(
        BIGINT,
        BIGINT,
        TEXT
    )
    FROM management_caller;
GRANT ALL PRIVILEGES
    ON FUNCTION management_private.apply_representative_grant_change(
        BIGINT,
        BIGINT,
        TEXT
    )
    TO management_caller;
