"""初球の投影済み値だけを保持する閉じた登録token。真正な保存資格ではない。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True, repr=False)
class FirstBallPlayRowInsertToken(TenantOperationToken):
    """同writerが供給する物理値。認可/空初球/数学/DB印は別に必要。"""

    id: UUID
    game_id: UUID
    source_event_id: UUID
    generation: int
    d1: int
    d2: int
    d5: UUID
    source_fingerprint: str
    batter_id: UUID
    pitcher_id: UUID
    catcher_id: UUID
    pitch_type_key: str
    course_x: float
    course_y: float
    pitch_speed: float | None = None
    stance: str | None = None
    batting_side: str | None = None

    @property
    def capability_id(self) -> str:
        """既CAPの識別だけを返す。runtime許可を新設しない。"""
        return "CAP:play_rows:insert"


@dataclass(frozen=True, slots=True, repr=False)
class FirstBallPlayRowReadToken(TenantOperationToken):
    """同game/source_eventに閉じたnative可視行の限定read値。"""

    game_id: UUID
    source_event_id: UUID

    @property
    def capability_id(self) -> str:
        """既read CAPの識別だけを返す。"""
        return "CAP:play_rows:read"
