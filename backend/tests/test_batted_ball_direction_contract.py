"""打球方向ベクタを領域シードと語彙シードに照合する。"""

from __future__ import annotations

import copy
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "backend/domain/batted_ball_direction_contract_v1.json"
SEED_PATH = ROOT / "contracts/field-regions/field_region_seed_v1.json"
VOCABULARY_PATH = ROOT / "contracts/vocabulary/input_vocabulary_v1.json"
GEOMETRY_PATH = ROOT / "contracts/display_geometry_263_v1.json"
COORDINATE_SYSTEM = "normalized-bottom-left-units-1-263"
SUFFIXES = ("left", "left-center", "center", "right-center", "right")
DISPLAY_NAMES = {
    "left": "レフト",
    "left-center": "左中間",
    "center": "センター",
    "right-center": "右中間",
    "right": "ライト",
    "foul-territory": "ファウル地域",
}
RELATIVE_NAMES = {
    "pull": "引っ張り",
    "center-return": "センター返し",
    "opposite": "流し",
    "foul-territory": "ファウル地域",
}
BATTER_SIDES = {"right", "left"}
CASE_COUNTS = {"interior": 30, "boundary": 24, "outside": 12}


def _read_json(path: Path) -> dict[str, Any]:
    """JSON のオブジェクトを読む。

    Args:
        path: 読み込む JSON のパス。

    Returns:
        JSON のトップレベルオブジェクト。
    """
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _parse_integer_literal(token: str) -> int:
    """負のゼロ以外の整数リテラルを受理する。

    Args:
        token: JSON の整数リテラル。

    Returns:
        整数値。

    Raises:
        AssertionError: 負のゼロの場合。
    """
    assert token != "-0", "負のゼロは禁止"
    return int(token)


def _reject_non_integer_literal(token: str) -> int:
    """小数・指数・非有限値を拒否する。

    Args:
        token: JSON の数値リテラル。

    Raises:
        AssertionError: 常に拒否する。
    """
    raise AssertionError(f"整数以外の数値リテラルは禁止: {token}")


def _cross(first: dict[str, int], second: dict[str, int]) -> int:
    """2 つの整数ベクトルの外積を返す。

    Args:
        first: 第 1 ベクトル。
        second: 第 2 ベクトル。

    Returns:
        符号付きの整数外積。
    """
    return first["x"] * second["y"] - first["y"] * second["x"]


def _relative_direction(physical: str, batter_side: str) -> str:
    """物理方向を打席左右に応じて 2:1:2 で畳む。

    Args:
        physical: 物理方向の ID。
        batter_side: right または left。

    Returns:
        打者相対方向の ID。
    """
    suffix = physical.removeprefix("batted-ball-direction.")
    if suffix == "foul-territory":
        return "batter-relative.foul-territory"
    if suffix == "center":
        return "batter-relative.center-return"
    if (batter_side == "right" and suffix in ("left", "left-center")) or (
        batter_side == "left" and suffix in ("right", "right-center")
    ):
        return "batter-relative.pull"
    return "batter-relative.opposite"


def _sector_matches(
    vector: dict[str, int], sectors: list[dict[str, Any]]
) -> list[str]:
    """左翼線側の区分が共有境界を取る規則で該当区分を求める。

    Args:
        vector: 本塁から点への整数ベクトル。
        sectors: 左翼線から右翼線へ並ぶ 5 区分。

    Returns:
        外積条件を満たす区分 ID の列。
    """
    matches: list[str] = []
    for index, sector in enumerate(sectors):
        start_cross = _cross(sector["startRay"], vector)
        end_cross = _cross(vector, sector["endRay"])
        # 共有レイは前の区分の終端に含め、次の区分の始端から除く。
        if (start_cross <= 0 if index == 0 else start_cross < 0) and end_cross <= 0:
            matches.append(sector["directionId"])
    return matches


