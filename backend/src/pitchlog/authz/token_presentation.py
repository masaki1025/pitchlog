"""トークン ID の提示値を署名し、署名済み提示値から ID を取り出す。"""

import hmac as _hmac
import re as _re
from uuid import UUID as _UUID

__all__ = ["TokenPresentation"]

_PRESENTATION_PATTERN = _re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.([0-9a-f]{64})"
)


class TokenPresentation:
    """鍵を受け取り、単一の正規形で提示値を発行・検証する。"""

    __slots__ = ("_key",)

    def __init__(self, key: bytes) -> None:
        """署名鍵を保持する。鍵の設定と起動時検証は呼び出し元が行う。"""
        if not isinstance(key, bytes):
            raise TypeError("署名鍵の型が不正です")
        self._key = key

    def encode(self, token_id: _UUID) -> str:
        """UUID の小文字ハイフン付き表記を署名して提示値を返す。"""
        if not isinstance(token_id, _UUID):
            raise TypeError("トークン ID の型が不正です")
        canonical_id = str(token_id)
        signature = _hmac.digest(self._key, canonical_id.encode("ascii"), "sha256")
        return f"{canonical_id}.{signature.hex()}"

    def decode(self, value: str) -> _UUID:
        """正規形と署名を照合し、成功時だけ UUID を返す。"""
        if not isinstance(value, str):
            raise ValueError("提示値の形式または署名が不正です")
        match = _PRESENTATION_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError("提示値の形式または署名が不正です")
        canonical_id, signature_hex = match.groups()
        expected = _hmac.digest(self._key, canonical_id.encode("ascii"), "sha256")
        if not _hmac.compare_digest(expected, bytes.fromhex(signature_hex)):
            raise ValueError("提示値の形式または署名が不正です")
        return _UUID(canonical_id)
