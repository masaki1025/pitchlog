"""TenantContext の型境界と生成箇所契約を検査する。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from pitchlog.repositories import tenant_context_contract
from pitchlog.repositories.context import (
    _ISSUANCE_CAPABILITY,
    TenantContext,
    TenantContextIssuanceCapability,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLIST_PATH = Path("contracts/tenant_boundary/tenant-context-allowlist.json")


def make_tenant_context(tenant_id: UUID) -> TenantContext:
    """生成箇所 allowlist で許可されたテスト専用経路から文脈を構築する。"""
    return TenantContext(tenant_id, _ISSUANCE_CAPABILITY)


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
        "integrity_secret_symbol": tenant_context_contract.INTEGRITY_SECRET_SYMBOL,
        "integrity_secret_allowed_symbols": list(
            tenant_context_contract.INTEGRITY_SECRET_ALLOWED_SYMBOLS
        ),
        "integrity_proof_factory_symbol": (
            tenant_context_contract.INTEGRITY_PROOF_FACTORY_SYMBOL
        ),
        "integrity_proof_factory_allowed_symbols": list(
            tenant_context_contract.INTEGRITY_PROOF_FACTORY_ALLOWED_SYMBOLS
        ),
        "issuance_capability_symbol": (
            tenant_context_contract.ISSUANCE_CAPABILITY_SYMBOL
        ),
        "issuance_capability_allowed_symbols": list(
            tenant_context_contract.ISSUANCE_CAPABILITY_ALLOWED_SYMBOLS
        ),
        "issuance_entrypoint_symbol": (
            tenant_context_contract.ISSUANCE_ENTRYPOINT_SYMBOL
        ),
        "issuance_entrypoint_allowed_symbols": list(
            tenant_context_contract.ISSUANCE_ENTRYPOINT_ALLOWED_SYMBOLS
        ),
        "allowed_test_modules": list(tenant_context_contract.ALLOWED_TEST_MODULES),
        "allowed_product_modules": list(
            tenant_context_contract.ALLOWED_PRODUCT_MODULES
        ),
    }


def _asset_snapshot(asset: dict[str, Any]) -> dict[str, Any]:
    """更新履歴を除く生成対象フィールドを返す。"""
    snapshot = dict(asset)
    snapshot.pop("baseline_control", None)
    return snapshot


def test_tenant_context_is_an_immutable_value_object() -> None:
    """TenantContext が UUID を保持する frozen 値オブジェクトであることを確認する。"""
    tenant_id = uuid4()

    context = make_tenant_context(tenant_id)

    assert context.tenant_id == tenant_id
    assert getattr(TenantContext, "__final__", False) is True
    with pytest.raises(FrozenInstanceError):
        setattr(context, "tenant_id", uuid4())


def test_tenant_context_requires_issuance_capability() -> None:
    """発行能力を渡さない構築を拒否する。"""
    with pytest.raises(TypeError):
        cast(Any, TenantContext)(uuid4())


def test_tenant_context_rejects_another_issuance_capability_instance() -> None:
    """同型でも別実体の発行能力は拒否する。"""
    with pytest.raises(TypeError):
        TenantContext(uuid4(), TenantContextIssuanceCapability())


def test_issuance_capability_is_final() -> None:
    """発行能力の型を継承不可として宣言している。"""
    assert getattr(TenantContextIssuanceCapability, "__final__", False) is True


def test_tenant_context_documents_unverified_authenticity_boundary() -> None:
    """証跡の限界と真正性の責任所有者が説明に残ることを確認する。"""
    documentation = TenantContext.__doc__ or ""

    assert "tenant_id だけを書き換え" in documentation
    assert "同一プロセス内の攻撃者に対する信頼境界ではない" in documentation
    assert "静的検査が" in documentation
    assert "真正性を検査しない" in documentation
    assert "TSK-217 / U-A1" in documentation
    assert "単一の発行能力を" in documentation
    assert "導出経路へ到達する任意コードは保証外" in documentation
    assert "名前が直接現れない転送も静的検査の保証外" in documentation


def test_tenant_context_integrity_proof_detects_tenant_id_tampering() -> None:
    """Frozen を迂回した構築後の tenant_id 改竄を発行証跡で検出する。"""
    context = make_tenant_context(uuid4())

    object.__setattr__(context, "tenant_id", uuid4())

    assert context._has_valid_integrity_proof() is False


def test_generated_allowlist_matches_asset() -> None:
    """生成箇所資産と配布対象モジュールが完全一致することを確認する。"""
    asset = _read_allowlist()

    assert tenant_context_contract.SOURCE_ASSET == _ALLOWLIST_PATH.as_posix()
    assert asset["source_digest"] == _asset_digest(asset)
    assert _generated_snapshot() == _asset_snapshot(asset)


def test_product_construction_allowlist_names_roster_issuer_only() -> None:
    """製品側の生成入口を選手の発行専用モジュールへ閉じる。"""
    assert __name__ in tenant_context_contract.ALLOWED_TEST_MODULES
    assert tenant_context_contract.ALLOWED_PRODUCT_MODULES == (
        "pitchlog.repositories.tenant_context_issuance",
    )


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
        "integrity_secret_symbol",
        "integrity_secret_allowed_symbols",
        "issuance_capability_symbol",
        "issuance_capability_allowed_symbols",
        "issuance_entrypoint_symbol",
        "issuance_entrypoint_allowed_symbols",
        "allowed_test_modules",
        "allowed_product_modules",
    ),
)
def test_each_stale_generated_allowlist_field_is_red(field: str) -> None:
    """生成モジュールの各フィールドが古い変異を一致検査で検出する。"""
    generated = _generated_snapshot()
    generated[field] = object()

    assert generated != _asset_snapshot(_read_allowlist())
