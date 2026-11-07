-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:protect_pitcher_entry_sources()

CREATE FUNCTION stats_api.protect_pitcher_entry_sources()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_guard$
BEGIN
 RAISE EXCEPTION 'pitcher entry immutable boundary rejected' USING ERRCODE='42501';
END;
$d03_guard$;
CREATE TRIGGER d03_pitcher_entry_immutable
BEFORE UPDATE OR DELETE ON sync_fence.pitcher_entry_sources
FOR EACH ROW EXECUTE FUNCTION stats_api.protect_pitcher_entry_sources();
CREATE TRIGGER d03_pitcher_entry_no_truncate
BEFORE TRUNCATE ON sync_fence.pitcher_entry_sources
FOR EACH STATEMENT EXECUTE FUNCTION stats_api.protect_pitcher_entry_sources();