def _in_fair_wedge(vector: dict[str, int], sectors: list[dict[str, Any]]) -> bool:
    """左右のファウルラインの内側にあるかを整数外積で判定する。

    Args:
        vector: 本塁から点への整数ベクトル。
        sectors: 左翼線から右翼線へ並ぶ 5 区分。

    Returns:
        両ファウルラインを含む扇形の内側なら True。
    """
    return (
        _cross(sectors[0]["startRay"], vector) <= 0
        and _cross(vector, sectors[-1]["endRay"]) <= 0
    )


def _assert_seed_topology(seed: dict[str, Any]) -> None:
    """方向区分の順序・原点・レイの接続を確認する。

    Args:
        seed: 領域シード。

    Raises:
        AssertionError: 5 区分が連続した扇形を作らない場合。
    """
    sectors = seed["directionSectors"]
    assert len(sectors) == 5, "方向区分は 5 件"
    assert [sector["directionId"] for sector in sectors] == [
        f"batted-ball-direction.{suffix}" for suffix in SUFFIXES
    ], "方向区分の順序が違う"
    assert seed["directionOrigin"] == {"x": 123, "y": 39}
    assert sectors[0]["startRay"] == {"x": -47, "y": 53}
    assert sectors[-1]["endRay"] == {"x": 47, "y": 53}
    assert seed["source"]["directionSource"] == {
        "geometryPath": "contracts/display_geometry_263_v1.json",
        "geometryFields": ["field.home", "field.first", "field.third"],
        "requirementPath": "docs/requirements/requirements-pitchlog-2026-07-22.md",
        "requirementClause": "付録A-3 打球方向",
        "derivation": "equal-angle-five-way-approximated-by-integer-rays",
    }
    for index, sector in enumerate(sectors):
        start = sector["startRay"]
        end = sector["endRay"]
        for ray in (start, end):
            assert set(ray) == {"x", "y"}
            assert all(type(value) is int for value in ray.values())
            assert ray != {"x": 0, "y": 0}
            assert math.gcd(abs(ray["x"]), abs(ray["y"])) == 1
        assert _cross(start, end) < 0, "区分レイが左翼線から右翼線の順でない"
        if index:
            assert sectors[index - 1]["endRay"] == start, (
                "隣接区分の境界レイが一致しない"
            )


def _assert_geometry_source(seed: dict[str, Any]) -> None:
    """方向の原点と外側レイを表示幾何の基準点と照合する。

    Args:
        seed: 領域シード。
    """
    geometry = _read_json(GEOMETRY_PATH)
    size = geometry["size"]
    field = geometry["field"]
    home = field["home"]
    assert seed["directionOrigin"] == {"x": home[0], "y": size - home[1]}
    for field_name, ray in (
        ("third", seed["directionSectors"][0]["startRay"]),
        ("first", seed["directionSectors"][-1]["endRay"]),
    ):
        base = field[field_name]
        assert ray == {"x": base[0] - home[0], "y": home[1] - base[1]}


