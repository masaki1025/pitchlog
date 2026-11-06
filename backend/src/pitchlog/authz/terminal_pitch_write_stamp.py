"""v2の限定SQL producer。正式assetへの書込やDB適用は行わない。"""

from pitchlog.authz.ordinary_pitch_write_stamp import (
    CONSUME_SQL,
    PREPARE_SQL,
    _writer_equal,
)
from pitchlog.authz.ordinary_prefix_sql import candidate_read_function_bodies

_OWNER = "pitchlog_sync_right_fn_owner"
_REJECT = "RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501';"


def _prepare_sql():
    """旧writer証跡検査を共有し、v2のraw before/wire viewへ限定する。"""
    sql = PREPARE_SQL.replace(
        "prepare_ordinary_projection(", "prepare_play_prefix_projection("
    )
    sql = sql.replace("ordinary-pitch-play-v1", "play-prefix-play-v2").replace(
        "ordinary-pitch-calculation-v1", "play-prefix-calculation-v2"
    )
    sql = sql.replace(
        "source_row.payload->'calculation'->'request'->'prior'->'t2'",
        "source_row.payload->'calculation'->'request'->'source'->'t2'",
    )
    original = (
        "before_cp->'prefix_ref' IS DISTINCT FROM\nsource_row.pay"
        "load->'calculation'->'response'->'value'->'previousPref"
        "ixRef'"
    )
    replacement = """before_cp->'prefix_ref' IS DISTINCT FROM
(CASE WHEN before_cp->>'version'='1' THEN
source_row.payload->'calculation'->'response'->'value'->'previousPrefixRef'->'origin'
ELSE source_row.payload->'calculation'->'response'->'value'->'previousPrefixRef'
END)"""

    if original not in sql:
        raise ValueError("v1 prepare templateの比較面が変化しました")
    sql = sql.replace(original, replacement)
    point = " SELECT c.* INTO current_cp"
    checks = """
 IF after_cp->>'version' IS DISTINCT FROM '2'
 OR after_cp->>'artifact_sha256' IS DISTINCT FROM p->>'artifact_sha256'
 OR after_cp->'pa_start_source' IS DISTINCT FROM (CASE
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->>'plateAppearanceEnded'='true'
 THEN pg_catalog.jsonb_build_object('kind','confirmed-play','id',source_row.id::text)
 ELSE source_row.payload->'calculation'->'request'->'source'
 ->'responsibility'->'paStartSource' END)
 OR after_cp->'bridge_origin' IS DISTINCT FROM (CASE WHEN before_cp->>'version'='1'
 THEN source_row.payload->'calculation'->'request'->'source'->'bridge'
 ELSE before_cp->'bridge_origin' END)
 OR after_cp->'storage_anchor'->>'id' IS DISTINCT FROM before_cp->>'id'
 OR after_cp->'storage_anchor'->>'history_epoch' IS DISTINCT FROM
before_cp->>'history_version'
 OR after_cp->'prefix_ref'->>'version' IS DISTINCT FROM '2'
 OR after_cp->'prefix_ref'->>'scope' IS DISTINCT FROM 'play-prefix-v2'
 OR after_cp->'runners' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'runners'
 OR after_cp->'participants' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'participants'
 OR after_cp->'projection_snapshot'->'play_row' IS DISTINCT FROM p->'play_row'
 OR pg_catalog.jsonb_typeof(after_cp->'projection_snapshot'->'play_runners') IS
DISTINCT FROM 'array'
 OR pg_catalog.jsonb_array_length(after_cp->'projection_snapshot'->'play_runners')
 IS DISTINCT FROM pg_catalog.jsonb_array_length(
 source_row.payload->'calculation'->'request'->'source'->'runners')
 OR source_row.state_diff IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'newHistoryEntry'->'difference'
 OR source_row.payload->'calculation'->'request'->'playIdentity' IS DISTINCT FROM
pg_catalog.jsonb_build_object('eventId',source_row.id::text,'d5',source_row.d5::text,
 'playId',p->'play_row'->>'id')
 OR source_row.payload->'calculation'->'request'->'source'->'responsibility'->>'kind'
 IS DISTINCT FROM 'no-change'
 THEN RAISE EXCEPTION 'play prefix preparation rejected' USING ERRCODE='42501';
END IF;
"""
    checks += """
 IF source_row.payload->'calculation'->'request'->'source'
 ->'responsibility'->'paStartSource'
 IS DISTINCT FROM (CASE WHEN before_cp->>'version'='1' THEN
 pg_catalog.jsonb_build_object('kind','started-game','id',p_game_id::text)
 ELSE before_cp->'pa_start_source' END)
 OR EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.d1<=previous_d1
 AND (e.ledger_kind<>'accepted' OR e.is_tombstone OR e.replaced_at IS NOT NULL
 OR e.retired_at IS NOT NULL OR e.import_batch_id IS NOT NULL
 OR e.legacy_row_identifier IS NOT NULL OR e.migration_unverified))
 OR EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.d1<=previous_d1
 AND e.event_kind<>'play_input' AND e.d1>(CASE
 WHEN before_cp->>'version'='2'
 AND before_cp->'pa_start_source'->>'kind'='confirmed-play'
 THEN (SELECT z.d1 FROM public.operation_events z WHERE z.tenant_id=p_tenant_id
 AND z.game_id=p_game_id AND z.generation=stamp.internal_generation
 AND z.id=(before_cp->'pa_start_source'->>'id')::uuid) ELSE 0 END))
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 after_cp->'projection_snapshot'->'play_runners') r WHERE
 (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(r) k)
 IS DISTINCT FROM ARRAY['base','id','import_batch_id','play_id',
 'responsible_pitcher_id','retired_at','runner_id','status','status_source','tenant_id']::text[]
 OR r->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
 OR r->>'play_id' IS DISTINCT FROM p->'play_row'->>'id'
 OR r->>'id' IS NULL OR r->'retired_at' IS DISTINCT FROM 'null'::jsonb
 OR r->'import_batch_id' IS DISTINCT FROM 'null'::jsonb
 OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 source_row.payload->'calculation'->'request'->'source'->'runners') m
 WHERE r->>'base'=m->>'base' AND r->>'runner_id'=m->>'runnerId'
 AND r->>'responsible_pitcher_id'=m->>'responsiblePitcherId'
 AND r->>'status'=(CASE
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'='hold'
 THEN '継続'
 WHEN m->>'base'='1' AND source_row.payload->'calculation'->'response'
 ->'value'->'t1'->'runnerDefaultAdvance'->'first'->>'destination'='2' THEN '二進'
 WHEN m->>'base' IN ('1','2') AND source_row.payload->'calculation'
 ->'response'->'value'->'t1'->'runnerDefaultAdvance'
 ->(CASE m->>'base' WHEN '1' THEN 'first' ELSE 'second' END)
 ->>'destination'='3' THEN '三進'
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination'='4'
 THEN '本進' ELSE NULL END)
 AND r->>'status_source'=(CASE WHEN EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(CASE WHEN pg_catalog.jsonb_typeof(
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides')='array' THEN
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides' ELSE '[]'::jsonb END) o
 WHERE o->>'runnerBase'=m->>'base' AND o->>'destination'=
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination')
 THEN 'manual' ELSE 'auto' END)
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(CASE WHEN
 pg_catalog.jsonb_typeof(source_row.payload->'calculation'->'request'
 ->'t1'->'runnerAdvanceOverrides'->'overrides')='array' THEN
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides' ELSE '[]'::jsonb END) o
 WHERE o->>'runnerBase'=m->>'base' AND o->>'destination' IS DISTINCT FROM
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination')
 AND source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'
 IN ('hold','optional','forced')))
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'outEffect'->'targets') target WHERE pg_catalog.jsonb_typeof(target)='object'
 AND target ? 'runner')
 THEN RAISE EXCEPTION 'play prefix source or runners rejected'
 USING ERRCODE='42501'; END IF;
"""
    if point not in sql:
        raise ValueError("v1 prepare templateのpoint lockが変化しました")
    return sql.replace(point, checks + point, 1)


