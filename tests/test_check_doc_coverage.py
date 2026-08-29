"""要件の安定 ID 抽出と帰属表の全数検査を検証する。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_doc_coverage.py"
REQUIREMENTS = REPOSITORY_ROOT / "docs" / "requirements" / (
    "requirements-pitchlog-2026-07-22.md"
)
DOCUMENT = REPOSITORY_ROOT / "docs" / "design" / "sync-protocol.md"
UNIVERSE = REPOSITORY_ROOT / "scripts" / "design_relations" / "req-universe.json"


def _load_checker() -> Any:
    """テスト対象を sys.path の変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location("check_doc_coverage_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _write_text(root: Path, relative: Path, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repository(
    tmp_path: Path,
    *,
    requirements_mutator: Callable[[str], str] | None = None,
    document_mutator: Callable[[str], str] | None = None,
) -> Path:
    root = tmp_path / "repository"
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    document = DOCUMENT.read_text(encoding="utf-8")
    if requirements_mutator is not None:
        requirements = requirements_mutator(requirements)
    if document_mutator is not None:
        document = document_mutator(document)
    _write_text(root, checker.DEFAULT_REQUIREMENTS, requirements)
    _write_text(root, checker.DEFAULT_DOCUMENT, document)
    _write_text(root, checker.DEFAULT_UNIVERSE, UNIVERSE.read_text(encoding="utf-8"))
    return root


def _run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _remove_requirement_heading(text: str) -> str:
    return text.replace("#### FR-001:", "#### FR-X01:", 1)


def _add_unknown_requirement_heading(text: str) -> str:
    return text + "\n#### FR-999: 母集合外のテスト用要件\n"


def _remove_assignment(text: str) -> str:
    line = "| FR-001 | 境界として参照 | 5-5・7-4 |\n"
    assert line in text
    return text.replace(line, "", 1)


def _duplicate_assignment(text: str) -> str:
    line = "| FR-001 | 境界として参照 | 5-5・7-4 |\n"
    assert line in text
    return text.replace(line, line + line, 1)


def _add_unknown_assignment(text: str) -> str:
    marker = "| FR-001 | 境界として参照 | 5-5・7-4 |\n"
    assert marker in text
    return text.replace(
        marker,
        marker + "| FR-999 | 対象外 | 母集合に存在しないテスト用 ID |\n",
        1,
    )


def test_extractor_matches_all_oracle_categories() -> None:
    universe = checker.load_universe(UNIVERSE)
    extracted = checker.extract_requirement_ids(REQUIREMENTS.read_text(encoding="utf-8"))

    assert tuple(extracted) == checker.CATEGORY_IDS
    assert {
        category: len(identifiers) for category, identifiers in extracted.items()
    } == {
        "requirements": 65,
        "sections": 28,
        "blocks": 8,
        "appendix_items": 23,
        "identified_table_rows": 16,
        "keyed_table_rows": 39,
        "release_dod": 8,
        "clause_subitems": 24,
    }
    assert all(
        set(extracted[category]) == set(universe.categories[category])
        for category in checker.CATEGORY_IDS
    )


def test_valid_assignment_table_covers_universe_once() -> None:
    universe = checker.load_universe(UNIVERSE)
    extracted = checker.extract_requirement_ids(REQUIREMENTS.read_text(encoding="utf-8"))
    assignments = checker.parse_assignments(DOCUMENT.read_text(encoding="utf-8"))

    assert checker.check_coverage(extracted, universe, assignments) == ()
    assert len(assignments) == 211
    assert Counter(assignment.kind for assignment in assignments) == {
        "同期側で決める": 36,
        # P1-7(確定ゲート 1 周目)で、4-3 の V5・5-5 が直接入力する `3` と、
        # 8-4 がサーバーのステートレス規範として引用する `7.1` を「対象外」から
        # 「境界として参照」へ移した。総数 211 と過不足なしの表明は変えていない。
        # P1-5(確定ゲート 2 周目)で、配信方式を同期の境界外とする 10-1 に合わせ、
        # NFR-006 を「同期側で決める」から「境界として参照」へ移した。
        "境界として参照": 87,
        "対象外": 88,
    }


