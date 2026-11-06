"""基本成績APIの閉じた応答型。"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

StatState = Literal["available", "source_unavailable"]
Category = Literal["official", "practice", "all"]


class RatioValue(BaseModel):
    """丸め前の非負有理数を閉じた正準整数文字列で返す。"""

    model_config = ConfigDict(extra="forbid")
    numerator: str = Field(pattern=r"^(0|[1-9][0-9]*)$")
    denominator: str = Field(pattern=r"^[1-9][0-9]*$")


class BasicStatItem(BaseModel):
    """1指標の表示値。率は生成済みformatterの表示をそのまま返す。"""

    metric_id: str
    label: str
    state: StatState
    value: int | RatioValue | None
    display: str | None
    reason: str | None = None
    components: dict[str, Any] | None = None


class PlayerBasicStats(BaseModel):
    """1選手の打撃16・投手11と未接続理由。"""

    player_id: UUID
    player_name: str
    uniform_number: str = ""
    team_record_id: UUID
    team_name: str
    is_pitcher: bool
    batting: list[BasicStatItem]
    pitching: list[BasicStatItem]
    pending: list[str]


class GameBasicStats(BaseModel):
    """試合別基本成績。modeで公式/暫定を区別する。"""

    game_id: UUID
    mode: Literal["current", "official"]
    players: list[PlayerBasicStats]
    next_cursor: str | None = None


class SeasonBasicStats(BaseModel):
    """JST暦年の基本成績。終了確定した最新版だけを対象にする。"""

    year: int = Field(ge=1, le=9999)
    category: Category
    period_label: str
    players: list[PlayerBasicStats]
    next_cursor: str | None = None


class BasicStatsCsvManifest(BaseModel):
    """成績CSVの同一snapshotと行数。"""

    format_version: int
    game_id: UUID | None = None
    year: int | None = None
    category: Category | None = None
    rows: int
    sha256: str
    filename: str
