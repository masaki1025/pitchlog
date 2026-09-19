"""TenantContext の型境界と生成箇所契約を検査する。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from pitchlog.repositories import tenant_context_contract
from pitchlog.repositories.context import TenantContext

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLIST_PATH = Path("contracts/tenant_boundary/tenant-context-allowlist.json")


def make_tenant_context(tenant_id: UUID) -> TenantContext:
    """生成箇所 allowlist で許可されたテスト専用経路から文脈を構築する。"""
    return TenantContext(tenant_id)


def _read_allowlist() -> dict[str, Any]:
    """生成箇所 allowlist を JSON object として読む。"""
    value = json.loads((_REPOSITORY_ROOT / _ALLOWLIST_PATH).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AssertionError("TenantContext allowlist が JSON object でない")
    return value


def _asset_digest(asset: dict[str, Any]) -> str:
    """source_digest 欄を除く正規化 digest を計算する。"""
    payload = dict(asset)
    payload.pop("source_digest", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _generated_snapshot() -> dict[str, object]:
    """配布モジュールの生成値を資産と比較できる形へ変換する。"""
    return {
        "schema_version": tenant_context_contract.SCHEMA_VERSION,
        "contract_revision": tenant_context_contract.CONTRACT_REVISION,
        "asset_kind": tenant_context_contract.ASSET_KIND,
        "canonicalization": tenant_context_contract.CANONICALIZATION,
        "source_digest": tenant_context_contract.SOURCE_DIGEST,
        "constructor_symbol": tenant_context_contract.CONSTRUCTOR_SYMBOL,
        "forbidden_construction_symbols": list(
            tenant_context_contract.FORBIDDEN_CONSTRUCTION_SYMBOLS
        ),
        "allowed_test_modules": list(tenant_context_contract.ALLOWED_TEST_MODULES),
        "allowed_product_modules": list(
            tenant_context_contract.ALLOWED_PRODUCT_MODULES
        ),
    }


def test_tenant_context_is_an_immutable_value_object() -> None:
    """TenantContext が UUID を保持する frozen 値オブジェクトであることを確認する。"""
    tenant_id = uuid4()

    context = make_tenant_context(tenant_id)

    assert context.tenant_id == tenant_id
    assert getattr(TenantContext, "__final__", False) is True
    with pytest.raises(FrozenInstanceError):
        setattr(context, "tenant_id", uuid4())


def test_tenant_context_documents_unverified_authenticity_boundary() -> None:
    """真正性を守らない境界と責任所有者が型の説明に残ることを確認する。"""
    documentation = TenantContext.__doc__ or ""

    assert "真正性を検査しない" in documentation
    assert "TSK-217 / U-A1" in documentation


def test_generated_allowlist_matches_asset() -> None:
    """生成箇所資産と配布対象モジュールが完全一致することを確認する。"""
    asset = _read_allowlist()

    assert tenant_context_contract.SOURCE_ASSET == _ALLOWLIST_PATH.as_posix()
    assert asset["source_digest"] == _asset_digest(asset)
    assert _generated_snapshot() == asset


def test_product_construction_allowlist_is_empty() -> None:
    """U-A1 / TSK-217 の導入前は製品側の生成入口を開けない。"""
    assert __name__ in tenant_context_contract.ALLOWED_TEST_MODULES
    assert tenant_context_contract.ALLOWED_PRODUCT_MODULES == ()


@pytest.mark.parametrize(
    "field",
    (
        "schema_version",
        "contract_revision",
        "asset_kind",
        "canonicalization",
        "source_digest",
        "constructor_symbol",
        "forbidden_construction_symbols",
        "allowed_test_modules",
        "allowed_product_modules",
    ),
)
def test_each_stale_generated_allowlist_field_is_red(field: str) -> None:
    """生成モジュールの各フィールドが古い変異を一致検査で検出する。"""
    generated = _generated_snapshot()
    generated[field] = object()

    assert generated != _read_allowlist()
