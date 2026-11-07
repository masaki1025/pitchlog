"""D03を既保存TXから呼ぶowner-only SQL候補。外部CAP/自由tokenを増やさない。"""

from __future__ import annotations


def candidate_start_entry_function() -> str:
    """同TX実原本から唯一projectorを再利用する開始保存候補を描画する。"""
    import hashlib

    from pitchlog.domaingen.stats_appearance import generate_appearance_bundle
    from pitchlog.domainrt.host import _product_artifact_paths, _verified_source

    artifact = hashlib.sha256(
        _verified_source(*_product_artifact_paths()).encode()
    ).hexdigest()
    bundle, _ = generate_appearance_bundle()
    query = bundle["backend/src/pitchlog/stats/generated/pitcher_entry_projection.sql"]
    return f"""CREATE FUNCTION initial_right_api.persist_start_pitcher_entry(
 p_tenant_id uuid,p_attempt_id uuid,p_generation bigint)
RETURNS TABLE(proof_sha256 text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_start$
#variable_conflict use_column
DECLARE v_tenant uuid; v_game uuid; v_device uuid; v_home uuid; v_away uuid;
 v_fingerprint text; v_home_pitcher uuid; v_away_pitcher uuid;
 v_entry jsonb; v_proof jsonb; v_digest text; v_context text;
BEGIN
 v_tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 IF session_user IS DISTINCT FROM 'pitchlog_initial_actor'
 OR current_user IS DISTINCT FROM 'pitchlog_initial_fn_owner'
 OR v_tenant IS NULL OR p_tenant_id IS DISTINCT FROM v_tenant
 OR p_attempt_id IS NULL OR p_generation IS NULL
 OR p_generation<1 OR pg_catalog.current_setting('transaction_read_only')<>'off'
 THEN RAISE EXCEPTION 'pitcher entry start boundary rejected'
 USING ERRCODE='42501'; END IF;
 SELECT a.game_id,a.device_id,g.home_team_record_id,g.away_team_record_id,
 pg_catalog.encode(r.request_digest,'hex')
 INTO STRICT v_game,v_device,v_home,v_away,v_fingerprint
 FROM public.game_start_attempts a
 JOIN public.game_start_requests r
 ON (r.tenant_id,r.game_id,r.start_request_id,r.device_id)=
 (a.tenant_id,a.game_id,a.start_request_id,a.device_id)
 JOIN public.games g ON g.tenant_id=a.tenant_id AND g.id=a.game_id
 JOIN public.recording_generations rg
 ON rg.tenant_id=a.tenant_id AND rg.game_id=a.game_id
 WHERE a.tenant_id=v_tenant AND a.attempt_id=p_attempt_id AND a.outcome='committed'
 AND rg.generation=p_generation AND rg.kind='normal' AND rg.revoked_at IS NULL
 AND rg.holder_device=a.device_id::text
 AND g.status='in_progress' AND g.started_at IS NOT NULL;
 SELECT (entries.value->>'player_id')::uuid INTO STRICT v_home_pitcher
 FROM public.game_lineups l CROSS JOIN LATERAL
 pg_catalog.jsonb_array_elements(l.entries_with_uniform_number_snapshot)
 AS entries(value)
 WHERE l.tenant_id=v_tenant AND l.game_id=v_game AND l.team_record_id=v_home
 AND entries.value->'fielding_position'='{{"kind":"fielding","position":1}}'::jsonb;
 SELECT (entries.value->>'player_id')::uuid INTO STRICT v_away_pitcher
 FROM public.game_lineups l CROSS JOIN LATERAL
 pg_catalog.jsonb_array_elements(l.entries_with_uniform_number_snapshot)
 AS entries(value)
 WHERE l.tenant_id=v_tenant AND l.game_id=v_game AND l.team_record_id=v_away
 AND entries.value->'fielding_position'='{{"kind":"fielding","position":1}}'::jsonb;
 WITH appearance_transition AS (SELECT v_tenant AS tenant_id,v_game AS game_id,
 p_attempt_id AS source_id,'start'::text AS origin_kind,
 p_generation AS internal_generation,
 NULL::bigint AS d1,NULL::bigint AS before_inning,NULL::text AS before_half,
 1::bigint AS after_inning,'top'::text AS after_half,
 v_home_pitcher AS after_home_pitcher_id,v_away_pitcher AS after_away_pitcher_id,
 NULL::uuid AS before_home_pitcher_id,NULL::uuid AS before_away_pitcher_id,
 NULL::text AS changed_side,NULL::boolean AS half_completed,
 NULL::boolean AS end_condition_detected,NULL::boolean AS lock_further_play,
 NULL::text AS outcome,NULL::text AS x_mark,NULL::boolean AS released_end_condition,
 NULL::boolean AS half_started_before,'{artifact}'::text AS artifact_sha256,
 v_fingerprint AS source_fingerprint)
 SELECT pg_catalog.to_jsonb(projected) INTO STRICT v_entry FROM (
{query}
 ) projected;
 IF v_entry->>'state' IS DISTINCT FROM 'evaluated' OR v_entry->>'player_id' IS NULL
 THEN RAISE EXCEPTION 'pitcher entry start unavailable' USING ERRCODE='42501'; END IF;
 v_context:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 pg_catalog.jsonb_build_object('homePitcher',v_home_pitcher,
 'awayPitcher',v_away_pitcher,'requestDigest',v_fingerprint)::text,'UTF8')),'hex');
 v_proof:=pg_catalog.jsonb_build_object('tenant_id',v_tenant,'game_id',v_game,
 'origin_kind','start','start_attempt_id',p_attempt_id,'source_event_id',NULL,
 'generation',p_generation,'d1',NULL,'slot_version',NULL,
 'player_id',(v_entry->>'player_id')::uuid,'defending_side',v_entry->>'defending_side',
 'inning',(v_entry->>'inning')::bigint,'half',v_entry->>'half',
 'proof_kind',v_entry->>'proof_kind','source_fingerprint',v_fingerprint,
 'artifact_sha256','{artifact}','context_sha256',v_context);
 v_digest:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_proof::text,'UTF8')),'hex');
 INSERT INTO sync_fence.pitcher_entry_sources(
 tenant_id,game_id,proof_sha256,origin_kind,start_attempt_id,source_event_id,
 generation,d1,slot_version,player_id,defending_side,inning,half,proof_kind,
 source_fingerprint,artifact_sha256,context_sha256)
 SELECT v_tenant,v_game,v_digest,'start',p_attempt_id,NULL,p_generation,NULL,NULL,
 (v_entry->>'player_id')::uuid,v_entry->>'defending_side',(v_entry->>'inning')::bigint,
 v_entry->>'half',v_entry->>'proof_kind',v_fingerprint,'{artifact}',v_context
 ON CONFLICT (tenant_id,game_id,proof_sha256) DO NOTHING;
 IF NOT EXISTS(SELECT 1 FROM sync_fence.pitcher_entry_sources e
 WHERE e.tenant_id=v_tenant AND e.game_id=v_game AND e.proof_sha256=v_digest
 AND pg_catalog.to_jsonb(e)-'proof_sha256'=v_proof)
 THEN RAISE EXCEPTION 'pitcher entry start identity mismatch'
 USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT v_digest;
END;
$d03_start$;
"""


