\pset footer off
\echo '=== ④ 所属を与えなければ SET ROLE は拒否されるか ==='
BEGIN;
SET ROLE app_role;
DO $$ BEGIN
  BEGIN
    EXECUTE 'SET ROLE fn_owner_bypass';
    RAISE NOTICE '結果: SET ROLE に成功してしまった(防壁なし)';
  EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE '結果: SET ROLE は拒否された(期待どおり)';
  END;
END $$;
COMMIT;
RESET ROLE;

\echo '=== ⑤ search_path 乗っ取り: 関数が SET search_path を持たない場合 ==='
CREATE FUNCTION unsafe_fn() RETURNS bigint LANGUAGE sql SECURITY DEFINER
  AS 'SELECT count(*) FROM play';
ALTER FUNCTION unsafe_fn() OWNER TO fn_owner_bypass;
GRANT EXECUTE ON FUNCTION unsafe_fn() TO app_role;
GRANT CREATE ON SCHEMA public TO app_role;
BEGIN;
SET ROLE app_role;
CREATE TABLE public.evil_play (tenant_id text, note text);
CREATE SCHEMA IF NOT EXISTS hijack;
CREATE TABLE hijack.play (tenant_id text, note text);
INSERT INTO hijack.play VALUES ('X','偽の行'),('Y','偽の行2'),('Z','偽の行3');
SET search_path = hijack, public;
SELECT 'SET search_path を持たない関数' AS 関数, unsafe_fn() AS 返した行数;
COMMIT;
RESET ROLE;
