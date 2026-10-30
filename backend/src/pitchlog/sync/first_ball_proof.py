"""提示済みV12だけを厳密に読む。権利・nonce・端末資格を発行しない。"""

from __future__ import annotations

import base64
import hashlib
import re


class FirstBallProofError(ValueError):
    """秘密を含めないV12形式拒否。"""


def proof_digest(value: object) -> bytes:
    """canonicalなraw32byteのV12をSHA256へ写す。

    Args:
        value: paddingなしbase64urlの提示済みV12。

    Returns:
        raw32byteに対する32byte digest。

    Raises:
        FirstBallProofError: canonical形式でない場合。
    """
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is None:
        raise FirstBallProofError("記録権証明の形式が不正")
    raw = base64.urlsafe_b64decode(value + "=")
    if (
        len(raw) != 32
        or base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value
    ):
        raise FirstBallProofError("記録権証明の形式が不正")
    return hashlib.sha256(raw).digest()
