"""要件の安定 ID 抽出と帰属表の全数検査を検証する。"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import replace
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
RELATIONS_DIR = REPOSITORY_ROOT / "scripts" / "design_relations"
PROFILE = RELATIONS_DIR / "profiles" / "sync-protocol.json"
SAMPLE_PROFILE = (
    REPOSITORY_ROOT
    / "tests/fixtures/profile-sample/profiles/data-model-like.json"
)


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
    if root != REPOSITORY_ROOT:
        for directory in ("schemas", "profiles", "invariants"):
            shutil.copytree(
                RELATIONS_DIR / directory,
                root / "scripts" / "design_relations" / directory,
                dirs_exist_ok=True,
            )
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_sample_profile() -> Any:
    """データモデル型サンプルプロファイルを読む。"""
    return checker.doc_check_profile.load_profile(
        SAMPLE_PROFILE,
        root=REPOSITORY_ROOT,
        schema_dir=RELATIONS_DIR / "schemas",
    )


def _write_json(path: Path, value: Any) -> None:
    """合成資産JSONをUTF-8で書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _replace_sample_asset(
    profile: Any,
    tmp_path: Path,
    asset_name: str,
    value: Any,
) -> Any:
    """サンプル資産1本を合成JSONへ差し替える。"""
    path = tmp_path / f"{asset_name}.json"
    _write_json(path, value)
    raw = json.loads(json.dumps(profile.raw))
    raw["assets"][asset_name]["path"] = str(path)
    changes = {"raw": raw}
    if asset_name == "direct_requirements":
        changes["direct_requirements"] = path
    return replace(profile, **changes)


def _remove_requirement_heading(text: str) -> str:
    return text.replace("#### FR-001:", "#### FR-X01:", 1)


def _add_unknown_requirement_heading(text: str) -> str:
    return text + "\n#### FR-999: 母集合外のテスト用要件\n"


def _assignment_line(text: str) -> str:
    """帰属表から FR-001 の行を取り出す。

    行の内容(区分・帰属先節)は本検査の対象ではなく、変異の起点として
    実在の行が 1 つあればよい。正本の改訂で帰属先が変わってもテストが
    壊れないよう、リテラルで固定せず文書から導出する。

    Args:
        text: 帰属表を含む Markdown 全文。

    Returns:
        末尾に改行を含む FR-001 の帰属行。
    """
    match = re.search(r"^\| FR-001 \|[^\n]*\|\n", text, re.MULTILINE)
    assert match is not None
    return match.group(0)


def _remove_assignment(text: str) -> str:
    line = _assignment_line(text)
    return text.replace(line, "", 1)


def _duplicate_assignment(text: str) -> str:
    line = _assignment_line(text)
    return text.replace(line, line + line, 1)


def _add_unknown_assignment(text: str) -> str:
    marker = _assignment_line(text)
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
        "keyed_table_rows": 40,
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
    assert len(assignments) == 212
    assert Counter(assignment.kind for assignment in assignments) == {
        "同期側で決める": 38,
        # P1-7(確定ゲート 1 周目)で、4-3 の V5・5-5 が直接入力する `3` と、
        # 8-4 がサーバーのステートレス規範として引用する `7.1` を「対象外」から
        # 「境界として参照」へ移した。総数 211 と過不足なしの表明は変えていない。
        # P1-5(確定ゲート 2 周目)で、配信方式を同期の境界外とする 10-1 に合わせ、
        # NFR-006 を「同期側で決める」から「境界として参照」へ移した。
        # P1-4(確定ゲート 4 周目)で、FR-024 のプリフェッチ契約を同期対象外へ移した。
        # P1-3(確定ゲート 5 周目)で、RTO値を同期規則の入力に使わない NFR-008 を
        # 「境界として参照」から「対象外」へ移した。
        # P1-6(確定ゲート 9 周目)で、DoD ⑥を復元ライフサイクルの同期側の
        # 完走条件として「境界として参照」から「同期側で決める」へ移した。
        # ステップ41で6.1のP3受理結果保持を母集合と同期側の帰属へ1件追加した。
        "境界として参照": 84,
        "対象外": 90,
    }


def test_assignment_destination_grammar_parses_all_212_rows() -> None:
    """現行帰属212行と代表的な節式・理由文の展開を固定する。"""
    assignments = {
        assignment.id: assignment
        for assignment in checker.parse_assignments(DOCUMENT.read_text(encoding="utf-8"))
    }

    assert len(assignments) == 212
    assert assignments["FR-012"].sections == (
        "2-1",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
    )
    assert assignments["FR-013"].sections == ("2-1", "6", "9")
    assert assignments["NFR-006"].sections == ("10-1", "11-1")
    assert assignments["FR-016"].sections == ()
    assert assignments["FR-016"].destination.startswith("当該条は")


