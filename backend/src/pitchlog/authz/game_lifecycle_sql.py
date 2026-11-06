"""真正制御admissionを同TXのCP/status/終了版へ結ぶ有限SQL producer。"""

from __future__ import annotations

import re

from pitchlog.authz.nonplay_prefix_sql import _head
from pitchlog.authz.ordinary_pitch_write_stamp import _writer_equal
from pitchlog.authz.stats_primitive_sql import (
    _ROOT,
    _credit_integrity_guard,
    _verified_inputs,
)
from pitchlog.authz.sync_right_sql import _COMMON
from pitchlog.db.game_state.stats import StatsPrimitiveFact, StatsPrimitiveSource
from pitchlog.db.writer_binding.lifecycle_models import LifecycleWriteAdmission
from pitchlog.db.writer_binding.nonplay_models import _IDENTITY

_REJECT = "RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501';"
_TABLE = "sync_fence.lifecycle_write_admissions"
_HEAD = "sync_fence.game_lifecycle_heads"


def control_bridge_guard(
    content="cp.content",
    tenant="p_tenant_id",
    game="p_game_id",
    generation="stamp.internal_generation",
):
    """登録済SQLsite内部だけが使う固定guard。caller SQLに公開しない。"""
    approved = {
        ("cp.content", "p_tenant_id", "p_game_id", "stamp.internal_generation"),
        ("cp.content", "p_tenant_id", "p_game_id", "p_generation"),
    }
    if (content, tenant, game, generation) not in approved:
        raise ValueError("終了control証拠のSQLsiteが未登録です")
    bridges = f"{content}->'content'->'controlBridges'"
    proof = f"""SELECT a.*,e.id AS original_id,r.issuance_order AS generation_order
 FROM {_TABLE} a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
 AND e.id=a.source_event_id AND e.generation=a.internal_generation AND e.d1=a.source_d1
 JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.recording_generations r ON r.tenant_id=e.tenant_id AND r.game_id=e.game_id
 AND r.generation=e.generation
 JOIN public.recording_generations current_generation ON
 current_generation.tenant_id=r.tenant_id
 AND current_generation.game_id=r.game_id AND current_generation.generation={generation}
 JOIN sync_fence.writer_bindings original_binding
 ON (original_binding.tenant_id,original_binding.attempt_id,original_binding.phase_id)
 =(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE a.tenant_id={tenant} AND a.game_id={game} AND a.state='consumed'
 AND a.consumed_at IS NOT NULL AND e.ledger_kind='accepted'
 AND e.event_kind=CASE WHEN a.action='end' THEN 'game_end_declaration' ELSE
 'game_reopen' END
 AND a.action IN ('end','reopen') AND e.d2=a.source_d2 AND e.d5=a.d5
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND slot.confirmed_version=1
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.source_fingerprint=a.event_fingerprint AND e.xmin=a.xmin AND l.xmin=a.xmin
 AND {_writer_equal("a", "original_binding")}
 AND r.issuance_order<=current_generation.issuance_order
 AND (e.generation<>{generation} OR e.d1<=cp.confirmed_watermark)
"""
    return f"""
 -- 既legacy/undoには新defaultを補完しない。presentなら全consumed原本へ閉じる。
 IF {content}->>'formatVersion'='nonplay-prefix-checkpoint-v1' THEN
 IF EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(COALESCE({bridges},'[]'::jsonb)) b(value)
 WHERE NOT EXISTS(SELECT 1 FROM ({proof}) a
 WHERE a.source_event_id=(b.value->'source'->>'eventId')::uuid
 AND a.frame_id=(b.value->>'frameId')::uuid
 AND a.action=b.value->>'action' AND a.wire_d4=b.value->'source'->>'generation'
 AND a.source_d1::text=b.value->'source'->>'d1'
 AND a.d5::text=b.value->'source'->>'d5'
 AND a.event_fingerprint=b.value->'source'->>'fingerprint'
 AND a.checkpoint_id::text=b.value->'checkpointBefore'->>'id'
 AND a.checkpoint_revision::text=b.value->'checkpointBefore'->>'revision'
 AND a.checkpoint_digest=b.value->'checkpointBefore'->>'digest'
 AND a.receipt_id::text=b.value->'kernel'->'request'->'event'->>'receiptId'
 AND a.source_event_id::text=b.value->'kernel'->'request'->'event'->>'eventId'
 AND b.value->'source'->>'gameId'={game}::text
 AND a.preparation->'after_source'->'checkpoint'->'content'->'controlBridges'->-1
 =b.value
 AND a.preparation->'event_original'->'payload'=(SELECT e.payload FROM
 public.operation_events e
 WHERE e.tenant_id={tenant} AND e.id=a.source_event_id)))
 OR EXISTS(SELECT 1 FROM ({proof}) a WHERE NOT EXISTS(
 SELECT 1 FROM pg_catalog.jsonb_array_elements(COALESCE({bridges},'[]'::jsonb)) b(value)
 WHERE b.value->'source'->>'eventId'=a.source_event_id::text))
 OR EXISTS(SELECT 1 FROM public.operation_events control_event
 JOIN public.recording_generations control_generation ON
 (control_generation.tenant_id,control_generation.game_id,control_generation.generation)
 =(control_event.tenant_id,control_event.game_id,control_event.generation)
 JOIN public.recording_generations selected_generation ON
 selected_generation.tenant_id=control_event.tenant_id
 AND selected_generation.game_id=control_event.game_id AND
 selected_generation.generation={generation}
 WHERE control_event.tenant_id={tenant} AND control_event.game_id={game}
 AND control_event.event_kind IN ('game_end_declaration','game_reopen')
 AND control_event.ledger_kind='accepted' AND control_event.replaced_at IS NULL
 AND control_event.retired_at IS NULL
 AND control_generation.issuance_order<=selected_generation.issuance_order
 AND (control_event.generation<>{generation} OR
 control_event.d1<=cp.confirmed_watermark)
 AND NOT EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(COALESCE({bridges},'[]'::jsonb)) b(value)
 WHERE b.value->'source'->>'eventId'=control_event.id::text))
 OR EXISTS(SELECT 1 FROM (SELECT count(*) AS n,count(DISTINCT
 value->'source'->>'eventId') AS unique_n
 FROM pg_catalog.jsonb_array_elements(COALESCE({bridges},'[]'::jsonb)))
 duplicate_controls
 WHERE n<>unique_n)
 OR EXISTS(SELECT 1 FROM (
 SELECT a.generation_order,a.source_d1,
 lag(a.generation_order) OVER(ORDER BY b.ordinality) AS previous_generation,
 lag(a.source_d1) OVER(ORDER BY b.ordinality) AS previous_d1
 FROM pg_catalog.jsonb_array_elements(COALESCE({bridges},'[]'::jsonb))
 WITH ORDINALITY b(value,ordinality)
 JOIN ({proof}) a ON a.source_event_id::text=b.value->'source'->>'eventId'
 ) ordered_controls WHERE previous_generation>generation_order
 OR (previous_generation=generation_order AND previous_d1>=source_d1))
 THEN {_REJECT} END IF;
 IF pg_catalog.jsonb_array_length(COALESCE({bridges},'[]'::jsonb))>0 AND NOT EXISTS(
 SELECT 1 FROM {_HEAD} lifecycle_head WHERE lifecycle_head.tenant_id={tenant}
 AND lifecycle_head.game_id={game}
 AND lifecycle_head.last_control_event_id::text=({bridges}->-1)->'source'->>'eventId'
 AND lifecycle_head.is_finished=(({bridges}->-1)->>'action'='end')
 ) THEN {_REJECT} END IF;
 END IF;
"""


