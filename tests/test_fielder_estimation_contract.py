"""領域・座標変換・打球方向契約と独立確認の記録を照合する。"""

from __future__ import annotations

import json
import re
from collections import Counter
from fractions import Fraction
from math import lcm
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIELDER_CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/field-regions/fielder_estimation_contract_v1.json"
)
COORDINATE_CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/display-geometry/coordinate_transform_contract_v1.json"
)
DIRECTION_CONTRACT_PATH = (
    REPOSITORY_ROOT / "backend/domain/batted_ball_direction_contract_v1.json"
)
DESIGN_PATH = REPOSITORY_ROOT / "docs/features/field-region-vectors/design.md"
VERIFICATION_CASES = [("5-1", True), ("5-2", True), ("5-3", False)]
HEADING = re.compile(r"^#{1,6}[ \t]+")
CASE_ID_CELL = re.compile(r"`([^`]+)`")
TABLE_SEPARATOR = re.compile(r":?-{3,}:?")


def _section_lines(markdown: str, section_number: str) -> list[str]:
    """節番号の見出しから次の見出しまでの行を返す。

    Args:
        markdown: design.md の本文。
        section_number: 取得する節番号。

    Returns:
        指定した節の本文行。

    Raises:
        AssertionError: 指定した節の見出しが一意でない場合。
    """
    lines = markdown.splitlines()
    section_heading = re.compile(
        rf"^#{{1,6}}[ \t]+{re.escape(section_number)}(?=[.\s]|$)"
    )
    starts = [index for index, line in enumerate(lines) if section_heading.match(line)]
    if len(starts) != 1:
        raise AssertionError(f"design.md の {section_number} 節の見出しが一意でない: {starts}")
    start = starts[0] + 1
    end = next(
        (index for index in range(start, len(lines)) if HEADING.match(lines[index])),
        len(lines),
    )
    return lines[start:end]


def _recorded_case_ids(
    markdown: str, section_number: str, *, require_four_columns: bool = False
) -> list[str]:
    """節内の表からバッククォート付き caseId を抽出する。

    Args:
        markdown: design.md の本文。
        section_number: 表を読む節番号。
        require_four_columns: 独立確認の記録行に 4 列の値を要求するか。

    Returns:
        表に記録された caseId の列。

    Raises:
        AssertionError: 記録行の列数・必須値に欠落がある場合。
    """
    identifiers: list[str] = []
    for line in _section_lines(markdown, section_number):
        row = line.strip()
        if not row.startswith("|"):
            continue
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        first = cells[0]
        if first == "caseId" or TABLE_SEPARATOR.fullmatch(first):
            continue
        match = CASE_ID_CELL.fullmatch(first)
        if match is None:
            if require_four_columns and len(cells) == 4:
                raise AssertionError(f"{section_number} 節: caseId が空か形式が不正: {first!r}")
            continue
        case_id = match.group(1)
        if require_four_columns:
            if len(cells) != 4:
                raise AssertionError(f"{section_number} 節: {case_id} の記録が 4 列ではない")
            for label, value in zip(("caseId", "確認者", "方法", "結果"), cells, strict=True):
                if not value:
                    raise AssertionError(f"{section_number} 節: {case_id} の {label} が空")
        identifiers.append(case_id)
    return identifiers


def _assert_case_id_match(
    contract_ids: list[str], recorded_ids: list[str], section_number: str
) -> None:
    """契約と記録表の caseId が重複なく完全一致することを検査する。

    Args:
        contract_ids: 契約側の caseId。
        recorded_ids: 表側の caseId。
        section_number: エラー表示に使う節番号。

    Raises:
        AssertionError: 重複または片側にしかない caseId がある場合。
    """
    contract_duplicates = sorted(
        case_id for case_id, count in Counter(contract_ids).items() if count > 1
    )
    recorded_duplicates = sorted(
        case_id for case_id, count in Counter(recorded_ids).items() if count > 1
    )
    if contract_duplicates or recorded_duplicates:
        raise AssertionError(
            f"{section_number} 節: caseId の重複: "
            f"契約={contract_duplicates}, design.md={recorded_duplicates}"
        )
    contract_only = sorted(set(contract_ids) - set(recorded_ids))
    recorded_only = sorted(set(recorded_ids) - set(contract_ids))
    if contract_only or recorded_only:
        raise AssertionError(
            f"{section_number} 節: 契約にのみある caseId={contract_only}; "
            f"design.md にのみある caseId={recorded_only}"
        )


