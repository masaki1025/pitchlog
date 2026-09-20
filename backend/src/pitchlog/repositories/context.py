"""リポジトリへ渡すテナント文脈を定義する。"""

import hmac
import secrets
from dataclasses import dataclass, field
from typing import final
from uuid import UUID

_TENANT_CONTEXT_SECRET = secrets.token_bytes(32)


def _tenant_context_proof(tenant_id: UUID) -> bytes:
    """プロセス内だけで有効なテナント ID の発行証跡を作る。"""
    return hmac.digest(_TENANT_CONTEXT_SECRET, tenant_id.bytes, "sha256")


@final
@dataclass(frozen=True, slots=True, init=False)
class TenantContext:
    """呼び出し側が渡したテナント ID を信じて束縛する値オブジェクト。

    発行証跡は構築後に tenant_id が改竄されていないという完全性だけを検査する。
    この型は値の真正性を検査しない。テナント ID が認証済み主体のもので
    あることは引き続き API 層（TSK-217 / U-A1）の責務である。
    """

    tenant_id: UUID
    _integrity_proof: bytes = field(repr=False, compare=False)

    def __init__(self, tenant_id: UUID) -> None:
        """テナント ID を保持する。

        Args:
            tenant_id: 呼び出し側が認証済み主体から導出するテナント ID。
        """
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
