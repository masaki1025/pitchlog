"""同TXで捕捉した保存原本の参照欄だけを88列へ写す。"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID

from pitchlog.db.game_state.models import PlayRow
from pitchlog.exports.generated.coordinate_transform import (
    fielding_position_label,
    plate_result_display,
    server_accepted_elapsed,
)
from pitchlog.exports.generated.play_export_completion import saved_half_completed
from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.sync.play_export_identity import RecordedPlayIdentity


class RecordedExportProjectionUnavailable(ValueError):
    """保存NULLと原本欠測を区別して非成功にする。"""


_JST = timezone(timedelta(hours=9), "JST")
_HEADER = CSV_HEADERS["plays.csv"]
_DIRECT = frozenset({9, 26, 39, 41, 47, 52, 53, 54, 55, 57, 58, 60})
_TENANT_VOCAB = {
    29: "strategy_key",
    30: "strategy_detail_key",
    31: "strategy_result_key",
    44: "pitch_type_key",
}
_ADMIN_VOCAB = {
    45: "batting_result_key",
    46: "secondary_batting_result_key",
    48: "batted_ball_type",
    49: "batted_ball_strength",
}
_NAT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def _text(value: Any) -> str | None:
    """保存済み有限scalarだけを文字列化し、欠測は補わない。"""
    if value is None:
        return None
    if type(value) is str:
        if "\x00" in value:
            raise RecordedExportProjectionUnavailable
        return value
    if type(value) is int:
        return str(value)
    raise RecordedExportProjectionUnavailable


def _lookup(rows: tuple[dict[str, Any], ...], key: Any) -> str | None:
    """記録時に捕捉した同tenant語彙の表示名だけを使う。"""
    if key is None:
        return None
    matches = [row for row in rows if row.get("key") == key]
    if len(matches) != 1 or type(matches[0].get("display_name")) is not str:
        raise RecordedExportProjectionUnavailable
    return matches[0]["display_name"]


def _player(identity: RecordedPlayIdentity, identifier: Any) -> dict[str, Any]:
    """現時点DBを再取得せず、今回捕捉した一意選手だけを読む。"""
    if type(identifier) is not UUID:
        raise RecordedExportProjectionUnavailable
    matches = [row for row in identity.players if row.get("id") == identifier]
    if len(matches) != 1:
        raise RecordedExportProjectionUnavailable
    return matches[0]


def _team(identity: RecordedPlayIdentity, identifier: Any) -> str:
    """記録時の同tenant二チーム以外を表示名へ拡張しない。"""
    if type(identifier) is not UUID:
        raise RecordedExportProjectionUnavailable
    matches = [row for row in identity.teams if row.get("id") == identifier]
    if len(matches) != 1 or type(matches[0].get("name")) is not str:
        raise RecordedExportProjectionUnavailable
    return matches[0]["name"]


def _starting_entry(identity: RecordedPlayIdentity, identifier: UUID) -> dict[str, Any]:
    """開始時保存名簿で選手/番号/守備roleを一意に照合する。"""
    matches = [
        entry
        for lineup in identity.lineups
        for entry in lineup["entries_with_uniform_number_snapshot"]
        if entry["player_id"] == str(identifier)
    ]
    if len(matches) != 1:
        raise RecordedExportProjectionUnavailable
    return matches[0]


def _recorded_context(
    identity: RecordedPlayIdentity,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
    """v3直系と非play真正CPの保存時文脈を同じ入口で読む。"""
    try:
        source = identity.payload["calculation"]["request"].get("source")
        if type(source) is not dict:
            return None, None
        if source.get("formatVersion") == "nonplay-prefix-source-v1":
            content = source["checkpoint"]["content"]
            scope = content["scope"]
            if scope["tenantId"] != str(identity.source.tenant_id) or scope[
                "gameId"
            ] != str(identity.source.game_id):
                raise RecordedExportProjectionUnavailable
            restored = content["restored"]
            lineup, runners = restored["lineup"], restored["runners"]
        else:
            lineup, runners = source.get("lineup"), source.get("runners")
        if lineup is None:
            return None, None
        if type(lineup) is not dict or type(runners) is not list:
            raise RecordedExportProjectionUnavailable
        return lineup, runners
    except (KeyError, TypeError):
        raise RecordedExportProjectionUnavailable from None


def _recorded_entry(
    identity: RecordedPlayIdentity,
    identifier: UUID,
    substitutes: dict[UUID, dict[str, Any]],
) -> dict[str, Any]:
    """開始名簿と受理交代の記録時snapshotを混同しない。"""
    if identifier not in substitutes:
        return _starting_entry(identity, identifier)
    snapshot = substitutes[identifier]
    player = _player(identity, identifier)
    if (
        type(snapshot) is not dict
        or type(snapshot.get("event_id")) is not UUID
        or type(snapshot.get("d2")) is not int
        or snapshot["d2"] >= identity.source.d2
        or snapshot.get("name") != player.get("name")
        or snapshot.get("uniform_number_snapshot") != player.get("uniform_number")
        or snapshot.get("side") not in ("away", "home")
    ):
        raise RecordedExportProjectionUnavailable
    current, runners = _recorded_context(identity)
    if current is None or runners is None:
        raise RecordedExportProjectionUnavailable
    side = snapshot["side"]
    lineup = current.get(side)
    if type(lineup) is not dict or lineup.get("teamId") != str(
        identity.game[f"{side}_team_record_id"]
    ):
        raise RecordedExportProjectionUnavailable
    active = set(lineup.get("battingOrder", {}).values()) | {
        lineup.get("pitcherId"),
        lineup.get("catcherId"),
    }
    active.update(row.get("runnerId") for row in runners if type(row) is dict)
    if str(identifier) not in active:
        raise RecordedExportProjectionUnavailable
    operation = snapshot.get("operation")
    if type(operation) is not dict or operation.get("side") != side:
        raise RecordedExportProjectionUnavailable
    kind = snapshot.get("kind")
    role: dict[str, Any] | None = None
    if kind == "pitcher":
        role = {"kind": "fielding", "position": 1}
    elif kind == "defense":
        changes = operation.get("changes")
        matches = (
            [row for row in changes if row.get("incomingId") == str(identifier)]
            if type(changes) is list
            else []
        )
        if len(matches) != 1 or matches[0].get("position") not in tuple("123456789"):
            raise RecordedExportProjectionUnavailable
        role = {"kind": "fielding", "position": int(matches[0]["position"])}
    elif kind not in ("pinch-hitter", "pinch-runner"):
        raise RecordedExportProjectionUnavailable
    return {
        "player_id": str(identifier),
        "uniform_number_snapshot": snapshot["uniform_number_snapshot"],
        "fielding_position": role,
    }


def _saved_fielding_role(role: Any) -> dict[str, str]:
    """開始名簿の保存整数roleをD-1生成targetの正準文字列ABIへ写す。"""
    if type(role) is not dict:
        raise RecordedExportProjectionUnavailable
    if role == {"kind": "designated-hitter"}:
        return {"kind": "designated-hitter"}
    if (
        set(role) != {"kind", "position"}
        or role["kind"] != "fielding"
        or type(role["position"]) is not int
        or not 1 <= role["position"] <= 9
    ):
        raise RecordedExportProjectionUnavailable
    return {"kind": "fielding", "position": str(role["position"])}


def _starting_lineup_columns(identity: RecordedPlayIdentity) -> dict[str, str | None]:
    """記録の最初のplayだけに開始時名簿配列を全値で保存する。"""
    if identity.play["play_number"] != 1:
        return {_HEADER[index]: None for index in range(78, 86)}
    output: dict[str, str | None] = {}
    try:
        for side, first in (("away", 78), ("home", 82)):
            team_id = identity.game[f"{side}_team_record_id"]
            matching = [
                row for row in identity.lineups if row["team_record_id"] == team_id
            ]
            if len(matching) != 1:
                raise RecordedExportProjectionUnavailable
            raw_entries = matching[0]["entries_with_uniform_number_snapshot"]
            if (
                type(raw_entries) is not list
                or len(raw_entries) not in (9, 10)
                or any(type(entry) is not dict for entry in raw_entries)
            ):
                raise RecordedExportProjectionUnavailable
            entries = cast(list[dict[str, Any]], raw_entries)
            if any(
                type(entry.get("batting_order")) not in (int, type(None))
                or (
                    type(entry.get("batting_order")) is int
                    and not 1 <= entry["batting_order"] <= 9
                )
                for entry in entries
            ):
                raise RecordedExportProjectionUnavailable
            order = sorted(
                entries,
                key=lambda entry: (
                    entry["batting_order"] is None,
                    entry["batting_order"] or 0,
                ),
            )
            if [entry["batting_order"] for entry in order[:9]] != [
                value for value in range(1, 10)
            ]:
                raise RecordedExportProjectionUnavailable
            poses, names, nums, lrs = [], [], [], []
            for entry in order:
                player = _player(identity, UUID(entry["player_id"]))
                poses.append(
                    fielding_position_label(
                        _saved_fielding_role(entry["fielding_position"])
                    )
                )
                names.append(_text(player["name"]))
                nums.append(_text(entry["uniform_number_snapshot"]))
                lrs.append(_text(player["bats"]))
            for index, values in enumerate((poses, names, nums, lrs)):
                output[_HEADER[first + index]] = json.dumps(
                    values, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                )
        return output
    except (KeyError, TypeError, ValueError):
        raise RecordedExportProjectionUnavailable from None


def _native_before(payload: dict[str, Any]) -> dict[str, str]:
    """記録時の保存T1 beforeを列10–16へ直写しする。"""
    try:
        before = payload["calculation"]["request"]["t1"]["before"]["stateFields"]
        if type(before) is not dict:
            raise RecordedExportProjectionUnavailable
        half = before["state.half"]
        score = before["state.score"]
        if (
            half not in ("top", "bottom")
            or type(score) is not dict
            or set(score) != {"away", "home"}
        ):
            raise RecordedExportProjectionUnavailable
        fields = (
            before["state.inning"],
            score["away"],
            score["home"],
            before["state.count.strikes"],
            before["state.count.balls"],
            before["state.outs"],
        )
        if any(
            type(value) is not str or _NAT.fullmatch(value) is None for value in fields
        ):
            raise RecordedExportProjectionUnavailable
        result = {
            _HEADER[10]: fields[0],
            _HEADER[11]: "表" if half == "top" else "裏",
            _HEADER[12]: fields[1],
            _HEADER[13]: fields[2],
            _HEADER[14]: fields[3],
            _HEADER[15]: fields[4],
            _HEADER[16]: fields[5],
        }
        orders = payload["calculation"]["request"]["t1"]["before"].get(
            "battingOrderBySide"
        )
        if payload.get("formatVersion") == "play-prefix-play-v3":
            if (
                type(orders) is not dict
                or set(orders) != {"away", "home"}
                or any(
                    type(value) is not str or _NAT.fullmatch(value) is None
                    for value in orders.values()
                )
            ):
                raise RecordedExportProjectionUnavailable
            result[_HEADER[73]] = orders["away"]
            result[_HEADER[74]] = orders["home"]
        elif payload.get("formatVersion") in (
            "first-ball-play-v1",
            "ordinary-pitch-play-v1",
            "play-prefix-play-v2",
        ):
            # 旧prefixの第一回表のみ。開始原典は両側1で、裏の打順は未進行。
            # 他回/裏のv2で両側値を推測してはならない。
            active = before["state.battingOrder"]
            if (
                half != "top"
                or before["state.inning"] != "1"
                or type(active) is not str
                or re.fullmatch(r"[1-9]", active) is None
            ):
                raise RecordedExportProjectionUnavailable
            result[_HEADER[73]] = active
            result[_HEADER[74]] = "1"
        else:
            raise RecordedExportProjectionUnavailable
        return result
    except (KeyError, TypeError):
        raise RecordedExportProjectionUnavailable from None


def _native_completion(payload: dict[str, Any]) -> dict[str, str]:
    """保存T1/T2の確定フラグを旧表示語へ写す。"""
    try:
        value = payload["calculation"]["response"]["value"]
        t1 = value["t1"]
        pa_ended = t1["plateAppearanceEnded"]
        half_completed = saved_half_completed(payload)
        game_ended = t1["after"]["stateFields"]["state.gameEnded"]
        if any(
            type(flag) is not bool for flag in (pa_ended, half_completed, game_ended)
        ):
            raise RecordedExportProjectionUnavailable
        return {
            _HEADER[17]: "打席完了" if pa_ended else "打席継続",
            _HEADER[18]: (
                "試合終了"
                if game_ended
                else "イニング開始"
                if half_completed
                else "イニング継続"
            ),
            _HEADER[19]: "試合終了" if game_ended else "試合継続",
        }
    except (KeyError, TypeError, ValueError):
        raise RecordedExportProjectionUnavailable from None


def _batted_coordinates(identity: RecordedPlayIdentity) -> dict[str, str | None]:
    """受理済V7の保存正規化座標を原字面で保持する。"""
    try:
        observations = identity.payload["observations"]
        if type(observations) is not dict:
            raise RecordedExportProjectionUnavailable
        ball = observations.get("battedBall")
        if ball is None:
            values = (None, None)
        else:
            if type(ball) is not dict:
                raise RecordedExportProjectionUnavailable
            values = (ball["hitX"], ball["hitY"])
        if (values[0] is None) != (values[1] is None):
            raise RecordedExportProjectionUnavailable
        for value, field in zip(values, ("hit_x", "hit_y"), strict=True):
            stored = identity.play[field]
            if value is None:
                if stored is not None:
                    raise RecordedExportProjectionUnavailable
            elif (
                type(value) is not str
                or _DECIMAL.fullmatch(value) is None
                or not Decimal(0) <= Decimal(value) <= Decimal(1)
                or type(stored) is not float
                or not math.isfinite(stored)
                or float(value) != stored
            ):
                raise RecordedExportProjectionUnavailable
        return {_HEADER[50]: values[0], _HEADER[51]: values[1]}
    except (KeyError, TypeError, InvalidOperation, OverflowError):
        raise RecordedExportProjectionUnavailable from None


def _accepted_pitch_speed(identity: RecordedPlayIdentity) -> str | None:
    """物理Doubleと一致する受理済km/h原字面だけを写す。"""
    try:
        if identity.play["event_kind"] == "non_pitch":
            if (
                identity.payload["observations"] != {"kind": "intentional-walk"}
                or any(
                    identity.play[field] is not None
                    for field in (
                        "pitch_speed",
                        "pitch_type_key",
                        "course_x",
                        "course_y",
                        "stance",
                    )
                )
                or identity.course_screen != (None, None)
            ):
                raise RecordedExportProjectionUnavailable
            return None
        value = identity.payload["observations"]["pitchSpeed"]["kmh"]
        stored = identity.play["pitch_speed"]
        if value is None:
            if stored is not None:
                raise RecordedExportProjectionUnavailable
            return None
        if (
            type(value) is not str
            or _DECIMAL.fullmatch(value) is None
            or type(stored) is not float
            or not math.isfinite(stored)
            or float(value) != stored
        ):
            raise RecordedExportProjectionUnavailable
        return value
    except (KeyError, TypeError, OverflowError):
        raise RecordedExportProjectionUnavailable from None


def _input_origin(identity: RecordedPlayIdentity) -> str:
    """真正V7と保存source idの実識別子だけを閉版JSONへ写す。"""
    try:
        payload = identity.payload
        calculation = payload["calculation"]
        source_format = payload["formatVersion"]
        calculation_format = calculation["formatVersion"]
        artifact = calculation["artifactSha256"]
        formats = {
            "first-ball-play-v1": frozenset({"first-ball-calculation-v1"}),
            "ordinary-pitch-play-v1": frozenset({"ordinary-pitch-calculation-v1"}),
            "play-prefix-play-v2": frozenset({"play-prefix-calculation-v2"}),
            "play-prefix-play-v3": frozenset(
                {"play-prefix-calculation-v3", "nonplay-prefix-calculation-v1"}
            ),
        }
        if (
            type(source_format) is not str
            or source_format not in formats
            or type(calculation_format) is not str
            or calculation_format not in formats[source_format]
            or type(artifact) is not str
            or _SHA.fullmatch(artifact) is None
        ):
            raise RecordedExportProjectionUnavailable
        origin = {
            "formatVersion": "play-export-input-origin-v1",
            "operationKind": "play_input",
            "sourceFormat": source_format,
            "calculationFormat": calculation_format,
            "calculationArtifactSha256": artifact,
            "sourceEventId": str(identity.source.source_event_id),
        }
        if source_format in ("play-prefix-play-v2", "play-prefix-play-v3"):
            source = calculation["request"]["source"]
            if type(source) is not dict:
                raise RecordedExportProjectionUnavailable
            if calculation_format in (
                "play-prefix-calculation-v2",
                "play-prefix-calculation-v3",
            ):
                kind = source["kind"]
                allowed = (
                    ("bridged-v1", "evaluated-prefix-v2")
                    if source_format == "play-prefix-play-v2"
                    else ("started-initial-v3", "evaluated-prefix-v3")
                )
                if type(kind) is not str or kind not in allowed:
                    raise RecordedExportProjectionUnavailable
                origin["sourceKind"] = kind
            elif calculation_format == "nonplay-prefix-calculation-v1":
                if source.get("formatVersion") != "nonplay-prefix-source-v1":
                    raise RecordedExportProjectionUnavailable
                origin["sourceFormatVersion"] = source["formatVersion"]
            else:
                raise RecordedExportProjectionUnavailable
        return json.dumps(
            origin, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (KeyError, TypeError):
        raise RecordedExportProjectionUnavailable from None


def _runner_columns(
    identity: RecordedPlayIdentity, substitutes: dict[UUID, dict[str, Any]]
) -> dict[str, str | None]:
    """同TXのPlayRunnerと保存打順対応から走者欄を埋める。"""
    rows = identity.runners
    if type(rows) is not tuple or len(rows) > 3:
        raise RecordedExportProjectionUnavailable
    result: dict[str, str | None] = {}
    if not rows:
        for base, offset in ((1, 0), (2, 2), (3, 4)):
            for index in (
                20 + offset,
                21 + offset,
                36 + base - 1,
                65 + offset,
                66 + offset,
            ):
                result[_HEADER[index]] = None
        return result
    try:
        before = identity.payload["calculation"]["request"]["t1"]["before"][
            "stateFields"
        ]
        side = {"top": "away", "bottom": "home"}[before["state.half"]]
        current, _ = _recorded_context(identity)
        if current is not None:
            order_map = current[side]["battingOrder"]
            if type(order_map) is not dict:
                raise RecordedExportProjectionUnavailable
        else:
            team_id = identity.game[f"{side}_team_record_id"]
            matching = [
                row for row in identity.lineups if row.get("team_record_id") == team_id
            ]
            if len(matching) != 1:
                raise RecordedExportProjectionUnavailable
            order_map = {
                entry["batting_order"]: entry["player_id"]
                for entry in matching[0]["entries_with_uniform_number_snapshot"]
                if entry["batting_order"] is not None
            }
            if any(
                type(order) is not int or not 1 <= order <= 9 for order in order_map
            ):
                raise RecordedExportProjectionUnavailable
        if len(order_map) != len(set(order_map.values())):
            raise RecordedExportProjectionUnavailable
        by_base = {row["base"]: row for row in rows}
        if len(by_base) != len(rows) or any(base not in (1, 2, 3) for base in by_base):
            raise RecordedExportProjectionUnavailable
        for base, offset in ((1, 0), (2, 2), (3, 4)):
            row = by_base.get(base)
            if row is None:
                for index in (
                    20 + offset,
                    21 + offset,
                    36 + base - 1,
                    65 + offset,
                    66 + offset,
                ):
                    result[_HEADER[index]] = None
                continue
            runner_id = row["runner_id"]
            player = _player(identity, runner_id)
            orders = [
                order
                for order, identifier in order_map.items()
                if identifier == str(runner_id)
            ]
            if (
                len(orders) != 1
                or type(orders[0]) not in (str, int)
                or _NAT.fullmatch(str(orders[0])) is None
            ):
                raise RecordedExportProjectionUnavailable
            if type(row["status"]) is not str or row["status_source"] not in (
                "auto",
                "manual",
            ):
                raise RecordedExportProjectionUnavailable
            result[_HEADER[20 + offset]] = str(orders[0])
            result[_HEADER[21 + offset]] = _text(player["name"])
            result[_HEADER[36 + base - 1]] = row["status"]
            result[_HEADER[65 + offset]] = _text(player["name"])
            result[_HEADER[66 + offset]] = _text(
                _recorded_entry(identity, runner_id, substitutes)[
                    "uniform_number_snapshot"
                ]
            )
        return result
    except (KeyError, TypeError, ValueError):
        raise RecordedExportProjectionUnavailable from None


def project_recorded_direct(
    identity: RecordedPlayIdentity,
    substitutes: dict[UUID, dict[str, Any]] | None = None,
) -> dict[str, str | None]:
    """保存値・記録時表示参照・B-7生成値の確定列だけを返す。

    Args:
        identity: 真正writerが同TXで捕捉したゲーム/プレイ/表示原本。
        substitutes: 同TXで交代eventとreceiptを照合した途中出場者snapshot。

    Returns:
        直接供給済みの列だけ。残列は後段producerが埋める。

    Raises:
        RecordedExportProjectionUnavailable: 原本の型・参照・時刻が不正。
    """
    if type(identity) is not RecordedPlayIdentity:
        raise RecordedExportProjectionUnavailable
    game, play = identity.game, identity.play
    if substitutes is None:
        substitutes = {}
    if type(substitutes) is not dict:
        raise RecordedExportProjectionUnavailable
    if (
        game.get("tenant_id") != identity.source.tenant_id
        or game.get("id") != identity.source.game_id
        or play.get("tenant_id") != identity.source.tenant_id
        or play.get("source_event_id") != identity.source.source_event_id
    ):
        raise RecordedExportProjectionUnavailable
    scheduled = game.get("scheduled_at")
    started = game.get("started_at")
    if (
        type(scheduled) is not datetime
        or scheduled.tzinfo is None
        or (
            started is not None
            and (type(started) is not datetime or started.tzinfo is None)
        )
    ):
        raise RecordedExportProjectionUnavailable
    if started is None:
        raise RecordedExportProjectionUnavailable
    try:
        elapsed = server_accepted_elapsed(started, identity.accepted_server_at)
    except ValueError:
        raise RecordedExportProjectionUnavailable from None
    result: dict[str, str | None] = {
        _HEADER[0]: scheduled.astimezone(_JST).strftime("%Y/%m/%d"),
        _HEADER[1]: _text(game["section_label"]),
        _HEADER[2]: _lookup(identity.tenant_vocabularies, game["tournament_key"]),
        _HEADER[3]: _text(game["week_label"]),
        _HEADER[4]: _text(game["day_label"]),
        _HEADER[5]: _text(game["game_number_label"]),
        _HEADER[6]: _text(game["plate_umpire"]),
        _HEADER[7]: _team(identity, game["home_team_record_id"]),
        _HEADER[8]: _team(identity, game["away_team_record_id"]),
        _HEADER[75]: elapsed,
        _HEADER[76]: started.astimezone(_JST).strftime("%H:%M:%S"),
        _HEADER[77]: identity.accepted_server_at.astimezone(_JST).strftime("%H:%M:%S"),
        _HEADER[42]: identity.course_screen[0],
        _HEADER[43]: identity.course_screen[1],
    }
    result.update(_native_before(identity.payload))
    result.update(_native_completion(identity.payload))
    result.update(_batted_coordinates(identity))
    result[_HEADER[56]] = _accepted_pitch_speed(identity)
    result[_HEADER[72]] = _input_origin(identity)
    result.update(_runner_columns(identity, substitutes))
    result.update(_starting_lineup_columns(identity))
    # 列番号は唯一の物理mapper metadataから取る。人手の列→fieldコピーを持たない。
    pairs = [
        (index, column.name)
        for column in PlayRow.__table__.c
        for index in column.info.get("legacy_source_columns", ())
        if index in _DIRECT
    ]
    actual = dict(pairs)
    if len(pairs) != len(actual) or set(actual) != _DIRECT:
        raise RecordedExportProjectionUnavailable
    for index, field in actual.items():
        if field not in play:
            raise RecordedExportProjectionUnavailable
        result[_HEADER[index]] = _text(play[field])
    for index, field in _TENANT_VOCAB.items():
        if field not in play:
            raise RecordedExportProjectionUnavailable
        result[_HEADER[index]] = _lookup(identity.tenant_vocabularies, play[field])
    for index, field in _ADMIN_VOCAB.items():
        if field not in play:
            raise RecordedExportProjectionUnavailable
        result[_HEADER[index]] = _lookup(identity.admin_vocabularies, play[field])
    try:
        plate_ended = identity.payload["calculation"]["response"]["value"]["t1"][
            "plateAppearanceEnded"
        ]
        result_label = _lookup(identity.admin_vocabularies, play["batting_result_key"])
        ball_type_label = _lookup(identity.admin_vocabularies, play["batted_ball_type"])
        plate_display = plate_result_display(
            result_label,
            plate_ended,
            _text(play["raw_error_position"]),
            ball_type_label,
        )
    except (KeyError, TypeError, ValueError):
        raise RecordedExportProjectionUnavailable from None
    result[_HEADER[61]] = plate_display
    result[_HEADER[62]] = plate_display
    for index, field in ((27, "batter_id"), (32, "pitcher_id"), (35, "catcher_id")):
        result[_HEADER[index]] = _text(_player(identity, play[field])["name"])
    batter = _player(identity, play["batter_id"])
    pitcher = _player(identity, play["pitcher_id"])
    if play["batting_side"] not in (None, "右", "左") or pitcher["throws"] not in (
        None,
        "右",
        "左",
    ):
        raise RecordedExportProjectionUnavailable
    result[_HEADER[28]] = _text(play["batting_side"])
    result[_HEADER[33]] = _text(pitcher["throws"])
    if play["event_kind"] not in ("pitch", "non_pitch"):
        raise RecordedExportProjectionUnavailable
    result[_HEADER[40]] = "投球" if play["event_kind"] == "pitch" else "非投球"
    result[_HEADER[63]] = _text(batter["name"])
    batter_entry = _recorded_entry(identity, play["batter_id"], substitutes)
    pitcher_entry = _recorded_entry(identity, play["pitcher_id"], substitutes)
    batter_role = batter_entry["fielding_position"]
    result[_HEADER[59]] = (
        None
        if batter_role is None
        else fielding_position_label(_saved_fielding_role(batter_role))
    )
    result[_HEADER[64]] = _text(batter_entry["uniform_number_snapshot"])
    result[_HEADER[71]] = _text(pitcher_entry["uniform_number_snapshot"])
    return result
