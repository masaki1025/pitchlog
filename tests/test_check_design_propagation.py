"""同期プロトコル設計の伝播突合検査を検証する。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_design_propagation.py"
FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "sync-protocol-source.txt"
DESIGN = REPOSITORY_ROOT / "docs" / "design" / "sync-protocol.md"


def _load_checker() -> Any:
    """テスト対象をsys.pathの変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(
        "check_design_propagation_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


@pytest.fixture(scope="module")
def manifest() -> dict[str, checker.ManifestRelation]:
    """検査用に実マニフェストを読む。"""
    return checker.load_manifest(REPOSITORY_ROOT / checker.DEFAULT_MANIFEST)


@pytest.fixture(scope="module")
def defects() -> dict[str, checker.Defect]:
    """検査用に実欠陥oracleを読む。"""
    return checker.load_defects(REPOSITORY_ROOT / checker.DEFAULT_DEFECTS)


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _finding_ids(result: subprocess.CompletedProcess[str]) -> set[str]:
    return {
        line.split(":", 1)[0]
        for line in result.stderr.splitlines()
        if ": [" in line
    }


DEFECT_CHECK_CASES = (
    (
        "SP-01",
        """### 6-3. 境界結果
| B4 | A5 が退避を返す |
### 7-2. キュー遷移
| 遷移 | 条件 |
| 未送信 → 退避済み | ACK の A5 が「退避」を返す |
""",
        """### 7-2. キュー遷移
| 遷移 | 条件 |
| 未送信 → 退避済み | ACK の境界結果が **B4** であること |
""",
    ),
    (
        "SP-02",
        """### 6-3. 境界結果
| B1 | 受理・重複 |
| B2 | 未処理 |
| B3 | 拒否 |
| B4 | 退避 |
### 7-1. ACK
| A5 | 受理・重複・拒否・退避・未処理 |
### 7-2. キュー遷移
| 未送信 → 同期済み | 受理・重複 |
| 未送信 → 要操作 | 拒否 |
| 未送信 → 退避済み | 退避 |
| 未送信 → 未送信 | 未処理 |
""",
        """### 6-3. 境界結果
| B1 | 受理・重複 |
| B2 | 未処理 |
| B3 | 拒否 |
| B4 | 退避 |
### 7-1. ACK
| A5 | 受理・重複・拒否・退避・未処理 |
### 7-2. キュー遷移
| 未送信 → 同期済み | 受理・重複 |
| 未送信 → 要操作 | 拒否 |
| 未送信 → 退避済み | 退避 |
""",
    ),
    (
        "SP-07",
        """### 8-1. 経路表
| P4 | 旧世代検出 → 退避の永続化 → B4 応答 | T8 |
### 9-2. 境界表
| 旧世代 | 退避の永続化と B4 応答の原子性 |
### 10-2. 故障系
| 退避 | B4 応答との原子性 |
### 11-2. 影響差分
| P4 | 退避の永続化と B4 応答 |
""",
        """### 8-1. 経路表
| P1 | 通常経路 |
""",
    ),
    (
        "SP-08",
        """### 4-4. 写像
一時 ID の写像を保存する。
### 7-1. ACK
D5 ごとの確定結果を保存する。
### 8-1. 経路表
| T6 | べき等キーごとの確定結果と一時 ID 写像の保存 |
| P1 | T1・T2・T3・T4・T6 |
| P2 | T1・T2・T3・T4・T5・T6 |
| P3 | T1・T2・T4・T6・T7 |
""",
        """### 8-1. 経路表
| T1 | べき等キーの記録 |
""",
    ),
    (
        "SP-16",
        """### 6-1. prefix
D1 を持たない変更イベントは prefix の対象外である。
### 6-2. 決定表
D1 を持たない変更イベントは prefix の対象外である。
""",
        """### 6-1. prefix
prefix の算出手順を定める。
""",
    ),
    (
        "SP-20",
        "### 2-1. 識別子\n"
        "| D1 | 同期連番 | 用途は順序と欠落の判定・undo の逆順。"
        "再送の重複排除は D5 の用途であり、D1 の用途ではない。 |\n"
        "### 4-2. 役割\n"
        "| べき等キー | D5 | 再送の二重適用を防ぐ |\n"
        "| イベント連番 | D1 | 順序と欠落の判定 |\n",
        """### 2-1. 識別子
| D1 | 同期連番 | 用途は**欠番検知・再送の重複排除・undo の逆順**に限る |
""",
    ),
    (
        "SP-18",
        """### 4-3-A. 変更規則
| W3 | **対象の D2 に従う** |
""",
        """### 4-3-A. 変更規則
| W3 | 持つ。**論理位置(V6)は対象の D2 に従う**(従属 — 5-5)。**D1(V2)を持たない** |
""",
    ),
    (
        "MT-01",
        """## 1. 本書の位置づけ
同期プロトコルの設計を定める。
""",
        """## 1. 本書の位置づけ
本書は「候補案」であり「決定」ではない。
""",
    ),
)


@pytest.mark.parametrize(
    ("defect_id", "valid_text", "invalid_text"),
    DEFECT_CHECK_CASES,
    ids=(
        "condition-key",
        "enum-propagation",
        "route-matrix",
        "element-coverage",
        "scope-declaration",
        "order-use",
        "emphasis",
        "draft-metadata",
    ),
)
def test_defect_backed_checks_have_normal_and_abnormal_cases(
    defect_id: str,
    valid_text: str,
    invalid_text: str,
    manifest: dict[str, checker.ManifestRelation],
    defects: dict[str, checker.Defect],
) -> None:
    assert checker.defect_violation_reason(defects[defect_id], valid_text, manifest) is None
    assert checker.defect_violation_reason(defects[defect_id], invalid_text, manifest)


def _manifest_document(relation: checker.ManifestRelation) -> str:
    targets = json.dumps(relation.targets, ensure_ascii=False, separators=(",", ":"))
    elements = json.dumps(
        relation.expected_elements, ensure_ascii=False, separators=(",", ":")
    )
    return (
        "### 2-5. 表間参照宣言\n"
        "| 関係 ID | 正本の表 | 伝播先の表 | 比較キー | 要素 ID の期待全集合 |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"| **{relation.id}** | `{relation.source_table}` | `{targets}` | "
        f"`{relation.compare_key}` | `{elements}` |\n"
    )


def test_manifest_consistency_accepts_all_five_fields() -> None:
    relation = checker.ManifestRelation("R-ONE", "2-1", ("4-1",), "ID", ("E1",))
    assert checker.check_manifest_consistency(
        _manifest_document(relation), {relation.id: relation}
    ) == ()


@pytest.mark.parametrize(
    "changed",
    (
        checker.ManifestRelation("R-TWO", "2-1", ("4-1",), "ID", ("E1",)),
        checker.ManifestRelation("R-ONE", "2-2", ("4-1",), "ID", ("E1",)),
        checker.ManifestRelation("R-ONE", "2-1", ("4-2",), "ID", ("E1",)),
        checker.ManifestRelation("R-ONE", "2-1", ("4-1",), "name", ("E1",)),
        checker.ManifestRelation("R-ONE", "2-1", ("4-1",), "ID", ("E2",)),
    ),
    ids=("id", "source-table", "targets", "compare-key", "expected-elements"),
)
def test_manifest_consistency_rejects_each_changed_field(
    changed: checker.ManifestRelation,
) -> None:
    expected = checker.ManifestRelation("R-ONE", "2-1", ("4-1",), "ID", ("E1",))
    declared = replace(changed, id="R-ONE") if changed.id == "R-TWO" else changed
    document = _manifest_document(declared)
    if changed.id == "R-TWO":
        document = document.replace("R-ONE", "R-TWO")
    assert checker.check_manifest_consistency(document, {expected.id: expected})


@pytest.mark.parametrize(
    ("text", "is_valid"),
    (
        ("要件書 FR-012/E0 を参照する。", True),
        ("docs/legacy/research/data-layer.md:287 を参照する。", True),
        ("docs/legacy/research/data-layer.md:287・同 :288 を参照する。", True),
        ("REQ:287 を参照する。", False),
        ("docs/requirements/a.md:287 を参照する。", False),
        ("docs/requirements/a.md:287・同 :288 を参照する。", False),
        ("要件書:287 を参照する。", False),
    ),
)
def test_citation_format_has_normal_and_abnormal_cases(
    text: str, is_valid: bool
) -> None:
    assert (checker.check_citation_format(text) == ()) is is_valid


def test_citation_format_bare_line_inherits_immediately_preceding_path() -> None:
    legacy = "[原典](../legacy/research/data-layer.md)・同 :287"
    mutable = "[要件](../requirements/requirements.md)・同 :287"
    unknown = "直前の参照先なし :287"

    assert checker.check_citation_format(legacy) == ()
    assert checker.check_citation_format(mutable) == ("裸の行番号",)
    assert checker.check_citation_format(unknown) == ("裸の行番号",)


def test_citation_format_reports_mutable_path_and_inherited_bare_line() -> None:
    text = "docs/requirements/a.md:287・同 :288"

    assert checker.check_citation_format(text) == (
        "<パス>.md:<行番号>",
        "裸の行番号",
    )


def test_citation_format_requirement_line_is_always_invalid() -> None:
    text = "docs/legacy/research/data-layer.md:287・REQ:288"

    assert checker.check_citation_format(text) == ("REQ:<行番号>",)


def test_noncanonical_reference_has_normal_and_abnormal_cases() -> None:
    valid = "## 2. 本文\n要件書 FR-012/E0 を参照する。\n"
    invalid = "## 2. 本文\n[plan](../features/example/plan.md) を正とする。\n"
    assert checker.check_noncanonical_reference(valid) == ()
    assert checker.check_noncanonical_reference(invalid) == (2,)


def test_link_target_has_normal_and_abnormal_cases(tmp_path: Path) -> None:
    design_dir = tmp_path / "docs" / "design"
    design_dir.mkdir(parents=True)
    (design_dir / "target.md").write_text("target\n", encoding="utf-8")
    assert checker.check_link_targets("[target](target.md)", tmp_path) == ()
    assert checker.check_link_targets("[missing](missing.md)", tmp_path) == (
        "missing.md",
    )


def test_fixture_reports_exact_machine_defect_set(
    defects: dict[str, checker.Defect],
) -> None:
    expected = {key for key, defect in defects.items() if defect.detection == "machine"}
    result = _run_cli(
        "--document",
        str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "--defects",
        ",".join(sorted(expected)),
    )
    assert result.returncode == 1
    assert _finding_ids(result) == expected


def test_fixture_default_adds_three_global_findings(
    defects: dict[str, checker.Defect],
) -> None:
    machine = {key for key, defect in defects.items() if defect.detection == "machine"}
    expected = machine | {
        "citation-format",
        "manifest-consistency",
        "noncanonical-reference",
    }
    result = _run_cli(
        "--document", str(FIXTURE.relative_to(REPOSITORY_ROOT))
    )
    assert result.returncode == 1
    assert _finding_ids(result) == expected


def test_defect_selector_filters_findings() -> None:
    result = _run_cli(
        "--document",
        str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "--defects",
        "SP-20",
    )
    assert result.returncode == 1
    assert _finding_ids(result) == {"SP-20"}


def test_check_selector_filters_findings() -> None:
    result = _run_cli(
        "--document",
        str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "--checks",
        "order-use",
    )
    assert result.returncode == 1
    assert _finding_ids(result) == {"SP-19", "SP-20"}


def test_combined_selectors_use_intersection() -> None:
    result = _run_cli(
        "--document",
        str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "--defects",
        "SP-02,SP-20",
        "--checks",
        "order-use",
    )
    assert result.returncode == 1
    assert _finding_ids(result) == {"SP-20"}


@pytest.mark.parametrize(
    ("arguments", "message"),
    (
        (("--defects", "SP-99"), "未知の欠陥ID"),
        (("--checks", "unknown-check"), "未知の検査ID"),
        (("--defects", "CI-01"), "人間照合の欠陥ID"),
    ),
    ids=("unknown-defect", "unknown-check", "human-defect"),
)
def test_invalid_selectors_fail(arguments: tuple[str, ...], message: str) -> None:
    result = _run_cli(*arguments)
    assert result.returncode == 2
    assert message in result.stderr


def test_corrected_document_is_green_for_step_four_defects() -> None:
    result = _run_cli("--document", str(DESIGN), "--defects", "SP-20,MT-01")
    assert result.returncode == 0, result.stderr


def test_current_manifest_declaration_is_green() -> None:
    result = _run_cli(
        "--document", str(DESIGN), "--checks", "manifest-consistency"
    )
    assert result.returncode == 0, result.stderr