def _assert_sql():
    """BEFORE/AFTERで同じfresh writer/source/41列を照合する私有関数。"""
    # 旧consumeの原本/nonce/xid/xmin/device/RG1照合までを単一templateから取る。
    marker = " bootstrap:=NOT EXISTS"
    if marker not in CONSUME_SQL:
        raise ValueError("v1 consume templateの境界が変化しました")
    sql = CONSUME_SQL.split(marker)[0]
    sql = sql.replace(
        "consume_ordinary_projection(", "assert_play_prefix_projection("
    ).replace("ordinary-pitch-play-v1", "play-prefix-play-v2")
    return sql + " RETURN;\nEND;\n$ordinary$;\n"


def _finish_sql():
    """親INSERTのAFTERでrunner→checkpoint/history→印消費を不可分にする。"""
    sql = CONSUME_SQL.replace(
        "sync_right_api.consume_ordinary_projection(p_row jsonb)\nRETURNS void",
        "sync_right_api.finish_play_prefix_projection()\nRETURNS trigger",
    )
    sql = sql.replace(
        " saved_clock timestamptz;",
        " saved_clock timestamptz; p_row jsonb; expected_runner "
        "jsonb; actual_runners jsonb;",
    )
    sql = sql.replace(
        "BEGIN\n IF session_user",
        "BEGIN\n p_row:=pg_catalog.to_jsonb(NEW);\n IF TG_TABLE_SC"
        "HEMA<>'public' OR TG_TABLE_NAME<>'play_rows' OR TG_OP<>"
        "'INSERT' OR TG_WHEN<>'AFTER' THEN " + _REJECT + " END IF;\n IF session_user",
        1,
    )
    sql = sql.replace("ordinary-pitch-play-v1", "play-prefix-play-v2")
    # 旧formatには新処理をせず、既BEFOREの独立消費結果を保持する。
    sql = sql.replace(
        " p_row:=pg_catalog.to_jsonb(NEW);",
        """ p_row:=pg_catalog.to_jsonb(NEW);
 IF NOT EXISTS(SELECT 1 FROM public.operation_events e WHERE
e.tenant_id=NEW.tenant_id
 AND e.id=NEW.source_event_id AND e.payload->>'formatVersion'='play-prefix-play-v2')
 THEN RETURN NEW; END IF;""",
        1,
    )
    marker = " bootstrap:=NOT EXISTS"
    runners = """
 PERFORM sync_right_api.assert_play_prefix_projection(p_row);
 FOR expected_runner IN SELECT value FROM pg_catalog.jsonb_array_elements(
 s.next_checkpoint_content->'projection_snapshot'->'play_runners') LOOP
 INSERT INTO
public.play_runners(tenant_id,id,play_id,base,runner_id,status,status_source,
 responsible_pitcher_id,import_batch_id,retired_at)
 SELECT x.tenant_id,x.id,x.play_id,x.base,x.runner_id,x.status,x.status_source,
 x.responsible_pitcher_id,x.import_batch_id,x.retired_at
 FROM pg_catalog.jsonb_populate_record(NULL::public.play_runners,expected_runner) x;
 END LOOP;
 SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(r) ORDER BY
r.base),'[]'::jsonb)
 INTO actual_runners FROM public.play_runners r
 WHERE r.tenant_id=s.tenant_id AND r.play_id=s.play_row_id;
 IF actual_runners IS DISTINCT FROM
s.next_checkpoint_content->'projection_snapshot'->'play_runners'
 THEN RAISE EXCEPTION 'play prefix runner set rejected' USING ERRCODE='42501'; END
IF;
"""
    sql = sql.replace(marker, runners + marker, 1)
    sql = sql.replace("END;\n$ordinary$;", "RETURN NEW;\nEND;\n$ordinary$;")
    return sql


def _runner_sql():
    """appの直接runner INSERTを通さず、同AFTER内の全10列だけを認める。"""
    return f"""CREATE FUNCTION sync_right_api.guard_play_prefix_runner_insert()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $runner$
DECLARE a sync_fence.ordinary_pitch_write_admissions%ROWTYPE; own_xid text;
BEGIN
 IF session_user<>'pitchlog_app' THEN RETURN NEW; END IF;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF current_user<>'{_OWNER}' OR pg_catalog.pg_trigger_depth()<>2
 OR TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'play_runners' OR TG_OP<>'INSERT'
 OR NEW.tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR NEW.import_batch_id IS NOT NULL OR NEW.retired_at IS NOT NULL
 THEN {_REJECT} END IF;
 SELECT s.* INTO STRICT a FROM sync_fence.ordinary_pitch_write_admissions s
 JOIN sync_fence.writer_bindings b ON (b.tenant_id,b.attempt_id,b.phase_id)=
 (s.tenant_id,s.attempt_id,s.phase_id)
 WHERE s.tenant_id=NEW.tenant_id AND s.play_row_id=NEW.play_id
 AND s.state='evaluated' AND s.consumed_at IS NULL AND s.transaction_id=own_xid
 AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND b.state='open' AND b.transaction_id=own_xid
 AND b.expires_at>pg_catalog.clock_timestamp() AND {_writer_equal("s", "b")}
 FOR UPDATE OF s;
 IF a.next_checkpoint_content->>'version' IS DISTINCT FROM '2'
 OR NOT EXISTS(SELECT 1 FROM public.play_rows p WHERE p.tenant_id=NEW.tenant_id
 AND p.id=NEW.play_id AND pg_catalog.to_jsonb(p)=a.expected_play_row)
 OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_array_elements(
 a.next_checkpoint_content->'projection_snapshot'->'play_runners') x
 WHERE x=pg_catalog.to_jsonb(NEW))<>1 THEN {_REJECT} END IF;
 RETURN NEW;
END;
$runner$;
"""


