"""唯一の共通生成SQLを使い、成績native関数4本だけを描画する。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pitchlog.authz.sync_right_sql import _STAMP_COLS
from pitchlog.domaingen.core import _canonical_hash, generate_primitive_sql_bundle
from pitchlog.repositories.stats_function_codec import (
    _current_decisions,
    _native_profiles,
)
from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH

_ROOT = Path(__file__).parents[4]
_SQL_PATH = "backend/src/pitchlog/exports/generated/play_primitives.sql"
_MODEL_PATH = "backend/domain/play-export.model.json"
_CONSUMER_PATH = "backend/domain/stats.model.json"
_SQL_PATHS = frozenset(
    {
        _SQL_PATH,
        "backend/src/pitchlog/stats/generated/stats.sql",
        "backend/src/pitchlog/stats/generated/stats_rates.sql",
    }
)
_MANIFEST_PATH = "backend/domain/stats-manifest.json"
_ARTIFACT_PATHS = frozenset(
    {
        "backend/src/pitchlog/stats/generated/facts.py",
        "frontend/src/lib/generated/statsPrimitives.ts",
    }
)


def _verified_inputs(root: Path) -> tuple[str, dict[str, str], str, str]:
    """共通model/生成selector/artifact宣言の全値一致だけを受ける。"""
    common_model = json.loads((root / _MODEL_PATH).read_text())
    consumer_model = json.loads((root / _CONSUMER_PATH).read_text())
    manifest = json.loads((root / _MANIFEST_PATH).read_text())
    bundle = generate_primitive_sql_bundle(common_model, consumer_model)
    model_hash = _canonical_hash(common_model)
    profiles = _native_profiles(root)
    if profiles["v2"]["model_sha256"] != model_hash or set(bundle) != _SQL_PATHS:
        raise ValueError("成績nativeの現在版/生成SQL集合が一致しません")
    if common_model["calculations"][0]["typedProgram"].get("version") != 2:
        raise ValueError("成績native SQL sinkは現在v2専用です")
    if (
        common_model["calculations"][0]["typedProgram"].get("decisions")
        != _current_decisions()
    ):
        raise ValueError("成績nativeの採用metadataが一致しません")
    for path in _SQL_PATHS:
        raw_sql = (root / path).read_text()
        if (
            raw_sql != bundle[path]
            or manifest["generatedFiles"][path]
            != hashlib.sha256(raw_sql.encode()).hexdigest()
        ):
            raise ValueError("成績nativeの生成SQL本文が一致しません")
    if profiles["v2"]["artifact_binding"] != manifest["t5ArtifactSetBinding"]:
        raise ValueError("成績native現在profileとartifact宣言が一致しません")
    raw = (root / _SQL_PATH).read_text()
    binding = manifest["t5ArtifactSetBinding"]
    if (
        model_hash != SOURCE_MODEL_HASH
        or manifest["commonModelHash"] != model_hash
        or manifest["generationInputFiles"][_MODEL_PATH]
        != hashlib.sha256((root / _MODEL_PATH).read_bytes()).hexdigest()
        or raw != bundle[_SQL_PATH]
        or manifest["generatedFiles"][_SQL_PATH]
        != hashlib.sha256(raw.encode()).hexdigest()
        or set(binding) != {"version", "model_sha256", "artifacts"}
        or type(binding["version"]) is not int
        or binding["version"] != 1
        or binding["model_sha256"] != model_hash
        or set(binding["artifacts"]) != _ARTIFACT_PATHS
        or any(
            hashlib.sha256((root / path).read_bytes()).hexdigest() != value
            for path, value in binding["artifacts"].items()
        )
        or _canonical_hash(binding) != "sha256:" + manifest["t5ArtifactSetSha256"]
        or tuple(
            item["id"]
            for item in common_model["calculations"][0]["typedProgram"]["metrics"]
        )
        != METRIC_IDS
    ):
        raise ValueError("成績共通model/生成SQL/artifactの対応が不一致")
    parts = raw.split("-- pitchlog-query: ")[1:]
    sections = {
        part.split("\n", 1)[0]: part.split("\n", 1)[1].strip() for part in parts
    }
    if len(parts) != 5 or set(sections) != {
        "window",
        "count",
        "current_totals",
        "canonical_members",
        "canonical_health",
    }:
        raise ValueError("成績の生成query集合が閉じていません")
    return raw, sections, model_hash, manifest["t5ArtifactSetSha256"]


def candidate_function_bodies() -> dict[str, str]:
    """採用済みS/COUNT/window/totalsと同TX条件をSQL本文へ束縛する。"""
    raw, sections, MODEL, ART = _verified_inputs(_ROOT)
    common, tail = sections["canonical_health"].rsplit("\nSELECT ", 1)
    anchor = "FROM canonical_scope g LEFT JOIN canonical_s c"
    if not common.startswith("WITH canonical_scope") or common.count(anchor) != 1:
        raise ValueError("成績の唯一canonical集合を特定できません")
    previous = common.replace(
        anchor,
        (
            "FROM canonical_scope g LEFT JOIN "
            "(SELECT * FROM canonical_s WHERE "
            "source_event_id IS DISTINCT FROM "
            "p_source_event_id) "
            "c"
        ),
    )
    IDS = METRIC_IDS
    sqlarray = "ARRAY[" + ",".join("'" + x + "'" for x in sorted(IDS)) + "]::text[]"

    def bind(s: str, substitutions: dict[str, str] | None = None) -> str:
        """生成queryの既bind名だけを固定PL変数へ写す。"""
        names = {
            "tenant_id": "tenant",
            "game_id": "p_game_id",
            "player_id": "p_player_id",
            "model_sha256": "p_model_sha256",
            "fact_version_id": "p_fact_version_id",
            "source_set_sha256": "p_source_set_sha256",
            "revision": "p_revision",
            "after_d2": "p_after_d2",
            "after_source_event_id": "p_after_source_event_id",
            "after_metric_id": "p_after_metric_id",
            "page_size": "p_page_size",
            # nativeの単一game読取は合算固定。任意の集合/選択は呼出者に開かない。
            "named_category": "'all'",
            "raw_game_type_keys": "ARRAY["
            + ",".join(
                "'" + key + "'"
                for key in json.loads((_ROOT / _MODEL_PATH).read_text())[
                    "calculations"
                ][0]["typedProgram"]["namedScopes"]["groups"]["all"]
            )
            + "]::text[]",
        }
        if substitutions:
            names.update(substitutions)

        def repl(m: re.Match[str]) -> str:
            """未登録bindは補完せず拒否する。"""
            if m[1] not in names:
                raise ValueError("未知の成績SQL bindです")
            return names[m[1]]

        return re.sub(
            r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)",
            lambda m: m[0] if m[0].startswith("'") else repl(m),
            s,
        ).rstrip(";")

    HEALTH = bind(common + "\nSELECT " + tail)
    PREVIOUS = bind(previous + "\nSELECT " + tail)
    CURRENT = bind(
        common
        + (
            "\nSELECT c.* FROM canonical_s c WHERE "
            "c.source_event_id=p_source_event_id AND "
            "c.source_state='included'"
        )
    )
    COUNT = bind(sections["count"])
    same = " AND ".join(
        "s." + x + " IS NOT DISTINCT FROM b." + x for x in _STAMP_COLS.split(",")
    )
    OWNER = "pitchlog_sync_right_fn_owner"
    REJECT = (
        "RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501';"
    )

    def function(name: str, args: str, returns: str, decl: str, body: str) -> str:
        """固定属性のSECURITY DEFINER本文を描画する。"""
        return (
            "CREATE FUNCTION "
            "stats_api."
            f"{name}"
            "("
            f"{args}"
            ")\nRETURNS TABLE("
            f"{returns}"
            ") LANGUAGE plpgsql VOLATILE SECURITY "
            "DEFINER\nSET search_path=pg_catalog,"
            "pg_temp AS $stats$\n#variable_conflict "
            "use_column\nDECLARE "
            f"{decl}"
            "\nBEGIN\n"
            f"{body}"
            "\nEND;\n$stats$;\n"
        )

    read_guard = (
        " tenant:=NULLIF(pg_catalog.current_setti"
        "ng('app.tenant_id',true),'')::uuid;\n IF "
        "session_user IS DISTINCT FROM "
        "'pitchlog_app' OR current_user IS "
        "DISTINCT FROM "
        "'"
        f"{OWNER}"
        "'\n OR tenant IS NULL OR p_game_id IS "
        "NULL OR p_player_id IS NULL\n OR "
        "p_model_sha256 IS DISTINCT FROM "
        "'"
        f"{MODEL}"
        "'\n OR pg_catalog.current_setting('transa"
        "ction_isolation') IS DISTINCT FROM "
        "'repeatable read'\n OR "
        "pg_catalog.current_setting('transaction_"
        "read_only') IS DISTINCT FROM 'on'\n THEN "
        f"{REJECT}"
        " END IF;\n IF NOT EXISTS(SELECT 1 FROM "
        "public.players p WHERE "
        "p.tenant_id=tenant AND "
        "p.id=p_player_id)\n THEN "
        f"{REJECT}"
        " END IF;\n"
    )
    count_check = (
        " IF audit.fact_version_id IS NULL OR "
        "audit.model_sha256 IS DISTINCT FROM "
        "p_model_sha256\n OR "
        "audit.completion_state IS DISTINCT FROM "
        "'current_open'\n OR audit.source_count "
        "IS DISTINCT FROM "
        "audit.actual_source_count\n OR "
        "audit.source_count IS DISTINCT FROM "
        "audit.canonical_source_count\n OR "
        "audit.unavailable_count IS DISTINCT "
        "FROM 0::bigint\n OR "
        "audit.source_set_sha256 IS DISTINCT "
        "FROM audit.canonical_source_set_sha256\n "
        "OR audit.row_count IS DISTINCT FROM "
        "audit.source_count*26\n OR (SELECT "
        "COUNT(*) FROM "
        "sync_fence.stats_primitive_sources s "
        "WHERE s.tenant_id=tenant\n AND "
        "s.game_id=p_game_id AND "
        "s.fact_version_id=p_fact_version_id) IS "
        "DISTINCT FROM audit.source_count\n OR "
        "audit.transaction_id IS DISTINCT FROM "
        "pg_catalog.pg_current_snapshot()::text\n "
        "THEN "
        f"{REJECT}"
        " END IF;"
    )
    credit_integrity = (
        "\n -- 内容を再計算せず、保存済み唯一T5応答の全creditと実fact集合"
        "を双方向比較する。\n IF EXISTS(SELECT 1 FROM "
        "sync_fence.stats_primitive_sources s\n "
        "WHERE s.tenant_id=tenant AND "
        "s.game_id=p_game_id AND "
        "s.fact_version_id=p_fact_version_id\n "
        "AND s.evaluation_sha256 IS DISTINCT "
        "FROM pg_catalog.encode(pg_catalog.sha256"
        "(pg_catalog.convert_to(\n "
        "s.metric_states::text,'UTF8')),'hex')) "
        "OR EXISTS(\n WITH expected_credits AS (\n "
        " SELECT s.source_event_id,m.key AS "
        "metric_id,(c.value->>'player_id')::uuid "
        "AS player_id,\n  c.ordinality-1 AS "
        "credit_ordinal,'available'::text AS "
        "state,(c.value->>'quantity')::numeric "
        "AS amount\n  FROM "
        "sync_fence.stats_primitive_sources s\n  "
        "CROSS JOIN LATERAL "
        "pg_catalog.jsonb_each(s.metric_states->'"
        "metrics') m\n  CROSS JOIN LATERAL "
        "pg_catalog.jsonb_array_elements(m.value-"
        ">'credits') WITH ORDINALITY c\n  WHERE "
        "s.tenant_id=tenant AND "
        "s.game_id=p_game_id AND "
        "s.fact_version_id=p_fact_version_id\n ), "
        "actual_credits AS (\n  SELECT "
        "f.source_event_id,f.metric_id,"
        "f.player_id,f.credit_ordinal,f.state,"
        "f.amount\n  FROM "
        "sync_fence.stats_primitive_facts f "
        "WHERE f.tenant_id=tenant AND "
        "f.game_id=p_game_id\n  AND "
        "f.fact_version_id=p_fact_version_id\n )\n "
        "(SELECT * FROM expected_credits EXCEPT "
        "SELECT * FROM actual_credits)\n UNION "
        "ALL (SELECT * FROM actual_credits "
        "EXCEPT SELECT * FROM expected_credits)\n "
        ") THEN "
        f"{REJECT}"
        " END IF;\n"
    )
    count_check += credit_integrity
    open_body = read_guard + (
        "\n SELECT v.id,v.revision,"
        "v.source_set_sha256 INTO STRICT "
        "p_fact_version_id,p_revision,"
        "p_source_set_sha256\n FROM "
        "sync_fence.stats_fact_versions v WHERE "
        "v.tenant_id=tenant AND "
        "v.game_id=p_game_id\n AND "
        "v.model_sha256=p_model_sha256 AND "
        "v.is_current AND v.invalidated_at IS "
        "NULL\n AND v.rule_sha256 ~ "
        "'^[a-f0-9]{64}$'\n AND "
        "v.t5_artifact_set_sha256='"
        f"{ART}"
        "' AND v.completion_state='current_open';"
        "\n SELECT * INTO STRICT health FROM "
        "("
        f"{HEALTH}"
        ") canonical_result;\n IF "
        "health.game_count IS DISTINCT FROM "
        "1::bigint THEN "
        f"{REJECT}"
        " END IF;\n SELECT * INTO STRICT audit "
        "FROM ("
        f"{COUNT}"
        ") snapshot_result;\n "
        f"{count_check}"
        "\n RETURN QUERY SELECT "
        "audit.fact_version_id,audit.revision,"
        "audit.source_set_sha256,\n "
        "audit.model_sha256,audit.source_count,"
        "audit.row_count,audit.transaction_id,"
        "audit.completion_state;\n"
    )
    functions: dict[str, str] = {}
    functions["open_primitive_snapshot"] = function(
        "open_primitive_snapshot",
        "p_game_id uuid,p_player_id uuid,p_model_sha256 text",
        (
            "fact_version_id uuid,revision bigint,"
            "source_set_sha256 text,model_sha256 "
            "text,source_count bigint,row_count "
            "bigint,transaction_id text,"
            "completion_state "
            "text"
        ),
        (
            "tenant uuid; p_fact_version_id uuid; "
            "p_revision bigint; p_source_set_sha256 "
            "text; audit record; health "
            "record;"
        ),
        open_body,
    )
    receipt_guard = (
        " IF p_fact_version_id IS NULL OR "
        "p_revision IS NULL OR p_revision<1\n OR "
        "p_source_set_sha256 IS NULL OR "
        "p_source_set_sha256 !~ '^[a-f0-9]{64}$'\n"
        " OR p_transaction_id IS NULL OR "
        "p_transaction_id IS DISTINCT FROM "
        "pg_catalog.pg_current_snapshot()::text\n "
        "THEN "
        f"{REJECT}"
        " END IF;\n SELECT * INTO STRICT receipt "
        "FROM stats_api.open_primitive_snapshot(p"
        "_game_id,p_player_id,p_model_sha256);\n "
        "IF receipt.fact_version_id IS DISTINCT "
        "FROM p_fact_version_id OR "
        "receipt.revision IS DISTINCT FROM "
        "p_revision\n OR "
        "receipt.source_set_sha256 IS DISTINCT "
        "FROM p_source_set_sha256\n OR "
        "receipt.model_sha256 IS DISTINCT FROM "
        "p_model_sha256\n OR "
        "receipt.transaction_id IS DISTINCT FROM "
        "p_transaction_id\n THEN "
        f"{REJECT}"
        " END IF;\n"
    )
    base_read_args = (
        "p_game_id uuid,p_player_id uuid,"
        "p_fact_version_id uuid,p_revision "
        "bigint,p_source_set_sha256 text,"
        "p_model_sha256 text,p_transaction_id "
        "text"
    )
    page_body = (
        read_guard
        + receipt_guard
        + (
            "\n IF p_page_size IS NULL OR "
            "p_page_size<1 OR p_page_size>500\n OR "
            "NOT ((p_after_d2 IS NULL AND "
            "p_after_source_event_id IS NULL AND "
            "p_after_metric_id IS NULL)\n OR "
            "(p_after_d2 IS NOT NULL AND "
            "p_after_source_event_id IS NOT NULL AND "
            "p_after_metric_id IS NOT NULL AND "
            "p_after_metric_id=ANY("
            f"{sqlarray}"
            ")))\n THEN "
            f"{REJECT}"
            " END IF;\n RETURN QUERY "
            f"{bind(sections['window'])}"
            ";\n"
        )
    )
    functions["read_play_export_primitives"] = function(
        "read_play_export_primitives",
        base_read_args
        + (
            ",p_after_d2 bigint,"
            "p_after_source_event_id uuid,"
            "p_after_metric_id text,p_page_size "
            "integer"
        ),
        "metric_id text,state text,value numeric,d2 bigint,source_event_id uuid",
        "tenant uuid; receipt record;",
        page_body,
    )
    functions["read_primitive_totals"] = function(
        "read_primitive_totals",
        base_read_args,
        "metric_id text,state text,value numeric",
        "tenant uuid; receipt record;",
        read_guard
        + receipt_guard
        + "\n RETURN QUERY "
        + bind(sections["current_totals"])
        + ";\n",
    )
    # saveは同scopeの実frame/evaluation identity gateを必須とする。
    # SQLはT5を再計算しない。
    save_guard = (
        " tenant:=NULLIF(pg_catalog.current_setti"
        "ng('app.tenant_id',true),'')::uuid;\n "
        "own_xid:=pg_catalog.pg_current_xact_id()"
        "::text;\n IF session_user IS DISTINCT "
        "FROM 'pitchlog_app' OR current_user IS "
        "DISTINCT FROM "
        "'"
        f"{OWNER}"
        "'\n OR tenant IS NULL OR p_attempt_id IS "
        "NULL OR p_phase_id IS NULL OR "
        "p_source_event_id IS NULL\n OR "
        "p_binding_nonce IS NULL OR "
        "pg_catalog.octet_length(p_binding_nonce)"
        "<>32\n OR pg_catalog.current_setting('tra"
        "nsaction_read_only') IS DISTINCT FROM "
        "'off'\n OR p_model_sha256 IS DISTINCT "
        "FROM '"
        f"{MODEL}"
        "'\n OR p_expected_revision IS NULL OR "
        "p_expected_revision<0\n OR "
        "((p_expected_revision=0) IS DISTINCT "
        "FROM (p_expected_source_set_sha256 IS "
        "NULL))\n OR (p_expected_source_set_sha256"
        " IS NOT NULL AND "
        "p_expected_source_set_sha256 !~ "
        "'^[a-f0-9]{64}$')\n THEN "
        f"{REJECT}"
        " END IF;\n SELECT b.* INTO STRICT "
        "binding FROM sync_fence.writer_bindings "
        "b\n WHERE b.tenant_id=tenant AND "
        "b.attempt_id=p_attempt_id AND "
        "b.phase_id=p_phase_id\n AND "
        "b.state='open' AND "
        "b.transaction_id=own_xid AND "
        "b.expires_at>pg_catalog.clock_timestamp("
        ");\n PERFORM "
        "sync_fence_api.assert_writer_binding(ten"
        "ant,p_attempt_id,p_phase_id,"
        "p_binding_nonce,binding.device_id,"
        "binding.game_id);\n "
        "p_game_id:=binding.game_id;\n IF NOT "
        "EXISTS(SELECT 1 FROM public.games g "
        "WHERE g.tenant_id=tenant AND "
        "g.id=p_game_id\n AND "
        "g.status='in_progress' AND g.hidden_at "
        "IS NULL AND g.trashed_at IS NULL) THEN "
        f"{REJECT}"
        " END IF;\n SELECT e.* INTO STRICT "
        "event_row FROM public.operation_events "
        "e\n WHERE e.tenant_id=tenant AND "
        "e.game_id=p_game_id AND "
        "e.id=p_source_event_id\n AND "
        "e.generation=binding.internal_generation"
        " AND e.d5=binding.d5\n AND "
        "e.ledger_kind='accepted' AND "
        "e.event_kind='play_input' AND NOT "
        "e.is_tombstone\n AND e.replaced_at IS "
        "NULL AND e.retired_at IS NULL AND "
        "e.import_batch_id IS NULL\n AND "
        "e.legacy_row_identifier IS NULL AND NOT "
        "e.migration_unverified\n AND "
        "e.xmin::text::numeric=pg_catalog.mod(own"
        "_xid::numeric,4294967296::numeric);\n "
        "variant:=event_row.payload->>'formatVers"
        "ion';\n IF event_row.payload#>'{calculati"
        "on,response,ok}' IS DISTINCT FROM "
        "'true'::jsonb\n OR "
        "event_row.payload#>>'{calculation,"
        "formatVersion}' IS DISTINCT FROM (CASE "
        "variant\n WHEN 'first-ball-play-v1' THEN "
        "'first-ball-calculation-v1'\n WHEN "
        "'ordinary-pitch-play-v1' THEN "
        "'ordinary-pitch-calculation-v1'\n WHEN "
        "'play-prefix-play-v2' THEN "
        "'play-prefix-calculation-v2'\n WHEN "
        "'play-prefix-play-v3' THEN "
        "'play-prefix-calculation-v3' END)\n OR "
        "variant NOT IN ('first-ball-play-v1',"
        "'ordinary-pitch-play-v1',"
        "'play-prefix-play-v2',"
        "'play-prefix-play-v3')\n OR variant IS "
        "NULL THEN "
        f"{REJECT}"
        " END IF;\n IF "
        "variant='first-ball-play-v1' THEN\n  "
        "SELECT pg_catalog.to_jsonb(s) INTO "
        "STRICT stamp FROM "
        "sync_fence.first_ball_write_admissions "
        "s\n  JOIN sync_fence.writer_bindings b "
        "USING(tenant_id,attempt_id,phase_id)\n  "
        "JOIN sync_fence.writer_admissions wa "
        "USING(tenant_id,attempt_id,phase_id)\n  "
        "WHERE s.tenant_id=tenant AND "
        "s.attempt_id=p_attempt_id AND "
        "s.phase_id=p_phase_id\n  AND "
        "s.state='consumed' AND s.consumed_at IS "
        "NOT NULL AND "
        "s.source_event_id=p_source_event_id\n  "
        "AND s.transaction_id=own_xid AND "
        "s.xmin::text::numeric=pg_catalog.mod(own"
        "_xid::numeric,4294967296::numeric)\n  "
        "AND wa.transaction_id=own_xid AND "
        "wa.lease_id=b.lease_id\n  AND "
        "wa.xmin::text::numeric=pg_catalog.mod(ow"
        "n_xid::numeric,4294967296::numeric)\n  "
        "AND "
        f"{same}"
        ";\n  IF EXISTS(SELECT 1 FROM "
        "sync_fence.ordinary_pitch_write_admissio"
        "ns o\n   WHERE o.tenant_id=tenant AND "
        "o.attempt_id=p_attempt_id AND "
        "o.phase_id=p_phase_id\n   AND o.state IN "
        "('device_verified','right_verified',"
        "'evaluated','consumed')) THEN "
        f"{REJECT}"
        " END IF;\n  checkpoint_id:=NULL; "
        "checkpoint_revision:=NULL; "
        "checkpoint_digest:=NULL; "
        "frame_digest:=NULL;\n  "
        "provider:='first_ball';\n ELSE\n  SELECT "
        "pg_catalog.to_jsonb(s) INTO STRICT "
        "stamp FROM sync_fence.ordinary_pitch_wri"
        "te_admissions s\n  JOIN "
        "sync_fence.writer_bindings b "
        "USING(tenant_id,attempt_id,phase_id)\n  "
        "JOIN sync_fence.writer_admissions wa "
        "USING(tenant_id,attempt_id,phase_id)\n  "
        "WHERE s.tenant_id=tenant AND "
        "s.attempt_id=p_attempt_id AND "
        "s.phase_id=p_phase_id\n  AND "
        "s.state='consumed' AND s.consumed_at IS "
        "NOT NULL AND "
        "s.source_event_id=p_source_event_id\n  "
        "AND s.transaction_id=own_xid AND "
        "s.xmin::text::numeric=pg_catalog.mod(own"
        "_xid::numeric,4294967296::numeric)\n  "
        "AND wa.transaction_id=own_xid AND "
        "wa.lease_id=b.lease_id\n  AND "
        "wa.xmin::text::numeric=pg_catalog.mod(ow"
        "n_xid::numeric,4294967296::numeric)\n  "
        "AND "
        f"{same}"
        ";\n  IF EXISTS(SELECT 1 FROM "
        "sync_fence.first_ball_write_admissions "
        "f\n   WHERE f.tenant_id=tenant AND "
        "f.attempt_id=p_attempt_id AND "
        "f.phase_id=p_phase_id\n   AND f.state IN "
        "('device_verified','right_verified',"
        "'consumed')) THEN "
        f"{REJECT}"
        " END IF;\n  SELECT c.* INTO STRICT "
        "checkpoint FROM "
        "sync_fence.ordinary_pitch_checkpoints c\n"
        "  WHERE c.tenant_id=tenant AND "
        "c.game_id=p_game_id AND "
        "c.internal_generation=binding.internal_g"
        "eneration\n  AND "
        "c.id=(stamp->>'checkpoint_id')::uuid "
        "AND c.state='current'\n  AND "
        "c.content=stamp->'next_checkpoint_conten"
        "t' AND c.content_digest=stamp->'next_che"
        "ckpoint_content'->>'content_digest'\n  "
        "AND c.revision=(stamp->'next_checkpoint_"
        "content'->>'revision')::bigint\n  AND "
        "c.history_version=(stamp->'next_checkpoi"
        "nt_content'->>'history_version')::bigint"
        "\n  AND c.confirmed_watermark=event_row.d"
        "1 AND c.applied_watermark=event_row.d1\n "
        " AND c.saved_at=(stamp->>'consumed_at'):"
        ":timestamptz\n  AND "
        "c.xmin::text::numeric=pg_catalog.mod(own"
        "_xid::numeric,4294967296::numeric);\n  "
        "IF stamp->>'artifact_sha256' IS "
        "DISTINCT FROM "
        "event_row.payload#>>'{calculation,"
        "artifactSha256}'\n  OR "
        "stamp->>'frame_digest' IS NULL OR "
        "stamp->>'frame_digest' !~ "
        "'^[a-f0-9]{64}$'\n  OR "
        "stamp->>'source_d1' IS DISTINCT FROM "
        "event_row.d1::text\n  OR "
        "stamp->>'source_d2' IS DISTINCT FROM "
        "event_row.d2::text\n  THEN "
        f"{REJECT}"
        " END IF;\n  checkpoint_id:=checkpoint.id;"
        " checkpoint_revision:=checkpoint.revisio"
        "n;\n  checkpoint_digest:=checkpoint.conte"
        "nt_digest; frame_digest:=stamp->>'frame_"
        "digest'; provider:='ordinary';\n END IF;\n"
        " SELECT p.* INTO STRICT saved_play FROM "
        "public.play_rows p\n WHERE "
        "p.tenant_id=tenant AND "
        "p.game_id=p_game_id AND "
        "p.source_event_id=p_source_event_id\n "
        "AND p.id=(stamp->>'play_row_id')::uuid "
        "AND p.hidden_at IS NULL\n AND "
        "p.import_batch_id IS NULL AND "
        "p.legacy_row_identifier IS NULL AND NOT "
        "p.migration_unverified\n AND "
        "p.xmin::text::numeric=pg_catalog.mod(own"
        "_xid::numeric,4294967296::numeric);\n IF "
        "provider='ordinary' AND "
        "pg_catalog.to_jsonb(saved_play) IS "
        "DISTINCT FROM "
        "stamp->'expected_play_row'\n THEN "
        f"{REJECT}"
        " END IF;\n IF NOT EXISTS(SELECT 1 FROM "
        "public.idempotency_ledger l WHERE "
        "l.tenant_id=tenant\n AND l.d5=binding.d5 "
        "AND l.kind='accepted' AND "
        "l.source_fingerprint=binding.event_finge"
        "rprint\n AND l.retired_at IS NULL AND "
        "l.import_batch_id IS NULL\n AND "
        "l.xmin::text::numeric=pg_catalog.mod(own"
        "_xid::numeric,4294967296::numeric))\n OR "
        "NOT EXISTS(SELECT 1 FROM "
        "public.recording_generations r WHERE "
        "r.tenant_id=tenant AND "
        "r.game_id=p_game_id\n AND "
        "r.generation=binding.internal_generation"
        " AND r.kind='normal' AND "
        "r.holder_device=binding.device_id::text\n"
        " AND r.revoked_at IS NULL AND "
        "r.retired_at IS NULL AND "
        "r.recovery_generation=binding.recovery_g"
        "eneration\n AND "
        "r.confirmed_watermark=event_row.d1 AND "
        "r.applied_prefix=event_row.d1)\n OR NOT "
        "EXISTS(SELECT 1 FROM "
        "public.rg1_restore_gate g WHERE "
        "g.singleton_id=1 AND g.state='open'\n "
        "AND g.recovery_generation=binding.recove"
        "ry_generation)\n OR NOT EXISTS(SELECT 1 "
        "FROM public.trusted_devices d WHERE "
        "d.tenant_id=tenant AND "
        "d.device_id=binding.device_id AND "
        "d.revoked_at IS NULL)\n THEN "
        f"{REJECT}"
        " END IF;\n SELECT * INTO STRICT "
        "current_source FROM "
        "("
        f"{CURRENT}"
        ") canonical_current;\n IF "
        "current_source.recording_generation IS "
        "DISTINCT FROM event_row.generation\n OR "
        "current_source.d1 IS DISTINCT FROM "
        "event_row.d1 OR current_source.d2 IS "
        "DISTINCT FROM event_row.d2\n OR "
        "current_source.slot_version IS DISTINCT "
        "FROM 1::bigint\n OR "
        "current_source.play_row_id IS DISTINCT "
        "FROM saved_play.id OR "
        "current_source.play_row_version IS "
        "DISTINCT FROM saved_play.version\n OR "
        "current_source.source_fingerprint IS "
        "DISTINCT FROM binding.event_fingerprint\n"
        " OR current_source.artifact_sha256 IS "
        "DISTINCT FROM "
        "event_row.payload#>>'{calculation,"
        "artifactSha256}'\n THEN "
        f"{REJECT}"
        " END IF;\n SELECT * INTO STRICT health "
        "FROM ("
        f"{HEALTH}"
        ") canonical_current_health;\n IF "
        "health.game_count IS DISTINCT FROM "
        "1::bigint OR health.unavailable_count "
        "IS DISTINCT FROM 0::bigint\n THEN "
        f"{REJECT}"
        " END IF;\n"
    )
    eval_guard = (
        "\n -- rootはこのenvelopeを実frameの唯一T5生成値/toke"
        "n identityへ同scope束縛する。\n IF "
        "p_evaluation_json IS NULL OR "
        "pg_catalog.jsonb_typeof(p_evaluation_jso"
        "n) IS DISTINCT FROM 'object'\n OR "
        "(SELECT pg_catalog.array_agg(k ORDER BY "
        "k) FROM pg_catalog.jsonb_object_keys(p_e"
        "valuation_json) k)\n IS DISTINCT FROM "
        "ARRAY['decisions','metrics','native_rule_sha256',"
        "'pa_row','selected',"
        "'source_event_id']::text[]\n OR "
        "p_evaluation_json->'selected' IS "
        "DISTINCT FROM 'true'::jsonb\n OR "
        "p_evaluation_json->>'source_event_id' "
        "IS DISTINCT FROM "
        "p_source_event_id::text\n OR "
        "pg_catalog.jsonb_typeof(p_evaluation_jso"
        "n->'native_rule_sha256') IS DISTINCT "
        "FROM 'string'\n OR "
        "p_evaluation_json->>'native_rule_sha256'"
        " !~ '^[a-f0-9]{64}$'\n OR "
        "p_evaluation_json->'decisions' IS "
        "DISTINCT FROM "
        + "'"
        + json.dumps(
            _current_decisions(), separators=(",", ":"), ensure_ascii=False
        ).replace("'", "''")
        + "'::jsonb\n OR "
        + "pg_catalog.jsonb_typeof(p_evaluation_jso"
        "n->'metrics') IS DISTINCT FROM 'object'\n"
        " OR (SELECT pg_catalog.array_agg(k "
        "ORDER BY k) FROM "
        "pg_catalog.jsonb_object_keys(p_evaluatio"
        "n_json->'metrics') k)\n IS DISTINCT FROM "
        f"{sqlarray}"
        "\n THEN "
        f"{REJECT}"
        " END IF;\n pa_value:=p_evaluation_json->'"
        "pa_row';\n IF pa_value IS DISTINCT FROM "
        "'null'::jsonb THEN\n  IF "
        "pg_catalog.jsonb_typeof(pa_value) IS "
        "DISTINCT FROM 'object'\n  OR (SELECT "
        "pg_catalog.array_agg(k ORDER BY k) FROM "
        "pg_catalog.jsonb_object_keys(pa_value) "
        "k)\n   IS DISTINCT FROM "
        "ARRAY['batter_id','counts_as_ab','half',"
        "'hit_kind','inning',"
        "'ordinal_for_batter','pa_id','rbi',"
        "'rbi_state','reached_by',"
        "'result_display']::text[]\n  OR "
        "event_row.payload#>'{calculation,"
        "response,value,t1,"
        "plateAppearanceEnded}' IS DISTINCT FROM "
        "'true'::jsonb\n  OR "
        "pg_catalog.jsonb_typeof(pa_value->'pa_id"
        "') IS DISTINCT FROM 'string'\n  OR "
        "pa_value->>'pa_id' !~ "
        "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0"
        "-9a-f]{4}-[0-9a-f]{12}$'\n  OR "
        "pg_catalog.jsonb_typeof(pa_value->'batte"
        "r_id') IS DISTINCT FROM 'string'\n  OR "
        "pa_value->>'batter_id' !~ "
        "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0"
        "-9a-f]{4}-[0-9a-f]{12}$'\n  OR "
        "pg_catalog.jsonb_typeof(pa_value->'ordin"
        "al_for_batter') IS DISTINCT FROM "
        "'string'\n  OR "
        "pa_value->>'ordinal_for_batter' !~ "
        "'^[1-9][0-9]*$' OR "
        "pg_catalog.length(pa_value->>'ordinal_fo"
        "r_batter')>20\n  OR "
        "pg_catalog.jsonb_typeof(pa_value->'innin"
        "g') IS DISTINCT FROM 'string'\n  OR "
        "pa_value->>'inning' !~ '^[1-9][0-9]*$' "
        "OR pg_catalog.length(pa_value->>'inning'"
        ")>20\n  OR pg_catalog.jsonb_typeof(pa_val"
        "ue->'half') IS DISTINCT FROM 'string'\n  "
        "OR pa_value->>'half' NOT IN ('top',"
        "'bottom')\n  OR "
        "pg_catalog.jsonb_typeof(pa_value->'resul"
        "t_display') IS DISTINCT FROM 'string'\n  "
        "OR pg_catalog.jsonb_typeof(pa_value->'co"
        "unts_as_ab') IS DISTINCT FROM 'boolean'\n"
        "  OR pg_catalog.jsonb_typeof(pa_value->'"
        "hit_kind') IS DISTINCT FROM 'string'\n  "
        "OR pa_value->>'hit_kind' NOT IN ('none',"
        "'single','double','triple','home_run')\n "
        " OR pg_catalog.jsonb_typeof(pa_value->'r"
        "eached_by') IS DISTINCT FROM 'string'\n  "
        "OR pa_value->'rbi_state' IS DISTINCT "
        "FROM p_evaluation_json#>'{metrics,rbi,"
        "state}'\n  OR pa_value->'rbi' IS "
        "DISTINCT FROM "
        "p_evaluation_json#>'{metrics,rbi,"
        "value}'\n  OR "
        "pg_catalog.length(pa_value->>'rbi')>128\n"
        "  THEN "
        f"{REJECT}"
        " END IF;\n END IF;\n "
        "rule_hash:=p_evaluation_json->>'native_r"
        "ule_sha256';\n IF variant IN "
        "('play-prefix-play-v2',"
        "'play-prefix-play-v3') AND rule_hash IS "
        "DISTINCT FROM\n "
        "event_row.payload#>>'{calculation,"
        "request,source,rulesDigest}' THEN "
        f"{REJECT}"
        " END IF;\n FOR metric IN SELECT key,"
        "value FROM pg_catalog.jsonb_each(p_evalu"
        "ation_json->'metrics') LOOP\n  IF "
        "pg_catalog.jsonb_typeof(metric.value) "
        "IS DISTINCT FROM 'object'\n  OR (SELECT "
        "pg_catalog.array_agg(k ORDER BY k) FROM "
        "pg_catalog.jsonb_object_keys(metric.valu"
        "e) k)\n   IS DISTINCT FROM "
        "ARRAY['credits','display','reason',"
        "'state','value']::text[]\n  OR "
        "pg_catalog.jsonb_typeof(metric.value->'c"
        "redits') IS DISTINCT FROM 'array'\n  OR "
        "pg_catalog.jsonb_array_length(metric.val"
        "ue->'credits')>4\n  THEN "
        f"{REJECT}"
        " END IF;\n  IF "
        "metric.value->>'state'='available' THEN\n"
        "   IF pg_catalog.jsonb_typeof(metric.val"
        "ue->'value') IS DISTINCT FROM 'string'\n "
        "  OR metric.value->>'value' !~ "
        "'^(0|[1-9][0-9]*)$'\n   OR "
        "metric.value->'display' IS DISTINCT "
        "FROM metric.value->'value'\n   OR "
        "metric.value->'reason' IS DISTINCT FROM "
        "'null'::jsonb THEN "
        f"{REJECT}"
        " END IF;\n   amount_sum:=0;\n   FOR "
        "credit IN SELECT value FROM "
        "pg_catalog.jsonb_array_elements(metric.v"
        "alue->'credits') LOOP\n    IF "
        "pg_catalog.jsonb_typeof(credit) IS "
        "DISTINCT FROM 'object'\n    OR (SELECT "
        "pg_catalog.array_agg(k ORDER BY k) FROM "
        "pg_catalog.jsonb_object_keys(credit) k)\n"
        "     IS DISTINCT FROM ARRAY['player_id',"
        "'quantity']::text[]\n    OR "
        "pg_catalog.jsonb_typeof(credit->'player_"
        "id') IS DISTINCT FROM 'string'\n    OR "
        "credit->>'player_id' !~ "
        "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0"
        "-9a-f]{4}-[0-9a-f]{12}$'\n    OR "
        "pg_catalog.jsonb_typeof(credit->'quantit"
        "y') IS DISTINCT FROM 'string'\n    OR "
        "credit->>'quantity' !~ '^[1-9][0-9]*$'\n "
        "   THEN "
        f"{REJECT}"
        " END IF;\n    "
        "amount_sum:=amount_sum+(credit->>'quanti"
        "ty')::numeric;\n   END LOOP;\n   IF "
        "amount_sum IS DISTINCT FROM "
        "(metric.value->>'value')::numeric\n   OR "
        "(SELECT COUNT(DISTINCT x->>'player_id') "
        "FROM pg_catalog.jsonb_array_elements(met"
        "ric.value->'credits') x)\n      IS "
        "DISTINCT FROM "
        "pg_catalog.jsonb_array_length(metric.val"
        "ue->'credits')::bigint\n   THEN "
        f"{REJECT}"
        " END IF;\n  ELSIF "
        "metric.value->>'state'='source_unavailab"
        "le' THEN\n   IF metric.value->'value' IS "
        "DISTINCT FROM 'null'::jsonb OR "
        "metric.value->'display' IS DISTINCT "
        "FROM 'null'::jsonb\n   OR "
        "metric.value->>'reason' NOT IN "
        "('MISSING_OBSERVATION',"
        "'MISSING_ATTRIBUTION')\n   OR "
        "metric.value->>'reason' IS NULL OR "
        "pg_catalog.jsonb_array_length(metric.val"
        "ue->'credits')<>0\n   THEN "
        f"{REJECT}"
        " END IF;\n  ELSE "
        f"{REJECT}"
        " END IF;\n END LOOP;\n SELECT "
        "COALESCE(pg_catalog.array_agg(key ORDER "
        "BY key),'{}'::text[]) INTO new_keys\n "
        "FROM pg_catalog.jsonb_each(p_evaluation_"
        "json->'metrics') WHERE "
        "value->>'state'='available';\n "
        "eval_hash:=pg_catalog.encode(pg_catalog."
        "sha256(pg_catalog.convert_to(p_evaluatio"
        "n_json::text,'UTF8')),'hex');\n"
    )
    write_body = (
        "\n SELECT v.* INTO series FROM "
        "sync_fence.stats_fact_versions v\n WHERE "
        "v.tenant_id=tenant AND "
        "v.game_id=p_game_id AND "
        "v.model_sha256=p_model_sha256\n AND "
        "v.is_current AND v.invalidated_at IS "
        "NULL FOR UPDATE;\n had_series:=FOUND;\n "
        "IF had_series THEN\n  IF "
        "series.completion_state IS DISTINCT "
        "FROM 'current_open' OR "
        "series.rule_sha256 IS DISTINCT FROM "
        "rule_hash\n  OR "
        "series.t5_artifact_set_sha256 IS "
        "DISTINCT FROM "
        "'"
        f"{ART}"
        "' THEN "
        f"{REJECT}"
        " END IF;\n  SELECT s.* INTO prior_source "
        "FROM sync_fence.stats_primitive_sources "
        "s\n  WHERE s.tenant_id=tenant AND "
        "s.game_id=p_game_id AND "
        "s.fact_version_id=series.id AND "
        "s.source_event_id=p_source_event_id;\n  "
        "IF FOUND THEN\n   -- 同TXの同qualified "
        "source/evalだけを再掲。別TXの旧admissionは上段で拒否済み。"
        "\n   IF prior_source.attempt_id IS "
        "DISTINCT FROM p_attempt_id OR "
        "prior_source.phase_id IS DISTINCT FROM "
        "p_phase_id\n   OR "
        "prior_source.evaluation_sha256 IS "
        "DISTINCT FROM eval_hash OR "
        "prior_source.metric_states IS DISTINCT "
        "FROM p_evaluation_json\n   OR "
        "prior_source.slot_version IS DISTINCT "
        "FROM current_source.slot_version\n   OR "
        "prior_source.play_row_version IS "
        "DISTINCT FROM saved_play.version\n   OR "
        "prior_source.source_fingerprint IS "
        "DISTINCT FROM binding.event_fingerprint\n"
        "   OR prior_source.artifact_sha256 IS "
        "DISTINCT FROM "
        "current_source.artifact_sha256\n   THEN "
        f"{REJECT}"
        " END IF;\n   IF series.revision IS "
        "DISTINCT FROM p_expected_revision+1 "
        "THEN "
        f"{REJECT}"
        " END IF;\n   IF p_expected_revision=0 "
        "THEN\n    IF series.source_count<>1 OR "
        "p_expected_source_set_sha256 IS NOT "
        "NULL THEN "
        f"{REJECT}"
        " END IF;\n   ELSE\n    SELECT * INTO "
        "STRICT previous_health FROM "
        "("
        f"{PREVIOUS}"
        ") idempotent_previous_health;\n    IF "
        "previous_health.game_count IS DISTINCT "
        "FROM 1::bigint\n    OR "
        "previous_health.unavailable_count IS "
        "DISTINCT FROM 0::bigint\n    OR "
        "previous_health.canonical_source_count "
        "IS DISTINCT FROM series.source_count-1\n "
        "   OR previous_health.canonical_source_s"
        "et_sha256 IS DISTINCT FROM "
        "p_expected_source_set_sha256\n    THEN "
        f"{REJECT}"
        " END IF;\n   END IF;\n   "
        "p_fact_version_id:=series.id; "
        "p_revision:=series.revision; "
        "p_source_set_sha256:=series.source_set_s"
        "ha256;\n   p_player_id:=(event_row.payloa"
        "d#>>'{participants,pitcherId}')::uuid;\n "
        "  SELECT * INTO STRICT audit FROM "
        "("
        f"{COUNT}"
        ") idempotent_counts;\n   "
        f"{count_check}"
        "\n   RETURN QUERY SELECT series.id,"
        "p_source_event_id,p_model_sha256,"
        "series.source_set_sha256;\n   RETURN;\n  "
        "END IF;\n  IF series.revision IS "
        "DISTINCT FROM p_expected_revision OR "
        "series.source_set_sha256 IS DISTINCT "
        "FROM p_expected_source_set_sha256\n  "
        "THEN "
        f"{REJECT}"
        " END IF;\n  SELECT * INTO STRICT "
        "previous_health FROM "
        "("
        f"{PREVIOUS}"
        ") previous_canonical_health;\n  IF "
        "previous_health.game_count IS DISTINCT "
        "FROM 1::bigint OR "
        "previous_health.unavailable_count IS "
        "DISTINCT FROM 0::bigint\n  OR "
        "previous_health.canonical_source_count "
        "IS DISTINCT FROM series.source_count\n  "
        "OR previous_health.canonical_source_set_"
        "sha256 IS DISTINCT FROM "
        "series.source_set_sha256\n  OR "
        "health.canonical_source_count IS "
        "DISTINCT FROM series.source_count+1\n  "
        "THEN "
        f"{REJECT}"
        " END IF;\n ELSE\n  IF "
        "p_expected_revision<>0 OR "
        "p_expected_source_set_sha256 IS NOT "
        "NULL OR health.canonical_source_count<>1"
        "\n  THEN "
        f"{REJECT}"
        " END IF;\n  INSERT INTO "
        "sync_fence.stats_fact_versions(tenant_id"
        ",game_id,id,model_sha256,rule_sha256,\n  "
        "t5_artifact_set_sha256,"
        "source_set_sha256,source_count,revision,"
        "last_generation,last_d1,last_d2,"
        "updated_at,\n  computed_metric_keys,"
        "is_current,completion_state,"
        "completion_receipt_id,"
        "public_pointer_receipt_id,created_at,"
        "invalidated_at)\n  VALUES(tenant,"
        "p_game_id,pg_catalog.gen_random_uuid(),"
        "p_model_sha256,rule_hash,"
        "'"
        f"{ART}"
        "',\n  health.canonical_source_set_sha256,"
        "1,1,event_row.generation,event_row.d1,"
        "event_row.d2,"
        "pg_catalog.clock_timestamp(),\n  "
        "new_keys,true,'current_open',NULL,NULL,"
        "pg_catalog.clock_timestamp(),NULL) "
        "RETURNING * INTO STRICT series;\n END "
        "IF;\n INSERT INTO "
        "sync_fence.stats_primitive_sources(tenan"
        "t_id,game_id,fact_version_id,"
        "source_event_id,play_row_id,\n "
        "recording_generation,d1,d2,slot_version,"
        "play_row_version,provider_kind,"
        "attempt_id,phase_id,wire_d4,"
        "source_fingerprint,\n checkpoint_id,"
        "checkpoint_revision,checkpoint_digest,"
        "frame_digest,evaluation_sha256,"
        "artifact_sha256,rule_sha256,\n "
        "metric_states,computed_metric_keys,"
        "saved_at)\n VALUES(tenant,p_game_id,"
        "series.id,p_source_event_id,"
        "saved_play.id,event_row.generation,"
        "event_row.d1,event_row.d2,\n "
        "current_source.slot_version,"
        "saved_play.version,provider,"
        "p_attempt_id,p_phase_id,binding.wire_d4,"
        "binding.event_fingerprint,\n "
        "checkpoint_id,checkpoint_revision,"
        "checkpoint_digest,frame_digest,"
        "eval_hash,current_source.artifact_sha256"
        ",rule_hash,\n p_evaluation_json,new_keys,"
        "pg_catalog.clock_timestamp());\n FOR "
        "metric IN SELECT key,value FROM "
        "pg_catalog.jsonb_each(p_evaluation_json-"
        ">'metrics') LOOP\n  credit_ordinal:=0;\n  "
        "FOR credit IN SELECT value FROM "
        "pg_catalog.jsonb_array_elements(metric.v"
        "alue->'credits') LOOP\n   INSERT INTO "
        "sync_fence.stats_primitive_facts(tenant_"
        "id,game_id,fact_version_id,"
        "source_event_id,\n   metric_id,player_id,"
        "credit_ordinal,state,amount)\n   "
        "VALUES(tenant,p_game_id,series.id,"
        "p_source_event_id,metric.key,"
        "(credit->>'player_id')::uuid,\n   "
        "credit_ordinal,'available',"
        "(credit->>'quantity')::numeric);\n   "
        "credit_ordinal:=credit_ordinal+1;\n  END "
        "LOOP;\n END LOOP;\n IF had_series THEN\n  "
        "UPDATE sync_fence.stats_fact_versions v "
        "SET revision=v.revision+1,\n  "
        "source_set_sha256=health.canonical_sourc"
        "e_set_sha256,"
        "source_count=health.canonical_source_cou"
        "nt,\n  computed_metric_keys=ARRAY(SELECT "
        "x FROM pg_catalog.unnest(v.computed_metr"
        "ic_keys) x WHERE x=ANY(new_keys) ORDER "
        "BY x),\n  last_generation=event_row.gener"
        "ation,last_d1=event_row.d1,"
        "last_d2=event_row.d2,"
        "updated_at=pg_catalog.clock_timestamp()\n"
        "  WHERE v.tenant_id=tenant AND "
        "v.game_id=p_game_id AND v.id=series.id "
        "AND v.is_current AND v.invalidated_at "
        "IS NULL\n  AND "
        "v.completion_state='current_open' AND "
        "v.revision=p_expected_revision AND "
        "v.source_set_sha256=p_expected_source_se"
        "t_sha256\n  AND "
        "v.model_sha256=p_model_sha256 AND "
        "v.rule_sha256=rule_hash AND "
        "v.t5_artifact_set_sha256='"
        f"{ART}"
        "'\n  RETURNING * INTO STRICT series;\n "
        "END IF;\n p_fact_version_id:=series.id; "
        "p_revision:=series.revision; "
        "p_source_set_sha256:=series.source_set_s"
        "ha256;\n p_player_id:=(event_row.payload#"
        ">>'{participants,pitcherId}')::uuid;\n "
        "SELECT * INTO STRICT audit FROM "
        "("
        f"{COUNT}"
        ") completed_counts;\n "
        f"{count_check}"
        "\n RETURN QUERY SELECT series.id,"
        "p_source_event_id,p_model_sha256,"
        "series.source_set_sha256;\n"
    )
    # writerは終了直前にも同じ実bindingを再検査する。nonceは既leaseからcoreが注入する。
    write_body = write_body.replace(
        " RETURN QUERY SELECT series.id",
        (
            " PERFORM sync_fence_api.assert_writer_bi"
            "nding(tenant,p_attempt_id,p_phase_id,"
            "p_binding_nonce,binding.device_id,"
            "binding.game_id);\n RETURN QUERY SELECT "
            "series.id"
        ),
    )
    # writerは実xidを照合し、READ COMMITTEDのsnapshot変化を別TXと誤認しない。
    write_body = write_body.replace(
        (
            " OR audit.transaction_id IS DISTINCT "
            "FROM pg_catalog.pg_current_snapshot()::t"
            "ext\n"
        ),
        "\n",
    )
    functions["save_primitive_source"] = function(
        "save_primitive_source",
        (
            "p_attempt_id uuid,p_phase_id uuid,"
            "p_source_event_id uuid,p_model_sha256 "
            "text,p_expected_revision bigint,"
            "p_expected_source_set_sha256 text,"
            "p_evaluation_json jsonb,p_binding_nonce "
            "bytea"
        ),
        (
            "fact_version_id uuid,source_event_id "
            "uuid,model_sha256 text,"
            "source_set_sha256 "
            "text"
        ),
        (
            "tenant uuid; own_xid text; p_game_id "
            "uuid; p_player_id uuid; "
            "p_fact_version_id uuid; p_revision "
            "bigint; p_source_set_sha256 text;\n "
            "binding sync_fence.writer_bindings%ROWTY"
            "PE; event_row "
            "public.operation_events%ROWTYPE;\n "
            "saved_play public.play_rows%ROWTYPE; "
            "checkpoint sync_fence.ordinary_pitch_che"
            "ckpoints%ROWTYPE;\n series "
            "sync_fence.stats_fact_versions%ROWTYPE; "
            "prior_source "
            "sync_fence.stats_primitive_sources%ROWTY"
            "PE;\n stamp jsonb; pa_value jsonb; "
            "variant text; provider text; "
            "checkpoint_id uuid; checkpoint_revision "
            "bigint; checkpoint_digest text; "
            "frame_digest text;\n current_source "
            "record; health record; previous_health "
            "record; audit record;\n rule_hash text; "
            "eval_hash text; metric record; credit "
            "jsonb; amount_sum numeric; "
            "credit_ordinal bigint; new_keys text[]; "
            "had_series boolean;"
        ),
        save_guard + eval_guard + write_body,
    )
    functions = {
        n: s.replace("array_agg(k ORDER BY k)", 'array_agg(k ORDER BY k COLLATE "C")')
        for n, s in functions.items()
    }
    return functions
