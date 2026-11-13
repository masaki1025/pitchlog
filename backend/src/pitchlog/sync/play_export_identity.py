"""実play writerの同一transactionからCSV表示原本を採取する。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select

from pitchlog.db.game_state.models import Game, GameLineup, PlayRow, PlayRunner
from pitchlog.db.tenant_isolation.models import (
    AdminVocabulary,
    Player,
    SystemVocabulary,
    TeamRecord,
    TenantVocabulary,
)
from pitchlog.exports.generated.coordinate_transform import course_screen
from pitchlog.sync import stats_native_flush
from pitchlog.sync.stats_native_hook import _NativeStatsSource


class PlayExportIdentityUnavailable(RuntimeError):
    """現行原本を過去又は他tenantの表示値で補えない。"""


@dataclass(frozen=True, slots=True, repr=False)
class RecordedPlayIdentity:
    """同一writerの一時表示原本。保存receiptの代わりにはしない。"""

    source: _NativeStatsSource
    game: dict[str, Any]
    play: dict[str, Any]
    lineups: tuple[dict[str, Any], dict[str, Any]]
    players: tuple[dict[str, Any], ...]
    teams: tuple[dict[str, Any], dict[str, Any]]
    tenant_vocabularies: tuple[dict[str, Any], ...]
    admin_vocabularies: tuple[dict[str, Any], ...]
    system_vocabulary: dict[str, Any]
    payload: dict[str, Any]
    course_screen: tuple[str | None, str | None]
    accepted_server_at: datetime
    runners: tuple[dict[str, Any], ...] = ()


def _course_screen(
    payload: dict[str, Any], play: dict[str, Any] | None = None
) -> tuple[str | None, str | None]:
    """受理済V7の正準k、又は非投球の未観測を保存行へ照合する。"""
    observations = payload.get("observations")
    if play is not None and play.get("event_kind") == "non_pitch":
        if type(observations) is dict and observations.get("kind") == "non-pitch-event":
            from pitchlog.domainrt.lineup_play_prefix_continuation import (
                RunnerEventT1Input,
            )
            from pitchlog.sync.terminal_pitch_payload import (
                LineupPitchPlayPayload,
                RunnerNonpitchPlayObservations,
            )

            try:
                raw = json.dumps(payload, allow_nan=False, sort_keys=True)
                parsed = LineupPitchPlayPayload.model_validate_json(raw)
                if (
                    json.dumps(
                        parsed.model_dump(
                            mode="json", by_alias=True, exclude_unset=True
                        ),
                        sort_keys=True,
                    )
                    != raw
                ):
                    raise PlayExportIdentityUnavailable
                request = parsed.calculation.request
                if (
                    type(parsed.observations) is not RunnerNonpitchPlayObservations
                    or type(request.t1) is not RunnerEventT1Input
                ):
                    raise PlayExportIdentityUnavailable
                original = request.t1.runner_observation
                p = original.per_pitch
                if (
                    parsed.observations.runner_observation != original
                    or original.primary_result_id is not None
                    or request.t1.pitch_event_kind != "non-pitch-event"
                ):
                    raise PlayExportIdentityUnavailable
                if any(
                    column not in play or play[column] is not None
                    for column in (
                        "course_x",
                        "course_y",
                        "pitch_type_key",
                        "pitch_speed",
                        "stance",
                        "batting_side",
                    )
                ):
                    raise PlayExportIdentityUnavailable
                if play["batting_result_key"] is not None:
                    raise PlayExportIdentityUnavailable
                if p.kind == "secondary-result":
                    if (
                        p.result_id != "secondary-result.balk"
                        or play["secondary_batting_result_key"] != p.result_id
                    ):
                        raise PlayExportIdentityUnavailable
                elif p.kind == "runner-event":
                    event = getattr(p.runner_event_payload, "event_kind", None)
                    if (
                        p.result_id != event
                        or play["secondary_batting_result_key"] is not None
                    ):
                        raise PlayExportIdentityUnavailable
                else:
                    raise PlayExportIdentityUnavailable
                return None, None
            except (ValueError, KeyError, TypeError):
                raise PlayExportIdentityUnavailable from None
        try:
            if (
                payload["formatVersion"] != "play-prefix-play-v3"
                or observations != {"kind": "intentional-walk"}
                or payload["calculation"]["request"]["t1"]["pitchEventKind"]
                != "non-pitch-event"
                or payload["calculation"]["request"]["t1"]["resultId"]
                != "batting-result.intentional-walk"
                or play["batting_result_key"] != "batting-result.intentional-walk"
                or play["course_x"] is not None
                or play["course_y"] is not None
            ):
                raise PlayExportIdentityUnavailable
        except (KeyError, TypeError):
            raise PlayExportIdentityUnavailable from None
        return None, None
    if (play is not None and play.get("event_kind") != "pitch") or observations == {
        "kind": "intentional-walk"
    }:
        raise PlayExportIdentityUnavailable
    if type(observations) is not dict or type(observations.get("course")) is not dict:
        raise PlayExportIdentityUnavailable
    course = observations["course"]
    if set(course) != {"x", "y", "unit"}:
        raise PlayExportIdentityUnavailable
    try:
        return course_screen(course["x"], course["y"], course["unit"])
    except ValueError:
        raise PlayExportIdentityUnavailable from None


def _rows(scope, statement, maximum: int) -> tuple[dict[str, Any], ...]:
    """既Sessionのtenant限定SELECTを上限+1で閉じる。"""
    result = scope.session.execute(statement.limit(maximum + 1)).mappings()
    rows = tuple(dict(row) for row in result)
    if len(rows) > maximum:
        raise PlayExportIdentityUnavailable
    return rows


def _player_ids(payload: dict[str, Any], lineups, play) -> frozenset[UUID]:
    """V7の固定参照欄と開始保存名簿だけから選手集合を取る。"""
    identifiers = {
        value
        for key in ("batter_id", "pitcher_id", "catcher_id")
        if (value := play.get(key)) is not None
    }
    for lineup in lineups:
        entries = lineup.get("entries_with_uniform_number_snapshot")
        if type(entries) is not list or not 9 <= len(entries) <= 10:
            raise PlayExportIdentityUnavailable
        for entry in entries:
            if type(entry) is not dict or type(entry.get("player_id")) is not str:
                raise PlayExportIdentityUnavailable
            identifiers.add(UUID(entry["player_id"]))
    people = payload.get("participants")
    if type(people) is not dict:
        raise PlayExportIdentityUnavailable
    for key in ("batterId", "pitcherId", "catcherId"):
        if type(people.get(key)) is not str:
            raise PlayExportIdentityUnavailable
        identifiers.add(UUID(people[key]))
    calculation = payload.get("calculation")
    if type(calculation) is not dict or type(calculation.get("request")) is not dict:
        raise PlayExportIdentityUnavailable
    source = calculation["request"].get("source")
    if source is not None:
        if type(source) is not dict:
            raise PlayExportIdentityUnavailable
        current_lineup = source.get("lineup")
        if current_lineup is not None:
            if type(current_lineup) is not dict or set(current_lineup) != {
                "away",
                "home",
            }:
                raise PlayExportIdentityUnavailable
            for side in ("away", "home"):
                team = current_lineup[side]
                if type(team) is not dict or type(team.get("battingOrder")) is not dict:
                    raise PlayExportIdentityUnavailable
                for identifier in team["battingOrder"].values():
                    if type(identifier) is not str:
                        raise PlayExportIdentityUnavailable
                    identifiers.add(UUID(identifier))
                for key in ("pitcherId", "catcherId"):
                    if type(team.get(key)) is not str:
                        raise PlayExportIdentityUnavailable
                    identifiers.add(UUID(team[key]))
        runners = source.get("runners")
        if runners is not None:
            if type(runners) is not list or len(runners) > 3:
                raise PlayExportIdentityUnavailable
            for runner in runners:
                if type(runner) is not dict:
                    raise PlayExportIdentityUnavailable
                for key in ("runnerId", "responsiblePitcherId"):
                    if type(runner.get(key)) is not str:
                        raise PlayExportIdentityUnavailable
                    identifiers.add(UUID(runner[key]))
    if len(identifiers) > 64 or any(type(value) is not UUID for value in identifiers):
        raise PlayExportIdentityUnavailable
    return frozenset(identifiers)


def capture_recorded_play_identity(scope, receipt, source) -> RecordedPlayIdentity:
    """資格のある同TXから試合・play・名簿・実名を有限取得する。

    Args:
        scope: 成績保存と同じ真正writer scope。
        receipt: 同じframeの一回消費済みprivate receipt。
        source: 実V7と保存eventへ束縛済みのsource。

    Returns:
        後段88列producerへ渡す同TX保存原本。

    Raises:
        PlayExportIdentityUnavailable: 欠測・越境・source不一致の場合。
    """
    try:
        if type(source) is not _NativeStatsSource:
            raise PlayExportIdentityUnavailable
        # 呼出元のpersist_accepted_play_exportが直前に_assert_scopeを完了している。
        tenant = source.tenant_id
        game_rows = _rows(
            scope,
            select(*Game.__table__.c).where(
                Game.__table__.c.tenant_id == tenant,
                Game.__table__.c.id == source.game_id,
                Game.__table__.c.import_batch_id.is_(None),
            ),
            1,
        )
        play_rows = _rows(
            scope,
            select(*PlayRow.__table__.c).where(
                PlayRow.__table__.c.tenant_id == tenant,
                PlayRow.__table__.c.game_id == source.game_id,
                PlayRow.__table__.c.source_event_id == source.source_event_id,
                PlayRow.__table__.c.hidden_at.is_(None),
            ),
            1,
        )
        lineup_rows = _rows(
            scope,
            select(*GameLineup.__table__.c).where(
                GameLineup.__table__.c.tenant_id == tenant,
                GameLineup.__table__.c.game_id == source.game_id,
            ),
            2,
        )
        if len(game_rows) != 1 or len(play_rows) != 1 or len(lineup_rows) != 2:
            raise PlayExportIdentityUnavailable
        game, play = game_rows[0], play_rows[0]
        runner_rows = _rows(
            scope,
            select(*PlayRunner.__table__.c).where(
                PlayRunner.__table__.c.tenant_id == tenant,
                PlayRunner.__table__.c.play_id == play["id"],
                PlayRunner.__table__.c.retired_at.is_(None),
            ),
            3,
        )
        if len({row["base"] for row in runner_rows}) != len(runner_rows):
            raise PlayExportIdentityUnavailable
        if (
            game["hidden_at"] is not None
            or game["trashed_at"] is not None
            or play["version"] != 1
            or type(play["id"]) is not UUID
        ):
            raise PlayExportIdentityUnavailable
        team_ids = (game["away_team_record_id"], game["home_team_record_id"])
        if (
            any(type(value) is not UUID for value in team_ids)
            or team_ids[0] == team_ids[1]
            or {row["team_record_id"] for row in lineup_rows} != set(team_ids)
        ):
            raise PlayExportIdentityUnavailable
        payload = json.loads(source.native_payload_json)
        if type(payload) is not dict:
            raise PlayExportIdentityUnavailable
        screen = _course_screen(payload, play)
        clock = _rows(scope, select(func.clock_timestamp().label("accepted_at")), 1)
        if (
            len(clock) != 1
            or type(clock[0].get("accepted_at")) is not datetime
            or clock[0]["accepted_at"].tzinfo is None
        ):
            raise PlayExportIdentityUnavailable
        player_ids = _player_ids(payload, lineup_rows, play)
        players = _rows(
            scope,
            select(*Player.__table__.c).where(
                Player.__table__.c.tenant_id == tenant,
                Player.__table__.c.id.in_(player_ids),
            ),
            64,
        )
        teams = _rows(
            scope,
            select(*TeamRecord.__table__.c).where(
                TeamRecord.__table__.c.tenant_id == tenant,
                TeamRecord.__table__.c.id.in_(team_ids),
            ),
            2,
        )
        tenant_keys = {
            value
            for key in (
                "strategy_key",
                "strategy_detail_key",
                "strategy_result_key",
                "pitch_type_key",
            )
            if (value := play.get(key)) is not None
        }
        tenant_keys.add(game["tournament_key"])
        admin_keys = {
            value
            for key in (
                "batting_result_key",
                "secondary_batting_result_key",
                "batted_ball_type",
                "batted_ball_strength",
            )
            if (value := play.get(key)) is not None
        }
        tenant_vocabulary = _rows(
            scope,
            select(*TenantVocabulary.__table__.c).where(
                TenantVocabulary.__table__.c.tenant_id == tenant,
                TenantVocabulary.__table__.c.key.in_(tenant_keys),
            ),
            5,
        )
        admin_vocabulary = _rows(
            scope,
            select(*AdminVocabulary.__table__.c).where(
                AdminVocabulary.__table__.c.key.in_(admin_keys),
            ),
            4,
        )
        system_vocabulary = _rows(
            scope,
            select(*SystemVocabulary.__table__.c).where(
                SystemVocabulary.__table__.c.key == game["game_type_key"],
                SystemVocabulary.__table__.c.category == "game_type",
            ),
            1,
        )
        if (
            {row["id"] for row in players} != player_ids
            or any(row["runner_id"] not in player_ids for row in runner_rows)
            or {row["id"] for row in teams} != set(team_ids)
            or {row["key"] for row in tenant_vocabulary} != tenant_keys
            or {row["key"] for row in admin_vocabulary} != admin_keys
            or len(system_vocabulary) != 1
        ):
            raise PlayExportIdentityUnavailable
        stats_native_flush._assert_scope(scope, receipt, source)
        return RecordedPlayIdentity(
            source,
            game,
            play,
            lineup_rows,
            players,
            cast(tuple[dict[str, Any], dict[str, Any]], teams),
            tenant_vocabulary,
            admin_vocabulary,
            system_vocabulary[0],
            payload,
            screen,
            clock[0]["accepted_at"],
            runner_rows,
        )
    except (KeyError, TypeError, ValueError, LookupError):
        raise PlayExportIdentityUnavailable from None
