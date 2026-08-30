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
REQUIREMENTS = (
    REPOSITORY_ROOT / "docs" / "requirements" / "requirements-pitchlog-2026-07-22.md"
)

P3_RESULTS = (
    "変更受理",
    "B8:期待版不一致",
    "B9:記録権不保持",
    "B10:一時障害",
    "B11:認証失効",
    "B12:認可・テナント不一致",
    "B13:D5衝突",
    "B14:変更内容拒否",
)
STEP38_P3_ORDER_ELEMENTS = (
    "I1:P3のD5照合位置=③認可後+RG1後+復旧世代照合後+V12前+V11前",
    "I2:P3の既存D5・同一内容=保存済み結果を再掲+再適用しない",
    "I3:P3の既存D5・異なる内容=B13",
    "I4:P3の未使用D5=現復旧世代+V12・V11照合対象",
)
STEP37_P3_INVALIDATION_ELEMENTS = (
    "I5:P3の無効化発火=未使用D5の変更受理でT7に無効化意図を永続化+"
    "配信完了まで冪等再試行+保存済み結果再掲では意図を重複作成しない",
)
STEP38_P3_RETENTION_ELEMENTS = (
    "I6:P3受理結果の端末保持=端末永続化まで成立した対象参照+V11の版+D5+"
    "確定内容+同期済みと同じ24時間保持+サーバー確定から端末永続化まで保護なし+"
    "RG1中は自動破棄停止+退避・閲覧・書き出し対象+復元規則なし",
)
STEP37_P3_RETENTION_ID = ("I6",)
STEP38_RECOVERY_GATE_ELEMENTS = (
    "RG1:復元調整中のfail-closed共通ゲート=③認可後+D5照合前+"
    "全通常書き込み・内部ジョブ停止+P1・P2・P4・通常/緊急引き継ぎはB7+"
    "P3はB10+D5消費なし+コミット直前再検証+サービス再開fail-closed+"
    "解除・新D4開始不可分+復旧制御面だけ許可",
)
STEP37_V12_RECOVERY_ELEMENT = (
    "VF6:V12の復旧世代結合=現D4+現復旧世代+保持端末"
)
STEP37_T7_ELEMENT = "T7:V11照合・対象確定版更新・無効化意図保存"
STEP32_B3_BRANCH_ELEMENTS = (
    "B3a:未使用D5の内容拒否=P5+T9",
    "B3b:既存D5との衝突=先着原本との比較+B3+T9開始なし",
)
STEP32_D1_D5_ELEMENTS = (
    "DI1:D1付き経路のD5照合位置=③認可後+V12前",
    "DI2:D1付き経路の既存D5・同一内容=保存済み結果を再掲+再適用しない",
    "DI3:D1付き経路の既存D5・異なる内容=B3b",
    "DI4:D1付き経路の未使用D5=V12・prefix・内容検査対象",
    "DI5:混在バッチのA5=D5内部先行分類+既存同一D5は保存済み結果候補+"
    "既存異内容D5はB3b候補+未使用D5は後段結果候補+"
    "外部はD1昇順の最初のB2・B3+以降は事前分類済みB3bを含め未処理+同一ACK",
)


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


def test_element_coverage_detects_replaced_right_hand_meaning() -> None:
    """識別子を残した意味反転でも右辺の不一致を検出する。"""
    relation = _manifest_relation(
        source_table="2-1 の参加区分表",
        targets=("3-1 の経路表",),
        source_elements=("1:毎球入力=論理位置を持つ",),
    )
    valid = """### 2-1. 参加区分
| # | 種別 | 区分 |
| --- | --- | --- |
| 1 | 毎球入力 | 論理位置を持つ |
### 3-1. 経路
| # | 種別 | 区分 |
| --- | --- | --- |
| 1 | 毎球入力 | 論理位置を持つ |
"""
    mutated = valid.replace(
        "### 3-1. 経路\n| # | 種別 | 区分 |\n| --- | --- | --- |\n"
        "| 1 | 毎球入力 | 論理位置を持つ |",
        "### 3-1. 経路\n| # | 種別 | 区分 |\n| --- | --- | --- |\n"
        "| 1 | 毎球入力 | 同期順のみ |",
    )

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-ONE: 3-1 の経路表 にない要素: 1:毎球入力=論理位置を持つ",
    )


