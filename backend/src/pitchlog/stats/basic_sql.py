"""基本成績の候補SQLを、既存の単一T6生成SQLから組み立てる。

式・集計・率は ``stats/generated/stats.sql`` を唯一の正とし、このmoduleは
scope条件（試合/暦年・公式/暫定）と関数境界だけを追加する。手書きの集計式を
持たない。
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
_STATS_SQL = ROOT / "backend/src/pitchlog/stats/generated/stats.sql"
_MODEL = ROOT / "backend/domain/play-export.model.json"

_FUNCTION_SCHEMA = "stats_basic_api"
_READ_FUNCTION = "read_basic_stats"
_FINALIZE_FUNCTION = "finalize_game_stats"
_READ_ARGS = (
    "p_tenant_id uuid,p_game_id text,p_year_start text,p_year_end text,"
    "p_category text,p_raw_game_type_keys text,p_official boolean,"
    "p_after_player_id text,p_page_size integer,p_model_sha256 text"
)
_READ_RETURNS = (
    "player_id uuid,player_name text,uniform_number text,team_record_id uuid,"
    "team_name text,metrics_json text"
)
_REJECT = "RAISE EXCEPTION 'basic stats boundary rejected' USING ERRCODE='42501';"


class BasicSqlError(ValueError):
    """生成SQLの前提が崩れた場合。"""


def _replace_once(text: str, needle: str, replacement: str) -> str:
    """既生成SQLの対象条件が一箇所だけであることを強制する。"""
    if text.count(needle) != 1:
        raise BasicSqlError(f"生成SQLの対象条件が一箇所ではありません: {needle[:40]}")
    return text.replace(needle, replacement)


def _replace_all(text: str, needle: str, replacement: str) -> str:
    """複数箇所に同じscope条件がある場合だけ全置換する。"""
    if text.count(needle) < 1:
        raise BasicSqlError(f"生成SQLの対象条件がありません: {needle[:40]}")
    return text.replace(needle, replacement)


def read_query() -> str:
    """公式/暫定・試合/暦年のscopeを差し替えたT6 queryを返す。"""
    text = _STATS_SQL.read_text()
    text = text.rstrip().removesuffix(";")
    # 位置bindへ写す。値はPL/pgSQLのEXECUTE USINGで渡す。
    text = _replace_all(text, ":tenant_id", "$1")
    text = _replace_all(text, ":player_id", "$2")
    text = _replace_all(text, ":model_sha256", "$3")
    text = _replace_all(text, "CAST(:raw_game_type_keys AS text[])", "($7::text[])")
    text = _replace_all(text, ":named_category", "$6")
    # 終了確定のみ/再開中を含む暫定の切替。既存式は変更しない。
    text = _replace_once(
        text,
        "AND g.status='finished'",
        "AND (($9 AND g.status='finished') OR "
        "(NOT $9 AND g.status IN ('in_progress','finished')))",
    )
    text = _replace_once(
        text,
        "AND v.completion_state='confirmed_ended'\n"
        "   AND v.completion_receipt_id IS NOT NULL AND "
        "v.public_pointer_receipt_id IS NOT NULL",
        "AND (($9 AND v.completion_state='confirmed_ended'\n"
        "   AND v.completion_receipt_id IS NOT NULL AND "
        "v.public_pointer_receipt_id IS NOT NULL)\n"
        "   OR (NOT $9 AND v.completion_state='current_open'))",
    )
    scope = (
        "AND ((($8 IS NOT NULL) AND g.id=$8) OR "
        "(($8 IS NULL) AND g.scheduled_at>=$4::timestamptz "
        "AND g.scheduled_at<$5::timestamptz))"
    )
    text = _replace_all(
        text,
        "AND g.scheduled_at>=:year_start_jst AND g.scheduled_at<:year_end_jst",
        scope,
    )
    if re.search(
        r":(tenant_id|player_id|model_sha256|named_category|raw_game_type_keys|"
        r"year_start_jst|year_end_jst|fact_version_id|revision|source_set_sha256|"
        r"after_d2|after_source_event_id|after_metric_id|page_size)",
        text,
    ):
        raise BasicSqlError("未置換のbindが残っています")
    return text


def _named_scopes() -> dict[str, list[str]]:
    """モデル宣言の公式/練習/合算写像をそのまま読む。"""
    import json

    model = json.loads(_MODEL.read_text())
    groups = model["calculations"][0]["typedProgram"]["namedScopes"]["groups"]
    if set(groups) != {"official", "practice", "all"}:
        raise BasicSqlError("named scopeの閉集合が不一致")
    return groups


def _category_case() -> str:
    """生成SQLと同じ固定写像を関数境界の照合にも使う。"""
    groups = _named_scopes()

    def array(keys: list[str]) -> str:
        return "ARRAY[" + ",".join("'" + key + "'" for key in keys) + "]::text[]"

    return (
        "CASE p_category WHEN 'official' THEN "
        + array(groups["official"])
        + " WHEN 'practice' THEN "
        + array(groups["practice"])
        + " WHEN 'all' THEN "
        + array(groups["all"])
        + " ELSE NULL::text[] END"
    )


def read_function_body() -> str:
    """実DBへ配置する基本成績read関数の完全なCREATE文を返す。"""
    query = read_query()
    player_scope = f"""
 game_uuid:=NULLIF(p_game_id,'')::uuid;
 IF game_uuid IS NOT NULL THEN
  SELECT count(*) INTO game_count FROM public.games g
   WHERE g.tenant_id=tenant AND g.id=game_uuid
     AND g.hidden_at IS NULL AND g.trashed_at IS NULL
     AND g.status NOT IN ('hidden','trashed');
  IF game_count<>1 THEN
   RAISE EXCEPTION 'basic stats game boundary rejected' USING ERRCODE='42501';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
      JOIN public.games g ON g.tenant_id=v.tenant_id AND g.id=v.game_id
      WHERE v.tenant_id=tenant AND v.game_id=game_uuid
        AND v.model_sha256=p_model_sha256 AND v.is_current
        AND v.invalidated_at IS NULL
        AND (($9 AND v.completion_state='confirmed_ended'
              AND v.completion_receipt_id IS NOT NULL
              AND v.public_pointer_receipt_id IS NOT NULL)
             OR (NOT $9 AND v.completion_state='current_open'))
        AND (($9 AND g.status='finished')
             OR (NOT $9 AND g.status IN ('in_progress','finished')))) THEN
   RETURN;
  END IF;
 END IF;
 IF game_uuid IS NULL AND (NOT p_official OR p_year_start IS NULL OR
     p_year_end IS NULL OR p_year_end::timestamptz<=p_year_start::timestamptz) THEN
  RAISE EXCEPTION 'basic stats season boundary rejected' USING ERRCODE='42501';
 END IF;
 IF game_uuid IS NULL THEN
  IF NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
      JOIN public.games g ON g.tenant_id=v.tenant_id AND g.id=v.game_id
      WHERE v.tenant_id=tenant AND v.model_sha256=p_model_sha256
        AND v.is_current AND v.invalidated_at IS NULL
        AND v.completion_state='confirmed_ended'
        AND v.completion_receipt_id IS NOT NULL
        AND v.public_pointer_receipt_id IS NOT NULL
        AND g.hidden_at IS NULL AND g.trashed_at IS NULL
        AND g.status='finished' AND g.scheduled_at>=p_year_start::timestamptz
        AND g.scheduled_at<p_year_end::timestamptz
        AND g.game_type_key=ANY({_category_case()})) THEN
   RETURN;
  END IF;
 END IF;
 IF p_official IS NULL OR p_page_size IS NULL OR p_page_size<1 OR p_page_size>200 THEN
  RAISE EXCEPTION 'basic stats page boundary rejected' USING ERRCODE='42501';
 END IF;
 IF p_after_player_id IS NOT NULL AND p_after_player_id<>'' THEN
  IF p_after_player_id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
   RAISE EXCEPTION 'basic stats cursor boundary rejected' USING ERRCODE='42501';
  END IF;
 END IF;
 IF p_category NOT IN ('official','practice','all') THEN
  RAISE EXCEPTION 'basic stats category boundary rejected' USING ERRCODE='42501';
 END IF;
