"""開始済み試合の再取得応答を定義する。確定状態と現在参照だけを返す。

記録権の保持者・資格・証明・確認済みの進み具合・tenantは返さない。端末が保持者かを
判断する比較は呼出側の責務で、この応答は書込みの許可に使わない。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, model_validator

from pitchlog.api.schemas.base import BaseSchema, EntityId, Timestamp
from pitchlog.api.schemas.games import GameTypeKey
from pitchlog.domainrt.first_pitch import (
    DecimalInteger,
    HistoryEntry,
    StateSnapshot,
    StatFlags,
)
from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire, T2NoEndCore
from pitchlog.domainrt.initial_game_roster import (
    InitialRosterProjection,
    OneToNine,
    Role,
)
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    T2 as LineupT2,
)
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    Lineup,
    NonplayActiveFrame,
    NonplayCheckpoint,
)
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    Participants as LineupParticipants,
)
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    PaStart as LineupPaStart,
)
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    PrefixRef as LineupPrefixRef,
)
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    Runner as LineupRunner,
)
from pitchlog.domainrt.ordinary_pitch_continuation import (
    NewHistoryEntry,
    OrdinaryT2,
    PrefixRef,
)
from pitchlog.domainrt.ordinary_wire import (
    RECOVERY_WIRE_FIELD,
    assert_prefix_matches,
)
from pitchlog.domainrt.play_prefix_continuation import (
    BridgeEvidence,
    CanonicalUuid,
    Checkpoint,
    Digest,
    Participants,
    PaStartSource,
    PlayIdentity,
    PlayPrefixRef,
    PlayT2,
    RunnerSnapshot,
)
from pitchlog.domainrt.strikeout_pitch import StrikeoutHistoryEntry, StrikeoutSnapshot
from pitchlog.domainrt.terminal_pitch import TerminalHistoryEntry, TerminalSnapshot
from pitchlog.repositories.play_prefix import StorageAnchor
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
"""保存 `text` の4状態。boolへ潰さず、`0` と `1` を同じ値にしない。

