"""通常投球V7/V8の閉codec。数学・権利・保存資格は生成しない。"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from pitchlog.domainrt.first_ball_projection import (
    _canonical_json,
    _canonical_sha256,
    _same_member_types,
)
from pitchlog.domainrt.first_pitch import _Frozen, _invalid_constant, _unique_object
from pitchlog.domainrt.first_pitch_continuation import (
    _check_frozen_members,
    _WireFrozen,
)
from pitchlog.domainrt.initial_game_roster import CanonicalUUID
from pitchlog.domainrt.ordinary_pitch_continuation import (
    NewHistoryEntry,
    OrdinaryContinuationRequest,
    OrdinaryContinuationSuccess,
)
from pitchlog.sync.first_ball_payload import FirstBallObservations


class OrdinaryPitchPayloadError(ValueError):
    """原観測や資格を含めない固定の不一致。"""

    def __init__(self) -> None:
        """失敗を成功へ補修しない。"""
        super().__init__("通常投球payloadの閉値又は実評価値が不一致です")


class OrdinaryPitchParticipants(_WireFrozen):
    """実prefixの現在打者/守備者へ束縛すべき参照値。"""

    batter_id: CanonicalUUID = Field(alias="batterId")
    pitcher_id: CanonicalUUID = Field(alias="pitcherId")
    catcher_id: CanonicalUUID = Field(alias="catcherId")
    batting_order: Literal["1", "2", "3", "4", "5", "6", "7", "8", "9"] = Field(
        alias="battingOrder"
    )


class OrdinaryPitchCalculation(_Frozen):
    """同一artifactの今回request/responseの全値。数学の資格ではない。"""

    format_version: Literal["ordinary-pitch-calculation-v1"] = Field(
        alias="formatVersion"
    )
    artifact_sha256: Annotated[str, AfterValidator(_canonical_sha256)] = Field(
        alias="artifactSha256"
    )
    request: OrdinaryContinuationRequest
    response: OrdinaryContinuationSuccess


class OrdinaryPitchPlayPayload(_Frozen):
    """初球と区別するV7閉形。未対応結果は実artifactが拒否する。"""

    format_version: Literal["ordinary-pitch-play-v1"] = Field(alias="formatVersion")
    observations: FirstBallObservations
    participants: OrdinaryPitchParticipants
    calculation: OrdinaryPitchCalculation


def _raw_json(value: str) -> object:
    """重複key/非有限値をパース時に拒否する。"""
    if type(value) is not str:
        raise OrdinaryPitchPayloadError
    return json.loads(
        value, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )


def _checked(value, model):
    """自由model/強制変更/型の正規化を閉境界で拒否する。"""
    if type(value) is not model:
        raise OrdinaryPitchPayloadError
    _check_frozen_members(value)
    validated = model.model_validate(value)
    _same_member_types(value, validated)
    return validated


def format_ordinary_pitch_payload(
    observations: FirstBallObservations,
    participants: OrdinaryPitchParticipants,
    calculation: OrdinaryPitchCalculation,
) -> tuple[str, str]:
    """全評価値を無計算でV7/V8へ写し、勝手な履歴を生成しない。"""
    try:
        payload = OrdinaryPitchPlayPayload(
            formatVersion="ordinary-pitch-play-v1",
            observations=_checked(observations, FirstBallObservations),
            participants=_checked(participants, OrdinaryPitchParticipants),
            calculation=_checked(calculation, OrdinaryPitchCalculation),
        )
        return (
            _canonical_json(
                payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
            ),
            _canonical_json(
                calculation.response.value.new_history_entry.difference.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                )
            ),
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise OrdinaryPitchPayloadError from None


def read_ordinary_pitch_payload(
    v7_json: str,
    v8_json: str,
    *,
    expected_calculation: OrdinaryPitchCalculation,
    expected_participants: OrdinaryPitchParticipants,
) -> OrdinaryPitchPlayPayload:
    """実frame側から独立供給された全値と完全一致する場合だけ読む。"""
    try:
        calc = _checked(expected_calculation, OrdinaryPitchCalculation)
        people = _checked(expected_participants, OrdinaryPitchParticipants)
        raw = _raw_json(v7_json)
        payload = OrdinaryPitchPlayPayload.model_validate_json(v7_json)
        if _canonical_json(raw) != _canonical_json(
            payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
        ):
            raise OrdinaryPitchPayloadError
        if (
            payload.calculation != calc
            or payload.participants != people
            or payload.participants.batting_order
            != calc.request.t1.before.state_fields.batting_order
        ):
            raise OrdinaryPitchPayloadError
        entry = NewHistoryEntry.model_validate(
            {"kind": "confirmed-play", "difference": _raw_json(v8_json)}
        )
        if (
            _canonical_json(_raw_json(v8_json))
            != _canonical_json(
                entry.difference.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                )
            )
            or entry.difference != calc.response.value.new_history_entry.difference
        ):
            raise OrdinaryPitchPayloadError
        return payload
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise OrdinaryPitchPayloadError from None


def select_ordinary_pitch_participants(roster, before) -> OrdinaryPitchParticipants:
    """実配置の現在打順と守備位置を選び、配置計算を再実装しない。"""
    from pitchlog.domainrt.first_pitch import StateSnapshot
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection

    if type(roster) is not InitialRosterProjection or type(before) is not StateSnapshot:
        raise OrdinaryPitchPayloadError
    _check_frozen_members(roster)
    _check_frozen_members(before)
    away, home = roster.teams
    batting, fielding = (
        (away, home) if before.state_fields.half == "top" else (home, away)
    )
    batters = [
        entry
        for entry in batting.participants
        if entry.batting_slot.kind == "slot"
        and entry.batting_slot.slot == before.state_fields.batting_order
    ]
    pitchers = [
        entry
        for entry in fielding.participants
        if any(role.kind == "fielding" and role.position == "1" for role in entry.roles)
    ]
    catchers = [
        entry
        for entry in fielding.participants
        if any(role.kind == "fielding" and role.position == "2" for role in entry.roles)
    ]
    if len(batters) != 1 or len(pitchers) != 1 or len(catchers) != 1:
        raise OrdinaryPitchPayloadError
    return OrdinaryPitchParticipants(
        batterId=batters[0].player.player_id,
        pitcherId=pitchers[0].player.player_id,
        catcherId=catchers[0].player.player_id,
        battingOrder=before.state_fields.batting_order,
    )
