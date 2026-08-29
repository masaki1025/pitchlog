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
    source_elements = json.dumps(
        relation.source_elements, ensure_ascii=False, separators=(",", ":")
    )
    expected_elements = json.dumps(
        dict(relation.expected_elements), ensure_ascii=False, separators=(",", ":")
    )
    return (
        "### 2-5. 表間参照宣言\n"
        "| 関係 ID | 正本の表 | 伝播先の表 | 比較キー | 正本の要素全集合 | "
        "伝播先ごとの期待部分集合 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        f"| **{relation.id}** | `{relation.source_table}` | `{targets}` | "
        f"`{relation.compare_key}` | `{source_elements}` | `{expected_elements}` |\n"
    )


def _manifest_relation(
    relation_id: str = "R-ONE",
    source_table: str = "2-1",
    targets: tuple[str, ...] = ("4-1",),
    compare_key: str = "ID",
    source_elements: tuple[str, ...] = ("E1",),
    expected_elements: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
) -> checker.ManifestRelation:
    """6フィールドを持つ最小の関係宣言を作る。"""
    if expected_elements is None:
        expected_elements = tuple((target, source_elements) for target in targets)
    return checker.ManifestRelation(
        relation_id,
        source_table,
        targets,
        compare_key,
        source_elements,
        expected_elements,
    )


def test_manifest_consistency_accepts_all_six_fields() -> None:
    relation = _manifest_relation()
    assert checker.check_manifest_consistency(
        _manifest_document(relation), {relation.id: relation}
    ) == ()


@pytest.mark.parametrize(
    "changed",
    (
        _manifest_relation(relation_id="R-TWO"),
        _manifest_relation(source_table="2-2"),
        _manifest_relation(targets=("4-2",)),
        _manifest_relation(compare_key="name"),
        _manifest_relation(source_elements=("E2",)),
        _manifest_relation(
            expected_elements=(("4-1", ("E1", "E2")),),
        ),
    ),
    ids=(
        "id",
        "source-table",
        "targets",
        "compare-key",
        "source-elements",
        "expected-elements",
    ),
)
def test_manifest_consistency_rejects_each_changed_field(
    changed: checker.ManifestRelation,
) -> None:
    expected = _manifest_relation()
    declared = replace(changed, id="R-ONE") if changed.id == "R-TWO" else changed
    document = _manifest_document(declared)
    if changed.id == "R-TWO":
        document = document.replace("R-ONE", "R-TWO")
    assert checker.check_manifest_consistency(document, {expected.id: expected})


def test_element_coverage_is_manifest_driven_and_accepts_target_subsets() -> None:
    relation = _manifest_relation(
        relation_id="R-NEW",
        source_table="2-1 の正本表",
        targets=("3-1 の表", "4-1 の表"),
        source_elements=("E1", "E2"),
        expected_elements=(("3-1 の表", ("E1",)), ("4-1 の表", ("E2",))),
    )
    document = """### 2-1. 正本
| E1 | 一つ目 |
| E2 | 二つ目 |
### 3-1. 伝播先A
| E1 | 一つ目 |
### 4-1. 伝播先B
| E2 | 二つ目 |
"""

    assert checker.check_element_coverage(document, {relation.id: relation}) == ()


def test_element_coverage_detects_missing_element_for_new_relation() -> None:
    relation = _manifest_relation(
        relation_id="R-NEW",
        source_table="2-1 の正本表",
        targets=("3-1 の表",),
        source_elements=("E1", "E2"),
    )
    document = """### 2-1. 正本
| E1 | 一つ目 |
| E2 | 二つ目 |
### 3-1. 伝播先
| E1 | 一つ目 |
"""

    reasons = checker.check_element_coverage(document, {relation.id: relation})

    assert reasons == ("R-NEW: 3-1 の表 にない要素: E2",)