@pytest.mark.parametrize(
    ("requirements_mutator", "document_mutator", "expected_check"),
    (
        (_remove_requirement_heading, None, "extractor-mismatch"),
        (_add_unknown_requirement_heading, None, "extractor-mismatch"),
        (None, _remove_assignment, "unassigned"),
        (None, _duplicate_assignment, "duplicate-assignment"),
        (None, _add_unknown_assignment, "unknown-assignment"),
    ),
    ids=("extractor-missing", "extractor-unknown", "unassigned", "duplicate", "unknown"),
)
def test_cli_rejects_each_coverage_failure_path(
    tmp_path: Path,
    requirements_mutator: Callable[[str], str] | None,
    document_mutator: Callable[[str], str] | None,
    expected_check: str,
) -> None:
    root = _make_repository(
        tmp_path,
        requirements_mutator=requirements_mutator,
        document_mutator=document_mutator,
    )

    result = _run_cli(root, "--checks", "attribution")

    assert result.returncode == 1
    assert f"{expected_check}:" in result.stderr


def test_cli_accepts_complete_temporary_repository(tmp_path: Path) -> None:
    result = _run_cli(_make_repository(tmp_path), "--checks", "attribution")

    assert result.returncode == 0
    assert result.stderr == ""


def test_cli_accepts_real_document() -> None:
    result = _run_cli(REPOSITORY_ROOT, "--checks", "attribution")

    assert result.returncode == 0
    assert result.stderr == ""


def test_universe_is_not_derived_from_extractor() -> None:
    raw = json.loads(UNIVERSE.read_text(encoding="utf-8"))

    assert "抽出器より先に固定した期待値" in raw["_note"]
    assert raw["total"] == 211


def test_appendix_c_is_stable_id_in_link_label_and_fragment(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    document_path = Path("docs/design/test.md")
    document = (
        "# 合成設計書\n\n"
        "## 1. 主張\n\n"
        "[付録C](docs/requirements/requirements.md) と "
        "[設定値表](docs/requirements/requirements.md#付録C)を参照する。\n"
    )
    _write_text(root, document_path, document)

    citations = checker.extract_citations(document, root, document_path)

    assert [citation.stable_id for citation in citations] == ["付録C", "付録C"]


def _ledger_row(
    claim_id: str,
    ordinal: int,
    target_path: str,
    target_kind: str,
    stable_id: str,
    verdict: str = "支持",
    correction: str = "",
) -> str:
    return (
        f"| {claim_id} | {ordinal} | {target_path} | {target_kind} | "
        f"{stable_id} | {verdict} | {correction} |"
    )


def _ledger_document(claim: str, rows: list[str]) -> str:
    return "\n".join(
        (
            "# 合成設計書",
            "",
            "## 1. 主張",
            "",
            claim,
            "",
            "### 11-5. 意味照合台帳",
            "",
            "| 主張 ID | 主張内 ordinal | 参照先パス | 参照先の種別 | "
            "参照先の安定 ID | 判定 | 是正内容 |",
            "| --- | ---: | --- | --- | --- | --- | --- |",
            *rows,
            "",
        )
    )


def _run_ledger_cli(tmp_path: Path, document: str) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "ledger-repository"
    _write_text(root, checker.DEFAULT_DOCUMENT, document)
    return _run_cli(root, "--checks", "ledger")


def test_ledger_accepts_matching_keys_with_repeated_and_same_named_references(
    tmp_path: Path,
) -> None:
    claim = (
        "根拠 [E-1](docs/requirements/a.md) と [E-1](docs/requirements/a.md)、"
        "別文書 [E-1](docs/design/b.md)。"
    )
    rows = [
        _ledger_row("1/p1", 1, "docs/requirements/a.md", "要件", "E-1"),
        _ledger_row("1/p1", 2, "docs/requirements/a.md", "要件", "E-1"),
        _ledger_row("1/p1", 1, "docs/design/b.md", "正本", "E-1"),
    ]

    result = _run_ledger_cli(tmp_path, _ledger_document(claim, rows))

    assert result.returncode == 0
    assert result.stderr == ""


def test_heading_identifier_ignores_emphasis() -> None:
    parents = {2: "1"}

    emphasized = checker._heading_identifier(  # noqa: SLF001
        "同位置を作らない(**tie-break に D1・D4 を使わない**)",
        4,
        parents,
    )
    plain = checker._heading_identifier(  # noqa: SLF001
        "同位置を作らない(tie-break に D1・D4 を使わない)",
        4,
        parents,
    )

    assert emphasized == plain
    assert emphasized == "1/同位置を作らない(tie-break-に-D1・D4-を使わない)"


@pytest.mark.parametrize(
    "heading",
    (
        "#### 同位置を作らない(**tie-break に D1・D4 を使わない**)",
        "#### 同位置を作らない(tie-break に D1・D4 を使わない)",
    ),
    ids=("emphasized", "plain"),
)
def test_ledger_key_matches_heading_with_or_without_emphasis(
    tmp_path: Path,
    heading: str,
) -> None:
    claim = "根拠 [FR-012](docs/requirements/a.md)。"
    row = _ledger_row(
        "1/同位置を作らない(tie-break-に-D1・D4-を使わない)/p1",
        1,
        "docs/requirements/a.md",
        "要件",
        "FR-012",
    )
    document = _ledger_document(f"{heading}\n\n{claim}", [row])

    result = _run_ledger_cli(tmp_path, document)

    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    "rows",
    (
        [],
        [
            _ledger_row("1/p1", 1, "docs/requirements/a.md", "要件", "FR-012"),
            _ledger_row("1/p1", 1, "docs/requirements/a.md", "要件", "NFR-001"),
        ],
    ),
    ids=("ledger-missing", "ledger-extra"),
)
def test_ledger_rejects_key_set_shortage_and_excess(
    tmp_path: Path,
    rows: list[str],
) -> None:
    claim = "根拠 [FR-012](docs/requirements/a.md)。"

    result = _run_ledger_cli(tmp_path, _ledger_document(claim, rows))

    assert result.returncode == 1
    assert "ledger-key-mismatch:" in result.stderr