@pytest.mark.parametrize(
    "destination",
    ("2-1・付録A", "9〜4", "2-1。"),
    ids=("unknown-token", "descending-range", "empty-description"),
)
def test_assignment_destination_rejects_unparsed_expression(
    destination: str,
) -> None:
    """未解析トークン・逆順範囲・空説明を入力不正にする。"""
    with pytest.raises(checker.CoverageError):
        checker.parse_assignment_destination("同期側で決める", destination)


def test_assignment_destination_treats_not_applicable_as_reason_text() -> None:
    """対象外の自由文を節式として解析しない。"""
    assert (
        checker.parse_assignment_destination(
            "対象外",
            "節番号ではない理由文のため対象外",
        )
        == ()
    )


def test_step41_p3_retention_row_extends_only_the_keyed_requirement_universe() -> None:
    """6.1のP3保持行と母集合・帰属の1件追加を固定する。"""
    requirement_id = "6.1/P3受理結果の端末保持"
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    row = next(
        line
        for line in requirements.splitlines()
        if line.startswith("| P3受理結果の端末保持 |")
    )
    universe = checker.load_universe(UNIVERSE)
    assignments = {
        assignment.id: assignment
        for assignment in checker.parse_assignments(DOCUMENT.read_text(encoding="utf-8"))
    }

    assert all(
        term in row
        for term in (
            "対象参照",
            "期待版（V11）",
            "べき等キー（D5）",
            "確定内容",
            "`accepted_at`",
            "24時間",
            "未同期キューとは別",
            "通常の再送対象ではない",
            "退避資料としてのみ",
            "正史へ戻す規則は持たない",
        )
    )
    assert universe.categories["keyed_table_rows"].count(requirement_id) == 1
    assert len(universe.categories["keyed_table_rows"]) == 40
    assert assignments[requirement_id].kind == "同期側で決める"
    assert assignments[requirement_id].destination == "7-1・7-2・9-5"


def test_step32_assignment_corrections_are_fixed() -> None:
    """FR-024と一致性テスト要件を誤った同期節へ戻さない。"""
    assignments = {
        assignment.id: assignment
        for assignment in checker.parse_assignments(DOCUMENT.read_text(encoding="utf-8"))
    }

    assert assignments["FR-021"].destination == "8-2"
    assert assignments["FR-022"].destination == "8-2"
    assert assignments["FR-023"].destination == "8-2"
    assert assignments["FR-024"].kind == "対象外"
    assert "プリフェッチ" in assignments["FR-024"].destination
    assert assignments["NFR-019/(a)"].destination == "8-2・10-3"


def test_step34_nfr_008_is_outside_the_sync_protocol() -> None:
    """同期規則の入力に使わないRTOを境界参照へ戻さない。"""
    assignments = {
        assignment.id: assignment
        for assignment in checker.parse_assignments(DOCUMENT.read_text(encoding="utf-8"))
    }

    assert assignments["NFR-008"].kind == "対象外"
    assert "RTO 値" in assignments["NFR-008"].destination
    assert "同期プロトコルの決定または入力に用いない" in assignments[
        "NFR-008"
    ].destination


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


def test_cli_profile_registry_and_override_routes_match_default() -> None:
    """レジストリ、単一プロファイル、上書き経路の結果を揃える。"""
    default = _run_cli(REPOSITORY_ROOT)
    registry = _run_cli(
        REPOSITORY_ROOT,
        "--registry",
        "scripts/design_relations/profiles/registry.json",
    )
    profile = _run_cli(REPOSITORY_ROOT, "--profile", str(PROFILE))
    overridden = _run_cli(
        REPOSITORY_ROOT,
        "--profile",
        str(PROFILE),
        "--document",
        checker.DEFAULT_DOCUMENT.as_posix(),
        "--requirements",
        checker.DEFAULT_REQUIREMENTS.as_posix(),
        "--universe",
        checker.DEFAULT_UNIVERSE.as_posix(),
    )

    assert {result.returncode for result in (default, registry, profile, overridden)} == {
        0
    }
    assert {result.stdout for result in (default, registry, profile, overridden)} == {
        ""
    }
    assert {result.stderr for result in (default, registry, profile, overridden)} == {
        ""
    }


def test_cli_uses_profile_attribution_section_pattern(tmp_path: Path) -> None:
    """帰属表の節正規表現をプロファイルから取る。"""
    profile_data = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile_data["attribution"]["section_re"] = r"^99-9\."
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(profile_data, ensure_ascii=False),
        encoding="utf-8",
    )

    result = _run_cli(
        REPOSITORY_ROOT,
        "--profile",
        str(profile_path),
        "--checks",
        "attribution",
    )

    assert result.returncode == 2
    assert "帰属表の節がない" in result.stderr


