"""既確定Sと保存T1だけから毎球CSVの球数・回別表示SQLを生成する。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pprint import pformat

from jsonschema import Draft202012Validator

from pitchlog.authz.stats_primitive_sql import _verified_inputs
from pitchlog.domaingen.core import _canonical_hash

_ROOT = Path(__file__).resolve().parents[4]
_MODEL = "backend/domain/play-export-score.model.json"
_SCHEMA = "backend/domain/play-export-score.schema.json"
_TARGET = "backend/src/pitchlog/exports/generated/play_export_score.sql"
_COMPLETION_TARGET = "backend/src/pitchlog/exports/generated/play_export_completion.py"
_MANIFEST = "backend/domain/play-export-score.manifest.json"
_CANONICAL = "backend/src/pitchlog/exports/generated/play_primitives_native.sql"


class PlayExportScoreDeclarationError(ValueError):
    """宣言・既確定S・生成SQLの不一致を拒否する。"""


def _completion_sql(profiles: list[dict]) -> str:
    """閉じたV7/T2組ごとの半回完了値をSQL CASEへ写す。"""
    clauses = []
    for profile in profiles:
        conditions = [
            f"b.payload->>'formatVersion'='{profile['sourceFormat']}'",
            "b.payload#>>'{calculation,formatVersion}'="
            f"'{profile['calculationFormat']}'",
            f"b.payload#>>'{{calculation,response,value,t2,kind}}'='{profile['kind']}'",
        ]
        scope = profile["scope"]
        if scope is None:
            conditions.append(
                "b.payload#>>'{calculation,response,value,t2,scope}' IS NULL"
            )
        else:
            conditions.append(
                f"b.payload#>>'{{calculation,response,value,t2,scope}}'='{scope}'"
            )
        path = profile["path"]
        if path is None:
            value = "'false'::jsonb"
        else:
            value = (
                "b.payload#>'{calculation,response,value,t2," + ",".join(path) + "}'"
            )
        clauses.append("WHEN " + " AND ".join(conditions) + " THEN " + value)
    return "CASE\n    " + "\n    ".join(clauses) + "\n    ELSE NULL END"


def _completion_python(profiles: list[dict]) -> str:
    """同じ閉宣言から表示投影用T2読取器を生成する。"""
    return f'''"""自動生成: 保存V7/T2の半回完了値を閉形で読む。"""

from __future__ import annotations

_PROFILES = {pformat(tuple(profiles), width=79, sort_dicts=True)}


def saved_half_completed(payload: dict) -> bool:
    """宣言済みのsource/calculation/T2形だけを受理する。"""
    try:
        calculation = payload["calculation"]
        t2 = calculation["response"]["value"]["t2"]
        for profile in _PROFILES:
            if (
                payload["formatVersion"] != profile["sourceFormat"]
                or calculation["formatVersion"] != profile["calculationFormat"]
                or t2["kind"] != profile["kind"]
                or t2.get("scope") != profile["scope"]
            ):
                continue
            path = profile["path"]
            if path is None:
                return False
            if type(path) is not list:
                raise ValueError("保存T2参照経路が不正")
            value = t2
            for key in path:
                value = value[key]
            if type(value) is not bool or (
                profile["value"] is not None and value is not profile["value"]
            ):
                raise ValueError("保存T2完了値が不正")
            return value
    except (KeyError, TypeError):
        pass
    raise ValueError("保存V7/T2の閉形が不正")
'''


def _canonical_parts(sections: dict[str, str]) -> tuple[str, str]:
    """既生成SのCTEと会員JOINを全byteの閉位置から抽出する。"""
    canonical = sections["canonical_members"]
    member = sections["canonical_source_members"]
    marker = "\nSELECT * FROM canonical_s\nWHERE "
    source_marker = "\nSELECT s.* FROM "
    if canonical.count(marker) != 1 or member.count(source_marker) != 1:
        raise PlayExportScoreDeclarationError("既生成selectorの節境界が不正")
    prefix, _ = canonical.split(marker)
    _, from_source = member.split(source_marker)
    if (
        not prefix.startswith("WITH canonical_scope AS (")
        or not prefix.endswith("\n)")
        or not from_source.endswith(";")
        or "c.source_state='included'" not in from_source
        or "s.fact_version_id=:fact_version_id" not in from_source
    ):
        raise PlayExportScoreDeclarationError("既生成selectorの内容が不正")
    return prefix, "SELECT s.* FROM " + from_source[:-1]


def _score_query(model: dict, sections: dict[str, str]) -> str:
    """確定会員に束縛したGROUP BY/windowだけをSQLへ下げる。"""
    prefix, member_query = _canonical_parts(sections)
    slots = model["scoreboard"]["legacyInningSlots"]
    metric = model["pitchCount"]["metricId"]
    state_path = ",".join(model["pitchCount"]["metricStatePath"])
    event_kinds = model["pitchCount"]["sourceEventKinds"]
    row_kinds = ",".join(f"'{item['playRow']}'" for item in event_kinds)
    kind_match = " OR ".join(
        "(p.event_kind='"
        + item["playRow"]
        + "' AND e.payload#>>'{calculation,request,t1,pitchEventKind}'='"
        + item["t1"]
        + "')"
        for item in event_kinds
    )
    bounded_kind_match = " OR ".join(
        "(b.event_kind='"
        + item["playRow"]
        + "' AND b.payload#>>'{calculation,request,t1,pitchEventKind}'='"
        + item["t1"]
        + "')"
        for item in event_kinds
    )
    source_hash = _canonical_hash(model)
    complete = _completion_sql(model["scoreboard"]["completeProfiles"])
    # 保存T1のbefore/after以外から得点・H/E/K/Bを再判定しない。
    return f"""-- 自動生成 D-1 score model={source_hash}
