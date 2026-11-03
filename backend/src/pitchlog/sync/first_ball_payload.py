"""初球V7/V8の閉値codec。真正frame・権利・保存の資格は発行しない。

観測を計算し直さず、独立に供給された計算/参加者の期待値だけと照合する。
registered Portからimportする部品ではなく、privileged内容検証側で使う。
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal, TypeVar

from pydantic import AfterValidator, Field, model_validator

from pitchlog.domainrt.first_ball_projection import (
    FirstBallCalculationValue,
    _canonical_json,
    _same_member_types,
    format_first_ball_calculation,
    read_first_ball_calculation,
)
from pitchlog.domainrt.first_pitch import (
    DecimalInteger,
    HistoryDifference,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.first_pitch_continuation import (
    _check_frozen_members,
    _WireFrozen,
)
from pitchlog.domainrt.initial_game_roster import (
    CanonicalUUID,
    InitialRosterProjection,
    ProjectedEntry,
)

_ERROR = "初球payloadの閉形式又は期待値が一致しません"
_Model = TypeVar("_Model", bound=_Frozen)


class FirstBallPayloadError(ValueError):
    """原観測/資格/元例外を表示しない固定のcodec拒否。"""


def _course_unit(value: str) -> str:
    """座標変換はせず、既正準整数kの表現と範囲だけを確認する。"""
    if not 0 <= int(value) <= 263:
        raise ValueError("正準座標の範囲外")
    return value


def _stance(value: str) -> str:
    """任意構えの既1〜25表現を、0補完せず確認する。"""
    if not 1 <= int(value) <= 25:
        raise ValueError("構えの範囲外")
    return value


def _speed(value: str) -> str:
    """有限十進文字列の表現だけを確認し、丸め/単位変換をしない。"""
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value, re.ASCII) is None:
        raise ValueError("球速の十進表現が不正")
    return value


class FirstBallCourse(_WireFrozen):
    """捕手視点の正準保存座標。画面floatからの変換はしない。"""

    unit: Literal["1/263"]
    x: Annotated[DecimalInteger, AfterValidator(_course_unit)]
    y: Annotated[DecimalInteger, AfterValidator(_course_unit)]


class FirstBallPitchSpeed(_WireFrozen):
    """任意球速と確認観測。範囲設定/物理Double適合を証明しない。"""

    kmh: Annotated[str, AfterValidator(_speed)] | None
    outside_range_confirmed: bool = Field(alias="outsideRangeConfirmed")

    @model_validator(mode="after")
    def _missing_has_no_range_confirmation(self) -> FirstBallPitchSpeed:
        """欠損球速へ確認成立を補わない。"""
        if self.kmh is None and self.outside_range_confirmed:
            raise ValueError("欠損球速の範囲外確認は持てない")
        return self


class FirstBallObservations(_WireFrozen):
    """記録員が供給する観測値。正式語彙/実打席側の認定はしない。"""

    pitch_type_key: Annotated[str, Field(min_length=1)] = Field(alias="pitchTypeKey")
    course: FirstBallCourse
    pitch_speed: FirstBallPitchSpeed = Field(alias="pitchSpeed")
    stance: Annotated[DecimalInteger, AfterValidator(_stance)] | None
    batting_side: Literal["右", "左"] | None = Field(alias="battingSide")


class FirstBallParticipants(_WireFrozen):
    """参照形だけを保持し、所属/現在出場は期待値の供給側が確認する。"""

    batter_id: CanonicalUUID = Field(alias="batterId")
    pitcher_id: CanonicalUUID = Field(alias="pitcherId")
    catcher_id: CanonicalUUID = Field(alias="catcherId")
    batting_order: Literal["1"] = Field(alias="battingOrder")


class FirstBallPlayPayload(_WireFrozen):
    """V7のexact4。既計算DTOを第二実装へ写し替えない。"""

    format_version: Literal["first-ball-play-v1"] = Field(alias="formatVersion")
    observations: FirstBallObservations
    participants: FirstBallParticipants
    calculation: FirstBallCalculationValue


class FirstBallPayloadValue(_Frozen):
    """独立に読み戻した値。writer・権利・Ready・DB保存の証明ではない。"""

    v7: FirstBallPlayPayload
    v8: HistoryDifference


def _checked(value: _Model, exact_type: type[_Model]) -> _Model:
    """実型と全memberを再検査し、強制変異の暗黙正規化を拒否する。"""
    if type(value) is not exact_type:
        raise TypeError("既閉値の実型が必要")
    _check_frozen_members(value)
    checked = exact_type.model_validate(value)
    _same_member_types(value, checked)
    return checked


def _calculation(value: FirstBallCalculationValue) -> FirstBallCalculationValue:
    """既formatterで全値を再検査し、初球result variantだけを限定する。"""
    checked = _checked(value, FirstBallCalculationValue)
    request = checked.request.t1
    if (
        request.event_kind != "batting-result"
        or request.result_id != "batting-result.ball"
        or request.pitch_event_kind != "pitch-event"
    ):
        raise ValueError("未対応result variant")
    raw = format_first_ball_calculation(
        checked.request, checked.response, artifact_sha256=checked.artifact_sha256
    )
    if _canonical_json(checked.model_dump(mode="json", by_alias=True)) != raw:
        raise ValueError("計算値の閉全値が不一致")
    return read_first_ball_calculation(
        raw,
        expected_request=checked.request,
        expected_response=checked.response,
        expected_artifact_sha256=checked.artifact_sha256,
    )


def _raw(raw: str) -> object:
    """重複key/非JSON数値を修復せず読み取る。"""
    if type(raw) is not str:
        raise TypeError("JSON文字列が必要")
    return json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )


def select_first_ball_participants(
    roster: InitialRosterProjection,
) -> FirstBallParticipants:
    """単一artifactの配置から一意の先頭打者/投手/捕手を抜き出す。

    配置・打順・守備を計算しない。一意に取れない場合は ValueError とする。
    保存経路と再評価経路で同じ規則を共有する（単一実装）。

    Args:
        roster: 開始原典から再構成した名簿の射影。

    Returns:
        payloadのparticipants閉値（打順は "1" 固定）。

    Raises:
        ValueError: 先頭打者/投手/捕手が一意に定まらない場合。
    """
    away, home = roster.teams

    def unique(
        entries: tuple[ProjectedEntry, ...], position: str | None
    ) -> list[ProjectedEntry]:
        if position is None:
            return [
                entry
                for entry in entries
                if entry.batting_slot.kind == "slot" and entry.batting_slot.slot == "1"
            ]
        return [
            entry
            for entry in entries
            if any(
                role.kind == "fielding" and role.position == position
                for role in entry.roles
            )
        ]

    batters = unique(away.participants, None)
    pitchers = unique(home.participants, "1")
    catchers = unique(home.participants, "2")
    if len(batters) != 1 or len(pitchers) != 1 or len(catchers) != 1:
        raise ValueError("先頭打者/投手/捕手を一意に特定できない")
    return FirstBallParticipants(
        batterId=batters[0].player.player_id,
        pitcherId=pitchers[0].player.player_id,
        catcherId=catchers[0].player.player_id,
        battingOrder="1",
    )


def format_first_ball_payload(
    observations: FirstBallObservations,
    participants: FirstBallParticipants,
    calculation: FirstBallCalculationValue,
) -> tuple[str, str]:
    """閉観測/参加者/既計算値をV7/V8へ写す。真正性は判定しない。

    Args:
        observations: 記録員が供給する正準観測。
        participants: 保存名簿へ結合すべき参照値。
        calculation: 同一評価を取得すべき既計算値。

    Returns:
        V7/V8閉JSON。差分は実応答から無計算で保持する。

    Raises:
        FirstBallPayloadError: 型/形式/variantが不正な場合。
    """
    try:
        obs = _checked(observations, FirstBallObservations)
        people = _checked(participants, FirstBallParticipants)
        calc = _calculation(calculation)
        payload = FirstBallPlayPayload(
            formatVersion="first-ball-play-v1",
            observations=obs,
            participants=people,
            calculation=calc,
        )
        return (
            _canonical_json(payload.model_dump(mode="json", by_alias=True)),
            _canonical_json(
                calc.response.value.t1.history_context[0].difference.model_dump(
                    mode="json", by_alias=True
                )
            ),
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise FirstBallPayloadError(_ERROR) from None


def read_first_ball_payload(
    v7_json: str,
    v8_json: str,
    *,
    expected_calculation: FirstBallCalculationValue,
    expected_participants: FirstBallParticipants,
) -> FirstBallPayloadValue:
    """独立期待calc/参加者とV8へ全値一致する閉payloadを戻す。

    Args:
        v7_json: 取得した原V7のJSON。元SyncEventは変更しない。
        v8_json: 取得した原V8のJSON。
        expected_calculation: 真正性/同一評価を供給側が確認すべき期待値。
        expected_participants: 保存名簿へ供給側が束縛すべき期待参照。

    Returns:
        原入力とaliasを持たない値。認可/同writer/数学/保存証明ではない。

    Raises:
        FirstBallPayloadError: 閉形式/期待/差分が不一致の場合。
    """
    try:
        expected = _calculation(expected_calculation)
        people = _checked(expected_participants, FirstBallParticipants)
        raw_v7, raw_v8 = _raw(v7_json), _raw(v8_json)
        payload = FirstBallPlayPayload.model_validate_json(
            v7_json, by_alias=True, by_name=False
        )
        difference = HistoryDifference.model_validate_json(
            v8_json, by_alias=True, by_name=False
        )
        if _canonical_json(raw_v7) != _canonical_json(
            payload.model_dump(mode="json", by_alias=True)
        ):
            raise ValueError("V7の原表現と型が不一致")
        if _canonical_json(raw_v8) != _canonical_json(
            difference.model_dump(mode="json", by_alias=True)
        ):
            raise ValueError("V8の原表現と型が不一致")
        if _canonical_json(
            payload.calculation.model_dump(mode="json", by_alias=True)
        ) != _canonical_json(expected.model_dump(mode="json", by_alias=True)):
            raise ValueError("独立計算期待と全値不一致")
        if _canonical_json(
            payload.participants.model_dump(mode="json", by_alias=True)
        ) != _canonical_json(people.model_dump(mode="json", by_alias=True)):
            raise ValueError("独立名簿期待と全値不一致")
        if _canonical_json(
            difference.model_dump(mode="json", by_alias=True)
        ) != _canonical_json(
            expected.response.value.t1.history_context[0].difference.model_dump(
                mode="json", by_alias=True
            )
        ):
            raise ValueError("同一評価の差分と全値不一致")
        return FirstBallPayloadValue(v7=payload, v8=difference)
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise FirstBallPayloadError(_ERROR) from None
