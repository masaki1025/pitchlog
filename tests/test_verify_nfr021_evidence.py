"""verify_nfr021_evidence.py の命名・スキーマ検査を単体検証する。"""

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
RESERVATION_FILENAME = "2026-08-19T142916Z-phase4-phase4-seq001-reservation.md"
COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_COMMIT_SHA = "fedcba9876543210fedcba9876543210fedcba98"
ONBOARDING_BLOB_SHA = "89abcdef0123456789abcdef0123456789abcdef"
OTHER_ONBOARDING_BLOB_SHA = "76543210fedcba987654321076543210fedcba98"
RECORD_TIMESTAMP = "2026-08-19T101500Z"
ATTEMPT_ID_TIMESTAMP = "20260819T101500Z"
CODE_DELIMITER = chr(96)


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
    return build_frontmatter(
        lines,
        evidence_body(
            body_commit_sha or tested_commit_sha,
            body_onboarding_blob_sha or onboarding_blob_sha,
        ),
    )


def parse_record(filename: str, text: str):
    """テスト用のファイル名と内容を解析済みレコードへ変換する。

    Args:
        filename: 受入証跡ディレクトリ直下からの相対パス。
        text: 解析する証跡内容。

    Returns:
        verify_nfr021_evidence の解析済みレコード。
    """
    return verify.parse_acceptance_record(filename, text)


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

    assert any("phase4 の結果証跡に release_version がある" in violation for violation in violations)


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


def write_invalidation_file(root: Path, relative_path: str, content: str) -> None:
    """一時リポジトリに UTF-8 テキストファイルを書き出す。

    Args:
        root: 一時リポジトリのルート。
        relative_path: root からの相対パス。
        content: 書き込むテキスト。

    Returns:
        戻り値はない。
    """
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def test_unclassified_path_reads_noninvalidating_default_from_settings() -> None:
    """実装側で default を invalidating と決め打ちしない。"""
    classification = verify.classify_invalidation_path(
        "README.md",
        make_invalidation_settings(default="allowlist"),
    )

    assert classification.classification == verify.CLASSIFICATION_DEFAULT
    assert not classification.invalidating


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
