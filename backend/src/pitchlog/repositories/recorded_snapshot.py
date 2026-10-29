"""唯一のnative初球を開始原典から再評価するR2-A内部計算候補。

物理41列の一致、正式登録、recorded DTO、実HTTP復元の成功は返さない。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

from pitchlog.db.game_state.models import Game
from pitchlog.db.sync_protocol.models import IdempotencyLedger
from pitchlog.domainrt.first_ball_projection import (
    format_first_ball_calculation,
    read_first_ball_calculation,
)
from pitchlog.domainrt.first_pitch import FirstPitchRequest
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    CombinedSuccess,
    _check_frozen_members,
    decode_combined_response,
)
from pitchlog.domainrt.host import NodeDomainHost, open_domain_host
from pitchlog.domainrt.initial_game_roster import (
    InitialGameRosterRequest,
    InitialRosterProjection,
    InitialRosterSuccess,
    decode_initial_roster_response,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.game_start import _saved_start_rule_wire
from pitchlog.repositories.recorded_snapshot_operations import (
    RECORDED_EVENT_COLUMNS,
    RECORDED_PLAY_ROW_COLUMNS,
    RECORDED_SLOT_COLUMNS,
    RecordedEventRowsReadToken,
    RecordedEventSlotsReadToken,
    RecordedPlayRowsReadToken,
)
from pitchlog.repositories.roster import PlayerReadToken, player_read_statement
from pitchlog.repositories.started_snapshot import (
    SavedStartedLineup,
    _initial_before,
    _one,
    _plain,
    _rows,
    _saved_lineup,
    _uuid,
)
from pitchlog.repositories.started_snapshot_operations import (
    LINEUP_COLUMNS,
    StartedLineupsReadToken,
)
from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
from pitchlog.repositories.tokens import ImmutableValue, TenantOperationToken
from pitchlog.repositories.transaction import _TRANSACTION_RUNTIMES, _TenantTransaction
from pitchlog.sync.first_ball_payload import (
    FirstBallParticipants,
    FirstBallPayloadValue,
    read_first_ball_payload,
)
from pitchlog.sync.tokens import (
    GameLockToken,
    GameReadToken,
    IdempotencyLedgerReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
)


class RecordedSnapshotUnavailable(RuntimeError):
    """入力値・原blob・資格を含まない固定の非成功。"""

    def __init__(self) -> None:
        """内部計算候補の未照合を成功として返さない。"""
        super().__init__("保存した初球の計算値を確認できません")


@dataclass(frozen=True, slots=True, repr=False)
class RecordedCalculationCandidate:
    """独立再評価とpayload照合のみ。物理未照合でDTO公開しない。"""

    tenant_id: UUID
    game_id: UUID
    source_event_id: UUID
    d5: UUID
    generation: int
    artifact_sha256: str
    request: CombinedRequest
    response: CombinedSuccess
    roster: InitialRosterProjection
    lineups: tuple[SavedStartedLineup, SavedStartedLineup]
    payload: FirstBallPayloadValue
    unverified_play_row: tuple[ImmutableValue, ...]


def _positive(value: object) -> int:
    """boolを世代番号へ変換しない。"""
    if type(value) is not int or not 0 < value < 2**63:
        raise RecordedSnapshotUnavailable
    return value


def _equal(actual: object, expected: object) -> bool:
    """入れ子のDB値も型込みで比較する。"""
    if type(actual) is not type(expected):
        return False
    if type(actual) is MappingProxyType and type(expected) is MappingProxyType:
        return actual.keys() == expected.keys() and all(
            _equal(actual[k], expected[k]) for k in actual
        )
    if type(actual) is tuple and type(expected) is tuple:
        return len(actual) == len(expected) and all(
            _equal(a, b) for a, b in zip(actual, expected, strict=True)
        )
    return actual == expected


def _same(row: dict[str, Any], expected: dict[str, Any]) -> None:
    """SQL実値を型込みで比較し、Trueと1を等値としない。"""
    if any(not _equal(row[k], v) for k, v in expected.items()):
        raise RecordedSnapshotUnavailable


def _participants(roster: InitialRosterProjection) -> FirstBallParticipants:
    """単一artifactの配置から一意の先頭打者/投手/捕手を抜き出す。"""
    away, home = roster.teams
    batters = [
        p.player.player_id
        for p in away.participants
        if p.batting_slot.kind == "slot" and p.batting_slot.slot == "1"
    ]
    defense = {
        position: [
            p.player.player_id
            for p in home.participants
            if any(r.kind == "fielding" and r.position == position for r in p.roles)
        ]
        for position in ("1", "2")
    }
    if len(batters) != 1 or any(len(v) != 1 for v in defense.values()):
        raise RecordedSnapshotUnavailable
    return FirstBallParticipants(
        batterId=batters[0],
        pitcherId=defense["1"][0],
        catcherId=defense["2"][0],
        battingOrder="1",
    )


def _read_recorded_calculation(
    handle: _TenantTransaction,
    game_id: UUID,
) -> RecordedCalculationCandidate:
    """同handleの開始原典と唯一の保存初球を照合する。実登録はR3が担う。"""
    try:
        if type(handle) is not _TenantTransaction or type(game_id) is not UUID:
            raise RecordedSnapshotUnavailable
        context = handle._context
        tenant = _uuid(handle._bound_tenant_id)
        key = handle._state_key
        runtime = _TRANSACTION_RUNTIMES.get(key)
        lifetime = handle._writer_lifetime()

        def live() -> None:
            """各readと実host呼出しの前後で同scopeを再確認する。"""
            if (
                key is None
                or handle._state_key is not key
                or _TRANSACTION_RUNTIMES.get(key) is not runtime
                or type(context) is not TenantContext
                or handle._context is not context
                or context.tenant_id != tenant
                or handle._bound_tenant_id != tenant
                or handle._bound_integrity_proof != context._integrity_proof
                or not context._has_valid_integrity_proof()
            ):
                raise RecordedSnapshotUnavailable
            now = handle._writer_lifetime()
            if now[0] is not lifetime[0] or now[1] is not lifetime[1]:
                raise RecordedSnapshotUnavailable
            handle._assert_writer_lifetime(lifetime)

        def run(token: TenantOperationToken):
            """自由SQL/別scopeを受けず既宣言だけを同handleで実行する。"""
            live()
            value = handle.run(token)
            live()
            return value

        game_columns = tuple(Game.__table__.c.keys())
        locked = _one(run(GameLockToken(game_id)), game_columns)
        game = _one(run(GameReadToken(game_id)), game_columns)
        _same(locked, game)
        _same(
            game,
            dict(
                tenant_id=tenant,
                id=game_id,
                status="in_progress",
                trashed_at=None,
                hidden_at=None,
                import_batch_id=None,
            ),
        )
        if (
            type(game["started_at"]) is not datetime
            or game["started_at"].utcoffset() is None
        ):
            raise RecordedSnapshotUnavailable
        away, home = (
            _uuid(game[k]) for k in ("away_team_record_id", "home_team_record_id")
        )
        if away == home:
            raise RecordedSnapshotUnavailable
        current = _one(
            run(RecordingGenerationReadToken(game_id)), _GENERATION_READ_COLUMNS
        )
        generation = _positive(current["generation"])
        locked_generation = _one(
            run(RecordingGenerationLockToken(game_id, generation)),
            _GENERATION_READ_COLUMNS,
        )
        _same(locked_generation, current)
        _same(
            current,
            dict(
                tenant_id=tenant,
                game_id=game_id,
                kind="normal",
                revoked_at=None,
                retired_at=None,
                import_batch_id=None,
                confirmed_watermark=1,
                applied_prefix=1,
            ),
        )
        event = _one(run(RecordedEventRowsReadToken(game_id)), RECORDED_EVENT_COLUMNS)
        slot = _one(run(RecordedEventSlotsReadToken(game_id)), RECORDED_SLOT_COLUMNS)
        play = _one(run(RecordedPlayRowsReadToken(game_id)), RECORDED_PLAY_ROW_COLUMNS)
        event_id, d5, row_id = (
            _uuid(event["id"]),
            _uuid(event["d5"]),
            _uuid(play["id"]),
        )
        _same(
            event,
            dict(
                tenant_id=tenant,
                game_id=game_id,
                generation=generation,
                d1=1,
                ledger_kind="accepted",
                event_kind="play_input",
                is_tombstone=False,
                replaced_at=None,
                retired_at=None,
                import_batch_id=None,
                legacy_row_identifier=None,
                migration_unverified=False,
                target_generation=None,
                target_d1=None,
                expected_version=None,
                change_order=None,
            ),
        )
        if type(event["d2"]) is not int or not 0 <= event["d2"] < 2**63:
            raise RecordedSnapshotUnavailable
        _same(
            slot,
            dict(
                tenant_id=tenant,
                game_id=game_id,
                generation=generation,
                d1=1,
                confirmed_version=1,
            ),
        )
        _same(
            play,
            dict(
                tenant_id=tenant,
                game_id=game_id,
                id=row_id,
                source_event_id=event_id,
                play_number=1,
                batting_order=1,
                event_kind="pitch",
                version=1,
                hidden_at=None,
                import_batch_id=None,
                legacy_row_identifier=None,
                migration_unverified=False,
            ),
        )
        ledger = _one(
            run(IdempotencyLedgerReadToken(d5)),
            tuple(IdempotencyLedger.__table__.c.keys()),
        )
        _same(ledger, dict(tenant_id=tenant, d5=d5, kind="accepted", retired_at=None))
        if (
            type(ledger["source_fingerprint"]) is not str
            or re.fullmatch(r"(?:wire-v1:)?[0-9a-f]{64}", ledger["source_fingerprint"])
            is None
        ):
            raise RecordedSnapshotUnavailable
        rows = _rows(run(StartedLineupsReadToken(game_id)), LINEUP_COLUMNS)
        if len(rows) != 2:
            raise RecordedSnapshotUnavailable
        for row in rows:
            _same(row, dict(tenant_id=tenant, game_id=game_id))
        lineups = tuple(_saved_lineup(row) for row in rows)
        if len({x.id for x in lineups}) != 2 or {x.team_id for x in lineups} != {
            away,
            home,
        }:
            raise RecordedSnapshotUnavailable
        sides = tuple(
            next(x for x in lineups if x.team_id == team) for team in (away, home)
        )
        players = set()
        for lineup in sides:
            for entry in lineup.entries:
                identifier = UUID(entry.roster.player_id)
                if identifier in players:
                    raise RecordedSnapshotUnavailable
                players.add(identifier)
                token = PlayerReadToken(
                    1,
                    record_id=identifier,
                    team_record_id=lineup.team_id,
                    include_hidden=True,
                )
                columns = tuple(player_read_statement(token).selected_columns.keys())
                player = _one(run(token), columns)
                _same(player, dict(id=identifier, team_record_id=lineup.team_id))
        rules = _saved_start_rule_wire(_plain(game["applied_rules"]))
        roster_request = InitialGameRosterRequest.model_validate_json(
            json.dumps(
                {
                    "dh": rules.dh,
                    **{
                        name: {
                            "team_id": str(lineup.team_id),
                            "entries": [
                                x.roster.model_dump(mode="json") for x in lineup.entries
                            ],
                        }
                        for name, lineup in zip(("away", "home"), sides, strict=True)
                    },
                }
            ),
            by_alias=True,
            by_name=False,
        )
        # 全履歴exact1/水位1/開始原典確認後にだけ共有の開始beforeを得る。
        request = CombinedRequest(
            t1=FirstPitchRequest(
                eventKind="batting-result",
                resultId="batting-result.ball",
                pitchEventKind="pitch-event",
                before=_initial_before(),
            ),
            rules=rules,
        )
        _check_frozen_members(request)
        with open_domain_host() as host:
            if type(host) is not NodeDomainHost or type(host._source) is not str:
                raise RecordedSnapshotUnavailable
            source = host._source
            digest = hashlib.sha256(source.encode()).hexdigest()
            live()
            roster_result = decode_initial_roster_response(
                host.call(
                    "validateInitialGameRoster",
                    roster_request.model_dump_json(by_alias=True),
                )
            )
            live()
            if (
                type(roster_result) is not InitialRosterSuccess
                or host._source != source
            ):
                raise RecordedSnapshotUnavailable
            response = decode_combined_response(
                host.call(
                    "deriveFirstPitchWithContinuation",
                    request.model_dump_json(by_alias=True),
                )
            )
            live()
            if type(response) is not CombinedSuccess or host._source != source:
                raise RecordedSnapshotUnavailable
        _check_frozen_members(response)
        expected = read_first_ball_calculation(
            format_first_ball_calculation(request, response, artifact_sha256=digest),
            expected_request=request,
            expected_response=response,
            expected_artifact_sha256=digest,
        )
        payload = read_first_ball_payload(
            json.dumps(_plain(event["payload"])),
            json.dumps(_plain(event["state_diff"])),
            expected_calculation=expected,
            expected_participants=_participants(roster_result.value),
        )
        live()
        return RecordedCalculationCandidate(
            tenant,
            game_id,
            event_id,
            d5,
            generation,
            digest,
            request,
            response,
            roster_result.value,
            (sides[0], sides[1]),
            payload,
            tuple(play[k] for k in RECORDED_PLAY_ROW_COLUMNS),
        )
    except (AttributeError, KeyError, ValueError, TypeError, RuntimeError):
        raise RecordedSnapshotUnavailable from None


@dataclass(frozen=True, slots=True)
class RecordedSnapshotNotAvailable:
    """保存初球の前提を満たさない（2球目以降・訂正・墓標・失効世代など）。

    呼出側に例外分岐を置かず、記録後readの「内容を返さない」閉じた結果へ
    写すための値。破損と区別せず、推測で状態を補わない。
    """


def try_read_recorded_snapshot(
    handle: _TenantTransaction,
    game_id: UUID,
) -> RecordedCalculationCandidate | RecordedSnapshotNotAvailable:
    """保存初球の再評価を試み、前提不成立だけを閉じた値で返す。

    例外は本module内で閉じる。呼出側（``started_read``）は値の種類だけで
    分岐し、例外節から応答種別を返さない。

    Args:
        handle: 呼出元が所有する生存中の同一TX。
        game_id: 対象試合のUUID。

    Returns:
        候補、または前提不成立を表す閉じた値。
    """
    try:
        return _read_recorded_calculation(handle, game_id)
    except RecordedSnapshotUnavailable:
        return RecordedSnapshotNotAvailable()
