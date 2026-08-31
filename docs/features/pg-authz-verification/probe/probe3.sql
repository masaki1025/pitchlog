\pset footer off
-- 越境関数を 2 つ作る: 所有者が BYPASSRLS を持たない版 / 持つ版
CREATE FUNCTION cross_tenant_nobypass() RETURNS bigint
  LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public
  AS 'SELECT count(*) FROM public.play';
ALTER FUNCTION cross_tenant_nobypass() OWNER TO fn_owner_nobypass;

CREATE FUNCTION cross_tenant_bypass() RETURNS bigint
  LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public
  AS 'SELECT count(*) FROM public.play';
ALTER FUNCTION cross_tenant_bypass() OWNER TO fn_owner_bypass;

\echo '=== 誤り①の検証: SECURITY DEFINER だけでは RLS をバイパスしない ==='
BEGIN;
SET ROLE app_role;
SELECT set_config('app.tenant_id','A',true) \gset
SELECT '所有者に BYPASSRLS なし' AS 関数, cross_tenant_nobypass() AS 見える行数;
SELECT '所有者に BYPASSRLS あり' AS 関数, cross_tenant_bypass()   AS 見える行数;
COMMIT;

\echo '=== 誤り②の検証: 新規関数の EXECUTE は既定で PUBLIC に付く ==='
SELECT p.proname AS 関数, p.proacl::text AS ACL,
       has_function_privilege('public', p.oid, 'EXECUTE') AS "PUBLIC が実行可"
FROM pg_proc p WHERE p.proname LIKE 'cross_tenant%' ORDER BY 1;

\echo '=== 無所属ロールから実際に呼べてしまうか ==='
BEGIN;
SET ROLE outsider;
SELECT 'outsider が越境関数を実行' AS case, cross_tenant_bypass() AS 見える行数;
COMMIT;
