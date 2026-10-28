"""正準座標(1/263)から保存用 Double への単位変換を固定する。"""

import math

import pytest

from pitchlog.sync.first_ball_course import (
    COURSE_DENOMINATOR,
    FirstBallCourseError,
    course_unit_to_double,
)


def test_all_264_canonical_units_are_inside_the_closed_range() -> None:
    """全正準kが有限で0..1に入り、単調である。"""
    values = [course_unit_to_double(str(k)) for k in range(264)]
    assert values[0] == 0.0
    assert values[-1] == 1.0
    assert values == sorted(values)
    assert len(set(values)) == 264
    for value in values:
        assert type(value) is float
        assert math.isfinite(value)
        assert 0.0 <= value <= 1.0


def test_known_units_match_the_definition() -> None:
    """定義 k/263 の代表値と一致する。"""
    assert course_unit_to_double("0") == 0.0
    assert course_unit_to_double("1") == 1 / COURSE_DENOMINATOR
    assert course_unit_to_double("131") == 131 / COURSE_DENOMINATOR
    assert course_unit_to_double("263") == 1.0


@pytest.mark.parametrize(
    "value",
    ["", "264", "-1", " 1", "1.0", "０", 1, None, True],
)
def test_non_canonical_inputs_are_rejected(value: object) -> None:
    """非十進・範囲外・非文字列は保存用値へ変換しない。"""
    with pytest.raises(FirstBallCourseError):
        course_unit_to_double(value)
