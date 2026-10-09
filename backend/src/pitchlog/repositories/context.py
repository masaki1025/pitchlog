"""リポジトリへ渡すテナント文脈を定義する。"""

import hmac
import secrets
from dataclasses import dataclass, field
from typing import final
from uuid import UUID


@final
class TenantContextIssuanceCapability:
    """TenantContext の構築に必要な発行能力を表す。"""

    __slots__ = ()


_ISSUANCE_CAPABILITY = TenantContextIssuanceCapability()
_TENANT_CONTEXT_SECRET = secrets.token_bytes(32)


def _tenant_context_proof(tenant_id: UUID) -> bytes:
    """プロセス内だけで有効なテナント ID の発行証跡を作る。"""
    return hmac.digest(_TENANT_CONTEXT_SECRET, tenant_id.bytes, "sha256")


@final
@dataclass(frozen=True, slots=True, init=False)
class TenantContext:
    """呼び出し側が渡したテナント ID を信じて束縛する値オブジェクト。

    発行証跡が弾くのは、構築後に tenant_id だけを書き換え、証跡を更新しなかった
    場合である。同一プロセス内で導出経路へ到達できるコードは証跡を作り直せるため、
    同一プロセス内の攻撃者に対する信頼境界ではない。導出経路への参照も、静的検査が
    到達できる範囲だけで検出する。この型は値の真正性を検査しない。テナント ID が
    認証済み主体のものであることは引き続き API 層（TSK-217 / U-A1）の責務である。

    発行境界では、有効な TenantContext は当モジュールが私有する単一の発行能力を
    実引数に受けた構築からしか得られない。能力なしや同型の別実体では構築できない。
    同一プロセス内で発行能力の導出経路へ到達する任意コードは保証外である。
    発行能力や発行入口の名前が直接現れない転送も静的検査の保証外である。
    """

    tenant_id: UUID
    _integrity_proof: bytes = field(repr=False, compare=False)

    def __init__(
        self, tenant_id: UUID, issuance_capability: TenantContextIssuanceCapability
    ) -> None:
        """テナント ID を保持する。

        Args:
            tenant_id: 呼び出し側が認証済み主体から導出するテナント ID。
            issuance_capability: 当モジュールが私有する単一の発行能力。
        """
        if issuance_capability is not _ISSUANCE_CAPABILITY:
            raise TypeError("TenantContext の発行能力が一致しない")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "_integrity_proof", _tenant_context_proof(tenant_id))

    def _has_valid_integrity_proof(self) -> bool:
        """現在の tenant_id が構築時の発行証跡と一致するか返す。"""
        tenant_id = getattr(self, "tenant_id", None)
        integrity_proof = getattr(self, "_integrity_proof", None)
        if type(tenant_id) is not UUID or type(integrity_proof) is not bytes:
            return False
        return hmac.compare_digest(
            integrity_proof,
            _tenant_context_proof(tenant_id),
        )
