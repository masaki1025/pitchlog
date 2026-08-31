\pset footer off
-- 検証A: トランザクション内なら RLS 述語が効く
\echo '=== A. app_role: トランザクション内で set_config → 自テナントのみ ==='
BEGIN;
SET ROLE app_role;
SELECT set_config('app.tenant_id','A',true) \gset
SELECT 'A: app_role/tenant=A' AS case, count(*) AS rows, string_agg(note,',') AS seen FROM play;
COMMIT;

\echo '=== B. 同一トランザクションでも文脈なしなら 0 行(default-deny) ==='
BEGIN;
SET ROLE app_role;
SELECT 'B: app_role/文脈なし' AS case, count(*) AS rows FROM play;
COMMIT;

\echo '=== C. autocommit で set_config を別文にすると効かない(候補案 3-3 の警告) ==='
SET ROLE app_role;
SELECT set_config('app.tenant_id','A',true) \gset
SELECT 'C: autocommit 分離' AS case, count(*) AS rows FROM play;
RESET ROLE;
