"""署名済みトークン提示値の正規形と検証を確認する。"""

import base64
import hmac
import secrets
from uuid import UUID

import pytest

from pitchlog.authz import token_presentation
from pitchlog.authz.token_presentation import TokenPresentation

_TOKEN_ID = UUID("a1b2c3d4-e5f6-47a8-9b0c-d1e2f3a4b5c6")
_CANONICAL_ID = str(_TOKEN_ID)


def test_public_symbols_are_exact_set() -> None:
    """モジュールの公開シンボルは署名器だけに固定する。"""
    public_names = {
        name for name in vars(token_presentation) if not name.startswith("_")
    }

    assert token_presentation.__all__ == ["TokenPresentation"]
    assert public_names == {"TokenPresentation"}


def test_encode_and_decode_use_canonical_uuid_as_hmac_message() -> None:
    """提示値の往復と HMAC 対象の UUID 正規形を確認する。"""
    key = secrets.token_bytes(32)
    signer = TokenPresentation(key)
    expected_signature = hmac.digest(key, _CANONICAL_ID.encode("ascii"), "sha256").hex()

    value = signer.encode(_TOKEN_ID)

    assert value == f"{_CANONICAL_ID}.{expected_signature}"
    assert signer.decode(value) == _TOKEN_ID


@pytest.mark.parametrize(
    "invalid_id",
    [
        _CANONICAL_ID.upper(),
        _CANONICAL_ID.replace("-", ""),
        "{" + _CANONICAL_ID + "}",
        " " + _CANONICAL_ID,
        _CANONICAL_ID + " ",
    ],
)
def test_alternate_uuid_spellings_are_rejected(invalid_id: str) -> None:
    """同じ UUID に到達する別表記は有効な署名付きでも拒否する。"""
    key = secrets.token_bytes(32)
    signature = hmac.digest(key, invalid_id.encode("ascii"), "sha256").hex()
    value = f"{invalid_id}.{signature}"

    with pytest.raises(ValueError, match="提示値の形式または署名が不正です"):
        TokenPresentation(key).decode(value)


def test_alternate_signature_encodings_are_rejected() -> None:
    """同じ署名バイト列の別表記は受け付けない。"""
    signer = TokenPresentation(secrets.token_bytes(32))
    value = signer.encode(_TOKEN_ID)
    canonical_id, signature_hex = value.split(".")
    signature_bytes = bytes.fromhex(signature_hex)
    upper_hex = signature_hex.upper()
    standard_base64 = base64.b64encode(signature_bytes).decode("ascii")
    urlsafe_base64 = base64.urlsafe_b64encode(signature_bytes).decode("ascii")

    for alternate in (
        upper_hex,
        standard_base64,
        standard_base64.rstrip("="),
        urlsafe_base64,
        urlsafe_base64.rstrip("="),
    ):
        with pytest.raises(ValueError, match="提示値の形式または署名が不正です"):
            signer.decode(f"{canonical_id}.{alternate}")


@pytest.mark.parametrize(
    "invalid_value",
    [
        "",
        f"{_CANONICAL_ID}.",
        f"{_CANONICAL_ID}.{'0' * 63}",
        f"{_CANONICAL_ID}.{'0' * 65}",
        f"{_CANONICAL_ID}.{'G' * 64}",
        f"{_CANONICAL_ID}.{'0' * 64}=",
        f"{_CANONICAL_ID}.{'0' * 64}\n",
    ],
)
def test_malformed_presentation_is_rejected(invalid_value: str) -> None:
    """署名長・文字種・余分な文字が違う提示値を拒否する。"""
    with pytest.raises(ValueError, match="提示値の形式または署名が不正です"):
        TokenPresentation(secrets.token_bytes(32)).decode(invalid_value)


def test_signature_from_another_key_is_rejected_without_leaking_input() -> None:
    """異なる鍵の署名を拒否し、例外には提示値を含めない。"""
    value = TokenPresentation(secrets.token_bytes(32)).encode(_TOKEN_ID)

    with pytest.raises(ValueError) as error:
        TokenPresentation(secrets.token_bytes(32)).decode(value)

    assert value not in str(error.value)
    assert _CANONICAL_ID not in str(error.value)


def test_modified_id_is_rejected() -> None:
    """正規形の ID だけを差し替えても署名照合で拒否する。"""
    signer = TokenPresentation(secrets.token_bytes(32))
    value = signer.encode(_TOKEN_ID)
    alternate_id = UUID("b1b2c3d4-e5f6-47a8-9b0c-d1e2f3a4b5c6")
    forged_value = f"{alternate_id}.{value.split('.')[1]}"

    with pytest.raises(ValueError, match="提示値の形式または署名が不正です"):
        signer.decode(forged_value)
