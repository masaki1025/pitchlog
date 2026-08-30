"""docs-lint が文書検査を選択実行せず、全件実行する配線を検証する。

検査を CI に載せても選択用引数が付いていると、一部だけの実行で green になり得る。
そのため、YAML の構造とコマンドの禁止オプションを同時に検査する。
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
REQUIRED_FULL_CHECKS = ("check_design_propagation", "check_doc_coverage")
FORBIDDEN_SELECTORS = ("--defects", "--checks")


def _load_workflow(text: str) -> dict[str, Any]:
    workflow = yaml.safe_load(text)
    assert isinstance(workflow, dict), "ci.yml のルートはマッピングでなければならない"
    return workflow


def _docs_lint_commands(workflow: dict[str, Any]) -> list[str]:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "ci.yml に jobs がなければならない"

    docs_lint = jobs.get("docs-lint")
    assert isinstance(docs_lint, dict), "docs-lint ジョブがなければならない"

    steps = docs_lint.get("steps")
    assert isinstance(steps, list), "docs-lint.steps は配列でなければならない"
    return [
        command
        for step in steps
        if isinstance(step, dict)
        and isinstance((command := step.get("run")), str)
    ]


def _assert_full_docs_lint_wiring(text: str) -> None:
    commands = _docs_lint_commands(_load_workflow(text))
    assert any("check_docs_status" in command for command in commands), (
        "check_docs_status.py の既存配線を残さなければならない"
    )

    matched_indexes: list[int] = []
    for check_name in REQUIRED_FULL_CHECKS:
        matches = [
            (index, command)
            for index, command in enumerate(commands)
            if check_name in command
        ]
        assert len(matches) == 1, f"{check_name} を走らせる step は 1 件必要"
        index, command = matches[0]
        assert not any(selector in command for selector in FORBIDDEN_SELECTORS), (
            f"{check_name} は選択実行にせず、引数なしで全検査を走らせる"
        )
        matched_indexes.append(index)

    assert len(set(matched_indexes)) == len(REQUIRED_FULL_CHECKS), (
        "2 つの文書検査は別々の step として配線しなければならない"
    )


def test_docs_lint_runs_all_document_checks_without_selectors() -> None:
    _assert_full_docs_lint_wiring(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_docs_lint_rejects_selective_check_option() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    selective = workflow.replace(
        "scripts/check_doc_coverage.py",
        "scripts/check_doc_coverage.py --checks attribution",
        1,
    )
    assert selective != workflow

    with pytest.raises(AssertionError, match="選択実行"):
        _assert_full_docs_lint_wiring(selective)
