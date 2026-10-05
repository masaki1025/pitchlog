"""署名鍵の環境設定とアプリ起動時検証を確認する。"""

import base64
import secrets
from uuid import uuid4

import pytest

from pitchlog.api.app import create_app
from pitchlog.authz.signing_key_config import SigningKeyConfigurationError
from pitchlog.authz.token_presentation import TokenPresentation

_SIGNING_KEY_VARIABLE = "PITCHLOG_TOKEN_SIGNING_KEY_B64"


def test_missing_signing_key_prevents_app_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """鍵が欠落した場合はアプリの生成を拒否する。"""
    monkeypatch.delenv(_SIGNING_KEY_VARIABLE, raising=False)

    with pytest.raises(SigningKeyConfigurationError, match=_SIGNING_KEY_VARIABLE):
        create_app()


@pytest.mark.parametrize("encoded_key", ["A" * 40, "A" * 32])
def test_short_decoded_signing_key_prevents_app_creation(
    monkeypatch: pytest.MonkeyPatch,
    encoded_key: str,
) -> None:
    """文字数が足りても復号後の鍵が短ければ起動を拒否する。"""
    monkeypatch.setenv(_SIGNING_KEY_VARIABLE, encoded_key)

    with pytest.raises(SigningKeyConfigurationError) as error:
        create_app()

    assert "短すぎます" in str(error.value)
    assert encoded_key not in str(error.value)


@pytest.mark.parametrize("invalid_key", ["A" * 43, "A" * 40 + "\n", "非 ASCII"])
def test_invalid_encoding_prevents_app_creation(
    monkeypatch: pytest.MonkeyPatch,
    invalid_key: str,
) -> None:
    """符号化値の padding 欠落、改行、非 ASCII は起動前に拒否する。"""
    monkeypatch.setenv(_SIGNING_KEY_VARIABLE, invalid_key)

    with pytest.raises(SigningKeyConfigurationError) as error:
        create_app()

    assert "設定形式が不正" in str(error.value)
    assert invalid_key not in str(error.value)


def test_alternate_base64_spelling_prevents_app_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同じ 32 バイトへ復号される別表記も拒否する。"""
    key = secrets.token_bytes(32)
    canonical = base64.b64encode(key).decode("ascii")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    final_value = alphabet.index(canonical[-2])
    alternate = canonical[:-2] + alphabet[final_value + 1] + "="
    assert base64.b64decode(alternate, validate=True) == key
    monkeypatch.setenv(_SIGNING_KEY_VARIABLE, alternate)

    with pytest.raises(SigningKeyConfigurationError, match="設定形式が不正"):
        create_app()


def test_create_app_uses_configured_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """復号後の鍵がアプリ内の署名器へ渡ることを確認する。"""
    key = secrets.token_bytes(32)
    monkeypatch.setenv(_SIGNING_KEY_VARIABLE, base64.b64encode(key).decode("ascii"))
    token_id = uuid4()
    value = TokenPresentation(key).encode(token_id)

    app = create_app()

    assert app.state.token_presentation.decode(value) == token_id
