"""API の共通スキーマを定義する。"""

from typing import Generic, TypeAlias, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """すべての DTO の共通基底を表す。"""

    model_config = ConfigDict(extra="forbid")


class ReadSchema(BaseSchema):
    """属性から構築する読み取り DTO の共通基底を表す。"""

    model_config = ConfigDict(from_attributes=True)


EntityId: TypeAlias = UUID
"""サロゲート ID を表す。

複合主キーの ``id`` 側だけを表し、テナント文脈を含まない。
認可判定に使わない。
"""


Timestamp: TypeAlias = AwareDatetime
"""タイムゾーン情報を持つ日時を表す。"""


ItemT = TypeVar("ItemT")


class PageRequest(BaseSchema):
    """一覧のページ位置を要求する。

    件数上限の判定と拒否は各葉の責務であり、この型は値を詰めない。
    """

    limit: int = Field(ge=1)
    cursor: str | None = Field(default=None, min_length=1)


class Page(BaseSchema, Generic[ItemT]):
    """ページ単位の応答を表す。"""

    items: list[ItemT]
    next_cursor: str | None = Field(default=None, min_length=1)


class ErrorField(BaseSchema):
    """バリデーションエラーの発生箇所を表す。"""

    location: str


class ErrorDetail(BaseSchema):
    """API エラーの詳細を表す。"""

    message: str
    fields: list[ErrorField] | None = None


class ErrorEnvelope(BaseSchema):
    """API エラー応答の封筒を表す。"""

    error: ErrorDetail


class HealthResponse(BaseSchema):
    """ヘルスチェックの応答を表す。"""

    status: str


class VersionResponse(BaseSchema):
    """アプリケーション版の応答を表す。"""

    version: str
