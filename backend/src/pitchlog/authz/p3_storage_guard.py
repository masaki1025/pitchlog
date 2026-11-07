"""P3ページ保存の未完成commitを拒否する唯一のguard原典。"""

_FUNCTION = "sync_fence.p3_reject_unfinished_page_progress()"


def candidate_statements() -> tuple[str, ...]:
    """固定関数と遅延triggerを返す。配備・成功応答は発行しない。"""
    return (
        """CREATE FUNCTION sync_fence.p3_reject_unfinished_page_progress()
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
$p3_page_guard$;""",
        f"ALTER FUNCTION {_FUNCTION} OWNER TO pitchlog_owner;",
        f"REVOKE ALL ON FUNCTION {_FUNCTION} FROM PUBLIC,pitchlog_app,"
        "pitchlog_sync_right_fn_owner,pitchlog_sync_binding_actor,"
        "pitchlog_rg1_control_actor;",
        """CREATE CONSTRAINT TRIGGER p3_page_progress_must_finalize
AFTER INSERT OR UPDATE ON sync_fence.p3_projection_page_progress
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION sync_fence.p3_reject_unfinished_page_progress();""",
    )
