"""署名照合と DB 呼び出しの順序を DB なしで検査する。"""

import base64
import secrets
import traceback
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import SQLAlchemyError

from pitchlog.api.app import create_app
from pitchlog.authz import verified_tenant
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import logout_token, verify_tenant_id

_TOKEN_ID = UUID("a1b2c3d4-e5f6-47a8-9b0c-d1e2f3a4b5c6")
_TENANT_ID = UUID("b1b2c3d4-e5f6-47a8-9b0c-d1e2f3a4b5c6")
_EXPIRES_AT = datetime(2026, 10, 10, tzinfo=UTC)


@pytest.fixture
def configured_presentation(monkeypatch: pytest.MonkeyPatch) -> TokenPresentation:
    """起動時に検証した鍵を持つ署名器を返す。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    return create_app().state.token_presentation


def test_public_route_is_exact_set() -> None:
    """このモジュールの公開入口を 2 関数に固定する。"""
    public_names = {name for name in vars(verified_tenant) if not name.startswith("_")}
    assert verified_tenant.__all__ == ["verify_tenant_id", "logout_token"]
    assert public_names == {"verify_tenant_id", "logout_token"}


def test_signed_value_reaches_db_as_decoded_uuid(
    configured_presentation: TokenPresentation,
) -> None:
    """署名照合後の ID を固定された認証関数へ渡して結果を返す。"""
    presentation = configured_presentation
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.one.return_value = (_TENANT_ID, _EXPIRES_AT)

    assert verify_tenant_id(presentation.encode(_TOKEN_ID), presentation, engine) == (
        _TENANT_ID,
        _EXPIRES_AT,
    )

    statement, params = connection.execute.call_args.args
    assert str(statement) == (
        "SELECT tenant_id, expires_at FROM authn.verify_token(:token_id)"
    )
    assert params == {"token_id": _TOKEN_ID}
    engine.begin.assert_called_once_with()


def test_unsigned_id_and_tampered_value_never_open_db(
    configured_presentation: TokenPresentation,
) -> None:
    """生の UUID と改ざんされた提示値から DB 呼び出しに到達できない。"""
    presentation = configured_presentation
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


def test_unconfigured_signers_never_reach_authn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正規鍵と同じ鍵でも別途作った署名器を DB 到達前に拒否する。"""
    configured_key = secrets.token_bytes(32)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(configured_key).decode("ascii"),
    )
    create_app()
    engine = MagicMock()

    for key in (configured_key, secrets.token_bytes(32)):
        unconfigured = TokenPresentation(key)
        value = unconfigured.encode(_TOKEN_ID)
        for action in (verify_tenant_id, logout_token):
            with pytest.raises(TypeError, match="設定済みの署名器ではありません"):
                action(value, unconfigured, engine)

    engine.begin.assert_not_called()


