"""署名済み ID のログアウトに必要な DB API だけを使う正例。"""

from pitchlog.authz.token_presentation import TokenPresentation as _TokenPresentation  # ty: ignore
from sqlalchemy import Engine as _Engine  # ty: ignore
from sqlalchemy import text as _text  # ty: ignore


def logout_token(value: str, presentation: _TokenPresentation, engine: _Engine) -> None:
    """照合した ID だけをログアウト関数へ渡す。"""
    token_id = presentation.decode(value)
    with engine.begin() as connection:
        connection.execute(_text("SELECT authn.logout(:token_id)"), {"token_id": token_id})
