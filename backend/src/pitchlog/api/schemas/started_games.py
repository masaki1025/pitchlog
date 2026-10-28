"""開始済み試合の再取得応答を定義する。確定状態と現在参照だけを返す。

記録権の保持者・資格・証明・確認済みの進み具合・tenantは返さない。端末が保持者かを
判断する比較は呼出側の責務で、この応答は書込みの許可に使わない。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from pitchlog.api.schemas.base import BaseSchema, EntityId, Timestamp
from pitchlog.api.schemas.games import GameTypeKey
from pitchlog.domainrt.first_pitch import StateSnapshot
from pitchlog.domainrt.initial_game_roster import (
    InitialRosterProjection,
    OneToNine,
    Role,
)

CurrentD4 = Annotated[str, Field(pattern=r"^d4\.1\.[A-Za-z0-9_-]{55}$")]


class _FrozenSchema(BaseSchema):
    """未知keyを拒否し、構築後に変更できない応答の共通基底。"""

    model_config = ConfigDict(frozen=True)


class StartedLineupEntry(_FrozenSchema):
    """開始時に保存した一選手の役割と背番号。現在の名簿値で置換しない。"""

    player_id: EntityId
    batting_order: OneToNine | None
    fielding_position: Role
    uniform_number_snapshot: str | None


class StartedLineup(_FrozenSchema):
    """保存済みの片側lineup。順序を保つ。"""

    lineup_id: EntityId
    team_record_id: EntityId
    entries: Annotated[list[StartedLineupEntry], Field(min_length=9, max_length=10)]


class StartedLineups(_FrozenSchema):
    """away・homeの固定二要素。"""

    away: StartedLineup
    home: StartedLineup


class StartedGameRead(_FrozenSchema):
    """同tenantの開始済み(記録前)試合の確定状態。"""

    read_kind: Literal["initial"]
    id: EntityId
    scheduled_at: Timestamp
    game_type_key: GameTypeKey
    tournament_key: str = Field(min_length=1)
    away_team_record_id: EntityId
    home_team_record_id: EntityId
    plate_umpire: str | None
    section_label: str | None
    week_label: str | None
    day_label: str | None
    game_number_label: str | None
    status: Literal["in_progress"]
    started_at: Timestamp
    applied_rules: dict[str, object]
    lineups: StartedLineups
    roster: InitialRosterProjection
    state: StateSnapshot
    current_d4: CurrentD4 | None
