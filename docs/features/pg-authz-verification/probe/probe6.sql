\pset footer off
CREATE SCHEMA IF NOT EXISTS hijack;
CREATE TABLE IF NOT EXISTS hijack.play (tenant_id text, note text);
INSERT INTO hijack.play VALUES ('X','偽1'),('Y','偽2'),('Z','偽3');
SET search_path = hijack, public;
SELECT 'SET search_path なし' AS 関数, unsafe_fn() AS 返した行数;
SELECT 'SET search_path あり' AS 関数, cross_tenant_bypass() AS 返した行数;
