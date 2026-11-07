-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence:p3_reject_unfinished_page_progress()

CREATE FUNCTION sync_fence.p3_reject_unfinished_page_progress()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_page_guard$
DECLARE current_state text;
BEGIN
 SELECT p.state INTO STRICT current_state
 FROM sync_fence.p3_projection_page_progress p
 WHERE (p.tenant_id,p.game_id,p.internal_generation,p.capsule_id)=
   (NEW.tenant_id,NEW.game_id,NEW.internal_generation,NEW.capsule_id);
 IF current_state IS DISTINCT FROM 'finalized' THEN
  RAISE EXCEPTION 'P3 page build unfinished' USING ERRCODE='42501';
 END IF;
 RETURN NULL;
END;
$p3_page_guard$;
ALTER FUNCTION sync_fence.p3_reject_unfinished_page_progress() OWNER TO pitchlog_owner;
REVOKE ALL ON FUNCTION sync_fence.p3_reject_unfinished_page_progress() FROM PUBLIC,pitchlog_app,pitchlog_sync_right_fn_owner,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor;