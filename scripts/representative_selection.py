"""規範行の述語から宣言済みの順序で代表入力座標を選ぶ。"""

from __future__ import annotations

import copy
import itertools
from typing import Any


class RepresentativeSelectionError(ValueError):
    """代表値の宣言または述語を解釈できない場合を表す。"""


def validate_policy(document: dict[str, Any]) -> None:
    """代表値の実装上の約束を閉じた形で検査する。

    Args:
        document: 宣言された代表値選択規則。
    """
    required = {
        "schemaVersion", "policyId", "authority", "rationale", "axisOrder",
        "valueOrder", "predicateEvaluation", "candidateSelection", "unconstrainedAxis",
    }
    if set(document) != required or document.get("schemaVersion") != 1:
        raise RepresentativeSelectionError("代表値規則の列または版が不正")
    string_fields = required - {"schemaVersion"}
    if not all(isinstance(document[key], str) and document[key] for key in string_fields):
        raise RepresentativeSelectionError("代表値規則の文字列が不正")
    if document["authority"] != "implementation-convention-not-requirements-or-adr":
        raise RepresentativeSelectionError("代表値規則の由来が不正")
    if document["axisOrder"] != "descriptor-declaration-order":
        raise RepresentativeSelectionError("代表値規則の軸順序に未対応")
    if document["predicateEvaluation"] != "appendix-e-1-predicate-ast":
        raise RepresentativeSelectionError("代表値規則の述語体系に未対応")
    if document["valueOrder"] not in (
        "descriptor-declaration-order", "reverse-descriptor-declaration-order"
    ):
        raise RepresentativeSelectionError("代表値規則の値順序に未対応")
    if document["candidateSelection"] not in (
        "first-satisfying-cartesian-product", "last-satisfying-cartesian-product"
    ):
        raise RepresentativeSelectionError("代表値規則の候補選択に未対応")
    if document["unconstrainedAxis"] != "first-value-in-declared-order":
        raise RepresentativeSelectionError("代表値規則の非制約軸に未対応")


def axis_values(descriptor: dict[str, Any], groups: tuple[str, ...]) -> dict[str, list[Any]]:
    """descriptor の宣言順を保って軸値域を取得する。

    Args:
        descriptor: 入力軸 descriptor。
        groups: 対象軸群。

    Returns:
        軸 ID ごとの値域。
    """
    values: dict[str, list[Any]] = {}
    for group in groups:
        axes = descriptor.get(group)
        if not isinstance(axes, list):
            raise RepresentativeSelectionError(f"入力軸群が不正: {group}")
        for axis in axes:
            if not isinstance(axis, dict) or not isinstance(axis.get("axisId"), str):
                raise RepresentativeSelectionError("入力軸が不正")
            axis_id = axis["axisId"]
            classification = axis.get("classification")
            if classification == "boundary-partition":
                field = "boundaryValues"
            elif classification == "finite-enumerable":
                field = "values"
            else:
                raise RepresentativeSelectionError(f"軸分類が不正: {axis_id}")
            candidates = axis.get(field)
            if axis_id in values or not isinstance(candidates, list) or not candidates:
                raise RepresentativeSelectionError(f"軸値域が不正: {axis_id}")
            values[axis_id] = candidates
    return values


def predicate_axes(predicate: dict[str, Any]) -> set[str]:
    """述語が参照する軸 ID を取得する。

    Args:
        predicate: 付録 E-1 型の述語。

    Returns:
        参照する軸 ID の集合。
    """
    operation = predicate.get("op")
    if operation in ("eq", "in", "gte", "lte"):
        axis_id = predicate.get("axisId")
        if not isinstance(axis_id, str):
            raise RepresentativeSelectionError("述語の軸 ID が不正")
        return {axis_id}
    if operation not in ("and", "or", "not"):
        raise RepresentativeSelectionError(f"未対応の述語演算子: {operation}")
    args = predicate.get("args")
    if not isinstance(args, list) or not args or not all(isinstance(arg, dict) for arg in args):
        raise RepresentativeSelectionError("述語の引数が不正")
    if operation == "not" and len(args) != 1:
        raise RepresentativeSelectionError("否定述語の引数が不正")
    return set().union(*(predicate_axes(arg) for arg in args))


def _same_literal(left: Any, right: Any) -> bool:
    """真偽値と整数を混同せず JSON literal を比較する。"""
    return type(left) is type(right) and left == right


def predicate_holds(predicate: dict[str, Any], coordinate: dict[str, Any]) -> bool:
    """具体的な座標で述語の真偽を評価する。

    Args:
        predicate: 評価する述語。
        coordinate: 軸 ID と具体値の対応。

    Returns:
        述語が成立するなら真。
    """
    operation = predicate.get("op")
    if operation in ("eq", "in", "gte", "lte"):
        axis_id = predicate.get("axisId")
        if not isinstance(axis_id, str) or axis_id not in coordinate:
            raise RepresentativeSelectionError(f"座標に述語の軸がない: {axis_id}")
        actual = coordinate[axis_id]
        if operation == "eq":
            return _same_literal(actual, predicate.get("value"))
        if operation == "in":
            candidates = predicate.get("values")
            if not isinstance(candidates, list) or not candidates:
                raise RepresentativeSelectionError("包含述語の値が不正")
            return any(_same_literal(actual, candidate) for candidate in candidates)
        expected = predicate.get("value")
        if type(actual) not in (int, float) or type(expected) not in (int, float):
            raise RepresentativeSelectionError("大小比較は数値の軸値だけに対応")
        return actual >= expected if operation == "gte" else actual <= expected
    args = predicate.get("args")
    if not isinstance(args, list) or not args or not all(isinstance(arg, dict) for arg in args):
        raise RepresentativeSelectionError("述語の引数が不正")
    if operation == "and":
        return all(predicate_holds(arg, coordinate) for arg in args)
    if operation == "or":
        return any(predicate_holds(arg, coordinate) for arg in args)
    if operation == "not" and len(args) == 1:
        return not predicate_holds(args[0], coordinate)
    raise RepresentativeSelectionError(f"未対応の述語演算子: {operation}")


def _positive_equalities(predicate: dict[str, Any]) -> dict[str, Any]:
    """連言に含まれる正の等値条件を固定候補として取り出す。"""
    operation = predicate.get("op")
    if operation == "eq":
        return {predicate["axisId"]: copy.deepcopy(predicate["value"])}
    if operation != "and":
        return {}
    fixed: dict[str, Any] = {}
    for child in predicate["args"]:
        for axis_id, value in _positive_equalities(child).items():
            if axis_id in fixed and not _same_literal(fixed[axis_id], value):
                raise RepresentativeSelectionError(f"等値条件が矛盾する: {axis_id}")
            fixed[axis_id] = value
    return fixed


def select_coordinate(
    predicate: dict[str, Any],
    values_by_axis: dict[str, list[Any]],
    coordinate_axes: list[str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """宣言された順序で述語を満たす最初の座標を選ぶ。

    Args:
        predicate: 規範行の事前条件。
        values_by_axis: descriptor 順の軸値域。
        coordinate_axes: ケースへ置く軸 ID。descriptor 順。
        policy: 資産側の代表値規則。

    Returns:
        代表入力座標。
    """
    validate_policy(policy)
    used_axes = predicate_axes(predicate)
    if not used_axes <= set(coordinate_axes) or not set(coordinate_axes) <= set(values_by_axis):
        raise RepresentativeSelectionError("述語または座標に未宣言の軸がある")
    descriptor_order = [axis_id for axis_id in values_by_axis if axis_id in coordinate_axes]
    if coordinate_axes != descriptor_order or len(coordinate_axes) != len(set(coordinate_axes)):
        raise RepresentativeSelectionError("座標軸の順序が descriptor と異なる")
    ordered_values = {
        axis_id: list(reversed(values))
        if policy["valueOrder"] == "reverse-descriptor-declaration-order"
        else values
        for axis_id, values in values_by_axis.items()
    }
    fixed = _positive_equalities(predicate)
    for axis_id, value in fixed.items():
        if not any(_same_literal(value, item) for item in values_by_axis[axis_id]):
            raise RepresentativeSelectionError(f"等値条件が descriptor の値域外: {axis_id}")
    coordinate = {axis_id: copy.deepcopy(ordered_values[axis_id][0]) for axis_id in coordinate_axes}
    coordinate.update(fixed)
    free_axes = [axis_id for axis_id in coordinate_axes if axis_id in used_axes - fixed.keys()]
    selected: dict[str, Any] | None = None
    for choice in itertools.product(*(ordered_values[axis_id] for axis_id in free_axes)):
        candidate = {**coordinate, **dict(zip(free_axes, choice, strict=True))}
        if predicate_holds(predicate, candidate):
            selected = candidate
            if policy["candidateSelection"] == "first-satisfying-cartesian-product":
                return selected
    if selected is not None:
        return selected
    raise RepresentativeSelectionError("述語を満たす代表値が descriptor 内にない")


def validate_coordinate(
    predicate: dict[str, Any],
    coordinate: dict[str, Any],
    values_by_axis: dict[str, list[Any]],
    coordinate_axes: list[str],
    policy: dict[str, Any],
) -> None:
    """展開結果の座標が宣言された代表値そのものか検査する。

    Args:
        predicate: 規範行の事前条件。
        coordinate: 検査対象の座標。
        values_by_axis: descriptor 順の軸値域。
        coordinate_axes: ケースへ置く軸 ID。
        policy: 資産側の代表値規則。
    """
    expected = select_coordinate(predicate, values_by_axis, coordinate_axes, policy)
    if coordinate != expected:
        raise RepresentativeSelectionError("展開結果が宣言済みの代表値規則に一致しない")
