"""d4参照のwire符号化を単一箇所で公開する純粋関数。

発行・認可・失効・世代の実在確認は行わない。符号化の結果を権利の証明として
扱わない。特権brokerと開始済みread入口が同じ関数でbyte列を作り、複製実装を
持たない(NFR-018)。
"""

from __future__ import annotations

import base64
from uuid import UUID

_PREFIX = "d4.1."
_VERSION = b"\x01"


class D4ReferenceInvalid(ValueError):
    """符号化の入力が型または範囲の条件を満たさない。入力値を含めない。"""

    def __init__(self) -> None:
        """値を含まない固定の外形を作る。"""
        super().__init__("d4参照の入力が不正")


def encode_d4_reference(tenant_id: UUID, game_id: UUID, generation: int) -> str:
    """tenant・試合・世代の値をowner付きのd4参照へ写す。

    Args:
        tenant_id: 参照の所有tenant。型は厳密にUUIDであること。
        game_id: 対象試合。型は厳密にUUIDであること。
        generation: 1以上2^63未満のint。boolは受け付けない。

    Returns:
        ``d4.1.`` に41byteのbase64url(padなし)を続けた60文字。

    Raises:
        D4ReferenceInvalid: 型の相違または範囲外のとき。
    """
    if (
        type(tenant_id) is not UUID
        or type(game_id) is not UUID
        or type(generation) is not int
        or not 0 < generation < 2**63
    ):
        raise D4ReferenceInvalid
    raw = _VERSION + tenant_id.bytes + game_id.bytes + generation.to_bytes(8, "big")
    return _PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