def test_element_coverage_detects_swapped_right_hand_categories() -> None:
    """両識別子と両区分が節内に残る入れ替えを行対応で検出する。"""
    elements = (
        "1:毎球入力=論理位置を持つ",
        "2:undo=従属",
    )
    relation = _manifest_relation(
        source_table="2-1 の参加区分表",
        targets=("3-1 の経路表",),
        source_elements=elements,
    )
    valid = """### 2-1. 参加区分
| # | 種別 | 区分 |
| --- | --- | --- |
| 1 | 毎球入力 | 論理位置を持つ |
| 2 | undo | 従属 |
### 3-1. 経路
| # | 種別 | 区分 |
| --- | --- | --- |
| 1 | 毎球入力 | 論理位置を持つ |
| 2 | undo | 従属 |
"""
    mutated = valid.replace(
        "### 3-1. 経路\n| # | 種別 | 区分 |\n| --- | --- | --- |\n"
        "| 1 | 毎球入力 | 論理位置を持つ |\n| 2 | undo | 従属 |",
        "### 3-1. 経路\n| # | 種別 | 区分 |\n| --- | --- | --- |\n"
        "| 1 | 毎球入力 | 従属 |\n| 2 | undo | 論理位置を持つ |",
    )

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    reasons = checker.check_element_coverage(mutated, {relation.id: relation})
    assert reasons == (
        "R-ONE: 3-1 の経路表 にない要素: "
        "1:毎球入力=論理位置を持つ,2:undo=従属",
    )


@pytest.mark.parametrize(
    "mutated_target",
    (
        "| P1 | D1付きイベント | T1・T2・T3・T4 |",
        "| P1 | D1付きイベント | T1・T2・T3・T4 |\n"
        "\n"
        "| 別表の要素 | 内容 |\n"
        "| --- | --- |\n"
        "| T6 | 確定結果 |",
    ),
    ids=("missing", "moved-to-another-row"),
)
def test_element_coverage_detects_missing_or_moved_set_member(
    mutated_target: str,
) -> None:
    """右辺のT要素を欠落させても別行へ移しても検出する。"""
    element = "P1:D1付きイベント=T1,T2,T3,T4,T6"
    relation = _manifest_relation(
        source_table="2-1 の経路表",
        targets=("3-1 の経路表",),
        source_elements=(element,),
    )
    source = """### 2-1. 経路
| 経路 ID | 経路 | T 要素 |
| --- | --- | --- |
| P1 | D1付きイベント | T1・T2・T3・T4・T6 |
"""
    valid = source + """### 3-1. 経路
| 経路 ID | 経路 | T 要素 |
| --- | --- | --- |
| P1 | D1付きイベント | T1・T2・T3・T4・T6 |
"""
    mutated = source + """### 3-1. 経路
| 経路 ID | 経路 | T 要素 |
| --- | --- | --- |
""" + mutated_target + "\n"

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        f"R-ONE: 3-1 の経路表 にない要素: {element}",
    )


def _v12_identifier_case(target_rows: str) -> tuple[checker.ManifestRelation, str]:
    """V12境界の行ID変異に使う関係と文書を作る。"""
    elements = (
        "VF1:P1・P2・P4=V12必須",
        "VF4:P1・P2・P4のV12不成立=B4",
    )
    relation = _manifest_relation(
        source_table="2-1 の V12 条件・結果写像",
        targets=("3-1 の境界表",),
        source_elements=elements,
    )
    source = """### 2-1. V12 条件・結果写像
| 条件 ID | 条件 | 結果 |
| --- | --- | --- |
| VF1 | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |
"""
    target = f"""### 3-1. 境界
| 条件 ID | 条件 | 結果 |
| --- | --- | --- |
{target_rows}
"""
    return relation, source + target


def test_element_coverage_detects_deleted_identifier_with_meanings_preserved() -> None:
    """左辺・右辺を残して行IDだけを削除しても検出する。"""
    valid_rows = """| VF1 | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    relation, valid = _v12_identifier_case(valid_rows)
    mutated_rows = """|  | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    _, mutated = _v12_identifier_case(mutated_rows)

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-ONE: 3-1 の境界表 にない要素: VF1:P1・P2・P4=V12必須",
    )


