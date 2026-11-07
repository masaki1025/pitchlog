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
    from pitchlog.authz.stats_primitive_product import _add_column

    declarations = {"functions": functions, "column_acl_expectations": []}
    for table in ("stats_primitive_sources", "stats_fact_versions"):
        _add_column(declarations, bodies, "sync_fence", table, "xmin", ["SELECT"])
    return declarations, bodies


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
    result.extend(
        bodies["column_acl_expectation|" + row["expectation_id"]]
        for row in declarations["column_acl_expectations"]
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
ALTER TABLE sync_fence.pitcher_entry_sources OWNER TO pitchlog_owner;
ALTER TABLE sync_fence.pitcher_entry_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.pitcher_entry_sources FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT ON sync_fence.pitcher_entry_sources
TO pitchlog_initial_fn_owner,pitchlog_sync_right_fn_owner;
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
 v_payload jsonb; v_value jsonb;
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
  SELECT s.* INTO STRICT v_source FROM sync_fence.stats_primitive_sources s
  JOIN sync_fence.stats_fact_versions v ON (v.tenant_id,v.game_id,v.id)=
   (s.tenant_id,s.game_id,s.fact_version_id)
  WHERE s.tenant_id=v_tenant AND s.game_id=v_event.game_id
  AND s.source_event_id=v_event.id
  AND s.attempt_id=p_attempt_id AND s.phase_id=p_phase_id
  AND s.recording_generation=v_event.generation AND s.d1=v_event.d1
  AND s.d2=v_event.d2 AND s.wire_d4=v_binding.wire_d4
  AND s.source_fingerprint=v_fingerprint AND s.slot_version=v_slot
  AND v.is_current AND v.invalidated_at IS NULL AND v.completion_state='current_open'
  AND v.model_sha256='{SOURCE_MODEL_HASH}' AND v.revision>=1 AND v.source_count>=1
  AND v.source_set_sha256 ~ '^[a-f0-9]{{64}}$'
  AND s.xmin=v_event_xmin AND v.xmin=v_event_xmin;
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
  AND n.state='right_verified' AND n.transaction_id=v_xid
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
  AND frames.value#>>'{{source,generation}}'=v_binding.wire_d4
  AND frames.value#>>'{{source,d1}}'=v_event.d1::text
  AND frames.value#>>'{{source,d5}}'=v_event.d5::text
  AND frames.value#>>'{{source,fingerprint}}'=v_fingerprint
  AND frames.value#>>'{{source,eventKind}}'='substitution';
  v_before:=v_frame#>'{{beforeContext,current,stateFields}}';
  v_after:=v_frame#>'{{afterContext,current,stateFields}}';
  v_bl:=v_frame#>'{{beforeContext,lineup}}'; v_al:=v_frame#>'{{afterContext,lineup}}';
  v_changed:=v_event.payload#>>'{{operation,side}}';
  v_artifact:=v_cp.content#>>'{{content,executionArtifactSha256}}';
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


def _candidate_context_guards() -> tuple[str, str]:
    """既readonlyの真正CP検査を再利用し、同RR内で行lockだけを不要にする。"""
    from pitchlog.authz.nonplay_prefix_read_sql import (
        _legacy_read_sql,
        candidate_read_function_bodies,
    )

    reject = (
        "RAISE EXCEPTION 'pitcher appearance context rejected' USING ERRCODE='42501';"
    )
    rendered = candidate_read_function_bodies()["read_nonplay_active_history"]
    marker = " SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c"
    # dispatch後半が非play原本、legacyは同じ唯一factoryから直接描画する。
    normal = rendered[rendered.rindex(marker) :]
    legacy = _legacy_read_sql("D03_ACTIVE_QUERY_NOT_EXECUTED", reject)
    legacy = legacy[legacy.index(marker) :]
    guards = []
    for source in (legacy, normal):
        boundary = " WITH active AS ("
        if boundary not in source:
            raise ValueError("既CP検査の閉境界が不一致")
        guard = source.split(boundary, 1)[0]
        lock = " FOR SHARE OF c;"
        if guard.count(lock) != 1:
            raise ValueError("既CPの行lock位置が不一致")
        # RR/ROはこの関数全体で強制。全検査が同一snapshotを読み、書込資格は発行しない。
        guard = guard.replace(lock, ";")
        if "FOR SHARE" in guard or "FOR UPDATE" in guard:
            raise ValueError("登板の同RR読取へ書込lockが残っています")
        if "source_fingerprint" not in guard or "xmin" not in guard:
            raise ValueError("既CPの真正受理印検査が欠落")
        guards.append(guard)
    return guards[0], guards[1]


def candidate_appearance_context_function() -> str:
    """既CP全資格を同RR/ROで検証する内部読取候補。登板集合の完成とは別。"""
    legacy, normal = _candidate_context_guards()
    return f"""CREATE FUNCTION stats_api.read_pitcher_appearance_context(
 p_tenant_id uuid,p_game_id uuid)
RETURNS TABLE(context_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_context$
DECLARE cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 p_generation bigint; p_checkpoint_id uuid; p_revision bigint; p_epoch bigint;
 p_d3 bigint; p_logical_version bigint; physical_xmin xid; chain jsonb;
BEGIN
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL
 OR p_tenant_id IS DISTINCT FROM NULLIF(
 pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR pg_catalog.current_setting('transaction_isolation')
 IS DISTINCT FROM 'repeatable read'
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'
 THEN RAISE EXCEPTION 'pitcher appearance readonly boundary rejected'
 USING ERRCODE='42501'; END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 JOIN public.recording_generations g ON (g.tenant_id,g.game_id,g.generation)=
 (c.tenant_id,c.game_id,c.internal_generation)
 JOIN public.games game ON (game.tenant_id,game.id)=(c.tenant_id,c.game_id)
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id AND c.state='current'
 AND g.kind='normal' AND g.revoked_at IS NULL AND g.retired_at IS NULL
 AND g.import_batch_id IS NULL AND game.started_at IS NOT NULL
 AND game.hidden_at IS NULL AND game.trashed_at IS NULL
 AND game.import_batch_id IS NULL AND game.status IN ('in_progress','finished');
 p_generation:=cp.internal_generation; p_checkpoint_id:=cp.id;
 p_revision:=cp.revision; p_epoch:=cp.history_version; p_d3:=cp.confirmed_watermark;
 IF cp.content->>'version'='3' THEN
  p_logical_version:=(cp.content#>>'{{prefix_ref,historyVersion}}')::bigint;
{legacy}
 ELSIF cp.content->>'formatVersion'='nonplay-prefix-checkpoint-v1' THEN
  p_logical_version:=(cp.content#>>'{{content,historyVersion}}')::bigint;
{normal}
 ELSE RAISE EXCEPTION 'pitcher appearance checkpoint profile unavailable'
 USING ERRCODE='42501'; END IF;
 IF p_logical_version IS NULL OR p_logical_version<1 THEN
 RAISE EXCEPTION 'pitcher appearance logical version unavailable'
 USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'checkpoint_id',cp.id,'checkpoint_generation',cp.internal_generation,
 'checkpoint_revision',cp.revision,'checkpoint_digest',cp.content_digest,
 'd3',cp.confirmed_watermark,'checkpoint',cp.content)::text;
END;
$d03_context$;
"""


def candidate_appearance_source_query() -> str:
    """正常世代の真正entryを唯一S/CP/終了receiptへ束縛し、唯一計数を接合する。"""
    from pitchlog.authz.stats_primitive_sql import _ROOT, _verified_inputs
    from pitchlog.domaingen.play_export_score import _canonical_parts
    from pitchlog.domaingen.stats_appearance import generate_appearance_bundle
    from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

    _, sections, _, _ = _verified_inputs(_ROOT)
    prefix, source_query = _canonical_parts(sections)
    bundle, _ = generate_appearance_bundle()
    projected = bundle[
        "backend/src/pitchlog/stats/generated/pitcher_entry_projection.sql"
    ]
    source_query = source_query.replace(":fact_version_id", "v.id")
    return (
        prefix
        + f""",
appearance_version AS MATERIALIZED (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 WHERE v.tenant_id=:tenant_id AND v.game_id=:game_id
 AND v.is_current AND v.invalidated_at IS NULL
 AND v.model_sha256='{SOURCE_MODEL_HASH}'
), appearance_cp AS MATERIALIZED (
 SELECT j.context_json::jsonb AS j FROM
 stats_api.read_pitcher_appearance_context(:tenant_id,:game_id) j
), appearance_lc AS MATERIALIZED (
 SELECT l.record_json::jsonb AS j FROM
 sync_right_api.read_lifecycle_display(:tenant_id,:game_id) l
), appearance_native AS MATERIALIZED (
 SELECT s.* FROM appearance_version v CROSS JOIN LATERAL ({source_query}) s
), appearance_events AS MATERIALIZED (
 SELECT e.*,l.source_fingerprint AS fingerprint
 FROM public.operation_events e JOIN canonical_scope g
 ON (g.tenant_id,g.game_id)=(e.tenant_id,e.game_id)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 WHERE e.ledger_kind='accepted' AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND l.kind='accepted' AND l.retired_at IS NULL
), appearance_frames AS MATERIALIZED (
 SELECT e.tenant_id,e.game_id,e.id,e.generation,e.d1,e.fingerprint,
 'play'::text AS origin_kind,e.payload AS context,
 e.payload#>'{{calculation,request,t1,before,stateFields}}' AS before_fields,
 e.payload#>'{{calculation,response,value,t1,after,stateFields}}' AS after_fields,
 CASE WHEN e.payload#>>'{{calculation,request,source,formatVersion}}'=
 'nonplay-prefix-source-v1' THEN
 e.payload#>'{{calculation,request,source,checkpoint,content,restored,lineup}}'
 ELSE e.payload#>'{{calculation,request,source,lineup}}' END AS before_lineup,
 e.payload#>'{{calculation,response,value,lineup}}' AS after_lineup,
 e.payload#>'{{calculation,response,value,t2}}' AS t2,
 NULL::text AS changed_side,s.artifact_sha256,s.slot_version
 FROM appearance_native s JOIN appearance_events e ON
 (e.tenant_id,e.game_id,e.id,e.generation,e.d1)=
 (s.tenant_id,s.game_id,s.source_event_id,s.recording_generation,s.d1)
 WHERE e.event_kind='play_input' AND s.slot_version=1
 AND e.payload->>'formatVersion'='play-prefix-play-v3'
 UNION ALL
 SELECT e.tenant_id,e.game_id,e.id,e.generation,e.d1,e.fingerprint,
 'substitution',frame.value,
 frame.value#>'{{beforeContext,current,stateFields}}',
 frame.value#>'{{afterContext,current,stateFields}}',
 frame.value#>'{{beforeContext,lineup}}',frame.value#>'{{afterContext,lineup}}',
 NULL::jsonb,e.payload#>>'{{operation,side}}',
 cp.j#>>'{{checkpoint,content,executionArtifactSha256}}',1::bigint
 FROM appearance_cp cp CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
 COALESCE(cp.j#>'{{checkpoint,content,substitutionFrames}}','[]'::jsonb)) frame(value)
 JOIN appearance_events e ON frame.value#>>'{{source,eventId}}'=e.id::text
 AND frame.value#>>'{{source,gameId}}'=e.game_id::text
 AND frame.value#>>'{{source,d1}}'=e.d1::text
 AND frame.value#>>'{{source,d5}}'=e.d5::text
 AND frame.value#>>'{{source,fingerprint}}'=e.fingerprint
 JOIN sync_fence.substitution_write_receipts sr ON
 (sr.tenant_id,sr.game_id,sr.source_event_id,sr.source_d1)=
 (e.tenant_id,e.game_id,e.id,e.d1)
 JOIN sync_fence.nonplay_write_admissions n ON
 (n.tenant_id,n.attempt_id,n.phase_id)=(sr.tenant_id,sr.attempt_id,sr.phase_id)
 WHERE e.event_kind='substitution' AND n.state='right_verified'
 AND frame.value#>>'{{source,generation}}'=n.wire_d4
 AND frame.value#>>'{{source,eventKind}}'='substitution'
), appearance_transition AS MATERIALIZED (
 SELECT f.tenant_id,f.game_id,f.id AS source_id,f.origin_kind,
 f.generation AS internal_generation,f.d1,
 (f.before_fields->>'state.inning')::bigint AS before_inning,
 f.before_fields->>'state.half' AS before_half,
 (f.after_fields->>'state.inning')::bigint AS after_inning,
 f.after_fields->>'state.half' AS after_half,
 (f.before_lineup#>>'{{home,pitcherId}}')::uuid AS before_home_pitcher_id,
 (f.before_lineup#>>'{{away,pitcherId}}')::uuid AS before_away_pitcher_id,
 (f.after_lineup#>>'{{home,pitcherId}}')::uuid AS after_home_pitcher_id,
 (f.after_lineup#>>'{{away,pitcherId}}')::uuid AS after_away_pitcher_id,
 f.changed_side,(f.t2#>>'{{facts,halfCompleted}}')::boolean AS half_completed,
 (f.t2#>>'{{decision,endConditionDetected}}')::boolean AS end_condition_detected,
 (f.t2#>>'{{decision,lockFurtherPlayInput}}')::boolean AS lock_further_play,
 f.t2#>>'{{decision,outcome}}' AS outcome,f.t2#>>'{{decision,xMark}}' AS x_mark,
 NULL::boolean AS released_end_condition,NULL::boolean AS half_started_before,
 f.artifact_sha256,f.fingerprint AS source_fingerprint
 FROM appearance_frames f
), appearance_projected AS MATERIALIZED ({projected}),
appearance_proofs AS MATERIALIZED (
 SELECT e.* FROM sync_fence.pitcher_entry_sources e
 WHERE e.tenant_id=:tenant_id AND e.game_id=:game_id
), appearance_valid_proofs AS MATERIALIZED (
 SELECT e.* FROM appearance_proofs e WHERE e.proof_sha256=
 pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 (pg_catalog.to_jsonb(e)-'proof_sha256')::text,'UTF8')),'hex')
), appearance_effective AS MATERIALIZED (
 SELECT e.* FROM appearance_valid_proofs e,appearance_cp cp
 WHERE e.origin_kind='start' AND e.generation=(cp.j->>'checkpoint_generation')::bigint
 AND e.proof_kind='defensive-half-entry' AND e.defending_side='home'
 AND e.inning=1 AND e.half='top' AND e.start_attempt_id IS NOT NULL
 AND e.source_event_id IS NULL AND e.d1 IS NULL AND e.slot_version IS NULL
 UNION ALL
 SELECT e.* FROM appearance_valid_proofs e JOIN appearance_projected p ON
 (e.tenant_id,e.game_id,e.origin_kind,e.source_event_id,e.generation,e.d1,e.player_id,
 e.defending_side,e.inning,e.half,e.proof_kind,e.artifact_sha256,e.source_fingerprint)=
 (p.tenant_id,p.game_id,p.origin_kind,p.source_id,p.internal_generation,p.d1,p.player_id,
 p.defending_side,p.inning,p.half,p.proof_kind,p.artifact_sha256,p.source_fingerprint)
 JOIN appearance_frames f ON f.id=p.source_id AND f.tenant_id=p.tenant_id
 AND f.game_id=p.game_id AND e.slot_version=f.slot_version
 WHERE p.state='evaluated' AND p.player_id IS NOT NULL
 AND e.context_sha256=pg_catalog.encode(pg_catalog.sha256(
 pg_catalog.convert_to(f.context::text,'UTF8')),'hex')
), appearance_completeness AS (
 SELECT (SELECT count(*) FROM appearance_version)=1
 AND (SELECT count(*) FROM appearance_cp)=1 AND (SELECT count(*) FROM appearance_lc)=1
 AND EXISTS(SELECT 1 FROM appearance_version v JOIN canonical_health h ON
 (h.tenant_id,h.game_id)=(v.tenant_id,v.game_id)
 WHERE h.unavailable_count=0 AND h.game_count=1
 AND h.canonical_source_count=v.source_count
 AND h.canonical_source_set_sha256=v.source_set_sha256
 AND v.source_count=(SELECT count(*) FROM appearance_native))
 AND NOT EXISTS(SELECT 1 FROM appearance_events e WHERE e.event_kind NOT IN
 ('play_input','substitution','game_end_declaration','game_reopen'))
 AND NOT EXISTS(SELECT 1 FROM appearance_events e WHERE e.event_kind='game_reopen'
 AND NOT EXISTS(SELECT 1 FROM sync_fence.lifecycle_write_admissions a
 WHERE (a.tenant_id,a.game_id,a.source_event_id,a.internal_generation,
 a.source_d1,a.source_d2,a.d5,a.event_fingerprint)=
 (e.tenant_id,e.game_id,e.id,e.generation,e.d1,e.d2,e.d5,e.fingerprint)
 AND a.action='reopen' AND a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.receipt_id::text=e.payload#>>'{{event,receiptId}}'
 AND a.preparation#>'{{before_source,checkpoint,content,restored,lastPlayEvaluation,
 decision,lockFurtherPlayInput}}'='false'::jsonb
 AND a.preparation#>'{{before_source,checkpoint,content,restored,current,
 stateFields,state.gameEnded}}'='true'::jsonb
 AND a.preparation#>'{{after_source,checkpoint,content,restored,current,
 stateFields,state.gameEnded}}'='false'::jsonb
 AND (a.preparation#>'{{before_source,checkpoint,content,restored}}')
 #- '{{current,stateFields,state.gameEnded}}' =
 (a.preparation#>'{{after_source,checkpoint,content,restored}}')
 #- '{{current,stateFields,state.gameEnded}}'))
 AND (SELECT count(DISTINCT generation) FROM appearance_events)=1
 AND (SELECT count(*) FROM appearance_frames WHERE origin_kind='play')=
 (SELECT count(*) FROM appearance_native)
 AND (SELECT count(*) FROM appearance_frames WHERE origin_kind='substitution')=
 (SELECT count(*) FROM appearance_events WHERE event_kind='substitution')
 AND NOT EXISTS(SELECT 1 FROM appearance_frames f WHERE f.origin_kind='play'
 AND (f.context#>>'{{calculation,response,value,executionArtifactSha256}}'
 IS DISTINCT FROM f.artifact_sha256
 OR f.t2#>>'{{facts,beforeHalf}}' IS DISTINCT FROM f.before_fields->>'state.half'
 OR f.t2#>>'{{facts,afterHalf}}' IS DISTINCT FROM f.after_fields->>'state.half'
 OR f.t2#>>'{{facts,beforeInning}}' IS DISTINCT FROM f.before_fields->>'state.inning'
 OR f.t2#>>'{{facts,afterInning}}' IS DISTINCT FROM f.after_fields->>'state.inning'))
 AND NOT EXISTS(SELECT 1 FROM appearance_frames
 GROUP BY tenant_id,game_id,id HAVING count(*)<>1)
 AND NOT EXISTS(SELECT 1 FROM appearance_effective
 GROUP BY tenant_id,game_id,proof_sha256 HAVING count(*)<>1)
 AND NOT EXISTS(SELECT 1 FROM appearance_projected WHERE state<>'evaluated'
 OR state IS NULL)
 AND (SELECT count(*) FROM appearance_effective WHERE origin_kind='start')=1
 AND (SELECT count(*) FROM appearance_effective WHERE origin_kind<>'start')=
 (SELECT count(*) FROM appearance_projected WHERE player_id IS NOT NULL)
 AND (SELECT count(*) FROM appearance_effective)=
 (SELECT count(*) FROM appearance_proofs)
 AND EXISTS(SELECT 1 FROM appearance_version v,appearance_lc l WHERE
 ((:official AND v.completion_state='confirmed_ended'
 AND l.j->>'status'='finished' AND l.j->>'activeStatsVersionId'=v.id::text
 AND l.j#>>'{{active,receiptId}}'=v.completion_receipt_id::text
 AND v.public_pointer_receipt_id=v.completion_receipt_id)
 OR (NOT :official AND v.completion_state='current_open'
 AND l.j->>'status'='in_progress' AND l.j->'active'='null'::jsonb)))
 AS complete
), appearance_scope AS MATERIALIZED (
 SELECT v.tenant_id,v.game_id,v.id AS fact_version_id,v.revision,v.source_set_sha256,
 (cp.j->>'checkpoint_id')::uuid AS checkpoint_id,
 (cp.j->>'checkpoint_generation')::bigint AS checkpoint_generation,
 (cp.j->>'checkpoint_revision')::bigint AS checkpoint_revision,
 cp.j->>'checkpoint_digest' AS checkpoint_digest,(cp.j->>'d3')::bigint AS d3,
 v.completion_receipt_id AS lifecycle_receipt_id,
 pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(COALESCE(
 (SELECT pg_catalog.string_agg(e.proof_sha256,E'\\n' ORDER BY e.proof_sha256)
 FROM appearance_effective e),'pitcher-entry-set-v1:empty'),'UTF8')),'hex')
 AS entry_set_sha256,c.complete AS supply_complete,
 (SELECT count(*) FROM appearance_effective) AS member_count
 FROM appearance_version v,appearance_cp cp,appearance_completeness c
), appearance_members AS MATERIALIZED (
 SELECT s.*,e.player_id,e.proof_kind,e.proof_sha256 AS proof_source_id
 FROM appearance_scope s JOIN appearance_effective e ON
 (e.tenant_id,e.game_id)=(s.tenant_id,s.game_id)
)
SELECT pg_catalog.jsonb_build_object(
 'scope',(SELECT pg_catalog.to_jsonb(s) FROM appearance_scope s),
 'members',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(m)
 ORDER BY m.proof_source_id) FROM appearance_members m),'[]'::jsonb))::text
"""
    )


def candidate_appearance_source_function() -> str:
    """owner-only原本供給を同RRに閉じ、不足資格をavailableへ補修しない。"""
    import re

    query = candidate_appearance_source_query()
    for name, target in {"tenant_id": "$1", "game_id": "$2", "official": "$3"}.items():
        query = re.sub(r"(?<!:):" + name + r"\b", target, query)
    literals_removed = re.sub(r"'(?:''|[^'])*'", "''", query)
    if re.search(r"(?<!:):[a-z_]", literals_removed):
        raise ValueError("登板の原本queryへ未知bindが残っています")
    return f"""CREATE FUNCTION stats_api.read_pitcher_appearance_source(
 p_tenant_id uuid,p_game_id uuid,p_official boolean)
RETURNS TABLE(record_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_source$
DECLARE query text:=$appearance_query${query}$appearance_query$;
BEGIN
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_official IS NULL
 OR p_tenant_id IS DISTINCT FROM NULLIF(
 pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR pg_catalog.current_setting('transaction_isolation')
 IS DISTINCT FROM 'repeatable read'
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'
 THEN RAISE EXCEPTION 'pitcher appearance source readonly boundary rejected'
 USING ERRCODE='42501'; END IF;
 BEGIN
  RETURN QUERY EXECUTE query USING p_tenant_id,p_game_id,p_official;
 EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS OR insufficient_privilege THEN
  -- 読取資格/原本不足だけを未供給にする。SQL不正/欠表/未知故障は503へ残す。
  RETURN QUERY SELECT '{{"scope":null,"members":[]}}'::text;
 END;
END;
$d03_source$;
"""


def candidate_appearance_read_install_sql() -> str:
    """未登録read候補をownedだけへ配置する。app/actorへ直接EXECUTEなし。"""
    statements = []
    for name, arguments, body in (
        (
            "read_pitcher_appearance_context",
            "uuid,uuid",
            candidate_appearance_context_function(),
        ),
        (
            "read_pitcher_appearance_source",
            "uuid,uuid,boolean",
            candidate_appearance_source_function(),
        ),
    ):
        identity = f"stats_api.{name}({arguments})"
        statements.extend(
            (
                body,
                f"ALTER FUNCTION {identity} OWNER TO pitchlog_sync_right_fn_owner;\n",
                f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,pitchlog_app,"
                "pitchlog_initial_actor,pitchlog_sync_binding_actor,"
                "pitchlog_initial_fn_owner;\n",
            )
        )
    return "".join(statements)
