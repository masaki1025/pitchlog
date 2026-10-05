"""選手とチームレコードの入出力スキーマを定義する。"""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from pitchlog.api.schemas.base import (
    BaseSchema,
    EntityId,
    PageRequest,
    ReadSchema,
    Timestamp,
)

UniformNumber = Annotated[str, Field(min_length=1)]
ROSTER_PAGE_SIZE_MAX = 200


class TeamRecordRead(ReadSchema):
    """チームレコードの表示情報を表す。"""

    id: EntityId
    kind: Literal["self", "opponent"]
    name: str
    hidden_at: Timestamp | None = None


class TeamRecordCreate(BaseSchema):
    """対戦相手チームレコードの作成内容を表す。"""

    name: str = Field(min_length=1)


class TeamRecordUpdate(BaseSchema):
    """チームレコードの変更内容を表す。"""

    name: str | None = None

    @field_validator("name")
    @classmethod
    def reject_null_name(cls, value: str | None) -> str:
        """明示された名前の null を拒否する。

        Args:
            value: 入力された名前。

        Returns:
            null でない名前。

        Raises:
            ValueError: null が指定された場合。
        """
        if value is None:
            raise ValueError("名前に null は指定できません")
        return value


class TeamRecordCreated(TeamRecordRead):
    """登録結果と類似名の警告を表す。"""

    similar_names: list[str]


class PlayerRead(ReadSchema):
    """選手の表示情報を表す。"""

    id: EntityId
    team_record_id: EntityId
    name: str
    throws: Literal["right", "left"] | None = None
    bats: Literal["right", "left", "both"] | None = None
    uniform_number: UniformNumber | None = None
    roster_status_key: str
    roster_label_key: str | None = None
    hidden_at: Timestamp | None = None


class PlayerCreate(BaseSchema):
    """選手の作成内容を表す。"""

    team_record_id: EntityId
    name: str
    throws: Literal["right", "left"] | None = None
    bats: Literal["right", "left", "both"] | None = None
    uniform_number: UniformNumber | None = None
    roster_status_key: str
    roster_label_key: str | None = None


class PlayerUpdate(BaseSchema):
    """選手の変更内容を表す。"""

    name: str | None = None
    throws: Literal["right", "left"] | None = None
    bats: Literal["right", "left", "both"] | None = None
    uniform_number: UniformNumber | None = None
    roster_status_key: str | None = None
    roster_label_key: str | None = None

    @field_validator("name", "roster_status_key")
    @classmethod
    def reject_null_required_value(cls, value: str | None) -> str:
        """NULL にできない列への明示的な null を拒否する。

        Args:
            value: 入力された値。

        Returns:
            null でない値。

        Raises:
            ValueError: null が指定された場合。
        """
        if value is None:
            raise ValueError("この項目に null は指定できません")
        return value


class PlayerCreated(PlayerRead):
    """登録結果と同じ背番号の選手を表す。"""

    same_number_players: list[PlayerRead]


class PlayerListRequest(PageRequest):
    """選手一覧の絞り込みとページ位置を表す。"""

    limit: int = Field(ge=1, le=ROSTER_PAGE_SIZE_MAX)
    team_record_id: EntityId | None = None
    roster_status_key: str | None = None
    include_hidden: bool = False


class TeamRecordListRequest(PageRequest):
    """チームレコード一覧のページ位置を表す。"""

    limit: int = Field(ge=1, le=ROSTER_PAGE_SIZE_MAX)
    include_hidden: bool = False


class PlayerStatusBulkRequest(BaseSchema):
    """複数選手の在籍区分変更要求を表す。"""

    player_ids: list[EntityId] = Field(min_length=1, max_length=50)
    roster_status_key: str
    roster_label_key: str | None

    @field_validator("player_ids")
    @classmethod
    def reject_duplicate_players(cls, value: list[EntityId]) -> list[EntityId]:
        """同じ選手 ID の重複を拒否する。

        Args:
            value: 入力された選手 ID。

        Returns:
            重複のない選手 ID。

        Raises:
            ValueError: 重複した ID が含まれる場合。
        """
        if len(value) != len(set(value)):
            raise ValueError("選手 ID が重複しています")
        return value


class PlayerStatusChange(ReadSchema):
    """プレビュー内の選手ごとの変更を表す。"""

    player_id: EntityId
    name: str
    before_status_key: str
    after_status_key: str


class PlayerStatusPreview(ReadSchema):
    """在籍区分変更のプレビューを表す。"""

    changes: list[PlayerStatusChange]
    unchanged_player_ids: list[EntityId]
    not_found_player_ids: list[EntityId]


class PlayerStatusApplied(ReadSchema):
    """在籍区分変更の適用結果を表す。"""

    applied: list[PlayerRead]
    not_found_player_ids: list[EntityId]