def test_element_coverage_detects_swapped_identifiers_with_meanings_preserved() -> None:
    """文書内のID集合を保った行IDの交換でも対応違反を検出する。"""
    valid_rows = """| VF1 | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    relation, valid = _v12_identifier_case(valid_rows)
    mutated_rows = """| VF4 | P1・P2・P4 | V12 必須 |
| VF1 | P1・P2・P4 の V12 不成立 | B4 |"""
    _, mutated = _v12_identifier_case(mutated_rows)

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-ONE: 3-1 の境界表 にない要素: "
        "VF1:P1・P2・P4=V12必須,VF4:P1・P2・P4のV12不成立=B4",
    )


def test_element_coverage_detects_unknown_identifier_with_meanings_preserved() -> None:
    """左辺・右辺を残した未知IDへの置換でも検出する。"""
    valid_rows = """| VF1 | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    relation, valid = _v12_identifier_case(valid_rows)
    mutated_rows = """| VFX | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    _, mutated = _v12_identifier_case(mutated_rows)

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-ONE: 3-1 の境界表 にない要素: VF1:P1・P2・P4=V12必須",
    )


def test_element_coverage_requires_identifier_for_named_element() -> None:
    """``ID:意味句`` も意味句だけではIDの出現を代替できない。"""
    element = "B10:一時障害"
    relation = _manifest_relation(
        source_table="2-1 の境界結果表",
        targets=("3-1 の通知表",),
        source_elements=(element,),
    )
    source = """### 2-1. 境界結果
| ID | 結果 |
| --- | --- |
| B10 | 一時障害 |
"""
    valid = source + """### 3-1. 通知
| ID | 結果 |
| --- | --- |
| B10 | 一時障害 |
"""
    mutated = source + """### 3-1. 通知
