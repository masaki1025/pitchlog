"""O5 の対象となる不変条件違反を列挙する(SP 6-3 の O5)。

O5 は「決定的」かつ「未使用 D5 の新規適用の取引内」で検出した不変条件違反だけを
対象にする。対象は実装が列挙し、列挙の外の例外は B7 のまま残す。
prefix_path と ordering の双方から import するため、循環を作らない独立の
モジュールに置く。
"""

from __future__ import annotations

from typing import Final, Literal

type O5Code = Literal[
    "player_mapping_type",
    "d1_multiple_current_rows",
    "event_without_slot",
    "d3_advance_failed",
    "d2_row_type",
    "d2_out_of_range",
    "d2_no_gap",
]

# 列挙の正。送出箇所(raise O5InvariantViolation)との一致は pytest が AST で突合する。
O5_CODES: Final[frozenset[O5Code]] = frozenset(
    {
        "player_mapping_type",
        "d1_multiple_current_rows",
        "event_without_slot",
        "d3_advance_failed",
        "d2_row_type",
        "d2_out_of_range",
        "d2_no_gap",
    }
)


class O5InvariantViolation(RuntimeError):
    """O5: 未使用 D5 の新規適用の取引内で検出した決定的な不変条件違反(SP 6-3)。

    当該イベントの取引を全取消してから B3 + A5「拒否」(理由 O5)へ写す。
    ``P1PreconditionError`` の部分型にはしない(区分付き前提違反の捕捉に
    吸われて T9 や再送出へ流れないようにする)。

    Attributes:
        code: 列挙済みの O5 の識別子。
    """

    def __init__(self, code: O5Code, message: str) -> None:
        """列挙済みの識別子と、利用者入力を含まない固定文言を保持する。

        Args:
            code: ``O5_CODES`` の一つ。
            message: 検出した不変条件違反の固定文言。
        """
        super().__init__(message)
        self.code: O5Code = code