def candidate_entry_guard_function() -> str:
    """監査原本のUPDATE/DELETE/TRUNCATEを無条件拒否する。"""
    return """CREATE FUNCTION stats_api.protect_pitcher_entry_sources()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_guard$
BEGIN
 RAISE EXCEPTION 'pitcher entry immutable boundary rejected' USING ERRCODE='42501';
END;
$d03_guard$;
"""


def candidate_private_entry_declarations():
    """公開操作を増やさず内部helperの全属性と唯一bodyをrootへ渡す。"""
    definitions = (
        (
            "initial_right_api",
            "persist_start_pitcher_entry",
            "uuid, uuid, bigint",
            "pitchlog_initial_fn_owner",
            candidate_start_entry_function(),
            "TABLE(proof_sha256 text)",
        ),
        (
            "stats_api",
            "persist_writer_pitcher_entry",
            "uuid, uuid, uuid, bytea",
            "pitchlog_sync_right_fn_owner",
            candidate_writer_entry_function(),
            "TABLE(proof_sha256 text)",
        ),
        (
            "stats_api",
            "protect_pitcher_entry_sources",
            "",
            "pitchlog_sync_right_fn_owner",
            candidate_entry_guard_function(),
            "trigger",
        ),
    )
    functions, bodies = [], {}
    roles = (
        "PUBLIC",
        "pitchlog_app",
        "pitchlog_initial_actor",
        "pitchlog_sync_binding_actor",
        "pitchlog_initial_fn_owner",
        "pitchlog_sync_right_fn_owner",
    )
    for schema, name, args, owner, body, returns in definitions:
        identity = f"FUNCTION:{schema}:{name}({args})"
        functions.append(
            {
                "function_id": identity,
                "schema_name": schema,
                "function_name": name,
                "identity_args": args,
                "owner_role_id": owner,
                "function_kind": "definer",
                "language": "plpgsql",
                "returns": returns,
                "security_mode": "definer",
                "volatility": "volatile",
                "search_path": ["pg_catalog", "pg_temp"],
                "acl_expectations": [],
                "revoked_acl_expectations": [
                    {"grantee": role, "privilege": "EXECUTE", "grantable": False}
                    for role in roles
                    if role != owner
                ],
            }
        )
        bodies["function|" + identity] = body
    return {"functions": functions}, bodies


