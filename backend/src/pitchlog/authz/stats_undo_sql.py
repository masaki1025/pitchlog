"""消費済み取消と唯一生成Sに閉じ、同TXで残存factの版を作る私有関数。"""

from __future__ import annotations

import json
import re

from pitchlog.authz.nonplay_prefix_sql import _ADMISSION, _REJECT, _head
from pitchlog.authz.stats_primitive_sql import (
    _ROOT,
    _credit_integrity_guard,
    _verified_inputs,
)
from pitchlog.authz.sync_right_sql import _COMMON
from pitchlog.db.game_state.stats import StatsPrimitiveFact, StatsPrimitiveSource
from pitchlog.domaingen.core import _canonical_hash
from pitchlog.stats.generated.receiver import METRIC_IDS


def candidate_function_body() -> str:
    """原保存model/profileを再刻印せず、閉native selectorだけを別hashで束縛する。"""
    _raw, sections, model, artifact = _verified_inputs(_ROOT)
    profile = json.loads(
        (_ROOT / "backend/domain/play-export-undo-selection.model.json").read_text()
    )
    profile_hash = _canonical_hash(profile)

    def bind(sql, *, before=False):
        """有限の生成bindだけを私有変数へ移す。復元は現在の真正取消一件に限る。"""
        names = {
            "tenant_id": "p_tenant_id",
            "game_id": "p_game_id",
            "fact_version_id": "prior.id",
        }

        def replace(match):
            if match[0].startswith("'"):
                return match[0]
            if match[1] not in names:
                raise ValueError("取消S生成SQLに未知bindがあります")
            return names[match[1]]

        value = re.sub(r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)", replace, sql).rstrip(
            ";"
        )
        marker = "NULL::uuid /* restore-undo-event */"
        if marker not in value:
            raise ValueError("取消Sの閉復元点がありません")
        return value.replace(marker, "stamp.source_event_id" if before else marker)

    health = bind(sections["canonical_health"])
    before_health = bind(sections["canonical_health"], before=True)
    members = bind(sections["canonical_source_members"])
    before_members = bind(sections["canonical_source_members"], before=True)
    keys = "ARRAY[" + ",".join("'" + key + "'" for key in METRIC_IDS) + "]::text[]"

    def clone(model_type, *, facts=False):
        """実固定model全列を写し、版id以外の値を変更しない。"""
        table = model_type.__table__
        columns = [str(c.name) for c in table.c]
        target = "sync_fence." + str(table.name)
        values = [
            "new_id" if c == "fact_version_id" else "original." + c for c in columns
        ]
        selection = (
            members
            if not facts
            else (
                "SELECT original.* FROM " + target + " original WHERE "
                "original.tenant_id=p_tenant_id AND original.game_id=p_game_id "
                "AND original.fact_version_id=prior.id AND EXISTS(SELECT 1 FROM ("
                + members
                + ") kept WHERE kept.source_event_id=original.source_event_id)"
            )
        )
        return (
            " INSERT INTO "
            + target
            + "("
            + ",".join(columns)
            + ") SELECT "
            + ",".join(values)
            + " FROM ("
            + selection
            + ") original;\n"
        )

    return f"""CREATE FUNCTION stats_api.rebuild_after_nonplay_undo({_COMMON},p_request_json text)
RETURNS TABLE(receipt_json text) LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $undo_stats$
DECLARE stamp {_ADMISSION}%ROWTYPE; own_xid text; p jsonb;
 prior sync_fence.stats_fact_versions%ROWTYPE; before_s record; after_s record;
 new_id uuid; kept_count bigint; position record; computed_keys text[];
BEGIN
 IF current_user<>'pitchlog_sync_right_fn_owner' OR session_user<>'pitchlog_app'
 THEN {_REJECT} END IF;
{_head()}
 p:=p_request_json::jsonb;
 IF stamp.state<>'consumed' OR stamp.consumed_at IS NULL
 OR stamp.preparation_json IS DISTINCT FROM p_request_json OR stamp.preparation IS DISTINCT FROM p
 OR stamp.frame_id IS DISTINCT FROM (p->>'frame_id')::uuid
 OR stamp.frame_digest IS DISTINCT FROM p->>'frame_digest'
 OR NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_checkpoints cp
 WHERE cp.tenant_id=p_tenant_id AND cp.game_id=p_game_id AND cp.id=stamp.checkpoint_id
 AND cp.internal_generation=stamp.internal_generation AND cp.state='current'
 AND cp.revision=stamp.checkpoint_revision+1
 AND cp.content=p->'after_source'->'checkpoint'
 AND cp.content_digest=p->'after_source'->'checkpoint'->'ref'->>'digest')
 THEN {_REJECT} END IF;
 SELECT v.* INTO STRICT prior FROM sync_fence.stats_fact_versions v
 WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND v.model_sha256='{model}'
 AND v.is_current AND v.invalidated_at IS NULL AND v.completion_state='current_open'
 AND v.t5_artifact_set_sha256='{artifact}' FOR UPDATE;
{_credit_integrity_guard("undo-prior")}
 SELECT * INTO STRICT before_s FROM ({before_health}) qualified_before;
 SELECT * INTO STRICT after_s FROM ({health}) qualified_after;
 SELECT count(*) INTO kept_count FROM ({before_members}) qualified_prior;
 IF before_s.game_count<>1 OR after_s.game_count<>1
 OR before_s.unavailable_count<>0 OR after_s.unavailable_count<>0
 OR before_s.canonical_source_count<>prior.source_count OR kept_count<>prior.source_count
 OR before_s.canonical_source_set_sha256 IS DISTINCT FROM prior.source_set_sha256
 OR after_s.canonical_source_count<>prior.source_count-1
 OR NOT EXISTS(SELECT 1 FROM ({before_members}) target
 WHERE target.source_event_id=stamp.target_event_id AND target.play_row_id=stamp.target_play_id)
 OR EXISTS(SELECT 1 FROM ({before_members}) retained WHERE retained.rule_sha256<>prior.rule_sha256)
 THEN {_REJECT} END IF;
 SELECT count(*) INTO kept_count FROM ({members}) qualified_remaining;
 IF kept_count<>after_s.canonical_source_count THEN {_REJECT} END IF;
 SELECT recording_generation,d1,d2 INTO position FROM ({members}) last_member
 ORDER BY d2 DESC,source_event_id DESC LIMIT 1;
 SELECT ARRAY(SELECT key FROM unnest({keys}) key WHERE NOT EXISTS(
 SELECT 1 FROM ({members}) remaining WHERE NOT(key=ANY(remaining.computed_metric_keys)))
 ORDER BY key) INTO computed_keys;
 new_id:=pg_catalog.gen_random_uuid();
 UPDATE sync_fence.stats_fact_versions SET is_current=false,
 invalidated_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id AND id=prior.id
 AND is_current AND invalidated_at IS NULL AND completion_state='current_open'
 AND revision=prior.revision AND source_set_sha256=prior.source_set_sha256;
 IF NOT FOUND THEN {_REJECT} END IF;
 INSERT INTO sync_fence.stats_fact_versions(tenant_id,game_id,id,model_sha256,rule_sha256,
 t5_artifact_set_sha256,source_set_sha256,source_count,revision,last_generation,last_d1,last_d2,
 updated_at,computed_metric_keys,is_current,completion_state,completion_receipt_id,
 public_pointer_receipt_id,created_at,invalidated_at)
 VALUES(p_tenant_id,p_game_id,new_id,prior.model_sha256,prior.rule_sha256,
 prior.t5_artifact_set_sha256,after_s.canonical_source_set_sha256,kept_count,prior.revision+1,
 position.recording_generation,position.d1,position.d2,pg_catalog.clock_timestamp(),
 computed_keys,true,'current_open',NULL,NULL,pg_catalog.clock_timestamp(),NULL);
{clone(StatsPrimitiveSource)}{clone(StatsPrimitiveFact, facts=True)}
{_credit_integrity_guard("undo-current")}
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'formatVersion','undo-native-stats-receipt-v1','profileSha256','{profile_hash}',
 'modelSha256',prior.model_sha256,'tenantId',p_tenant_id::text,'gameId',p_game_id::text,
 'attemptId',p_attempt_id::text,'phaseId',p_phase_id::text,'undoEventId',stamp.source_event_id::text,
 'targetEventId',stamp.target_event_id::text,'frameId',stamp.frame_id::text,
 'frameDigest',stamp.frame_digest,'artifactSha256',stamp.artifact_sha256,
 'sourceFingerprint',stamp.event_fingerprint,'transactionId',own_xid,'internalGeneration',stamp.internal_generation::text,
 'checkpointDigest',p->'after_source'->'checkpoint'->'ref'->>'digest',
 'oldFactVersionId',prior.id::text,'factVersionId',new_id::text,
 'oldRevision',prior.revision::text,'revision',(prior.revision+1)::text,
 'beforeSourceSetSha256',prior.source_set_sha256,
 'sourceSetSha256',after_s.canonical_source_set_sha256,'sourceCount',kept_count::text)::text;
END;
$undo_stats$;
"""  # noqa: E501 — 固定された生成SQL本文