def _function(name, body, result="record_json text", extra=""):
    """名前/引数は内部の固定呼出しのみ。caller SQLを受け取らない。"""
    return f"""CREATE FUNCTION sync_right_api.{name}({_COMMON},p_request_json text)
RETURNS TABLE({result}) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $lifecycle$
DECLARE stamp sync_fence.nonplay_write_admissions%ROWTYPE; own_xid text; p jsonb;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 game_row record; h {_HEAD}%ROWTYPE; {extra}
BEGIN
{_head()}
 IF stamp.state<>'right_verified' OR p_request_json IS NULL THEN {_REJECT} END IF;
 p:=p_request_json::jsonb;
{body}
END;
$lifecycle$;
"""


def _head_state_sql():
    """既game行lock下で実headを読み、過去control欠落を拒否する。"""
    return f"""
 SELECT x.tenant_id,x.id,x.status,x.trashed_at,x.hidden_at,x.import_batch_id
 INTO STRICT game_row FROM public.games x
 WHERE x.tenant_id=p_tenant_id AND x.id=p_game_id
 AND x.trashed_at IS NULL AND x.hidden_at IS NULL
 AND x.import_batch_id IS NULL;
 SELECT x.* INTO h FROM {_HEAD} x
 WHERE x.tenant_id=p_tenant_id AND x.game_id=p_game_id;
 IF NOT FOUND THEN
   IF game_row.status<>'in_progress' OR EXISTS(SELECT 1 FROM public.operation_events e
   WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
   AND e.event_kind IN ('game_end_declaration','game_reopen')
   AND e.ledger_kind='accepted' AND e.replaced_at IS NULL AND e.retired_at IS NULL
   AND e.id IS DISTINCT FROM (p->>'event_id')::uuid) THEN {_REJECT} END IF;
   lifecycle:=pg_catalog.jsonb_build_object('status','in_progress','lastVersion','0','active',NULL);
 ELSE
   IF h.is_finished IS DISTINCT FROM (game_row.status='finished')
   OR game_row.status NOT IN ('in_progress','finished') THEN {_REJECT} END IF;
   IF h.is_finished AND NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
   JOIN public.operation_events e ON e.tenant_id=v.tenant_id
   AND e.game_id=v.game_id AND e.id=h.active_end_event_id
   JOIN {_TABLE} a ON a.tenant_id=e.tenant_id AND a.game_id=e.game_id
   AND a.source_event_id=e.id AND a.receipt_id=h.active_receipt_id
   WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND
 v.id=h.active_stats_version_id
   AND v.is_current AND v.invalidated_at IS NULL AND
 v.completion_state='confirmed_ended'
   AND v.completion_receipt_id=h.active_receipt_id
   AND v.public_pointer_receipt_id=h.active_receipt_id AND a.state='consumed'
   AND a.action='end' AND e.event_kind='game_end_declaration'
   AND e.ledger_kind='accepted' AND NOT e.is_tombstone AND e.retired_at IS NULL
   AND e.replaced_at IS NULL) THEN {_REJECT} END IF;
   lifecycle:=pg_catalog.jsonb_build_object('status',game_row.status,
    'lastVersion',h.last_version::text,'active',CASE WHEN h.is_finished
     THEN pg_catalog.jsonb_build_object('version',h.last_version::text,
      'eventId',h.active_end_event_id::text,'receiptId',h.active_receipt_id::text)
     ELSE NULL END);
 END IF;
"""