def candidate_function_bodies():
    """先行宣言された7関数の実本文を決定的に生成する。"""
    reads = candidate_read_function_bodies()
    result = {
        n.replace("ordinary", "play_prefix"): sql.replace(
            "read_ordinary_checkpoint", "read_play_prefix_checkpoint"
        ).replace("lock_ordinary_checkpoint", "lock_play_prefix_checkpoint")
        for n, sql in reads.items()
        if n != "read_ordinary_history_page"
    }
    # 新pageはstorage epochとwire headを別入力で束縛する。
    page = reads["read_ordinary_history_page"].replace(
        "read_ordinary_history_page", "read_play_prefix_history_page"
    )
    page = page.replace(
        "p_history_version bigint,p_checkpoint_id uuid,\np_checkp"
        "oint_revision bigint,p_upper_watermark",
        "p_storage_history_epoch bigint,p_wire_checkpoint_id uui"
        "d,\np_wire_checkpoint_revision bigint,p_wire_history_ver"
        "sion bigint,p_upper_watermark",
    )
    page = (
        page.replace("p_history_version", "p_storage_history_epoch")
        .replace(
            "c.id=p_checkpoint_id",
            "(c.content->'prefix_ref'->'checkpoint'->>'id')::uuid=p_wire_checkpoint_id",
        )
        .replace("p_checkpoint_id", "p_wire_checkpoint_id")
        .replace("p_checkpoint_revision", "p_wire_checkpoint_revision")
    )
    page = page.replace(
        "AND c.state='current' FOR SHARE;",
        "AND c.content->>'version'='2' AND (c.content->'prefix_r"
        "ef'->>'historyVersion')::bigint=p_wire_history_version "
        "AND c.state='current' FOR SHARE;",
    )
    page = page.replace(
        "item.events->0->'payload'->>'formatVersion'='ordinary-pitch-play-v1'",
        "item.events->0->'payload'->>'formatVersion' IN ('ordina"
        "ry-pitch-play-v1','play-prefix-play-v2')",
    )
    evidence = """'source_evidence',(SELECT pg_catalog.jsonb_build_object(
 'all_play_count',pg_catalog.count(*) FILTER (WHERE e.event_kind='play_input'),
 'ordinary_play_count',pg_catalog.count(*) FILTER (WHERE e.event_kind='play_input'
 AND e.payload->>'formatVersion' IN ('first-ball-play-v1','ordinary-pitch-play-v1')
 AND
e.payload->'calculation'->'response'->'value'->'t1'->>'plateAppearanceEnded'='false'),
 'invalid_count',pg_catalog.count(*) FILTER (WHERE e.ledger_kind<>'accepted' OR
e.is_tombstone
 OR e.replaced_at IS NOT NULL OR e.retired_at IS NOT NULL OR e.import_batch_id IS
NOT NULL
 OR e.migration_unverified OR e.legacy_row_identifier IS NOT NULL),
 'non_play_count',pg_catalog.count(*) FILTER (WHERE e.event_kind<>'play_input'),
 'history_count',(SELECT pg_catalog.count(*) FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=c.tenant_id AND h.game_id=c.game_id AND
h.internal_generation=c.internal_generation
 AND h.history_version=c.history_version),
 'pa_change_count',pg_catalog.count(*) FILTER (WHERE e.event_kind<>'play_input'
 AND e.d1>CASE WHEN c.content->'pa_start_source'->>'kind'='confirmed-play' THEN
 (SELECT z.d1 FROM public.operation_events z WHERE z.tenant_id=c.tenant_id
 AND z.game_id=c.game_id AND z.generation=c.internal_generation
 AND z.id=(c.content->'pa_start_source'->>'id')::uuid) ELSE 0 END))
 FROM public.operation_events e WHERE e.tenant_id=c.tenant_id AND e.game_id=c.game_id
 AND e.generation=c.internal_generation AND e.d1<=c.confirmed_watermark)"""
    for name in ("read_play_prefix_checkpoint", "lock_play_prefix_checkpoint"):
        sql = result[name]
        sql = sql.replace(
            "'last_play_row',s.expected_play_row)",
            "'last_play_row',s.expected_play_row,'last_play_runners'"
            ",(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_js"
            "onb(pr) ORDER BY pr.base),'[]'::jsonb) FROM public.play"
            "_runners pr WHERE pr.tenant_id=c.tenant_id AND pr.play_"
            "id=s.play_row_id))",
        )
        sql = sql.replace(
            "'last_play_row',s.expected_play_row,",
            "'last_play_row',s.expected_play_row," + evidence + ",",
        )
        result[name] = sql
    page = page.replace(
        "ad.rows AS admissions,ad.n AS admission_count,fb.n AS first_count",
        "ad.rows AS admissions,ad.n AS admission_count,fb.n AS f"
        "irst_count, rn.rows AS play_runners, ad.runners AS expe"
        "cted_play_runners",
    )
    page = page.replace(
        "pg_catalog.jsonb_agg(a.expected_play_row) rows,",
        "pg_catalog.jsonb_agg(a.expected_play_row) rows, pg_cata"
        "log.jsonb_agg(a.next_checkpoint_content->'projection_sn"
        "apshot'->'play_runners') runners,",
    )
    page = page.replace(
        " ORDER BY h.d1,h.d2,h.source_event_id\n LOOP",
        " CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_a"
        "gg(pg_catalog.to_jsonb(r) ORDER BY r.base),'[]'::jsonb)"
        " rows FROM public.play_runners r WHERE r.tenant_id=h.te"
        "nant_id AND r.play_id=(pr.rows->0->>'id')::uuid) rn\n OR"
        "DER BY h.d1,h.d2,h.source_event_id\n LOOP",
    )
    page = page.replace(
        "'expected_play_row',item.admissions->0)",
        "'expected_play_row',item.admissions->0,'play_runners',i"
        "tem.play_runners,'expected_play_runners',item.expected_"
        "play_runners->0)",
    )
    page = page.replace(
        "AND a.history_entry=h.entry AND a.consumed_at IS NOT NULL)",
        "AND a.history_entry=h.entry AND a.consumed_at IS NOT NULL "
        "AND EXISTS(SELECT 1 FROM public.idempotency_ledger l "
        "WHERE l.tenant_id=a.tenant_id AND l.d5=a.d5 AND l.kind='accepted' "
        "AND l.source_fingerprint=a.event_fingerprint AND l.retired_at IS NULL "
        "AND l.import_batch_id IS NULL))",
    )
    result["read_play_prefix_history_page"] = page
    result.update(
        prepare_play_prefix_projection=_prepare_sql(),
        assert_play_prefix_projection=_assert_sql(),
        finish_play_prefix_projection=_finish_sql(),
        guard_play_prefix_runner_insert=_runner_sql(),
    )
    return result


def trigger_expectations():
    """既3triggerと新2triggerの全値を別catalog検査へ固定する。"""
    from pitchlog.authz.first_ball_write_stamp import stamp_trigger_expectations

    rows = list(stamp_trigger_expectations())
    rows.extend(
        (
            name,
            kind,
            "O",
            "sync_right_api",
            function,
            _OWNER,
            True,
            [],
            False,
            False,
            True,
            True,
            0,
            "",
            None,
            None,
        )
        for name, kind, function in (
            ("trg_play_prefix_30_project_after", 5, "finish_play_prefix_projection"),
            ("trg_play_prefix_runner_10_admit", 7, "guard_play_prefix_runner_insert"),
        )
    )
    return tuple(sorted(rows, key=lambda row: row[0]))