def _validate_assets(
    contract_path: Path, seed_path: Path, vocabulary_path: Path
) -> None:
    """契約の全ケースをシードの外積分類と語彙に照合する。

    Args:
        contract_path: 打球方向契約の JSON ファイル。
        seed_path: 領域シードの JSON ファイル。
        vocabulary_path: 入力語彙シードの JSON ファイル。

    Raises:
        AssertionError: 構造・参照・分類・畳み込みに不整合がある場合。
    """
    contract = _read_json(contract_path)
    seed = _read_json(seed_path)
    vocabulary = _read_json(vocabulary_path)
    _assert_seed_topology(seed)
    _assert_geometry_source(seed)
    assert contract["schemaVersion"] == 1
    assert contract["version"] == "batted_ball_direction_contract_v1"
    assert contract["calculation"] == "batted-ball-direction"
    assert contract["boundaryTieBreak"] == "first-defined-direction-sector-wins"
    assert "共有レイ上の点" in contract["boundaryRule"]
    axes = [axis for axis in vocabulary["axes"] if axis["axisId"] == "batted-ball-type"]
    assert len(axes) == 1
    type_ids = {entry["id"] for entry in axes[0]["entries"]}
    assert type_ids == {
        "batted-ball-type.ground",
        "batted-ball-type.line",
        "batted-ball-type.fly",
    }
    sectors = seed["directionSectors"]
    origin = seed["directionOrigin"]
    observed_types: set[str] = set()
    observed_sides: set[str] = set()
    observed_physical: set[str] = set()
    observed_ids: set[str] = set()
    counts: Counter[str] = Counter()
    group_points: dict[str, set[tuple[int, int]]] = defaultdict(set)
    group_pairs: dict[tuple[str, int, int], set[tuple[str, str]]] = defaultdict(set)
    for case in contract["cases"]:
        case_id = case["caseId"]
        assert case_id not in observed_ids, f"{case_id}: caseId が重複"
        observed_ids.add(case_id)
        group = case_id.split("-", 1)[0]
        assert group in CASE_COUNTS
        counts[group] += 1
        assert set(case["input"]) == {"coordinate", "battedBallType", "batterSide"}
        assert set(case["expected"]) == {
            "physicalDirection",
            "physicalDirectionDisplayName",
            "batterRelative",
            "batterRelativeDisplayName",
        }
        point = case["input"]["coordinate"]
        assert set(point) == {"x", "y", "coordinateSystem"}
        assert point["coordinateSystem"] == COORDINATE_SYSTEM
        x, y = point["x"], point["y"]
        assert type(x) is type(y) is int and 0 <= x <= 263 and 0 <= y <= 263
        assert (x, y) != (origin["x"], origin["y"])
        batted_type = case["input"]["battedBallType"]
        assert batted_type in type_ids, f"{case_id}: 語彙にない打球種別"
        side = case["input"]["batterSide"]
        assert side in BATTER_SIDES
        observed_types.add(batted_type)
        observed_sides.add(side)
        group_points[group].add((x, y))
        group_pairs[(group, x, y)].add((batted_type, side))
        vector = {"x": x - origin["x"], "y": y - origin["y"]}
        matches = _sector_matches(vector, sectors)
        assert len(matches) <= 1, f"{case_id}: 複数の方向区分に重複"
        fair = _in_fair_wedge(vector, sectors)
        assert bool(matches) == fair, f"{case_id}: 方向区分に隙間がある"
        if group == "interior":
            assert len(matches) == 1
            sector = next(s for s in sectors if s["directionId"] == matches[0])
            assert _cross(sector["startRay"], vector) < 0
            assert _cross(vector, sector["endRay"]) < 0
        elif group == "boundary":
            assert sum(_cross(s["endRay"], vector) == 0 for s in sectors[:-1]) == 1
        else:
            assert not fair
        expected = case["expected"]
        physical = matches[0] if matches else "batted-ball-direction.foul-territory"
        assert expected["physicalDirection"] == physical, (
            f"{case_id}: 物理方向が外積分類と不一致"
        )
        observed_physical.add(physical)
        suffix = physical.removeprefix("batted-ball-direction.")
        assert expected["physicalDirectionDisplayName"] == DISPLAY_NAMES[suffix]
        relative = _relative_direction(physical, side)
        assert expected["batterRelative"] == relative, (
            f"{case_id}: 打者相対の畳み込みが不一致"
        )
        assert expected["batterRelativeDisplayName"] == RELATIVE_NAMES[
            relative.removeprefix("batter-relative.")
        ]
        provenance = case["provenance"]
        assert any(
            source["path"] == "contracts/field-regions/field_region_seed_v1.json"
            for source in provenance["sources"]
        )
        if not matches:
            assert provenance["subjectKind"] == "contract-defined"
            assert "本契約" in provenance["decision"]
        else:
            assert provenance["subjectKind"] == "clause"
    assert counts == CASE_COUNTS
    assert {group: len(points) for group, points in group_points.items()} == {
        "interior": 5,
        "boundary": 4,
        "outside": 2,
    }
    all_pairs = {(kind, side) for kind in type_ids for side in BATTER_SIDES}
    assert all(pairs == all_pairs for pairs in group_pairs.values())
    assert observed_types == type_ids
    assert observed_sides == BATTER_SIDES
    assert observed_physical == {
        *(f"batted-ball-direction.{suffix}" for suffix in SUFFIXES),
        "batted-ball-direction.foul-territory",
    }


