"""レビュー母集団の機械列挙(TSK-312 ステップ 1 — 計画 §4-(3))。

全対象(contracts/authz の 15 資産 + 検査器 + 要件書 heading)の名前空間付き ID 集合を
決定的に列挙する。レビュアー側の走査リストとの exact-set 突合(差集合 0)に使う。

列挙規則:
- 資産の各トップレベルキーについて、値が「dict の list」で下表に ID フィールドの指定が
  ある場合は 1 要素 = 1 行 `<資産名>:<キー>:<ID値>`(複合キーは `/` 連結)。
- それ以外のトップレベルキー(スカラー・dict・スカラー list・指定外の list)は
  1 行 `<資産名>:<キー>`。
- 検査器 = `check_authz_catalog.py:def:<関数名>` / `:class:<クラス名>` /
  `:const:<大文字定数名>`(モジュールトップレベルのみ — 計画レビュー 5 周目 P0-1)。
- 要件書 = `requirements-pitchlog-2026-07-22.md:heading:<heading_id>`
  (正 = requirement-claims.json の input_manifest.heading_ids・125 件)。

実行: リポジトリルートで `python docs/features/authz-claims-corpus/enumerate_universe.py`
出力: 標準出力(1 行 1 ID・ソート済み)。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AUTHZ = ROOT / "contracts" / "authz"
CHECKER = ROOT / "scripts" / "check_authz_catalog.py"

# 資産ごとの「dict の list」の ID フィールド(複合キーはタプル)
ID_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "attack-tree.json": {
        "attack_goals": ("attack_goal_id",),
        "minimal_cut_sets": ("cut_set_id",),
        "two_factor_interactions": ("interaction_id",),
        "provenance": ("provenance_id",),
    },
    "auth-catalog.json": {
        "route_scopes": ("route_scope_id",),
        "entries": ("catalog_entry_id",),
    },
    "auth-catalog.lock.json": {"entries": ("entry_id",)},
    "boundary-proposal.json": {
        "boundaries": ("boundary_id",),
        "pending_human_reviews": ("review_id",),
        "provenance": ("provenance_id",),
    },
    "claim-mutant-map.json": {
        "claims": ("claim_id",),
        "mutants": ("mutant_id",),
        "two_factor_interactions": ("interaction_id",),
        "provenance": ("provenance_id",),
    },
    "ddl-elements.json": {
        "roles": ("role_id",),
        "schemas": ("schema_id",),
        "tables": ("table_id",),
        "policies": ("policy_id",),
        "functions": ("function_id",),
        "acl_expectations": ("acl_id",),
        "transaction_boundaries": ("boundary_id",),
        "provenance": ("provenance_id",),
        "column_acl_expectations": ("expectation_id",),
        "table_privilege_probe_matrix": (
            "privilege_id",
            "calling_role_id",
            "target_table_id",
        ),
    },
    "http-route-matrix.json": {
        "routes": ("matrix_route_id",),
        "cells": ("cell_id",),
    },
    "http-route-matrix.lock.json": {"entries": ("entry_id",)},
    "oracle-seal.lock.json": {
        "input_assets": ("path",),
        "sealed_assets": ("path",),
    },
    "rejected-configs.json": {
        "rejections": ("rejection_id",),
        "provenance": ("provenance_id",),
    },
    "requirement-claims.json": {"claims": ("source_id",)},
    "requirement-claims.lock.json": {"decisions": ("source_id",)},
    "route-registry.json": {
        "design_provenance": ("provenance_id",),
        "routes": ("route_id",),
        "management_operations": ("operation_id",),
    },
    "route-registry.lock.json": {"entries": ("entry_id",)},
    "verification-evidence.json": {
        "residual_risks": ("risk_id",),
        "provenance": ("provenance_id",),
    },
}


def enumerate_assets() -> list[str]:
    """15 資産の名前空間付き ID を列挙する。

    Returns:
        名前空間付き ID のリスト。
    """
    ids: list[str] = []
    asset_paths = sorted(AUTHZ.glob("*.json"))
    if len(asset_paths) != 15:
        raise SystemExit(f"資産数が 15 でない: {len(asset_paths)}")
    for path in asset_paths:
        name = path.name
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = ID_FIELDS.get(name, {})
        for key, value in data.items():
            spec = fields.get(key)
            if (
                spec
                and isinstance(value, list)
                and value
                and all(isinstance(e, dict) for e in value)
            ):
                for entry in value:
                    composite = "/".join(str(entry[f]) for f in spec)
                    ids.append(f"{name}:{key}:{composite}")
            else:
                ids.append(f"{name}:{key}")
    return ids


def enumerate_checker() -> list[str]:
    """検査器のトップレベル関数・クラス・大文字定数を列挙する。

    Returns:
        名前空間付き ID のリスト。
    """
    tree = ast.parse(CHECKER.read_text(encoding="utf-8"))
    ids: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ids.append(f"check_authz_catalog.py:def:{node.name}")
        elif isinstance(node, ast.ClassDef):
            ids.append(f"check_authz_catalog.py:class:{node.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    ids.append(f"check_authz_catalog.py:const:{t.id}")
    return ids


def enumerate_headings() -> list[str]:
    """要件書の heading_id(母集合 input_manifest が正・125 件)を列挙する。

    Returns:
        名前空間付き ID のリスト。
    """
    claims = json.loads(
        (AUTHZ / "requirement-claims.json").read_text(encoding="utf-8")
    )
    headings = claims["input_manifest"]["heading_ids"]
    return [
        f"requirements-pitchlog-2026-07-22.md:heading:{h}" for h in headings
    ]


def main() -> None:
    """全対象を列挙してソート済みで出力する。"""
    ids = enumerate_assets() + enumerate_checker() + enumerate_headings()
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise SystemExit(f"ID 重複: {dupes[:10]}")
    for line in sorted(ids):
        print(line)


if __name__ == "__main__":
    main()
