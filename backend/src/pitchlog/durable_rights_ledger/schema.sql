-- 業務DBへ適用しない外部耐久台帳専用DDL。資格は配置側で供給する。
CREATE ROLE pitchlog_ledger_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE pitchlog_ledger_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE pitchlog_ledger_control LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT pg_read_all_stats TO pitchlog_ledger_owner;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO pitchlog_ledger_owner;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_checkpoint() TO pitchlog_ledger_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA pitchlog_ledger AUTHORIZATION pitchlog_ledger_owner;
REVOKE ALL ON SCHEMA pitchlog_ledger FROM PUBLIC;
GRANT USAGE ON SCHEMA pitchlog_ledger TO pitchlog_ledger_app, pitchlog_ledger_control;
SET ROLE pitchlog_ledger_owner;
ALTER DEFAULT PRIVILEGES IN SCHEMA pitchlog_ledger REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
CREATE TABLE pitchlog_ledger.state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    epoch bigint NOT NULL CHECK (epoch > 0)
);
INSERT INTO pitchlog_ledger.state VALUES (true, 1);
CREATE TABLE pitchlog_ledger.highwater (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    value bigint NOT NULL CHECK (value >= 0)
);
INSERT INTO pitchlog_ledger.highwater VALUES (true, 0);
CREATE TABLE pitchlog_ledger.reservations (
    attempt_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    game_id uuid NOT NULL,
    start_request_id uuid NOT NULL,
    generation bigint NOT NULL UNIQUE CHECK (generation > 0),
    recovery_generation bigint NOT NULL CHECK (recovery_generation > 0),
    claimed boolean NOT NULL DEFAULT false,
    quarantined boolean NOT NULL DEFAULT false,
    UNIQUE (tenant_id, game_id, start_request_id)
);
CREATE FUNCTION pitchlog_ledger.identity() RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
SELECT jsonb_build_object(
    'system_id', (SELECT system_identifier::text FROM pg_control_system()),
    'timeline', (SELECT timeline_id FROM pg_control_checkpoint()),
    'started_at', pg_postmaster_start_time()::text,
    'address', inet_server_addr()::text, 'recovery', pg_is_in_recovery(), 'version', current_setting('server_version_num')::integer,
    'fsync', current_setting('fsync'), 'full_page_writes', current_setting('full_page_writes'),
    'synchronous_commit', current_setting('synchronous_commit'),
    'synchronous_standby_names', current_setting('synchronous_standby_names'),
    'received_wal', CASE WHEN pg_is_in_recovery() THEN pg_last_wal_receive_lsn()::text ELSE NULL END,
    'wal', CASE WHEN pg_is_in_recovery() THEN pg_last_wal_replay_lsn()::text
               ELSE pg_current_wal_flush_lsn()::text END,
    'epoch', (SELECT epoch FROM pitchlog_ledger.state), 'highwater', (SELECT value FROM pitchlog_ledger.highwater),
    'reservation_count', (SELECT count(*) FROM pitchlog_ledger.reservations),
    'peers', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'name', application_name, 'state', state, 'sync_state', sync_state,
        'flush', flush_lsn::text, 'address', client_addr::text, 'user', usename)) FROM pg_catalog.pg_stat_replication), '[]'::jsonb)
)
$$;
CREATE FUNCTION pitchlog_ledger.epoch_fence() RETURNS bigint
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
SELECT epoch FROM pitchlog_ledger.state WHERE singleton FOR SHARE
$$;
CREATE FUNCTION pitchlog_ledger.reservation(p_attempt uuid, p_tenant uuid, p_game uuid, p_start uuid)
RETURNS TABLE(generation bigint, recovery_generation bigint, tenant_id uuid,
             game_id uuid, start_request_id uuid, claimed boolean, quarantined boolean)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
SELECT r.generation, r.recovery_generation, r.tenant_id, r.game_id, r.start_request_id, r.claimed, r.quarantined
FROM pitchlog_ledger.reservations r WHERE r.attempt_id = p_attempt AND r.tenant_id = p_tenant
    AND r.game_id = p_game AND r.start_request_id = p_start
