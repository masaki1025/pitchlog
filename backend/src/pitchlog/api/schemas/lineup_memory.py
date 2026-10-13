"""前回スタメンの復元候補を返す DTO。"""

from pydantic import JsonValue, StrictInt

from pitchlog.api.schemas.base import BaseSchema, EntityId


class LineupMemoryEntry(BaseSchema):
    """確定時の枠と現在採用できる選手を表す。"""

    batting_order: StrictInt | None
    fielding_position: JsonValue
    player_id: EntityId | None
    name: str | None
    uniform_number: str | None
    replacement_required: bool


class LineupMemoryResponse(BaseSchema):
    """保存時の順序を維持した復元候補を表す。"""

    entries: list[LineupMemoryEntry]
