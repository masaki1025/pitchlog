\pset footer off
GRANT USAGE ON SCHEMA hijack TO PUBLIC;
GRANT SELECT ON hijack.play TO PUBLIC;
SET search_path = hijack, public;
SELECT 'SET search_path なし(unsafe_fn)' AS 関数, unsafe_fn() AS 返した行数, '偽テーブルは 3 行' AS 備考;
SELECT 'SET search_path あり(cross_tenant_bypass)' AS 関数, cross_tenant_bypass() AS 返した行数, '本物は 2 行' AS 備考;
