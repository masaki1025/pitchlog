"""Publicの不変性母集団と私有9表の分担を過不足なく固定する。"""

import copy
import json
from pathlib import Path

from db.test_immutability_enforcement import (
    _NON_PUBLIC_MANIFEST_TABLES,
    _load_manifest,
    _manifest_population,
)


def test_private_scope_matches_only_formal_sync_fence_tables():
    """有限9名と正式schemaを照合し、public50表は減らさない。"""
    root = Path(__file__).resolve().parents[2]
    asset = json.loads((root / "contracts/authz/product/ddl-elements.json").read_text())
    private = {
        row["table_id"]
        for row in asset["tables"]
        if row.get("schema_name") == "sync_fence"
    }
    assert private == _NON_PUBLIC_MANIFEST_TABLES
    assert len(private) == 9
    manifest = _load_manifest()
    public = {t["name"] for t in manifest["tables"]} - private
    assert len(public) == 50
    assert {t.name for t in _manifest_population(manifest)} == public


def test_unknown_stats_table_is_not_excluded_by_name_prefix():
    """新しいstats風の表を包括除外せず、public検査へ残す。"""
    manifest = copy.deepcopy(_load_manifest())
    row = copy.deepcopy(
        next(t for t in manifest["tables"] if t["name"] == "stats_primitive_facts")
    )
    row["name"] = "stats_unknown"
    manifest["tables"].append(row)
    assert "stats_unknown" in {t.name for t in _manifest_population(manifest)}
