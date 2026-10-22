"""準備中試合の作成入力と一覧位置を定義する。"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from pitchlog.api.schemas.base import BaseSchema, EntityId, PageRequest, Timestamp

PREPARING_GAME_PAGE_SIZE_MAX = 100


class ExistingTournament(BaseSchema):
    """既存の大会語彙キーを選ぶ。"""

    kind: Literal["existing"]
    key: str = Field(min_length=1)


class NewTournament(BaseSchema):
    """新しい大会表示名を指定する。"""

    kind: Literal["new"]
    display_name: str = Field(min_length=1)


TournamentSelection = Annotated[
    ExistingTournament | NewTournament, Field(discriminator="kind")
]


class PreparingGameCreate(BaseSchema):
    """preparing 試合の作成に必要な利用者入力だけを受け取る。"""

    scheduled_at: Timestamp
    game_type_key: Literal[
        "game_official",
        "game_semi_official",
        "game_open",
        "game_intrasquad",
        "game_other",
    ]
    away_team_record_id: EntityId
    home_team_record_id: EntityId
    tournament: TournamentSelection
    plate_umpire: str | None = None
    section_label: str | None = None
    week_label: str | None = None
    day_label: str | None = None
    game_number_label: str | None = None


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
