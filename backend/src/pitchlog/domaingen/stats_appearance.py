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
    matches = " AND ".join(f"m.{name}=s.{name}" for name in binding)
    proof_kinds = ",".join("'" + value + "'" for value in model["source"]["proofKinds"])
    member_count = model["source"]["memberCountColumn"]
    expected_game_count = model["source"]["expectedGameCountBind"]
    invalid_scope = " OR ".join(f"s.{name} IS NULL" for name in binding)
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
        "generatedFiles": {_TARGET: hashlib.sha256(query.encode()).hexdigest()},
        "providerInstalled": False,
    }
    return {_TARGET: query}, manifest


def write_appearance_bundle(root: Path = _ROOT) -> None:
    """正式受理とは別に候補生成物だけを保存する。"""
    bundle, manifest = generate_appearance_bundle(root)
    for name, text in bundle.items():
        (root / name).write_text(text)
    (root / _MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
