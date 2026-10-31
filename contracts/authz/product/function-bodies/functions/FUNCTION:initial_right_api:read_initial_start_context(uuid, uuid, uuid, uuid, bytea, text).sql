-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:read_initial_start_context(uuid, uuid, uuid, uuid, bytea, text)

CREATE OR REPLACE FUNCTION initial_right_api.read_initial_start_context(
p_tenant_id uuid,p_game_id uuid,p_request_id uuid,p_attempt_id uuid,
p_request_digest bytea,p_payload text)
RETURNS TABLE(context_json text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE
    payload jsonb; req record; attempt record; game_row record;
    team record; player record; entry jsonb; side text; ids uuid[];
    away_entries jsonb; home_entries jsonb; result jsonb;
    self_team uuid; snapshot jsonb; lineup record; away_id uuid; home_id uuid;
BEGIN
    IF session_user <> 'pitchlog_initial_actor' OR current_user <>
    'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_request_id IS NULL
       OR p_attempt_id IS NULL OR p_request_digest IS NULL
       OR octet_length(p_request_digest) <> 32 OR p_payload IS NULL
       OR octet_length(p_payload) > 32768
       OR nullif(current_setting('app.tenant_id',true),'') IS DISTINCT FROM
    p_tenant_id::text
       OR sha256(convert_to(p_payload,'UTF8')) IS DISTINCT FROM p_request_digest THEN
        RAISE EXCEPTION 'initial start input rejected' USING ERRCODE='42501';
    END IF;
    payload := p_payload::jsonb;
    IF jsonb_typeof(payload) <> 'object' OR
       (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(payload) k) IS DISTINCT
    FROM
       ARRAY['away','credential_digest','device_id','domain','game_id','home','start_request_id','tenant_id']::text[]
       OR payload->>'domain' <> 'pitchlog.initial-game-start.v1'
       OR payload->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
       OR payload->>'game_id' IS DISTINCT FROM p_game_id::text
       OR payload->>'start_request_id' IS DISTINCT FROM p_request_id::text THEN
        RAISE EXCEPTION 'initial start payload rejected' USING ERRCODE='42501';
    END IF;
    SELECT r.device_id,r.request_digest INTO STRICT req FROM
    public.game_start_requests r
      WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND
    r.start_request_id=p_request_id
      FOR UPDATE;
    IF req.device_id::text IS DISTINCT FROM payload->>'device_id'
       OR req.request_digest IS DISTINCT FROM p_request_digest THEN
        RAISE EXCEPTION 'initial start owner rejected' USING ERRCODE='42501';
    END IF;
    PERFORM 1 FROM public.trusted_devices d WHERE d.tenant_id=p_tenant_id
      AND d.device_id=req.device_id AND d.revoked_at IS NULL
      AND encode(d.credential_digest,'hex')=payload->>'credential_digest' FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'initial start device rejected' USING
    ERRCODE='42501'; END IF;
    SELECT a.outcome INTO STRICT attempt FROM public.game_start_attempts a
      WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND
    a.start_request_id=p_request_id
        AND a.attempt_id=p_attempt_id FOR UPDATE;
    SELECT
    g.away_team_record_id,g.home_team_record_id,g.applied_rules,g.status,g.started_at,
           g.trashed_at,g.hidden_at INTO STRICT game_row FROM public.games g
      WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id FOR UPDATE;
    IF game_row.away_team_record_id=game_row.home_team_record_id
       OR game_row.trashed_at IS NOT NULL OR game_row.hidden_at IS NOT NULL THEN
        RAISE EXCEPTION 'initial start game rejected' USING ERRCODE='42501';
    END IF;
    FOREACH side IN ARRAY ARRAY['away','home'] LOOP
        IF jsonb_typeof(payload->side) IS DISTINCT FROM 'array'
           OR jsonb_array_length(payload->side) NOT IN (9,10) THEN
            RAISE EXCEPTION 'initial start entries rejected' USING ERRCODE='42501';
        END IF;
        FOR entry IN SELECT v FROM jsonb_array_elements(payload->side) v LOOP
            IF jsonb_typeof(entry) <> 'object' OR
               (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(entry) k) IS
    DISTINCT FROM
               ARRAY['batting_order','fielding_position','player_id']::text[]
               OR jsonb_typeof(entry->'player_id') <> 'string'
               OR (entry->>'player_id')::uuid::text IS DISTINCT FROM entry->>'player_id'
               OR NOT (entry->'batting_order'='null'::jsonb OR
                    (jsonb_typeof(entry->'batting_order')='number' AND
    entry->>'batting_order' ~ '^[1-9]$'))
               OR jsonb_typeof(entry->'fielding_position') <> 'object' THEN
                RAISE EXCEPTION 'initial start entry rejected' USING ERRCODE='42501';
            END IF;
            IF entry->'fielding_position'->>'kind' = 'fielding' THEN
                IF (SELECT count(*) FROM
    jsonb_object_keys(entry->'fielding_position'))<>2
                   OR jsonb_typeof(entry->'fielding_position'->'position') <> 'number'
                   OR NOT (entry->'fielding_position'->>'position' ~ '^[1-9]$') THEN
                    RAISE EXCEPTION 'initial start role rejected' USING ERRCODE='42501';
                END IF;
            ELSIF entry->'fielding_position' = '{"kind":"designated-hitter"}'::jsonb
    THEN
                NULL;
            ELSE RAISE EXCEPTION 'initial start role rejected' USING ERRCODE='42501';
            END IF;
        END LOOP;
    END LOOP;
    IF attempt.outcome='pending' THEN
        IF game_row.status <> 'preparing' OR game_row.started_at IS NOT NULL
           OR EXISTS (SELECT 1 FROM public.game_lineups l WHERE
    l.tenant_id=p_tenant_id AND l.game_id=p_game_id) THEN
            RAISE EXCEPTION 'initial start already exists' USING ERRCODE='42501';
        END IF;
        FOR team IN SELECT t.id,t.kind,t.hidden_at FROM public.team_records t
          WHERE t.tenant_id=p_tenant_id AND t.id IN
    (game_row.away_team_record_id,game_row.home_team_record_id)
          ORDER BY t.id FOR UPDATE LOOP
            IF team.hidden_at IS NOT NULL OR team.kind NOT IN ('self','opponent') THEN
                RAISE EXCEPTION 'initial start team rejected' USING ERRCODE='42501';
            END IF;
            IF team.kind='self' THEN
                IF self_team IS NOT NULL THEN RAISE EXCEPTION
    'initial start self rejected' USING ERRCODE='42501'; END IF;
                self_team:=team.id;
            END IF;
        END LOOP;
        IF self_team IS NULL OR (SELECT count(*) FROM public.team_records t WHERE
    t.tenant_id=p_tenant_id
            AND t.id IN (game_row.away_team_record_id,game_row.home_team_record_id))
    <> 2 THEN
            RAISE EXCEPTION 'initial start teams missing' USING ERRCODE='42501';
        END IF;
        SELECT array_agg((e->>'player_id')::uuid ORDER BY (e->>'player_id')::uuid)
    INTO ids
          FROM jsonb_array_elements((payload->'away')||(payload->'home')) e;
        FOR player IN SELECT p.id,p.team_record_id,p.roster_status_key,p.hidden_at
    FROM public.players p
          WHERE p.tenant_id=p_tenant_id AND p.id=ANY(ids) ORDER BY p.id FOR UPDATE LOOP
            IF player.hidden_at IS NOT NULL OR player.roster_status_key <> 'active' THEN
                RAISE EXCEPTION 'initial start player rejected' USING ERRCODE='42501';
            END IF;
        END LOOP;
        FOREACH side IN ARRAY ARRAY['away','home'] LOOP
            SELECT jsonb_agg(e ||
    jsonb_build_object('uniform_number_snapshot',p.uniform_number) ORDER BY ord)
              INTO snapshot FROM jsonb_array_elements(payload->side) WITH ORDINALITY
    AS input(e,ord)
              JOIN public.players p ON p.tenant_id=p_tenant_id AND
    p.id=(e->>'player_id')::uuid
              AND p.team_record_id=CASE WHEN side='away' THEN
    game_row.away_team_record_id ELSE game_row.home_team_record_id END
              AND p.hidden_at IS NULL AND p.roster_status_key='active';
            IF jsonb_array_length(snapshot) IS DISTINCT FROM
    jsonb_array_length(payload->side) THEN
                RAISE EXCEPTION 'initial start player missing' USING ERRCODE='42501';
            END IF;
            IF side='away' THEN away_entries:=snapshot; ELSE home_entries:=snapshot;
    END IF;
        END LOOP;
    ELSIF attempt.outcome='committed' THEN
        IF game_row.status NOT IN ('in_progress','finished') OR game_row.started_at
    IS NULL THEN
            RAISE EXCEPTION 'initial start receipt missing' USING ERRCODE='42501';
        END IF;
        IF (SELECT count(*) FROM public.game_lineups l WHERE l.tenant_id=p_tenant_id
    AND l.game_id=p_game_id)<>2 THEN
            RAISE EXCEPTION 'initial start lineups missing' USING ERRCODE='42501';
        END IF;
        FOREACH side IN ARRAY ARRAY['away','home'] LOOP
            SELECT l.id,l.entries_with_uniform_number_snapshot INTO STRICT lineup
    FROM public.game_lineups l
              WHERE l.tenant_id=p_tenant_id AND l.game_id=p_game_id
              AND l.team_record_id=CASE WHEN side='away' THEN
    game_row.away_team_record_id ELSE game_row.home_team_record_id END;
            SELECT jsonb_agg(e-'uniform_number_snapshot' ORDER BY ord) INTO snapshot
              FROM jsonb_array_elements(lineup.entries_with_uniform_number_snapshot)
    WITH ORDINALITY AS input(e,ord);
            IF snapshot IS DISTINCT FROM payload->side THEN
                RAISE EXCEPTION 'initial start immutable payload mismatch' USING
    ERRCODE='42501';
            END IF;
            IF side='away' THEN
    away_entries:=lineup.entries_with_uniform_number_snapshot; away_id:=lineup.id;
            ELSE home_entries:=lineup.entries_with_uniform_number_snapshot;
    home_id:=lineup.id; END IF;
        END LOOP;
        -- 現役選手/背番号は読まない。側所属の固定teamだけからselfを識別する。
        SELECT t.id INTO STRICT self_team FROM public.team_records t WHERE
    t.tenant_id=p_tenant_id
          AND t.id IN (game_row.away_team_record_id,game_row.home_team_record_id) AND
    t.kind='self';
    ELSE RAISE EXCEPTION 'initial start unresolved' USING ERRCODE='42501';
    END IF;
    result:=jsonb_build_object('tenant_id',p_tenant_id,'game_id',p_game_id,'start_request_id',p_request_id,
      'device_id',req.device_id,'attempt_id',p_attempt_id,'request_digest',encode(p_request_digest,'hex'),
      'outcome',attempt.outcome,'away_team_id',game_row.away_team_record_id,'home_team_id',game_row.home_team_record_id,
      'self_team_id',self_team,'applied_rules',game_row.applied_rules,'away',away_entries,'home',home_entries,
      'started_at',game_row.started_at,'away_lineup_id',away_id,'home_lineup_id',home_id);
    RETURN QUERY SELECT result::text;
EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'initial start operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.read_initial_start_context(uuid, uuid, uuid, uuid, bytea, text) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.read_initial_start_context(uuid, uuid, uuid, uuid, bytea, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.read_initial_start_context(uuid, uuid, uuid, uuid, bytea, text) TO pitchlog_initial_actor;
