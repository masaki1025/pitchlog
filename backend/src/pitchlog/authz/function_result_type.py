"""PostgreSQL関数の戻り値宣言を単一のメタデータ表記へ揃える。"""

from __future__ import annotations

import re


def pg_result_type(value: str) -> str:
    """型と列順を保持し、TABLE列境界だけをpg_get_function_resultへ揃える。"""
    normalized = re.sub(r"\bTABLE\s*\(", "TABLE(", value)
    if not normalized.startswith("TABLE(") or not normalized.endswith(")"):
        return normalized
    contents = normalized[6:-1]
    columns = []
    start = 0
    depth = 0
    quoted = False
    for index, character in enumerate(contents):
        if character == '"':
            # 二重quoteのescapeは連続2回の反転となり、間のcommaも無い。
            quoted = not quoted
        elif not quoted:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth < 0:
                    return normalized
            elif character == "," and depth == 0:
                columns.append(contents[start:index].strip())
                start = index + 1
    if quoted or depth != 0:
        return normalized
    columns.append(contents[start:].strip())
    return "TABLE(" + ", ".join(columns) + ")"
