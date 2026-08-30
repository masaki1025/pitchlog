\pset footer off
CREATE TEMP TABLE play (tenant_id text, note text);
INSERT INTO play VALUES ('X','偽1'),('Y','偽2'),('Z','偽3'),('W','偽4');
GRANT SELECT ON play TO PUBLIC;
\echo '=== CREATE 権限ゼロのロールが、一時表で SECURITY DEFINER 関数を乗っ取れるか ==='
SELECT has_schema_privilege('app_role','public','CREATE') AS "public への CREATE",
       has_database_privilege('app_role','probe','CREATE') AS "DB への CREATE",
       has_database_privilege('app_role','probe','TEMPORARY') AS "DB への TEMPORARY";
SELECT 'SET search_path なし' AS 関数, unsafe_fn() AS 返した行数, '偽表 4 行 / 本物 2 行' AS 備考;
