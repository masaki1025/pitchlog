"""通常投球Portの元参照命令と、投影値の有限SQL入力。資格は生成しない。"""

from dataclasses import dataclass, field
from uuid import UUID

from pitchlog.sync.model import SyncEvent
from pitchlog.sync.tokens import _SyncToken


@dataclass(frozen=True, slots=True)
class ValidateOrdinaryPitchToken(_SyncToken):
    """元event/同writerを核へ返す内容確認命令。"""

    game_id: UUID
    d5: UUID
    event: SyncEvent = field(repr=False)
    writer: object = field(repr=False)
    _capability_id = "CAP:operation_events:read"

    def __post_init__(self):
        """UUID/元参照を変換せず照合する。"""
        if (
            type(self.game_id) is not UUID
            or type(self.d5) is not UUID
            or type(self.event) is not SyncEvent
            or str(self.game_id) != self.event.game_id
            or str(self.d5) != self.event.d5
        ):
            raise ValueError("通常内容命令の参照が不一致")


@dataclass(frozen=True, slots=True)
class ProjectOrdinaryPitchToken(_SyncToken):
    """採番済み元eventの実frame消費/保存を要求し、boolを受け取らない。"""

    game_id: UUID
    d5: UUID
    projected: SyncEvent = field(repr=False)
    writer: object = field(repr=False)
    _capability_id = "CAP:play_rows:insert"

    def __post_init__(self):
        """別game/D5/同型レコードを正規化しない。"""
        if (
            type(self.game_id) is not UUID
            or type(self.d5) is not UUID
            or type(self.projected) is not SyncEvent
            or str(self.game_id) != self.projected.game_id
            or str(self.d5) != self.projected.d5
        ):
            raise ValueError("通常投影命令の参照が不一致")


@dataclass(frozen=True, slots=True)
class OrdinaryPlayRowInsertToken(_SyncToken):
    """全41物理列と同TX原本メタ値。DB資格とは別に検査する。"""

    game_id: UUID
    generation: int
    d1: int
    d2: int
    d5: UUID
    source_fingerprint: str
    row_json: str = field(repr=False)
    _capability_id = "CAP:play_rows:insert"
