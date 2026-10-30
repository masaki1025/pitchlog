-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:guard_writer_records()

CREATE FUNCTION sync_fence_api.guard_writer_records()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
 IF TG_TABLE_SCHEMA<>'sync_fence' OR TG_TABLE_NAME NOT IN ('writer_bindings','writer_admissions') OR TG_OP IN ('DELETE','TRUNCATE') OR TG_TABLE_NAME='writer_admissions' THEN
  RAISE EXCEPTION 'writer security original is immutable' USING ERRCODE='42501';
 END IF;
 IF TG_OP<>'UPDATE' OR OLD.state<>'open' OR OLD.close_id IS NOT NULL OR NEW.state<>'closed' OR NEW.close_id IS NULL
 OR (to_jsonb(NEW)-'state'-'close_id') IS DISTINCT FROM (to_jsonb(OLD)-'state'-'close_id') THEN
  RAISE EXCEPTION 'writer security transition rejected' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END;$f$;
ALTER FUNCTION sync_fence_api.guard_writer_records() OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.guard_writer_records() FROM PUBLIC;

CREATE TRIGGER sync_writer_binding_immutable BEFORE UPDATE OR DELETE ON sync_fence.writer_bindings FOR EACH ROW EXECUTE FUNCTION sync_fence_api.guard_writer_records();
CREATE TRIGGER sync_writer_binding_no_truncate BEFORE TRUNCATE ON sync_fence.writer_bindings FOR EACH STATEMENT EXECUTE FUNCTION sync_fence_api.guard_writer_records();
CREATE TRIGGER sync_writer_admission_immutable BEFORE UPDATE OR DELETE ON sync_fence.writer_admissions FOR EACH ROW EXECUTE FUNCTION sync_fence_api.guard_writer_records();
CREATE TRIGGER sync_writer_admission_no_truncate BEFORE TRUNCATE ON sync_fence.writer_admissions FOR EACH STATEMENT EXECUTE FUNCTION sync_fence_api.guard_writer_records();
