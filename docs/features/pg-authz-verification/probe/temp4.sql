\pset footer off
CREATE TEMP TABLE play (tenant_id text, note text);
INSERT INTO play VALUES ('X','偽1'),('Y','偽2'),('Z','偽3'),('W','偽4');
GRANT SELECT ON play TO PUBLIC;
\echo '=== 一時表(4 行)を置いた状態で 3 種の関数を呼ぶ。本物は 2 行 ==='
SELECT 'search_path 未設定'                        AS 関数設定, unsafe_fn()        AS 返した行数;
SELECT 'search_path = pg_catalog, public'          AS 関数設定, safe_nopgtemp()    AS 返した行数;
SELECT 'search_path = pg_catalog, public, pg_temp' AS 関数設定, safe_pgtemp_last() AS 返した行数;
