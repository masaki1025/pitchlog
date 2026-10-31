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
 AND r->>'status'='継続' AND r->>'status_source'='auto'
 AND source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'='hold'
 AND source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->'destination'='null'::jsonb))
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
