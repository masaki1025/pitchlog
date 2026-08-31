-- 候補案 3-2 節の構成を組む
CREATE ROLE tbl_owner  LOGIN PASSWORD 'x';        -- マイグレーション用(テーブル所有者)
CREATE ROLE app_role   LOGIN PASSWORD 'x';        -- アプリ用(RLS に従う)
CREATE ROLE fn_owner_nobypass NOLOGIN;            -- 関数所有(BYPASSRLS なし)
CREATE ROLE fn_owner_bypass   NOLOGIN BYPASSRLS;  -- 関数所有(BYPASSRLS あり)
CREATE ROLE outsider   LOGIN PASSWORD 'x';        -- 無所属

GRANT USAGE ON SCHEMA public TO app_role, outsider, fn_owner_nobypass, fn_owner_bypass;
GRANT CREATE ON SCHEMA public TO tbl_owner;

SET ROLE tbl_owner;
CREATE TABLE play (tenant_id text NOT NULL, note text NOT NULL);
INSERT INTO play VALUES ('A','A-secret'), ('B','B-secret');
ALTER TABLE play ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON play
  USING (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT ON play TO app_role;
RESET ROLE;

\echo '=== 検証1: アプリ用ロールは自テナントのみ(RLS が効く) ==='
SET ROLE app_role;
SELECT set_config('app.tenant_id','A',true);
SELECT 'app_role/A' AS who, count(*) AS visible FROM play;
RESET ROLE;

\echo '=== 検証2: テナント文脈なしなら 0 行(default-deny) ==='
SET ROLE app_role;
SELECT 'app_role/no-context' AS who, count(*) AS visible FROM play;
RESET ROLE;

\echo '=== 検証3: テーブル所有者は RLS をバイパスする(FORCE 前) ==='
SET ROLE tbl_owner;
SELECT 'tbl_owner(FORCE前)' AS who, count(*) AS visible FROM play;
RESET ROLE;

\echo '=== 検証4: FORCE ROW LEVEL SECURITY を掛けると所有者も従う ==='
ALTER TABLE play OWNER TO tbl_owner;
SET ROLE tbl_owner;
ALTER TABLE play FORCE ROW LEVEL SECURITY;
SELECT 'tbl_owner(FORCE後)' AS who, count(*) AS visible FROM play;
RESET ROLE;