def trigger_query():
    """両tableの未知追加も含め観測する。旧reapplyの別queryを緩めない。"""
    from pitchlog.authz.first_ball_write_stamp import STAMP_TRIGGER_QUERY

    return STAMP_TRIGGER_QUERY.replace(
        "t.tgrelid='public.play_rows'::pg_catalog.regclass",
        "t.tgrelid IN ('public.play_rows'::pg_catalog.regclass, "
        "'public.play_runners'::pg_catalog.regclass)",
    ).replace("AND t.tgname<>'trg_play_prefix_30_project_after'", "")


def _lineup_origin_sql():
    """元端末の現在資格を要求せず、同一logical成功開始だけを返す。"""
    return f"""CREATE FUNCTION sync_right_api.read_lineup_started_origin(
p_tenant_id uuid,p_game_id uuid,p_generation bigint)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $origin$
DECLARE origins jsonb;
BEGIN
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM '{_OWNER}'
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_game_id IS NULL OR p_generation IS NULL OR p_generation<=0 THEN {_REJECT} END IF;
 SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(x)) INTO origins FROM (
 SELECT DISTINCT r.start_request_id::text AS start_request_id,
 r.device_id::text AS device_id
 FROM public.game_start_requests r JOIN public.game_start_attempts a
 ON (a.tenant_id,a.game_id,a.start_request_id,a.device_id)=
 (r.tenant_id,r.game_id,r.start_request_id,r.device_id)
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND a.outcome='committed'
 LIMIT 2) x;
 IF origins IS NULL OR pg_catalog.jsonb_array_length(origins)<>1 THEN {_REJECT} END IF;
 RETURN QUERY SELECT (origins->0)::text;
END;
$origin$;
"""


