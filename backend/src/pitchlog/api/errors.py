"""API 例外を共通のエラー封筒へ変換する。"""

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from pitchlog.api.schemas.base import ErrorDetail, ErrorEnvelope, ErrorField

_LOGGER = logging.getLogger(__name__)
_VALIDATION_ERROR_MESSAGE = "入力に誤りがあります"
_NOT_FOUND_ERROR_MESSAGE = "対象が見つかりません"
_REQUEST_ERROR_MESSAGE = "リクエストを処理できません"
_INTERNAL_SERVER_ERROR_MESSAGE = "サーバー内部でエラーが発生しました"


def _error_response(
    status_code: int,
    message: str,
    fields: list[ErrorField] | None = None,
) -> JSONResponse:
    """共通のエラー封筒を JSON 応答へ変換する。

    Args:
        status_code: 応答する HTTP ステータスコード。
        message: 利用者へ返す固定文言。
        fields: バリデーションエラーの発生箇所。

    Returns:
        共通のエラー封筒を持つ JSON 応答。
    """
    envelope = ErrorEnvelope(error=ErrorDetail(message=message, fields=fields))
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(exclude_none=True),
    )


async def _request_validation_exception_handler(
    _request: Request,
    exception: Exception,
) -> JSONResponse:
    """リクエストのバリデーション失敗を共通封筒へ写す。

    Args:
        _request: 例外が発生したリクエスト。
        exception: FastAPI が送出したバリデーション例外。

    Returns:
        発生箇所だけを含む 422 応答。
    """
    validation_exception = cast(RequestValidationError, exception)
    fields = [
        ErrorField(location=".".join(str(item) for item in error["loc"]))
        for error in validation_exception.errors()
    ]
    _LOGGER.info("リクエストの入力検証に失敗しました。")
    return _error_response(
        status_code=422,
        message=_VALIDATION_ERROR_MESSAGE,
        fields=fields,
    )


async def _http_exception_handler(
    _request: Request,
    exception: Exception,
) -> JSONResponse:
    """HTTP 例外を共通封筒へ写す。

    Args:
        _request: 例外が発生したリクエスト。
        exception: Starlette が送出した HTTP 例外。

    Returns:
        対応する HTTP ステータスの共通エラー応答。
    """
    http_exception = cast(StarletteHTTPException, exception)
    if http_exception.status_code == 403:
        _LOGGER.error("403 の HTTP 例外を 404 として応答します。")
        return _error_response(status_code=404, message=_NOT_FOUND_ERROR_MESSAGE)

    _LOGGER.info("HTTP 例外を共通エラー封筒へ変換しました。")
    if http_exception.status_code == 404:
        return _error_response(status_code=404, message=_NOT_FOUND_ERROR_MESSAGE)
    return _error_response(
        status_code=http_exception.status_code,
        message=_REQUEST_ERROR_MESSAGE,
    )


async def _unhandled_exception_handler(
    _request: Request,
    _exception: Exception,
) -> JSONResponse:
    """未捕捉例外を内部情報を出さない応答へ写す。

    Args:
        _request: 例外が発生したリクエスト。
        _exception: 捕捉した例外。

    Returns:
        固定文言だけを含む 500 応答。
    """
    _LOGGER.exception("未捕捉例外を処理しました。")
    return _error_response(status_code=500, message=_INTERNAL_SERVER_ERROR_MESSAGE)


def register_exception_handlers(app: FastAPI) -> None:
    """FastAPI インスタンスへ共通例外ハンドラを登録する。

    Args:
        app: 例外ハンドラを登録する FastAPI インスタンス。
    """
    app.add_exception_handler(
        RequestValidationError,
        _request_validation_exception_handler,
    )
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