$$;
CREATE FUNCTION pitchlog_ledger.reserve(p_attempt uuid, p_tenant uuid, p_game uuid, p_start uuid)
RETURNS TABLE(generation bigint, recovery_generation bigint, tenant_id uuid,
             game_id uuid, start_request_id uuid, claimed boolean, quarantined boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
DECLARE s pitchlog_ledger.state%ROWTYPE; r pitchlog_ledger.reservations%ROWTYPE; h bigint;
BEGIN
    IF p_attempt IS NULL OR p_tenant IS NULL OR p_game IS NULL OR p_start IS NULL
       OR current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    SELECT * INTO STRICT s FROM pitchlog_ledger.state WHERE singleton FOR SHARE;
    SELECT value INTO STRICT h FROM pitchlog_ledger.highwater WHERE singleton FOR UPDATE;
    SELECT * INTO r FROM pitchlog_ledger.reservations WHERE attempt_id = p_attempt;
    IF FOUND THEN
        IF r.tenant_id <> p_tenant OR r.game_id <> p_game OR r.start_request_id <> p_start
           OR r.recovery_generation <> s.epoch OR r.claimed OR r.quarantined THEN
            RAISE EXCEPTION 'ledger operation refused';
        END IF;
    ELSE
        IF h = 9223372036854775807 THEN
            RAISE EXCEPTION 'ledger operation refused';
        END IF;
        UPDATE pitchlog_ledger.highwater SET value = value + 1 WHERE singleton;
        INSERT INTO pitchlog_ledger.reservations VALUES
            (p_attempt, p_tenant, p_game, p_start, h + 1, s.epoch, false, false)
            RETURNING * INTO r;
    END IF;
    RETURN QUERY SELECT r.generation, r.recovery_generation, r.tenant_id,
                        r.game_id, r.start_request_id, r.claimed, r.quarantined;
END $$;
CREATE FUNCTION pitchlog_ledger.claim(p_attempt uuid, p_tenant uuid, p_game uuid, p_start uuid)
RETURNS TABLE(generation bigint, recovery_generation bigint, tenant_id uuid,
             game_id uuid, start_request_id uuid, claimed boolean, quarantined boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
DECLARE e bigint; r pitchlog_ledger.reservations%ROWTYPE;
BEGIN
    IF current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    SELECT epoch INTO STRICT e FROM pitchlog_ledger.state WHERE singleton FOR SHARE;
    SELECT * INTO STRICT r FROM pitchlog_ledger.reservations WHERE attempt_id = p_attempt FOR UPDATE;
    IF p_tenant IS NULL OR p_game IS NULL OR p_start IS NULL OR r.tenant_id <> p_tenant
       OR r.game_id <> p_game OR r.start_request_id <> p_start
       OR r.recovery_generation <> e OR r.claimed OR r.quarantined THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    UPDATE pitchlog_ledger.reservations SET claimed = true WHERE attempt_id = p_attempt;
    RETURN QUERY SELECT r.generation, r.recovery_generation, r.tenant_id,
                        r.game_id, r.start_request_id, true, false;
END $$;
CREATE FUNCTION pitchlog_ledger.advance_epoch(p_previous bigint) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
DECLARE e bigint;
BEGIN
    IF current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    SELECT epoch INTO STRICT e FROM pitchlog_ledger.state WHERE singleton FOR UPDATE;
    IF p_previous IS NULL OR e <> p_previous OR e = 9223372036854775807 THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    UPDATE pitchlog_ledger.state SET epoch = e + 1 WHERE singleton;
    RETURN e + 1;
END $$;
-- journal照合済みの起動時だけ、値を変えずに実同期WAL barrierを作る。
CREATE FUNCTION pitchlog_ledger.confirm_state(p_epoch bigint, p_highwater bigint, p_count bigint)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
DECLARE e bigint; h bigint; c bigint;
BEGIN
    IF p_epoch IS NULL OR p_highwater IS NULL OR p_count IS NULL
       OR current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    SELECT epoch INTO STRICT e FROM pitchlog_ledger.state WHERE singleton FOR SHARE;
    SELECT value INTO STRICT h FROM pitchlog_ledger.highwater WHERE singleton FOR UPDATE;
    SELECT count(*) INTO c FROM pitchlog_ledger.reservations;
    IF e <> p_epoch OR h <> p_highwater OR c <> p_count THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    UPDATE pitchlog_ledger.highwater SET value = h WHERE singleton;
    RETURN e;
END $$;
CREATE FUNCTION pitchlog_ledger.audit_page(p_after bigint, p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
DECLARE result jsonb;
BEGIN
    IF p_after IS NULL OR p_after < 0 OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256 THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    SELECT COALESCE(jsonb_agg(to_jsonb(r) ORDER BY r.generation), '[]'::jsonb) INTO result
    FROM (SELECT * FROM pitchlog_ledger.reservations WHERE generation > p_after ORDER BY generation LIMIT p_limit) r;
    RETURN result;
END $$;
CREATE FUNCTION pitchlog_ledger.reconcile(
    p_attempt uuid, p_tenant uuid, p_game uuid, p_start uuid,
    p_generation bigint, p_epoch bigint, p_claimed boolean, p_quarantined boolean,
    p_previous_highwater bigint
) RETURNS TABLE(generation bigint, recovery_generation bigint, tenant_id uuid,
                game_id uuid, start_request_id uuid, claimed boolean, quarantined boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger, pg_temp AS $$
DECLARE e bigint; h bigint; r pitchlog_ledger.reservations%ROWTYPE;
BEGIN
    IF p_attempt IS NULL OR p_tenant IS NULL OR p_game IS NULL OR p_start IS NULL
       OR p_generation IS NULL OR p_generation <= 0 OR p_epoch IS NULL OR p_epoch <= 0
       OR p_claimed IS NULL OR p_quarantined IS NULL OR p_previous_highwater IS NULL
       OR current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'ledger operation refused';
    END IF;
    SELECT epoch INTO STRICT e FROM pitchlog_ledger.state WHERE singleton FOR SHARE;
    SELECT value INTO STRICT h FROM pitchlog_ledger.highwater WHERE singleton FOR UPDATE;
    IF h <> p_previous_highwater OR p_epoch > e THEN RAISE EXCEPTION 'ledger operation refused'; END IF;
    SELECT * INTO r FROM pitchlog_ledger.reservations WHERE attempt_id=p_attempt FOR UPDATE;
    IF FOUND THEN
        IF r.tenant_id <> p_tenant OR r.game_id <> p_game OR r.start_request_id <> p_start
           OR r.generation <> p_generation OR r.recovery_generation <> p_epoch
           OR (r.claimed AND NOT p_claimed) OR (r.quarantined AND NOT p_quarantined) THEN
            RAISE EXCEPTION 'ledger operation refused';
        END IF;
        UPDATE pitchlog_ledger.reservations SET claimed=p_claimed, quarantined=p_quarantined WHERE attempt_id=p_attempt;
    ELSE
        INSERT INTO pitchlog_ledger.reservations VALUES
            (p_attempt,p_tenant,p_game,p_start,p_generation,p_epoch,p_claimed,p_quarantined);
    END IF;
    UPDATE pitchlog_ledger.highwater SET value=greatest(value,p_generation) WHERE singleton;
    RETURN QUERY SELECT x.generation,x.recovery_generation,x.tenant_id,x.game_id,
                        x.start_request_id,x.claimed,x.quarantined
                 FROM pitchlog_ledger.reservations x WHERE x.attempt_id=p_attempt;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA pitchlog_ledger FROM PUBLIC, pitchlog_ledger_app, pitchlog_ledger_control;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA pitchlog_ledger FROM PUBLIC, pitchlog_ledger_app, pitchlog_ledger_control;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.identity() TO pitchlog_ledger_app, pitchlog_ledger_control;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.epoch_fence() TO pitchlog_ledger_app;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.reservation(uuid, uuid, uuid, uuid) TO pitchlog_ledger_app;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.reserve(uuid, uuid, uuid, uuid) TO pitchlog_ledger_app;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.claim(uuid, uuid, uuid, uuid) TO pitchlog_ledger_app;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.advance_epoch(bigint) TO pitchlog_ledger_control;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.audit_page(bigint, integer) TO pitchlog_ledger_control;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.reconcile(uuid, uuid, uuid, uuid, bigint, bigint, boolean, boolean, bigint) TO pitchlog_ledger_control;
GRANT EXECUTE ON FUNCTION pitchlog_ledger.confirm_state(bigint,bigint,bigint) TO pitchlog_ledger_control;
RESET ROLE;
