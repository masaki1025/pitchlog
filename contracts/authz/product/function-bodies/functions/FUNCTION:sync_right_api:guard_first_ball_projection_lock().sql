-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:guard_first_ball_projection_lock()

CREATE FUNCTION sync_right_api.guard_first_ball_projection_lock()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $stamp$
DECLARE current_generation bigint;
BEGIN
 IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'play_rows' OR TG_OP<>'INSERT'
 OR TG_WHEN<>'BEFORE' OR TG_LEVEL<>'ROW' OR TG_NARGS<>0
 OR session_user<>'pitchlog_app' OR current_user<>'pitchlog_app'
 OR NEW.tenant_id IS NULL OR NEW.game_id IS NULL OR NEW.source_event_id IS NULL
 OR NEW.tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR NEW.import_batch_id IS NOT NULL OR NEW.legacy_row_identifier IS NOT NULL
 OR NEW.migration_unverified IS DISTINCT FROM false THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 -- 既核と同じgame→current generationの順。資格GUCを設定しない。
 PERFORM 1 FROM public.games g
 WHERE g.tenant_id=NEW.tenant_id AND g.id=NEW.game_id FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 SELECT r.generation INTO STRICT current_generation
 FROM public.recording_generations r WHERE r.tenant_id=NEW.tenant_id
 AND r.game_id=NEW.game_id AND r.kind='normal' AND r.revoked_at IS NULL
 AND r.retired_at IS NULL;
 PERFORM 1 FROM public.recording_generations r
 WHERE r.tenant_id=NEW.tenant_id AND r.game_id=NEW.game_id
 AND r.generation=current_generation AND r.kind='normal'
 AND r.revoked_at IS NULL AND r.retired_at IS NULL FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation THEN
 RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
END;
$stamp$;
ALTER FUNCTION sync_right_api.guard_first_ball_projection_lock()
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.guard_first_ball_projection_lock()
 FROM PUBLIC, pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor;

CREATE TRIGGER trg_first_ball_10_lock BEFORE INSERT ON public.play_rows FOR EACH ROW EXECUTE FUNCTION sync_right_api.guard_first_ball_projection_lock();
CREATE TRIGGER trg_first_ball_20_admit BEFORE INSERT ON public.play_rows FOR EACH ROW EXECUTE FUNCTION sync_right_api.guard_first_ball_projection_admission();
