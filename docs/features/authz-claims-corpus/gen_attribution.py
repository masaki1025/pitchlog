"""帰属表(attribution.json)の生成と「帰属なし 0」の機械検査(TSK-312 — 計画 §4-(4))。

基準 = 分岐点コミット 41884a9 との git diff のうち成果物
(contracts/authz/**・scripts/check_authz_catalog.py・tests/**・要件書・docs/README.md)。
JSON 資産はエントリ単位・コード/文書は hunk(変更識別子)単位で抽出し、
各変更を「裁定項目(F1〜F16)」「既知 3 件」「機械的追随」のいずれかへ帰属させる。
帰属できない変更が 1 件でもあれば exit 1。

実行: リポジトリルートで `python docs/features/authz-claims-corpus/gen_attribution.py`
出力: docs/features/authz-claims-corpus/attribution.json
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "41884a9"
OUT = Path(__file__).resolve().parent / "attribution.json"

# 裁定リスト由来の source_id → 帰属(step1-rulings.json の採用項目)
SPLIT_ATTR = {
    "FR-012/list_item-013": ["F1"],
    "FR-034/heading-002/list_item-005": ["F2"],
    "FR-034/heading-002/list_item-006": ["F2"],
    "FR-041/list_item-006": ["F3"],
    "FR-041/list_item-007": ["F3"],
    "FR-035/list_item-005": ["F4"],
    "FR-035/list_item-010": ["F4"],
    "NFR-011/list_item-002": ["F4"],
    "FR-041/list_item-014": ["F15"],
}
CLOSED_WORLD_ATTR = ["F6"]

# 検査器の変更識別子(diff の @@ 文脈・追加行から抽出)→ 帰属
CHECKER_PATTERNS = [
    (r"_table_cells|table_line", ["F16"]),
    (r"AUTH 分類規則は適用条件|_parse_classification_rules", ["F5"]),
    (r"(?i)closed_world", ["F6"]),
    (r"_validate_claim\b", ["mechanical:schema-follow"]),
    (r"_claim_ids_by_location", ["F7", "F9"]),
    (r"_has_db_decision", ["F10"]),
    (r"validate_ddl", ["F14", "F12"]),
    (r"claim_dispositions|_validate_claim_dispositions|reason_code", ["F7", "F9"]),
    (r"legacy route|legacy_route", ["F8"]),
    (r"predicates|acl_expectation|schema_usage|_validate_ddl|policy", ["F14", "F12"]),
    (r"atomic", ["F1", "F2", "F3", "F4", "F15"]),
    (r"execution_support|probe_executable|contract_only", ["F10"]),
    (r"decision_projection|compute_decision_digest|decision_lock", ["mechanical:digest"]),
    (r"(?i)REQUIRED_TABLE_PRIVILEGE|table_privilege|target_pairs", ["F13"]),
    (r"attack_goal|cut_set|singleton|two_factor", ["F13"]),
    (r"owner_dependency|schema_usage|USAGE", ["F12"]),
    (r"oracle_commit|oracle_context|seal", ["mechanical:reseal"]),
]

TEST_ATTR = ["mechanical:step-tests"]  # 負例・期待件数・走査一般化(各ステップの従属)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def _entries(path: str, rev: str | None) -> dict:
    """JSON 資産を { 名前空間つきキー: 正規化 JSON 文字列 } へ展開する。

    Args:
        path: リポジトリ相対パス。
        rev: 参照リビジョン(None = 作業ツリー)。

    Returns:
        エントリ辞書。
    """
    if rev is None:
        text = (ROOT / path).read_text(encoding="utf-8")
    else:
        r = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{rev}:{path}"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return {}
        text = r.stdout
    data = json.loads(text)
    name = Path(path).name
    id_fields = {
        "claims": "source_id" if "requirement" in name else "claim_id",
        "decisions": "source_id", "routes": None,
        "management_operations": "operation_id", "entries": None,
        "claim_dispositions": None, "cells": "cell_id",
        "route_scopes": "route_scope_id", "design_provenance": "provenance_id",
        "mutants": "mutant_id", "attack_goals": "attack_goal_id",
        "minimal_cut_sets": "cut_set_id", "two_factor_interactions": "interaction_id",
        "provenance": "provenance_id", "roles": "role_id", "schemas": "schema_id",
        "tables": "table_id", "policies": "policy_id", "functions": "function_id",
        "acl_expectations": "acl_id", "transaction_boundaries": "boundary_id",
        "column_acl_expectations": "expectation_id", "boundaries": "boundary_id",
        "pending_human_reviews": "review_id", "rejections": "rejection_id",
        "residual_risks": "risk_id", "predicates": "predicate_id",
        "input_assets": "path", "sealed_assets": "path",
    }
    out: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, list) and value and all(isinstance(e, dict) for e in value):
            for e in value:
                if key == "claim_dispositions":
                    eid = f"{e['source_id']}@{e['location']}"
                elif key == "routes":
                    eid = e.get("route_id") or e.get("matrix_route_id")
                elif key == "entries":
                    eid = e.get("entry_id") or e.get("catalog_entry_id")
                else:
                    f = id_fields.get(key)
                    eid = e.get(f) if f else json.dumps(e, ensure_ascii=False)[:60]
                out[f"{name}:{key}:{eid}"] = json.dumps(e, sort_keys=True, ensure_ascii=False)
        else:
            out[f"{name}:{key}"] = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return out


def attribute_asset_change(unit: str, new_val: str | None) -> list[str]:
    """資産エントリの変更 1 件を帰属させる。

    Args:
        unit: 名前空間つきエントリキー。
        new_val: 変更後の値(削除なら None)。

    Returns:
        帰属先 ID のリスト(空 = 帰属不能)。
    """
    attrs: list[str] = []
    m = re.match(r"(?P<asset>[^:]+):(?P<key>[^:]+)(?::(?P<eid>.*))?$", unit)
    asset, key, eid = m["asset"], m["key"], m["eid"] or ""

    if asset in ("requirement-claims.json", "requirement-claims.lock.json"):
        if eid.startswith("CHANGELOG/"):
            attrs.append("known:changelog-row")
        if eid.startswith("NFR-018/paragraph") or eid.startswith("NFR-018/table"):
            attrs.append("known:indent-extraction")
            if "table_row" in eid:
                attrs.append("known:exception-cells")
        base_id = eid.split("#")[0]
        if base_id in SPLIT_ATTR:
            attrs += SPLIT_ATTR[base_id]
        if new_val and "closed_world" in new_val:
            attrs += CLOSED_WORLD_ATTR
        if key == "classification_rules":
            attrs.append("F5")
        if key in ("input_manifest", "aggregate_decision_digest",
                   "classification_rules_digest", "decision_count",
                   "item_counts_by_kind", "basis_rules_digest", "layer_ids_digest"):
            attrs.append("mechanical:reseal")
        if asset.endswith("lock.json") and key == "decisions" and not attrs:
            attrs.append("mechanical:reseal")
    elif asset.startswith("route-registry"):
        if key == "claim_dispositions":
            attrs += ["F7", "F9"]
        if key == "routes":
            attrs.append("F8")
        if key == "management_operations":
            attrs.append("F3")
        if key in ("input_manifest",) or asset.endswith("lock.json"):
            attrs.append("mechanical:reseal")
        if key == "enums" and new_val and "requirement" in (new_val or ""):
            attrs.append("F8")
    elif asset.startswith("auth-catalog"):
        base_id = eid.replace("CATALOG:", "").split("#")[0]
        if base_id in SPLIT_ATTR:
            attrs += SPLIT_ATTR[base_id]
        if key in ("input_manifest", "entry_count", "aggregate_decision_digest",
                   "asset_digest") or asset.endswith("lock.json"):
            attrs.append("mechanical:reseal")
        if not attrs:
            attrs.append("mechanical:atomic-follow")
    elif asset.startswith("http-route-matrix"):
        attrs.append("mechanical:reseal")
    elif asset == "oracle-seal.lock.json":
        attrs.append("mechanical:reseal")
    elif asset in ("ddl-elements.json", "rejected-configs.json",
                   "verification-evidence.json", "boundary-proposal.json",
                   "claim-mutant-map.json", "attack-tree.json"):
        # oracle 資産(ステップ 11): 裁定・従属・機械追随へ帰属
        if "APP-ROLE" in eid or "app_role" in eid or "app_role" in (new_val or ""):
            attrs.append("F13")
        if asset == "ddl-elements.json" and (
            key in ("predicates", "policies", "functions", "acl_expectations",
                    "schemas", "column_acl_expectations", "enums",
                    "table_privilege_probe_matrix", "representative_management_probe")
        ):
            attrs += ["F12", "F14"]
        if asset == "claim-mutant-map.json":
            base_id = eid.split("#")[0]
            if base_id in SPLIT_ATTR:
                attrs += SPLIT_ATTR[base_id]
            if key in ("claims", "mutants", "two_factor_interactions"):
                attrs.append("mechanical:atomic-follow")
            if key in ("classification_rules", "execution_classes", "kill_contract",
                       "positive_cases", "table_privilege_mutation_rule",
                       "mutant_axes", "mcdc_decision_forms"):
                attrs += ["F10", "F13"]
        if asset == "attack-tree.json" and key in (
            "attack_goals", "minimal_cut_sets", "two_factor_interactions",
            "two_factor_scope",
        ):
            attrs.append("F13")
        if asset == "boundary-proposal.json":
            attrs.append("mechanical:atomic-follow")
        if key in ("oracle_context", "provenance", "supabase_verification",
                   "required_initial_rejection_ids"):
            attrs.append("mechanical:reseal")
        if not attrs:
            attrs.append("mechanical:atomic-follow")
    return attrs


def main() -> None:
    """帰属表を生成し「帰属なし 0」を検査する。"""
    records: list[dict] = []
    unattributed: list[str] = []

    changed = _git("diff", "--name-only", BASE, "--",
                   "contracts/authz", "scripts/check_authz_catalog.py",
                   "tests", "docs/requirements", "docs/README.md").split()

    for path in changed:
        name = Path(path).name
        if path.startswith("contracts/authz/"):
            old = _entries(path, BASE)
            new = _entries(path, None)
            for unit in sorted(set(old) | set(new)):
                if old.get(unit) == new.get(unit):
                    continue
                kind = ("added" if unit not in old
                        else "removed" if unit not in new else "modified")
                attrs = attribute_asset_change(unit, new.get(unit))
                records.append({"unit": unit, "change": kind, "attribution": attrs})
                if not attrs:
                    unattributed.append(unit)
        elif path == "scripts/check_authz_catalog.py":
            diff = _git("diff", BASE, "--", path)
            hunks = re.split(r"\n@@", diff)
            for h in hunks[1:]:
                attrs = sorted({a for pat, ids in CHECKER_PATTERNS
                                if re.search(pat, h) for a in ids})
                head = h.splitlines()[0][:80]
                records.append({"unit": f"{name}:@@{head}", "change": "hunk",
                                "attribution": attrs})
                if not attrs:
                    unattributed.append(f"{name}:@@{head}")
        elif path.startswith("tests/"):
            records.append({"unit": path, "change": "file", "attribution": TEST_ATTR})
        elif path.startswith("docs/requirements/"):
            records.append({"unit": f"{name}:NFR-018 例外表 2 セル", "change": "hunk",
                            "attribution": ["known:exception-cells"]})
            records.append({"unit": f"{name}:変更履歴 1 行", "change": "hunk",
                            "attribution": ["known:changelog-row"]})
        elif path == "docs/README.md":
            records.append({"unit": path, "change": "file",
                            "attribution": ["known:exception-cells"]})

    result = {
        "meta": {"base": BASE, "date": "2026-09-03",
                 "rulings": "step1-rulings.json",
                 "known": ["indent-extraction(採取欠陥)", "exception-cells(例外表 2 セル)",
                            "changelog-row(変更履歴行)"]},
        "records": records,
        "summary": {"total_units": len(records), "unattributed": len(unattributed)},
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"units={len(records)} unattributed={len(unattributed)}")
    if unattributed:
        for u in unattributed[:20]:
            print(" 帰属なし:", u)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