def candidate_private_entry_install_sql() -> str:
    """候補配置もowner-onlyに閉じ、外部callerへEXECUTEを追加しない。"""
    declarations, bodies = candidate_private_entry_declarations()
    result = []
    for fn in declarations["functions"]:
        identity = f"{fn['schema_name']}.{fn['function_name']}({fn['identity_args']})"
        revoked = ",".join(row["grantee"] for row in fn["revoked_acl_expectations"])
        result.extend(
            (
                bodies["function|" + fn["function_id"]],
                f"ALTER FUNCTION {identity} OWNER TO {fn['owner_role_id']};\n",
                f"REVOKE ALL ON FUNCTION {identity} FROM {revoked};\n",
            )
        )
    result.append("""CREATE TRIGGER d03_pitcher_entry_immutable
BEFORE UPDATE OR DELETE ON sync_fence.pitcher_entry_sources
FOR EACH ROW EXECUTE FUNCTION stats_api.protect_pitcher_entry_sources();
CREATE TRIGGER d03_pitcher_entry_no_truncate
BEFORE TRUNCATE ON sync_fence.pitcher_entry_sources
FOR EACH STATEMENT EXECUTE FUNCTION stats_api.protect_pitcher_entry_sources();
""")
    return "".join(result)


def candidate_entry_table_install_sql() -> str:
    """root正式配置前にownedだけへ適用する1表/閉ACL/RLS候補を返す。"""
    from sqlalchemy.dialects.postgresql import dialect
    from sqlalchemy.schema import CreateIndex, CreateTable

    from pitchlog.db import all_models
    from pitchlog.db.game_state.pitcher_appearance_models import PitcherEntrySource

    if not all_models.IMPORTED_MODEL_MODULE_NAMES:
        raise ValueError("正式FK先が未供給です")
    table = PitcherEntrySource.__table__
    ddl = str(CreateTable(table).compile(dialect=dialect())) + ";\n"
    ddl += "\n".join(
        str(CreateIndex(i).compile(dialect=dialect())) + ";"
        for i in sorted(table.indexes, key=lambda i: str(i.name))
    )
    return (
        ddl
        + """
GRANT USAGE ON SCHEMA sync_fence TO pitchlog_initial_fn_owner;
ALTER TABLE sync_fence.pitcher_entry_sources OWNER TO pitchlog_sync_right_fn_owner;
ALTER TABLE sync_fence.pitcher_entry_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.pitcher_entry_sources FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT ON sync_fence.pitcher_entry_sources TO pitchlog_initial_fn_owner;
CREATE POLICY pitcher_entry_internal ON sync_fence.pitcher_entry_sources
TO pitchlog_initial_fn_owner,pitchlog_sync_right_fn_owner
USING (tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid);
"""
    )