def _v3_prepare_sql():
    """同じwriter検証を保ち、v3の実源泉/全比較面だけを追加する。"""
    sql = (
        PREPARE_SQL.replace(
            "prepare_ordinary_projection(", "prepare_play_prefix_projection("
        )
        .replace("ordinary-pitch-play-v1", "play-prefix-play-v3")
        .replace("ordinary-pitch-calculation-v1", "play-prefix-calculation-v3")
        .replace("->'prior'->'t2'", "->'source'->'t2'")
    )
    checks = """
 IF before_cp->>'version' IS DISTINCT FROM '3' OR after_cp->>'version' IS DISTINCT
FROM '3'
 OR before_cp->'source_origin' IS DISTINCT FROM after_cp->'source_origin'
 OR before_cp->'source_origin' IS DISTINCT FROM before_cp->'prefix_ref'->'origin'
 OR after_cp->'source_origin' IS DISTINCT FROM after_cp->'prefix_ref'->'origin'
 OR before_cp->'lineup' IS DISTINCT FROM after_cp->'lineup'
 OR after_cp->'lineup' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'lineup'
 OR before_cp->'roster_source_digest' IS DISTINCT FROM
after_cp->'roster_source_digest'
 OR after_cp->'roster_digest' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'rosterDigest'
 OR after_cp->'participants' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'participants'
 OR before_cp->'participants' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'beforeParticipants'
 OR before_cp->'participants' IS DISTINCT FROM
source_row.payload->'calculation'->'request'->'source'->'participants'
 OR after_cp->'pa_start_source' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'nextResponsibility'->'paStartSource'
 OR after_cp->'runners' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'runners'
 OR after_cp->'previous_prefix_ref' IS DISTINCT FROM before_cp->'prefix_ref'
 OR before_cp->'storage_anchor' IS DISTINCT FROM after_cp->'storage_anchor'
 OR after_cp->'storage_anchor'->>'id' IS DISTINCT FROM before_cp->>'id'
 OR after_cp->'storage_anchor'->>'history_epoch' IS DISTINCT FROM
before_cp->>'history_version'
 OR after_cp->'prefix_ref'->>'version' IS DISTINCT FROM '3'
 OR after_cp->'prefix_ref'->>'scope' IS DISTINCT FROM 'play-prefix-v3'
 OR after_cp->'projection_snapshot'->'play_row' IS DISTINCT FROM p->'play_row'
 OR pg_catalog.jsonb_typeof(after_cp->'projection_snapshot'->'play_runners') IS
DISTINCT FROM 'array'
 OR p->'play_row'->>'batter_id' IS DISTINCT FROM
before_cp->'participants'->>'batterId'
 OR p->'play_row'->>'pitcher_id' IS DISTINCT FROM
before_cp->'participants'->>'pitcherId'
 OR p->'play_row'->>'catcher_id' IS DISTINCT FROM
before_cp->'participants'->>'catcherId'
 OR before_cp->'source_origin'->>'eventId' IS DISTINCT FROM
 (SELECT r.record_json::jsonb->>'start_request_id' FROM
sync_right_api.read_lineup_started_origin(
p_tenant_id,p_game_id,stamp.internal_generation) r)
 OR EXISTS(SELECT 1 FROM public.operation_events e WHERE e.tenant_id=p_tenant_id AND
e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.d1<=previous_d1
 AND (e.ledger_kind<>'accepted' OR e.is_tombstone OR e.replaced_at IS NOT NULL OR
e.retired_at IS NOT NULL
 OR e.import_batch_id IS NOT NULL OR e.migration_unverified OR
e.legacy_row_identifier IS NOT NULL OR e.event_kind<>'play_input'))
 THEN RAISE EXCEPTION 'lineup source mismatch' USING ERRCODE='42501'; END IF;
"""
    marker = " SELECT c.* INTO current_cp"
    if marker not in sql:
        raise ValueError("prepare共有templateが変更されました")
    runner_template = _prepare_sql()
    begin = runner_template.index(
        " OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(\n "
        "after_cp->'projection_snapshot'->'play_runners') r WHERE"
    )
    end = runner_template.index(
        " THEN RAISE EXCEPTION 'play prefix source or runners rejected'", begin
    )
    runner_checks = runner_template[begin:end]
    checks += (
        """
 IF pg_catalog.jsonb_array_length(after_cp->'projection_snapshot'->'play_runners')
 IS DISTINCT FROM
pg_catalog.jsonb_array_length(source_row.payload->'calculation'->'request'->'source'->'runners')
 OR source_row.state_diff IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'newHistoryEntry'->'difference'
 OR source_row.payload->'calculation'->'request'->'playIdentity' IS DISTINCT FROM
 pg_catalog.jsonb_build_object('eventId',source_row.id::text,'d5',source_row.d5::text,'playId',p->'play_row'->>'id')
 OR
source_row.payload->'calculation'->'request'->'source'->'responsibility'->>'kind' IS
DISTINCT FROM 'no-change'
 OR
source_row.payload->'calculation'->'request'->'source'->'responsibility'
->'paStartSource' IS DISTINCT FROM before_cp->'pa_start_source'
"""
        + runner_checks
        + " THEN RAISE EXCEPTION 'lineup physical source rejected' "
        "USING ERRCODE='42501'; END IF;\n"
    )
    # 新安打の12観測と同41物理行だけを、実source/roster/語彙へ結合する。
    sql = sql.replace("DECLARE p jsonb;", "DECLARE p jsonb; batted_obs jsonb;", 1)
    checks += r"""
 -- 新安打だけの閉分岐。旧writer/原本/nonce検査は変更しない。
 batted_obs:=source_row.payload->'observations';
 IF source_row.payload->'calculation'->'request'->'t1'->>'resultId'
 IN ('batting-result.single','batting-result.double',
 'batting-result.triple','batting-result.home-run')
 OR batted_obs ? 'battedBall' THEN
  IF pg_catalog.jsonb_typeof(batted_obs) IS DISTINCT FROM 'object'
  OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
  pg_catalog.jsonb_object_keys(batted_obs) k)
  IS DISTINCT FROM ARRAY['battedBall','battingSide','course','interferenceRuling',
  'officialScoringPayload','pitchSpeed','pitchTypeKey','resultId',
  'runnerAdvanceOverridesByRunner','stance','thirdOutObservation','thirdOutTimingByRunner']::text[]
  OR pg_catalog.jsonb_typeof(batted_obs->'resultId') IS DISTINCT FROM 'string'
  OR batted_obs->>'resultId' NOT IN ('batting-result.single','batting-result.double',
  'batting-result.triple','batting-result.home-run')
  OR batted_obs->>'resultId' IS DISTINCT FROM
  source_row.payload->'calculation'->'request'->'t1'->>'resultId'
  OR batted_obs->'officialScoringPayload' IS DISTINCT FROM
  '{"kind":"no-error","errorCount":"0","fielders":[]}'::jsonb
  OR batted_obs->'interferenceRuling' IS DISTINCT FROM '{"kind":"not-required"}'::jsonb
  OR (
   batted_obs->'runnerAdvanceOverridesByRunner' IS DISTINCT FROM
   '{"kind":"not-applied","overrides":[]}'::jsonb
   AND batted_obs->'runnerAdvanceOverridesByRunner' IS DISTINCT FROM
   source_row.payload->'calculation'->'request'->'t1'->'runnerAdvanceOverrides')
  OR (
   batted_obs->'runnerAdvanceOverridesByRunner' =
   '{"kind":"not-applied","overrides":[]}'::jsonb
   AND source_row.payload->'calculation'->'request'->'t1'
   ->>'runnerAdvanceOverrides' IS DISTINCT FROM 'not-applied')
  OR batted_obs->'thirdOutObservation' IS DISTINCT FROM '{"kind":"none"}'::jsonb
  OR batted_obs->'thirdOutTimingByRunner' IS DISTINCT FROM '{}'::jsonb
  OR source_row.payload->'calculation'->'request'->'t1'->>'officialScoringPayload'
  IS DISTINCT FROM 'no-error'
  OR source_row.payload->'calculation'->'request'->'t1'->>'interferenceRuling'
  IS DISTINCT FROM 'not-required'
  OR source_row.payload->'calculation'->'request'->'t1'->>'thirdOutObservation'
  IS DISTINCT FROM 'none'
  OR pg_catalog.jsonb_typeof(batted_obs->'battedBall') IS DISTINCT FROM 'object'
  OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
  pg_catalog.jsonb_object_keys(batted_obs->'battedBall') k)
  IS DISTINCT FROM ARRAY['hitX','hitY','rawFielderPosition','resolvedFielderId',
  'strengthKey','typeKey']::text[]
  OR p->'play_row'->>'event_kind' IS DISTINCT FROM 'pitch'
  OR p->'play_row'->>'batting_result_key' IS DISTINCT FROM batted_obs->>'resultId'
  OR p->'play_row'->>'pitch_type_key' IS DISTINCT FROM batted_obs->>'pitchTypeKey'
  OR p->'play_row'->'raw_fielder_position' IS DISTINCT FROM
  batted_obs->'battedBall'->'rawFielderPosition'
  OR p->'play_row'->'resolved_fielder_id' IS DISTINCT FROM
  batted_obs->'battedBall'->'resolvedFielderId'
  OR p->'play_row'->'batted_ball_type' IS DISTINCT FROM
  batted_obs->'battedBall'->'typeKey'
  OR p->'play_row'->'batted_ball_strength' IS DISTINCT FROM
  batted_obs->'battedBall'->'strengthKey'
  OR (batted_obs->'battedBall'->'hitX'='null'::jsonb AND
  p->'play_row'->'hit_x' IS DISTINCT FROM 'null'::jsonb)
  OR (batted_obs->'battedBall'->'hitY'='null'::jsonb AND
  p->'play_row'->'hit_y' IS DISTINCT FROM 'null'::jsonb)
  OR (batted_obs->'battedBall'->'hitX'<>'null'::jsonb AND
  (pg_catalog.jsonb_typeof(batted_obs->'battedBall'->'hitX') IS DISTINCT FROM 'string'
  OR NOT ((batted_obs->'battedBall'->>'hitX')::numeric BETWEEN 0 AND 1)
  OR (p->'play_row'->>'hit_x')::double precision IS DISTINCT FROM
  (batted_obs->'battedBall'->>'hitX')::double precision))
  OR (batted_obs->'battedBall'->'hitY'<>'null'::jsonb AND
  (pg_catalog.jsonb_typeof(batted_obs->'battedBall'->'hitY') IS DISTINCT FROM 'string'
  OR NOT ((batted_obs->'battedBall'->>'hitY')::numeric BETWEEN 0 AND 1)
  OR (p->'play_row'->>'hit_y')::double precision IS DISTINCT FROM
  (batted_obs->'battedBall'->>'hitY')::double precision))
  OR NOT EXISTS(SELECT 1 FROM public.tenant_vocabularies v
  WHERE v.tenant_id=p_tenant_id AND v.key=batted_obs->>'pitchTypeKey'
  AND v.category='pitch_type' AND NOT v.disabled)
  OR NOT EXISTS(SELECT 1 FROM public.admin_vocabularies v
  WHERE v.key=batted_obs->>'resultId' AND v.category='batting_result'
  AND NOT v.disabled)
  OR (batted_obs->'battedBall'->'typeKey'<>'null'::jsonb AND NOT EXISTS(
  SELECT 1 FROM public.admin_vocabularies v
  WHERE v.key=batted_obs->'battedBall'->>'typeKey' AND v.category='batted_ball'
  AND NOT v.disabled))
  OR (batted_obs->'battedBall'->'strengthKey'<>'null'::jsonb AND NOT EXISTS(
  SELECT 1 FROM public.admin_vocabularies v
  WHERE v.key=batted_obs->'battedBall'->>'strengthKey' AND v.category='batted_ball'
  AND NOT v.disabled))
  OR (batted_obs->'battedBall'->'resolvedFielderId'<>'null'::jsonb AND NOT EXISTS(
   SELECT 1 FROM pg_catalog.jsonb_array_elements(p->'roster'->'teams') team,
   LATERAL pg_catalog.jsonb_array_elements(team->'participants') player
   WHERE team->>'side'=(CASE before_cp->'after'->'stateFields'->>'state.half'
   WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' ELSE '' END)
   AND player->'player'->>'player_id'=batted_obs->'battedBall'->>'resolvedFielderId'
   AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(player->'roles') role
   WHERE role->>'kind'='fielding')))
  THEN RAISE EXCEPTION 'batted hit physical source rejected'
  USING ERRCODE='42501'; END IF;
 END IF;
"""
    return sql.replace(marker, checks + marker, 1)