-- SELECT実行はwriter専用資格関数と同一transactionに限定する。
{prefix}, version_scope AS (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 JOIN canonical_health h ON h.tenant_id=v.tenant_id AND h.game_id=v.game_id
 WHERE v.tenant_id=:tenant_id AND v.game_id=:game_id
   AND v.id=:fact_version_id AND v.model_sha256=:model_sha256
   AND v.source_set_sha256=:source_set_sha256 AND v.revision=:revision
   AND v.is_current AND v.invalidated_at IS NULL
   AND v.completion_state='current_open'
   AND h.game_count=1 AND h.unavailable_count=0
   AND h.canonical_source_count=v.source_count
   AND h.canonical_source_set_sha256=v.source_set_sha256
), candidate_members AS (
 {member_query}
), source_members AS (
 SELECT s.* FROM candidate_members s JOIN version_scope v
   ON (v.tenant_id,v.game_id,v.id)=(s.tenant_id,s.game_id,s.fact_version_id)
), member_health AS (
 SELECT v.id,COUNT(s.source_event_id) AS actual_count,v.source_count
 FROM version_scope v LEFT JOIN source_members s
   ON (s.tenant_id,s.game_id,s.fact_version_id)=(v.tenant_id,v.game_id,v.id)
 GROUP BY v.id,v.source_count
), target AS (
 SELECT s.source_event_id,s.d2,p.pitcher_id
 FROM source_members s JOIN public.play_rows p
   ON (p.tenant_id,p.game_id,p.id)=(s.tenant_id,s.game_id,s.play_row_id)
 JOIN public.operation_events e
   ON (e.tenant_id,e.game_id,e.id)=(s.tenant_id,s.game_id,s.source_event_id)
 WHERE s.source_event_id=:source_event_id AND p.event_kind IN ({row_kinds})
   AND p.source_event_id=s.source_event_id AND p.version=s.play_row_version
   AND ({kind_match})
), bounded AS (
 SELECT s.*,e.payload,p.event_kind,p.pitcher_id
 FROM source_members s JOIN target t
   ON (s.d2,s.source_event_id)<=(t.d2,t.source_event_id)
 JOIN public.operation_events e
   ON (e.tenant_id,e.game_id,e.id)=(s.tenant_id,s.game_id,s.source_event_id)
 JOIN public.play_rows p
   ON (p.tenant_id,p.game_id,p.id)=(s.tenant_id,s.game_id,s.play_row_id)
 WHERE p.version=s.play_row_version AND p.source_event_id=s.source_event_id
), raw_frame AS (
 SELECT b.*,b.payload#>>'{{calculation,request,t1,before,stateFields,state.inning}}'
     AS inning_text,
   b.payload#>>'{{calculation,request,t1,before,stateFields,state.half}}' AS half,
   {complete} AS complete_json,
   b.payload#>>'{{calculation,request,t1,before,scoreboard,inningScores,away}}'
     AS before_away,
   b.payload#>>'{{calculation,response,value,t1,after,scoreboard,inningScores,away}}'
     AS after_away,
   b.payload#>>'{{calculation,request,t1,before,scoreboard,inningScores,home}}'
     AS before_home,
   b.payload#>>'{{calculation,response,value,t1,after,scoreboard,inningScores,home}}'
     AS after_home,
   b.payload#>>'{{calculation,request,t1,before,scoreboard,hits}}' AS before_hits,
   b.payload#>>'{{calculation,response,value,t1,after,scoreboard,hits}}' AS after_hits,
   b.payload#>>'{{calculation,request,t1,before,scoreboard,errors}}' AS before_errors,
   b.payload#>>'{{calculation,response,value,t1,after,scoreboard,errors}}'
     AS after_errors,
   b.payload#>>'{{calculation,request,t1,before,scoreboard,strikeouts}}'
     AS before_strikeouts,
   b.payload#>>'{{calculation,response,value,t1,after,scoreboard,strikeouts}}'
     AS after_strikeouts,
   b.payload#>>'{{calculation,request,t1,before,scoreboard,walks}}' AS before_walks,
   b.payload#>>'{{calculation,response,value,t1,after,scoreboard,walks}}' AS after_walks
 FROM bounded b
), checked_frame AS (
 SELECT r.*,
   r.inning_text ~ '^[1-9][0-9]{{0,17}}$' AND r.half IN ('top','bottom')
   AND r.complete_json IN ('true'::jsonb,'false'::jsonb)
   AND r.before_away ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.after_away ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.before_home ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.after_home ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.before_hits ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.after_hits ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.before_errors ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.after_errors ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.before_strikeouts ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.after_strikeouts ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.before_walks ~ '^(0|[1-9][0-9]{{0,17}})$'
   AND r.after_walks ~ '^(0|[1-9][0-9]{{0,17}})$' AS shape_ok
 FROM raw_frame r
), score_delta AS (
 SELECT c.source_event_id,c.d2,c.event_kind,c.pitcher_id,c.fact_version_id,
   CASE WHEN shape_ok THEN inning_text::bigint END AS inning,
   half,CASE WHEN shape_ok THEN complete_json='true'::jsonb END AS completed,
   CASE WHEN shape_ok THEN after_away::bigint-before_away::bigint END AS away_runs,
   CASE WHEN shape_ok THEN after_home::bigint-before_home::bigint END AS home_runs,
   CASE WHEN shape_ok THEN after_hits::bigint-before_hits::bigint END AS hits,
   CASE WHEN shape_ok THEN after_errors::bigint-before_errors::bigint END AS errors,
   CASE WHEN shape_ok THEN after_strikeouts::bigint-before_strikeouts::bigint
   END AS strikeouts,
   CASE WHEN shape_ok THEN after_walks::bigint-before_walks::bigint END AS walks,
   shape_ok
 FROM checked_frame c
), score_health AS (
 SELECT COUNT(*)=COUNT(*) FILTER (WHERE shape_ok AND inning>0 AND inning<=100000
   AND away_runs>=0 AND home_runs>=0 AND hits>=0 AND errors>=0
   AND strikeouts>=0 AND walks>=0
   AND ((half='top' AND home_runs=0) OR (half='bottom' AND away_runs=0))) AS valid
 FROM score_delta
), score_rows AS (
 SELECT half,inning,
   SUM(CASE WHEN half='top' THEN away_runs ELSE home_runs END)::bigint AS runs,
   BOOL_OR(completed) AS completed,
   SUM(hits)::bigint AS hits,SUM(errors)::bigint AS errors,
   SUM(strikeouts)::bigint AS strikeouts,SUM(walks)::bigint AS walks
 FROM score_delta GROUP BY half,inning
), score_totals AS (
 SELECT COALESCE(SUM(hits) FILTER (WHERE half='top'),0)::bigint AS top_hits,
   COALESCE(SUM(errors) FILTER (WHERE half='bottom'),0)::bigint AS top_errors,
   COALESCE(SUM(strikeouts) FILTER (WHERE half='top'),0)::bigint AS top_strikeouts,
   COALESCE(SUM(walks) FILTER (WHERE half='top'),0)::bigint AS top_walks,
   COALESCE(SUM(hits) FILTER (WHERE half='bottom'),0)::bigint AS bottom_hits,
   COALESCE(SUM(errors) FILTER (WHERE half='top'),0)::bigint AS bottom_errors,
   COALESCE(SUM(strikeouts) FILTER (WHERE half='bottom'),0)::bigint
     AS bottom_strikeouts,
   COALESCE(SUM(walks) FILTER (WHERE half='bottom'),0)::bigint AS bottom_walks
 FROM score_rows
), legacy_cells AS (
 SELECT half,LEAST(inning,{slots}) AS slot,SUM(runs)::bigint AS runs,
   BOOL_OR(completed) AS completed
 FROM score_rows GROUP BY half,LEAST(inning,{slots})
), legacy_arrays AS (
 SELECT side.half,
   pg_catalog.jsonb_agg(CASE WHEN c.runs>0 OR c.completed
     THEN pg_catalog.to_jsonb(c.runs)
     ELSE '""'::jsonb END ORDER BY i.n) AS cells
 FROM (VALUES('top'),('bottom')) side(half)
 CROSS JOIN pg_catalog.generate_series(1,{slots}) i(n)
 LEFT JOIN legacy_cells c ON c.half=side.half AND c.slot=i.n
 GROUP BY side.half
), all_innings AS (
 SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
   'inning',i.n,'half',side.half,
   'state',CASE WHEN r.inning IS NULL THEN 'unplayed'
     WHEN r.completed THEN 'completed' ELSE 'in-progress' END,
   'runs',CASE WHEN r.inning IS NULL THEN NULL ELSE r.runs END
 ) ORDER BY i.n,side.ord) AS value
 FROM pg_catalog.generate_series(1,(SELECT MAX(inning)::int FROM score_rows)) i(n)
 CROSS JOIN (VALUES('top',1),('bottom',2)) side(half,ord)
 LEFT JOIN score_rows r ON r.inning=i.n AND r.half=side.half
), source_metric AS (
 SELECT b.source_event_id,b.event_kind,b.pitcher_id,b.tenant_id,b.game_id,
   b.fact_version_id,
   ({bounded_kind_match}) AS kind_bound,
   b.computed_metric_keys @> ARRAY['{metric}']::text[] AS computed,
   b.evaluation_sha256=pg_catalog.encode(pg_catalog.sha256(
     pg_catalog.convert_to(b.metric_states::text,'UTF8')),'hex') AS bound,
   b.metric_states#>>'{{{state_path},state}}' AS state,
   b.metric_states#>>'{{{state_path},value}}' AS metric_value,
   b.metric_states#>'{{{state_path},credits}}' AS saved_credits
 FROM bounded b
), pitch_source_health AS (
 SELECT m.source_event_id,m.event_kind,m.pitcher_id,m.kind_bound,
   m.computed,m.bound,
   m.state,m.metric_value,m.saved_credits,
   COUNT(f.source_event_id) AS credits,
   BOOL_AND(f.state='available' AND f.amount=1
     AND f.player_id=m.pitcher_id AND f.credit_ordinal=0) AS valid_fact
 FROM source_metric m LEFT JOIN sync_fence.stats_primitive_facts f
   ON (f.tenant_id,f.game_id,f.fact_version_id,f.source_event_id)
    =(m.tenant_id,m.game_id,m.fact_version_id,m.source_event_id)
   AND f.metric_id='{metric}'
 GROUP BY m.source_event_id,m.event_kind,m.pitcher_id,m.kind_bound,
   m.computed,m.bound,
   m.state,m.metric_value,m.saved_credits
), pitcher_total AS (
 SELECT COALESCE(SUM(f.amount),0)::bigint AS value,
   BOOL_AND(COALESCE(h.kind_bound AND h.computed AND h.bound
     AND h.state='available'
     AND h.event_kind IN ({row_kinds})
     AND CASE WHEN h.metric_value='0' THEN
       h.saved_credits='[]'::jsonb AND h.credits=0
     WHEN h.metric_value='1' THEN
       h.saved_credits=pg_catalog.jsonb_build_array(
         pg_catalog.jsonb_build_object('player_id',h.pitcher_id::text,
           'quantity','1'))
       AND h.credits=1 AND h.valid_fact
     ELSE false END,false)) AS valid
 FROM pitch_source_health h CROSS JOIN target t
 LEFT JOIN sync_fence.stats_primitive_facts f
   ON f.source_event_id=h.source_event_id AND f.fact_version_id=:fact_version_id
   AND f.tenant_id=:tenant_id AND f.game_id=:game_id
   AND f.metric_id='{metric}' AND f.player_id=t.pitcher_id
)
SELECT p.value AS pitcher_pitch_count,
  a.cells || pg_catalog.jsonb_build_array(
    z.top_hits,z.top_errors,z.top_strikeouts,z.top_walks)
    AS top_score,
  b.cells || pg_catalog.jsonb_build_array(
    z.bottom_hits,z.bottom_errors,z.bottom_strikeouts,z.bottom_walks)
    AS bottom_score,
  f.value AS full_innings
