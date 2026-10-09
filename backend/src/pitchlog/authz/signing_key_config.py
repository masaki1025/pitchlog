"""署名鍵の環境設定値を検証する。"""

import base64
import binascii


class SigningKeyConfigurationError(Exception):
    """署名鍵の設定が安全に解釈できない状態を表す。"""


def require_signing_key_configuration(variable_name: str, value: str | None) -> bytes:
    """標準 Base64 の正規形から署名鍵を復号して検証する。

    鍵は CSPRNG で生成した 32 バイト以上の乱数を、標準 Base64 の
    padding 付き正規形で設定する。別表記は受け付けない。

    Args:
        variable_name: 設定を供給する環境変数名。
        value: 環境から取得済みの符号化値。

    Returns:
        復号後の署名鍵。

    Raises:
        SigningKeyConfigurationError: 値の欠落、形式不正、または鍵の不足時。
    """
    if not value:
        raise SigningKeyConfigurationError(f"署名鍵の設定が未設定: {variable_name}")

    try:
        key = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise SigningKeyConfigurationError(
            f"署名鍵の設定形式が不正: {variable_name}"
        ) from None

    if base64.b64encode(key).decode("ascii") != value:
        raise SigningKeyConfigurationError(f"署名鍵の設定形式が不正: {variable_name}")
    if len(key) < 32:
        raise SigningKeyConfigurationError(f"署名鍵の設定が短すぎます: {variable_name}")
    return key