| ID | 結果 |
| --- | --- |
|  | 一時障害 |
"""

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        f"R-ONE: 3-1 の通知表 にない要素: {element}",
    )


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
            ("O1", "O2", "O4"),
            {
                "5-3 の隙間・再採番": ("O1", "O2"),
                "6-3 の O4境界結果": ("O4",),
                "7-1 の A5": ("O4",),
                "7-2 のキュー状態遷移": ("O4",),
                "8-1 の T5・経路 P2": ("O1", "O2", "O4"),
                "10-2 の故障系観点": ("O4",),
                "11-2 のデータモデル影響差分": ("O1", "O2", "O4"),
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
            P3_RESULTS
            + STEP38_P3_ORDER_ELEMENTS
            + STEP37_P3_INVALIDATION_ELEMENTS
            + STEP38_P3_RETENTION_ELEMENTS
            + STEP38_RECOVERY_GATE_ELEMENTS,
            {
                "6-2 の P3 処理段階": STEP38_P3_ORDER_ELEMENTS
                + STEP38_RECOVERY_GATE_ELEMENTS,
                "7-1 の P3 応答契約": P3_RESULTS
                + STEP38_P3_ORDER_ELEMENTS
                + STEP37_P3_INVALIDATION_ELEMENTS
                + STEP38_P3_RETENTION_ELEMENTS,
                "8-1 の経路表": (
                    "B8:期待版不一致",
                    "B9:記録権不保持",
                ),
                "8-3 の補正通知": (
                    P3_RESULTS[1:]
                    + STEP38_P3_ORDER_ELEMENTS
                ),
                "8-5 の無効化発火": STEP37_P3_INVALIDATION_ELEMENTS,
                "9-2 の境界表": P3_RESULTS
                + STEP38_P3_ORDER_ELEMENTS
                + STEP37_P3_INVALIDATION_ELEMENTS
                + STEP38_P3_RETENTION_ELEMENTS
                + STEP38_RECOVERY_GATE_ELEMENTS,
                "9-5 の復元時保持・共通前段ゲート": (
                    STEP38_P3_RETENTION_ELEMENTS + STEP38_RECOVERY_GATE_ELEMENTS
                ),
                "10-2 の故障系観点": P3_RESULTS
                + STEP38_P3_ORDER_ELEMENTS
                + STEP37_P3_INVALIDATION_ELEMENTS
                + STEP38_P3_RETENTION_ELEMENTS
                + STEP38_RECOVERY_GATE_ELEMENTS,
                "11-2 のデータモデル影響差分": (
                    STEP37_P3_INVALIDATION_ELEMENTS
                    + STEP38_P3_RETENTION_ELEMENTS
                    + STEP38_RECOVERY_GATE_ELEMENTS
                ),
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
    tombstone_participation = "8:墓標=同期順のみ"
    revision_participation = "9:改訂版=元イベントの参加区分を継承"

    assert tombstone_rule in relation.source_elements
    assert dict(relation.expected_elements)["6-4 の再開2択"] == (
        tombstone_participation,
        revision_participation,
        tombstone_rule,
    )
    assert dict(relation.expected_elements)["7-2 のキュー状態遷移"] == (
        tombstone_participation,
        revision_participation,
        tombstone_rule,
    )
    assert all(tombstone_rule in elements for _, elements in relation.expected_elements)


def test_step29_manifest_keeps_new_routes_and_required_target_subsets(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """ステップ29で追加・拡張した期待部分集合を弱められないように固定する。"""
    transaction = manifest["R-TXN-ROUTE"]
    rejection_route = "P5:未使用D5の内容拒否=T9"
    rejection_atomic = "T9:未使用D5の内容拒否原本・D5・拒否結果・理由の保存"
    assert rejection_route in transaction.source_elements
    assert rejection_atomic in transaction.source_elements
    assert all(
        rejection_route in elements and rejection_atomic in elements
        for target, elements in transaction.expected_elements
        if target != "10-3 の故障系資産契約"
    )

    change = dict(manifest["R-CHANGE-RULE"].expected_elements)
    for target in (
        "6-2 の P3 処理段階",
        "6-3 の境界結果表",
        "7-1 の P3 応答契約",
        "8-1 の経路表",
        "10-2 の故障系観点",
        "11-2 のデータモデル影響差分",
    ):
        assert "W4" in change[target]
    assert "W3-c" in change["6-3 の境界結果表"]

    v12 = manifest["R-V12-BOUNDARY"]
    v12_elements = (
        "VF1:P1・P2・P4=V12必須",
        "VF2:進行中P3=V12必須",
        "VF3:終了後P3=V12不要",
        "VF4:P1・P2・P4のV12不成立=B4",
        "VF5:進行中P3のV12不成立=B9",
    )
    assert v12.source_elements == v12_elements + (STEP37_V12_RECOVERY_ELEMENT,)
    v12_expected = dict(v12.expected_elements)
    assert v12_expected["7-7 のローカル取り込み"] == (
        v12_elements[0],
        v12_elements[3],
    )
    for target in (
        "6-2 の P3 処理段階",
        "6-3 の境界結果表",
        "7-1 の P3 応答契約",
    ):
        assert v12_expected[target] == v12_elements
    for target in ("8-1 の経路表", "9-2 の境界表", "10-2 の故障系観点"):
        assert v12_expected[target] == v12_elements + (
            STEP37_V12_RECOVERY_ELEMENT,
        )
    assert v12_expected["11-2 のデータモデル影響差分"] == (
        STEP37_V12_RECOVERY_ELEMENT,
    )

    participation = manifest["R-PARTICIPATION"]
    participation_expected = dict(participation.expected_elements)
    assert (
        participation_expected["11-2 のデータモデル影響差分"]
        == participation.source_elements
    )


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


def test_step32_all_routes_check_d5_after_authorization_before_versions() -> None:
    """全経路が認可後、記録権・版より先にD5を照合することを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, "6-2 の処理段階")
    d1_routes = section[section.index("P1・P2・P4 の境界結果") :]
    d1_routes = d1_routes[: d1_routes.index("P3 は D1・D3")]

    authorization = d1_routes.index("③ 認可(テナント)")
    idempotency = d1_routes.index("④ D5 の照合")
    recording_right = d1_routes.index("⑤ 記録権(D4・V12)")
    prefix = d1_routes.index("⑥ 連番(D1)の連続性")
    content = d1_routes.index("⑦ 内容の検証")
    assert authorization < idempotency < recording_right < prefix < content
    assert "P1・P2・P4" in d1_routes
    assert "既存 D5・同一内容なら保存済み結果を再掲" in d1_routes


