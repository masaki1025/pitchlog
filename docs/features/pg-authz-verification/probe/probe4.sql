\pset footer off
\echo '=== ① proacl が NULL でも PUBLIC は実行できる(「権限なし」ではなく「既定」) ==='
CREATE FUNCTION fresh_fn() RETURNS int LANGUAGE sql AS 'SELECT 1';
SELECT proname AS 関数, proacl IS NULL AS "proacl は NULL か",
       has_function_privilege('public', oid, 'EXECUTE') AS "PUBLIC が実行可"
FROM pg_proc WHERE proname = 'fresh_fn';

\echo '=== ② REVOKE で PUBLIC を剥がすと outsider は実行できなくなる ==='
REVOKE ALL ON FUNCTION cross_tenant_bypass() FROM PUBLIC;
SELECT has_function_privilege('public', 'cross_tenant_bypass()', 'EXECUTE') AS "PUBLIC が実行可(REVOKE 後)",
       has_function_privilege('outsider','cross_tenant_bypass()', 'EXECUTE') AS "outsider が実行可",
       has_function_privilege('app_role','cross_tenant_bypass()', 'EXECUTE') AS "app_role が実行可";

\echo '=== ③ NOLOGIN ロールへ SET ROLE で到達できるか(所属を与えた場合) ==='
GRANT fn_owner_bypass TO app_role;
BEGIN;
SET ROLE app_role;
SET ROLE fn_owner_bypass;
SELECT current_user AS "SET ROLE 後の実行者", count(*) AS "直接読めた行数" FROM play;
COMMIT;
REVOKE fn_owner_bypass FROM app_role;

\echo '=== ④ 所属を与えなければ SET ROLE は失敗するか ==='
BEGIN;
SET ROLE app_role;
DO $$ BEGIN
  BEGIN
    EXECUTE 'SET ROLE fn_owner_bypass';
    RAISE NOTICE '結果: SET ROLE に成功してしまった';
  EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE '結果: SET ROLE は拒否された(期待どおり)';
  END;
END $$;
COMMIT;
