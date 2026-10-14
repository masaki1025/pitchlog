"""署名済み ID のパスワード変更に必要な DB API だけを使う正例。"""

from pitchlog.authz.token_presentation import TokenPresentation as _TokenPresentation  # ty: ignore
from sqlalchemy import Engine as _Engine  # ty: ignore
from sqlalchemy import text as _text  # ty: ignore


def change_password_token(
    value: str,
    current_password: str,
    new_password: str,
    presentation: _TokenPresentation,
    engine: _Engine,
) -> bool:
    """照合した ID だけをパスワード変更関数へ渡す。"""
    token_id = presentation.decode(value)
    with engine.begin() as connection:
        connection.execute(
            _text(
                "SELECT authn.change_password("
                ":token_id, :current_password, :new_password)"
            ),
            {
                "token_id": token_id,
                "current_password": current_password,
                "new_password": new_password,
            },
        )
    return False
