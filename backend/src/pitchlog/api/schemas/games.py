"""準備中試合の作成入力と一覧位置を定義する。"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import math
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from pitchlog.api.schemas.base import BaseSchema, EntityId, Page, PageRequest, Timestamp
from pitchlog.db.game_state.rule_snapshot import (
    DomainValidatedRuleSnapshot,
    decode_applied_rules,
)
from pitchlog.repositories.tokens import ImmutableValue

PREPARING_GAME_PAGE_SIZE_MAX = 100
GameTypeKey = Literal[
    "game_official", "game_semi_official", "game_open", "game_intrasquad", "game_other"
]


class ExistingTournament(BaseSchema):
    """既存の大会語彙キーを選ぶ。"""

    kind: Literal["existing"]
    key: str = Field(min_length=1)


class NewTournament(BaseSchema):
    """新しい大会表示名を指定する。"""

    kind: Literal["new"]
    display_name: str = Field(min_length=1)

    @field_validator("display_name")
    @classmethod
    def reject_blank_name(cls, value: str) -> str:
        """空白だけを拒否し、有効な入力のUnicode表現は変えない。"""
        if value.isspace():
            raise ValueError("大会名は空白だけにできません")
        return value


TournamentSelection = Annotated[
    ExistingTournament | NewTournament, Field(discriminator="kind")
]


class PreparingGameCreate(BaseSchema):
    """preparing 試合の作成に必要な利用者入力だけを受け取る。"""

    scheduled_at: Timestamp
    game_type_key: GameTypeKey
    away_team_record_id: EntityId
    home_team_record_id: EntityId
    tournament: TournamentSelection
    plate_umpire: str | None = None
    section_label: str | None = None
    week_label: str | None = None
    day_label: str | None = None
    game_number_label: str | None = None


class PreparingGameRead(BaseSchema):
    """同tenantの可視な準備中試合と検証済み保存snapshotを返す。"""

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
    status: Literal["preparing"]
    applied_rules: dict[str, object]

    @field_validator("scheduled_at")
    @classmethod
    def normalize_scheduled_at(cls, value: datetime) -> datetime:
        """保存後readと同じUTC表現へ揃え、同一instantは変更しない。"""
        return value.astimezone(timezone.utc)


def encode_preparation_options_cursor(key: str) -> str:
    """大会キーを値を変えずに不透明なページ位置へ写す。"""
    if type(key) is not str or not key:
        raise ValueError("大会キーは空でない文字列が必要")
    return base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii").rstrip("=")


def decode_preparation_options_cursor(cursor: str) -> str:
    """正規形のページ位置だけを元の大会キーへ戻す。"""
    if type(cursor) is not str or not cursor:
        raise ValueError("大会ページ位置が不正")
    try:
        key = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
        ).decode("utf-8")
        if encode_preparation_options_cursor(key) != cursor:
            raise ValueError
        return key
    except (binascii.Error, UnicodeError, ValueError):
        raise ValueError("大会ページ位置が不正") from None


class PreparationOptionsRequest(PageRequest):
    """有効大会のページ件数と位置を指定する。"""

    limit: int = Field(default=20, ge=1, le=PREPARING_GAME_PAGE_SIZE_MAX, strict=True)

    @field_validator("limit", mode="before")
    @classmethod
    def parse_query_limit(cls, value: object) -> object:
        """既存のHTTP件数表記と同じ規則を使う。"""
        return PreparingGameListRequest.parse_query_limit(value)

    @field_validator("cursor")
    @classmethod
    def validate_cursor(cls, value: str | None) -> str | None:
        """位置があれば正規形であることを検査する。"""
        if value is not None:
            decode_preparation_options_cursor(value)
        return value


class PreparationGameTypeOption(BaseSchema):
    """正本seedから供給する固定試合区分の表示。"""

    key: GameTypeKey
    display_name: str = Field(min_length=1)


class PreparationTournamentOption(BaseSchema):
    """テナント内で有効な大会のキーと表示名。"""

    key: str = Field(min_length=1)
    display_name: str = Field(min_length=1)


class PreparingGamePreparationOptions(BaseSchema):
    """固定区分とページングした大会選択肢。"""

    game_types: list[PreparationGameTypeOption]
    tournaments: Page[PreparationTournamentOption]


def _copy_preparing_snapshot_json(value: ImmutableValue) -> object:
    """実行器の不変 JSON コンテナを codec に渡せる新しいコンテナへ写す。

    Args:
        value: 実行器が不変化した JSON 値。

    Returns:
        新しい dict/list、または型を変えない JSON スカラー。

    Raises:
        ValueError: JSON 以外の型や非有限数が含まれる場合。
    """
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is MappingProxyType:
        if any(type(key) is not str for key in value):
            raise ValueError("snapshot JSON 値の型が不正")
        return {key: _copy_preparing_snapshot_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_copy_preparing_snapshot_json(item) for item in value]
    raise ValueError("snapshot JSON 値の型が不正")


def _decode_preparing_snapshot(value: ImmutableValue) -> DomainValidatedRuleSnapshot:
    """実行器の不変 JSON を正規 codec で検証する。出所証明は行わない。

    Args:
        value: 実行器が返した保存済み snapshot の不変 JSON 値。

    Returns:
        形・値域・相関を検証した snapshot。規則行の出所は含まない。

    Raises:
        ValueError: 非 JSON 値または不正な snapshot が含まれる場合。
        RuleSnapshotContractUnavailable: 正規 codec の凍結契約を読めない場合。
    """
    return decode_applied_rules(_copy_preparing_snapshot_json(value))


def encode_preparing_game_cursor(scheduled_at: datetime, game_id: UUID) -> str:
    """降順 keyset の位置を不透明なカーソルへ変換する。

    Args:
        scheduled_at: タイムゾーン付きの試合予定時刻。
        game_id: 同時刻の順序を確定する試合 ID。

    Returns:
        URL に使える不透明なカーソル。

    Raises:
        ValueError: 位置の型または時刻が不正な場合。
    """
    if (
        type(scheduled_at) is not datetime
        or scheduled_at.tzinfo is None
        or scheduled_at.utcoffset() is None
        or type(game_id) is not UUID
    ):
        raise ValueError("カーソル位置は aware な日時と UUID が必要")
    stamp = scheduled_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
    payload = f"{stamp}|{game_id.hex}".encode("ascii")
    checksum = hashlib.sha256(payload).hexdigest()[:16].encode("ascii")
    return (
        base64.urlsafe_b64encode(payload + b"|" + checksum).decode("ascii").rstrip("=")
    )


def decode_preparing_game_cursor(cursor: str) -> tuple[datetime, UUID]:
    """カーソルを正規形の aware 日時と試合 ID に戻す。

    Args:
        cursor: 一覧応答が返した不透明なページ位置。

    Returns:
        降順 keyset の比較位置。

    Raises:
        ValueError: 破損した形式、非正規形、型、または naive 日時の場合。
    """
    if type(cursor) is not str or not 1 <= len(cursor) <= 256:
        raise ValueError("カーソルの形式が不正")
    try:
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
        )
        if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != cursor:
            raise ValueError
        stamp, id_hex, checksum = raw.decode("ascii").rsplit("|", 2)
        payload = f"{stamp}|{id_hex}".encode("ascii")
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest()[:16], checksum):
            raise ValueError
        scheduled_at = datetime.fromisoformat(stamp)
        game_id = UUID(hex=id_hex)
        if game_id.hex != id_hex or scheduled_at.utcoffset() is None:
            raise ValueError
        if encode_preparing_game_cursor(scheduled_at, game_id) != cursor:
            raise ValueError
        return scheduled_at, game_id
    except (binascii.Error, UnicodeError, ValueError) as error:
        raise ValueError("カーソルの形式が不正") from error


class PreparingGameListRequest(PageRequest):
    """preparing 試合の一覧件数と不透明なページ位置を指定する。"""

    limit: int = Field(default=20, ge=1, le=PREPARING_GAME_PAGE_SIZE_MAX, strict=True)

    @field_validator("limit", mode="before")
    @classmethod
    def parse_query_limit(cls, value: object) -> object:
        """HTTP query の ASCII 十進表記だけを strict int へ変換する。"""
        if type(value) is str and value.isascii() and value.isdecimal():
            return int(value)
        return value

    @field_validator("cursor")
    @classmethod
    def validate_cursor(cls, value: str | None) -> str | None:
        """存在するカーソルをデコードできる正規形に限定する。"""
        if value is not None:
            decode_preparing_game_cursor(value)
        return value