FROM target t CROSS JOIN member_health h CROSS JOIN score_health sh
CROSS JOIN pitcher_total p CROSS JOIN score_totals z CROSS JOIN all_innings f
JOIN legacy_arrays a ON a.half='top'
JOIN legacy_arrays b ON b.half='bottom'
WHERE h.actual_count=h.source_count AND sh.valid AND p.valid
  AND p.value>=0 AND f.value IS NOT NULL;
"""


def generate_play_export_score_bundle(root: Path = _ROOT) -> tuple[str, dict]:
    """既採用T5/Sを検証し、独立D-1宣言のSQLを一対象へ生成する。"""
    try:
        model_bytes = (root / _MODEL).read_bytes()
        schema_bytes = (root / _SCHEMA).read_bytes()
        model = json.loads(model_bytes)
        Draft202012Validator(json.loads(schema_bytes)).validate(model)
        _, sections, _, _ = _verified_inputs(root)
        target = _score_query(model, sections)
        source = (root / _CANONICAL).read_bytes()
        completion = _completion_python(model["scoreboard"]["completeProfiles"])
        manifest = {
            "schemaVersion": 1,
            "status": "candidate-formal-acceptance-pending",
            "modelSha256": _canonical_hash(model),
            "inputs": {
                path: hashlib.sha256(value).hexdigest()
                for path, value in (
                    (_MODEL, model_bytes),
                    (_SCHEMA, schema_bytes),
                    (_CANONICAL, source),
                    (
                        "backend/src/pitchlog/domaingen/play_export_score.py",
                        (
                            root / "backend/src/pitchlog/domaingen/play_export_score.py"
                        ).read_bytes(),
                    ),
                )
            },
            "generatedFiles": {
                _TARGET: hashlib.sha256(target.encode()).hexdigest(),
                _COMPLETION_TARGET: hashlib.sha256(completion.encode()).hexdigest(),
            },
            "t5ModelUnchanged": True,
        }
        return target, manifest
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise PlayExportScoreDeclarationError("スコアD-1生成入力が不正") from error


def main() -> None:
    """生成SQLと候補manifestを一括生成又は全byte検査する。"""
    parser = argparse.ArgumentParser(description="毎球CSVのD-1スコアSQL生成")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    target, manifest = generate_play_export_score_bundle()
    expected = {
        _TARGET: target,
        _COMPLETION_TARGET: _completion_python(
            json.loads((_ROOT / _MODEL).read_text())["scoreboard"]["completeProfiles"]
        ),
        _MANIFEST: json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    }
    for path, content in expected.items():
        output = _ROOT / path
        if args.write:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content)
        elif not output.is_file() or output.read_text() != content:
            raise PlayExportScoreDeclarationError("スコアD-1生成targetが不一致")


if __name__ == "__main__":
    main()