def test_replaced_startup_signer_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """鍵の入れ替え後は旧アプリの署名器を DB 到達前に拒否する。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    old_presentation = create_app().state.token_presentation
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    new_presentation = create_app().state.token_presentation
    engine = MagicMock()

    for action in (verify_tenant_id, logout_token):
        with pytest.raises(TypeError, match="設定済みの署名器ではありません"):
            action(old_presentation.encode(_TOKEN_ID), old_presentation, engine)

    engine.begin.assert_not_called()
    assert new_presentation is not old_presentation


def test_registered_signer_with_replaced_key_never_reaches_authn(
    configured_presentation: TokenPresentation,
) -> None:
    """起動後に署名器の鍵を差し替えても DB 到達できない。"""
    configured_presentation._key = secrets.token_bytes(32)
    value = configured_presentation.encode(_TOKEN_ID)
    engine = MagicMock()

    for action in (verify_tenant_id, logout_token):
        with pytest.raises(TypeError, match="設定済みの署名器ではありません"):
            action(value, configured_presentation, engine)

    engine.begin.assert_not_called()


def test_db_null_is_same_public_result_for_invalid_records(
    configured_presentation: TokenPresentation,
) -> None:
    """DB 側の無効理由に関係なく NULL を None のまま返す。"""
    presentation = configured_presentation
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.one.return_value = (None, None)

    assert (
        verify_tenant_id(presentation.encode(_TOKEN_ID), presentation, engine) is None
    )


@pytest.mark.parametrize(
    "invalid_row",
    (
        (_TENANT_ID, None),
        (None, _EXPIRES_AT),
        (_TENANT_ID, datetime(2026, 10, 10)),
    ),
)
def test_incomplete_db_result_is_not_accepted(
    configured_presentation: TokenPresentation,
    invalid_row: tuple[UUID | None, datetime | None],
) -> None:
    """片方だけの値や時差のない期限は照合成功として扱わない。"""
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.one.return_value = invalid_row

    with pytest.raises(RuntimeError, match="トークンの照合結果が不正です"):
        verify_tenant_id(
            configured_presentation.encode(_TOKEN_ID), configured_presentation, engine
        )


def test_db_error_message_omits_token_id(
    configured_presentation: TokenPresentation,
) -> None:
    """DB の例外メッセージに ID があっても公開例外には載せない。"""
    presentation = configured_presentation
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.side_effect = SQLAlchemyError(str(_TOKEN_ID))
    value = presentation.encode(_TOKEN_ID)

    with pytest.raises(RuntimeError, match="トークンの照合を完了できない") as error:
        verify_tenant_id(value, presentation, engine)

    assert str(_TOKEN_ID) not in str(error.value)
    assert value not in str(error.value)
    assert error.value.__context__ is None


@pytest.mark.parametrize(
    "invalid",
    ("raw_uuid", "tampered_signature", "unsigned", "another_key"),
)
def test_logout_rejects_unsigned_values_without_db(
    invalid: str, configured_presentation: TokenPresentation
) -> None:
    """署名の無い ID や別鍵の提示値を DB に渡さない。"""
    presentation = configured_presentation
    signed = presentation.encode(_TOKEN_ID)
    if invalid == "raw_uuid":
        value = str(_TOKEN_ID)
    elif invalid == "tampered_signature":
        value = signed[:-1] + ("0" if signed[-1] != "0" else "1")
    elif invalid == "unsigned":
        value = "unsigned"
    else:
        value = TokenPresentation(secrets.token_bytes(32)).encode(_TOKEN_ID)
    engine = MagicMock()

    assert logout_token(value, presentation, engine) is None
    assert engine.begin.call_count == 0
    assert engine.begin.return_value.__enter__.return_value.execute.call_count == 0


def test_logout_rejects_fake_and_subclassed_presentation_without_db() -> None:
    """同名の decode と派生クラスを DB 到達前に拒否する。"""

    class DerivedTokenPresentation(TokenPresentation):
        """厳密な型検査を確認するための派生クラス。"""

    engine = MagicMock()
    fake = MagicMock()
    fake.decode.return_value = _TOKEN_ID
    derived = DerivedTokenPresentation(secrets.token_bytes(32))
    for presentation in (cast(TokenPresentation, fake), derived):
        with pytest.raises(TypeError, match="署名器の型が不正です"):
            logout_token("opaque", presentation, engine)

    fake.decode.assert_not_called()
    assert engine.begin.call_count == 0
    assert engine.begin.return_value.__enter__.return_value.execute.call_count == 0


def test_signed_logout_calls_db_once_and_returns_none(
    configured_presentation: TokenPresentation,
) -> None:
    """署名済み ID だけを authn.logout に 1 回渡し void を維持する。"""
    presentation = configured_presentation
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value

    assert logout_token(presentation.encode(_TOKEN_ID), presentation, engine) is None
    assert engine.begin.call_count == 1
    assert connection.execute.call_count == 1
    statement, parameters = connection.execute.call_args.args
    assert str(statement) == "SELECT authn.logout(:token_id)"
    assert parameters == {"token_id": _TOKEN_ID}


def test_logout_db_error_omits_presentation_and_id_from_full_traceback(
    configured_presentation: TokenPresentation,
) -> None:
    """DB 例外の文脈を切り、メッセージと全トレースに入力を残さない。"""
    presentation = configured_presentation
    value = presentation.encode(_TOKEN_ID)
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.side_effect = SQLAlchemyError(f"{_TOKEN_ID} {value}")

    with pytest.raises(
        RuntimeError, match="トークンのログアウトを完了できない"
    ) as error:
        logout_token(value, presentation, engine)

    assert engine.begin.call_count == 1
    assert connection.execute.call_count == 1
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    assert str(_TOKEN_ID) not in str(error.value)
    assert value not in str(error.value)
    formatted = "".join(traceback.format_exception(error.value))
    assert str(_TOKEN_ID) not in formatted
    assert value not in formatted
