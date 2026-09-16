"""FastAPI アプリケーションの生成機構を提供する。"""

from fastapi import APIRouter, FastAPI

from pitchlog.api.errors import register_exception_handlers
from pitchlog.api.routers import meta

ROUTERS: tuple[APIRouter, ...] = (meta.router,)


def create_app() -> FastAPI:
    """共通設定を適用した FastAPI アプリケーションを作る。

    Returns:
        例外ハンドラと静的列挙したルータを登録済みのアプリケーション。
    """
    app = FastAPI()
    register_exception_handlers(app)
    for router in ROUTERS:
        app.include_router(router)
    return app