"""
    # 静的SQLでは関数引数名を使う。$9は動的queryのEXECUTE USING専用。
    player_scope = player_scope.replace("$9", "p_official")
    loop = """
 FOR player IN
  SELECT p.id,p.name,p.uniform_number,p.team_record_id,tr.name AS team_name
   FROM public.players p
   JOIN public.team_records tr
     ON tr.tenant_id=p.tenant_id AND tr.id=p.team_record_id
   WHERE p.tenant_id=tenant AND p.hidden_at IS NULL
     AND tr.hidden_at IS NULL
     AND (
       (game_uuid IS NOT NULL AND p.team_record_id IN (
         SELECT g.away_team_record_id FROM public.games g
          WHERE g.tenant_id=tenant AND g.id=game_uuid
         UNION
         SELECT g.home_team_record_id FROM public.games g
          WHERE g.tenant_id=tenant AND g.id=game_uuid))
       OR
       (game_uuid IS NULL AND tr.kind='self')
     )
     AND (p_after_player_id IS NULL OR p_after_player_id='' OR
          p.id>NULLIF(p_after_player_id,'')::uuid)
   ORDER BY p.id
   LIMIT p_page_size+1
 LOOP
  metrics := '{}'::jsonb;
  FOR metric IN EXECUTE query USING tenant,player.id,p_model_sha256,
      p_year_start,p_year_end,p_category,raw_keys,game_uuid,p_official LOOP
   metrics := metrics || pg_catalog.jsonb_build_object(
     metric.metric_id,
     pg_catalog.jsonb_build_object('state',metric.state,
       'value',CASE WHEN metric.value IS NULL THEN NULL
                    ELSE metric.value::text END));
  END LOOP;
  RETURN QUERY SELECT player.id,player.name,
    COALESCE(player.uniform_number,''),player.team_record_id,player.team_name,
    metrics::text;
 END LOOP;
