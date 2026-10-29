"""正準座標(1/263 整数)から保存用 Double への写像（**候補・正式採用前**）。

状態: 独立レビュー（2026-10-29、P0=2）により「単一実装として確定・採用済み」
とは扱えない。D18=A と `docs/features/tsk544-t1-state-calculation/plan.md:716`
（既B7の単一TS供給から物理投影値を受け、Pythonで k/263 を再実装しない）に
照らし、正式採用は (a) 単一artifact操作の追加＋264点全数ベクタ＋manifest＋
非作者レビュー＋ADR v0.10/要件 v2.18 の確定ゲートで行う。本関数はその間の
隔離候補であり、成功の証拠・正本の正解値としては使わない。

画面 tap から正準整数 k への変換は artifact 側の既決境界であり、ここでは
行わない。ここが持つのは「既に正準な k」を DB の 0..1 Double へ写す
単位換算だけで、Y 反転・丸め・量子化をやり直さない。
"""

from __future__ import annotations

import math

COURSE_DENOMINATOR = 263
_MAX_COURSE_UNIT = 263


class FirstBallCourseError(ValueError):
    """座標の表現・範囲が保存用の閉形式に合わない。"""


def course_unit_to_double(value: object) -> float:
    """正準整数 k(0..263)を 0..1 の binary64 へ写す。

    Args:
        value: wire の正準座標。十進整数の文字列だけを受け付ける。

    Returns:
        k / 263 の binary64。0 と 263 は厳密に 0.0 と 1.0 になる。

    Raises:
        FirstBallCourseError: 文字列でない、非十進、範囲外、非有限の場合。
    """
    if type(value) is not str or not value.isascii() or not value.isdigit():
        raise FirstBallCourseError("正準座標は十進整数の文字列が必要です")
    unit = int(value)
    if not 0 <= unit <= _MAX_COURSE_UNIT:
        raise FirstBallCourseError("正準座標の範囲外です")
    result = unit / COURSE_DENOMINATOR
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise FirstBallCourseError("保存用座標が 0..1 の有限値になりません")
    return result
