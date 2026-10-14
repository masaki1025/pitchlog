"""チームログインが許可された DB API だけへ到達する正例。"""

from datetime import datetime as _datetime

from pitchlog.authz.token_presentation import TokenPresentation as _TokenPresentation  # ty: ignore
from sqlalchemy import Engine as _Engine  # ty: ignore
from sqlalchemy import text as _text  # ty: ignore


def login_attempt(
    team_name: str,
    password: str,
    source: str,
    presentation: _TokenPresentation,
    engine: _Engine,
) -> tuple[str, _datetime] | int:
    """認証関数をトランザクション内で呼び出す。"""
    with engine.begin() as connection:
        connection.execute(
            _text("SELECT authn.login_attempt(:team_name, :password, :source)"),
            {"team_name": team_name, "password": password, "source": source},
        )
    return 0
