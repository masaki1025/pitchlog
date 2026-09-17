"""API の共通スキーマを定義する。"""

from typing import TypeAlias
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict


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
