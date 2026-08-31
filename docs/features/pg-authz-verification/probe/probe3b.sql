\pset footer off
GRANT SELECT ON play TO fn_owner_nobypass, fn_owner_bypass;
GRANT EXECUTE ON FUNCTION cross_tenant_nobypass(), cross_tenant_bypass() TO app_role;

\echo '=== 誤り①: SECURITY DEFINER だけでは RLS をバイパスしない ==='
\echo '(app.tenant_id=A の文脈で、テーブルには A/B の 2 行がある)'
BEGIN;
SET ROLE app_role;
SELECT set_config('app.tenant_id','A',true) \gset
SELECT '所有者に BYPASSRLS なし' AS 関数所有者, cross_tenant_nobypass() AS 関数が見た行数;
SELECT '所有者に BYPASSRLS あり' AS 関数所有者, cross_tenant_bypass()   AS 関数が見た行数;
COMMIT;

\echo '=== 誤り②: 新規関数の EXECUTE は既定で PUBLIC に付く ==='
SELECT p.proname AS 関数,
       COALESCE(p.proacl::text,'(既定 = NULL)') AS ACL,
       has_function_privilege('public', p.oid, 'EXECUTE') AS "PUBLIC が実行可"
FROM pg_proc p WHERE p.proname LIKE 'cross_tenant%' ORDER BY 1;

\echo '=== 無所属ロールが実際に越境関数を呼べるか ==='
BEGIN;
SET ROLE outsider;
SELECT 'outsider' AS 実行者, cross_tenant_bypass() AS 見えた行数;
COMMIT;
