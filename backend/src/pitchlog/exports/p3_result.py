"""P3保存payloadから打席結果の正本だけを取り出す。"""

from __future__ import annotations

from typing import Any


def saved_result_id(payload: dict[str, Any]) -> str | None:
    """V7の ``calculation.request.t1.resultId`` だけを打席結果として返す。

    通常投球の ``observations`` には resultId が存在しない。観測側や最上位の
    t1 へ読み替えて比較条件を緩めない。
    """
    calculation = payload.get("calculation")
    if type(calculation) is not dict:
        return None
    request = calculation.get("request")
    if type(request) is not dict:
        return None
    t1 = request.get("t1")
    if type(t1) is not dict:
        return None
    result = t1.get("resultId")
    return result if type(result) is str else None
