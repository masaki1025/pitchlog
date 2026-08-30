\pset footer off
\echo '=== app_role の実接続。CREATE 権限は無いが TEMPORARY はある ==='
CREATE TEMP TABLE play (tenant_id text, note text);
INSERT INTO play VALUES ('X','偽1'),('Y','偽2'),('Z','偽3'),('W','偽4');
\echo '--- 一時表は 4 行。本物は 2 行 ---'
SELECT 'search_path(既定)' AS 状況, current_setting('search_path') AS 値;
SELECT 'SET search_path なしの SECURITY DEFINER 関数' AS 関数, unsafe_fn() AS 返した行数;
