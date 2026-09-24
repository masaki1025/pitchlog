-- ELEMENT-TYPE: predicate
-- ELEMENT-ID: PREDICATE:TENANT

-- PostgreSQLに独立した述語オブジェクトはないため、各ポリシーへ展開する。
-- TENANT(c) = COALESCE({column} = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE)
