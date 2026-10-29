"""開始済み試合の再取得入力を、同一TX・同一lock順で組み立てる。

既存の0球reader(``read_initial_started_snapshot``)を改変せず、その前に
不可視(404)・記録あり(409)・破損(503)を値の種類で振り分ける。認証・現在権利・
書込許可の証明は返さない。lock順は games の行 → 記録権世代の行である。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pitchlog.db.game_state.models import Game
from pitchlog.db.game_state.rule_snapshot import (
    decode_applied_rules,
    encode_applied_rules,
)
from pitchlog.domainrt.first_pitch import StateSnapshot
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.repositories.recorded_snapshot import (
    RecordedCalculationCandidate,
    try_read_recorded_snapshot,
)
from pitchlog.repositories.started_snapshot import (
    SavedStartedLineup,
    StartedSnapshotUnavailable,
    _one,
    _plain,
    _rows,
    read_initial_started_snapshot,
)
from pitchlog.repositories.started_snapshot_operations import (
    StartedEventSlotsExistenceToken,
    StartedOperationEventsExistenceToken,
    StartedPlayRowsExistenceToken,
)
from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.d4_reference import encode_d4_reference
from pitchlog.sync.tokens import (
    GameLockToken,
    GameReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
)


class StartedReadCorrupt(Exception):
    """保存原本の不整合。値や原因を含まない固定の非成功。

    値で返さず例外として送出する。呼出側の ``with`` を例外つきで抜けさせ、
    確定の経路へ進ませないためである。
    """

    def __init__(self) -> None:
        """原例外・DB値・入力値を持たない固定外形を作る。"""
        super().__init__("開始済み試合を確認できません")


@dataclass(frozen=True, slots=True)
class StartedReadNotVisible:
    """不存在・別tenant・不可視・開始済みでない試合。理由を区別しない。"""


@dataclass(frozen=True, slots=True)
class StartedReadRecorded:
    """記録が始まった試合。記録後の内容はここでは返さない。"""


@dataclass(frozen=True, slots=True)
class StartedGameView:
    """同じTX・ロック下で読んだ開始済み試合の確定値。権利の証明ではない。"""

    game_id: UUID
    scheduled_at: datetime
    game_type_key: str
    tournament_key: str
    away_team_record_id: UUID
    home_team_record_id: UUID
    plate_umpire: str | None
    section_label: str | None
    week_label: str | None
    day_label: str | None
    game_number_label: str | None
    started_at: datetime
    applied_rules: dict[str, object]
    lineups: tuple[SavedStartedLineup, SavedStartedLineup]
    roster: InitialRosterProjection
    before: StateSnapshot
    current_d4: str


@dataclass(frozen=True, slots=True)
class StartedRecordedView:
    """記録後も同じTX・ロック順で読んだ、保存初球の独立再評価値。

    先頭1球だけを対象とし、前提を満たさない記録では生成しない。保持者・資格・
    証明・D3は返さない（権利や同期済みの証明ではない）。``history``/``stat_flags``/
    ``t2``/``play_row`` は保存初球の閉値をそのまま保持し、再計算しない。
    """

    game_id: UUID
    scheduled_at: datetime
    game_type_key: str
    tournament_key: str
    away_team_record_id: UUID
    home_team_record_id: UUID
    plate_umpire: str | None
    section_label: str | None
    week_label: str | None
    day_label: str | None
    game_number_label: str | None
    started_at: datetime
    applied_rules: dict[str, object]
    lineups: tuple[SavedStartedLineup, SavedStartedLineup]
    roster: InitialRosterProjection
    after: StateSnapshot
    history: tuple[object, ...]
    stat_flags: object
    t2: object
    play_row: tuple[object, ...]
    current_d4: str


StartedReadResult = (
    StartedGameView | StartedRecordedView | StartedReadNotVisible | StartedReadRecorded
)


def read_started_game(handle: _TenantTransaction, game_id: UUID) -> StartedReadResult:
    """開始済み試合を振り分けて返す。新しいSession・TXは開かない。

    Args:
        handle: ``tenant_transaction_scope`` が返した生存中のTX。
        game_id: 対象試合のUUID。tenantはhandleからのみ得る。

    Returns:
        成功は値、不可視と記録ありは閉じた型の値。

    Raises:
        StartedReadCorrupt: 保存原本の不整合、未登録操作、scope失効のとき。
    """
    try:
        return _assemble(handle, game_id)
    except (StartedSnapshotUnavailable, ValueError, TypeError, KeyError, RuntimeError):
        raise StartedReadCorrupt from None


def _assemble(handle: _TenantTransaction, game_id: UUID) -> StartedReadResult:
    """lock順を守って読み、不可視・記録あり・成功へ振り分ける。"""
    if type(handle) is not _TenantTransaction or type(game_id) is not UUID:
        raise StartedReadCorrupt
    tenant = getattr(handle, "_bound_tenant_id", None)
    state_key = getattr(handle, "_state_key", None)
    if type(tenant) is not UUID or state_key is None:
        raise StartedReadCorrupt

    def run(operation: TenantOperationToken) -> TenantOperationResult:
        """各readの前後で同じwriterキーとtenantを保持する。"""
        if handle._state_key is not state_key or handle._bound_tenant_id != tenant:
            raise StartedReadCorrupt
        value = handle.run(operation)
        if handle._state_key is not state_key or handle._bound_tenant_id != tenant:
            raise StartedReadCorrupt
        return value

    # (1) games の行を lock してから同じ行を読む。0行は別tenant・不存在。
    columns = tuple(Game.__table__.c.keys())
    locked_rows = _rows(run(GameLockToken(game_id)), columns)
    read_rows = _rows(run(GameReadToken(game_id)), columns)
    if not locked_rows and not read_rows:
        return StartedReadNotVisible()
    if len(locked_rows) != 1 or locked_rows != read_rows:
        raise StartedReadCorrupt
    game = read_rows[0]
    if game["tenant_id"] != tenant or game["id"] != game_id:
        raise StartedReadCorrupt

    # (2) 不可視の条件は0球readerの4条件と同一。以後のSQLは実行しない。
    if (
        game["status"] != "in_progress"
        or game["trashed_at"] is not None
        or game["hidden_at"] is not None
        or game["import_batch_id"] is not None
    ):
        return StartedReadNotVisible()

    # (3) 現在の記録権世代を読み、同じ行を lock する。無い・食い違うは破損。
    current = _one(run(RecordingGenerationReadToken(game_id)), _GENERATION_READ_COLUMNS)
    number = current["generation"]
    if type(number) is not int or not 0 < number <= 2**63 - 1:
        raise StartedReadCorrupt
    locked = _one(
        run(RecordingGenerationLockToken(game_id, number)), _GENERATION_READ_COLUMNS
    )
    if current != locked:
        raise StartedReadCorrupt

    # (4) 記録ありは0球readerより先に判定する。1件でも行があれば記録後。
    recorded = False
    for token_type in (
        StartedEventSlotsExistenceToken,
        StartedOperationEventsExistenceToken,
        StartedPlayRowsExistenceToken,
    ):
        if _rows(run(token_type(game_id)), ("game_id",)):
            recorded = True
            break
    if recorded:
        # 保存初球だけを同じhandle・同じロック順で独立再評価する。前提を満たさ
        # ない記録（2球目以降・訂正・墓標・失効世代）は、リーダーが返す閉じた値
        # で「内容を返さない」結果へ写す（例外節から応答種別を返さない）。
        candidate = try_read_recorded_snapshot(handle, game_id)
        if type(candidate) is not RecordedCalculationCandidate:
            return StartedReadRecorded()
        if (
            candidate.tenant_id != tenant
            or candidate.game_id != game_id
            or candidate.generation != number
        ):
            raise StartedReadCorrupt
        return StartedRecordedView(
            game_id=game_id,
            scheduled_at=game["scheduled_at"],
            game_type_key=game["game_type_key"],
            tournament_key=game["tournament_key"],
            away_team_record_id=game["away_team_record_id"],
            home_team_record_id=game["home_team_record_id"],
            plate_umpire=game["plate_umpire"],
            section_label=game["section_label"],
            week_label=game["week_label"],
            day_label=game["day_label"],
            game_number_label=game["game_number_label"],
            started_at=game["started_at"],
            applied_rules=encode_applied_rules(
                decode_applied_rules(_plain(game["applied_rules"]))
            ),
            lineups=candidate.lineups,
            roster=candidate.roster,
            after=candidate.response.value.t1.after,
            history=tuple(candidate.response.value.t1.history_context),
            stat_flags=candidate.response.value.t1.stat_flags,
            t2=candidate.response.value.t2,
            play_row=tuple(candidate.unverified_play_row),
            current_d4=encode_d4_reference(tenant, game_id, candidate.generation),
        )

    # (5) 0球readerを改変せず呼ぶ。その拒否は不可視でなく破損として扱う。
    snapshot = read_initial_started_snapshot(handle, game_id)
    if (
        snapshot.tenant_id != tenant
        or snapshot.game_id != game_id
        or snapshot.started_at != game["started_at"]
    ):
        raise StartedReadCorrupt
    rules = encode_applied_rules(
        decode_applied_rules(json.loads(snapshot.saved_rules_json))
    )
    return StartedGameView(
        game_id=game_id,
        scheduled_at=game["scheduled_at"],
        game_type_key=game["game_type_key"],
        tournament_key=game["tournament_key"],
        away_team_record_id=game["away_team_record_id"],
        home_team_record_id=game["home_team_record_id"],
        plate_umpire=game["plate_umpire"],
        section_label=game["section_label"],
        week_label=game["week_label"],
        day_label=game["day_label"],
        game_number_label=game["game_number_label"],
        started_at=snapshot.started_at,
        applied_rules=rules,
        lineups=snapshot.lineups,
        roster=snapshot.roster,
        before=snapshot.before,
        current_d4=encode_d4_reference(
            snapshot.tenant_id, snapshot.game_id, snapshot.generation
        ),
    )