def test_step32_active_p3_checks_d5_after_authorization_before_versions() -> None:
    """P3が認可後、記録権・期待版より先にD5を照合することを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, "6-2 の処理段階")
    active_p3 = section[section.index("P3 は D1・D3") :]

    authorization = active_p3.index("③ 認可(テナント)")
    idempotency = active_p3.index("④ D5 の照合")
    recording_right = active_p3.index("⑤ 記録権証明")
    expected_version = active_p3.index("⑦ V11 の期待版照合")
    assert authorization < idempotency < recording_right < expected_version
    assert "B9 記録権不保持" in active_p3


def test_step35_removed_mechanism_is_absent_and_manifest_is_reduced(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """除去対象が本文とマニフェストへ復活しないことを固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    removed_markers = ("凍結", "リース", "FS", "FT", "B15", "B16", "O3")
    assert all(marker not in document for marker in removed_markers)

    manifest_text = repr(
        [
            (
                relation.id,
                relation.source_table,
                relation.targets,
                relation.source_elements,
                relation.expected_elements,
            )
            for relation in manifest.values()
        ]
    )
    assert all(marker not in manifest_text for marker in removed_markers)

    ack = manifest["R-ACK-STATE"]
    assert ack.source_elements == ("受理", "重複", "拒否", "退避", "未処理")
    assert all(
        elements == ack.source_elements
        for elements in dict(ack.expected_elements).values()
    )

    queue = manifest["R-QUEUE-LIFE"]
    assert queue.source_elements == (
        "未送信",
        "要操作",
        "同期済み",
        "退避済み",
    ) + STEP37_P3_RETENTION_ID
    queue_expected = dict(queue.expected_elements)
    for target in ("7-2 の遷移表", "6-3 の保持の記述", "9-5 の回収対象"):
        assert queue_expected[target] == queue.source_elements
    assert queue_expected["11-2 のデータモデル影響差分"] == (
        STEP37_P3_RETENTION_ID
    )

    order = manifest["R-ORDER-ASSIGN"]
    assert order.source_elements == ("O1", "O2", "O4")
    assert dict(order.expected_elements) == {
        "5-3 の隙間・再採番": ("O1", "O2"),
        "6-3 の O4境界結果": ("O4",),
        "7-1 の A5": ("O4",),
        "7-2 のキュー状態遷移": ("O4",),
        "8-1 の T5・経路 P2": ("O1", "O2", "O4"),
        "10-2 の故障系観点": ("O4",),
        "11-2 のデータモデル影響差分": ("O1", "O2", "O4"),
    }

    boundary = manifest["R-BOUNDARY"]
    assert boundary.source_elements[:7] == (
        "B1:要求終端",
        "B2:gap",
        "B3:恒久的な内容拒否",
        "B4:記録権不一致",
        "B5:認証失効",
        "B6:認可・テナント不一致",
        "B7:一時障害",
    )
    p3_boundary = manifest["R-P3-BOUNDARY"]
    assert p3_boundary.source_elements == (
        P3_RESULTS
        + STEP38_P3_ORDER_ELEMENTS
        + STEP37_P3_INVALIDATION_ELEMENTS
        + STEP38_P3_RETENTION_ELEMENTS
        + STEP38_RECOVERY_GATE_ELEMENTS
    )


