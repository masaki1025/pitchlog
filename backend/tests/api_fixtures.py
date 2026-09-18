"""API エラーを検証するテスト用アプリケーションを提供する。"""

import logging
from collections.abc import Generator

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pitchlog.api.errors import register_exception_handlers
from pitchlog.api.schemas.base import BaseSchema


class _ValidationPayload(BaseModel):
    """バリデーション検証用の入力を表す。"""

    player_name: str


class _ArrayItemPayload(BaseSchema):
    """配列要素の入力を表す。"""

    name: str


class _ArrayValidationPayload(BaseSchema):
    """配列を含むバリデーション検証用の入力を表す。"""

    player_name: str
    players: list[_ArrayItemPayload]


@pytest.fixture
def error_logger() -> Generator[logging.Logger, None, None]:
    """API エラーロガーの ``disabled`` 状態からテストを隔離する。

    TSK-387 の各テスト冒頭の表明は隔離後にロガーが有効であることを確認し、
    本フィクスチャは状態の退避・一時解除・復元を担う。

    Yields:
        テスト中だけ有効化した API エラーロガー。
    """
    logger = logging.getLogger("pitchlog.api.errors")
    previous_disabled = logger.disabled
    logger.disabled = False
    try:
        yield logger
    finally:
        logger.disabled = previous_disabled


def create_error_test_app() -> FastAPI:
    """例外ハンドラを登録した検証用アプリケーションを作る。

    Returns:
        エラー応答を検証できる素の FastAPI アプリケーション。
    """
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/validation")
    async def validate_payload(payload: _ValidationPayload) -> dict[str, str]:
        """バリデーションを通過した入力を返す。

        Args:
            payload: 検証対象の入力。

        Returns:
            検証を通過した選手名。
        """
        return {"player_name": payload.player_name}

    @app.get("/forbidden")
    async def raise_forbidden() -> None:
        """403 の HTTP 例外を送出する。"""
        raise HTTPException(status_code=403)

    @app.get("/unhandled")
    async def raise_unhandled() -> None:
        """未捕捉例外を送出する。"""
        raise RuntimeError("意図的なテスト例外")

    return app


def create_schema_validation_test_app() -> FastAPI:
    """配列を含む入力の検証を確認する一時アプリケーションを作る。

    Returns:
        検証エラーの発生箇所を確認できる素の FastAPI アプリケーション。
    """
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/schema-validation")
    async def validate_array_payload(
        payload: _ArrayValidationPayload,
    ) -> dict[str, str]:
        """バリデーションを通過した入力を返す。

        Args:
            payload: 検証対象の入力。

        Returns:
            検証を通過した選手名。
        """
        return {"player_name": payload.player_name}

    return app