def _verify_assets(
    contract_path: Path,
    design_path: Path,
    verification_section: str,
    comparison_section: str | None = None,
    *,
    forbid_seed_provenance: bool = True,
) -> None:
    """契約の独立確認者・典拠と design.md の記録表を検査する。

    Args:
        contract_path: 対象計算契約の JSON ファイル。
        design_path: 独立確認表を含む Markdown ファイル。
        verification_section: 独立確認記録の節番号。
        comparison_section: 三者突合表の節番号。対象外なら None。
        forbid_seed_provenance: 領域シードを期待値の典拠として禁止するか。

    Raises:
        AssertionError: 独立確認の記録または典拠に不整合がある場合。
    """
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    verifier_id = contract["independentVerifierId"]
    if verifier_id == "not-performed":
        raise AssertionError("independentVerifierId が not-performed のまま")
    if not isinstance(verifier_id, str) or not verifier_id:
        raise AssertionError("independentVerifierId が空")

    contract_ids: list[str] = []
    for case in contract["cases"]:
        case_id = case["caseId"]
        contract_ids.append(case_id)
        # 捕球選手推定・座標変換ではシードを期待値の典拠にできない。
        # 打球方向では directionSectors が定義そのものなので許す。
        if forbid_seed_provenance:
            for source in case["provenance"]["sources"]:
                if "field_region_seed" in json.dumps(source, ensure_ascii=False).casefold():
                    raise AssertionError(f"{case_id} の provenance に field_region_seed を含む")

    markdown = design_path.read_text(encoding="utf-8")
    sections = [(verification_section, True)]
    if comparison_section is not None:
        sections.append((comparison_section, False))
    for section_number, require_four_columns in sections:
        recorded_ids = _recorded_case_ids(
            markdown, section_number, require_four_columns=require_four_columns
        )
        _assert_case_id_match(contract_ids, recorded_ids, section_number)