def test_cli_maps_missing_profile_to_exit_2(tmp_path: Path) -> None:
    """プロファイルの読み込み失敗を入力不正として報告する。"""
    result = _run_cli(
        REPOSITORY_ROOT,
        "--profile",
        str(tmp_path / "missing.json"),
    )

    assert result.returncode == 2
    assert result.stderr.startswith("check_doc_coverage.py: ")


def test_cli_maps_registry_file_mismatch_to_exit_2(tmp_path: Path) -> None:
    """レジストリに未登録のJSONがあれば入力不正にする。"""
    root = tmp_path / "repository"
    _write_text(root, checker.DEFAULT_DOCUMENT, DOCUMENT.read_text(encoding="utf-8"))
    _run_cli(root, "--checks", "ledger")
    extra = root / "scripts" / "design_relations" / "profiles" / "extra.json"
    extra.write_text("{}\n", encoding="utf-8")

    result = _run_cli(root, "--checks", "ledger")

    assert result.returncode == 2
    assert "登録集合と実ファイル集合が一致しません" in result.stderr


def test_cli_reports_not_applicable_attribution_destination() -> None:
    """同期プロファイルの新検査を理由付きの対象なしとする。"""
    result = _run_cli(
        REPOSITORY_ROOT,
        "--checks",
        checker.ATTRIBUTION_DESTINATION_CHECK_ID,
    )

    assert result.returncode == 0
    assert "attribution-destination: 対象なし:" in result.stdout
    assert result.stderr == ""