def test_step35_keeps_fr013_must_and_declares_deferred_should() -> None:
    """退避のMustと現行世代への投入を分離して固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    escrow = document[document.index("### 9-4.") : document.index("### 9-5.")]
    handoff = document[document.index("### 11-4.") : document.index("### 11-5.")]

    assert "旧世代のイベントは**適用されないが破棄されず退避される**" in escrow
    assert "管理コンソール" in escrow
    assert "閲覧・書き出しができる" in escrow
    assert "**Must**" in escrow

    assert "**U-2**" in handoff
    assert "退避イベントの現行世代への取り込み(挿入位置の指定・採番)" in handoff
    assert "**Should**" in handoff
    assert "v0.1 の射程外" in handoff
    assert "退避・非破棄・管理コンソールでの閲覧・書き出し" in handoff
    assert "**RR-1**" in handoff
    assert "**TSK-267**" in handoff
    assert "要件書 v2.5 + 本正本 v0.2" in handoff

    assert all(element in document for element in ("D8", "B4", "P4", "T8"))
    assert all(element in document for element in ("O1", "O2", "O4"))
    assert "P3" in document


def test_step37_restore_scope_stops_at_fence_and_escrow() -> None:
    """復元時に端末資料から正史へ戻す規則を再導入させない。"""
    document = DESIGN.read_text(encoding="utf-8")
    restore = checker._reference_section(document, "9-5")
    attribution = checker._reference_section(document, "11-3")
    handoff = checker._reference_section(document, "11-4")

    assert "再構成" not in restore
    assert "正史照合" not in restore
    assert "全試合の既存 D4 を失効" in restore
    assert "B4/P4" in restore
    assert "破棄せず退避" in restore
    assert "管理コンソールで閲覧・書き出し" in restore
    assert "復元前に受理済みだったイベントを正史へ戻す規則は v0.1 では決めない" in restore
    assert "端末ストレージは書き換え得る" in restore
    assert "| NFR-009 | 同期側で決める | 9-5・11-4 |" in attribution
    assert "**U-4**" in handoff
    assert "**RR-2**" in handoff
    assert "復元前に受理済みだったイベントを正史へ戻す規則が未定義" in handoff
    assert "起動時刻、担当者、端末回収順、復元調整の解除判断" in handoff
    assert "**NFR-009 の復旧手順**(運用ドキュメント)" in handoff


def test_step37_p3_invalidation_intent_is_atomic_and_eventually_delivered(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """P3確定と無効化意図を分離せず、未配信分を完了まで再試行する。"""
    document = DESIGN.read_text(encoding="utf-8")
    transaction = checker._reference_section(document, "8-1")
    invalidation = checker._reference_section(document, "8-5")
    failures = checker._reference_section(document, "10-2")
    fixture_contract = checker._reference_section(document, "10-3")
    relation = manifest["R-P3-BOUNDARY"]
    transaction_relation = manifest["R-TXN-ROUTE"]

    assert STEP37_P3_INVALIDATION_ELEMENTS[0] in relation.source_elements
    assert dict(relation.expected_elements)["8-5 の無効化発火"] == (
        STEP37_P3_INVALIDATION_ELEMENTS
    )
    assert STEP37_T7_ELEMENT in transaction_relation.source_elements
    assert dict(transaction_relation.expected_elements)[
        "10-3 の故障系資産契約"
    ] == (STEP37_T7_ELEMENT,)
    assert (
        "T7 の無効化意図は P3 の変更イベント・対象確定版更新と同じトランザクション"
        in transaction
    )
    assert "配信完了まで冪等に再試行" in invalidation
    assert "保存済み結果再掲では意図を重複作成しない" in invalidation
    assert "T7 の確定後・無効化配信前" in failures
    assert "未配信分を配信完了まで冪等に再試行" in failures
    assert "故障注入には **T7 確定後・無効化配信前**" in fixture_contract
    assert "保存済み結果再掲後の意図件数" in fixture_contract


def test_step38_p3_retention_starts_after_device_persistence(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """I6の開始点、未保護窓、保持期間、退避先を固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    response = checker._reference_section(document, "7-1 の P3 応答契約")
    queue = checker._reference_section(document, "7-2 のキュー状態遷移")
    restore = checker._reference_section(document, "9-5")
    model = checker._reference_section(document, "11-2")
    p3_relation = manifest["R-P3-BOUNDARY"]
    queue_relation = manifest["R-QUEUE-LIFE"]

    for section in (response, queue, restore, model):
        assert all(
            field in section for field in ("対象参照", "V11 の版", "D5", "確定内容")
        )
    assert "初回の変更受理から 24 時間" in response
    assert "端末永続化まで成立した P3 受理結果だけ" in response
    assert "窓は保護しない" in response
    assert "同期済み(P3 受理結果) → 退避済み" in queue
    assert "RG1 中でないことを確認済み" in queue
    assert "期限清掃より先に RG1 を確認" in queue
    assert "P3 として再送せず退避資料として保存" in restore
    assert "管理コンソールで閲覧・書き出し" in restore
    assert "復元規則なし" in restore
    assert STEP38_P3_RETENTION_ELEMENTS[0] in p3_relation.source_elements
    assert dict(p3_relation.expected_elements)[
        "9-5 の復元時保持・共通前段ゲート"
    ][0] == STEP38_P3_RETENTION_ELEMENTS[0]
    assert STEP37_P3_RETENTION_ID[0] in queue_relation.source_elements


