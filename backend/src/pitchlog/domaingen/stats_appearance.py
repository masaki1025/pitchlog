"""版付き実投手出場集合だけを数えるD03候補SQLを生成する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[4]
_MODEL = "backend/domain/stats-appearance.model.json"
_SCHEMA = "backend/domain/stats-appearance.schema.json"
_TARGET = "backend/src/pitchlog/stats/generated/appearances.sql"
_MANIFEST = "backend/domain/stats-appearance.manifest.json"


class AppearanceDeclarationError(ValueError):
    """未知の出場定義や入力元へ生成器を拡張しない。"""


def generate_appearance_bundle(
    root: Path = _ROOT,
) -> tuple[dict[str, str], dict[str, Any]]:
    """期待値を入力にせず、閉じたD03宣言から唯一SQLと候補manifestを作る。"""
    model_path, schema_path = root / _MODEL, root / _SCHEMA
    try:
        model = json.loads(model_path.read_text())
        schema = json.loads(schema_path.read_text())
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(model))
    except (OSError, ValueError) as error:
        raise AppearanceDeclarationError("登板の生成宣言を読めません") from error
    if errors:
        raise AppearanceDeclarationError("登板の閉宣言が不一致です")
    # CTEの供給は真正providerの責務。このtargetは自由なSQL/Sessionを受け取らない。
    # scopeの欠測を投球数・開始名簿・現在名簿から補完しない。
    binding = model["source"]["binding"]
    nullable = model["source"]["nullableBinding"]
    matches = " AND ".join(
        f"m.{name} IS NOT DISTINCT FROM s.{name}"
        if name in nullable
        else f"m.{name}=s.{name}"
        for name in binding
    )
    proof_kinds = ",".join("'" + value + "'" for value in model["source"]["proofKinds"])
    member_count = model["source"]["memberCountColumn"]
    expected_game_count = model["source"]["expectedGameCountBind"]
    invalid_scope = " OR ".join(
        f"s.{name} IS NULL" for name in binding if name not in nullable
    )
    query = f"""-- 生成元: {_MODEL}。真正scope/member CTEの供給前は製品提供不可。
SELECT 'appearances' AS metric_id,
 CASE WHEN invalid_supply THEN 'source_unavailable' ELSE 'available' END AS state,
 CASE WHEN invalid_supply THEN NULL ELSE (
   SELECT COUNT(DISTINCT m.game_id) FROM appearance_members m
   JOIN appearance_scope s ON {matches}
   WHERE m.tenant_id=:tenant_id AND m.player_id=:player_id
 ) END AS value
FROM (SELECT
 :{expected_game_count} IS NULL OR :{expected_game_count}<0
 OR (SELECT COUNT(*) FROM appearance_scope s WHERE s.tenant_id=:tenant_id)
    <>:{expected_game_count}
 OR EXISTS(SELECT 1 FROM appearance_scope s WHERE s.tenant_id=:tenant_id
   AND (s.supply_complete IS NOT TRUE OR {invalid_scope}
     OR s.revision<=0 OR s.{member_count} IS NULL OR s.{member_count}<0
     OR s.{member_count}<>(SELECT COUNT(*) FROM appearance_members m WHERE {matches})))
 OR EXISTS(SELECT 1 FROM appearance_scope s WHERE s.tenant_id=:tenant_id
   GROUP BY s.tenant_id,s.game_id HAVING COUNT(*)<>1)
 OR EXISTS(SELECT 1 FROM appearance_members m WHERE m.tenant_id=:tenant_id
   AND (m.proof_kind NOT IN ({proof_kinds}) OR m.proof_kind IS NULL
     OR m.player_id IS NULL OR m.proof_source_id IS NULL
     OR NOT EXISTS(SELECT 1 FROM appearance_scope s WHERE {matches})))
 AS invalid_supply) supply
"""
    canonical = json.dumps(
        model, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    projection = _entry_projection(model)
    projection_path = (
        "backend/src/pitchlog/stats/generated/pitcher_entry_projection.sql"
    )
    manifest = {
        "schemaVersion": 1,
        "status": "candidate-source-provider-pending",
        "modelSha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "inputs": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                _MODEL,
                _SCHEMA,
                "backend/src/pitchlog/domaingen/stats_appearance.py",
            )
        },
        "generatedFiles": {
            _TARGET: hashlib.sha256(query.encode()).hexdigest(),
            projection_path: hashlib.sha256(projection.encode()).hexdigest(),
        },
        "providerInstalled": False,
    }
    return {_TARGET: query, projection_path: projection}, manifest


def _entry_projection(model: dict[str, Any]) -> str:
    """既開始/唯一kernel/交代contextの値を一度だけentryへ写す。"""
    declaration = model["entryProjection"]
    outcomes = ",".join("'" + x + "'" for x in declaration["continueOutcomes"])
    known = ",".join("'" + x + "'" for x in declaration["knownOutcomes"])
    x_marks = ",".join("'" + x + "'" for x in declaration["knownXMarks"])
    kinds = ",".join("'" + x + "'" for x in declaration["sourceKinds"])
    half_reason = declaration["halfReason"]
    sub_reason = declaration["substitutionReason"]
    return f"""-- 生成元: {_MODEL}。真正TX原本のappearance_transitionだけを供給する。
