"""FastAPI アプリケーションの生成機構を提供する。"""

import os

from fastapi import APIRouter, FastAPI

from pitchlog.api.errors import register_exception_handlers
from pitchlog.api.routers import lineup_memory, meta, players, team_records
from pitchlog.authz.signing_key_config import require_signing_key_configuration
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import _activate_presentation
from pitchlog.domainrt import verify_domain_artifact

ROUTERS: tuple[APIRouter, ...] = (
    meta.router,
    players.router,
    team_records.router,
    lineup_memory.router,
)
_SIGNING_KEY_VARIABLE = "PITCHLOG_TOKEN_SIGNING_KEY_B64"


def create_app() -> FastAPI:
    """共通設定を適用した FastAPI アプリケーションを作る。

    Returns:
        例外ハンドラと静的列挙したルータを登録済みのアプリケーション。
    """
    signing_key = require_signing_key_configuration(
        _SIGNING_KEY_VARIABLE,
        os.environ.get(_SIGNING_KEY_VARIABLE),
    )
    # CI では Node の版を揃えないため、ここでは artifact だけを照合する。
    # Node の起動と版の照合は domainrt のホストを開くときに行う。
    verify_domain_artifact()
    app = FastAPI(
        title="Pitchlog API",
        version=meta.get_application_version(),
        description="Pitchlog の API を提供する。",
    )
    app.state.token_presentation = TokenPresentation(signing_key)
    register_exception_handlers(app)
    for router in ROUTERS:
        app.include_router(router)
    _activate_presentation(app.state.token_presentation)
    return app
