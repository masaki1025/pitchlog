"""P3の同一実frameからだけ発行するページ保存命令。"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True)
class _BeginP3ProjectionPageToken(TenantOperationToken):
    """同一P3実frameからだけ生成するページ保存開始命令。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID
    capsule_header: str = field(repr=False)
    stats_header: str = field(repr=False)

    @property
    def capability_id(self) -> str:
        """P3ページ保存開始だけの固定能力。"""
        return "CAP:sync_p3:begin_p3_projection_page"


@dataclass(frozen=True, slots=True)
class _AppendP3ProjectionPageToken(TenantOperationToken):
    """同一P3実frameからだけ生成する最大25行の追記命令。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID
    capsule_id: UUID
    page_json: str = field(repr=False)

    @property
    def capability_id(self) -> str:
        """P3ページ追記だけの固定能力。"""
        return "CAP:sync_p3:append_p3_projection_page"


@dataclass(frozen=True, slots=True)
class _FinalizeP3ProjectionPageToken(TenantOperationToken):
    """同一P3実frameの全ページ照合後だけ生成する確定命令。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID
    capsule_id: UUID

    @property
    def capability_id(self) -> str:
        """P3ページ確定だけの固定能力。"""
        return "CAP:sync_p3:finalize_p3_projection_page"