def _preparation_guard():
    """prepareとconsumeの同じ全前後比較。host評価の偽boolを受け付けない。"""
    return f"""
 IF pg_catalog.jsonb_typeof(p) IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(p) k)
 IS DISTINCT FROM ARRAY['after_source','artifact_sha256','before_source','event_id',
 'event_original','frame_digest','frame_id','receipt_id','request','response',
 'source_fingerprint','storage']::text[] THEN {_REJECT} END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 AND c.recovery_generation=stamp.recovery_generation FOR UPDATE;
 IF p->'storage'->'row' IS DISTINCT FROM pg_catalog.to_jsonb(cp)
 OR p->'before_source'->'checkpoint'->'ref'->>'id' IS DISTINCT FROM cp.id::text
 OR p->'before_source'->'checkpoint'->'ref'->>'revision' IS DISTINCT FROM
 cp.revision::text
 -- v3の物理digestと既readerが導出するnonplay論理digestは別原本。
 OR (cp.content->>'version' IS DISTINCT FROM '3' AND
 p->'before_source'->'checkpoint'->'ref'->>'digest' IS DISTINCT FROM
 cp.content_digest)
 OR (cp.content->>'version'='3' AND
 (p->'before_source'->'checkpoint'->'ref'->>'digest' IS NULL OR
 p->'before_source'->'checkpoint'->'ref'->>'digest' !~ '^[a-f0-9]{{64}}$'))
 OR cp.confirmed_watermark+1<>(p->'event_original'->>'d1')::bigint
 OR cp.applied_watermark<>cp.confirmed_watermark THEN {_REJECT} END IF;
{control_bridge_guard()}
 before_cp:=p->'before_source'->'checkpoint'; after_cp:=p->'after_source'->'checkpoint';
 IF cp.content->>'version'='3' THEN
   expected_restored:=pg_catalog.jsonb_build_object('current',cp.content->'after',
    'rules',cp.content->'rules','rulesDigest',before_cp->'content'->'restored'->'rulesDigest',
    'layoutDigest',cp.content->'roster_digest','rosterDigest',cp.content->'roster_digest',
    'lineup',cp.content->'lineup','participants',cp.content->'participants',
    'runners',cp.content->'runners','responsibility',pg_catalog.jsonb_build_object('kind','no-change',
    'paStartSource',cp.content->'pa_start_source','previousPitcherId',NULL,
    'strikesAtChange',NULL,'ballsAtChange',NULL),
    'lastPlayEvaluation',cp.content->'t2');
   IF before_cp->'content'->'restored' IS DISTINCT FROM expected_restored THEN
 {_REJECT} END IF;
 ELSE
   IF cp.content->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
   OR before_cp IS DISTINCT FROM cp.content THEN {_REJECT} END IF;
 END IF;
 SELECT e.* INTO STRICT own_event FROM public.operation_events e
 JOIN public.event_slots s ON (s.tenant_id,s.game_id,s.generation,s.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.id=(p->>'event_id')::uuid
 AND e.d5=stamp.d5 AND e.ledger_kind='accepted' AND l.kind='accepted'
 AND l.source_fingerprint=stamp.event_fingerprint AND l.retired_at IS NULL
 AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.confirmed_version=1 AND NOT e.is_tombstone AND e.replaced_at IS NULL
 AND e.retired_at IS NULL AND e.import_batch_id IS NULL AND e.d2>=0;
 action:=p->'request'->>'action';
 IF action NOT IN ('end','reopen') OR own_event.event_kind IS DISTINCT FROM
 (CASE WHEN action='end' THEN 'game_end_declaration' ELSE 'game_reopen' END)
 OR own_event.payload->>'formatVersion' IS DISTINCT FROM 'native-game-lifecycle-v1'
 OR own_event.payload->>'action' IS DISTINCT FROM action
 OR NOT (
  (own_event.payload->'checkpointRef'->>'kind'='confirmed'
   AND ((own_event.payload->'checkpointRef')-'kind')=before_cp->'ref')
  OR (own_event.payload->'checkpointRef'->>'kind'='queued_predecessor'
   AND own_event.payload->'checkpointRef'=pg_catalog.jsonb_build_object(
    'kind','queued_predecessor','d4',stamp.wire_d4,'d1',own_event.d1-1,
    'd5',before_cp->'content'->'d1Head'->'source'->>'d5')
   AND before_cp->'content'->'d1Head'->'source'->>'gameId'=p_game_id::text
   AND before_cp->'content'->'d1Head'->'source'->>'generation'=stamp.wire_d4
   AND before_cp->'content'->'d1Head'->'source'->>'d1'=(own_event.d1-1)::text)
  OR (own_event.payload->'checkpointRef'->>'kind'='confirmed_prefix'
   AND own_event.payload->'checkpointRef'=pg_catalog.jsonb_build_object(
    'kind','confirmed_prefix','id',before_cp->'content'->'controlBridges'->-1
    ->'checkpointBefore'->>'id','revision',before_cp->'content'->'controlBridges'
    ->-1->'checkpointBefore'->>'revision','digest',before_cp->'content'
    ->'controlBridges'->-1->'checkpointBefore'->>'digest','d4',stamp.wire_d4,
    'd1',own_event.d1-1,'d5',before_cp->'content'->'d1Head'->'source'->>'d5')
   AND before_cp->'content'->'controlBridges'->-1->'source'
    =before_cp->'content'->'d1Head'->'source'
   AND before_cp->'content'->'d1Head'->'source'->>'gameId'=p_game_id::text
   AND before_cp->'content'->'d1Head'->'source'->>'generation'=stamp.wire_d4
   AND before_cp->'content'->'d1Head'->'source'->>'d1'=(own_event.d1-1)::text))
 OR NOT (
  (action='end' AND own_event.payload->'target'='null'::jsonb
   AND p->'request'->'target'='null'::jsonb)
  OR (action='reopen' AND
   ((own_event.payload->'target'->>'kind'='confirmed'
     AND (own_event.payload->'target')-'kind'=p->'request'->'target')
    OR (own_event.payload->'target'->>'kind'='queued_end'
     AND p->'request'->'target'=lifecycle->'active'
     AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
      COALESCE(before_cp->'content'->'controlBridges','[]'::jsonb)) b(value)
      WHERE b.value->>'action'='end'
      AND b.value->'source'->>'gameId'=p_game_id::text
      AND b.value->'source'->>'generation'=own_event.payload->'target'->>'d4'
      AND b.value->'source'->>'d1'=own_event.payload->'target'->>'d1'
      AND b.value->'source'->>'d5'=own_event.payload->'target'->>'d5'
      AND b.value->'source'->>'eventId'=own_event.payload->'target'->>'eventId'
      AND b.value->'kernel'->'request'->'event'->>'receiptId'
       =own_event.payload->'target'->>'receiptId'
      AND b.value->'kernel'->'response'->'value'->'lifecycle'->'active'
       =p->'request'->'target')))))
 OR own_event.payload->'event'->>'eventId' IS DISTINCT FROM own_event.id::text
 OR own_event.payload->'event'->>'receiptId' IS DISTINCT FROM p->>'receipt_id'
 OR p->>'source_fingerprint' IS DISTINCT FROM stamp.event_fingerprint
 OR p->'event_original'->>'event_kind' IS DISTINCT FROM own_event.event_kind
 OR p->'event_original'->'payload' IS DISTINCT FROM own_event.payload
 OR p->'event_original'->>'d4' IS DISTINCT FROM stamp.wire_d4
 OR p->'event_original'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'event_original'->>'d5' IS DISTINCT FROM own_event.d5::text
 OR (p->'event_original'->>'d1')::bigint IS DISTINCT FROM own_event.d1
 OR (p->'event_original'->>'d2')::bigint IS DISTINCT FROM own_event.d2
 OR p->'request'->'event'->>'eventId' IS DISTINCT FROM own_event.id::text
 OR p->'request'->'event'->>'receiptId' IS DISTINCT FROM p->>'receipt_id'
 OR p->'request'->'lifecycle' IS DISTINCT FROM lifecycle
 OR p->'request'->'current' IS DISTINCT FROM before_cp->'content'->'restored'->'current'
 OR p->'response'->'ok' IS DISTINCT FROM 'true'::jsonb
 OR p->'after_source'->'activeStack' IS DISTINCT FROM p->'before_source'->'activeStack'
 THEN {_REJECT} END IF;
 IF action='end' THEN
   IF game_row.status<>'in_progress' OR
   p->'request'->'target' IS DISTINCT FROM 'null'::jsonb
   OR p->'response'->'value'->'current' IS DISTINCT FROM p->'request'->'current'
   THEN {_REJECT} END IF;
   next_lifecycle:=pg_catalog.jsonb_build_object('status','finished',
    'lastVersion',((lifecycle->>'lastVersion')::bigint+1)::text,
    'active',pg_catalog.jsonb_build_object('version',((lifecycle->>'lastVersion')::bigint+1)::text,
    'eventId',own_event.id::text,'receiptId',p->>'receipt_id'));
 ELSE
   IF game_row.status<>'finished' OR p->'request'->'target' IS DISTINCT FROM
 lifecycle->'active'
   OR p->'response'->'value'->'current' IS DISTINCT FROM
    pg_catalog.jsonb_set(p->'request'->'current','{{stateFields,state.gameEnded}}','false'::jsonb)
   THEN {_REJECT} END IF;
   next_lifecycle:=pg_catalog.jsonb_build_object('status','in_progress',
    'lastVersion',lifecycle->>'lastVersion','active',NULL);
 END IF;
 IF p->'response'->'value'->'lifecycle' IS DISTINCT FROM next_lifecycle THEN
 {_REJECT} END IF;
 expected_restored:=(before_cp->'content'->'restored')||pg_catalog.jsonb_build_object(
 'current',p->'response'->'value'->'current');
 expected_head:=pg_catalog.jsonb_build_object('eventId',own_event.id::text,'gameId',p_game_id::text,
 'generation',stamp.wire_d4,'d1',own_event.d1::text,'d5',own_event.d5::text,
 'fingerprint',stamp.event_fingerprint,'eventKind',own_event.event_kind);
 anchor_id:=before_cp->'content'->'origin'->>'eventId';
 IF pg_catalog.jsonb_array_length(p->'before_source'->'activeStack')>0 THEN
 anchor_id:=p->'before_source'->'activeStack'->0->'play'->'source'->>'eventId'; END IF;
 expected_bridge:=pg_catalog.jsonb_build_object('source',expected_head,'action',action,
 'anchorEventId',anchor_id,'beforeContext',before_cp->'content'->'restored',
 'afterContext',expected_restored,'kernel',pg_catalog.jsonb_build_object(
 'request',p->'request','response',p->'response'),'frameId',p->>'frame_id',
 'checkpointBefore',before_cp->'ref');
 expected_content:=before_cp->'content'||pg_catalog.jsonb_build_object(
 'd3',own_event.d1::text,'d1Head',pg_catalog.jsonb_build_object('kind','accepted-event','source',expected_head),
 'projectionHead',pg_catalog.jsonb_build_object('kind','d1-event','source',expected_head),
 'historyVersion',((before_cp->'content'->>'historyVersion')::bigint+1)::text,
 'restored',expected_restored,'controlBridges',
 COALESCE(before_cp->'content'->'controlBridges','[]'::jsonb)||pg_catalog.jsonb_build_array(expected_bridge));
 IF after_cp->'content' IS DISTINCT FROM expected_content
 OR after_cp->'ref'->>'id' IS DISTINCT FROM cp.id::text
 OR after_cp->'ref'->>'revision' IS DISTINCT FROM (cp.revision+1)::text
 OR after_cp->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 THEN {_REJECT} END IF;
"""


