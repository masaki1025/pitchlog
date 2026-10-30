-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:persist_initial_start(uuid, uuid, uuid, uuid, bytea, text)

CREATE OR REPLACE FUNCTION initial_right_api.persist_initial_start(
p_tenant_id uuid,p_game_id uuid,p_request_id uuid,p_attempt_id uuid,
p_request_digest bytea,p_payload text)
RETURNS TABLE(started_at timestamp with time zone, away_lineup_id uuid, home_lineup_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE ctx jsonb; stamp timestamptz; away_id uuid; home_id uuid;
BEGIN
    -- readは同じsubject/owner/digest/全payload検査と同一Session lockを持つ。
    SELECT r.context_json::jsonb INTO STRICT ctx FROM
    initial_right_api.read_initial_start_context(
        p_tenant_id,p_game_id,p_request_id,p_attempt_id,p_request_digest,p_payload) r;
    IF ctx->>'outcome' <> 'pending' THEN
        RAISE EXCEPTION 'initial start persistence rejected' USING ERRCODE='42501';
    END IF;
    away_id:=gen_random_uuid(); home_id:=gen_random_uuid(); stamp:=clock_timestamp();
    INSERT INTO
    public.game_lineups(tenant_id,id,game_id,team_record_id,entries_with_uniform_number_snapshot)
      VALUES(p_tenant_id,away_id,p_game_id,(ctx->>'away_team_id')::uuid,ctx->'away'),
            (p_tenant_id,home_id,p_game_id,(ctx->>'home_team_id')::uuid,ctx->'home');
    UPDATE public.games AS target SET status='in_progress',started_at=stamp
      WHERE target.tenant_id=p_tenant_id AND target.id=p_game_id
      AND target.status='preparing' AND target.started_at IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'initial start game changed' USING
    ERRCODE='42501'; END IF;
    RETURN QUERY SELECT stamp,away_id,home_id;
EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'initial start operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.persist_initial_start(uuid, uuid, uuid, uuid, bytea, text) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.persist_initial_start(uuid, uuid, uuid, uuid, bytea, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.persist_initial_start(uuid, uuid, uuid, uuid, bytea, text) TO pitchlog_initial_actor;