def _dispatch_sql(old_sql, new_sql, predicate):
    """既blockを丸ごと保持し、追加の閉profileを外側から分岐する。"""
    import re

    def split(sql):
        match = re.fullmatch(r"(.*?AS (\$[a-z]+\$)\n)(.*)\2;\n?", sql, re.DOTALL)
        if match is None:
            raise ValueError("閉SQLのdollar境界が不一致")
        return match[1], match[2], match[3]

    head, tag, old_body = split(old_sql)
    _, _, new_body = split(new_sql)
    return (
        head.replace(tag, "$dispatch$")
        + f"BEGIN\n IF {predicate} THEN\n{new_body}\n ELSE\n{old_body}\n"
        " END IF;\nEND;\n$dispatch$;\n"
    )


_v2_function_bodies = candidate_function_bodies


def candidate_function_bodies():
    """旧7本文を保持しv3閉枝/源泉read1だけを生成する。正式writerが採否する。"""
    result = _v2_function_bodies()
    result["prepare_play_prefix_projection"] = _dispatch_sql(
        result["prepare_play_prefix_projection"],
        _v3_prepare_sql(),
        "p_preparation_json::jsonb->'next_checkpoint'->>'version'='3'",
    )
    # 根拠は呼出rowの自己申告でなく同tenant/game/source eventの実payload。
    predicate = (
        "EXISTS(SELECT 1 FROM public.operation_events e WHERE "
        "e.tenant_id=(p_row->>'tenant_id')::uuid AND "
        "e.game_id=(p_row->>'game_id')::uuid AND "
        "e.id=(p_row->>'source_event_id')::uuid AND "
        "e.payload->>'formatVersion'='play-prefix-play-v3')"
    )
    result["assert_play_prefix_projection"] = _dispatch_sql(
        result["assert_play_prefix_projection"],
        _assert_sql().replace("play-prefix-play-v2", "play-prefix-play-v3"),
        predicate,
    )
    pred_trigger = (
        "EXISTS(SELECT 1 FROM public.operation_events e WHERE "
        "e.tenant_id=NEW.tenant_id AND e.game_id=NEW.game_id AND "
        "e.id=NEW.source_event_id AND "
        "e.payload->>'formatVersion'='play-prefix-play-v3')"
    )
    result["finish_play_prefix_projection"] = _dispatch_sql(
        result["finish_play_prefix_projection"],
        _finish_sql().replace("play-prefix-play-v2", "play-prefix-play-v3"),
        pred_trigger,
    )
    result["guard_play_prefix_runner_insert"] = result[
        "guard_play_prefix_runner_insert"
    ].replace(
        "a.next_checkpoint_content->>'version' IS DISTINCT FROM '2'",
        "(a.next_checkpoint_content->>'version' IS DISTINCT FROM '2' "
        "AND a.next_checkpoint_content->>'version' IS DISTINCT FROM '3')",
    )
    result["read_play_prefix_history_page"] = (
        result["read_play_prefix_history_page"]
        .replace("c.content->>'version'='2'", "c.content->>'version' IN ('2','3')")
        .replace(
            "'ordinary-pitch-play-v1','play-prefix-play-v2'",
            "'ordinary-pitch-play-v1','play-prefix-play-v2','play-prefix-play-v3'",
        )
    )
    for name in ("read_play_prefix_checkpoint", "lock_play_prefix_checkpoint"):
        target = "pg_catalog.to_jsonb(c) ||"
        last = """ || CASE WHEN c.content->>'version'='3' THEN
pg_catalog.jsonb_build_object('last_history',
(SELECT pg_catalog.to_jsonb(h) FROM sync_fence.ordinary_pitch_history h
WHERE h.tenant_id=c.tenant_id AND h.game_id=c.game_id AND
h.internal_generation=c.internal_generation
AND h.history_version=c.history_version AND
h.source_event_id=(c.content->'last_source'->>'id')::uuid)) ELSE '{}'::jsonb END"""
        if target not in result[name]:
            raise ValueError("checkpoint read共有templateが変更されました")
        result[name] = result[name].replace(
            target, "pg_catalog.to_jsonb(c)" + last + " ||", 1
        )
    result["read_lineup_started_origin"] = _lineup_origin_sql()
    result = _nonplay_normal_functions(result)
    return {
        name: sql.replace(
            "CREATE FUNCTION\nsync_right_api.", "CREATE FUNCTION sync_right_api."
        )
        for name, sql in result.items()
    }


