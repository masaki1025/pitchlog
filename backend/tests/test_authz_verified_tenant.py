"""署名照合と DB 呼び出しの順序を DB なしで検査する。"""

import secrets
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import SQLAlchemyError

from pitchlog.authz import verified_tenant
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import verify_tenant_id

_TOKEN_ID = UUID("a1b2c3d4-e5f6-47a8-9b0c-d1e2f3a4b5c6")
_TENANT_ID = UUID("b1b2c3d4-e5f6-47a8-9b0c-d1e2f3a4b5c6")


def test_public_route_is_exact_set() -> None:
    """このモジュールの公開入口を 1 関数に固定する。"""
    public_names = {name for name in vars(verified_tenant) if not name.startswith("_")}
    assert verified_tenant.__all__ == ["verify_tenant_id"]
    assert public_names == {"verify_tenant_id"}


def test_signed_value_reaches_db_as_decoded_uuid() -> None:
    """署名照合後の ID を固定された認証関数へ渡して結果を返す。"""
    presentation = TokenPresentation(secrets.token_bytes(32))
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = _TENANT_ID

    assert verify_tenant_id(presentation.encode(_TOKEN_ID), presentation, engine) == (
        _TENANT_ID
    )

    statement, params = connection.execute.call_args.args
    assert str(statement) == "SELECT authn.verify_token(:token_id)"
    assert params == {"token_id": _TOKEN_ID}
    engine.begin.assert_called_once_with()


def test_unsigned_id_and_tampered_value_never_open_db() -> None:
    """生の UUID と改ざんされた提示値から DB 呼び出しに到達できない。"""
    presentation = TokenPresentation(secrets.token_bytes(32))
    engine = MagicMock()
    signed = presentation.encode(_TOKEN_ID)
    forged = f"{_TENANT_ID}.{signed.split('.')[1]}"

    assert verify_tenant_id(cast(str, _TOKEN_ID), presentation, engine) is None
    assert verify_tenant_id(str(_TOKEN_ID), presentation, engine) is None
    assert verify_tenant_id(forged, presentation, engine) is None
    engine.begin.assert_not_called()


def test_fake_decoder_cannot_supply_unsigned_id() -> None:
    """同名の decode を持つ別オブジェクトも認証関数へ ID を渡せない。"""
    engine = MagicMock()
    fake_presentation = MagicMock()
    fake_presentation.decode.return_value = _TOKEN_ID

    with pytest.raises(TypeError, match="署名器の型が不正です"):
        verify_tenant_id("opaque", fake_presentation, engine)

    fake_presentation.decode.assert_not_called()
    engine.begin.assert_not_called()


def test_db_null_is_same_public_result_for_invalid_records() -> None:
    """DB 側の無効理由に関係なく NULL を None のまま返す。"""
    presentation = TokenPresentation(secrets.token_bytes(32))
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = None

    assert (
        verify_tenant_id(presentation.encode(_TOKEN_ID), presentation, engine) is None
    )


def test_db_error_message_omits_token_id() -> None:
    """DB の例外メッセージに ID があっても公開例外には載せない。"""
    presentation = TokenPresentation(secrets.token_bytes(32))
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.side_effect = SQLAlchemyError(str(_TOKEN_ID))
    value = presentation.encode(_TOKEN_ID)

    with pytest.raises(RuntimeError, match="トークンの照合を完了できない") as error:
        verify_tenant_id(value, presentation, engine)

    assert str(_TOKEN_ID) not in str(error.value)
    assert value not in str(error.value)
    assert error.value.__context__ is None