def _bind(sql):
    """唯一生成canonical sectionの固定bindだけを内部変数へ写す。"""
    names = {
        "tenant_id": "p_tenant_id",
        "game_id": "p_game_id",
        "fact_version_id": "prior.id",
    }

    def replace(m):
        if m[0].startswith("'"):
            return m[0]
        if m[1] not in names:
            raise ValueError("終了再開canonical SQLに未知bindがあります")
        return names[m[1]]

    return re.sub(r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)", replace, sql).rstrip(";")


def _clone(model):
    """原credit/sourceの全列を保持し、fact_version_idだけ新idへ写す。"""
    table = model.__table__
    columns = [str(c.name) for c in table.c]
    target = "sync_fence." + table.name
    values = ["new_id" if n == "fact_version_id" else "original." + n for n in columns]
    return (
        f" INSERT INTO {target}({','.join(columns)}) "
        f"SELECT {','.join(values)} FROM {target} original "
        "WHERE original.tenant_id=p_tenant_id "
        "AND original.game_id=p_game_id AND original.fact_version_id=prior.id;\n"
    )


def _display_body():
    """現在head一点を同game lock下で読む。書込nonceを公開しない。"""
    return f"""CREATE FUNCTION sync_right_api.read_lifecycle_display(
 p_tenant_id uuid,p_game_id uuid)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $lifecycle_display$
DECLARE g record; h {_HEAD}%ROWTYPE; lifecycle jsonb;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_game_id IS NULL THEN {_REJECT} END IF;
 SELECT x.id,x.status INTO g FROM public.games x
 WHERE x.tenant_id=p_tenant_id AND x.id=p_game_id AND x.started_at IS NOT NULL
 AND x.trashed_at IS NULL AND x.hidden_at IS NULL AND x.import_batch_id IS NULL
 AND x.status IN ('in_progress','finished');
 IF NOT FOUND THEN RETURN; END IF;
 SELECT x.* INTO h FROM {_HEAD} x WHERE x.tenant_id=p_tenant_id
 AND x.game_id=p_game_id;
 IF NOT FOUND THEN
  IF g.status<>'in_progress' OR EXISTS(SELECT 1 FROM public.operation_events e
  WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
  AND e.event_kind IN ('game_end_declaration','game_reopen')
  AND e.ledger_kind='accepted' AND e.replaced_at IS NULL AND e.retired_at IS NULL)
  THEN {_REJECT} END IF;
  lifecycle:=pg_catalog.jsonb_build_object('formatVersion','native-game-lifecycle-read-v1',
  'status','in_progress','lastVersion','0','active',NULL,'activeStatsVersionId',NULL);
 ELSE
  IF h.is_finished IS DISTINCT FROM (g.status='finished')
  OR NOT EXISTS(SELECT 1 FROM {_TABLE} a
  JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
  AND e.id=a.source_event_id
  JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
  JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
  =(e.tenant_id,e.game_id,e.generation,e.d1)
  WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.state='consumed'
  AND a.consumed_at IS NOT NULL AND e.id=h.last_control_event_id
  AND e.event_kind=(CASE WHEN h.is_finished THEN 'game_end_declaration' ELSE
 'game_reopen' END)
  AND a.action=(CASE WHEN h.is_finished THEN 'end' ELSE 'reopen' END)
  AND e.ledger_kind='accepted' AND NOT e.is_tombstone
  AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
  AND slot.confirmed_version=1 AND l.kind='accepted' AND l.retired_at IS NULL
  AND l.source_fingerprint=a.event_fingerprint)
  THEN {_REJECT} END IF;
  IF h.is_finished AND NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
  JOIN {_TABLE} a ON a.tenant_id=v.tenant_id AND a.game_id=v.game_id
  AND a.source_event_id=h.active_end_event_id AND a.receipt_id=h.active_receipt_id
  WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND
 v.id=h.active_stats_version_id
  AND v.is_current AND v.invalidated_at IS NULL AND v.completion_state='confirmed_ended'
  AND v.completion_receipt_id=h.active_receipt_id
  AND v.public_pointer_receipt_id=h.active_receipt_id AND a.action='end' AND
 a.state='consumed')
  THEN {_REJECT} END IF;
  IF NOT h.is_finished AND EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
  WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND v.is_current
  AND v.completion_state='confirmed_ended') THEN {_REJECT} END IF;
  lifecycle:=pg_catalog.jsonb_build_object('formatVersion','native-game-lifecycle-read-v1',
  'status',g.status,'lastVersion',h.last_version::text,
  'active',CASE WHEN h.is_finished THEN
 pg_catalog.jsonb_build_object('version',h.last_version::text,
  'eventId',h.active_end_event_id::text,'receiptId',h.active_receipt_id::text) ELSE
 NULL END,
  'activeStatsVersionId',h.active_stats_version_id::text);
 END IF;
 RETURN QUERY SELECT lifecycle::text;
END;
$lifecycle_display$;
"""


