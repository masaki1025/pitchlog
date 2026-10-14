"""領域・座標変換契約と独立確認の記録を照合する。"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIELDER_CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/field-regions/fielder_estimation_contract_v1.json"
)
COORDINATE_CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/display-geometry/coordinate_transform_contract_v1.json"
)
DESIGN_PATH = REPOSITORY_ROOT / "docs/features/field-region-vectors/design.md"
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
) -> None:
    """契約の独立確認者・典拠と design.md の記録表を検査する。

    Args:
        contract_path: 対象計算契約の JSON ファイル。
        design_path: 独立確認表を含む Markdown ファイル。
        verification_section: 独立確認記録の節番号。
        comparison_section: 三者突合表の節番号。対象外なら None。

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
        verification_rows: 5-1・5-2 節の記録行。
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
    ("contract_path", "verification_section", "comparison_section"),
    [
        (FIELDER_CONTRACT_PATH, "5-1", "6-2"),
        (COORDINATE_CONTRACT_PATH, "5-2", None),
    ],
    ids=["fielder-estimation", "coordinate-transform"],
)
def test_repository_verification_record(
    contract_path: Path, verification_section: str, comparison_section: str | None
) -> None:
    """各実契約と design.md の確認記録が全件対応する。

    Args:
        contract_path: 検査する実契約のパス。
        verification_section: 独立確認記録の節番号。
        comparison_section: 三者突合表の節番号。対象外なら None。
    """
    _verify_assets(contract_path, DESIGN_PATH, verification_section, comparison_section)


@pytest.mark.parametrize("verification_section", ["5-1", "5-2"])
def test_contract_only_case_id_is_rejected(
    tmp_path: Path, verification_section: str
) -> None:
    """契約にしかない caseId を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_section: 検査する独立確認記録の節番号。
    """
    contract_path, design_path = _write_synthetic_assets(tmp_path, verification_rows=[])
    with pytest.raises(
        AssertionError,
        match=rf"{verification_section} 節: 契約にのみある caseId=\['case-a'\]",
    ):
        _verify_assets(contract_path, design_path, verification_section, None)


@pytest.mark.parametrize("verification_section", ["5-1", "5-2"])
def test_record_only_case_id_is_rejected(
    tmp_path: Path, verification_section: str
) -> None:
    """記録表にしかない caseId を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_section: 検査する独立確認記録の節番号。
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
        _verify_assets(contract_path, design_path, verification_section, None)


@pytest.mark.parametrize(
    ("verification_row", "empty_column"),
    [
        ("| `case-a` |  | 独立計算 | 一致 |", "確認者"),
        ("| `case-a` | Claude |  | 一致 |", "方法"),
        ("| `case-a` | Claude | 独立計算 |  |", "結果"),
    ],
)
@pytest.mark.parametrize("verification_section", ["5-1", "5-2"])
def test_empty_verification_column_is_rejected(
    tmp_path: Path,
    verification_row: str,
    empty_column: str,
    verification_section: str,
) -> None:
    """確認者・方法・結果の空欄を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_row: 空欄を含む独立確認記録の行。
        empty_column: 空欄の列名。
        verification_section: 検査する独立確認記録の節番号。
    """
    contract_path, design_path = _write_synthetic_assets(
        tmp_path, verification_rows=[verification_row]
    )
    with pytest.raises(
        AssertionError, match=f"{verification_section} 節: case-a の {empty_column} が空"
    ):
        _verify_assets(contract_path, design_path, verification_section, None)


@pytest.mark.parametrize("verification_section", ["5-1", "5-2"])
def test_not_performed_verifier_is_rejected(
    tmp_path: Path, verification_section: str
) -> None:
    """独立確認が未実施の契約を拒否する。

    Args:
        tmp_path: 合成ファイルの作成先。
        verification_section: 検査する独立確認記録の節番号。
    """
    contract_path, design_path = _write_synthetic_assets(
        tmp_path, verifier_id="not-performed"
    )
    with pytest.raises(AssertionError, match="independentVerifierId が not-performed のまま"):
        _verify_assets(contract_path, design_path, verification_section, None)


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