def test_ledger_rejects_missing_correction_for_unsupported_entry(tmp_path: Path) -> None:
    claim = "根拠 [FR-012](docs/requirements/a.md)。"
    rows = [
        _ledger_row(
            "1/p1",
            1,
            "docs/requirements/a.md",
            "要件",
            "FR-012",
            verdict="不支持",
        )
    ]

    result = _run_ledger_cli(tmp_path, _ledger_document(claim, rows))

    assert result.returncode == 1
    assert "ledger-correction:" in result.stderr


def test_ledger_distinguishes_same_stable_id_in_different_documents(tmp_path: Path) -> None:
    claim = "根拠 [E-1](docs/requirements/a.md)。"
    rows = [_ledger_row("1/p1", 1, "docs/design/a.md", "正本", "E-1")]

    result = _run_ledger_cli(tmp_path, _ledger_document(claim, rows))

    assert result.returncode == 1
    assert "ledger-target-pair:" in result.stderr


def test_ledger_detects_repeated_reference_collapsing_from_two_to_one(tmp_path: Path) -> None:
    claim = (
        "根拠 [FR-012](docs/requirements/a.md) と "
        "[FR-012](docs/requirements/a.md)。"
    )
    rows = [_ledger_row("1/p1", 1, "docs/requirements/a.md", "要件", "FR-012")]

    result = _run_ledger_cli(tmp_path, _ledger_document(claim, rows))

    assert result.returncode == 1
    assert "ledger-key-mismatch:" in result.stderr


def test_ledger_detects_repeated_reference_growing_from_one_to_two(tmp_path: Path) -> None:
    claim = "根拠 [FR-012](docs/requirements/a.md)。"
    rows = [
        _ledger_row("1/p1", 1, "docs/requirements/a.md", "要件", "FR-012"),
        _ledger_row("1/p1", 2, "docs/requirements/a.md", "要件", "FR-012"),
    ]

    result = _run_ledger_cli(tmp_path, _ledger_document(claim, rows))

    assert result.returncode == 1
    assert "ledger-key-mismatch:" in result.stderr


@pytest.mark.parametrize("ordinals", ((1, 1), (1, 3)), ids=("duplicate", "gap"))
def test_ledger_rejects_duplicate_or_missing_ordinal(
    tmp_path: Path,
    ordinals: tuple[int, int],
) -> None:
    claim = (
        "根拠 [FR-012](docs/requirements/a.md) と "
        "[FR-012](docs/requirements/a.md)。"
    )
    rows = [
        _ledger_row("1/p1", ordinal, "docs/requirements/a.md", "要件", "FR-012")
        for ordinal in ordinals
    ]

    result = _run_ledger_cli(tmp_path, _ledger_document(claim, rows))

    assert result.returncode == 1
    assert "ledger-ordinal:" in result.stderr


def test_real_document_passes_all_coverage_checks() -> None:
    attribution = _run_cli(REPOSITORY_ROOT, "--checks", "attribution")
    ledger = _run_cli(REPOSITORY_ROOT, "--checks", "ledger")
    combined = _run_cli(REPOSITORY_ROOT)

    assert attribution.returncode == 0
    assert ledger.returncode == 0
    assert combined.returncode == 0
    assert attribution.stderr == ""
    assert ledger.stderr == ""
    assert combined.stderr == ""
