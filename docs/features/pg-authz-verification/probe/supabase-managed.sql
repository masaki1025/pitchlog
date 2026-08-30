-- Supabase(マネージド環境)での認可構成の実機検証 — 2026-08-31 実行
--
-- 実行者: 人間(山田正輝)。Claude は手順のみ設計し、接続情報は受け取っていない(NFR-014)。
-- 環境: 使い捨ての Supabase プロジェクト。Data API / 新規表の自動公開 / 自動 RLS をすべて OFF で作成。
-- 検証後にプロジェクトごと削除する。
--
-- 実行上の制約(実測): Supabase の SQL エディタの文分割はドル引用符を解さない。
--   DO ブロックは unterminated dollar-quoted string で落ちる。
--   コメント中のアポストロフィも分割を壊す。したがって全文を平文 SQL で書く。
--
-- 結果は research.md 1-7 節が正。以下は各 Run の末尾コメントに実測値を併記する。

-- ============================================================
-- Run 0: 前提条件 — postgres の属性と BYPASSRLS ロールの作成可否
-- ============================================================
SELECT rolname, rolsuper, rolcreaterole, rolbypassrls
FROM pg_roles WHERE rolname = 'postgres';
-- 実測: postgres | false | true | true
--   → Supabase の postgres は superuser ではないが rolbypassrls を持つ。
--     PostgreSQL は BYPASSRLS の付与に superuser ではなく付与側が同属性を持つことを要求するため、
--     CREATE ROLE ... BYPASSRLS が許される。

CREATE ROLE probe_fn_owner_bypass NOLOGIN BYPASSRLS;
-- 実測: 成功。候補案の構成が成立する前提条件は満たされている。

-- ============================================================
-- Run 1: CREATE ROLE 直後のロール所属 — 恒久的な到達経路の有無
-- ============================================================
SELECT r.rolname, mm.rolname AS member, g.rolname AS grantor,
       am.admin_option, am.inherit_option, am.set_option
FROM pg_auth_members am
JOIN pg_roles r  ON r.oid  = am.roleid
JOIN pg_roles mm ON mm.oid = am.member
JOIN pg_roles g  ON g.oid  = am.grantor
WHERE r.rolname = 'probe_fn_owner_bypass';
-- 実測: probe_fn_owner_bypass | postgres | supabase_admin | true | false | false
--   → Supabase は作成者へ自動的に所属を与えるが、set=false / inherit=false。
--     postgres は既定では SET ROLE できず権限も継承しない = 常時開いた到達経路は存在しない。
--     ただし admin=true なので postgres の資格情報を持つ者はいつでも経路を開ける(RES-01)。

-- ============================================================
-- Run A: 一時的な所属の付与(所有させる操作の前に必要)
-- ============================================================
DROP SCHEMA IF EXISTS probe_authz CASCADE;
DROP SCHEMA IF EXISTS probe_fnspace CASCADE;
DROP ROLE IF EXISTS probe_app;

GRANT probe_fn_owner_bypass TO postgres WITH SET TRUE;
SELECT pg_has_role('postgres','probe_fn_owner_bypass','SET') AS can_set_now;
-- 実測: can_set_now = true
--   注: この GRANT を後回しにすると Run B の CREATE SCHEMA ... AUTHORIZATION が
--       ERROR: 42501: must be able to SET ROLE で落ちる(実測済み)。順序が本質。

-- ============================================================
-- Run B: 構成の作成(RLS + FORCE RLS + POLICY / 関数用スキーマ)
-- ============================================================
CREATE ROLE probe_app NOLOGIN;
CREATE SCHEMA probe_authz;
CREATE TABLE probe_authz.t (tenant_id text NOT NULL, note text NOT NULL);
INSERT INTO probe_authz.t VALUES ('A','a'), ('B','b');
ALTER TABLE probe_authz.t ENABLE ROW LEVEL SECURITY;
ALTER TABLE probe_authz.t FORCE ROW LEVEL SECURITY;
CREATE POLICY p ON probe_authz.t USING (tenant_id = current_setting('app.tenant_id', true));
GRANT USAGE ON SCHEMA probe_authz TO probe_app, probe_fn_owner_bypass;
GRANT SELECT ON probe_authz.t TO probe_app, probe_fn_owner_bypass;
CREATE SCHEMA probe_fnspace AUTHORIZATION probe_fn_owner_bypass;
GRANT USAGE ON SCHEMA probe_fnspace TO probe_app;
-- 実測: 成功。
--   注: CREATE SCHEMA ... AUTHORIZATION は Run A の所属付与が前提。
--       また ALTER FUNCTION ... OWNER TO は新所有者が当該スキーマへ CREATE 権限を持つことも要求するため、
--       関数を probe_fn_owner_bypass が所有するスキーマに置いている。

-- ============================================================
-- Run C: SECURITY DEFINER 関数(1 行で書く — 文分割対策)
-- ============================================================
CREATE FUNCTION probe_fnspace.f() RETURNS bigint LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, probe_authz, pg_temp AS 'SELECT count(*) FROM probe_authz.t';
-- 実測: 成功。
--   注: search_path の末尾に pg_temp を明示している(research.md 1-4-A — pg_temp 乗っ取り対策)。

-- ============================================================
-- Run D: 所有者変更と ACL
-- ============================================================
ALTER FUNCTION probe_fnspace.f() OWNER TO probe_fn_owner_bypass;
REVOKE ALL ON FUNCTION probe_fnspace.f() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION probe_fnspace.f() TO probe_app;
SELECT has_function_privilege('public','probe_fnspace.f()','EXECUTE')    AS public_exec,
       has_function_privilege('probe_app','probe_fnspace.f()','EXECUTE') AS app_exec;
-- 実測: public_exec = false / app_exec = true
--   → REVOKE ALL FROM PUBLIC が効き、限定 GRANT だけが残る。

-- ============================================================
-- Run E: 一時的な所属を剥がす — 到達経路が閉じるか(本命)
-- ============================================================
REVOKE probe_fn_owner_bypass FROM postgres;
SELECT pg_has_role('postgres','probe_fn_owner_bypass','SET')   AS can_set_after,
       pg_has_role('postgres','probe_fn_owner_bypass','USAGE') AS can_inherit_after;
-- 実測: can_set_after = false / can_inherit_after = false
--   → 一時的に開けて、閉じられる。この検査は製品のカタログ検査に必須項目として入れる(RES-02)。

-- ============================================================
-- Run F: 挙動の確認 — 関数だけが越境できるか
-- ============================================================
GRANT probe_app TO postgres WITH SET TRUE;
BEGIN;
SET LOCAL ROLE probe_app;
SELECT set_config('app.tenant_id','A',true);
SELECT probe_fnspace.f() AS via_function,
       (SELECT count(*) FROM probe_authz.t) AS direct_read;
COMMIT;
-- 実測: via_function = 2 / direct_read = 1
--   → 同一トランザクション・同一ロールで、関数経由なら全行・直読みなら自テナント 1 行。
--     「関数だけが越境できる」という設計の中核が Supabase 上でも成立する。
--     FORCE RLS 下でも関数所有者の BYPASSRLS が効いている。

-- ============================================================
-- 後始末
-- ============================================================
-- 使い捨てプロジェクトごと削除するのが確実。個別に戻す場合は下記。
-- REVOKE probe_app FROM postgres;
-- DROP SCHEMA IF EXISTS probe_fnspace CASCADE;
-- DROP SCHEMA IF EXISTS probe_authz CASCADE;
-- DROP ROLE IF EXISTS probe_app;
-- DROP ROLE IF EXISTS probe_fn_owner_bypass;
