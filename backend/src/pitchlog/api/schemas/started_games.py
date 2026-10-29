"""開始済み試合の再取得応答を定義する。確定状態と現在参照だけを返す。

記録権の保持者・資格・証明・確認済みの進み具合・tenantは返さない。端末が保持者かを
判断する比較は呼出側の責務で、この応答は書込みの許可に使わない。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from pitchlog.api.schemas.base import BaseSchema, EntityId, Timestamp
from pitchlog.api.schemas.games import GameTypeKey
from pitchlog.domainrt.first_pitch import HistoryEntry, StateSnapshot, StatFlags
from pitchlog.domainrt.first_pitch_continuation import T2NoEndCore
from pitchlog.domainrt.initial_game_roster import (
    InitialRosterProjection,
    OneToNine,
    Role,
)
from pitchlog.sync.first_ball_payload import FirstBallCourse

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


PressWire = Literal["0", "1プレス", "3プレス", "両プレス"]
"""保存 `text` の4状態。boolへ潰さず、`0` と `1` を同じ値にしない。"""

FirstBallInteger = Annotated[int, Field(strict=True, ge=1, le=1)]
"""初球の範囲で1に固定された整数。boolの `True` を1として受理しない。"""


class StartedPlayRow(_FrozenSchema):
    """保存初球1行の公開値。物理41列のうち36列だけを公開する。

    除外するのは `tenant_id`（応答文脈で固定・非開示）と内部の移行・論理削除列
    `hidden_at` / `import_batch_id` / `legacy_row_identifier` / `migration_unverified`
    の計5列である（41 − 5 = 36列）。このうち座標 `course_x` / `course_y` の2列は、
    物理Doubleを公開せず、payloadの正準整数kを `course` 1値（`unit`/`x`/`y`）へ
    まとめて返すため、本型のfield数は35になる。公開列の集合は試験で固定する。

    値は `recorded_snapshot` が保存PlayRow・payload・participants の全値一致を
    確認したものだけであり、この型は再計算も補完もしない。`play_number` /
    `batting_order` / `event_kind` / `version` は reader が 1 / 1 / `pitch` / 1 を
    厳密一致で確認済みなので、初球の範囲を閉じた `Literal` で表す。
    `batter_id` / `pitcher_id` / `catcher_id` / `pitch_type_key` /
    `batting_result_key` / `course` も照合済みで必須。それ以外は保存列が
    nullable で照合対象にも含まれないため `| None` とする。
    """

    id: EntityId
    game_id: EntityId
    source_event_id: EntityId
    play_number: FirstBallInteger
    batting_order: FirstBallInteger
    batter_id: EntityId
    pitcher_id: EntityId
    catcher_id: EntityId
    batting_side: Literal["右", "左"] | None
    stance: str | None
    strategy_key: str | None
    strategy_detail_key: str | None
    strategy_result_key: str | None
    batter_status: str | None
    event_kind: Literal["pitch"]
    course: FirstBallCourse
    pitch_type_key: Annotated[str, Field(min_length=1)]
    batting_result_key: Annotated[str, Field(min_length=1)]
    secondary_batting_result_key: str | None
    raw_fielder_position: str | None
    resolved_fielder_id: EntityId | None
    batted_ball_type: str | None
    batted_ball_strength: str | None
    hit_x: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None
    hit_y: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None
    pickoff_type: str | None
    pickoff_detail: str | None
    error_type: str | None
    raw_error_position: str | None
    resolved_error_player_id: EntityId | None
    pitch_speed: Annotated[float, Field(allow_inf_nan=False)] | None
    press: PressWire | None
    fake_run: PressWire | None
    comment: str | None
    version: FirstBallInteger


class StartedRecordedGameRead(StartedGameRead):
    """記録後（保存済みの先頭1球）の再取得応答。

    `state` の意味は `initial` と変えない（開始原典の before）。記録後の状態は
    別key `after` に置き、同じkeyの意味を反転させない。`history` /
    `stat_flags` / `t2` / `play_rows` は保存初球の独立再評価値をそのまま返し、
    Pythonで再計算しない。
    """

    read_kind: Literal["recorded"]
    state: StateSnapshot = Field(description="開始原典のbefore。記録後の値はafter。")
    after: StateSnapshot = Field(
        description="保存済み初球1球を独立再評価した後の状態。"
    )
    history: Annotated[list[HistoryEntry], Field(min_length=1, max_length=1)]
    stat_flags: StatFlags
    t2: T2NoEndCore
    play_rows: Annotated[list[StartedPlayRow], Field(min_length=1, max_length=1)]


StartedGameReadResponse = Annotated[
    StartedGameRead | StartedRecordedGameRead,
    Field(discriminator="read_kind"),
]
"""`read_kind` で判別する記録前後の応答。既存 `initial` の形は変えない。"""
