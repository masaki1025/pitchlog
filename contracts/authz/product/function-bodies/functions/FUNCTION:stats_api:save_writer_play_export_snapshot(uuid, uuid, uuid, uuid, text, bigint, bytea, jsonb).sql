-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:save_writer_play_export_snapshot(uuid, uuid, uuid, uuid, text, bigint, bytea, jsonb)

CREATE FUNCTION stats_api.save_writer_play_export_snapshot(p_attempt_id uuid,p_phase_id uuid,p_source_event_id uuid,p_fact_version_id uuid,p_source_set_sha256 text,p_revision bigint,p_binding_nonce bytea,p_direct_json jsonb)
RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $export_save$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; bound_game uuid; bound_device uuid;
  bound_generation bigint; bound_d5 uuid; source_d2 bigint;
  saved_play uuid; saved_version bigint; direct_count bigint;
  score_pitch bigint; score_top jsonb; score_bottom jsonb; score_full jsonb;
  finished_json jsonb;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
   OR tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
   OR p_source_event_id IS NULL OR p_fact_version_id IS NULL
   OR p_direct_json IS NULL OR pg_catalog.jsonb_typeof(p_direct_json)<>'object'
 THEN RAISE EXCEPTION 'play export save boundary rejected'
   USING ERRCODE='42501'; END IF;
 SELECT count(*) INTO direct_count FROM pg_catalog.jsonb_object_keys(p_direct_json);
 IF direct_count<>85 OR NOT (p_direct_json ?& ARRAY['試合日時','Season','Kind','Week','Day','GameNumber','主審','後攻チーム','先攻チーム','プレイの番号','回','表.裏','先攻得点','後攻得点','S','B','アウト','打席の継続','イニング継続','試合継続','一走打順','一走氏名','二走打順','二走氏名','三走打順','三走氏名','打順','打者氏名','打席左右','作戦','作戦2','作戦結果','投手氏名','投手左右','捕手','一走状況','二走状況','三走状況','打者状況','プレイの種類','構え','コースX','コースY','球種','打撃結果','打撃結果2','捕球選手','打球タイプ','打球強度','打球位置X','打球位置Y','牽制の種類','牽制詳細','エラーの種類','タイムの種類','球速','プレス','偽走','打者位置','打席Id','打席結果','Result_col','打者登録名','打者番号','一走登録名','一走番号','二走登録名','二走番号','三走登録名','三走番号','投手番号','入力項目','先攻打順','後攻打順','経過時間','開始時刻','現在時刻','top_poses','top_names','top_nums','top_lrs','bottom_poses','bottom_names','bottom_nums','bottom_lrs']::text[])
 THEN RAISE EXCEPTION 'play export columns rejected' USING ERRCODE='22023'; END IF;
 SELECT b.game_id,b.device_id,b.internal_generation,b.d5
   INTO STRICT bound_game,bound_device,bound_generation,bound_d5
 FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
   AND b.state='open' AND b.transaction_id=own_xid
   AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,bound_device,bound_game);
 SELECT e.d2 INTO STRICT source_d2 FROM public.operation_events e
 WHERE e.tenant_id=tenant AND e.game_id=bound_game AND e.id=p_source_event_id
   AND e.generation=bound_generation AND e.d5=bound_d5
   AND e.event_kind='play_input' AND e.ledger_kind='accepted'
   AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
   AND e.import_batch_id IS NULL AND NOT e.migration_unverified
   AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 SELECT p.id,p.version INTO STRICT saved_play,saved_version FROM public.play_rows p
 WHERE p.tenant_id=tenant AND p.game_id=bound_game
   AND p.source_event_id=p_source_event_id
   AND p.event_kind IN ('pitch','non_pitch')
   AND p.hidden_at IS NULL AND p.version=1
   AND p.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 SELECT s.pitcher_pitch_count,s.top_score,s.bottom_score,s.full_innings
 INTO STRICT score_pitch,score_top,score_bottom,score_full
 FROM stats_api.read_writer_play_export_aggregate(p_attempt_id,p_phase_id,p_source_event_id,p_fact_version_id,
   p_source_set_sha256,p_revision,p_binding_nonce) s;
 IF score_pitch IS NULL OR score_top IS NULL OR score_bottom IS NULL
   OR score_full IS NULL OR source_d2 IS NULL
 THEN RAISE EXCEPTION 'play export score unavailable' USING ERRCODE='22023'; END IF;
 finished_json:=p_direct_json || pg_catalog.jsonb_build_object(
   '球数',score_pitch::text,'top_score',score_top::text,
   'bottom_score',score_bottom::text);
 INSERT INTO public.play_export_snapshots(
   tenant_id,game_id,play_row_id,plays_csv_json,full_innings_json,
   source_event_id,play_version,recording_generation,event_sequence)
 VALUES(tenant,bound_game,saved_play,finished_json,score_full,
   p_source_event_id,saved_version,bound_generation,source_d2);
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,bound_device,bound_game);
 RETURN saved_play;
END;
$export_save$;
ALTER FUNCTION stats_api.save_writer_play_export_snapshot(uuid,uuid,uuid,uuid,text,bigint,bytea,jsonb) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.save_writer_play_export_snapshot(uuid,uuid,uuid,uuid,text,bigint,bytea,jsonb) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_api.save_writer_play_export_snapshot(uuid,uuid,uuid,uuid,text,bigint,bytea,jsonb) TO pitchlog_app;