"""
    return (
        "CREATE FUNCTION "
        f"{_FUNCTION_SCHEMA}.{_READ_FUNCTION}({_READ_ARGS})\n"
        f"RETURNS TABLE({_READ_RETURNS}) LANGUAGE plpgsql STABLE SECURITY DEFINER\n"
        "SET search_path=pg_catalog,pg_temp AS $basic$\n"
        "#variable_conflict use_column\n"
        "DECLARE tenant uuid; game_uuid uuid; game_count bigint; raw_keys text[]; "
        "player record; metric record; metrics jsonb; query text:=$q$"
        + query
        + "$q$;\nBEGIN\n"
        " tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;\n"
        " IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM "
        "'pitchlog_sync_right_fn_owner'\n"
        "  OR tenant IS NULL OR p_tenant_id IS DISTINCT FROM tenant\n"
        "  OR p_model_sha256 IS DISTINCT FROM 'sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d'\n"
        "  OR pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'repeatable read'\n"
        "  OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'\n"
        " THEN "
        + _REJECT
        + "\n END IF;\n"
        + player_scope
        + " raw_keys:=string_to_array(p_raw_game_type_keys,',');\n"
        " IF raw_keys IS NULL OR pg_catalog.array_position(raw_keys,NULL) IS NOT NULL\n"
        "  OR raw_keys IS DISTINCT FROM ("
        + _category_case()
        + ") THEN\n"
        + _REJECT
        + "\n END IF;\n"
        + loop
        + "END;\n$basic$;\n"
    )


def finalize_function_body() -> str:
    """終了確定版だけを最新版へ昇格する候補関数を返す。"""
    return (
        "CREATE FUNCTION "
        f"{_FUNCTION_SCHEMA}.{_FINALIZE_FUNCTION}("
        "p_tenant_id uuid,p_game_id uuid,p_completion_receipt_id uuid,"
        "p_public_pointer_receipt_id uuid,p_model_sha256 text)\n"
        "RETURNS TABLE(fact_version_id uuid,revision bigint,completion_state text)\n"
        "LANGUAGE plpgsql VOLATILE SECURITY DEFINER\n"
        "SET search_path=pg_catalog,pg_temp AS $finalize$\n"
        "#variable_conflict use_column\n"
        "DECLARE tenant uuid; series record; fact_version_id uuid; "
        "revision bigint; completion_state text;\nBEGIN\n"
        " tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;\n"
        " IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM "
        "'pitchlog_sync_right_fn_owner'\n"
        "  OR tenant IS NULL OR p_tenant_id IS DISTINCT FROM tenant\n"
        "  OR p_game_id IS NULL OR p_completion_receipt_id IS NULL\n"
        "  OR p_public_pointer_receipt_id IS NULL\n"
        "  OR p_model_sha256 IS DISTINCT FROM 'sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d'\n"
        "  OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'\n"
        " THEN " + _REJECT + "\n END IF;\n"
        " IF NOT EXISTS(SELECT 1 FROM public.games g WHERE g.tenant_id=tenant\n"
        "   AND g.id=p_game_id AND g.status='finished'\n"
        "   AND g.hidden_at IS NULL AND g.trashed_at IS NULL) THEN\n"
        "  RAISE EXCEPTION 'basic stats finalize game not found' USING ERRCODE='42501';\n"
        " END IF;\n"
        " UPDATE sync_fence.stats_fact_versions v\n"
        "  SET completion_state='confirmed_ended',\n"
        "      completion_receipt_id=p_completion_receipt_id,\n"
        "      public_pointer_receipt_id=p_public_pointer_receipt_id,\n"
        "      updated_at=pg_catalog.now()\n"
        "  WHERE v.tenant_id=tenant AND v.game_id=p_game_id\n"
        "    AND v.model_sha256=p_model_sha256 AND v.is_current\n"
        "    AND v.invalidated_at IS NULL AND v.completion_state='current_open'\n"
        "  RETURNING v.id,v.revision,v.completion_state INTO "
        "fact_version_id,revision,completion_state;\n"
        " IF FOUND THEN\n"
        "  RETURN QUERY SELECT fact_version_id,revision,completion_state;\n"
        "  RETURN;\n"
        " END IF;\n"
        " SELECT v.* INTO series FROM sync_fence.stats_fact_versions v\n"
        "  WHERE v.tenant_id=tenant AND v.game_id=p_game_id\n"
        "    AND v.model_sha256=p_model_sha256 AND v.is_current\n"
        "    AND v.invalidated_at IS NULL;\n"
        " IF NOT FOUND OR series.completion_state<>'confirmed_ended'\n"
        "    OR series.completion_receipt_id IS DISTINCT FROM p_completion_receipt_id\n"
        "    OR series.public_pointer_receipt_id IS DISTINCT FROM p_public_pointer_receipt_id THEN\n"
        "  RAISE EXCEPTION 'basic stats finalize version not found' USING ERRCODE='42501';\n"
        " END IF;\n"
        " RETURN QUERY SELECT series.id,series.revision,series.completion_state;\n"
        "END;\n$finalize$;\n"
    )


def _schema_sql() -> str:
    """候補schemaの所有者/USAGEだけを返す。"""
    return (
        "-- 基本成績MVP候補: 正式authz catalogへ未登録。owned隔離DBの検証だけに使う。\n"
        "DO $schema$\nBEGIN\n"
        " IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n\n"
        "   JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner\n"
        "   WHERE n.nspname='stats_basic_api' AND r.rolname='pitchlog_owner') THEN\n"
        "  IF EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='stats_basic_api') THEN\n"
        "   RAISE EXCEPTION 'stats_basic_api schema owner collision';\n"
        "  END IF;\n"
        "  CREATE SCHEMA stats_basic_api AUTHORIZATION pitchlog_owner;\n"
        " END IF;\nEND;$schema$;\n"
        "REVOKE ALL ON SCHEMA stats_basic_api FROM PUBLIC;\n"
        "GRANT USAGE ON SCHEMA stats_basic_api TO pitchlog_app;\n"
    )


def candidate_sql() -> str:
    """製品候補のread関数だけを返す。

    finalizeは製品関数として公開しない。終了確定providerが自身のTX内で
    真正receiptとともにcompletion列を更新する。``finalize_candidate_sql`` は
    owned隔離DBのread検証専用で、正式catalog/HTTPへ接続しない。
    """
    owner = "pitchlog_sync_right_fn_owner"
    read_identity = f"{_FUNCTION_SCHEMA}.{_READ_FUNCTION}({_READ_ARGS})"
    return (
        _schema_sql()
        + read_function_body()
        + f"ALTER FUNCTION {read_identity} OWNER TO {owner};\n"
        + f"REVOKE ALL ON FUNCTION {read_identity} FROM PUBLIC,pitchlog_app;\n"
        + f"GRANT EXECUTE ON FUNCTION {read_identity} TO pitchlog_app;\n"
    )


def finalize_candidate_sql() -> str:
    """owned隔離DBのread検証専用finalize。正式catalog/HTTPへ接続しない。"""
    owner = "pitchlog_sync_right_fn_owner"
    finalize_identity = (
        f"{_FUNCTION_SCHEMA}.{_FINALIZE_FUNCTION}(uuid,uuid,uuid,uuid,text)"
    )
    return (
        "-- TEST ONLY: 正式な終了確定providerではない。catalog/HTTPへ接続しない。\n"
        + finalize_function_body()
        + f"ALTER FUNCTION {finalize_identity} OWNER TO {owner};\n"
        + f"REVOKE ALL ON FUNCTION {finalize_identity} FROM PUBLIC,pitchlog_app;\n"
        + f"GRANT EXECUTE ON FUNCTION {finalize_identity} TO pitchlog_app;\n"
    )