def candidate_function_bodies():
    """既producer/唯一S/credit guardを使い、全件アプリ集計を作らない。"""
    _raw, sections, model, artifact = _verified_inputs(_ROOT)
    health, members = (
        _bind(sections["canonical_health"]),
        _bind(sections["canonical_source_members"]),
    )
    result = {
        "read_lifecycle_state": _function(
            "read_lifecycle_state",
            _head_state_sql() + " RETURN QUERY SELECT lifecycle::text;",
            extra="lifecycle jsonb;",
        )
    }
    declarations = (
        "before_cp jsonb; after_cp jsonb; expected_content jsonb; exp"
        "ected_head jsonb; expected_restored jsonb; expected_bridge j"
        "sonb; lifecycle jsonb; next_lifecycle jsonb; own_event publi"
        "c.operation_events%ROWTYPE; action text; anchor_id text;"
    )
    identity = ",".join(_IDENTITY)
    preparation_columns = [
        c.name for c in LifecycleWriteAdmission.__table__.c if c.name not in _IDENTITY
    ]
    values = {
        "state": "'evaluated'",
        "frame_id": "(p->>'frame_id')::uuid",
        "frame_digest": "p->>'frame_digest'",
        "artifact_sha256": "p->>'artifact_sha256'",
        "source_event_id": "own_event.id",
        "source_d1": "own_event.d1",
        "source_d2": "own_event.d2",
        "checkpoint_id": "cp.id",
        "checkpoint_revision": "cp.revision",
        "checkpoint_digest": "before_cp->'ref'->>'digest'",
        "receipt_id": "(p->>'receipt_id')::uuid",
        "action": "action",
        "preparation_json": "p_request_json",
        "preparation": "p",
        "consumed_at": "NULL",
    }
    if set(preparation_columns) != set(values):
        raise ValueError("終了再開admissionの全列対応が不一致です")
    insert = (
        f"INSERT INTO {_TABLE}({identity},{','.join(preparation_columns)}) "
        f"VALUES({','.join('stamp.' + n for n in _IDENTITY)},"
        f"{','.join(values[n] for n in preparation_columns)});"
    )
    result["prepare_game_lifecycle"] = _function(
        "prepare_game_lifecycle",
        _head_state_sql()
        + _preparation_guard()
        + insert
        + " RETURN QUERY SELECT true;",
        result="prepared boolean",
        extra=declarations,
    )
    consume = (
        _head_state_sql()
        + _preparation_guard()
        + f"""
 SELECT a.* INTO STRICT lifecycle_stamp FROM {_TABLE} a
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND a.transaction_id=own_xid AND a.state='evaluated'
 AND a.preparation_json=p_request_json AND a.preparation=p
 AND a.frame_id=(p->>'frame_id')::uuid AND a.frame_digest=p->>'frame_digest'
 AND a.source_event_id=own_event.id AND a.d5=own_event.d5 FOR UPDATE;
 UPDATE sync_fence.ordinary_pitch_checkpoints SET content=after_cp,
 content_digest=after_cp->'ref'->>'digest',revision=cp.revision+1,
 confirmed_watermark=own_event.d1,applied_watermark=own_event.d1,
 saved_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id AND id=cp.id
 AND internal_generation=stamp.internal_generation AND revision=cp.revision
 AND content_digest=cp.content_digest AND state='current';
 IF NOT FOUND THEN {_REJECT} END IF;
 UPDATE {_TABLE} SET state='consumed',consumed_at=pg_catalog.clock_timestamp()
 WHERE (tenant_id,attempt_id,phase_id)=(p_tenant_id,p_attempt_id,p_phase_id) AND
 state='evaluated';
 IF NOT FOUND THEN {_REJECT} END IF;
 SELECT v.* INTO STRICT prior FROM sync_fence.stats_fact_versions v
 WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND v.is_current
 AND v.invalidated_at IS NULL AND v.model_sha256='{model}'
 AND v.t5_artifact_set_sha256='{artifact}'
 AND v.completion_state=CASE WHEN action='end' THEN 'current_open' ELSE
 'confirmed_ended' END FOR UPDATE;
 IF action='reopen' AND prior.id IS DISTINCT FROM h.active_stats_version_id THEN
 {_REJECT} END IF;
{_credit_integrity_guard("undo-prior")}
 SELECT * INTO STRICT source_health FROM ({health}) canonical_before;
 IF source_health.game_count<>1 OR source_health.unavailable_count<>0
 OR source_health.canonical_source_count<>prior.source_count
 OR source_health.canonical_source_set_sha256 IS DISTINCT FROM prior.source_set_sha256
 OR (SELECT count(*) FROM ({members}) original_members)<>prior.source_count
 OR (SELECT count(*) FROM sync_fence.stats_primitive_sources s
 WHERE s.tenant_id=p_tenant_id AND s.game_id=p_game_id
 AND s.fact_version_id=prior.id)<>prior.source_count
 THEN {_REJECT} END IF;
 new_id:=pg_catalog.gen_random_uuid();
 UPDATE sync_fence.stats_fact_versions SET
 is_current=false,invalidated_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id AND id=prior.id
 AND is_current AND invalidated_at IS NULL AND revision=prior.revision
 AND source_set_sha256=prior.source_set_sha256;
 IF NOT FOUND THEN {_REJECT} END IF;
 INSERT INTO sync_fence.stats_fact_versions(
 tenant_id,game_id,id,model_sha256,rule_sha256,
 t5_artifact_set_sha256,source_set_sha256,source_count,revision,last_generation,last_d1,last_d2,
 updated_at,computed_metric_keys,is_current,completion_state,completion_receipt_id,
 public_pointer_receipt_id,created_at,invalidated_at)
 VALUES(prior.tenant_id,prior.game_id,new_id,prior.model_sha256,prior.rule_sha256,
 prior.t5_artifact_set_sha256,prior.source_set_sha256,prior.source_count,prior.revision+1,
 prior.last_generation,prior.last_d1,prior.last_d2,pg_catalog.clock_timestamp(),prior.computed_metric_keys,
 true,CASE WHEN action='end' THEN 'confirmed_ended' ELSE 'current_open' END,
 CASE WHEN action='end' THEN lifecycle_stamp.receipt_id ELSE NULL END,
 CASE WHEN action='end' THEN lifecycle_stamp.receipt_id ELSE NULL END,
 pg_catalog.clock_timestamp(),NULL);
{_clone(StatsPrimitiveSource)}{_clone(StatsPrimitiveFact)}
{_credit_integrity_guard("undo-current")}
 INSERT INTO {_HEAD}(tenant_id,game_id,last_version,is_finished,active_end_event_id,
 active_receipt_id,active_stats_version_id,last_control_event_id,updated_at)
 VALUES(p_tenant_id,p_game_id,(next_lifecycle->>'lastVersion')::bigint,action='end',
 CASE WHEN action='end' THEN own_event.id ELSE NULL END,
 CASE WHEN action='end' THEN lifecycle_stamp.receipt_id ELSE NULL END,
 CASE WHEN action='end' THEN new_id ELSE NULL
 END,own_event.id,pg_catalog.clock_timestamp())
 ON CONFLICT(tenant_id,game_id) DO UPDATE SET last_version=EXCLUDED.last_version,
 is_finished=EXCLUDED.is_finished,active_end_event_id=EXCLUDED.active_end_event_id,
 active_receipt_id=EXCLUDED.active_receipt_id,active_stats_version_id=EXCLUDED.active_stats_version_id,
 last_control_event_id=EXCLUDED.last_control_event_id,updated_at=EXCLUDED.updated_at;
 UPDATE public.games SET status=next_lifecycle->>'status'
 WHERE tenant_id=p_tenant_id AND id=p_game_id AND status=game_row.status
 AND trashed_at IS NULL AND import_batch_id IS NULL;
 IF NOT FOUND THEN {_REJECT} END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('eventId',own_event.id::text,
 'receiptId',lifecycle_stamp.receipt_id::text,'frameId',lifecycle_stamp.frame_id::text,
 'factVersionId',new_id::text,'lifecycle',next_lifecycle)::text;
"""
    )
    result["consume_game_lifecycle"] = _function(
        "consume_game_lifecycle",
        consume,
        extra=declarations + f" lifecycle_stamp {_TABLE}%ROWTYPE; "
        "prior sync_fence.stats_fact_versions%ROWTYPE; "
        "new_id uuid; source_health record;",
    )
    result["read_lifecycle_display"] = _display_body()
    return result
