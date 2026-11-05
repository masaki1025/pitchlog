"""PostgreSQL関数の戻り値宣言を単一のメタデータ表記へ揃える。"""

from __future__ import annotations

import re


def pg_result_type(value: str) -> str:
    """pg_get_function_resultと同じTABLE括弧の表記を返す。"""
    return re.sub(r"\bTABLE\s*\(", "TABLE(", value)