def test_cli_runs_applicable_attribution_destination(tmp_path: Path) -> None:
    """新検査が必須のプロファイルで実際に判定する。"""
    document = tmp_path / "document.md"
    document.write_text(
        "\n".join(
            (
                "# 合成設計書",
                "",
                "## 2. 合成節",
                "",
                "FR-001 を根拠にする。",
                "",
                "### 11-3. 帰属表",
                "",
                "| ID | 区分 | 本書の対応箇所または対象外の理由 |",
                "| --- | --- | --- |",
                "| FR-001 | 同期側で決める | 2 |",
                "",
            )
        ),
        encoding="utf-8",
    )
    profile_data = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile_data["document"] = str(document)
    profile_data["required_checks"].append("attribution-destination")
    del profile_data["not_applicable"]["attribution-destination"]
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(profile_data, ensure_ascii=False),
        encoding="utf-8",
    )

    result = _run_cli(
        REPOSITORY_ROOT,
        "--profile",
        str(profile_path),
        "--checks",
        "attribution-destination",
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_attribution_destination_accepts_existing_section_with_evidence() -> None:
    """帰属先節に安定IDを持つ根拠行があれば適合する。"""
    text = "## 2. 合成節\n\nFR-001 を根拠にこの規則を定める。\n"
    assignment = checker.Assignment(
        "FR-001",
        "同期側で決める",
        "2",
        ("2",),
    )

    assert checker.check_attribution_destinations(text, (assignment,)) == ()


def test_attribution_destination_rejects_missing_section() -> None:
    """帰属先に実在しない節を指定した行を違反にする。"""
    assignment = checker.Assignment(
        "FR-001",
        "同期側で決める",
        "3",
        ("3",),
    )

    findings = checker.check_attribution_destinations(
        "## 2. 合成節\n\nFR-001 の根拠。\n",
        (assignment,),
    )

    assert len(findings) == 1
    assert findings[0].check == "attribution-destination"
    assert "節が存在しない" in findings[0].reason


def test_attribution_destination_rejects_missing_requirement_evidence() -> None:
    """節が実在しても安定IDの根拠行がなければ違反にする。"""
    assignment = checker.Assignment(
        "NFR-006",
        "境界として参照",
        "10-1",
        ("10-1",),
    )

    findings = checker.check_attribution_destinations(
        "### 10-1. 合成節\n\n要件IDを持たない無関係な説明。\n",
        (assignment,),
    )

    assert len(findings) == 1
    assert findings[0].check == "attribution-destination"
    assert "NFR-006 の根拠行がない" in findings[0].reason


def test_universe_is_not_derived_from_extractor() -> None:
    raw = json.loads(UNIVERSE.read_text(encoding="utf-8"))

    assert "抽出器より先に固定した期待値" in raw["_note"]
    assert raw["total"] == 212


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


def test_attribution_direct_sample_is_green_and_all_excluded_is_red() -> None:
    """直接要件が帰属していればgreen、対象外ならredにする。"""
    profile = _load_sample_profile()
    document = profile.document.read_text(encoding="utf-8")
    attribution = profile.raw["attribution"]
    options = {
        "section_re": attribution["section_re"],
        "assignment_kinds": frozenset(attribution["kinds"]),
        "assignment_header": tuple(attribution["assignment_header"]),
        "destination_grammar": attribution["destination_grammar"],
    }
    assignments = checker.parse_assignments(document, **options)
    assert not checker.check_attribution_direct(profile, assignments)

    excluded = tuple(
        replace(assignment, kind="対象外", destination="対象外の合成理由", sections=())
        for assignment in assignments
    )
    findings = checker.check_attribution_direct(profile, excluded)
    assert any("直接要件が対象外" in finding.reason for finding in findings)


def test_attribution_direct_rejects_missing_empty_and_outside_assets(
    tmp_path: Path,
) -> None:
    """必須資産の欠落・空・母集合外IDを入力不正にする。"""
    profile = _load_sample_profile()
    assignment = checker.Assignment("FR-001", "同期側で決める", "4-2", ("4-2",))
    raw = json.loads(json.dumps(profile.raw))
    del raw["assets"]["direct_requirements"]
    missing = replace(profile, raw=raw, direct_requirements=None)
    with pytest.raises(checker.doc_check_profile.ProfileError, match="direct_requirements"):
        checker.check_attribution_direct(missing, (assignment,))

    empty_value = {
        "schema_version": 1,
        "asset_kind": "direct_requirements",
        "oracle_context": {},
        "ids": [],
    }
    empty = _replace_sample_asset(
        profile,
        tmp_path / "empty",
        "direct_requirements",
        empty_value,
    )
    with pytest.raises(checker.doc_check_profile.ProfileError, match="空"):
        checker.check_attribution_direct(empty, (assignment,))

    outside_value = {**empty_value, "ids": ["FR-999"]}
    outside = _replace_sample_asset(
        profile,
        tmp_path / "outside",
        "direct_requirements",
        outside_value,
    )
    with pytest.raises(checker.doc_check_profile.ProfileError, match="母集合外"):
        checker.check_attribution_direct(outside, (assignment,))


def test_attribution_direct_detects_claim_classification_drift(
    tmp_path: Path,
) -> None:
    """direct_requirementsとclaims分類のexact違反をredにする。"""
    profile = _load_sample_profile()
    claims_path = REPOSITORY_ROOT / profile.raw["assets"]["claims"]["path"]
    claims = checker.doc_check_profile.load_json(claims_path)
    claims["claims"][0]["classification"] = "relation"
    changed = _replace_sample_asset(profile, tmp_path, "claims", claims)
    assignments = (
        checker.Assignment("FR-001", "同期側で決める", "4-2", ("4-2",)),
    )
    findings = checker.check_attribution_direct(changed, assignments)
    assert any("direct-requirements-vs-claims" in finding.reason for finding in findings)


def test_attribution_direct_resists_simultaneous_expected_and_universe_shrink(
    tmp_path: Path,
) -> None:
    """期待資産と母集合の同時縮小をclaimsのexactでredにする。"""
    profile = _load_sample_profile()
    claims_path = REPOSITORY_ROOT / profile.raw["assets"]["claims"]["path"]
    claims = checker.doc_check_profile.load_json(claims_path)
    second = json.loads(json.dumps(claims["claims"][0]))
    second["source_id"] = "FR-002"
    claims["claims"].append(second)
    profile = _replace_sample_asset(profile, tmp_path, "claims", claims)
    direct = {
        "schema_version": 1,
        "asset_kind": "direct_requirements",
        "oracle_context": {},
        "ids": ["FR-002"],
    }
    profile = _replace_sample_asset(
        profile,
        tmp_path,
        "direct_requirements",
        direct,
    )
    universe_path = tmp_path / "universe.json"
    _write_json(universe_path, {"schema_version": 1, "ids": ["FR-002"]})
    profile = replace(profile, universe=universe_path)
    assignments = (
        checker.Assignment("FR-002", "同期側で決める", "4-2", ("4-2",)),
    )
    findings = checker.check_attribution_direct(profile, assignments)
    assert any("left-only=['FR-001']" in finding.reason for finding in findings)


def test_attribution_direct_sync_is_not_applicable_and_sample_cli_runs() -> None:
    """同期では資産不要の対象外、サンプルでは実行する。"""
    sync_result = _run_cli(
        REPOSITORY_ROOT,
        "--checks",
        "attribution-direct",
    )
    assert sync_result.returncode == 0
    assert "attribution-direct: 対象なし:" in sync_result.stdout

    sample_result = _run_cli(
        REPOSITORY_ROOT,
        "--profile",
        str(SAMPLE_PROFILE),
        "--checks",
        "attribution-direct",
    )
    assert sample_result.returncode == 0
    assert sample_result.stderr == ""