def _write_assets(
    tmp_path: Path,
    contract: dict[str, Any],
    seed: dict[str, Any],
    vocabulary: dict[str, Any],
) -> tuple[Path, Path, Path]:
    """負例に使う合成 JSON を一時ディレクトリへ書く。

    Args:
        tmp_path: 合成ファイルの保存先。
        contract: 書き込む契約。
        seed: 書き込む領域シード。
        vocabulary: 書き込む語彙シード。

    Returns:
        契約・領域シード・語彙シードのパス。
    """
    paths = (
        tmp_path / "contract.json",
        tmp_path / "seed.json",
        tmp_path / "vocab.json",
    )
    for path, value in zip(paths, (contract, seed, vocabulary), strict=True):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return paths


def test_repository_batted_ball_direction_contract() -> None:
    """実契約の 66 件を整数外積と語彙で全件照合する。"""
    _validate_assets(CONTRACT_PATH, SEED_PATH, VOCABULARY_PATH)


def test_contract_uses_only_integer_numeric_literals() -> None:
    """打球方向契約の数値リテラルを整数だけに限る。"""
    json.loads(
        CONTRACT_PATH.read_text(encoding="utf-8"),
        parse_int=_parse_integer_literal,
        parse_float=_reject_non_integer_literal,
        parse_constant=_reject_non_integer_literal,
    )


def test_direction_rays_approximate_equal_angles() -> None:
    """整数レイの理想 5 等分角からの誤差を 0.01 度以内に抑える。"""
    sectors = _read_json(SEED_PATH)["directionSectors"]
    left = sectors[0]["startRay"]
    right = sectors[-1]["endRay"]
    left_angle = math.atan2(left["y"], left["x"])
    right_angle = math.atan2(right["y"], right["x"])
    for index, sector in enumerate(sectors[:-1], start=1):
        ray = sector["endRay"]
        ideal = left_angle + (right_angle - left_angle) * index / 5
        error_degrees = math.degrees(abs(math.atan2(ray["y"], ray["x"]) - ideal))
        assert error_degrees <= 0.01, (index, error_degrees)


def test_fair_grid_has_exactly_one_sector() -> None:
    """263 系の全格子点で扇形の内外と分類の一意性を確認する。"""
    seed = _read_json(SEED_PATH)
    sectors = seed["directionSectors"]
    origin = seed["directionOrigin"]
    for x in range(264):
        for y in range(264):
            vector = {"x": x - origin["x"], "y": y - origin["y"]}
            if vector == {"x": 0, "y": 0}:
                continue
            matches = _sector_matches(vector, sectors)
            assert len(matches) == int(_in_fair_wedge(vector, sectors)), (x, y)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unknown-type", "語彙にない打球種別"),
        ("wrong-relative", "打者相対の畳み込みが不一致"),
        ("sector-gap", "隣接区分の境界レイが一致しない"),
    ],
)
def test_invalid_synthetic_assets_are_rejected(
    tmp_path: Path, mutation: str, message: str
) -> None:
    """語彙・畳み込み・区分の隙間の負例を拒否する。

    Args:
        tmp_path: 合成ファイルの保存先。
        mutation: 注入する不整合。
        message: 期待する拒否理由。
    """
    contract = copy.deepcopy(_read_json(CONTRACT_PATH))
    seed = copy.deepcopy(_read_json(SEED_PATH))
    vocabulary = copy.deepcopy(_read_json(VOCABULARY_PATH))
    if mutation == "unknown-type":
        contract["cases"][0]["input"]["battedBallType"] = "batted-ball-type.unknown"
    elif mutation == "wrong-relative":
        contract["cases"][0]["expected"]["batterRelative"] = (
            "batter-relative.opposite"
        )
    else:
        seed["directionSectors"][1]["startRay"]["x"] += 2
    paths = _write_assets(tmp_path, contract, seed, vocabulary)
    with pytest.raises(AssertionError, match=message):
        _validate_assets(*paths)
