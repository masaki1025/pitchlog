"""codex_run.py の実装ステップ表判定の単体テスト。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude" / "scripts" / "codex_run.py"


def load_codex_run():
    """テスト対象スクリプトをモジュールとして読み込む。"""
    spec = importlib.util.spec_from_file_location("codex_run_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


codex_run = load_codex_run()


def test_step_table_under_deeper_heading_is_ok():
    plan_text = """\
### 実装ステップ

この節では実装を群ごとに説明する。

#### 第 1 群: 基盤

| 番号 | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 判定を実装する | 単体テストが通る |
"""

    assert codex_run.step_table_status(plan_text) is codex_run.StepTableStatus.OK
    assert codex_run.has_filled_step_row(plan_text) is True


@pytest.mark.parametrize("closing_heading", ["### 別の節", "## 上位の節"])
def test_same_or_upper_heading_ends_step_scope(closing_heading: str):
    plan_text = f"""\
### 実装ステップ
#### 第 1 群
説明。
{closing_heading}
| 1 | スコープ外の作業 | テストが通る |
"""

    assert (
        codex_run.step_table_status(plan_text)
        is codex_run.StepTableStatus.TABLE_OUTSIDE_SCOPE
    )


def test_numeric_table_under_unrelated_heading_is_outside_scope():
    plan_text = """\
## 人間の裁定

| 1 | 採用 | 理由あり |
"""

    assert (
        codex_run.step_table_status(plan_text)
        is codex_run.StepTableStatus.TABLE_OUTSIDE_SCOPE
    )
    assert codex_run.has_filled_step_row(plan_text) is False


@pytest.mark.parametrize(
    ("opening_fence", "closing_fence"),
    [("   ```markdown", "   ```"), ("\t~~~markdown", "\t~~~")],
    ids=["backtick-indented", "tilde-indented"],
)
def test_pseudo_heading_and_table_in_fenced_code_are_ignored(
    opening_fence: str, closing_fence: str
):
    plan_text = f"""\
{opening_fence}
### 実装ステップ
| 1 | 疑似ステップ | 疑似合格条件 |
{closing_fence}
"""

    assert (
        codex_run.step_table_status(plan_text)
        is codex_run.StepTableStatus.TABLE_IN_FENCED_CODE
    )
    assert codex_run.has_filled_step_row(plan_text) is False


@pytest.mark.parametrize(
    "heading",
    [
        "### 4. **実装ステップ**(コミット単位 — 設計書 6.1)",
        "### (1) _実装ステップ_（コミット単位）",
        "### 4-3. 実装ステップ",
    ],
)
def test_normalized_step_heading_is_recognized(heading: str):
    plan_text = f"{heading}\n| 1 | 実装する | テストが通る |\n"

    assert codex_run.step_table_status(plan_text) is codex_run.StepTableStatus.OK


@pytest.mark.parametrize("heading", ["### 実装ステップではない", "### 非実装ステップ"])
def test_negative_or_unrelated_heading_is_not_recognized(heading: str):
    plan_text = f"{heading}\n| 1 | 対象外の作業 | テストが通る |\n"

    assert (
        codex_run.step_table_status(plan_text)
        is codex_run.StepTableStatus.TABLE_OUTSIDE_SCOPE
    )


@pytest.mark.parametrize(
    ("plan_text", "expected"),
    [
        ("### 実装ステップ\n| 1 | 実装する | テストが通る |\n", "OK"),
        ("# 計画\n表はまだない。\n", "NO_TABLE"),
        ("### 実装ステップ\n| 1 |  |  |\n", "NO_FILLED_ROW"),
        ("## 別の節\n| 1 | 実装する | テストが通る |\n", "TABLE_OUTSIDE_SCOPE"),
        (
            "```markdown\n### 実装ステップ\n| 1 | 実装する | テストが通る |\n```\n",
            "TABLE_IN_FENCED_CODE",
        ),
    ],
)
def test_step_table_statuses_are_mutually_exclusive(plan_text: str, expected: str):
    status = codex_run.step_table_status(plan_text)

    assert status is getattr(codex_run.StepTableStatus, expected)


@pytest.mark.parametrize(
    ("plan_text", "expected"),
    [
        ("### 実装ステップ\n| 1 | 実装する | テストが通る |\n", True),
        ("# 計画\n", False),
        ("### 実装ステップ\n| 1 |  |  |\n", False),
        ("## 別の節\n| 1 | 実装する | テストが通る |\n", False),
        ("```\n### 実装ステップ\n| 1 | 実装する | テストが通る |\n```\n", False),
    ],
)
def test_has_filled_step_row_is_true_only_for_ok(plan_text: str, expected: bool):
    assert codex_run.has_filled_step_row(plan_text) is expected


def test_crlf_plan_has_same_result():
    lf_text = "### 実装ステップ\n#### 第 1 群\n| 1 | 実装する | テストが通る |\n"
    crlf_text = lf_text.replace("\n", "\r\n")

    assert codex_run.step_table_status(lf_text) is codex_run.StepTableStatus.OK
    assert codex_run.step_table_status(crlf_text) is codex_run.StepTableStatus.OK