WITH observed AS (
 SELECT e.*,
  CASE e.after_half WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' END AS defender,
  CASE e.after_half WHEN 'top' THEN e.after_home_pitcher_id
       WHEN 'bottom' THEN e.after_away_pitcher_id END AS pitcher,
  CASE e.after_half WHEN 'top' THEN e.before_home_pitcher_id
       WHEN 'bottom' THEN e.before_away_pitcher_id END AS previous_pitcher,
  CASE
   WHEN e.origin_kind='start' THEN 1
   WHEN e.origin_kind='play' AND e.half_completed IS TRUE
        AND e.end_condition_detected IS FALSE AND e.lock_further_play IS FALSE
        AND e.outcome IN ({outcomes}) THEN 1
   WHEN e.origin_kind='substitution' AND e.changed_side=
        CASE e.after_half WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' END
        AND (CASE e.after_half WHEN 'top' THEN e.after_home_pitcher_id
              WHEN 'bottom' THEN e.after_away_pitcher_id END) IS DISTINCT FROM
            (CASE e.after_half WHEN 'top' THEN e.before_home_pitcher_id
              WHEN 'bottom' THEN e.before_away_pitcher_id END) THEN 1
   WHEN e.origin_kind='reopen' AND e.half_completed IS TRUE
        AND e.released_end_condition IS TRUE AND e.half_started_before IS FALSE
        THEN 1
   ELSE 0 END AS emits_entry
 FROM {declaration["sourceRelation"]} e
), checked AS (
 SELECT o.*, CASE WHEN o.origin_kind IS NULL OR o.origin_kind NOT IN ({kinds})
  OR o.tenant_id IS NULL OR o.game_id IS NULL OR o.source_id IS NULL
  OR o.internal_generation IS NULL OR o.internal_generation<=0
  OR o.artifact_sha256 IS NULL OR o.source_fingerprint IS NULL
  OR o.after_half IS NULL OR o.after_half NOT IN ('top','bottom')
  OR o.after_inning IS NULL OR o.after_inning<=0
  OR (o.origin_kind='start' AND (o.d1 IS NOT NULL OR o.after_inning<>1
       OR o.after_half<>'top'))
  OR (o.origin_kind<>'start' AND (o.d1 IS NULL OR o.d1<=0
       OR o.before_half IS NULL OR o.before_half NOT IN ('top','bottom')
       OR o.before_inning IS NULL OR o.before_inning<=0))
  OR (o.origin_kind='play' AND (o.half_completed IS NULL
       OR o.end_condition_detected IS NULL OR o.lock_further_play IS NULL
       OR o.outcome IS NULL OR o.x_mark IS NULL
       OR o.outcome NOT IN ({known}) OR o.x_mark NOT IN ({x_marks})
       OR o.end_condition_detected IS DISTINCT FROM o.lock_further_play
       OR (o.half_completed IS TRUE AND o.before_half=o.after_half)
       OR (o.half_completed IS FALSE AND (o.before_half<>o.after_half
           OR o.before_inning<>o.after_inning))
       OR (o.end_condition_detected IS FALSE AND o.lock_further_play IS FALSE
           AND (o.outcome NOT IN ({outcomes}) OR o.x_mark<>'recorded-score'))
       OR (o.end_condition_detected IS TRUE AND o.outcome IN ({outcomes}))))
  OR (o.origin_kind='substitution' AND (o.changed_side IS NULL
       OR o.changed_side NOT IN ('home','away') OR o.before_half<>o.after_half
       OR o.before_inning<>o.after_inning))
  OR (o.origin_kind='reopen' AND (o.half_completed IS NULL
       OR o.released_end_condition IS NULL OR o.half_started_before IS NULL))
  OR (o.emits_entry=1 AND o.pitcher IS NULL)
 THEN 'source_unavailable' ELSE 'evaluated' END AS state
 FROM observed o
)
SELECT state,tenant_id,game_id,origin_kind,source_id,internal_generation,d1,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN pitcher END AS player_id,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN defender END AS defending_side,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN after_inning END AS inning,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN after_half END AS half,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN
  CASE WHEN origin_kind='substitution' THEN '{sub_reason}' ELSE '{half_reason}' END
 END AS proof_kind,artifact_sha256,source_fingerprint
FROM checked
"""


def write_appearance_bundle(root: Path = _ROOT) -> None:
    """正式受理とは別に候補生成物だけを保存する。"""
    bundle, manifest = generate_appearance_bundle(root)
    for name, text in bundle.items():
        (root / name).write_text(text)
    (root / _MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