初球writerはpress/fake_runを常にNULLで保存し、readerは非NULLを破損として
拒否する。この型は列の閉じた語彙（legacy値をbool化しないこと）を表す。
"""

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
    `batting_result_key` / `course` も照合済みで必須。payload が null を取り得る
    `stance` / `batting_side` / `pitch_speed` は payload と照合する。残る19列
    （作戦・打球・牽制・失策・press 等）は payload に由来が無く、初球 writer が
    常に NULL で保存するため、reader が NULL 一致を確認し、非NULLは破損（503）
    として公開しない。型が `| None` なのはこの NULL を表すためである。
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


class RecordedPrefixPlayRow(StartedPlayRow):
    """現在のordinary行の公開35key。内部41全値照合を別に要求する。"""

    play_number: Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
    batting_order: Annotated[int, Field(strict=True, ge=1, le=9)]
    version: Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]


class LineupNonPitchPlayRow(RecordedPrefixPlayRow):
    """v3申告敬遠だけの公開行。投球観測を仮補完せず全NULLで閉じる。"""

    event_kind: Literal["non_pitch"]
    batting_result_key: Literal["batting-result.intentional-walk"]
    course: None
    pitch_type_key: None
    pitch_speed: None
    stance: None
    batting_side: None
    strategy_key: None
    strategy_detail_key: None
    strategy_result_key: None
    batter_status: None
    secondary_batting_result_key: None
    raw_fielder_position: None
    resolved_fielder_id: None
    batted_ball_type: None
    batted_ball_strength: None
    hit_x: None
    hit_y: None
    pickoff_type: None
    pickoff_detail: None
    error_type: None
    raw_error_position: None
    resolved_error_player_id: None
    press: None
    fake_run: None
    comment: None


class OrdinaryAppendPolicy(_FrozenSchema):
    """初期D2とgapの限定送信方針。DB bigint上限を変更しない。"""

    version: Literal["ordinary-append-v1"]
    first_d2: Literal["1"]
    d2_gap: Literal["1000"]
    max_d2: Literal["9007199254740991"]


def _positive_prefix_integer(value: str) -> str:
    """非負正準整数型のうち0だけを拒否する。"""
    if value == "0":
        raise ValueError("正の位置/版が必要")
    return value


PositivePrefixInteger = Annotated[
    DecimalInteger, AfterValidator(_positive_prefix_integer)
]


class PrefixNextPosition(_FrozenSchema):
    """実同期原本から取得する次位置。prefix長/行版から推測しない。"""

    d1: PositivePrefixInteger
    d2: PositivePrefixInteger


class PrefixCheckpointAnchor(_FrozenSchema):
    """persist済checkpointだけの実識別。GETで生成しない。"""

    id: EntityId
    revision: PositivePrefixInteger
    history_version: PositivePrefixInteger


class PrefixPageItem(_FrozenSchema):
    """実保存行とそれに結合した今回entry。全履歴を意味しない。"""

    play_row: RecordedPrefixPlayRow
    history_entry: NewHistoryEntry


class PrefixPage(_FrozenSchema):
    """checkpointに固定した有限ページ。未送信分を含めない。"""

    items: Annotated[list[PrefixPageItem], Field(max_length=100)]
    next_cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None


class StartedRecordedPrefixGameRead(StartedGameRead):
    """通常投球の実保存prefix。旧無query応答は変更しない。"""

    read_kind: Literal["recorded-prefix"]
    after: StateSnapshot
    prefix_ref: PrefixRef
    rules: SavedRuleWire
    t2: T2NoEndCore | OrdinaryT2 | None
    last_entry: NewHistoryEntry | None
    next_position: PrefixNextPosition
    checkpoint_anchor: PrefixCheckpointAnchor | None
    recovery: PositivePrefixInteger = Field(alias=RECOVERY_WIRE_FIELD)
    page: PrefixPage
    append_policy: OrdinaryAppendPolicy
    last_saved_at: Timestamp

    @model_validator(mode="after")
    def _prefix_correlations(self):
        """空prefix/実anchor/今回entryの相関だけを検査する。"""
        n = int(self.prefix_ref.length)
        assert_prefix_matches(self.prefix_ref, str(self.id), self.current_d4)
        if n == 0:
            if (
                self.t2 is not None
                or self.last_entry is not None
                or self.checkpoint_anchor is not None
                or self.page.items
                or self.page.next_cursor is not None
                or self.after != self.state
            ):
                raise ValueError("空prefixへ記録済み値を付与できない")
        elif (
            self.t2 is None
            or self.last_entry is None
            or (n > 1 and self.checkpoint_anchor is None)
        ):
            raise ValueError("記録済みprefixの実根拠が不足")
        if n > 1 and not isinstance(self.t2, OrdinaryT2):
            raise ValueError("通常継続T2の型が不一致")
        if self.page.next_cursor is not None and not self.page.items:
            raise ValueError("空pageへ次cursorを付与できない")
        ids = set()
        for item in self.page.items:
            if item.play_row.game_id != self.id or item.play_row.id in ids:
                raise ValueError("pageに別試合/重複行を混ぜられない")
            ids.add(item.play_row.id)
        return self


class StartedPlayRunner(_FrozenSchema):
    """同tenantで全10列照合したrunnerの公開部分。"""

    id: EntityId
    play_id: EntityId
    base: Annotated[int, Field(strict=True, ge=1, le=3)]
    runner_id: EntityId
    status: Literal[
        "継続",
        "二進",
        "三進",
        "本進",
        "封殺",
        "投手牽制死",
        "捕手牽制死",
        "盗塁死",
        "走塁死",
    ]
    status_source: Literal["auto", "manual"]
    responsible_pitcher_id: EntityId

    @model_validator(mode="after")
    def _base_status(self):
        """起点塁ごとの既語彙だけを公開する。"""
        destinations = {
            1: {"二進", "三進", "本進"},
            2: {"三進", "本進"},
            3: {"本進"},
        }
        outcomes = {"継続", "封殺", "投手牽制死", "捕手牽制死", "盗塁死", "走塁死"}
        if self.status not in destinations[self.base] | outcomes:
            raise ValueError("起点塁と走者状況が不一致")
        return self


class PlayPrefixPageItem(_FrozenSchema):
    """legacy/newの実履歴と同play runner。"""

    play_row: RecordedPrefixPlayRow
    history_entry: TerminalHistoryEntry | NewHistoryEntry
    play_runners: Annotated[list[StartedPlayRunner], Field(max_length=3)]


class PlayPrefixPage(_FrozenSchema):
    """storage epochとwire headへ束縛した有界page。"""

    items: Annotated[list[PlayPrefixPageItem], Field(max_length=100)]
    next_cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None


class StartedPlayPrefixGameRead(StartedGameRead):
    """v2と移行候補のreadonly応答。書込資格ではない。"""

    read_kind: Literal["play-prefix"]
    last_source: PlayIdentity | None
    prior_artifact_sha256: Digest
    pa_start_source: PaStartSource
    after: TerminalSnapshot
    prefix_ref: PlayPrefixRef | PrefixRef
    rules: SavedRuleWire
    t2: PlayT2 | T2NoEndCore | OrdinaryT2 | None
    last_entry: TerminalHistoryEntry | NewHistoryEntry | None
    next_position: PrefixNextPosition
    checkpoint_anchor: PrefixCheckpointAnchor | None
    recovery: PositivePrefixInteger = Field(alias=RECOVERY_WIRE_FIELD)
    page: PlayPrefixPage
    append_policy: OrdinaryAppendPolicy
    last_saved_at: Timestamp
    bridge_checkpoint: Checkpoint | None
    storage_anchor: StorageAnchor | None
    bridge_origin: BridgeEvidence | None
    runners: Annotated[list[RunnerSnapshot], Field(max_length=3)]
    participants: Participants | None

    @model_validator(mode="after")
    def _head_binding(self):
        """実persist済v2か未保存移行候補のどちらか一方に閉じる。"""
        assert_prefix_matches(self.prefix_ref, str(self.id), self.current_d4)
        n = int(self.prefix_ref.length)
        if n == 0:
            if (
                self.last_source is not None
                or self.t2 is not None
                or self.last_entry is not None
                or self.checkpoint_anchor is not None
                or self.page.items
                or self.page.next_cursor is not None
                or self.after.model_dump(mode="json", by_alias=True)
                != self.state.model_dump(mode="json", by_alias=True)
            ):
                raise ValueError("空prefixへ保存済根拠を付与できない")
        elif self.last_source is None or self.last_entry is None or self.t2 is None:
            raise ValueError("記録済みsource根拠が不足")
        if self.page.next_cursor is not None and not self.page.items:
            raise ValueError("空pageへ次cursorを付与できない")
        ids = set()
        for item in self.page.items:
            if (
                item.play_row.game_id != self.id
                or item.play_row.id in ids
                or any(r.play_id != item.play_row.id for r in item.play_runners)
            ):
                raise ValueError("pageに別game/play/重複行を混ぜられない")
            ids.add(item.play_row.id)
        if isinstance(self.prefix_ref, PlayPrefixRef):
            if (
                self.bridge_checkpoint is not None
                or self.storage_anchor is None
                or self.bridge_origin is None
                or self.participants is None
                or not isinstance(self.t2, PlayT2)
                or self.checkpoint_anchor is None
            ):
                raise ValueError("v2実保存根拠不足")
            if (
                self.storage_anchor.id != str(self.checkpoint_anchor.id)
                or self.storage_anchor.history_epoch
                != self.checkpoint_anchor.history_version
                or self.prefix_ref.checkpoint.revision
                != self.checkpoint_anchor.revision
                or self.bridge_origin.v1_ref != self.prefix_ref.origin
            ):
                raise ValueError("storage anchorとwire headの相関が不一致")
        elif (
            self.bridge_checkpoint is None
            or self.storage_anchor is not None
            or self.bridge_origin is not None
            or self.runners
            or self.participants is not None
        ):
            raise ValueError("移行候補へv2実保存値を混在できない")
        return self


class LineupPrefixPageItem(_FrozenSchema):
    """実v3行/実差分/物理before走者の閉じたpage item。"""

    play_row: RecordedPrefixPlayRow | LineupNonPitchPlayRow
    history_entry: StrikeoutHistoryEntry
    play_runners: Annotated[list[StartedPlayRunner], Field(max_length=3)]


class LineupPrefixPage(_FrozenSchema):
    """現v3 headに固定した有界page。"""

    items: Annotated[list[LineupPrefixPageItem], Field(max_length=100)]
    next_cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None


class StartedLineupPrefixGameRead(StartedGameRead):
    """両cursor/実投捕を保存したv3だけのreadonly DTO。"""

    read_kind: Literal["lineup-prefix"]
    after: StrikeoutSnapshot
    prefix_ref: LineupPrefixRef
    rules: SavedRuleWire
    t2: LineupT2 | None
    last_entry: StrikeoutHistoryEntry | None
    last_source: PlayIdentity | None
    prior_artifact_sha256: Digest
    pa_start_source: LineupPaStart
    lineup: Lineup
    roster_digest: Digest
    runners: Annotated[list[LineupRunner], Field(max_length=3)]
    participants: LineupParticipants
    next_position: PrefixNextPosition
    checkpoint_anchor: PrefixCheckpointAnchor | None
    storage_anchor: StorageAnchor | None
    recovery: PositivePrefixInteger = Field(alias=RECOVERY_WIRE_FIELD)
    page: LineupPrefixPage
    append_policy: OrdinaryAppendPolicy
    last_saved_at: Timestamp

    @model_validator(mode="after")
    def _lineup_head(self):
        """実headと初期/記録済metadataを混ぜない。writer資格を発行しない。"""
        assert_prefix_matches(self.prefix_ref, str(self.id), self.current_d4)
        n = int(self.prefix_ref.length)
        if n == 0:
            before = self.after.model_dump(mode="json", by_alias=True)
            del before["battingOrderBySide"]
            if (
                before != self.state.model_dump(mode="json", by_alias=True)
                or self.last_source is not None
                or self.last_entry is not None
                or self.t2 is not None
                or self.checkpoint_anchor is not None
                or self.storage_anchor is not None
                or self.page.items
                or self.page.next_cursor is not None
                or self.runners
            ):
                raise ValueError("v3初期へ保存済値が混入")
        elif (
            self.last_source is None
            or self.last_entry is None
            or self.t2 is None
            or self.checkpoint_anchor is None
            or self.storage_anchor is None
        ):
            raise ValueError("v3保存head原本不足")
        if self.page.next_cursor is not None and not self.page.items:
            raise ValueError("v3空page位置不正")
        ids = set()
        for item in self.page.items:
            if item.play_row.game_id != self.id or item.play_row.id in ids:
                raise ValueError("v3page試合/重複不正")
            ids.add(item.play_row.id)
        return self


class NonplayActivePage(BaseSchema):
    """部分pageを完全Sourceと混同しない。"""

    items: Annotated[list[NonplayActiveFrame], Field(max_length=100)]
    next_cursor: Annotated[str, Field(max_length=2048)] | None


class LifecycleFinalizationRead(_FrozenSchema):
    """表示pointerだけ。書込資格/署名ではない。"""

    version: PositivePrefixInteger
    event_id: CanonicalUuid = Field(alias="eventId")
    receipt_id: CanonicalUuid = Field(alias="receiptId")


class LifecycleDisplayRead(_FrozenSchema):
    """終了状態は同TX実head/消費印/確定版へ束縛されてから公開される。"""

    format_version: Literal["native-game-lifecycle-read-v1"] = Field(
        alias="formatVersion"
    )
    status: Literal["in_progress", "finished"]
    last_version: DecimalInteger = Field(alias="lastVersion")
    active: LifecycleFinalizationRead | None
    active_stats_version_id: CanonicalUuid | None = Field(alias="activeStatsVersionId")

    @model_validator(mode="after")
    def _binding(self):
        if self.status == "finished":
            if (
                self.active is None
                or self.active_stats_version_id is None
                or self.active.version != self.last_version
            ):
                raise ValueError("終了pointerが最新確定版と不一致")
        elif self.active is not None or self.active_stats_version_id is not None:
            raise ValueError("進行中にactive確定版を返せない")
        return self


class StartedNonplayPrefixGameRead(StartedGameRead):
    """正式CP/三headと有限active履歴。秘密の保存資格は返さない。"""

    read_kind: Literal["nonplay-prefix"]
    status: Literal["in_progress", "finished"]
    lifecycle: LifecycleDisplayRead | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    profile: Literal["nonplay-prefix-read-v1"]
    checkpoint: NonplayCheckpoint
    after: StrikeoutSnapshot
    next_position: PrefixNextPosition
    recovery: PositivePrefixInteger = Field(alias=RECOVERY_WIRE_FIELD)
    page: NonplayActivePage
    append_policy: OrdinaryAppendPolicy
    last_saved_at: Timestamp

    @model_validator(mode="after")
    def _anchor(self):
        """空activeでも実D3/epochを保持し、別試合やbefore偽装を拒否する。"""
        if self.lifecycle is None:
            if self.status != "in_progress":
                raise ValueError("終了状態には真正lifecycle表示が必要")
        elif self.lifecycle.status != self.status:
            raise ValueError("試合statusと終了head表示が不一致")
        c = self.checkpoint.content
        if (
            c.scope.game_id != str(self.id)
            or self.after != c.restored.current
            or int(self.next_position.d1) != int(c.d3) + 1
            or len(self.page.items) > int(c.active_depth)
        ):
            raise ValueError("非play公開CP/位置が不一致")
        return self


StartedGameReadResponse = Annotated[
    StartedGameRead
    | StartedRecordedGameRead
    | StartedRecordedPrefixGameRead
    | StartedPlayPrefixGameRead
    | StartedLineupPrefixGameRead
    | StartedNonplayPrefixGameRead,
    Field(discriminator="read_kind"),
]
"""`read_kind` で判別する記録前後の応答。既存 `initial` の形は変えない。"""
