"""通常の記録権引き継ぎで使う閉じた要求・応答外形。"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, SecretStr

from pitchlog.api.schemas.base import BaseSchema


class HandoverReleaseRequest(BaseSchema):
    """旧保持端末が明示的に解放を確定する要求。

    資格と V12 はヘッダー/本文の一方へ重複させず、この型では本文だけを受ける。
    """

    handover_request_id: UUID
    to_device_id: UUID
    from_d4: str = Field(min_length=1, max_length=128)
    last_d1: int = Field(ge=0)
    recording_right_proof: SecretStr
    confirm_release: Literal[True]


class HandoverAcquireRequest(BaseSchema):
    """新保持端末が同じ引き継ぎ要求の配達を受ける要求。"""

    handover_request_id: UUID


class HandoverReleaseResponse(BaseSchema):
    """解放が確定した事実だけを返し、新 V12 を含めない。"""

    tenant_id: UUID
    game_id: UUID
    handover_request_id: UUID
    from_device_id: UUID
    from_generation: str
    to_device_id: UUID
    last_d1: int
    released_at: AwareDatetime


class HandoverGrantResponse(BaseSchema):
    """新保持端末へ一度だけ渡す新世代の記録権値。"""

    tenant_id: UUID
    game_id: UUID
    handover_request_id: UUID
    device_id: UUID
    d4: str = Field(min_length=1, max_length=128)
    recovery_generation: str
    recording_right_proof: SecretStr
