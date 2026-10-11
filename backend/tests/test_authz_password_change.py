"""署名付き提示値からのパスワード変更境界を DB なしで検査する。"""

import base64
import secrets
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import SQLAlchemyError

from pitchlog.api.app import create_app
from pitchlog.authz import password_change
from pitchlog.authz.password_change import change_password_token
from pitchlog.authz.token_presentation import TokenPresentation

_TOKEN_ID = UUID("a1b2c3d4-e5f6-47a8-9b0c-d1e2f3a4b5c6")


@pytest.fixture
def presentation(monkeypatch: pytest.MonkeyPatch) -> TokenPresentation:
    """起動時に登録した署名器を返す。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    return create_app().state.token_presentation


def test_public_names_are_exact_set() -> None:
    """新モジュールの公開入口を 1 本に固定する。"""
    assert password_change.__all__ == ["change_password_token"]
    assert {name for name in vars(password_change) if not name.startswith("_")} == {
        "change_password_token"
    }


@pytest.mark.parametrize("changed", [True, False])
def test_decoded_id_is_only_database_identity(
    presentation: TokenPresentation, changed: bool
) -> None:
    """署名を照合した ID と 2 つの PW だけを DB 関数へ渡す。"""
    connection_resource = MagicMock()
    connection = connection_resource.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = changed

    assert (
        change_password_token(
            presentation.encode(_TOKEN_ID),
            "current",
            "new",
            presentation,
            connection_resource,
        )
        is changed
    )
    statement, params = connection.execute.call_args.args
    assert str(statement) == (
        "SELECT authn.change_password(:token_id, :current_password, :new_password)"
    )
    assert params == {
        "token_id": _TOKEN_ID,
        "current_password": "current",
        "new_password": "new",
    }
    connection_resource.begin.assert_called_once_with()


def test_unsigned_and_tampered_values_do_not_open_database(
    presentation: TokenPresentation,
) -> None:
    """署名が無い値は DB 接続より前に拒否する。"""
    connection_resource = MagicMock()
    signed = presentation.encode(_TOKEN_ID)
    for value in (str(_TOKEN_ID), "unsigned", signed + "x"):
        assert not change_password_token(
            value, "current", "new", presentation, connection_resource
        )
    connection_resource.begin.assert_not_called()


def test_other_signer_does_not_open_database(presentation: TokenPresentation) -> None:
    """同一鍵で別途作った署名器でも DB 呼び出しを拒否する。"""
    other = TokenPresentation(presentation._key)
    connection_resource = MagicMock()
    with pytest.raises(TypeError, match="設定済みの署名器ではありません"):
        change_password_token(
            other.encode(_TOKEN_ID), "current", "new", other, connection_resource
        )
    connection_resource.begin.assert_not_called()


def test_database_error_does_not_expose_input(presentation: TokenPresentation) -> None:
    """DB 例外の詳細を公開例外へ引き継がない。"""
    value = presentation.encode(_TOKEN_ID)
    connection_resource = MagicMock()
    connection = connection_resource.begin.return_value.__enter__.return_value
    connection.execute.side_effect = SQLAlchemyError(value)
    with pytest.raises(RuntimeError, match="パスワード変更を完了できない") as error:
        change_password_token(
            value, "current", "new", presentation, connection_resource
        )
    assert value not in str(error.value)
    assert error.value.__context__ is None
