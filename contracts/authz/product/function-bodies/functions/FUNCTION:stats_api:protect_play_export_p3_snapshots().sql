-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:protect_play_export_p3_snapshots()

CREATE FUNCTION stats_api.protect_play_export_p3_snapshots()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_csv_guard$
BEGIN
 RAISE EXCEPTION 'P3 CSV snapshot immutable boundary rejected'
 USING ERRCODE='42501';
END;
$p3_csv_guard$;
ALTER FUNCTION stats_api.protect_play_export_p3_snapshots() OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.protect_play_export_p3_snapshots() FROM PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor,pitchlog_initial_fn_owner,pitchlog_sync_binding_fn_owner;
CREATE TRIGGER play_export_p3_immutable
BEFORE UPDATE OR DELETE ON sync_fence.play_export_p3_snapshots
FOR EACH ROW EXECUTE FUNCTION stats_api.protect_play_export_p3_snapshots();
CREATE TRIGGER play_export_p3_no_truncate
BEFORE TRUNCATE ON sync_fence.play_export_p3_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION stats_api.protect_play_export_p3_snapshots();