def _nonplay_normal_prepare_sql():
    """既真正stamp/nonce/xmin部を共有し、NP normalの全保存値を閉じる。"""
    sql = PREPARE_SQL.replace(
        "prepare_ordinary_projection(", "prepare_play_prefix_projection("
    )
    point = " IF source_row.payload->>'formatVersion'"
    sql = sql.split(point)[0]
    sql = sql.replace(
        "own_xid text; row_xmin text; previous_d1 bigint;",
        "own_xid text; row_xmin text; previous_d1 bigint; q jsonb; v jsonb; "
        "expected_cp jsonb; expected_head jsonb; expected_context jsonb;",
    )
    result = (
        sql
        + f"""
 q:=source_row.payload->'calculation'->'request';
 v:=source_row.payload->'calculation'->'response'->'value';
 SELECT c.* INTO STRICT current_cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current' FOR UPDATE;
 expected_head:=pg_catalog.jsonb_build_object('eventId',source_row.id::text,
 'gameId',p_game_id::text,'generation',stamp.wire_d4,'d1',source_row.d1::text,
 'd5',source_row.d5::text,'fingerprint',stamp.event_fingerprint,'eventKind',
 'play_input');
 expected_context:=pg_catalog.jsonb_build_object('current',v->'t1'->'after',
 'rules',before_cp->'content'->'restored'->'rules',
 'rulesDigest',before_cp->'content'->'restored'->'rulesDigest',
 'layoutDigest',before_cp->'content'->'restored'->'layoutDigest',
 'rosterDigest',v->'rosterDigest','lineup',v->'lineup','participants',v->'participants',
 'runners',v->'runners','responsibility',v->'nextResponsibility','lastPlayEvaluation',
 v->'t2');
 IF before_cp->'content'->'restored' ? 'substitutionState' THEN
 IF pg_catalog.jsonb_typeof(
 after_cp->'checkpoint'->'content'->'restored'->'substitutionState')
 IS DISTINCT FROM 'object' THEN {_REJECT} END IF;
 expected_context:=expected_context||pg_catalog.jsonb_build_object(
 'substitutionState',
 after_cp->'checkpoint'->'content'->'restored'->'substitutionState');
 ELSIF after_cp->'checkpoint'->'content'->'restored' ? 'substitutionState'
 THEN {_REJECT} END IF;
 expected_cp:=before_cp->'content'||pg_catalog.jsonb_build_object(
 'd3',source_row.d1::text,'d1Head',pg_catalog.jsonb_build_object('kind',
 'accepted-event','source',expected_head),
 'projectionHead',pg_catalog.jsonb_build_object('kind','d1-event','source',
 expected_head),
 'activeHead',pg_catalog.jsonb_build_object('source',expected_head,'playId',
 p->'play_row'->>'id',
 'd2',source_row.d2::text,'physicalPlayNumber',p->'play_row'->>'play_number'),
 'activeDepth',((before_cp->'content'->>'activeDepth')::bigint+1)::text,
 'historyVersion',((before_cp->'content'->>'historyVersion')::bigint+1)::text,
 'nextPhysicalPlayNumber',
 ((before_cp->'content'->>'nextPhysicalPlayNumber')::bigint+1)::text,
 'restored',expected_context);
 IF source_row.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'
 OR source_row.payload->'calculation'->>'formatVersion' IS DISTINCT FROM
 'nonplay-prefix-calculation-v1'
 OR source_row.payload->'calculation'->>'artifactSha256' IS DISTINCT FROM
 p->>'artifact_sha256'
 OR q->>'version' IS DISTINCT FROM 'nonplay-continuation-v1'
 OR q->'source'->'checkpoint' IS DISTINCT FROM before_cp
 OR q->'prefixRef' IS DISTINCT FROM before_cp->'ref'
 OR q->'rules' IS DISTINCT FROM before_cp->'content'->'restored'->'rules'
 OR q->'t1'->'before' IS DISTINCT FROM before_cp->'content'->'restored'->'current'
 OR q->'t1'->>'resultId' IS DISTINCT FROM 'batting-result.ball'
 OR q->'sourcePosition' IS DISTINCT FROM pg_catalog.jsonb_build_object(
 'd1',source_row.d1::text,'d2',source_row.d2::text,'appliedWatermark',previous_d1::text)
 OR q->'playIdentity' IS DISTINCT FROM pg_catalog.jsonb_build_object(
 'eventId',source_row.id::text,'d5',source_row.d5::text,'playId',p->'play_row'->>'id')
 OR v->'previousPrefixRef' IS DISTINCT FROM before_cp->'ref'
 OR v->'nextPrefixRef' IS DISTINCT FROM q->'nextCheckpoint'
 OR v->'playIdentity' IS DISTINCT FROM q->'playIdentity'
 OR v->'sourcePosition' IS DISTINCT FROM q->'sourcePosition'
 OR v->>'executionArtifactSha256' IS DISTINCT FROM p->>'artifact_sha256'
 OR before_cp->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 OR before_cp->'content'->'scope' IS DISTINCT FROM pg_catalog.jsonb_build_object(
 'tenantId',p_tenant_id::text,'gameId',p_game_id::text,'generation',stamp.wire_d4)
 OR before_cp->'content'->>'executionArtifactSha256' IS DISTINCT FROM
 p->>'artifact_sha256'
 OR current_cp.content IS DISTINCT FROM before_cp OR current_cp.roster IS DISTINCT FROM
 p->'roster'
 OR current_cp.id::text IS DISTINCT FROM before_cp->'ref'->>'id'
 OR current_cp.revision::text IS DISTINCT FROM before_cp->'ref'->>'revision'
 OR current_cp.content_digest IS DISTINCT FROM before_cp->'ref'->>'digest'
 OR current_cp.confirmed_watermark IS DISTINCT FROM previous_d1
 OR current_cp.applied_watermark IS DISTINCT FROM previous_d1
 OR current_cp.recovery_generation IS DISTINCT FROM stamp.recovery_generation
 OR current_cp.history_version::text IS DISTINCT FROM
 before_cp->'content'->>'storageHistoryEpoch'
 OR before_cp->'content'->>'d3' IS DISTINCT FROM previous_d1::text
 OR after_cp->>'formatVersion' IS DISTINCT FROM 'nonplay-normal-storage-v1'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
 pg_catalog.jsonb_object_keys(after_cp) k)
 IS DISTINCT FROM ARRAY['checkpoint','formatVersion','projection_snapshot']::text[]
 OR after_cp->'checkpoint'->'content' IS DISTINCT FROM expected_cp
 OR (((after_cp->'checkpoint')-'content')-'ref') IS DISTINCT FROM
 ((before_cp-'content')-'ref')
 OR ((after_cp->'checkpoint'->'ref')-'digest') IS DISTINCT FROM
 pg_catalog.jsonb_build_object('id',current_cp.id::text,'revision',
 (current_cp.revision+1)::text)
 OR after_cp->'checkpoint'->'ref'->>'digest' !~ '^[a-f0-9]{{64}}$'
 OR p->'source' IS DISTINCT FROM pg_catalog.jsonb_build_object('id',source_row.id::text,
 'tenant_id',p_tenant_id::text,'game_id',p_game_id::text,'generation',
 source_row.generation::text,
 'd1',source_row.d1::text,'d2',source_row.d2::text,'d5',source_row.d5::text,
 'source_fingerprint',stamp.event_fingerprint,'event_fingerprint',
 stamp.event_fingerprint)
 OR p->'history_entry' IS DISTINCT FROM v->'newHistoryEntry'
 OR source_row.state_diff IS DISTINCT FROM v->'newHistoryEntry'->'difference'
 OR after_cp->'projection_snapshot'->'play_row' IS DISTINCT FROM p->'play_row'
 OR p->'play_row'->>'source_event_id' IS DISTINCT FROM source_row.id::text
 OR p->'play_row'->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
 OR p->'play_row'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'play_row'->>'play_number' IS DISTINCT FROM
 before_cp->'content'->>'nextPhysicalPlayNumber'
 OR (p->'play_row'->>'play_number')::bigint IS DISTINCT FROM
 (SELECT COALESCE(pg_catalog.max(pr.play_number),0)+1 FROM public.play_rows pr
 WHERE pr.tenant_id=p_tenant_id AND pr.game_id=p_game_id)
 OR NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l WHERE l.tenant_id=p_tenant_id
 AND l.d5=stamp.d5 AND l.kind='accepted' AND
 l.source_fingerprint=stamp.event_fingerprint
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations g WHERE
 g.tenant_id=p_tenant_id
 AND g.game_id=p_game_id AND g.generation=stamp.internal_generation AND g.kind='normal'
 AND g.holder_device=stamp.device_id::text AND g.revoked_at IS NULL AND g.retired_at IS
 NULL
 AND g.recovery_generation=stamp.recovery_generation AND
 g.confirmed_watermark=source_row.d1
 AND g.applied_prefix=source_row.d1)
 OR EXISTS(SELECT 1 FROM sync_fence.first_ball_write_admissions f WHERE
 f.tenant_id=p_tenant_id
 AND f.game_id=p_game_id AND f.d5=stamp.d5 AND f.state IN ('device_verified',
 'right_verified','consumed'))
 THEN {_REJECT} END IF;
 UPDATE sync_fence.ordinary_pitch_write_admissions a SET state='evaluated',
 checkpoint_id=current_cp.id,checkpoint_revision=current_cp.revision,
 checkpoint_digest=current_cp.content_digest,
 prefix_length=(before_cp->'content'->>'activeDepth')::bigint,
 frame_id=(p->>'frame_id')::uuid,frame_digest=p->>'frame_digest',
 artifact_sha256=p->>'artifact_sha256',
 source_event_id=source_row.id,source_d1=source_row.d1,source_d2=source_row.d2,
 play_row_id=(p->'play_row'->>'id')::uuid,checkpoint_content=before_cp,
 next_checkpoint_content=after_cp,
 roster_snapshot=p->'roster',history_entry=p->'history_entry',
 expected_play_row=p->'play_row'
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND a.state='right_verified' AND a.transaction_id=own_xid
 RETURNING a.xmin::text INTO row_xmin;
 IF NOT FOUND OR row_xmin::numeric IS DISTINCT FROM pg_catalog.mod(own_xid::numeric,
 4294967296::numeric)
 THEN {_REJECT} END IF;
 RETURN QUERY SELECT true;
END;
$ordinary$;
"""
    )
    return result.replace(
        " UPDATE sync_fence.ordinary_pitch_write_admissions a SET",
        _nonplay_normal_runner_checks()
        + " UPDATE sync_fence.ordinary_pitch_write_admissions a SET",
        1,
    )


