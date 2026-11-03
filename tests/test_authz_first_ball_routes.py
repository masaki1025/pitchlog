"""初球作成・球種HTTPの有限対応と認証束縛を正式検査器で固定する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = "backend/src/pitchlog/api/routers/pitch_type_options.py"


def _load_checker() -> Any:
    """製品の検査器を実ファイルから読み、テスト内のコピー実装を置かない。"""
    spec = importlib.util.spec_from_file_location(
        "pitchlog_first_ball_authz_checker", ROOT / "scripts/check_authz_catalog.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _registry() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """共有候補の実registryを毎回複製し、元資産を変更しない。"""
    asset = json.loads((ROOT / "contracts/authz/route-registry.json").read_text())
    return {row["route_id"]: row for row in asset["routes"]}, asset["design_provenance"]


def test_first_ball_create_and_pitch_options_routes_match_source() -> None:
    """実HTTP3件と実CAPの全原文を閉じた2論理routeへ対応させる。"""
    routes, provenance = _registry()
    expected = checker._first_ball_options_http_provenance(ROOT)
    actual = {row["provenance_id"]: row for row in provenance}
    assert expected
    for key, value in expected.items():
        assert actual[key] == value
    checker._validate_first_ball_options_http_routes(routes, provenance, ROOT)


def test_registered_record_route_set_is_exactly_twelve() -> None:
    """既10件と作成/語彙read2件をexact-setとして検査する。"""
    routes, _ = _registry()
    actual = {key for key, row in routes.items() if row["route_kind"] == "record_and_aggregate"}
    assert len(actual) == 12
    assert {"ROUTE:RECORD:games:insert", "ROUTE:RECORD:tenant_vocabularies:read"} <= actual
    checker._validate_record_and_aggregate_route_ids(routes)


def test_unknown_thirteenth_record_route_is_rejected() -> None:
    """正例の追加で未知routeの拒否条件を緩めない。"""
    routes, _ = _registry()
    routes["ROUTE:RECORD:unreviewed:read"] = {"route_kind": "record_and_aggregate"}
    with pytest.raises(checker.CatalogError):
        checker._validate_record_and_aggregate_route_ids(routes)


@pytest.mark.parametrize(
    "mutation",
    ["missing-route", "source-drift", "unknown-cap", "wrong-route", "missing-operation"],
)
def test_first_ball_route_provenance_mutations_are_rejected(mutation: str) -> None:
    """未登録CAP/原文差/別route付替えを実registryの変異で拒否する。"""
    routes, provenance = copy.deepcopy(_registry())
    if mutation == "missing-route":
        del routes["ROUTE:RECORD:games:insert"]
    elif mutation == "source-drift":
        row = next(r for r in provenance if r["provenance_id"] == "HTTP:pitch_type_options")
        row["extracted_text"] = "source mismatch"
    elif mutation == "unknown-cap":
        provenance.append(
            {
                "provenance_id": "FIRST-BALL-OPTION-TOKEN:UnreviewedToken",
                "path": "unknown",
                "extracted_text": "CAP:unapproved",
            }
        )
    elif mutation == "wrong-route":
        routes["ROUTE:RECORD:players:read"]["provenance_ids"].append("HTTP:pitch_type_options")
    else:
        routes["ROUTE:RECORD:tenant_vocabularies:read"]["provenance_ids"].remove(
            "HTTP:pitch_type_options"
        )
    with pytest.raises(checker.CatalogError):
        checker._validate_first_ball_options_http_routes(routes, provenance, ROOT)


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        ("backend/src/pitchlog/api/tenant_access.py", '"pitch_type_options",', ""),
        (ROUTER, "Depends(require_tenant_access)", "Depends(not_authenticated)"),
        (
            "backend/src/pitchlog/repositories/pitch_type_options.py",
            '"CAP:tenant_vocabularies:read"',
            '"CAP:games:read"',
        ),
        (ROUTER, "router = APIRouter(", "router = FakeRouter("),
        (
            ROUTER,
            "router = APIRouter(",
            "require_tenant_access = lambda: None\nrouter = APIRouter(",
        ),
        (
            ROUTER,
            "from fastapi import APIRouter, Depends, HTTPException, Query",
            "from fake_fastapi import APIRouter, Depends, HTTPException, Query",
        ),
        (
            ROUTER,
            "router = APIRouter(",
            "tenant_transaction_scope = lambda *_: None\nrouter = APIRouter(",
        ),
        (ROUTER, "router = APIRouter(", "TenantMatchedRoute = object\nrouter = APIRouter("),
        (ROUTER, "router = APIRouter(", "from fastapi import Depends\nrouter = APIRouter("),
    ],
)
def test_real_source_binding_mutations_are_rejected(
    monkeypatch: pytest.MonkeyPatch, path: str, before: str, after: str
) -> None:
    """検査器の読取だけを差し替え、元原文provenance据置きの迂回を拒否する。"""
    routes, provenance = _registry()
    real_read = checker._read_text
    target = ROOT / path
    original = real_read(target, "mutation target")
    assert before in original, "変異が適用されないまま合格させない"

    def altered(file: Path, label: str) -> str:
        text: str = real_read(file, label)
        return text.replace(before, after) if file == target else text

    monkeypatch.setattr(checker, "_read_text", altered)
    with pytest.raises(checker.CatalogError):
        checker._validate_first_ball_options_http_routes(routes, provenance, ROOT)


def test_synthetic_without_the_new_http_group_does_not_read_product_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """新群が完全に無い個別意味fixtureへ実sourceの配置を要求しない。"""
    def unexpected(_root: Path) -> dict[str, dict[str, str]]:
        pytest.fail("合成fixtureで製品HTTP sourceを読んだ")

    monkeypatch.setattr(checker, "_first_ball_options_http_provenance", unexpected)
    checker._validate_first_ball_options_http_routes(
        {"ROUTE:RECORD:fixture:read": {"provenance_ids": []}}, [], tmp_path,
    )


def test_product_missing_the_entire_new_group_is_rejected_before_source_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """新群を丸ごと消しても製品本体の先行exact12拒否を迂回できない。"""
    asset = json.loads((ROOT / "contracts/authz/route-registry.json").read_text())
    claims = json.loads((ROOT / "contracts/authz/requirement-claims.json").read_text())
    removed = {"ROUTE:RECORD:games:insert", "ROUTE:RECORD:tenant_vocabularies:read"}
    asset["routes"] = [row for row in asset["routes"] if row["route_id"] not in removed]

    def unexpected(_root: Path) -> dict[str, dict[str, str]]:
        pytest.fail("exact12拒否前に新群のsourceを読んだ")

    def implemented_ids(value: object) -> set[str]:
        result: set[str] = set()
        if isinstance(value, dict):
            if value.get("status") == "implemented" and isinstance(value.get("id"), str):
                result.add(value["id"])
            for child in value.values():
                result.update(implemented_ids(child))
        elif isinstance(value, list):
            for child in value:
                result.update(implemented_ids(child))
        return result

    monkeypatch.setattr(checker, "_first_ball_options_http_provenance", unexpected)
    with pytest.raises(checker.CatalogError, match="record_and_aggregate route の exact-set"):
        checker.validate_route_registry(asset, claims, ROOT, frozenset(implemented_ids(asset)))