def test_step37_d4_is_never_reused_after_rollback(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """D4非再利用とV12の復旧世代結合を、物理方式を固定せず保証する。"""
    document = DESIGN.read_text(encoding="utf-8")
    definitions = checker._reference_section(document, "2-1")
    boundary = checker._reference_section(document, "9-2")
    implementation = checker._reference_section(document, "10-1")
    failures = checker._reference_section(document, "10-2")
    v12 = manifest["R-V12-BOUNDARY"]

    assert "ロールバック後も再利用しない識別子" in definitions
    assert "nonce・UUID・バックアップ対象外の単調カウンタ" in definitions
    assert "物理形式は本書で決めず" in definitions
    assert "D4 の非再利用" in boundary
    assert "現 D4・現復旧世代・保持端末" in boundary
    assert "生成アルゴリズム・物理形式" in implementation
    assert "どれを使ったかは期待値に固定しない" in failures
    assert STEP37_V12_RECOVERY_ELEMENT in v12.source_elements


def test_step38_recovery_adjustment_gate_is_fail_closed_for_every_write(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """全変更を事前・コミット直前で止め、全数表の空セルを許さない。"""
    document = DESIGN.read_text(encoding="utf-8")
    processing = checker._reference_section(document, "6-2 の処理段階")
    restore = checker._reference_section(document, "9-5")
    boundary = manifest["R-BOUNDARY"]
    p3_boundary = manifest["R-P3-BOUNDARY"]
    gate = STEP38_RECOVERY_GATE_ELEMENTS[0]

    d1 = processing[processing.index("P1・P2・P4 の境界結果") :]
    d1 = d1[: d1.index("P3 は D1・D3")]
    p3 = processing[processing.index("P3 は D1・D3") :]
    for route in (d1, p3):
        assert route.index("③ 認可(テナント)") < route.index("③-a 復元調整ゲート")
        assert route.index("③-a 復元調整ゲート") < route.index("④ D5 の照合")
    assert "進行中・終了後 P3" in restore
    assert "D5 を消費せず" in restore
    assert "通常・緊急の記録権遷移" in restore
    assert "コミット直前にも同じ状態を検証" in restore
    assert "復元調整解除と、過去に発行した値を再利用しない新しい D4" in restore

    table = restore[restore.index("| 変更経路群 | 含む操作 | RG1 中の結果") :]
    table = table[: table.index("\n\n")]
    rows = [
        tuple(cell.strip() for cell in line.strip("|").split("|"))
        for line in table.splitlines()[2:]
    ]
    assert [row[0].strip("*") for row in rows] == [
        "D1 付き同期",
        "変更イベント",
        "試合作成",
        "選手・スタメン・試合設定の変更",
        "通常の管理変更",
        "状態変更を伴う内部ジョブ",
        "通常引き継ぎ",
        "緊急引き継ぎ",
        "復旧制御面の退避",
        "復旧制御面のログ・通知",
        "復旧制御面の閲覧・書き出し",
    ]
    assert all(len(row) == 4 and all(row) for row in rows)
    assert gate in boundary.source_elements
    assert gate in p3_boundary.source_elements
    for target in (
        "6-2 の D1付き処理段階",
        "9-2 の境界表",
        "10-2 の故障系観点",
        "11-2 のデータモデル影響差分",
    ):
        assert gate in dict(boundary.expected_elements)[target]


def test_step38_all_p3_requests_are_bound_to_the_existing_recovery_generation(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """進行中・終了後P3を既存の復旧世代へ結合し、旧要求を適用しない。"""
    document = DESIGN.read_text(encoding="utf-8")
    change_rule = checker._reference_section(document, "4-3-A")
    processing = checker._reference_section(document, "6-2 の処理段階")
    restore = checker._reference_section(document, "9-5")
    relation = manifest["R-P3-BOUNDARY"]

    assert "全 P3 要求は既存の復旧世代へ結合" in change_rule
    assert "復旧世代は V1〜V12 に追加する新しいイベント値ではない" in change_rule
    assert "③-b 復旧世代の照合" in processing
    assert "旧復旧世代なら、終了後を含め B9" in processing
    assert "復元調整解除後も、復元前の復旧世代を伴う P3" in restore
    assert all(element in relation.source_elements for element in STEP38_P3_ORDER_ELEMENTS)


def test_step37_fr013_must_is_limited_to_escrow_and_admin_access() -> None:
    """FR-013のMustが二つのShouldを無条件に昇格させないことを固定する。"""
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    fr013 = requirements[requirements.index("#### FR-013:") :]
    fr013 = fr013[: fr013.index("#### FR-014:")]
    history = requirements[: requirements.index("## 1.")]

    must_line = next(
        line
        for line in fr013.splitlines()
        if "旧世代の記録権を持つ元端末" in line
    )
    assert "適用されず、破棄されず退避され" in must_line
    assert "管理コンソールで内容を閲覧・書き出しできる" in must_line
    assert "ローカル書き出しは FR-012 の補足 **Should** を採用した場合" in must_line
    assert "退避イベントの取り込みは本条の後段 **Should** を採用した場合" in must_line
    assert "どちらも無条件には要求しない" in must_line
    assert "FR-013 の無注記 Must 基準を優先度どおりに分離" in history
    assert "| 2.4 | 2026-08-30 |" in history


def test_step36_o4_reuses_the_existing_rejection_and_action_state(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """O4が既存の結果値とキュー状態で閉じることを固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    order = checker._reference_section(document, "5-5 の O1・O2・O4")
    boundary = checker._reference_section(document, "6-3 の O4境界結果")
    ack = checker._reference_section(document, "7-1 の A5")
    queue = checker._reference_section(document, "7-2 のキュー状態遷移")

    assert "O4: B3 + A5「拒否」" in order
    assert "要操作(管理者対応待ち)" in order
    assert "O4 の外部結果は B3 と A5「拒否」" in boundary
    assert "理由コード O4" in ack
    assert "O4 では管理者による D2 一意性の是正確認" in queue
    assert "同じ D1 スロットの内容を変えず" in order
    assert "新しい D1 は採番しない" in order

    ack_relation = manifest["R-ACK-STATE"]
    queue_relation = manifest["R-QUEUE-LIFE"]
    order_relation = manifest["R-ORDER-ASSIGN"]
    assert ack_relation.source_elements == ("受理", "重複", "拒否", "退避", "未処理")
    assert queue_relation.source_elements[:4] == (
        "未送信",
        "要操作",
        "同期済み",
        "退避済み",
    )
    for target in (
        "6-3 の O4境界結果",
        "7-1 の A5",
        "7-2 のキュー状態遷移",
        "10-2 の故障系観点",
    ):
        assert dict(order_relation.expected_elements)[target] == ("O4",)


def test_step34_d1_order_uniquely_decides_the_external_stop_boundary(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """D5先行分類がgap後のB3bを外部結果へ漏らさないことを固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    boundary = manifest["R-BOUNDARY"]

    assert tuple(
        element for element in boundary.source_elements if element.startswith("DI")
    ) == STEP32_D1_D5_ELEMENTS
    for target in (
        "4-5 の D5衝突分岐",
        "6-2 の D1付き処理段階",
        "7-1 の A5",
        "10-2 の故障系観点",
    ):
        assert tuple(
            element
            for element in dict(boundary.expected_elements)[target]
            if element.startswith("DI")
        ) == STEP32_D1_D5_ELEMENTS

    decision = checker._reference_section(document, "6-3 の境界結果表")
    ack = checker._reference_section(document, "7-1 の A5")
    failures = checker._reference_section(document, "10-2 の故障系観点")
    assert "D5 の全件先行照合は内部候補の分類" in decision
    assert "外部の A5 と停止境界を先取りしない" in decision
    assert "最初に現れる B2 または B3" in decision
    assert "既に B3b と分かっているイベントもすべて「未処理」" in decision
    assert "最初の B2 または B3 で停止" in ack
    assert "gap より後ろの B3b" in failures
    assert "D3 = 4" in failures
    assert "D1 = 6 と D1 = 7 をともに「未処理」" in failures
    assert "B3b を返さず T9 も開始しない" in failures


def test_step34_failure_fixture_contract_can_express_both_p5_branches() -> None:
    """NFR-019(d)のJSON契約でP5・B3a・B3bを明示できることを守る。"""
    section = checker._reference_section(DESIGN.read_text(), "10-3")

    assert "`適用経路`(**P1〜P5**)" in section
    assert "`P5分岐` に **B3a または B3b** を必須" in section
    assert "B3a では未使用 D5 と内容拒否になる原本" in section
    assert "B3b では先着の不変な原本" in section
    assert "同じ D5・異なる内容の後着入力" in section