def _nonplay_normal_finish_sql():
    """既assert/runner挿入を共有し、physicalCP id/FKとhistory epochを保持する。"""
    sql = _finish_sql().replace("play-prefix-play-v2", "play-prefix-play-v3")
    sql = sql.split(" bootstrap:=NOT EXISTS")[0]
    return (
        sql
        + f"""
 after_cp:=s.next_checkpoint_content->'checkpoint';
 UPDATE sync_fence.ordinary_pitch_checkpoints c SET
 revision=(after_cp->'ref'->>'revision')::bigint,
 confirmed_watermark=s.source_d1,applied_watermark=s.source_d1,
 content_digest=after_cp->'ref'->>'digest',content=after_cp,roster=s.roster_snapshot,
 saved_at=saved_clock
 WHERE c.tenant_id=s.tenant_id AND c.game_id=s.game_id AND
 c.internal_generation=s.internal_generation
 AND c.id=s.checkpoint_id AND c.revision=s.checkpoint_revision
 AND c.content_digest=s.checkpoint_digest AND c.content=s.checkpoint_content AND
 c.state='current';
 IF NOT FOUND THEN {_REJECT} END IF;
 INSERT INTO sync_fence.ordinary_pitch_history(tenant_id,game_id,internal_generation,
 history_version,source_event_id,d1,d2,entry)
 SELECT c.tenant_id,c.game_id,c.internal_generation,c.history_version,s.source_event_id,
 s.source_d1,s.source_d2,s.history_entry FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=s.tenant_id AND c.game_id=s.game_id AND
 c.internal_generation=s.internal_generation;
 UPDATE sync_fence.ordinary_pitch_write_admissions a SET state='consumed',
 consumed_at=saved_clock
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 AND a.state='evaluated' AND a.transaction_id=own_xid AND a.frame_id=s.frame_id
 RETURNING a.xmin::text INTO row_xmin;
 IF NOT FOUND OR row_xmin::numeric IS DISTINCT FROM pg_catalog.mod(own_xid::numeric,
 4294967296::numeric)
 THEN {_REJECT} END IF;
 RETURN NEW;
END;
$ordinary$;
"""
    )


def _nonplay_normal_functions(result):
    """既本文を保持した外側の閉dispatch。任意profileは受理しない。"""
    result["prepare_play_prefix_projection"] = _dispatch_sql(
        result["prepare_play_prefix_projection"],
        _nonplay_normal_prepare_sql(),
        "p_preparation_json::jsonb->'next_checkpoint'->>'formatVersion'='nonplay-normal-storage-v1'",
    )
    pred = (
        "EXISTS(SELECT 1 FROM public.operation_events e WHERE "
        "e.tenant_id=NEW.tenant_id AND e.game_id=NEW.game_id "
        "AND e.id=NEW.source_event_id AND "
        "e.payload->'calculation'->>'formatVersion'='nonplay-prefix-calculation-v1')"
    )
    result["finish_play_prefix_projection"] = _dispatch_sql(
        result["finish_play_prefix_projection"], _nonplay_normal_finish_sql(), pred
    )
    result["guard_play_prefix_runner_insert"] = result[
        "guard_play_prefix_runner_insert"
    ].replace(
        "AND a.next_checkpoint_content->>'version' IS DISTINCT FROM '3')",
        "AND a.next_checkpoint_content->>'version' IS DISTINCT FROM '3' AND "
        "a.next_checkpoint_content->>'formatVersion' IS DISTINCT FROM "
        "'nonplay-normal-storage-v1')",
    )
    return result


def _nonplay_normal_runner_checks():
    """既10列/hold検査を同じsource文脈へ写す。走塁計算を追加しない。"""
    template = _prepare_sql()
    begin = template.index(
        " OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(\n "
        "after_cp->'projection_snapshot'->'play_runners') r WHERE"
    )
    end = template.index(
        " THEN RAISE EXCEPTION 'play prefix source or runners rejected'", begin
    )
    checks = template[begin:end].replace(
        "source_row.payload->'calculation'->'request'->'source'->'runners'",
        "source_row.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored'->'runners'",
    )
    return (
        """
 IF pg_catalog.jsonb_typeof(after_cp->'projection_snapshot') IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k)
 FROM pg_catalog.jsonb_object_keys(after_cp->'projection_snapshot') k)
 IS DISTINCT FROM ARRAY['play_row','play_runners']::text[]
 OR pg_catalog.jsonb_typeof(after_cp->'projection_snapshot'->'play_runners')
 IS DISTINCT FROM 'array'
 OR pg_catalog.jsonb_array_length(after_cp->'projection_snapshot'->'play_runners')
 IS DISTINCT FROM pg_catalog.jsonb_array_length(
 before_cp->'content'->'restored'->'runners')
 OR source_row.payload->'participants' IS DISTINCT FROM
 before_cp->'content'->'restored'->'participants'
 OR v->'beforeParticipants' IS DISTINCT FROM source_row.payload->'participants'
 OR v->'responsibility' IS DISTINCT FROM
 before_cp->'content'->'restored'->'responsibility'
 OR (before_cp->'content'->'restored'->'responsibility'->>'kind'
 IS DISTINCT FROM 'no-change' AND
 before_cp->'content'->'restored'->'responsibility'->>'kind'
 IS DISTINCT FROM 'changed-mid-plate-appearance')
 OR p->'play_row'->>'batter_id' IS DISTINCT FROM
 before_cp->'content'->'restored'->'participants'->>'batterId'
 OR p->'play_row'->>'pitcher_id' IS DISTINCT FROM
 before_cp->'content'->'restored'->'participants'->>'pitcherId'
 OR p->'play_row'->>'catcher_id' IS DISTINCT FROM
 before_cp->'content'->'restored'->'participants'->>'catcherId'
"""
        + checks
        + " THEN "
        + _REJECT
        + " END IF;\n"
    )
