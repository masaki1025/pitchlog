-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:recording_vocab_api:read_batted_ball_options(uuid, integer, text)

CREATE FUNCTION recording_vocab_api.read_batted_ball_options(
  p_tenant_id uuid, p_page_size integer, p_cursor_key text
) RETURNS TABLE(key text, display_name text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
BEGIN
  IF session_user <> 'pitchlog_app'
     OR current_user <> 'pitchlog_recording_vocab_fn_owner'
     OR p_tenant_id IS NULL
     OR pg_catalog.current_setting('app.tenant_id', true)
        IS DISTINCT FROM p_tenant_id::text THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'recording vocabulary scope mismatch';
  END IF;
  IF p_page_size IS NULL OR p_page_size < 1 OR p_page_size > 100 OR p_cursor_key IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'recording vocabulary page invalid';
  END IF;
  IF p_cursor_key = '' THEN
    RETURN QUERY
      SELECT v.key, v.display_name
      FROM public.admin_vocabularies AS v
      WHERE v.category = 'batted_ball' AND v.disabled = false
      ORDER BY v.key COLLATE "C"
      LIMIT p_page_size + 1;
  ELSE
    RETURN QUERY
      SELECT v.key, v.display_name
      FROM public.admin_vocabularies AS v
      WHERE v.category = 'batted_ball' AND v.disabled = false
        AND v.key COLLATE "C" > p_cursor_key COLLATE "C"
      ORDER BY v.key COLLATE "C"
      LIMIT p_page_size + 1;
  END IF;
END;
$function$;

ALTER FUNCTION recording_vocab_api.read_batted_ball_options(uuid, integer, text) OWNER TO pitchlog_recording_vocab_fn_owner;
REVOKE ALL ON FUNCTION recording_vocab_api.read_batted_ball_options(uuid, integer, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION recording_vocab_api.read_batted_ball_options(uuid, integer, text) TO pitchlog_app;