def candidate_writer_entry_function() -> str:
    """既native Save/交代consume内部だけでDB原本からentryを保存する候補。"""
    from pitchlog.domaingen.stats_appearance import generate_appearance_bundle
    from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

    bundle, _ = generate_appearance_bundle()
    query = bundle["backend/src/pitchlog/stats/generated/pitcher_entry_projection.sql"]
    return f"""CREATE FUNCTION stats_api.persist_writer_pitcher_entry(
 p_attempt_id uuid,p_phase_id uuid,p_source_event_id uuid,p_binding_nonce bytea)
RETURNS TABLE(proof_sha256 text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_writer$
#variable_conflict use_column
DECLARE v_tenant uuid; v_xid text; v_binding sync_fence.writer_bindings%ROWTYPE;
 v_event public.operation_events%ROWTYPE; v_event_xmin xid;
 v_source sync_fence.stats_primitive_sources%ROWTYPE;
 v_receipt sync_fence.substitution_write_receipts%ROWTYPE;
 v_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; v_frame jsonb;
 v_revision bigint; v_s text; v_payload jsonb; v_value jsonb;
 v_before jsonb; v_after jsonb; v_bl jsonb; v_al jsonb;
 v_origin text; v_slot bigint; v_artifact text; v_fingerprint text;
 v_changed text; v_half_completed boolean; v_detected boolean; v_lock boolean;
 v_outcome text; v_xmark text; v_entry jsonb; v_proof jsonb;
 v_digest text; v_context text;
BEGIN
 v_tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 v_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR v_tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
 OR p_source_event_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only')<>'off'
 THEN RAISE EXCEPTION 'pitcher entry writer rejected' USING ERRCODE='42501'; END IF;
 SELECT b.* INTO STRICT v_binding FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=v_tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
 AND b.state='open' AND b.transaction_id=v_xid
 AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(v_tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,v_binding.device_id,v_binding.game_id);
 SELECT e.* INTO STRICT v_event FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots s ON (s.tenant_id,s.game_id,s.generation,s.d1)=
 (e.tenant_id,e.game_id,e.generation,e.d1)
 WHERE e.tenant_id=v_tenant AND e.game_id=v_binding.game_id
 AND e.id=p_source_event_id AND e.generation=v_binding.internal_generation
 AND e.d5=v_binding.d5 AND e.ledger_kind='accepted'
 AND e.event_kind IN ('play_input','substitution') AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND NOT e.migration_unverified AND l.kind='accepted' AND l.retired_at IS NULL
 AND l.import_batch_id IS NULL AND l.source_fingerprint=v_binding.event_fingerprint
 AND s.confirmed_version=1
 AND e.xmin::text::numeric=pg_catalog.mod(v_xid::numeric,4294967296::numeric)
 AND l.xmin=e.xmin AND s.xmin=e.xmin;
 -- ROWTYPEにsystem列は無い。同TXで物理表のxminを明示取得する。
 SELECT e.xmin INTO STRICT v_event_xmin FROM public.operation_events e
 WHERE e.tenant_id=v_tenant AND e.game_id=v_binding.game_id
 AND e.id=p_source_event_id
 AND e.xmin::text::numeric=pg_catalog.mod(v_xid::numeric,4294967296::numeric);
 v_slot:=1; v_fingerprint:=v_binding.event_fingerprint;
 IF v_event.event_kind='play_input' THEN
  SELECT r.revision,r.source_set_sha256 INTO STRICT v_revision,v_s
  FROM stats_api.read_primitive_writer_state(p_attempt_id,p_phase_id,
   p_source_event_id,'{SOURCE_MODEL_HASH}',p_binding_nonce) r;
  SELECT s.* INTO STRICT v_source FROM sync_fence.stats_primitive_sources s
  JOIN sync_fence.stats_fact_versions v ON (v.tenant_id,v.game_id,v.id)=
   (s.tenant_id,s.game_id,s.fact_version_id)
  WHERE s.tenant_id=v_tenant AND s.game_id=v_event.game_id
  AND s.source_event_id=v_event.id
  AND s.attempt_id=p_attempt_id AND s.phase_id=p_phase_id
  AND s.recording_generation=v_event.generation AND s.d1=v_event.d1
  AND s.source_fingerprint=v_fingerprint AND s.slot_version=v_slot
  AND v.is_current AND v.invalidated_at IS NULL AND v.completion_state='current_open'
  AND v.model_sha256='{SOURCE_MODEL_HASH}' AND v.revision=v_revision
  AND v.source_set_sha256=v_s AND s.xmin=v_event_xmin AND v.xmin=v_event_xmin;
  v_payload:=v_event.payload;
  v_before:=v_payload#>'{{calculation,request,t1,before,stateFields}}';
  v_after:=v_payload#>'{{calculation,response,value,t1,after,stateFields}}';
  IF v_payload->>'formatVersion' IN ('first-ball-play-v1','ordinary-pitch-play-v1',
      'play-prefix-play-v2') AND v_before->>'state.half' IS NOT NULL
    AND v_before->>'state.half'=v_after->>'state.half'
    AND v_before->>'state.inning'=v_after->>'state.inning' THEN
    PERFORM sync_fence_api.assert_writer_binding(v_tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,v_binding.device_id,v_binding.game_id);
 RETURN QUERY SELECT NULL::text; RETURN;
  END IF;
  IF v_payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'
  THEN RAISE EXCEPTION 'pitcher entry profile unavailable'
   USING ERRCODE='42501'; END IF;
  v_origin:='play'; v_value:=v_payload#>'{{calculation,response,value}}';
  IF v_payload#>>'{{calculation,request,source,formatVersion}}'=
    'nonplay-prefix-source-v1' THEN
   v_bl:=v_payload#>'{{calculation,request,source,checkpoint,content,restored,lineup}}';
  ELSE v_bl:=v_payload#>'{{calculation,request,source,lineup}}'; END IF;
  v_al:=v_value->'lineup'; v_artifact:=v_source.artifact_sha256;
  IF v_value->>'executionArtifactSha256' IS DISTINCT FROM v_artifact
   OR v_value#>>'{{t2,facts,beforeHalf}}' IS DISTINCT FROM v_before->>'state.half'
   OR v_value#>>'{{t2,facts,afterHalf}}' IS DISTINCT FROM v_after->>'state.half'
   OR v_value#>>'{{t2,facts,beforeInning}}' IS DISTINCT FROM v_before->>'state.inning'
   OR v_value#>>'{{t2,facts,afterInning}}' IS DISTINCT FROM v_after->>'state.inning'
  THEN RAISE EXCEPTION 'pitcher entry stored kernel mismatch'
   USING ERRCODE='42501'; END IF;
  v_half_completed:=(v_value#>>'{{t2,facts,halfCompleted}}')::boolean;
  v_detected:=(v_value#>>'{{t2,decision,endConditionDetected}}')::boolean;
  v_lock:=(v_value#>>'{{t2,decision,lockFurtherPlayInput}}')::boolean;
  v_outcome:=v_value#>>'{{t2,decision,outcome}}';
  v_xmark:=v_value#>>'{{t2,decision,xMark}}';
 ELSE
  v_origin:='substitution';
  SELECT sr.* INTO STRICT v_receipt FROM sync_fence.substitution_write_receipts sr
  JOIN sync_fence.nonplay_write_admissions n ON
   (n.tenant_id,n.attempt_id,n.phase_id)=(sr.tenant_id,sr.attempt_id,sr.phase_id)
  WHERE sr.tenant_id=v_tenant AND sr.game_id=v_event.game_id
  AND sr.attempt_id=p_attempt_id AND sr.phase_id=p_phase_id
  AND sr.source_event_id=v_event.id AND sr.source_d1=v_event.d1
  AND sr.xmin=v_event_xmin AND n.xmin=v_event_xmin
  AND n.state='right_verified' AND n.source_event_id=v_event.id
  AND n.game_id=v_event.game_id AND n.internal_generation=v_event.generation
  AND n.device_id=v_binding.device_id
  AND n.nonce_digest=pg_catalog.sha256(p_binding_nonce)
  AND n.d5=v_event.d5 AND n.event_fingerprint=v_fingerprint;
  SELECT c.* INTO STRICT v_cp FROM sync_fence.ordinary_pitch_checkpoints c
  WHERE c.tenant_id=v_tenant AND c.game_id=v_event.game_id
  AND c.internal_generation=v_event.generation AND c.id=v_receipt.checkpoint_id
  AND c.revision=v_receipt.after_revision AND c.content_digest=v_receipt.after_digest
  AND c.state='current' AND c.xmin=v_event_xmin;
  SELECT frames.value INTO STRICT v_frame FROM pg_catalog.jsonb_array_elements(
   v_cp.content#>'{{content,substitutionFrames}}') AS frames(value)
  WHERE frames.value#>>'{{source,eventId}}'=v_event.id::text
  AND frames.value#>>'{{source,gameId}}'=v_event.game_id::text
  AND frames.value#>>'{{source,d1}}'=v_event.d1::text
  AND frames.value#>>'{{source,d5}}'=v_event.d5::text
  AND frames.value#>>'{{source,fingerprint}}'=v_fingerprint
  AND frames.value#>>'{{source,eventKind}}'='substitution';
  v_before:=v_frame#>'{{beforeContext,current,stateFields}}';
  v_after:=v_frame#>'{{afterContext,current,stateFields}}';
  v_bl:=v_frame#>'{{beforeContext,lineup}}'; v_al:=v_frame#>'{{afterContext,lineup}}';
  v_changed:=v_event.payload#>>'{{operation,side}}';
  SELECT n.artifact_sha256 INTO STRICT v_artifact
  FROM sync_fence.nonplay_write_admissions n
  WHERE n.tenant_id=v_tenant AND n.attempt_id=p_attempt_id AND n.phase_id=p_phase_id;
 END IF;
 WITH appearance_transition AS (SELECT v_tenant AS tenant_id,v_event.game_id AS game_id,
 v_event.id AS source_id,v_origin AS origin_kind,
 v_event.generation AS internal_generation,v_event.d1 AS d1,
 (v_before->>'state.inning')::bigint AS before_inning,
 v_before->>'state.half' AS before_half,
 (v_after->>'state.inning')::bigint AS after_inning,
 v_after->>'state.half' AS after_half,
 (v_bl#>>'{{home,pitcherId}}')::uuid AS before_home_pitcher_id,
 (v_bl#>>'{{away,pitcherId}}')::uuid AS before_away_pitcher_id,
 (v_al#>>'{{home,pitcherId}}')::uuid AS after_home_pitcher_id,
 (v_al#>>'{{away,pitcherId}}')::uuid AS after_away_pitcher_id,
 v_changed AS changed_side,v_half_completed AS half_completed,
 v_detected AS end_condition_detected,v_lock AS lock_further_play,
 v_outcome AS outcome,v_xmark AS x_mark,NULL::boolean AS released_end_condition,
 NULL::boolean AS half_started_before,v_artifact AS artifact_sha256,
 v_fingerprint AS source_fingerprint)
 SELECT pg_catalog.to_jsonb(projected) INTO STRICT v_entry FROM (
{query}
 ) projected;
 IF v_entry->>'state' IS DISTINCT FROM 'evaluated'
 THEN RAISE EXCEPTION 'pitcher entry writer unavailable' USING ERRCODE='42501'; END IF;
 IF v_entry->>'player_id' IS NULL THEN
 PERFORM sync_fence_api.assert_writer_binding(v_tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,v_binding.device_id,v_binding.game_id);
 RETURN QUERY SELECT NULL::text; RETURN; END IF;
 v_context:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 CASE WHEN v_origin='play' THEN v_payload::text ELSE v_frame::text END,'UTF8')),'hex');
 v_proof:=pg_catalog.jsonb_build_object('tenant_id',v_tenant,'game_id',v_event.game_id,
 'origin_kind',v_origin,'start_attempt_id',NULL,'source_event_id',v_event.id,
 'generation',v_event.generation,'d1',v_event.d1,'slot_version',v_slot,
 'player_id',(v_entry->>'player_id')::uuid,'defending_side',v_entry->>'defending_side',
 'inning',(v_entry->>'inning')::bigint,'half',v_entry->>'half',
 'proof_kind',v_entry->>'proof_kind','source_fingerprint',v_fingerprint,
 'artifact_sha256',v_artifact,'context_sha256',v_context);
 v_digest:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_proof::text,'UTF8')),'hex');
 INSERT INTO sync_fence.pitcher_entry_sources(
 tenant_id,game_id,proof_sha256,origin_kind,start_attempt_id,source_event_id,
 generation,d1,slot_version,player_id,defending_side,inning,half,proof_kind,
 source_fingerprint,artifact_sha256,context_sha256)
 SELECT v_tenant,v_event.game_id,v_digest,v_origin,NULL,v_event.id,
 v_event.generation,v_event.d1,v_slot,(v_entry->>'player_id')::uuid,
 v_entry->>'defending_side',(v_entry->>'inning')::bigint,v_entry->>'half',
 v_entry->>'proof_kind',v_fingerprint,v_artifact,v_context
 ON CONFLICT (tenant_id,game_id,proof_sha256) DO NOTHING;
 IF NOT EXISTS(SELECT 1 FROM sync_fence.pitcher_entry_sources e
 WHERE e.tenant_id=v_tenant AND e.game_id=v_event.game_id AND e.proof_sha256=v_digest
 AND pg_catalog.to_jsonb(e)-'proof_sha256'=v_proof)
 THEN RAISE EXCEPTION 'pitcher entry identity mismatch' USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(v_tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,v_binding.device_id,v_binding.game_id);
 RETURN QUERY SELECT v_digest;
END;
$d03_writer$;
"""
