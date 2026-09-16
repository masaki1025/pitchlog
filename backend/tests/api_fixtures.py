"""API エラーを検証するテスト用アプリケーションを提供する。"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pitchlog.api.errors import register_exception_handlers


class _ValidationPayload(BaseModel):
    """バリデーション検証用の入力を表す。"""

    player_name: str


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
