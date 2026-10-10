"""署名済み ID の検証に必要な DB API だけを使う正例。"""

from uuid import UUID as _UUID

from pitchlog.authz.token_presentation import TokenPresentation as _TokenPresentation  # ty: ignore
from sqlalchemy import Engine as _Engine  # ty: ignore
from sqlalchemy import text as _text  # ty: ignore


def verify_tenant_id(
    value: str, presentation: _TokenPresentation, engine: _Engine
) -> _UUID | None:
    """照合した ID だけを認証関数へ渡す。"""
    token_id = presentation.decode(value)
    with engine.begin() as connection:
        connection.execute(_text("SELECT authn.verify_token(:token_id)"), {"token_id": token_id})
    return None