def test_manifest_rejects_source_element_without_any_target(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "R-NEW": {
                    "id": "R-NEW",
                    "source_table": "2-1 の正本表",
                    "targets": ["3-1 の表"],
                    "compare_key": "ID",
                    "source_elements": ["E1", "E2"],
                    "expected_elements": {"3-1 の表": ["E1"]},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(checker.CheckError, match="どこへも伝播しない要素ID.*E2"):
        checker.load_manifest(manifest_path)


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


def test_fixture_default_adds_global_findings(
    defects: dict[str, checker.Defect],
) -> None:
    machine = {key for key, defect in defects.items() if defect.detection == "machine"}
    expected = machine | {
        "citation-format",
        "element-coverage",
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


def test_current_manifest_all_relations_have_element_coverage() -> None:
    result = _run_cli("--document", str(DESIGN), "--checks", "element-coverage")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("relation_id", "source_elements", "expected_elements"),
    (
        (
            "R-TEMP-ID-MAPPING",
            ("C1", "C2", "C3", "C4"),
            {
                "7-1 の A4・A5": ("C1", "C3", "C4"),
                "7-2 の写像確定": ("C1", "C4"),
                "8-1 の T6": ("C1", "C2", "C3", "C4"),
                "11-2 のデータモデル影響差分": ("C1", "C2", "C3", "C4"),
            },
        ),
        (
            "R-ORDER-ASSIGN",
            ("O1", "O2", "O3", "O4"),
            {
                "5-3 の隙間・再採番": ("O1", "O2", "O3"),
                "8-1 の T5・経路 P2": ("O1", "O2", "O3", "O4"),
                "11-2 のデータモデル影響差分": ("O1", "O2", "O3", "O4"),
            },
        ),
    ),
)
def test_step26_relations_keep_complete_source_and_target_subsets(
    manifest: dict[str, checker.ManifestRelation],
    relation_id: str,
    source_elements: tuple[str, ...],
    expected_elements: dict[str, tuple[str, ...]],
) -> None:
    """追加関係の正本全集合と伝播先別部分集合を固定する。"""
    relation = manifest[relation_id]

    assert relation.source_elements == source_elements
    assert dict(relation.expected_elements) == expected_elements
    assert relation.targets == tuple(expected_elements)


@pytest.mark.parametrize(
    ("relation_id", "source_elements", "expected_elements"),
    (
        (
            "R-EVENT-FIELD",
            tuple(f"V{index}" for index in range(1, 13)),
            {
                "4-3-A の W3": tuple(f"V{index}" for index in range(1, 13)),
                "11-2 のデータモデル影響差分": tuple(
                    f"V{index}" for index in range(1, 13)
                ),
            },
        ),
        (
            "R-P3-BOUNDARY",
            ("B8:期待版不一致", "B9:記録権不保持"),
            {
                "7-1 の P3 応答契約": (
                    "B8:期待版不一致",
                    "B9:記録権不保持",
                ),
                "8-1 の経路表": ("B9:記録権不保持",),
                "8-3 の補正通知": (
                    "B8:期待版不一致",
                    "B9:記録権不保持",
                ),
                "9-2 の境界表": (
                    "B8:期待版不一致",
                    "B9:記録権不保持",
                ),
                "10-2 の故障系観点": ("B9:記録権不保持",),
            },
        ),
    ),
)
def test_step27_relations_keep_complete_source_and_target_subsets(
    manifest: dict[str, checker.ManifestRelation],
    relation_id: str,
    source_elements: tuple[str, ...],
    expected_elements: dict[str, tuple[str, ...]],
) -> None:
    """記録権証明とP3拒否結果の伝播集合を固定する。"""
    relation = manifest[relation_id]

    assert relation.source_elements == source_elements
    assert dict(relation.expected_elements) == expected_elements
    assert relation.targets == tuple(expected_elements)


def test_step27_tombstone_generation_stays_in_queued_participation_group(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """墓標の事前確認条件がD1付きキュー経路から脱落しないことを守る。"""
    relation = manifest["R-PARTICIPATION"]
    tombstone_rule = "K5:墓標生成=オンライン記録権確認後+D1付きキュー"

    assert tombstone_rule in relation.source_elements
    assert dict(relation.expected_elements)["6-4 の再開2択"] == (
        tombstone_rule,
    )
    assert dict(relation.expected_elements)["7-2 のキュー状態遷移"] == (
        tombstone_rule,
    )
    assert all(tombstone_rule in elements for _, elements in relation.expected_elements)


def test_step27_recording_right_proof_keeps_semantic_physical_boundary() -> None:
    """記録権証明が個人IDや未決の物理方式へ置き換わらないことを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    contract = checker._reference_section(document, "4-3 の V1〜V12")
    boundary = checker._reference_section(document, "9-2 の境界表")

    assert "V12 は個人利用者 ID ではない" in contract
    assert all(
        undecided in contract
        for undecided in ("物理形式", "寿命", "端末内の格納先", "更新方法")
    )
    assert "同一テナント・現 D4 でも" in boundary
    assert "V12 が保持端末を証明しない要求を拒否する" in boundary


def test_step27_tombstone_rule_propagates_to_generation_and_queue() -> None:
    """墓標の事前確認とD1付きキュー経路が三つの規範節で一致することを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    for reference in (
        "5-5 の参加区分表",
        "6-4 の再開2択",
        "7-2 のキュー状態遷移",
    ):
        section = checker._reference_section(document, reference)
        assert "K5" in section
        assert "V12" in section
    participation = checker._reference_section(document, "5-5 の参加区分表")
    assert "群 A: D1 付きで端末内キューに載る種別" in participation
    assert "改訂版は群 A のまま、ローカル生成を許す" in participation


def test_step27_active_p3_authorizes_tenant_before_recording_right() -> None:
    """P3が記録権の成否より先に他テナントの存在を漏らさないことを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, "6-2 の処理段階")
    active_p3 = section[section.index("P3 は D1・D3") :]

    assert active_p3.index("③ 認可(テナント)") < active_p3.index(
        "④ 記録権証明"
    )
    assert "B9 記録権不保持" in active_p3
