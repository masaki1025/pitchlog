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


class HealthResponse(BaseModel):
    """ヘルスチェックの応答を表す。"""

    status: str


class VersionResponse(BaseModel):
    """アプリケーション版の応答を表す。"""

    version: str
