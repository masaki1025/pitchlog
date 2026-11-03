"""座標量子化の単一 artifact を JSON 境界だけで呼ぶ。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pitchlog.domainrt.host import NodeDomainHost


class CourseQuantizationError(ValueError):
    """量子化の入出力が閉じた JSON 境界に適合しない。"""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """重複キーを補修しない。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CourseQuantizationError("量子化応答の重複キー")
        result[key] = value
    return result


def _constant(_value: str) -> object:
    """非有限 JSON 定数を拒否する。"""
    raise CourseQuantizationError("量子化応答の不正定数")


@dataclass(frozen=True, slots=True)
class CourseQuantizationAdapter:
    """検証済み実ホストへ量子化操作を委譲する（計算を持たない）。"""

    host: NodeDomainHost

    def execute(self, _case_id: str, request: object) -> dict[str, object]:
        """同一 artifact の全応答封筒を無損失で返す。

        Args:
            _case_id: runner が要求と対応付ける case ID。
            request: artifact の量子化要求。

        Returns:
            成否を含む閉じた JSON 封筒。

        Raises:
            CourseQuantizationError: 応答の外形が閉契約と異なる場合。
        """
        response = self.host.call(
            "quantizeCourse",
            json.dumps(
                request, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ),
        )
        try:
            value = json.loads(
                response, object_pairs_hook=_unique, parse_constant=_constant
            )
        except (ValueError, TypeError) as error:
            raise CourseQuantizationError("量子化応答を解釈できません") from error
        if not isinstance(value, dict) or type(value.get("ok")) is not bool:
            raise CourseQuantizationError("量子化応答の封筒が不正")
        if value["ok"]:
            body = value.get("value")
            if (
                set(value) != {"ok", "value"}
                or not isinstance(body, dict)
                or set(body) != {"unit", "x", "y"}
                or any(not isinstance(body[key], str) for key in body)
            ):
                raise CourseQuantizationError("量子化成功応答が不正")
        else:
            body = value.get("error")
            if (
                set(value) != {"ok", "error"}
                or not isinstance(body, dict)
                or set(body) != {"code"}
                or body["code"]
                not in {
                    "INVALID_REQUEST",
                    "INVALID_JSON",
                    "INVALID_SIZE",
                    "INVALID_VIEW",
                    "INVALID_DECIMAL",
                    "OUT_OF_RANGE",
                }
            ):
                raise CourseQuantizationError("量子化拒否応答が不正")
        return value
