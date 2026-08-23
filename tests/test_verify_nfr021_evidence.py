"""verify_nfr021_evidence.py の命名・スキーマ・ゲート検査を単体検証する。"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "verify_nfr021_evidence.py"
CORE_GUARD_SCRIPT = REPO / "scripts" / "core_guard.py"
DOCS_STATUS_SCRIPT = REPO / "scripts" / "check_docs_status.py"
INVALIDATING_PATHS_CONFIG = REPO / ".claude" / "nfr021-invalidating-paths.json"
ACCEPTANCE_DIRECTORY = REPO / "docs" / "ops" / "nfr021-acceptance"
PHASE4_EVIDENCE_TEMPLATE = ACCEPTANCE_DIRECTORY / "evidence-phase4-template.md"
RELEASE_EVIDENCE_TEMPLATE = ACCEPTANCE_DIRECTORY / "evidence-release-template.md"
RESERVATION_FILENAME = "2026-08-19T142916Z-phase4-phase4-seq001-reservation.md"
COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_COMMIT_SHA = "fedcba9876543210fedcba9876543210fedcba98"
ONBOARDING_BLOB_SHA = "89abcdef0123456789abcdef0123456789abcdef"
OTHER_ONBOARDING_BLOB_SHA = "76543210fedcba987654321076543210fedcba98"
RECORD_TIMESTAMP = "2026-08-19T101500Z"
ATTEMPT_ID_TIMESTAMP = "20260819T101500Z"
CODE_DELIMITER = chr(96)
CANONICAL_ACCEPTANCE_FILENAMES = (
    "README.md",
    "reservation-template.md",
    "evidence-phase4-template.md",
    "evidence-release-template.md",
)


def load_module(script: Path, name: str) -> ModuleType:
    """スクリプトを sys.path を変更せずにモジュールとして読み込む。

    Args:
        script: 読み込むスクリプトの絶対パス。
        name: テスト内で使う一意なモジュール名。

    Returns:
        実行済みのスクリプトモジュール。
    """
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core_guard = load_module(CORE_GUARD_SCRIPT, "core_guard")
verify = load_module(SCRIPT, "verify_nfr021_evidence_under_test")


def attempt_id(
    gate_key: str,
    attempt_seq: int,
    timestamp: str = ATTEMPT_ID_TIMESTAMP,
) -> str:
    """指定したゲートキーと連番から正規形 attempt_id を作る。

    Args:
        gate_key: phase4 または release-vX.Y.Z の合成ゲートキー。
        attempt_seq: 1 以上の連番。
        timestamp: ハイフンなしの UTC 時刻。

    Returns:
        テスト用の正規形 attempt_id。
    """
    return f"{gate_key}-{attempt_seq:03d}-{timestamp}"


def build_frontmatter(lines: list[str], body: str = "") -> str:
    """frontmatter 行と本文から証跡ファイル内容を作る。

    Args:
        lines: frontmatter 内に置くキー行。
        body: 終端記号より後に置く本文。

    Returns:
        UTF-8 テキストとして書ける証跡ファイル内容。
    """
    content = "\n".join(["---", *lines, "---"])
    return f"{content}\n{body}" if body else f"{content}\n"


def evidence_body(commit_sha: str, onboarding_blob_sha: str) -> str:
    """二重記録の 2 行を持つ最小の結果証跡本文を作る。

    Args:
        commit_sha: 本文へ書く commit SHA。
        onboarding_blob_sha: 本文へ書く onboarding blob SHA。

    Returns:
        2 行の Markdown 表を含む本文。
    """
    return "\n".join(
        [
            "# 結果証跡",
            "",
            "| 項目 | 記録 |",
            "| --- | --- |",
            f"| commit SHA | {CODE_DELIMITER}{commit_sha}{CODE_DELIMITER} |",
            (
                "| onboarding blob SHA | "
                f"{CODE_DELIMITER}{onboarding_blob_sha}{CODE_DELIMITER} |"
            ),
        ]
    )


def complete_evidence_body(
    commit_sha: str,
    onboarding_blob_sha: str,
    gate_kind: str = "phase4",
    *,
    evidence_rows: tuple[tuple[str, str], ...] | None = None,
    acceptance_items: tuple[tuple[str, str], ...] | None = None,
    acceptance_item_count: int | None = None,
) -> str:
    """⑩を満たす結果証跡本文を必要に応じて部分的に変えて作る。

    Args:
        commit_sha: 本文へ書く commit SHA。
        onboarding_blob_sha: 本文へ書く onboarding blob SHA。
        gate_kind: phase4 または release。
        evidence_rows: 証跡表へ置く ``(欄名, 値)`` 行。省略時は全欄を置く。
        acceptance_items: 合格項目表へ置く ``(#, 合格項目)`` 行。省略時はテンプレートから得る。
        acceptance_item_count: 指定時は選んだ合格項目から残す先頭行数。

    Returns:
        本文完全性を検査できる 2 つの Markdown 表を含む本文。
    """
    default_evidence_rows = (
        ("日時", "2026-08-19T101500Z"),
        ("commit SHA", f"{CODE_DELIMITER}{commit_sha}{CODE_DELIMITER}"),
        ("Windows 版", "Windows 11 24H2"),
        ("WSL 版", "WSL 2.6"),
        ("ディストリビューション版", "Ubuntu 26.04 LTS"),
        ("onboarding 版", "v1.0"),
        (
            "onboarding blob SHA",
            f"{CODE_DELIMITER}{onboarding_blob_sha}{CODE_DELIMITER}",
        ),
        (
            "主要ツールの版（python / uv / node / docker）",
            "python 3.12.3 / uv 0.8.13 / node 22 / docker 28",
        ),
        ("実行コマンドと終了コード", "uv run pytest (0)"),
        ("各合格項目の期待値と実測値", "下表に記載"),
        ("標準出力またはログ成果物への参照", "docs/worklog/test.log"),
        ("判定者", "判定者が内容を確認した"),
    )
    rows = evidence_rows if evidence_rows is not None else default_evidence_rows
    items = (
        acceptance_items
        if acceptance_items is not None
        else template_acceptance_items(gate_kind)
    )
    if acceptance_item_count is not None:
        items = items[:acceptance_item_count]
    evidence_table = [
        "| 項目 | 記録 |",
        "| --- | --- |",
        *(f"| {field} | {value} |" for field, value in rows),
    ]
    acceptance_table = [
        "| # | 合格項目 | 期待値 | 実測値 |",
        "| --- | --- | --- | --- |",
        *(
            f"| {number} | {item_name} | 期待値 {number} | 実測値 {number} |"
            for number, item_name in items
        ),
    ]
    return "\n".join(
        [
            "# 結果証跡",
            "",
            "## 証跡",
            "",
            *evidence_table,
            "",
            "## 合格項目",
            "",
            *acceptance_table,
        ]
    )


def template_table_rows(template_path: Path, heading: str) -> tuple[tuple[str, ...], ...]:
    """テンプレートの唯一の複写用ブロックから指定表のデータ行を取り出す。

    Args:
        template_path: 読み取る結果証跡テンプレートの絶対パス。
        heading: 取り出す ``##`` 見出しの表示名。

    Returns:
        指定表のデータ行を前後空白なしのセル列で並べた組。
    """
    fenced_parts = template_path.read_text(encoding="utf-8").split("```")
    assert len(fenced_parts) == 3
    lines = fenced_parts[1].splitlines()
    heading_index = lines.index(f"## {heading}")
    table_index = next(
        index
        for index in range(heading_index + 1, len(lines))
        if lines[index].strip().startswith("|") and lines[index].strip().endswith("|")
    )
    rows: list[tuple[str, ...]] = []
    for line in lines[table_index + 2 :]:
        stripped_line = line.strip()
        if not stripped_line.startswith("|") or not stripped_line.endswith("|"):
            break
        rows.append(tuple(cell.strip() for cell in stripped_line[1:-1].split("|")))
    return tuple(rows)


def template_acceptance_items(gate_kind: str) -> tuple[tuple[str, str], ...]:
    """実物テンプレートからゲート別の合格項目の番号と名前を得る。

    Args:
        gate_kind: phase4 または release。

    Returns:
        テンプレートに並ぶ ``(#, 合格項目)`` の対。
    """
    template_path = (
        PHASE4_EVIDENCE_TEMPLATE
        if gate_kind == "phase4"
        else RELEASE_EVIDENCE_TEMPLATE
    )
    return tuple(
        (row[0], row[1])
        for row in template_table_rows(template_path, "合格項目")
    )


def reservation_text(
    gate_key: str = "phase4",
    attempt_seq: int = 1,
    attempt_seq_value: str | None = None,
    attempt_id_value: str | None = None,
    started_at: str = RECORD_TIMESTAMP,
    extra_lines: tuple[str, ...] = (),
) -> str:
    """予約レコードの最小かつ適合する frontmatter を作る。

    Args:
        gate_key: frontmatter の合成ゲートキー。
        attempt_seq: attempt_id を作るための整数連番。
        attempt_seq_value: frontmatter 行へ直接書く値。省略時は整数連番。
        attempt_id_value: frontmatter へ直接書く attempt_id。省略時は正規形。
        started_at: frontmatter の started_at。
        extra_lines: 意図的なスキーマ違反に使う追加キー行。

    Returns:
        予約レコードの内容。
    """
    sequence_value = attempt_seq_value if attempt_seq_value is not None else str(attempt_seq)
    record_id = attempt_id_value or attempt_id(gate_key, attempt_seq)
    return build_frontmatter(
        [
            f'gate_key: "{gate_key}"',
            f"attempt_seq: {sequence_value}",
            f'attempt_id: "{record_id}"',
            f'started_at: "{started_at}"',
            'operator: "テスト担当者"',
            *extra_lines,
        ],
        "# 予約レコード",
    )


def evidence_text(
    gate_kind: str = "phase4",
    release_version: str | None = None,
    tested_commit_sha: str = COMMIT_SHA,
    onboarding_blob_sha: str = ONBOARDING_BLOB_SHA,
    result: str = "passed",
    attempt_seq: int = 1,
    attempt_seq_value: str | None = None,
    attempt_id_value: str | None = None,
    extra_lines: tuple[str, ...] = (),
    body_commit_sha: str | None = None,
    body_onboarding_blob_sha: str | None = None,
    body: str | None = None,
) -> str:
    """結果証跡の最小かつ適合する frontmatter と二重記録本文を作る。

    Args:
        gate_kind: frontmatter の gate_kind。
        release_version: release の場合の frontmatter の版。
        tested_commit_sha: frontmatter の tested_commit_sha。
        onboarding_blob_sha: frontmatter の onboarding_blob_sha。
        result: frontmatter の result。
        attempt_seq: attempt_id を作るための整数連番。
        attempt_seq_value: frontmatter 行へ直接書く値。省略時は整数連番。
        attempt_id_value: frontmatter へ直接書く attempt_id。省略時は正規形。
        extra_lines: 意図的なスキーマ違反に使う追加キー行。
        body_commit_sha: 本文へ書く commit SHA。省略時は frontmatter と一致させる。
        body_onboarding_blob_sha: 本文へ書く blob SHA。省略時は一致させる。
        body: frontmatter の後へ置く本文。省略時は二重記録だけの最小本文を使う。

    Returns:
        結果証跡の内容。
    """
    sequence_value = attempt_seq_value if attempt_seq_value is not None else str(attempt_seq)
    expected_gate_key = (
        "phase4" if gate_kind == "phase4" else f"release-{release_version}"
    )
    record_id = attempt_id_value or attempt_id(expected_gate_key, attempt_seq)
    lines = [
        f"gate_kind: {gate_kind}",
        f'tested_commit_sha: "{tested_commit_sha}"',
        f'onboarding_blob_sha: "{onboarding_blob_sha}"',
        f"result: {result}",
    ]
    if release_version is not None:
        lines.append(f"release_version: {release_version}")
    lines.extend(
        [
            f"attempt_seq: {sequence_value}",
            f'attempt_id: "{record_id}"',
            *extra_lines,
        ]
    )
    default_body = evidence_body(
        body_commit_sha or tested_commit_sha,
        body_onboarding_blob_sha or onboarding_blob_sha,
    )
    return build_frontmatter(lines, body if body is not None else default_body)


def parse_record(filename: str, text: str):
    """テスト用のファイル名と内容を解析済みレコードへ変換する。

    Args:
        filename: 受入証跡ディレクトリ直下からの相対パス。
        text: 解析する証跡内容。

    Returns:
        verify_nfr021_evidence の解析済みレコード。
    """
    return verify.parse_acceptance_record(filename, text)


def validate_evidence_completeness(
    tmp_path: Path,
    record: verify.AcceptanceRecord,
) -> tuple[str, ...]:
    """候補ツリーのテンプレートを使って本文完全性を検査する。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        record: 検査対象として解析済みの結果証跡。

    Returns:
        検証器が返す本文完全性の不合格理由。
    """
    root = init_invalidation_repository(tmp_path)
    return verify.validate_evidence_completeness(
        root,
        invalidation_head(root),
        record,
    )


def schema_violations(filename: str, text: str) -> tuple[str, ...]:
    """1 件のレコードに対する全スキーマ違反を得る。

    Args:
        filename: 受入証跡ディレクトリ直下からの相対パス。
        text: 解析する証跡内容。

    Returns:
        レコード単体のスキーマ違反。
    """
    return verify.validate_records((parse_record(filename, text),))


def test_parses_existing_reservation_record() -> None:
    """実在する予約 seq001 を reservation として成分・スキーマとも検証する。"""
    path = ACCEPTANCE_DIRECTORY / RESERVATION_FILENAME
    record = parse_record(RESERVATION_FILENAME, path.read_text(encoding="utf-8"))

    assert record.path.kind == verify.KIND_RESERVATION
    assert record.path.timestamp == "2026-08-19T142916Z"
    assert record.path.gate_key == "phase4"
    assert record.path.attempt_seq == 1
    assert verify.validate_records((record,)) == ()


@pytest.mark.parametrize(
    ("filename", "gate_kind", "release_version", "attempt_seq"),
    [
        (
            "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
            "phase4",
            None,
            1,
        ),
        (
            "2026-08-19T101500Z-release-v1.2.3-seq1000-0123456789ab.md",
            "release",
            "v1.2.3",
            1000,
        ),
    ],
)
def test_parses_canonical_evidence_filenames(
    filename: str,
    gate_kind: str,
    release_version: str | None,
    attempt_seq: int,
) -> None:
    """phase4 と release の正規結果証跡名から全成分を取得する。"""
    parsed = verify.parse_acceptance_path(filename)

    assert parsed.kind == verify.KIND_EVIDENCE
    assert parsed.timestamp == RECORD_TIMESTAMP
    assert parsed.gate_kind == gate_kind
    assert parsed.release_version == release_version
    assert parsed.attempt_seq == attempt_seq
    assert parsed.short_sha == COMMIT_SHA[:12]
    assert parsed.reason is None


@pytest.mark.parametrize(
    "filename",
    [
        "README.md",
        "reservation-template.md",
        "evidence-phase4-template.md",
        "evidence-release-template.md",
    ],
)
def test_classifies_only_the_four_primary_documents_as_canonical(filename: str) -> None:
    """正本 4 件を canonical とし、列挙対象のレコードから除外できることを検証する。"""
    parsed = verify.parse_acceptance_path(filename)

    assert parsed.kind == verify.KIND_CANONICAL
    assert parsed.timestamp is None
    assert parsed.gate_kind is None
    assert parsed.gate_key is None
    assert parsed.attempt_seq is None
    assert parsed.short_sha is None
    assert parsed.reason is None
    assert parsed.kind not in verify.RECORD_KINDS


def test_allows_two_sequences_at_the_same_gate_and_second() -> None:
    """同一ゲート・同一秒でも seq が異なる 2 件の予約を共存させる。"""
    first = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
        reservation_text(attempt_seq=1),
    )
    second = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq002-reservation.md",
        reservation_text(attempt_seq=2),
    )

    assert first.path.timestamp == second.path.timestamp
    assert first.path.attempt_seq != second.path.attempt_seq
    assert verify.validate_records((first, second)) == ()


def test_allows_started_at_that_differs_from_filename_timestamp() -> None:
    """started_at とファイル名の時刻に一致要求を追加しないことを検証する。"""
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
        reservation_text(started_at="2026-08-20T101500Z"),
    )

    assert verify.validate_records((record,)) == ()


@pytest.mark.parametrize(
    ("filename", "text"),
    [
        (
            "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
            evidence_text(),
        ),
        (
            "2026-08-19T101500Z-release-v1.2.3-seq001-0123456789ab.md",
            evidence_text(
                gate_kind="release",
                release_version="v1.2.3",
            ),
        ),
    ],
)
def test_accepts_valid_phase4_and_release_evidence(
    filename: str,
    text: str,
) -> None:
    """両ゲート種別の結果証跡スキーマと二重記録が通ることを検証する。"""
    assert schema_violations(filename, text) == ()


def test_accepts_matching_reservation_and_evidence_contract() -> None:
    """同じ attempt_id の予約と結果が一致すればレコード間契約を通す。"""
    filename = "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md"
    reservation = parse_record(filename, reservation_text())
    evidence = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(),
    )

    assert verify.validate_records((reservation, evidence)) == ()


@pytest.mark.parametrize(
    "relative_path",
    [
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.MD",
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.yaml",
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation",
        "archive",
        (
            "archive/"
            "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md"
        ),
    ],
)
def test_rejects_unknown_extensions_and_subdirectory_items(relative_path: str) -> None:
    """拡張子差、ディレクトリ自身、配下の正規名をすべて invalid にする。"""
    parsed = verify.parse_acceptance_path(relative_path)

    assert parsed.kind == verify.KIND_INVALID
    assert parsed.reason is not None


def test_rejects_uppercase_canonical_filename_as_an_invalid_tree_item() -> None:
    """README.MD を正本として扱わず閉じた命名文法の外へ置く。"""
    parsed = verify.parse_acceptance_path("README.MD")

    assert parsed.kind == verify.KIND_INVALID
    assert parsed.reason is not None


@pytest.mark.parametrize("sequence", ["0001", "1", "000"])
def test_rejects_noncanonical_filename_sequence(sequence: str) -> None:
    """seq0001、seq1、seq000 を正規形ではないとして拒否する。"""
    parsed = verify.parse_acceptance_path(
        f"2026-08-19T101500Z-phase4-phase4-seq{sequence}-reservation.md"
    )

    assert parsed.kind == verify.KIND_INVALID
    assert parsed.reason == verify.REASON_INVALID_SEQUENCE


@pytest.mark.parametrize(
    "short_sha",
    [
        "0123456789a",
        "0123456789abc",
        "0123456789AB",
    ],
)
def test_rejects_noncanonical_filename_short_sha(short_sha: str) -> None:
    """11 桁、13 桁、大文字入り short SHA を invalid にする。"""
    parsed = verify.parse_acceptance_path(
        f"2026-08-19T101500Z-phase4-phase4-seq001-{short_sha}.md"
    )

    assert parsed.kind == verify.KIND_INVALID
    assert parsed.reason is not None


@pytest.mark.parametrize(
    "filename",
    [
        "2026-08-19T101500Z-phase4-v1.0.0-seq001-reservation.md",
        "2026-08-19T101500Z-release-phase4-seq001-reservation.md",
    ],
)
def test_rejects_invalid_gate_pairs(filename: str) -> None:
    """phase4-v と release-phase4 のゲート組を invalid にする。"""
    parsed = verify.parse_acceptance_path(filename)

    assert parsed.kind == verify.KIND_INVALID
    assert parsed.reason == verify.REASON_INVALID_GATE_PAIR


def test_rejects_nonexistent_filename_timestamp() -> None:
    """実在しないファイル名時刻を正規表現通過後にも拒否する。"""
    parsed = verify.parse_acceptance_path(
        "2026-02-30T101500Z-phase4-phase4-seq001-reservation.md"
    )

    assert parsed.kind == verify.KIND_INVALID
    assert parsed.reason == verify.REASON_INVALID_TIMESTAMP


@pytest.mark.parametrize(
    "extra_line",
    [
        "gate_kind: phase4",
        "release_version: v1.2.3",
    ],
)
def test_rejects_gate_keys_on_reservation(extra_line: str) -> None:
    """予約が gate_kind または release_version を重複保持することを拒否する。"""
    violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
        reservation_text(extra_lines=(extra_line,)),
    )

    assert any("未知のキー" in violation for violation in violations)


@pytest.mark.parametrize("value", ['"1"', "0", "-1", "not-a-number"])
def test_rejects_noninteger_or_nonpositive_attempt_sequence(value: str) -> None:
    """引用符付き、0 以下、非 10 進の attempt_seq を拒否する。"""
    violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
        reservation_text(attempt_seq_value=value),
    )

    assert any("attempt_seq" in violation for violation in violations)


@pytest.mark.parametrize(
    "attempt_id_value",
    [
        "release-v1.2.3-001-20260819T101500Z",
        "phase4-002-20260819T101500Z",
        "phase4-001-2026-08-19T101500Z",
        "phase4-001-20260230T101500Z",
    ],
)
def test_rejects_invalid_or_inconsistent_attempt_id(attempt_id_value: str) -> None:
    """attempt_id のゲート、連番、時刻書式、実在時刻を拒否する。"""
    violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
        reservation_text(attempt_id_value=attempt_id_value),
    )

    assert any("attempt_id" in violation for violation in violations)


def test_rejects_result_outside_closed_vocabulary() -> None:
    """result: typo を passed または failed 以外として拒否する。"""
    violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(result="typo"),
    )

    assert any("result が passed または failed ではない" in violation for violation in violations)


def test_rejects_release_version_on_phase4_evidence() -> None:
    """phase4 の結果証跡が release_version を持つことを拒否する。"""
    violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(release_version="v1.2.3"),
    )

    assert any(
        "phase4 の結果証跡に release_version がある" in violation
        for violation in violations
    )


@pytest.mark.parametrize(
    ("record_kind", "extra_line"),
    [
        ("reservation", 'candidate_sha: "0123456789abcdef0123456789abcdef01234567"'),
        ("reservation", 'phase4_base_sha: "0123456789abcdef0123456789abcdef01234567"'),
        ("evidence", 'candidate_sha: "0123456789abcdef0123456789abcdef01234567"'),
        ("evidence", 'phase4_base_sha: "0123456789abcdef0123456789abcdef01234567"'),
    ],
)
def test_rejects_unknown_frontmatter_keys(
    record_kind: str,
    extra_line: str,
) -> None:
    """予約・結果の双方で candidate_sha と phase4_base_sha の混入を拒否する。"""
    if record_kind == "reservation":
        violations = schema_violations(
            "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
            reservation_text(extra_lines=(extra_line,)),
        )
    else:
        violations = schema_violations(
            "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
            evidence_text(extra_lines=(extra_line,)),
        )

    assert any("未知のキー" in violation for violation in violations)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("tested_commit_sha", COMMIT_SHA[:-1]),
        ("tested_commit_sha", COMMIT_SHA + "0"),
        ("tested_commit_sha", COMMIT_SHA[:16].upper() + COMMIT_SHA[16:]),
        ("onboarding_blob_sha", ONBOARDING_BLOB_SHA[:-1]),
        ("onboarding_blob_sha", ONBOARDING_BLOB_SHA + "0"),
        (
            "onboarding_blob_sha",
            ONBOARDING_BLOB_SHA[:10].upper() + ONBOARDING_BLOB_SHA[10:],
        ),
    ],
)
def test_rejects_noncanonical_full_oid(key: str, value: str) -> None:
    """39 桁、41 桁、大文字混在の commit/blob OID を拒否する。"""
    tested_commit_sha = value if key == "tested_commit_sha" else COMMIT_SHA
    onboarding_blob_sha = (
        value if key == "onboarding_blob_sha" else ONBOARDING_BLOB_SHA
    )
    violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(
            tested_commit_sha=tested_commit_sha,
            onboarding_blob_sha=onboarding_blob_sha,
        ),
    )

    assert any(
        f"{key} が完全な小文字 16 進 40 桁ではない" in violation
        for violation in violations
    ), violations


@pytest.mark.parametrize(
    ("filename", "text"),
    [
        (
            "2026-08-19T101500Z-phase4-phase4-seq002-0123456789ab.md",
            evidence_text(attempt_seq=3),
        ),
        (
            "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
            evidence_text(
                gate_kind="release",
                release_version="v1.2.3",
            ),
        ),
        (
            "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
            evidence_text(tested_commit_sha=OTHER_COMMIT_SHA),
        ),
        (
            "2026-08-19T101500Z-release-v1.2.3-seq001-0123456789ab.md",
            evidence_text(
                gate_kind="release",
                release_version="v2.0.0",
            ),
        ),
    ],
)
def test_rejects_filename_and_frontmatter_mismatches(
    filename: str,
    text: str,
) -> None:
    """連番、ゲート種別、short SHA、release 版の対応不一致を拒否する。"""
    violations = schema_violations(filename, text)

    assert any("ファイル名" in violation for violation in violations)


@pytest.mark.parametrize(
    "mismatch",
    [
        "gate_key",
        "attempt_seq",
        "release_version",
    ],
)
def test_rejects_inconsistent_records_with_the_same_attempt_id(
    mismatch: str,
) -> None:
    """同一 attempt_id の予約・結果で各契約値が食い違うことを拒否する。"""
    if mismatch == "gate_key":
        reservation = parse_record(
            "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
            reservation_text(),
        )
        evidence = parse_record(
            "2026-08-19T101500Z-release-v1.2.3-seq001-0123456789ab.md",
            evidence_text(
                gate_kind="release",
                release_version="v1.2.3",
                attempt_id_value=attempt_id("phase4", 1),
            ),
        )
        expected_reason = verify.REASON_CONTRACT_GATE_KEY
    elif mismatch == "attempt_seq":
        reservation = parse_record(
            "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
            reservation_text(),
        )
        evidence = parse_record(
            "2026-08-19T101500Z-phase4-phase4-seq002-0123456789ab.md",
            evidence_text(
                attempt_seq=2,
                attempt_id_value=attempt_id("phase4", 1),
            ),
        )
        expected_reason = verify.REASON_CONTRACT_SEQUENCE
    else:
        reservation = parse_record(
            "2026-08-19T101500Z-release-v1.2.3-seq001-reservation.md",
            reservation_text(gate_key="release-v1.2.3"),
        )
        evidence = parse_record(
            "2026-08-19T101500Z-release-v1.2.4-seq001-0123456789ab.md",
            evidence_text(
                gate_kind="release",
                release_version="v1.2.4",
                attempt_id_value=attempt_id("release-v1.2.3", 1),
            ),
        )
        expected_reason = verify.REASON_CONTRACT_RELEASE_VERSION

    violations = verify.validate_record_relationships((reservation, evidence))

    assert any(expected_reason in violation for violation in violations)


@pytest.mark.parametrize(
    ("body_commit_sha", "body_onboarding_blob_sha", "label"),
    [
        (OTHER_COMMIT_SHA, None, "commit SHA"),
        (None, OTHER_ONBOARDING_BLOB_SHA, "onboarding blob SHA"),
    ],
)
def test_rejects_body_and_frontmatter_double_record_mismatch(
    body_commit_sha: str | None,
    body_onboarding_blob_sha: str | None,
    label: str,
) -> None:
    """本文の commit/blob SHA が frontmatter と異なる結果証跡を拒否する。"""
    violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(
            body_commit_sha=body_commit_sha,
            body_onboarding_blob_sha=body_onboarding_blob_sha,
        ),
    )

    assert any(f"本文の {label}" in violation for violation in violations)


@pytest.mark.parametrize(
    ("filename", "text", "expects_parse_error"),
    [
        (
            "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
            build_frontmatter(
                [
                    'gate_key: "phase4"',
                    "attempt_seq: 1",
                    'attempt_id: "phase4-001-20260819T101500Z"',
                    'started_at: "2026-02-30T101500Z"',
                    'operator: "テスト担当者"',
                ]
            ),
            False,
        ),
        (
            "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
            '---\ngate_key: "phase4"\nattempt_seq: 1\n',
            True,
        ),
    ],
)
def test_rejects_invalid_started_at_and_malformed_frontmatter(
    filename: str,
    text: str,
    expects_parse_error: bool,
) -> None:
    """started_at の実在時刻違反と区切り記号欠落を fail-closed にする。"""
    if not expects_parse_error:
        violations = schema_violations(filename, text)
        assert any("started_at が実在時刻ではない" in violation for violation in violations)
    else:
        with pytest.raises(verify.GuardError):
            parse_record(filename, text)


def test_rejects_missing_required_keys() -> None:
    """予約と結果の必須キー不足を閉じたスキーマ違反として拒否する。"""
    reservation = reservation_text().replace('operator: "テスト担当者"\n', "", 1)
    evidence = evidence_text().replace(
        f'onboarding_blob_sha: "{ONBOARDING_BLOB_SHA}"\n',
        "",
        1,
    )

    reservation_violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
        reservation,
    )
    evidence_violations = schema_violations(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence,
    )

    assert any("必須キーがない" in violation for violation in reservation_violations)
    assert any("必須キーがない" in violation for violation in evidence_violations)


def test_lexical_literals_match_the_index_coverage_predicate(tmp_path: Path) -> None:
    """索引除外述語と本実装の時刻・組・seq・short SHA 規則の腐りを検出する。"""
    check_docs_status = load_module(
        DOCS_STATUS_SCRIPT,
        "check_docs_status_for_nfr021_literal_test",
    )
    index_pattern = check_docs_status.NFR021_ACCEPTANCE_RECORD_RE.pattern

    assert verify.TIMESTAMP_PATTERN in index_pattern
    assert verify.GATE_PAIR_PATTERN in index_pattern
    assert verify.SHORT_SHA_PATTERN in index_pattern
    for sequence in ("001", "1000", "0001", "1", "000"):
        assert verify.is_canonical_attempt_sequence(sequence) == (
            check_docs_status.is_canonical_nfr021_attempt_sequence(sequence)
        )

    directory = tmp_path / "docs" / "ops" / "nfr021-acceptance"
    for filename in (
        "2026-08-19T101500Z-phase4-phase4-seq001-reservation.md",
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        "2026-08-19T101500Z-release-v1.2.3-seq1000-0123456789ab.md",
        "2026-08-19T101500Z-phase4-phase4-seq0001-reservation.md",
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789AB.md",
    ):
        index_result = check_docs_status.is_nfr021_acceptance_record_for_index_coverage(
            directory / filename,
            tmp_path,
        )
        parsed = verify.parse_acceptance_path(filename)
        assert index_result == (parsed.kind in verify.RECORD_KINDS)


def git_for_invalidation(
    cwd: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """失効判定用の一時リポジトリに Git コマンドを実行する。

    Args:
        cwd: Git コマンドを実行する一時リポジトリのルート。
        *args: git に渡すサブコマンド以降の引数。

    Returns:
        標準出力と標準エラーを捕捉した Git コマンドの実行結果。
    """
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )


def write_invalidation_bytes(root: Path, relative_path: str, contents: bytes) -> None:
    """一時リポジトリに任意のバイト列のファイルを書き出す。

    Args:
        root: 一時リポジトリのルート。
        relative_path: root からの相対パス。
        contents: 書き込む生のバイト列。

    Returns:
        戻り値はない。
    """
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)


def write_invalidation_file(root: Path, relative_path: str, content: str) -> None:
    """一時リポジトリに UTF-8 テキストファイルを書き出す。

    Args:
        root: 一時リポジトリのルート。
        relative_path: root からの相対パス。
        content: 書き込むテキスト。

    Returns:
        戻り値はない。
    """
    write_invalidation_bytes(root, relative_path, content.encode("utf-8"))


def write_invalidation_symlink(root: Path, relative_path: str, target: str) -> None:
    """一時リポジトリの指定パスを任意のリンク先文字列を持つ symlink にする。

    Args:
        root: 一時 Git リポジトリのルート。
        relative_path: root からの相対パス。
        target: symlink に記録するリンク先文字列。

    Returns:
        戻り値はない。
    """
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    path.symlink_to(target)


def commit_invalidation_changes(root: Path, subject: str) -> None:
    """一時リポジトリの変更をすべてコミットする。

    Args:
        root: 一時リポジトリのルート。
        subject: コミット件名。

    Returns:
        戻り値はない。
    """
    git_for_invalidation(root, "add", "-A")
    git_for_invalidation(root, "commit", "-qm", subject)


def init_invalidation_repository(tmp_path: Path, branch: str = "develop") -> Path:
    """失効判定の履歴を組み立てる最小の一時 Git リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        branch: 初期コミットを置くブランチ名。

    Returns:
        初期コミット済みの一時リポジトリのルート。
    """
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", branch, str(root)],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    git_for_invalidation(root, "config", "user.email", "test@example.com")
    git_for_invalidation(root, "config", "user.name", "test")
    write_invalidation_file(root, "README.md", "# test\n")
    write_invalidation_bytes(root, "scripts/verify_nfr021_evidence.py", SCRIPT.read_bytes())
    write_invalidation_bytes(
        root,
        ".claude/nfr021-invalidating-paths.json",
        INVALIDATING_PATHS_CONFIG.read_bytes(),
    )
    write_invalidation_bytes(
        root,
        "docs/ops/nfr021-acceptance/evidence-phase4-template.md",
        PHASE4_EVIDENCE_TEMPLATE.read_bytes(),
    )
    write_invalidation_bytes(
        root,
        "docs/ops/nfr021-acceptance/evidence-release-template.md",
        RELEASE_EVIDENCE_TEMPLATE.read_bytes(),
    )
    commit_invalidation_changes(root, "chore: base")
    return root


def invalidation_head(root: Path) -> str:
    """一時リポジトリの現在のコミット OID を得る。

    Args:
        root: 一時リポジトリのルート。

    Returns:
        現在の HEAD を表す完全なコミット OID。
    """
    return git_for_invalidation(root, "rev-parse", "HEAD").stdout.strip()


def load_real_invalidation_settings() -> object:
    """リポジトリの失効パス設定をテスト用に読み込む。

    Args:
        なし。

    Returns:
        検証器が返す実設定オブジェクト。
    """
    return verify.load_invalidation_settings(INVALIDATING_PATHS_CONFIG)


def make_invalidation_settings(
    *,
    invalidating: tuple[str, ...] = ("/backend/**",),
    allowlist: tuple[str, ...] = (),
    default: str = "invalidating",
) -> object:
    """照合規則を固定したテスト用の失効パス設定を作る。

    Args:
        invalidating: 失効対象にするルート相対パターン。
        allowlist: 失効させないルート相対パターン。
        default: どちらにも一致しないパスの方針。

    Returns:
        検証器が返す検証済み設定オブジェクト。
    """
    return verify.parse_invalidation_settings(
        {
            "syntax": "gitignore-root-relative-v1",
            "default": default,
            "invalidating": list(invalidating),
            "allowlist": list(allowlist),
        }
    )


def test_changed_paths_include_created_then_deleted_path(tmp_path: Path) -> None:
    """範囲内で作成後に削除された失効対象パスをログの和集合で検出する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha = invalidation_head(root)
    transient_path = "backend/transient.py"
    write_invalidation_file(root, transient_path, "before deletion\n")
    commit_invalidation_changes(root, "feat: add transient path")
    (root / transient_path).unlink()
    commit_invalidation_changes(root, "chore: delete transient path")
    candidate_sha = invalidation_head(root)

    changed_paths = verify.changed_paths_between(
        root,
        tested_commit_sha,
        candidate_sha,
    )
    two_point_paths = set(
        git_for_invalidation(
            root,
            "diff",
            "--name-only",
            tested_commit_sha,
            candidate_sha,
        ).stdout.splitlines()
    )
    result = verify.evaluate_invalidation(
        root,
        tested_commit_sha,
        candidate_sha,
        load_real_invalidation_settings(),
    )

    assert transient_path in changed_paths
    assert transient_path not in two_point_paths
    assert result.invalidated
    assert any(
        classification.path == transient_path
        and classification.matched_pattern == "/backend/**"
        for classification in result.classifications
    )


def test_changed_paths_preserve_non_ascii_allowlist_path_with_null_termination(
    tmp_path: Path,
) -> None:
    """日本語を含む docs/features 配下だけの変更を失効として誤判定しない。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha = invalidation_head(root)
    changed_path = "docs/features/日本語.md"
    write_invalidation_file(root, changed_path, "allowlisted\n")
    commit_invalidation_changes(root, "docs: add non-ascii feature note")
    candidate_sha = invalidation_head(root)

    paths = verify.changed_paths_between(root, tested_commit_sha, candidate_sha)
    result = verify.evaluate_invalidation(
        root,
        tested_commit_sha,
        candidate_sha,
        load_real_invalidation_settings(),
    )

    assert paths == frozenset({changed_path})
    assert not result.invalidated


def test_changed_paths_include_merge_commit_path(tmp_path: Path) -> None:
    """-m によりマージコミット経由で入った失効対象パスを検出する。"""
    root = init_invalidation_repository(tmp_path)
    write_invalidation_file(root, "backend/shared.py", "base\n")
    commit_invalidation_changes(root, "feat: add shared path")
    tested_commit_sha = invalidation_head(root)
    merged_path = "backend/merge-resolution-only.py"
    git_for_invalidation(root, "checkout", "-q", "-b", "feature/invalidation")
    write_invalidation_file(root, "backend/shared.py", "feature\n")
    commit_invalidation_changes(root, "feat: change shared path")
    git_for_invalidation(root, "checkout", "-q", "develop")
    write_invalidation_file(root, "backend/shared.py", "develop\n")
    commit_invalidation_changes(root, "feat: change shared path on develop")
    with pytest.raises(subprocess.CalledProcessError):
        git_for_invalidation(root, "merge", "--no-ff", "feature/invalidation")
    write_invalidation_file(root, "backend/shared.py", "resolved\n")
    write_invalidation_file(root, merged_path, "merge-only\n")
    commit_invalidation_changes(root, "merge: resolve invalidation feature")
    candidate_sha = invalidation_head(root)

    changed_paths = verify.changed_paths_between(
        root,
        tested_commit_sha,
        candidate_sha,
    )
    paths_without_merge_expansion = set(
        git_for_invalidation(
            root,
            "log",
            "--format=",
            "--name-only",
            f"{tested_commit_sha}..{candidate_sha}",
        ).stdout.splitlines()
    )

    assert merged_path in changed_paths
    assert merged_path not in paths_without_merge_expansion


def test_changed_paths_preserve_old_path_of_rename(tmp_path: Path) -> None:
    """--no-renames により失効対象から allowlist への移動で旧パスを保持する。"""
    root = init_invalidation_repository(tmp_path)
    old_path = "backend/original.txt"
    new_path = "docs/features/moved.txt"
    write_invalidation_file(root, old_path, "same content\n")
    commit_invalidation_changes(root, "feat: add original")
    tested_commit_sha = invalidation_head(root)
    git_for_invalidation(root, "config", "diff.renames", "true")
    (root / "docs" / "features").mkdir(parents=True)
    git_for_invalidation(root, "mv", old_path, new_path)
    commit_invalidation_changes(root, "refactor: move path")
    candidate_sha = invalidation_head(root)

    changed_paths = verify.changed_paths_between(
        root,
        tested_commit_sha,
        candidate_sha,
    )
    result = verify.evaluate_invalidation(
        root,
        tested_commit_sha,
        candidate_sha,
        load_real_invalidation_settings(),
    )
    paths_with_rename_detection = set(
        git_for_invalidation(
            root,
            "log",
            "--format=",
            "--name-only",
            f"{tested_commit_sha}..{candidate_sha}",
        ).stdout.splitlines()
    )

    assert old_path in changed_paths
    assert new_path in changed_paths
    assert old_path not in paths_with_rename_detection
    assert result.invalidated
    assert any(
        classification.path == old_path
        and classification.matched_pattern == "/backend/**"
        for classification in result.classifications
    )


def test_non_ancestor_tested_commit_invalidates_evidence(tmp_path: Path) -> None:
    """T が C の祖先でない場合を判定不能ではなく失効として扱う。"""
    root = init_invalidation_repository(tmp_path)
    git_for_invalidation(root, "checkout", "-q", "-b", "feature/other")
    write_invalidation_file(root, "docs/features/other.md", "other\n")
    commit_invalidation_changes(root, "docs: other branch")
    tested_commit_sha = invalidation_head(root)
    git_for_invalidation(root, "checkout", "-q", "develop")
    write_invalidation_file(root, "docs/features/candidate.md", "candidate\n")
    commit_invalidation_changes(root, "docs: candidate branch")
    candidate_sha = invalidation_head(root)

    result = verify.evaluate_invalidation(
        root,
        tested_commit_sha,
        candidate_sha,
        load_real_invalidation_settings(),
    )

    assert not verify.is_ancestor(root, tested_commit_sha, candidate_sha)
    assert result.invalidated
    assert not result.ancestor
    assert result.classifications == ()


def test_unresolvable_ancestor_oid_raises_guard_error(tmp_path: Path) -> None:
    """存在しない完全 OID を祖先でない場合と混同せず fail-closed にする。"""
    root = init_invalidation_repository(tmp_path)

    with pytest.raises(verify.GuardError, match="解決不能"):
        verify.is_ancestor(root, "0" * 40, invalidation_head(root))


@pytest.mark.parametrize(
    ("operation", "side_effect"),
    [
        (
            "ancestor",
            subprocess.TimeoutExpired(["git", "merge-base"], timeout=1),
        ),
        ("changed_paths", OSError("git executable is unavailable")),
    ],
)
def test_git_timeout_and_start_failure_raise_guard_error(
    tmp_path: Path,
    operation: str,
    side_effect: BaseException,
) -> None:
    """Git のタイムアウトと起動失敗をいずれも GuardError へ変換する。"""
    root = tmp_path / "not-a-repository"
    with patch.object(verify.subprocess, "run", side_effect=side_effect):
        with pytest.raises(verify.GuardError):
            if operation == "ancestor":
                verify.is_ancestor(root, "1" * 40, "2" * 40)
            else:
                verify.changed_paths_between(root, "1" * 40, "2" * 40)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("backend/app.py", True),
        ("backend/x/y.py", True),
        ("backend", False),
        ("backend2/x.py", False),
    ],
)
def test_recursive_pattern_matches_only_descendants(
    path: str,
    expected: bool,
) -> None:
    """/backend/** が配下だけを一致させ、接頭辞誤一致を起こさない。"""
    assert verify.path_matches_invalidation_pattern(path, "/backend/**") is expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("backend/app.py", True),
        ("backend/nested/app.py", False),
    ],
)
def test_single_segment_wildcard_does_not_cross_path_separator(
    path: str,
    expected: bool,
) -> None:
    """* が 1 セグメントだけに一致し、スラッシュを跨がないことを確認する。"""
    assert verify.path_matches_invalidation_pattern(path, "/backend/*.py") is expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("docs/development/onboarding.md", True),
        ("docs/development/onboarding.md.bak", False),
    ],
)
def test_non_recursive_pattern_requires_complete_path_match(
    path: str,
    expected: bool,
) -> None:
    """末尾 ** を持たないパターンを完全一致として扱う。"""
    assert (
        verify.path_matches_invalidation_pattern(
            path,
            "/docs/development/onboarding.md",
        )
        is expected
    )


def test_allowlisted_docs_features_path_does_not_invalidate() -> None:
    """/docs/features/** のみの変更は allowlist として失効させない。"""
    settings = load_real_invalidation_settings()

    classification = verify.classify_invalidation_path(
        "docs/features/nfr021/plan.md",
        settings,
    )

    assert classification.classification == verify.CLASSIFICATION_ALLOWLIST
    assert classification.matched_pattern == "/docs/features/**"
    assert not classification.invalidating


def test_worklog_and_acceptance_paths_do_not_invalidate() -> None:
    """worklog と受入証跡ディレクトリだけの変更は allowlist として扱う。"""
    settings = load_real_invalidation_settings()
    classifications = tuple(
        verify.classify_invalidation_path(path, settings)
        for path in (
            "docs/worklog/2026-08-21.md",
            "docs/ops/nfr021-acceptance/result.md",
        )
    )

    assert all(
        classification.classification == verify.CLASSIFICATION_ALLOWLIST
        for classification in classifications
    )
    assert not any(classification.invalidating for classification in classifications)


def test_unclassified_path_follows_invalidating_default() -> None:
    """どちらの設定リストにもないパスを実設定の default に従わせる。"""
    classification = verify.classify_invalidation_path(
        "README.md",
        load_real_invalidation_settings(),
    )

    assert classification.classification == verify.CLASSIFICATION_DEFAULT
    assert classification.matched_pattern is None
    assert classification.invalidating


def test_rejects_allowlist_as_invalidation_default() -> None:
    """未分類パスを通す allowlist の default を fail-closed に拒否する。"""
    with pytest.raises(verify.GuardError):
        make_invalidation_settings(default="allowlist")


def test_invalidating_pattern_wins_when_path_matches_both_lists() -> None:
    """両リストに一致するパスは fail-closed で invalidating を優先する。"""
    settings = make_invalidation_settings(
        invalidating=("/docs/features/**",),
        allowlist=("/docs/features/**",),
    )

    classification = verify.classify_invalidation_path("docs/features/plan.md", settings)

    assert classification.classification == verify.CLASSIFICATION_INVALIDATING
    assert classification.matched_pattern == "/docs/features/**"
    assert classification.invalidating


@pytest.mark.parametrize(
    "value",
    [
        {
            "syntax": "unknown-pattern-v1",
            "default": "invalidating",
            "invalidating": ["/backend/**"],
            "allowlist": [],
        },
        {
            "syntax": "gitignore-root-relative-v1",
            "default": "invalidating",
            "invalidating": ["!/backend/**"],
            "allowlist": [],
        },
        {
            "syntax": "gitignore-root-relative-v1",
            "default": "invalidating",
            "invalidating": ["backend/**"],
            "allowlist": [],
        },
    ],
)
def test_rejects_unknown_or_unsafe_invalidation_settings(value: dict[str, object]) -> None:
    """未知文法、否定、非ルート相対のパターンを fail-closed で拒否する。"""
    with pytest.raises(verify.GuardError):
        verify.parse_invalidation_settings(value)


def test_real_allowlist_has_expected_three_patterns_and_matches_them() -> None:
    """実設定の閉じた allowlist 3 件を読み、その照合結果を確認する。"""
    settings = load_real_invalidation_settings()

    assert settings.allowlist_patterns == (
        "/docs/ops/nfr021-acceptance/**",
        "/docs/worklog/**",
        "/docs/features/**",
    )
    for path in (
        "docs/ops/nfr021-acceptance/evidence.md",
        "docs/worklog/2026-08-21.md",
        "docs/features/nfr021-evidence-verifier/design.md",
    ):
        assert not verify.classify_invalidation_path(path, settings).invalidating


def test_real_settings_keeps_closed_allowlist_and_invalidating_default() -> None:
    """実設定の allowlist 3 件と未分類を失効させる default を固定する。"""
    settings = load_real_invalidation_settings()

    assert settings.default == verify.DEFAULT_POLICY_INVALIDATING
    assert settings.allowlist_patterns == (
        "/docs/ops/nfr021-acceptance/**",
        "/docs/worklog/**",
        "/docs/features/**",
    )


def run_verifier(
    root: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """検証器 CLI を一時リポジトリに対して起動する。

    Args:
        root: 検証対象にする一時 Git リポジトリのルート。
        *args: --root の後に渡す CLI 引数。

    Returns:
        標準出力と標準エラーを取得した検証器の実行結果。
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )


def commit_onboarding(
    root: Path,
    *,
    status: str = "approved",
    extra_files: tuple[tuple[str, str], ...] = (),
) -> tuple[str, str]:
    """指定 status の onboarding を実施時点 T としてコミットする。

    Args:
        root: 一時 Git リポジトリのルート。
        status: onboarding frontmatter に書く status。
        extra_files: T と同じコミットに置く追加の ``(相対パス, 内容)`` 組。

    Returns:
        ``(tested_commit_sha, onboarding_blob_sha)`` の組。
    """
    write_invalidation_file(
        root,
        "docs/development/onboarding.md",
        "\n".join(["---", f"status: {status}", "---", "", "# onboarding", ""]),
    )
    for filename in ("README.md", "reservation-template.md"):
        write_invalidation_file(
            root,
            f"docs/ops/nfr021-acceptance/{filename}",
            "# 正本\n",
        )
    for relative_path, content in extra_files:
        write_invalidation_file(root, relative_path, content)
    commit_invalidation_changes(root, "docs: add onboarding")
    tested_commit_sha = invalidation_head(root)
    onboarding_blob_sha = git_for_invalidation(
        root,
        "rev-parse",
        f"{tested_commit_sha}:docs/development/onboarding.md",
    ).stdout.strip()
    return tested_commit_sha, onboarding_blob_sha


def evidence_filename(
    gate_kind: str,
    release_version: str | None,
    tested_commit_sha: str,
    *,
    attempt_seq: int = 1,
    timestamp: str = RECORD_TIMESTAMP,
) -> str:
    """テスト用の正規形結果証跡ファイル名を作る。

    Args:
        gate_kind: phase4 または release。
        release_version: release の場合の版。phase4 では None。
        tested_commit_sha: ファイル名末尾の short SHA の基になる OID。
        attempt_seq: ファイル名に書く 1 以上の連番。
        timestamp: ファイル名先頭に書くハイフン付き UTC 時刻。

    Returns:
        受入証跡ディレクトリ直下に置ける結果証跡ファイル名。
    """
    gate_value = "phase4" if gate_kind == "phase4" else release_version
    assert gate_value is not None
    return (
        f"{timestamp}-{gate_kind}-{gate_value}-seq{attempt_seq:03d}-"
        f"{tested_commit_sha[:12]}.md"
    )


def reservation_filename(
    gate_key: str,
    *,
    attempt_seq: int = 1,
    timestamp: str = RECORD_TIMESTAMP,
) -> str:
    """テスト用の正規形予約レコード名を作る。

    Args:
        gate_key: phase4 または release-vX.Y.Z の合成ゲートキー。
        attempt_seq: ファイル名に書く 1 以上の連番。
        timestamp: ファイル名先頭に書くハイフン付き UTC 時刻。

    Returns:
        受入証跡ディレクトリ直下に置ける予約レコード名。
    """
    if gate_key == "phase4":
        gate_kind = "phase4"
        gate_value = "phase4"
    else:
        gate_kind = "release"
        gate_value = gate_key.removeprefix("release-")
    return f"{timestamp}-{gate_kind}-{gate_value}-seq{attempt_seq:03d}-reservation.md"


def commit_reservation(
    root: Path,
    *,
    gate_key: str = "phase4",
    attempt_seq: int = 1,
    timestamp: str = RECORD_TIMESTAMP,
    attempt_id_value: str | None = None,
    extra_lines: tuple[str, ...] = (),
) -> str:
    """候補ツリーへ予約レコードを 1 件追加してコミットする。

    Args:
        root: 一時 Git リポジトリのルート。
        gate_key: frontmatter とファイル名に書く合成ゲートキー。
        attempt_seq: frontmatter とファイル名に書く 1 以上の連番。
        timestamp: ファイル名先頭に書くハイフン付き UTC 時刻。
        attempt_id_value: frontmatter へ直接書く attempt_id。省略時は正規形。
        extra_lines: frontmatter へ加えるテスト用の追加行。

    Returns:
        追加した予約レコードのリポジトリ相対パス。
    """
    filename = reservation_filename(
        gate_key,
        attempt_seq=attempt_seq,
        timestamp=timestamp,
    )
    relative_path = f"docs/ops/nfr021-acceptance/{filename}"
    write_invalidation_file(
        root,
        relative_path,
        reservation_text(
            gate_key=gate_key,
            attempt_seq=attempt_seq,
            attempt_id_value=attempt_id_value,
            extra_lines=extra_lines,
        ),
    )
    commit_invalidation_changes(root, "docs: add reservation")
    return relative_path


def commit_evidence(
    root: Path,
    tested_commit_sha: str,
    onboarding_blob_sha: str,
    *,
    gate_kind: str = "phase4",
    release_version: str | None = None,
    result: str = "passed",
    evidence_path: str | None = None,
    attempt_seq: int = 1,
    timestamp: str = RECORD_TIMESTAMP,
    attempt_id_value: str | None = None,
    extra_lines: tuple[str, ...] = (),
    body: str | None = None,
) -> tuple[str, str]:
    """名指し検証に使う結果証跡を候補コミット C へ追加する。

    Args:
        root: 一時 Git リポジトリのルート。
        tested_commit_sha: frontmatter と short SHA に書く実施時点 T。
        onboarding_blob_sha: frontmatter と本文に書く onboarding blob OID。
        gate_kind: frontmatter とファイル名のゲート種別。
        release_version: release の場合の版。
        result: frontmatter の result 値。
        evidence_path: 置き場所を直接指定する相対パス。省略時は正規直下名。
        attempt_seq: frontmatter とファイル名に書く 1 以上の連番。
        timestamp: ファイル名先頭に書くハイフン付き UTC 時刻。
        attempt_id_value: frontmatter へ直接書く attempt_id。省略時は正規形。
        extra_lines: frontmatter へ加えるテスト用の追加行。
        body: frontmatter の後へ置く本文。省略時は⑩を満たす本文を使う。

    Returns:
        ``(candidate_sha, evidence_path)`` の組。
    """
    filename = evidence_filename(
        gate_kind,
        release_version,
        tested_commit_sha,
        attempt_seq=attempt_seq,
        timestamp=timestamp,
    )
    relative_path = evidence_path or f"docs/ops/nfr021-acceptance/{filename}"
    write_invalidation_file(
        root,
        relative_path,
        evidence_text(
            gate_kind=gate_kind,
            release_version=release_version,
            tested_commit_sha=tested_commit_sha,
            onboarding_blob_sha=onboarding_blob_sha,
            result=result,
            attempt_seq=attempt_seq,
            attempt_id_value=attempt_id_value,
            extra_lines=extra_lines,
            body=(
                body
                if body is not None
                else complete_evidence_body(
                    tested_commit_sha,
                    onboarding_blob_sha,
                    gate_kind,
                )
            ),
        ),
    )
    commit_invalidation_changes(root, "docs: add evidence")
    return invalidation_head(root), relative_path


def commit_closed_attempt(
    root: Path,
    tested_commit_sha: str,
    onboarding_blob_sha: str,
    *,
    gate_kind: str = "phase4",
    release_version: str | None = None,
    result: str = "passed",
    attempt_seq: int = 1,
    timestamp: str = RECORD_TIMESTAMP,
    attempt_id_value: str | None = None,
    body: str | None = None,
) -> tuple[str, str]:
    """予約と結果証跡が 1 対 1 で対応する閉塞済み試行を追加する。

    Args:
        root: 一時 Git リポジトリのルート。
        tested_commit_sha: 結果証跡に書く実施時点 T。
        onboarding_blob_sha: 結果証跡に書く onboarding blob OID。
        gate_kind: phase4 または release。
        release_version: release の場合の版。
        result: 結果証跡に書く passed または failed。
        attempt_seq: 予約・結果で共通に使う連番。
        timestamp: 予約・結果ファイル名に共通に使う UTC 時刻。
        attempt_id_value: 両レコードに共通に書く attempt_id。省略時は正規形。
        body: 結果証跡の frontmatter 後に置く本文。省略時は完全な本文を使う。

    Returns:
        結果証跡を追加した後の ``(candidate_sha, evidence_path)``。
    """
    gate_key = "phase4" if gate_kind == "phase4" else f"release-{release_version}"
    commit_reservation(
        root,
        gate_key=gate_key,
        attempt_seq=attempt_seq,
        timestamp=timestamp,
        attempt_id_value=attempt_id_value,
    )
    return commit_evidence(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        gate_kind=gate_kind,
        release_version=release_version,
        result=result,
        attempt_seq=attempt_seq,
        timestamp=timestamp,
        attempt_id_value=attempt_id_value,
        body=body,
    )


def make_valid_evidence_repository(
    tmp_path: Path,
    *,
    onboarding_status: str = "approved",
    gate_kind: str = "phase4",
    release_version: str | None = None,
    result: str = "passed",
    body: str | None = None,
) -> tuple[Path, str, str, str, str]:
    """①〜⑩を満たす候補 C と実施時点 T を持つ一時リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        onboarding_status: T 時点の onboarding status。
        gate_kind: 結果証跡に書くゲート種別。
        release_version: release の場合の証跡版。
        result: 結果証跡に書く result。
        body: 結果証跡の frontmatter 後に置く本文。省略時は完全な本文を使う。

    Returns:
        ``(root, tested_sha, candidate_sha, evidence_path, onboarding_blob_sha)``。
    """
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(
        root,
        status=onboarding_status,
    )
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        gate_kind=gate_kind,
        release_version=release_version,
        result=result,
        body=body,
    )
    return root, tested_commit_sha, candidate_sha, evidence_path, onboarding_blob_sha


def make_valid_evidence_repository_with_acceptance_items(
    tmp_path: Path,
    acceptance_items: tuple[tuple[str, str], ...],
    *,
    gate_kind: str = "phase4",
    release_version: str | None = None,
) -> tuple[Path, str, str, str, str]:
    """合格項目だけを差し替えた、それ以外は適合する証跡リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        acceptance_items: 証跡本文へ書く ``(#, 合格項目)`` の対。
        gate_kind: 結果証跡に書くゲート種別。
        release_version: release の場合の結果証跡版。

    Returns:
        ``(root, tested_sha, candidate_sha, evidence_path, onboarding_blob_sha)``。
    """
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    body = complete_evidence_body(
        tested_commit_sha,
        onboarding_blob_sha,
        gate_kind,
        acceptance_items=acceptance_items,
    )
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        gate_kind=gate_kind,
        release_version=release_version,
        body=body,
    )
    return root, tested_commit_sha, candidate_sha, evidence_path, onboarding_blob_sha


def named_evidence_arguments(
    candidate_sha: str,
    evidence_path: str,
    *,
    gate_kind: str = "phase4",
    release_version: str | None = None,
) -> list[str]:
    """名指し証跡を検証する CLI 引数列を作る。

    Args:
        candidate_sha: 検証対象として固定した候補 commit OID。
        evidence_path: 候補ツリーにある結果証跡の相対パス。
        gate_kind: 要求するゲート種別。
        release_version: release の場合に要求する版。

    Returns:
        --root を除く検証器 CLI 引数列。
    """
    arguments = [
        "--gate-kind",
        gate_kind,
        "--candidate-sha",
        candidate_sha,
        "--evidence-path",
        evidence_path,
    ]
    if release_version is not None:
        arguments.extend(["--release-version", release_version])
    return arguments


@pytest.mark.parametrize("kind", ("head", "branch", "tag", "short", "uppercase"))
def test_rejects_mutable_or_noncanonical_candidate_sha(
    tmp_path: Path,
    kind: str,
) -> None:
    """HEAD・参照名・短縮形・大文字を候補 SHA として fail-closed にする。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    git_for_invalidation(root, "tag", "candidate-tag", candidate_sha)
    candidate_values = {
        "head": "HEAD",
        "branch": "develop",
        "tag": "candidate-tag",
        "short": candidate_sha[:12],
        "uppercase": candidate_sha.upper(),
    }

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_values[kind], evidence_path),
    )

    assert result.returncode == 1
    assert "candidate_sha が完全な小文字 16 進 40 桁ではない" in result.stderr
    assert result.stderr.startswith("verify_nfr021_evidence:")


def test_rejects_annotated_tag_object_as_candidate_sha(tmp_path: Path) -> None:
    """40 桁の注釈付きタグ OID を commit OID として受理しない。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    git_for_invalidation(
        root,
        "tag",
        "-a",
        "candidate-tag",
        "-m",
        "annotated candidate",
        candidate_sha,
    )
    tag_object_sha = git_for_invalidation(root, "rev-parse", "candidate-tag").stdout.strip()

    result = run_verifier(
        root,
        *named_evidence_arguments(tag_object_sha, evidence_path),
    )

    assert git_for_invalidation(root, "cat-file", "-t", tag_object_sha).stdout.strip() == "tag"
    assert (
        git_for_invalidation(root, "rev-parse", "candidate-tag^{commit}").stdout.strip()
        == candidate_sha
    )
    assert result.returncode == 1
    assert "candidate_sha が commit オブジェクトではない" in result.stderr


def test_rejects_annotated_tag_object_as_tested_commit_sha(tmp_path: Path) -> None:
    """結果証跡内の tested_commit_sha にタグ OID を入れる経路を閉じる。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    git_for_invalidation(
        root,
        "tag",
        "-a",
        "tested-tag",
        "-m",
        "annotated tested",
        tested_commit_sha,
    )
    tag_object_sha = git_for_invalidation(root, "rev-parse", "tested-tag").stdout.strip()
    candidate_sha, evidence_path = commit_evidence(
        root,
        tag_object_sha,
        onboarding_blob_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "tested_commit_sha が commit オブジェクトではない" in result.stderr


def test_rejects_commit_oid_as_onboarding_blob_sha(tmp_path: Path) -> None:
    """onboarding_blob_sha に commit OID を入れる型すり替えを拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, _ = commit_onboarding(root)
    candidate_sha, evidence_path = commit_evidence(
        root,
        tested_commit_sha,
        tested_commit_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "onboarding_blob_sha が blob オブジェクトではない" in result.stderr


def test_unresolvable_evidence_oid_is_indeterminate(tmp_path: Path) -> None:
    """字句だけ正しいが未解決の証跡 OID を GuardError として fail-closed にする。"""
    root = init_invalidation_repository(tmp_path)
    _, onboarding_blob_sha = commit_onboarding(root)
    unknown_oid = "0" * 40
    candidate_sha, evidence_path = commit_evidence(
        root,
        unknown_oid,
        onboarding_blob_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert result.stderr.startswith("verify_nfr021_evidence:")
    assert "tested_commit_sha の Git オブジェクトを解決できない" in result.stderr


def test_rejects_release_version_for_phase4_argument(tmp_path: Path) -> None:
    """phase4 に --release-version が渡された時点で入力エラーにする。"""
    root = init_invalidation_repository(tmp_path)

    result = run_verifier(
        root,
        "--gate-kind",
        "phase4",
        "--candidate-sha",
        COMMIT_SHA,
        "--evidence-path",
        "docs/ops/nfr021-acceptance/evidence.md",
        "--release-version",
        "v1.2.3",
    )

    assert result.returncode == 1
    assert "phase4 では --release-version を指定できない" in result.stderr


def test_requires_release_version_for_release_argument(tmp_path: Path) -> None:
    """release で --release-version を省略した時点で入力エラーにする。"""
    root = init_invalidation_repository(tmp_path)

    result = run_verifier(
        root,
        "--gate-kind",
        "release",
        "--candidate-sha",
        COMMIT_SHA,
        "--evidence-path",
        "docs/ops/nfr021-acceptance/evidence.md",
    )

    assert result.returncode == 1
    assert "release では --release-version が必須である" in result.stderr


@pytest.mark.parametrize(
    ("gate_kind", "release_version", "expected_reason"),
    [
        ("unknown", None, "コマンドライン引数が不正"),
        ("release", "invalid", "--release-version が vX.Y.Z 形式ではない"),
    ],
)
def test_rejects_invalid_gate_kind_or_release_version_argument(
    tmp_path: Path,
    gate_kind: str,
    release_version: str | None,
    expected_reason: str,
) -> None:
    """閉じたゲート種別と release 版の字句規則に適合しない入力を拒否する。"""
    root = init_invalidation_repository(tmp_path)
    arguments = [
        "--gate-kind",
        gate_kind,
        "--candidate-sha",
        COMMIT_SHA,
        "--evidence-path",
        "docs/ops/nfr021-acceptance/evidence.md",
    ]
    if release_version is not None:
        arguments.extend(["--release-version", release_version])

    result = run_verifier(root, *arguments)

    assert result.returncode == 1
    assert expected_reason in result.stderr


def test_requires_evidence_path_argument(tmp_path: Path) -> None:
    """evidence_path を省略した CLI 呼び出しを入力エラーにする。"""
    root = init_invalidation_repository(tmp_path)

    result = run_verifier(
        root,
        "--gate-kind",
        "phase4",
        "--candidate-sha",
        COMMIT_SHA,
    )

    assert result.returncode == 1
    assert result.stderr.startswith("verify_nfr021_evidence:")
    assert "コマンドライン引数が不正" in result.stderr


@pytest.mark.parametrize("kind", ("outside", "subdirectory", "uncommitted"))
def test_rejects_evidence_path_outside_candidate_tree(
    tmp_path: Path,
    kind: str,
) -> None:
    """候補ツリー外・サブディレクトリ・未コミットの証跡を受理しない。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    if kind == "outside":
        target_path = "docs/worklog/evidence.md"
        expected_reason = "evidence_path が docs/ops/nfr021-acceptance/直下"
    elif kind == "subdirectory":
        target_path = f"docs/ops/nfr021-acceptance/nested/{Path(evidence_path).name}"
        expected_reason = "evidence_path が docs/ops/nfr021-acceptance/直下"
    else:
        target_path = "docs/ops/nfr021-acceptance/uncommitted.md"
        write_invalidation_file(root, target_path, "uncommitted\n")
        expected_reason = "candidate_sha のツリーに収録されていない"

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, target_path),
    )

    assert result.returncode == 1
    assert expected_reason in result.stderr


def test_rejects_mismatched_requested_gate_kind(tmp_path: Path) -> None:
    """合格条件①として証跡の gate_kind と要求ゲート種別を突合する。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)

    result = run_verifier(
        root,
        *named_evidence_arguments(
            candidate_sha,
            evidence_path,
            gate_kind="release",
            release_version="v1.2.3",
        ),
    )

    assert result.returncode == 1
    assert "gate_kind が要求されたゲート種別と一致しない" in result.stderr


def test_rejects_failed_result_for_named_evidence(tmp_path: Path) -> None:
    """合格条件②として result: failed の名指し証跡を拒否する。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(
        tmp_path,
        result="failed",
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "result が passed ではない" in result.stderr


def test_rejects_tested_commit_that_is_not_candidate_ancestor(tmp_path: Path) -> None:
    """合格条件③として祖先でない実施時点 T を拒否する。"""
    root = init_invalidation_repository(tmp_path)
    git_for_invalidation(root, "checkout", "-q", "-b", "feature/tested")
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    git_for_invalidation(root, "checkout", "-q", "develop")
    candidate_sha, evidence_path = commit_evidence(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "tested_commit_sha が candidate_sha の祖先ではない" in result.stderr


def test_rejects_mismatched_onboarding_blob_oid(tmp_path: Path) -> None:
    """合格条件④として T 時点の onboarding blob と異なる blob を拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(
        root,
        extra_files=(("docs/development/other.md", "other blob\n"),),
    )
    other_blob_sha = git_for_invalidation(
        root,
        "rev-parse",
        f"{tested_commit_sha}:docs/development/other.md",
    ).stdout.strip()
    candidate_sha, evidence_path = commit_evidence(
        root,
        tested_commit_sha,
        other_blob_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert onboarding_blob_sha != other_blob_sha
    assert result.returncode == 1
    assert "onboarding.md の blob と一致しない" in result.stderr


def test_rejects_draft_onboarding_blob(tmp_path: Path) -> None:
    """合格条件④として status: draft の onboarding blob を拒否する。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(
        tmp_path,
        onboarding_status="draft",
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "onboarding.md の status が approved ではない" in result.stderr


def test_rejects_draft_onboarding_blob_despite_blob_replacement(
    tmp_path: Path,
) -> None:
    """blob replacement があっても候補ツリーの draft onboarding を受理しない。"""
    root, _, candidate_sha, evidence_path, onboarding_blob_sha = (
        make_valid_evidence_repository(tmp_path, onboarding_status="draft")
    )
    approved_contents = "\n".join(
        ["---", "status: approved", "---", "", "# onboarding", ""]
    )
    replacement_path = "docs/development/approved-replacement.md"
    write_invalidation_file(root, replacement_path, approved_contents)
    approved_blob_sha = git_for_invalidation(
        root,
        "hash-object",
        "-w",
        replacement_path,
    ).stdout.strip()
    git_for_invalidation(root, "replace", onboarding_blob_sha, approved_blob_sha)

    assert git_for_invalidation(
        root,
        "cat-file",
        "-p",
        onboarding_blob_sha,
    ).stdout == approved_contents

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "onboarding.md の status が approved ではない" in result.stderr


def test_ignores_commit_replacement_for_candidate_tree_and_ancestry(
    tmp_path: Path,
) -> None:
    """commit replacement が候補ツリー読取と祖先判定を差し替えない。"""
    root = init_invalidation_repository(tmp_path)
    initial_sha = invalidation_head(root)
    tested_commit_sha, _ = commit_onboarding(root)
    original_path = "candidate-only.txt"
    write_invalidation_file(root, original_path, "candidate tree\n")
    commit_invalidation_changes(root, "test: candidate tree")
    candidate_sha = invalidation_head(root)

    git_for_invalidation(root, "checkout", "-q", "-b", "replacement", initial_sha)
    replacement_path = "replacement-only.txt"
    write_invalidation_file(root, replacement_path, "replacement tree\n")
    commit_invalidation_changes(root, "test: replacement tree")
    replacement_sha = invalidation_head(root)
    git_for_invalidation(root, "checkout", "-q", "develop")
    git_for_invalidation(root, "replace", candidate_sha, replacement_sha)

    assert not git_for_invalidation(
        root,
        "ls-tree",
        "--name-only",
        candidate_sha,
        "--",
        original_path,
    ).stdout
    assert git_for_invalidation(
        root,
        "ls-tree",
        "--name-only",
        candidate_sha,
        "--",
        replacement_path,
    ).stdout.strip() == replacement_path
    assert verify.git_tree_object_oid(root, candidate_sha, original_path) is not None
    assert verify.git_tree_object_oid(root, candidate_sha, replacement_path) is None
    assert verify.is_ancestor(root, tested_commit_sha, candidate_sha)


def test_rejects_release_version_mismatch(tmp_path: Path) -> None:
    """合格条件⑤として release の要求版と証跡版を一致させる。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(
        tmp_path,
        gate_kind="release",
        release_version="v1.2.3",
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(
            candidate_sha,
            evidence_path,
            gate_kind="release",
            release_version="v1.2.4",
        ),
    )

    assert result.returncode == 1
    assert "release_version が要求された版と一致しない" in result.stderr


def test_rejects_phase4_evidence_with_release_version(tmp_path: Path) -> None:
    """phase4 の結果証跡に release_version がある経路を拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    candidate_sha, evidence_path = commit_evidence(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        release_version="v1.2.3",
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "phase4 の結果証跡に release_version がある" in result.stderr


def test_phase4_release_version_gate_condition_is_independent() -> None:
    """合格条件⑤の phase4 側禁止をゲート条件としても検出する。"""
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(release_version="v1.2.3"),
    )

    reasons = verify.validate_gate_conditions(record, "phase4", None)

    assert reasons == (verify.REASON_PHASE4_RELEASE_VERSION,)


def test_rejects_invalidating_change_between_tested_and_candidate(tmp_path: Path) -> None:
    """合格条件⑥として T→C の失効対象変更を検出する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    write_invalidation_file(root, "backend/changed.py", "changed\n")
    commit_invalidation_changes(root, "feat: change backend")
    candidate_sha, evidence_path = commit_evidence(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "失効対象の変更がある: backend/changed.py (/backend/**)" in result.stderr


def test_accepts_allowlisted_evidence_change_only(tmp_path: Path) -> None:
    """証跡の allowlist 変更だけなら合格条件⑥を満たす。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 0, result.stderr


def test_accepts_named_evidence_that_satisfies_conditions_one_to_ten(
    tmp_path: Path,
) -> None:
    """①〜⑩をすべて満たす名指し結果証跡が exit 0 になる。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_real_repository_onboarding_draft_is_not_approved() -> None:
    """実リポジトリの現 onboarding blob が draft で④を満たさないことを確認する。"""
    candidate_sha = git_for_invalidation(REPO, "rev-parse", "HEAD").stdout.strip()
    onboarding_blob_sha = git_for_invalidation(
        REPO,
        "rev-parse",
        f"{candidate_sha}:docs/development/onboarding.md",
    ).stdout.strip()

    reasons = verify.validate_onboarding_blob(
        REPO,
        candidate_sha,
        onboarding_blob_sha,
    )

    assert verify.REASON_ONBOARDING_STATUS in reasons


def test_accepts_single_closed_attempt_and_excludes_canonical_documents(
    tmp_path: Path,
) -> None:
    """予約と結果が 1 対 1 の 1 試行と正本 4 件を正しく扱う。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )
    tree_names = {
        path.name for path in verify.candidate_acceptance_tree_paths(root, candidate_sha)
    }

    assert set(CANONICAL_ACCEPTANCE_FILENAMES) <= tree_names
    assert result.returncode == 0, result.stderr


def test_accepts_failed_closed_attempt_before_newest_passed_attempt(
    tmp_path: Path,
) -> None:
    """失敗済み試行が残っても、より大きい passed 試行なら合格する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        result="failed",
        attempt_seq=1,
    )
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 0, result.stderr


def test_allows_gap_below_the_unique_maximum_attempt_sequence(tmp_path: Path) -> None:
    """下位番号の欠番だけでは⑦⑧⑨の不合格理由にしない。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=3,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 0, result.stderr


def test_allows_duplicate_sequence_below_the_unique_maximum(tmp_path: Path) -> None:
    """下位番号だけの重複では⑦⑧⑨の不合格理由にしない。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )
    commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
        timestamp="2026-08-19T101501Z",
        attempt_id_value=attempt_id("phase4", 2, "20260819T101501Z"),
    )
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=3,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 0, result.stderr


def test_accepts_two_sequences_with_the_same_gate_tested_commit_and_second(
    tmp_path: Path,
) -> None:
    """同一ゲート・同一 T・同秒で seq だけ違う試行が共存できる。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=1,
    )
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 0, result.stderr


def test_limits_attempt_enumeration_to_the_named_release_gate_key(
    tmp_path: Path,
) -> None:
    """別 release 版の試行を同一ゲートキーの判定対象へ混入させない。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        gate_kind="release",
        release_version="v1.0.0",
    )
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        gate_kind="release",
        release_version="v1.1.0",
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(
            candidate_sha,
            evidence_path,
            gate_kind="release",
            release_version="v1.1.0",
        ),
    )

    assert result.returncode == 0, result.stderr


def test_rejects_named_evidence_when_a_later_attempt_exists(tmp_path: Path) -> None:
    """合格条件⑦として、より大きい連番の試行があれば古い証跡を拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    _, old_evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=1,
    )
    candidate_sha, _ = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, old_evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_NAMED_ATTEMPT_NOT_MAXIMUM in result.stderr


def test_rejects_nonunique_maximum_attempt_sequence(tmp_path: Path) -> None:
    """合格条件⑦として、最大連番を持つ別試行が 2 件なら拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    _, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )
    candidate_sha, _ = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
        timestamp="2026-08-19T101501Z",
        attempt_id_value=attempt_id("phase4", 2, "20260819T101501Z"),
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_ATTEMPT_MAXIMUM_NOT_UNIQUE in result.stderr


def test_rejects_unclosed_reservation(tmp_path: Path) -> None:
    """合格条件⑧として、未閉塞の予約が 1 件でもあれば拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    _, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )
    commit_reservation(root, attempt_seq=1, timestamp="2026-08-19T101501Z")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_RESERVATION_UNCLOSED.split(":")[0] in result.stderr


def test_rejects_invalid_utf8_in_candidate_reservation_blob(tmp_path: Path) -> None:
    """候補ツリーの予約 blob が UTF-8 でなければ検証器を fail-closed にする。"""
    root, _, _, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    invalid_path = f"docs/ops/nfr021-acceptance/{reservation_filename('phase4')}"
    write_invalidation_bytes(
        root,
        invalid_path,
        (root / invalid_path).read_bytes() + b"\xff",
    )
    commit_invalidation_changes(root, "docs: add invalid utf8 reservation")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert invalid_path in result.stderr
    assert "UTF-8" in result.stderr


def test_rejects_frontmatter_gate_key_hidden_by_a_different_filename_gate(
    tmp_path: Path,
) -> None:
    """ファイル名が release でも frontmatter が phase4 の未閉塞予約を見逃さない。"""
    root, _, _, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    mismatched_path = (
        "docs/ops/nfr021-acceptance/"
        "2026-08-19T101501Z-release-v1.2.3-seq001-reservation.md"
    )
    write_invalidation_file(
        root,
        mismatched_path,
        reservation_text(gate_key="phase4", attempt_seq=1),
    )
    commit_invalidation_changes(root, "docs: add mismatched reservation gate")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert mismatched_path in result.stderr
    assert verify.REASON_FILENAME_GATE_KEY in result.stderr


def test_rejects_named_evidence_without_a_reservation(tmp_path: Path) -> None:
    """合格条件⑨として、名指し結果証跡の孤児を拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    candidate_sha, evidence_path = commit_evidence(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_NAMED_RESERVATION_COUNT in result.stderr


def test_rejects_two_reservations_for_the_named_attempt(tmp_path: Path) -> None:
    """合格条件⑨として、名指し結果証跡に対応する予約が 2 件なら拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    duplicate_attempt_id = attempt_id("phase4", 1)
    commit_reservation(root, attempt_id_value=duplicate_attempt_id)
    commit_reservation(
        root,
        timestamp="2026-08-19T101501Z",
        attempt_id_value=duplicate_attempt_id,
    )
    candidate_sha, evidence_path = commit_evidence(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_id_value=duplicate_attempt_id,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_NAMED_RESERVATION_COUNT in result.stderr


def test_rejects_an_orphan_evidence_for_another_attempt(tmp_path: Path) -> None:
    """合格条件⑨として、別試行の孤児結果証跡も拒否する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    _, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )
    candidate_sha, orphan_path = commit_evidence(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=1,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert orphan_path in result.stderr
    assert verify.REASON_ORPHAN_EVIDENCE.split(":")[0] in result.stderr


@pytest.mark.parametrize(
    ("relative_path", "reason"),
    [
        (
            "docs/ops/nfr021-acceptance/unexpected.yaml",
            verify.REASON_INVALID_FILENAME,
        ),
        (
            "docs/ops/nfr021-acceptance/unexpected",
            verify.REASON_INVALID_FILENAME,
        ),
        (
            "docs/ops/nfr021-acceptance/nested/unexpected.md",
            verify.REASON_NOT_DIRECT_CHILD,
        ),
    ],
)
def test_rejects_invalid_tree_item_during_attempt_enumeration(
    tmp_path: Path,
    relative_path: str,
    reason: str,
) -> None:
    """候補ツリー内の非正規名・サブディレクトリ項目を fail-closed にする。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    _, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
    )
    write_invalidation_file(root, relative_path, "unexpected\n")
    commit_invalidation_changes(root, "docs: add invalid acceptance item")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert f"{relative_path}: {reason}" in result.stderr


def test_rejects_attempt_sequence_contract_mismatch(tmp_path: Path) -> None:
    """同一 attempt_id の予約と結果で attempt_seq が違えば fail-closed にする。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    reservation_attempt_id = attempt_id("phase4", 2)
    commit_reservation(root, attempt_seq=1, attempt_id_value=reservation_attempt_id)
    candidate_sha, evidence_path = commit_evidence(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
        attempt_id_value=reservation_attempt_id,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_CONTRACT_SEQUENCE in result.stderr


def test_accepts_complete_phase4_evidence_body(tmp_path: Path) -> None:
    """11 欄と phase4 の合格項目 5 行が埋まった名指し証跡を受理する。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert git_for_invalidation(
        root,
        "ls-tree",
        candidate_sha,
        "--",
        evidence_path,
    ).stdout.startswith("100644 blob ")
    assert result.returncode == 0, result.stderr


def test_accepts_complete_release_evidence_body(tmp_path: Path) -> None:
    """release の合格項目 8 行がすべて埋まった名指し証跡を受理する。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(
        tmp_path,
        gate_kind="release",
        release_version="v1.2.3",
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(
            candidate_sha,
            evidence_path,
            gate_kind="release",
            release_version="v1.2.3",
        ),
    )

    assert result.returncode == 0, result.stderr


def test_rejects_generic_acceptance_item_labels(tmp_path: Path) -> None:
    """項目 1〜の汎用ラベルでは template 由来の合格項目契約を満たさない。"""
    generic_items = tuple(
        (number, f"項目 {number}")
        for number, _ in template_acceptance_items("phase4")
    )
    root, _, candidate_sha, evidence_path, _ = (
        make_valid_evidence_repository_with_acceptance_items(
            tmp_path,
            generic_items,
        )
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_ACCEPTANCE_ITEM_MISMATCH.format(
        gate_kind="phase4"
    ) in result.stderr


def test_rejects_acceptance_item_with_a_different_name(tmp_path: Path) -> None:
    """合格項目名が 1 件でもテンプレートと違えば本文完全性で拒否する。"""
    items = list(template_acceptance_items("phase4"))
    number, _ = items[2]
    items[2] = (number, "frontend の別テスト")
    root, _, candidate_sha, evidence_path, _ = (
        make_valid_evidence_repository_with_acceptance_items(
            tmp_path,
            tuple(items),
        )
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_ACCEPTANCE_ITEM_MISMATCH.format(
        gate_kind="phase4"
    ) in result.stderr


def test_rejects_reordered_acceptance_items(tmp_path: Path) -> None:
    """合格項目の番号と名前が同じでもテンプレート順でなければ拒否する。"""
    root, _, candidate_sha, evidence_path, _ = (
        make_valid_evidence_repository_with_acceptance_items(
            tmp_path,
            tuple(reversed(template_acceptance_items("phase4"))),
        )
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_ACCEPTANCE_ITEM_MISMATCH.format(
        gate_kind="phase4"
    ) in result.stderr


def test_rejects_phase4_evidence_with_too_many_acceptance_items(
    tmp_path: Path,
) -> None:
    """テンプレートより多い合格項目も行数契約違反として拒否する。"""
    items = (*template_acceptance_items("phase4"), ("6", "追加した項目"))
    root, _, candidate_sha, evidence_path, _ = (
        make_valid_evidence_repository_with_acceptance_items(
            tmp_path,
            items,
        )
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "合格項目表の行数が phase4 テンプレート" in result.stderr


def test_rejects_release_acceptance_item_with_a_different_name(
    tmp_path: Path,
) -> None:
    """release の 8 項目もテンプレート由来の番号と名前を照合する。"""
    items = list(template_acceptance_items("release"))
    number, _ = items[-1]
    items[-1] = (number, "NFR-018(b) の別検査")
    root, _, candidate_sha, evidence_path, _ = (
        make_valid_evidence_repository_with_acceptance_items(
            tmp_path,
            tuple(items),
            gate_kind="release",
            release_version="v1.2.3",
        )
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(
            candidate_sha,
            evidence_path,
            gate_kind="release",
            release_version="v1.2.3",
        ),
    )

    assert result.returncode == 1
    assert verify.REASON_ACCEPTANCE_ITEM_MISMATCH.format(
        gate_kind="release"
    ) in result.stderr


def test_rejects_evidence_when_candidate_tree_lacks_acceptance_template(
    tmp_path: Path,
) -> None:
    """候補ツリーにゲート別テンプレートが無ければ本文完全性を fail-closed にする。"""
    root, _, _, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    template_path = "docs/ops/nfr021-acceptance/evidence-phase4-template.md"
    git_for_invalidation(root, "rm", template_path)
    commit_invalidation_changes(root, "docs: remove phase4 evidence template")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_EVIDENCE_TEMPLATE_MISSING.split(":")[0] in result.stderr


def test_rejects_symlink_onboarding_from_candidate_tree(tmp_path: Path) -> None:
    """候補ツリーの onboarding.md が symlink なら blob 内容が正しくても中断する。"""
    root = init_invalidation_repository(tmp_path)
    onboarding_contents = "\n".join(
        ["---", "status: approved", "---", "", "# onboarding", ""]
    )
    write_invalidation_symlink(
        root,
        "docs/development/onboarding.md",
        onboarding_contents,
    )
    commit_invalidation_changes(root, "test: add symlink onboarding")
    tested_commit_sha = invalidation_head(root)
    onboarding_blob_sha = git_for_invalidation(
        root,
        "rev-parse",
        f"{tested_commit_sha}:docs/development/onboarding.md",
    ).stdout.strip()
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert "docs/development/onboarding.md が通常ファイルではない: mode 120000" in result.stderr


def test_allows_executable_regular_evidence_and_template_files(tmp_path: Path) -> None:
    """mode 100755 の通常 blob を証跡とテンプレートとして引き続き受理する。"""
    root, _, _, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    template_path = "docs/ops/nfr021-acceptance/evidence-phase4-template.md"
    (root / evidence_path).chmod(0o755)
    (root / template_path).chmod(0o755)
    commit_invalidation_changes(root, "test: make evidence and template executable")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 0, result.stderr
    evidence_tree = git_for_invalidation(
        root,
        "ls-tree",
        candidate_sha,
        "--",
        evidence_path,
    )
    template_tree = git_for_invalidation(
        root,
        "ls-tree",
        candidate_sha,
        "--",
        template_path,
    )
    assert evidence_tree.stdout.startswith("100755 blob ")
    assert template_tree.stdout.startswith("100755 blob ")


def test_rejects_symlink_named_evidence_from_candidate_tree(
    tmp_path: Path,
) -> None:
    """名指し証跡が symlink ならリンク先文字列が完全でも中断する。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    evidence_contents = (root / evidence_path).read_text(encoding="utf-8")
    write_invalidation_symlink(root, evidence_path, evidence_contents)
    commit_invalidation_changes(root, "test: replace named evidence with symlink")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert f"{evidence_path} が通常ファイルではない: mode 120000" in result.stderr


def test_rejects_symlink_evidence_template_from_candidate_tree(
    tmp_path: Path,
) -> None:
    """候補ツリーの合格項目テンプレートが symlink なら完全性検査を中断する。"""
    root, _, candidate_sha, evidence_path, _ = make_valid_evidence_repository(tmp_path)
    template_path = "docs/ops/nfr021-acceptance/evidence-phase4-template.md"
    template_contents = (root / template_path).read_text(encoding="utf-8")
    write_invalidation_symlink(root, template_path, template_contents)
    commit_invalidation_changes(root, "test: replace phase4 template with symlink")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert f"{template_path} が通常ファイルではない: mode 120000" in result.stderr


def test_rejects_gitlink_tree_item_as_nonregular_file(tmp_path: Path) -> None:
    """gitlink mode 160000 を通常 blob の代替として受理しない。"""
    root = init_invalidation_repository(tmp_path)
    candidate_sha = invalidation_head(root)
    gitlink_path = "docs/development/onboarding.md"
    git_for_invalidation(
        root,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{candidate_sha},{gitlink_path}",
    )
    git_for_invalidation(root, "commit", "-qm", "test: add gitlink onboarding")
    candidate_sha = invalidation_head(root)

    with pytest.raises(core_guard.GuardError) as error_info:
        verify.git_tree_object_oid(root, candidate_sha, gitlink_path)

    assert str(error_info.value) == verify.REASON_TREE_OBJECT_MODE.format(
        path=gitlink_path,
        mode="160000",
    )


def test_accepts_acceptance_item_table_reference_value(tmp_path: Path) -> None:
    """「下表に記載」を各合格項目の実値として空欄扱いしない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    assert "| 各合格項目の期待値と実測値 | 下表に記載 |" in body
    assert validate_evidence_completeness(tmp_path, record) == ()


def test_accepts_regular_body_values_without_angle_brackets(tmp_path: Path) -> None:
    """山括弧を含まない実値と通常文をプレースホルダとして扱わない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    assert "Windows 11 24H2" in body
    assert "python 3.12.3 / uv 0.8.13" in body
    assert "判定者が内容を確認した" in body
    assert validate_evidence_completeness(tmp_path, record) == ()


def test_rejects_complete_body_hidden_in_html_comment(tmp_path: Path) -> None:
    """HTML コメント内だけの完全な表をレンダリング上の欄として数えない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=f"<!--\n{body}\n-->"),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert verify.REASON_EVIDENCE_TABLE_FORMAT in reasons
    assert verify.REASON_ACCEPTANCE_TABLE_FORMAT in reasons


def test_rejects_evidence_table_hidden_in_html_comment(tmp_path: Path) -> None:
    """証跡表だけをコメントへ隠しても合格項目表では補えない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    evidence_part, acceptance_part = body.split("## 合格項目", maxsplit=1)
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=f"<!--\n{evidence_part}\n-->\n## 合格項目{acceptance_part}"),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert verify.REASON_EVIDENCE_TABLE_FORMAT in reasons
    assert verify.REASON_ACCEPTANCE_TABLE_FORMAT not in reasons


def test_rejects_complete_body_in_unclosed_html_comment(tmp_path: Path) -> None:
    """閉じられていない HTML コメント以降の表を完全性欄として数えない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=f"<!--\n{body}"),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert verify.REASON_EVIDENCE_TABLE_FORMAT in reasons
    assert verify.REASON_ACCEPTANCE_TABLE_FORMAT in reasons


def test_allows_complete_body_with_visible_tables_and_html_comments(
    tmp_path: Path,
) -> None:
    """表の外の複数 HTML コメントは正当な完全な本文を妨げない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    body = body.replace(
        "# 結果証跡\n",
        "# 結果証跡\n<!-- 注記 1 -->本文<!-- 注記 2 -->\n",
        1,
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    assert validate_evidence_completeness(tmp_path, record) == ()


def test_allows_visible_body_with_html_comment_marker_in_inline_code(
    tmp_path: Path,
) -> None:
    """インラインコード内の <!-- を HTML コメント開始として誤認しない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA).replace(
        "# 結果証跡\n",
        f"# 結果証跡\n注記: {CODE_DELIMITER}<!--{CODE_DELIMITER} は文字列である。\n",
        1,
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    assert verify.validate_records((record,)) == ()
    assert validate_evidence_completeness(tmp_path, record) == ()


def test_rejects_complete_body_hidden_after_unclosed_inline_code_marker(
    tmp_path: Path,
) -> None:
    """行内で閉じないバッククォートは次行の HTML コメントを無効化しない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=f"{CODE_DELIMITER}\n<!--\n{body}\n-->"),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert verify.REASON_EVIDENCE_TABLE_FORMAT in reasons
    assert verify.REASON_ACCEPTANCE_TABLE_FORMAT in reasons


def test_allows_visible_body_with_fence_marker_in_inline_code(tmp_path: Path) -> None:
    """インラインコード内の ``` をフェンス開始として誤認しない。"""
    inline_delimiter = CODE_DELIMITER * 4
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA).replace(
        "# 結果証跡\n",
        f"# 結果証跡\n注記: {inline_delimiter} ``` {inline_delimiter} は文字列である。\n",
        1,
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    assert validate_evidence_completeness(tmp_path, record) == ()


@pytest.mark.parametrize(
    "hidden_example",
    [
        "<!--\n| commit SHA | example-only |\n-->\n",
        "```\n| commit SHA | example-only |\n```\n",
        "\n    | commit SHA | example-only |\n\n",
    ],
)
def test_ignores_hidden_code_or_comment_body_field_examples(
    tmp_path: Path,
    hidden_example: str,
) -> None:
    """可視でない commit SHA の表行を二重記録の重複として数えない。"""
    body = f"{hidden_example}{complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)}"
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    assert verify.validate_records((record,)) == ()
    assert validate_evidence_completeness(tmp_path, record) == ()


def test_rejects_tables_hidden_in_indented_code_block(tmp_path: Path) -> None:
    """段落外で 4 スペース字下げされた表をレンダリング上の欄として数えない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    indented_body = "\n".join(
        f"    {line}" if line.startswith("|") else line for line in body.splitlines()
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=indented_body),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert verify.REASON_EVIDENCE_TABLE_FORMAT in reasons
    assert verify.REASON_ACCEPTANCE_TABLE_FORMAT in reasons


@pytest.mark.parametrize("indent", ("\t", " \t", "     "))
def test_rejects_tables_hidden_in_tab_or_wide_indented_code_block(
    tmp_path: Path,
    indent: str,
) -> None:
    """タブ混在または 5 スペースの字下げ表をレンダリング上の欄として数えない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    indented_body = "\n".join(
        f"{indent}{line}" if line.startswith("|") else line
        for line in body.splitlines()
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=indented_body),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert verify.REASON_EVIDENCE_TABLE_FORMAT in reasons
    assert verify.REASON_ACCEPTANCE_TABLE_FORMAT in reasons


def test_allows_trailing_whitespace_in_evidence_table_headings(tmp_path: Path) -> None:
    """証跡表と合格項目表の見出し末尾にある空白・タブを無視する。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    body = body.replace("## 証跡\n", "## 証跡 \t \n", 1).replace(
        "## 合格項目\n",
        "## 合格項目\t \n",
        1,
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    assert validate_evidence_completeness(tmp_path, record) == ()


def test_allows_escaped_pipe_in_visible_evidence_table_value(tmp_path: Path) -> None:
    r"""表セル内の \| を区切りにせず、値の | として完全性検査へ渡す。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA).replace(
        "| 実行コマンドと終了コード | uv run pytest (0) |",
        r"| 実行コマンドと終了コード | uv run pytest \| tee pytest.log (0) |",
        1,
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )
    cells = verify.parse_markdown_table_row(
        r"| 実行コマンドと終了コード | uv run pytest \| tee pytest.log (0) |"
    )

    assert cells == ("実行コマンドと終了コード", "uv run pytest | tee pytest.log (0)")
    assert validate_evidence_completeness(tmp_path, record) == ()


def test_allows_multiple_escaped_pipes_in_visible_evidence_table_value(
    tmp_path: Path,
) -> None:
    r"""複数の \| を含む表セルも 1 つの可視値として復元する。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA).replace(
        "| 実行コマンドと終了コード | uv run pytest (0) |",
        r"| 実行コマンドと終了コード | a \| b \| c (0) |",
        1,
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )
    cells = verify.parse_markdown_table_row(
        r"| 実行コマンドと終了コード | a \| b \| c (0) |"
    )

    assert cells == ("実行コマンドと終了コード", "a | b | c (0)")
    assert validate_evidence_completeness(tmp_path, record) == ()


@pytest.mark.parametrize("fence", ("```", "~~~"))
def test_rejects_complete_body_hidden_in_fenced_code_block(
    tmp_path: Path,
    fence: str,
) -> None:
    """バックティック・チルダ双方のコードフェンス内の表を欄として数えない。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=f"{fence}\n{body}\n{fence}"),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert verify.REASON_EVIDENCE_TABLE_FORMAT in reasons
    assert verify.REASON_ACCEPTANCE_TABLE_FORMAT in reasons


def test_checks_completeness_for_named_evidence_only(tmp_path: Path) -> None:
    """過去の不完全な failed 証跡で名指し passed 証跡を閉塞しない。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        result="failed",
        attempt_seq=1,
        body=evidence_body(tested_commit_sha, onboarding_blob_sha),
    )
    candidate_sha, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        attempt_seq=2,
    )

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 0, result.stderr


def test_rejects_evidence_body_with_a_missing_required_field(tmp_path: Path) -> None:
    """証跡 11 欄のうち 1 欄がなければ本文完全性を拒否する。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA).replace(
        "| 判定者 | 判定者が内容を確認した |\n",
        "",
        1,
    )
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert verify.REASON_EVIDENCE_FIELD_MISSING.split(":")[0] in reasons[0]
    assert "判定者" in reasons[0]


def test_rejects_phase4_evidence_body_with_four_acceptance_items(tmp_path: Path) -> None:
    """phase4 の合格項目が 4 行しかなければ本文完全性を拒否する。"""
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(
            body=complete_evidence_body(
                COMMIT_SHA,
                ONBOARDING_BLOB_SHA,
                acceptance_item_count=4,
            )
        ),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert any("合格項目表の行数が phase4" in reason for reason in reasons)


@pytest.mark.parametrize("table", ("evidence", "acceptance"))
def test_rejects_empty_body_table_value(tmp_path: Path, table: str) -> None:
    """証跡表と合格項目表のいずれの空欄も本文完全性で拒否する。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    if table == "evidence":
        body = body.replace("| Windows 版 | Windows 11 24H2 |", "| Windows 版 |   |", 1)
        expected_reason = "証跡表の Windows 版 の値が空である"
    else:
        first_item_name = template_acceptance_items("phase4")[0][1]
        body = body.replace(
            f"| 1 | {first_item_name} | 期待値 1 | 実測値 1 |",
            f"| 1 | {first_item_name} |   | 実測値 1 |",
            1,
        )
        expected_reason = "合格項目表の 1 行目の 期待値 が空である"
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert expected_reason in reasons


@pytest.mark.parametrize(
    ("table", "placeholder"),
    (
        ("evidence", "<未記入>"),
        ("acceptance", "<TBD>"),
        ("evidence", f"{CODE_DELIMITER}<未記入>{CODE_DELIMITER}"),
        ("acceptance", f"{CODE_DELIMITER}<TBD>{CODE_DELIMITER}"),
    ),
)
def test_rejects_body_table_placeholder(
    tmp_path: Path,
    table: str,
    placeholder: str,
) -> None:
    """バックティックの有無を問わず ``<...>`` を本文完全性で拒否する。"""
    body = complete_evidence_body(COMMIT_SHA, ONBOARDING_BLOB_SHA)
    if table == "evidence":
        body = body.replace("Windows 11 24H2", placeholder, 1)
        expected_reason = "証跡表の Windows 版 の値にプレースホルダが残っている"
    else:
        body = body.replace("実測値 1", placeholder, 1)
        expected_reason = "合格項目表の 1 行目の 実測値 にプレースホルダが残っている"
    record = parse_record(
        "2026-08-19T101500Z-phase4-phase4-seq001-0123456789ab.md",
        evidence_text(body=body),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert expected_reason in reasons


def test_rejects_release_evidence_body_with_five_acceptance_items(
    tmp_path: Path,
) -> None:
    """release の合格項目が phase4 と同じ 5 行だけなら拒否する。"""
    record = parse_record(
        "2026-08-19T101500Z-release-v1.2.3-seq001-0123456789ab.md",
        evidence_text(
            gate_kind="release",
            release_version="v1.2.3",
            body=complete_evidence_body(
                COMMIT_SHA,
                ONBOARDING_BLOB_SHA,
                "release",
                acceptance_item_count=5,
            ),
        ),
    )

    reasons = validate_evidence_completeness(tmp_path, record)

    assert any("合格項目表の行数が release" in reason for reason in reasons)


@pytest.mark.parametrize(
    "template_path",
    (PHASE4_EVIDENCE_TEMPLATE, RELEASE_EVIDENCE_TEMPLATE),
)
def test_evidence_field_constants_match_template_field_names(template_path: Path) -> None:
    """11 欄定数と機械照合用の追加欄を含むテンプレート実物を突き合わせる。"""
    field_names = {
        row[0] for row in template_table_rows(template_path, "証跡")
    }

    assert field_names == set(verify.REQUIRED_EVIDENCE_FIELD_NAMES) | {
        "onboarding blob SHA"
    }


@pytest.mark.parametrize(
    ("template_path", "gate_kind"),
    (
        (PHASE4_EVIDENCE_TEMPLATE, "phase4"),
        (RELEASE_EVIDENCE_TEMPLATE, "release"),
    ),
)
def test_candidate_template_acceptance_items_match_template_rows(
    tmp_path: Path,
    template_path: Path,
    gate_kind: str,
) -> None:
    """候補ツリーから導出した合格項目がテンプレート実物と一致する。"""
    root = init_invalidation_repository(tmp_path)
    expected_items = tuple(
        (row[0], row[1])
        for row in template_table_rows(template_path, "合格項目")
    )

    assert verify.candidate_template_acceptance_items(
        root,
        invalidation_head(root),
        gate_kind,
    ) == expected_items


@pytest.mark.parametrize(
    ("relative_path", "contents"),
    (
        ("artifacts/empty.bin", b""),
        ("artifacts/newline.bin", b"\n"),
        ("artifacts/multibyte.txt", "野球⚾\n".encode("utf-8")),
        ("artifacts/large.bin", b"0123456789abcdef" * 1024),
    ),
    ids=("empty", "newline", "multibyte", "large"),
)
def test_git_blob_oid_matches_git_tree_blob(
    tmp_path: Path,
    relative_path: str,
    contents: bytes,
) -> None:
    """自前計算した blob OID が内容の異なる Git blob と一致する。"""
    root = init_invalidation_repository(tmp_path)
    write_invalidation_bytes(root, relative_path, contents)
    commit_invalidation_changes(root, "test: add blob")
    candidate_sha = invalidation_head(root)

    tree_blob_oid = git_for_invalidation(
        root,
        "rev-parse",
        f"{candidate_sha}:{relative_path}",
    ).stdout.strip()

    assert verify.git_blob_oid(contents) == tree_blob_oid


def test_accepts_matching_self_identity(tmp_path: Path) -> None:
    """検証器と設定の内容が候補ツリーと一致すれば中断しない。"""
    root = init_invalidation_repository(tmp_path)

    verify.validate_self_identity(root, invalidation_head(root))


def test_rejects_verifier_self_identity_mismatch(tmp_path: Path) -> None:
    """実行中の検証器と候補ツリー内の検証器が違えば中断する。"""
    root = init_invalidation_repository(tmp_path)
    write_invalidation_file(
        root,
        verify.VERIFIER_RELATIVE_PATH,
        "# candidate verifier differs\n",
    )
    commit_invalidation_changes(root, "test: alter verifier")

    with pytest.raises(core_guard.GuardError) as error_info:
        verify.validate_self_identity(root, invalidation_head(root))

    assert str(error_info.value) == verify.REASON_SELF_IDENTITY_MISMATCH.format(
        label=verify.SELF_IDENTITY_VERIFIER_LABEL
    )


def test_rejects_invalidation_config_self_identity_mismatch(tmp_path: Path) -> None:
    """実行中の失効パス設定と候補ツリー内の設定が違えば中断する。"""
    root = init_invalidation_repository(tmp_path)
    candidate_sha = invalidation_head(root)
    write_invalidation_file(
        root,
        verify.INVALIDATING_PATHS_CONFIG_PATH.as_posix(),
        "{\"syntax\": \"different\"}\n",
    )

    with pytest.raises(core_guard.GuardError) as error_info:
        verify.validate_self_identity(root, candidate_sha)

    assert str(error_info.value) == verify.REASON_SELF_IDENTITY_MISMATCH.format(
        label=verify.SELF_IDENTITY_CONFIG_LABEL
    )


@pytest.mark.parametrize(
    ("relative_path", "reason"),
    (
        (
            verify.VERIFIER_RELATIVE_PATH,
            verify.REASON_SELF_IDENTITY_TREE_MISSING.format(
                path=verify.VERIFIER_RELATIVE_PATH
            ),
        ),
        (
            verify.INVALIDATING_PATHS_CONFIG_PATH.as_posix(),
            verify.REASON_SELF_IDENTITY_TREE_MISSING.format(
                path=verify.INVALIDATING_PATHS_CONFIG_PATH.as_posix()
            ),
        ),
    ),
)
def test_rejects_self_identity_target_missing_from_candidate_tree(
    tmp_path: Path,
    relative_path: str,
    reason: str,
) -> None:
    """候補ツリーに検証器または設定がなければ自己同一性確認を中断する。"""
    root = init_invalidation_repository(tmp_path)
    (root / relative_path).unlink()
    commit_invalidation_changes(root, "test: remove self identity target")

    with pytest.raises(core_guard.GuardError) as error_info:
        verify.validate_self_identity(root, invalidation_head(root))

    assert str(error_info.value) == reason


def test_interrupts_for_self_identity_before_gate_conditions(tmp_path: Path) -> None:
    """自己同一性の不一致を名指し証跡のゲート条件より先に中断する。"""
    root = init_invalidation_repository(tmp_path)
    tested_commit_sha, onboarding_blob_sha = commit_onboarding(root)
    _, evidence_path = commit_closed_attempt(
        root,
        tested_commit_sha,
        onboarding_blob_sha,
        result="failed",
    )
    write_invalidation_file(
        root,
        verify.VERIFIER_RELATIVE_PATH,
        "# candidate verifier differs\n",
    )
    commit_invalidation_changes(root, "test: alter verifier")
    candidate_sha = invalidation_head(root)

    result = run_verifier(
        root,
        *named_evidence_arguments(candidate_sha, evidence_path),
    )

    assert result.returncode == 1
    assert verify.REASON_SELF_IDENTITY_MISMATCH.format(
        label=verify.SELF_IDENTITY_VERIFIER_LABEL
    ) in result.stderr
    assert verify.REASON_RESULT_NOT_PASSED not in result.stderr
