"""API の共通スキーマを定義する。"""

from pydantic import BaseModel


class ErrorField(BaseModel):
    """バリデーションエラーの発生箇所を表す。"""

    location: str


class ErrorDetail(BaseModel):
    """API エラーの詳細を表す。"""

    message: str
    fields: list[ErrorField] | None = None


class ErrorEnvelope(BaseModel):
    """API エラー応答の封筒を表す。"""

    error: ErrorDetail