def _write_synthetic_assets(
    tmp_path: Path,
    *,
    verification_rows: list[str] | None = None,
    comparison_rows: list[str] | None = None,
    verifier_id: str = "claude-delegator",
    source_path: str = "legacy/fielder.ts",
) -> tuple[Path, Path]:
    """実リポジトリに依存しない契約と確認表を作る。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_rows: 5-1〜5-3 節の記録行。
        comparison_rows: 6-2 節の突合行。
        verifier_id: 契約の独立確認者 ID。
        source_path: 合成ケースの典拠パス。

    Returns:
        合成した契約と design.md のパス。
    """
    contract_path = tmp_path / "contract.json"
    design_path = tmp_path / "design.md"
    contract = {
        "independentVerifierId": verifier_id,
        "cases": [
            {"caseId": "case-a", "provenance": {"sources": [{"path": source_path}]}}
        ],
    }
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    if verification_rows is None:
        verification_rows = ["| `case-a` | Claude | 独立計算 | 一致 |"]
    if comparison_rows is None:
        comparison_rows = ["| `case-a` | (1, 2) | 3 | 3 | ○ | — |"]
    design_path.write_text(
        "\n".join(
            [
                "# 詳細設計",
                "### 5-1. 確認記録",
                "| caseId | 確認者 | 方法 | 結果 |",
                "| --- | --- | --- | --- |",
                *verification_rows,
                "### 5-2. 座標変換の確認記録",
                "| caseId | 確認者 | 方法 | 結果 |",
                "| --- | --- | --- | --- |",
                *verification_rows,
                "### 5-3. 打球方向の確認記録",
                "| caseId | 確認者 | 方法 | 結果 |",
                "| --- | --- | --- | --- |",
                *verification_rows,
                "### 6-2. 三者突合",
                "| caseId | 入力 | シード | 旧規則 | 一致 | 備考 |",
                "| --- | --- | --- | --- | --- | --- |",
                *comparison_rows,
                "### 6-3. 次の記録",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return contract_path, design_path


@pytest.mark.parametrize(
    (
        "contract_path",
        "verification_section",
        "comparison_section",
        "forbid_seed_provenance",
    ),
    [
        (FIELDER_CONTRACT_PATH, "5-1", "6-2", True),
        (COORDINATE_CONTRACT_PATH, "5-2", None, True),
        (DIRECTION_CONTRACT_PATH, "5-3", None, False),
    ],
    ids=["fielder-estimation", "coordinate-transform", "batted-ball-direction"],
)
def test_repository_verification_record(
    contract_path: Path,
    verification_section: str,
    comparison_section: str | None,
    forbid_seed_provenance: bool,
) -> None:
    """各実契約と design.md の確認記録が全件対応する。

    Args:
        contract_path: 検査する実契約のパス。
        verification_section: 独立確認記録の節番号。
        comparison_section: 三者突合表の節番号。対象外なら None。
        forbid_seed_provenance: 領域シードを典拠に含められない対象か。
    """
    _verify_assets(
        contract_path,
        DESIGN_PATH,
        verification_section,
        comparison_section,
        forbid_seed_provenance=forbid_seed_provenance,
    )


@pytest.mark.parametrize(
    ("verification_section", "forbid_seed_provenance"), VERIFICATION_CASES
)
def test_contract_only_case_id_is_rejected(
    tmp_path: Path, verification_section: str, forbid_seed_provenance: bool
) -> None:
    """契約にしかない caseId を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_section: 検査する独立確認記録の節番号。
        forbid_seed_provenance: 領域シードを典拠に含められない対象か。
    """
    contract_path, design_path = _write_synthetic_assets(tmp_path, verification_rows=[])
    with pytest.raises(
        AssertionError,
        match=rf"{verification_section} 節: 契約にのみある caseId=\['case-a'\]",
    ):
        _verify_assets(
            contract_path,
            design_path,
            verification_section,
            forbid_seed_provenance=forbid_seed_provenance,
        )


@pytest.mark.parametrize(
    ("verification_section", "forbid_seed_provenance"), VERIFICATION_CASES
)
def test_record_only_case_id_is_rejected(
    tmp_path: Path, verification_section: str, forbid_seed_provenance: bool
) -> None:
    """記録表にしかない caseId を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_section: 検査する独立確認記録の節番号。
        forbid_seed_provenance: 領域シードを典拠に含められない対象か。
    """
    contract_path, design_path = _write_synthetic_assets(
        tmp_path,
        verification_rows=[
            "| `case-a` | Claude | 独立計算 | 一致 |",
            "| `case-b` | Claude | 独立計算 | 一致 |",
        ],
    )
    with pytest.raises(
        AssertionError,
        match=rf"{verification_section} 節: .*design.md にのみある caseId=\['case-b'\]",
    ):
        _verify_assets(
            contract_path,
            design_path,
            verification_section,
            forbid_seed_provenance=forbid_seed_provenance,
        )


@pytest.mark.parametrize(
    ("verification_row", "empty_column"),
    [
        ("| `case-a` |  | 独立計算 | 一致 |", "確認者"),
        ("| `case-a` | Claude |  | 一致 |", "方法"),
        ("| `case-a` | Claude | 独立計算 |  |", "結果"),
    ],
)
@pytest.mark.parametrize(
    ("verification_section", "forbid_seed_provenance"), VERIFICATION_CASES
)
def test_empty_verification_column_is_rejected(
    tmp_path: Path,
    verification_row: str,
    empty_column: str,
    verification_section: str,
    forbid_seed_provenance: bool,
) -> None:
    """確認者・方法・結果の空欄を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_row: 空欄を含む独立確認記録の行。
        empty_column: 空欄の列名。
        verification_section: 検査する独立確認記録の節番号。
        forbid_seed_provenance: 領域シードを典拠に含められない対象か。
    """
    contract_path, design_path = _write_synthetic_assets(
        tmp_path, verification_rows=[verification_row]
    )
    with pytest.raises(
        AssertionError, match=f"{verification_section} 節: case-a の {empty_column} が空"
    ):
        _verify_assets(
            contract_path,
            design_path,
            verification_section,
            forbid_seed_provenance=forbid_seed_provenance,
        )


@pytest.mark.parametrize(
    ("verification_section", "forbid_seed_provenance"), VERIFICATION_CASES
)
def test_not_performed_verifier_is_rejected(
    tmp_path: Path, verification_section: str, forbid_seed_provenance: bool
) -> None:
    """独立確認が未実施の契約を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_section: 検査する独立確認記録の節番号。
        forbid_seed_provenance: 領域シードを典拠に含められない対象か。
    """
    contract_path, design_path = _write_synthetic_assets(
        tmp_path, verifier_id="not-performed"
    )
    with pytest.raises(AssertionError, match="independentVerifierId が not-performed のまま"):
        _verify_assets(
            contract_path,
            design_path,
            verification_section,
            forbid_seed_provenance=forbid_seed_provenance,
        )


@pytest.mark.parametrize("verification_section", ["5-1", "5-2"])
def test_seed_provenance_is_rejected(tmp_path: Path, verification_section: str) -> None:
    """期待値の典拠に領域シードを含む契約を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_section: 検査する独立確認記録の節番号。
    """
    contract_path, design_path = _write_synthetic_assets(
        tmp_path, source_path="contracts/field-regions/field_region_seed_v1.json"
    )
    with pytest.raises(AssertionError, match="case-a の provenance に field_region_seed を含む"):
        _verify_assets(contract_path, design_path, verification_section, None)


def test_comparison_only_case_id_is_rejected(tmp_path: Path) -> None:
    """6-2 節にしかない caseId を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
    """
    contract_path, design_path = _write_synthetic_assets(
        tmp_path,
        comparison_rows=[
            "| `case-a` | (1, 2) | 3 | 3 | ○ | — |",
            "| `case-b` | (2, 3) | 4 | 4 | ○ | — |",
        ],
    )
    with pytest.raises(
        AssertionError, match="6-2 節: .*design.md にのみある caseId=\\['case-b'\\]"
    ):
        _verify_assets(contract_path, design_path, "5-1", "6-2")


# --- 期待値そのものの検算(PR #137 の敵対レビュー 1 周目 P0) ---------------
#
# 上の _verify_assets は独立確認の「記録」を照合するだけで、expected の値を
# 検算していない。そのため expected.position を 2 から 9 へ書き換えても緑のまま
# 通ってしまう。以下はその穴を塞ぐ。
#
# 典拠の置き方は契約ごとに変える:
#   座標変換 … 条文(付録B-7・B-3・A-1)から算術を書き直す
#   捕球選手 … 旧の幾何規則(design.md 2-1 が固定コミットから転記したもの)から導く
#   領域シード … 同じ旧の幾何規則と全格子で突合する
#
# 捕球選手の期待値をシードから導かないのは、シードと契約を同時に壊したときに
# 検出できなくなるためである(provenance にシードを禁じているのとは別の理由)。

SCALE = 263

# design.md 2-1「旧システムは多角形を持っていない」が
# `dd03160:frontend/src/lib/fielder.ts`(全 37 行)から転記した規則。
# 座標は旧 263 系(左上原点)。上から順に評価し、当たればそこで決まる。
LEGACY_RECTANGLE_RULES = (
    (2, lambda x, y: y >= 205),
    (3, lambda x, y: x >= 155 and y >= 165),
    (5, lambda x, y: x <= 75 and y >= 165),
    (1, lambda x, y: 105 <= x < 145 and 140 <= y <= 190),
)
# 残りは 9 アンカーへの最近傍(ユークリッド距離の二乗)。
# 比較が厳密 `<` なので、距離が同じなら上から先に並ぶほうが勝つ。
LEGACY_ANCHORS = (
    (8, 116, 66),
    (7, 56, 101),
    (9, 174, 101),
    (6, 88, 144),
    (4, 152, 144),
    (5, 66, 174),
    (3, 166, 174),
    (1, 123, 164),
    (2, 123, 232),
)
# 旧実装は多角形の判定に入る前に x <= 0 || y <= 0 を null(未入力)で弾く。
# 本契約はこれを適用しない —— 付録B-7(v2.13)が「保存座標では 0 が有効な値である」
# と定めたため(design.md 6-3)。差が出るのは次の 2 件だけである。
LEGACY_SENTINEL_EXCEPTIONS = frozenset(
    {"range-edge-left-x0-valid", "range-edge-top-y0-valid"}
)


def _legacy_position(x_old: int, y_old: int) -> int:
    """旧 263 系の整数座標から守備位置を返す(センチネル判定は含まない)。

    Args:
        x_old: 旧 263 系の x(左上原点)。
        y_old: 旧 263 系の y(下向き)。

    Returns:
        守備位置 1〜9。
    """
    for position, rule in LEGACY_RECTANGLE_RULES:
        if rule(x_old, y_old):
            return position
    best_position = 0
    best_distance = None
    for position, ax, ay in LEGACY_ANCHORS:
        distance = (x_old - ax) ** 2 + (y_old - ay) ** 2
        if best_distance is None or distance < best_distance:
            best_distance, best_position = distance, position
    return best_position


def _units_to_legacy(x_units: int, y_units: int) -> tuple[int, int]:
    """保存座標(単位 1/263・左下原点)を旧 263 系(左上原点)へ写す。"""
    return (x_units, SCALE - y_units)


def _expect_units_integer(node: object, label: str) -> int:
    """契約の座標値を整数として取り出す。有理数・十進小数は拒否する。"""
    if isinstance(node, bool) or not isinstance(node, int):
        raise AssertionError(f"{label}: 単位 1/263 の整数でない: {node!r}")
    return node


def test_fielder_expected_positions_are_derived_from_the_legacy_geometry() -> None:
    """捕球選手推定の 31 件を旧の幾何規則から導き直して全件突合する。"""
    contract = json.loads(FIELDER_CONTRACT_PATH.read_text(encoding="utf-8"))
    cases = contract["cases"]
    assert len(cases) == 31

    mismatches: list[str] = []
    exceptions_seen: set[str] = set()
    for case in cases:
        case_id = case["caseId"]
        source = case["input"]
        assert source["coordinateSystem"] == "normalized-bottom-left-units-1-263"
        x_units = _expect_units_integer(source["coordinate"]["x"], f"{case_id}.x")
        y_units = _expect_units_integer(source["coordinate"]["y"], f"{case_id}.y")
        x_old, y_old = _units_to_legacy(x_units, y_units)
        if x_old <= 0 or y_old <= 0:
            # 旧実装ならセンチネルで null になる点。意図的な差として許す。
            assert case_id in LEGACY_SENTINEL_EXCEPTIONS, (
                f"{case_id}: 旧センチネルに当たるが design.md 6-3 の例外に無い"
            )
            exceptions_seen.add(case_id)
        expected = case["expected"]["position"]
        derived = _legacy_position(x_old, y_old)
        if expected != derived:
            mismatches.append(
                f"{case_id}: 期待 {expected} / 旧規則から {derived} "
                f"(保存 ({x_units},{y_units}) → 旧 ({x_old},{y_old}))"
            )

    assert not mismatches, "\n".join(mismatches)
    assert exceptions_seen == LEGACY_SENTINEL_EXCEPTIONS, (
        f"センチネルの例外が記録と一致しない: {sorted(exceptions_seen)}"
    )


# --- 領域シードを旧の幾何規則と全格子で突合する -----------------------------
#
# 3 段目。捕球選手契約をシードから検算すると、シードと契約を一緒に壊したときに
# 通ってしまう。そこでシードのほうは同じ旧の幾何規則と、旧 263 格子の全点で突き合わせる。
#
# 保存座標を 263 倍すると格子点は整数になるが、頂点は垂直二等分線の交点なので
# 分母が大きい。そこで辺ごとに判定式 f(p) = A*px + B*py + C を
# 整数係数へ払う(正の数を掛けるので符号は保たれる)。浮動小数は経由しない。

SEED_PATH = REPOSITORY_ROOT / "contracts/field-regions/field_region_seed_v1.json"
LATTICE_POINT_COUNT = (SCALE + 1) ** 2  # 264 × 264。両端を含む。
SENTINEL_POINT_COUNT = (SCALE + 1) * 2 - 1  # x = 0 の列と y = 0 の行(交点は 1 度だけ)。
COMPARED_POINT_COUNT = LATTICE_POINT_COUNT - SENTINEL_POINT_COUNT  # = 263 × 263。


def _seed_region_edges(region: dict[str, Any]) -> list[tuple[int, int, int, bool]]:
    """1 領域の辺を、整数係数の判定式 (A, B, C, 開いているか) の列へ変換する。"""
    vertices = [
        (
            Fraction(int(v["x"]["numerator"]), int(v["x"]["denominator"])) * SCALE,
            Fraction(int(v["y"]["numerator"]), int(v["y"]["denominator"])) * SCALE,
        )
        for v in region["vertices"]
    ]
    count = len(vertices)
    doubled_area = sum(
        vertices[i][0] * vertices[(i + 1) % count][1]
        - vertices[(i + 1) % count][0] * vertices[i][1]
        for i in range(count)
    )
    counterclockwise = doubled_area > 0
    opened = set(region.get("openEdges", []))
    edges: list[tuple[int, int, int, bool]] = []
    for i in range(count):
        ax, ay = vertices[i]
        bx, by = vertices[(i + 1) % count]
        dx, dy = bx - ax, by - ay
        a, b, c = -dy, dx, dy * ax - dx * ay
        if not counterclockwise:
            a, b, c = -a, -b, -c
        scale = lcm(a.denominator, b.denominator, c.denominator)
        edges.append((int(a * scale), int(b * scale), int(c * scale), i in opened))
    return edges


def _prepare_seed_regions() -> list[tuple[str, int, list[tuple[int, int, int, bool]]]]:
    """領域シードを評価順のまま、整数係数の辺の列へ前処理する。"""
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert seed["tieBreak"] == "first-defined-region-wins", seed["tieBreak"]
    return [
        (region["regionId"], region["position"], _seed_region_edges(region))
        for region in seed["regions"]
    ]


def _seed_position(
    regions: list[tuple[str, int, list[tuple[int, int, int, bool]]]],
    x_units: int,
    y_units: int,
) -> int | None:
    """保存座標の格子点が属する領域の守備位置を返す。属さなければ None。

    tieBreak が first-defined-region-wins なので、先に定義された領域が勝つ。
    開いた辺の上に乗る点はその領域に含めない。
    """
    for _region_id, position, edges in regions:
        for a, b, c, is_open in edges:
            value = a * x_units + b * y_units + c
            if value < 0 or (value == 0 and is_open):
                break
        else:
            return position
    return None


def test_region_seed_matches_the_legacy_geometry_on_every_lattice_point() -> None:
    """領域シードを旧の幾何規則と旧 263 格子の全点で突合する。

    センチネル(x <= 0 または y <= 0)は旧実装が未入力として弾く範囲であり、
    本契約は付録B-7(v2.13)によりこれを適用しない(design.md 6-3)。
    多角形は未入力の概念を持てないため、その 527 点は比較対象から外す。
    """
    regions = _prepare_seed_regions()
    differences: list[str] = []
    sentinel_count = 0
    compared_count = 0

    for y_old in range(SCALE + 1):
        for x_old in range(SCALE + 1):
            if x_old <= 0 or y_old <= 0:
                sentinel_count += 1
                continue
            compared_count += 1
            actual = _seed_position(regions, x_old, SCALE - y_old)
            expected = _legacy_position(x_old, y_old)
            if actual != expected:
                if len(differences) < 20:
                    differences.append(
                        f"旧(x={x_old}, y={y_old}): 旧規則 {expected} / シード {actual}"
                    )

    assert sentinel_count == SENTINEL_POINT_COUNT, sentinel_count
    assert compared_count == COMPARED_POINT_COUNT, compared_count
    assert not differences, (
        f"旧の幾何規則と一致しない点がある(先頭 {len(differences)} 件):\n"
        + "\n".join(differences)
    )


def test_region_seed_covers_every_non_sentinel_lattice_point() -> None:
    """センチネルを除く全格子点が、いずれかの領域に属する(穴がない)。"""
    regions = _prepare_seed_regions()
    uncovered = [
        (x_old, y_old)
        for y_old in range(1, SCALE + 1)
        for x_old in range(1, SCALE + 1)
        if _seed_position(regions, x_old, SCALE - y_old) is None
    ]
    assert not uncovered, f"どの領域にも属さない点が {len(uncovered)} 件: {uncovered[:10]}"


def test_region_seed_open_edge_is_honoured() -> None:
    """投手の矩形の開いた右辺が効いている(旧 x < 145 の再現)。

    design.md 2-1 の旧条件は `105 <= x < 145` であり、右辺だけが開く。
    開辺を無視して多角形を閉じると、x = 145 の縦線上で旧規則と食い違う。
    """
    regions = _prepare_seed_regions()
    closed = [
        (region_id, position, [(a, b, c, False) for a, b, c, _ in edges])
        for region_id, position, edges in regions
    ]
    divergences = [
        y_old
        for y_old in range(140, 191)
        if _seed_position(closed, 145, SCALE - y_old)
        != _seed_position(regions, 145, SCALE - y_old)
    ]
    assert divergences, "開辺を閉じても結果が変わらない(開辺が効いていない)"
    for y_old in divergences:
        assert _seed_position(regions, 145, SCALE - y_old) == _legacy_position(145, y_old)
