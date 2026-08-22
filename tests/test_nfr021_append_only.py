"""check_nfr021_append_only.py の統合時受入検査を検証する。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "check_nfr021_append_only.py"
CORE_GUARD_SCRIPT = REPO / "scripts" / "core_guard.py"
VERIFIER_SCRIPT = REPO / "scripts" / "verify_nfr021_evidence.py"
ACCEPTANCE_DIRECTORY = REPO / "docs" / "ops" / "nfr021-acceptance"
PHASE4_EVIDENCE_TEMPLATE = ACCEPTANCE_DIRECTORY / "evidence-phase4-template.md"
RELEASE_EVIDENCE_TEMPLATE = ACCEPTANCE_DIRECTORY / "evidence-release-template.md"
COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
ONBOARDING_BLOB_SHA = "89abcdef0123456789abcdef0123456789abcdef"
FILE_TIMESTAMP = "2026-08-20T101500Z"
ATTEMPT_TIMESTAMP = "20260820T101500Z"
OTHER_FILE_TIMESTAMP = "2026-08-20T101501Z"
OTHER_ATTEMPT_TIMESTAMP = "20260820T101501Z"
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
verify_nfr021_evidence = load_module(VERIFIER_SCRIPT, "verify_nfr021_evidence")
append_only = load_module(SCRIPT, "check_nfr021_append_only_under_test")


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """一時リポジトリに Git コマンドを実行する。

    Args:
        cwd: Git コマンドを実行する一時リポジトリのルート。
        *args: ``git`` に渡すサブコマンド以降の引数。

    Returns:
        Git コマンドの実行結果。
    """
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )


def write_text(root: Path, relative_path: str, content: str) -> None:
    """一時リポジトリ内へ UTF-8 テキストファイルを書き出す。

    Args:
        root: 一時リポジトリのルート。
        relative_path: root からの相対パス。
        content: 書き込む本文。
    """
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def commit_all(root: Path, subject: str) -> str:
    """現在の変更をすべてコミットし、その commit OID を返す。

    Args:
        root: テスト用リポジトリのルート。
        subject: コミット件名。

    Returns:
        作成したコミットの完全 OID。
    """
    git(root, "add", "-A")
    git(root, "commit", "-qm", subject)
    return git(root, "rev-parse", "HEAD").stdout.strip()


def init_repository(tmp_path: Path) -> tuple[Path, str]:
    """develop ブランチの最小一時 Git リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。

    Returns:
        一時リポジトリのルートと初期コミット OID の組。
    """
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "develop", str(root)],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")
    write_text(root, "README.md", "# test\n")
    write_text(
        root,
        acceptance_path("evidence-phase4-template.md"),
        PHASE4_EVIDENCE_TEMPLATE.read_text(encoding="utf-8"),
    )
    write_text(
        root,
        acceptance_path("evidence-release-template.md"),
        RELEASE_EVIDENCE_TEMPLATE.read_text(encoding="utf-8"),
    )
    return root, commit_all(root, "chore: base")


def attempt_id(
    gate_key: str = "phase4",
    attempt_seq: int = 1,
    timestamp: str = ATTEMPT_TIMESTAMP,
) -> str:
    """正規形の attempt_id を作る。

    Args:
        gate_key: phase4 または release-vX.Y.Z の合成ゲートキー。
        attempt_seq: 1 以上の試行連番。
        timestamp: ハイフンなし UTC 時刻。

    Returns:
        テスト用の正規形 attempt_id。
    """
    return f"{gate_key}-{attempt_seq:03d}-{timestamp}"


def reservation_filename(
    attempt_seq: int,
    timestamp: str = FILE_TIMESTAMP,
    gate_kind: str = "phase4",
    release_version: str | None = None,
) -> str:
    """予約レコードの正規ファイル名を作る。

    Args:
        attempt_seq: ファイル名へ入れる連番。
        timestamp: ハイフン付き UTC 時刻。
        gate_kind: phase4 または release。
        release_version: release の版。phase4 では ``None``。

    Returns:
        受入証跡ディレクトリ直下で使うファイル名。
    """
    gate_value = "phase4" if gate_kind == "phase4" else release_version
    assert gate_value is not None
    return f"{timestamp}-{gate_kind}-{gate_value}-seq{attempt_seq:03d}-reservation.md"


def evidence_filename(
    attempt_seq: int,
    timestamp: str = FILE_TIMESTAMP,
    gate_kind: str = "phase4",
    release_version: str | None = None,
) -> str:
    """結果証跡の正規ファイル名を作る。

    Args:
        attempt_seq: ファイル名へ入れる連番。
        timestamp: ハイフン付き UTC 時刻。
        gate_kind: phase4 または release。
        release_version: release の版。phase4 では ``None``。

    Returns:
        受入証跡ディレクトリ直下で使うファイル名。
    """
    gate_value = "phase4" if gate_kind == "phase4" else release_version
    assert gate_value is not None
    return (
        f"{timestamp}-{gate_kind}-{gate_value}-seq{attempt_seq:03d}-"
        f"{COMMIT_SHA[:12]}.md"
    )


def acceptance_path(filename: str) -> str:
    """受入証跡ディレクトリ直下のリポジトリ相対パスを作る。

    Args:
        filename: 受入証跡ディレクトリからの相対パス。

    Returns:
        リポジトリルートからの受入証跡パス。
    """
    return f"docs/ops/nfr021-acceptance/{filename}"


def frontmatter(lines: list[str], body: str) -> str:
    """frontmatter 行と本文から証跡レコード内容を作る。

    Args:
        lines: frontmatter 内に置くキー行。
        body: 終端記号の後へ置く本文。

    Returns:
        UTF-8 ファイルへ書ける証跡内容。
    """
    return "\n".join(["---", *lines, "---", body, ""])


def reservation_text(
    attempt_seq: int = 1,
    gate_key: str = "phase4",
    record_id: str | None = None,
    attempt_seq_value: str | None = None,
    omit_operator: bool = False,
) -> str:
    """スキーマ適合する最小の予約レコードを作る。

    Args:
        attempt_seq: attempt_id の既定値に使う試行連番。
        gate_key: frontmatter の合成ゲートキー。
        record_id: frontmatter の attempt_id。省略時は正規形を作る。
        attempt_seq_value: frontmatter 行に直接書く連番。省略時は整数を使う。
        omit_operator: 必須キー欠落の負例にする場合は ``True``。

    Returns:
        予約レコードの本文。
    """
    sequence_value = attempt_seq_value if attempt_seq_value is not None else str(attempt_seq)
    lines = [
        f'gate_key: "{gate_key}"',
        f"attempt_seq: {sequence_value}",
        f'attempt_id: "{record_id or attempt_id(gate_key, attempt_seq)}"',
        'started_at: "2026-08-20T101500Z"',
    ]
    if not omit_operator:
        lines.append('operator: "test"')
    return frontmatter(lines, "# 予約レコード")


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
    table = verify_nfr021_evidence.extract_named_markdown_table(
        template_path.read_text(encoding="utf-8"),
        "合格項目",
    )
    assert table is not None
    return tuple((row[0], row[1]) for row in table.rows)


def complete_evidence_body(
    gate_kind: str = "phase4",
    commit_sha: str = COMMIT_SHA,
    onboarding_blob_sha: str = ONBOARDING_BLOB_SHA,
    *,
    placeholder: str | None = None,
    acceptance_placeholder: str | None = None,
) -> str:
    """⑩を満たす結果証跡本文を作る。

    Args:
        gate_kind: phase4 または release。
        commit_sha: 証跡表の commit SHA。
        onboarding_blob_sha: 証跡表の onboarding blob SHA。
        placeholder: 指定時は証跡表の Windows 版へ残すプレースホルダ。
        acceptance_placeholder: 指定時は合格項目表の 1 行目へ残すプレースホルダ。

    Returns:
        証跡表とゲート別の合格項目表を含む本文。
    """
    evidence_rows = (
        ("日時", "2026-08-20T101500Z"),
        ("commit SHA", f"{CODE_DELIMITER}{commit_sha}{CODE_DELIMITER}"),
        ("Windows 版", placeholder or "Windows 11 24H2"),
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
        ("判定者", "test"),
    )
    evidence_table = [
        "| 項目 | 記録 |",
        "| --- | --- |",
        *(f"| {name} | {value} |" for name, value in evidence_rows),
    ]
    acceptance_rows: list[str] = []
    for number, item_name in template_acceptance_items(gate_kind):
        actual_value = (
            acceptance_placeholder
            if number == "1" and acceptance_placeholder is not None
            else f"実測 {number}"
        )
        acceptance_rows.append(
            f"| {number} | {item_name} | 期待 {number} | {actual_value} |"
        )
    acceptance_table = [
        "| # | 合格項目 | 期待値 | 実測値 |",
        "| --- | --- | --- | --- |",
        *acceptance_rows,
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


def evidence_text(
    attempt_seq: int = 1,
    gate_kind: str = "phase4",
    release_version: str | None = None,
    record_id: str | None = None,
    attempt_seq_value: str | None = None,
    body: str | None = None,
) -> str:
    """スキーマ適合する結果証跡を作る。

    Args:
        attempt_seq: attempt_id の既定値に使う試行連番。
        gate_kind: frontmatter の gate_kind。
        release_version: release の版。phase4 では ``None``。
        record_id: frontmatter の attempt_id。省略時は正規形を作る。
        attempt_seq_value: frontmatter 行に直接書く連番。省略時は整数を使う。
        body: frontmatter 後の本文。省略時は完全な本文を使う。

    Returns:
        結果証跡の本文。
    """
    gate_key = "phase4" if gate_kind == "phase4" else f"release-{release_version}"
    sequence_value = attempt_seq_value if attempt_seq_value is not None else str(attempt_seq)
    lines = [
        f"gate_kind: {gate_kind}",
        f'tested_commit_sha: "{COMMIT_SHA}"',
        f'onboarding_blob_sha: "{ONBOARDING_BLOB_SHA}"',
        "result: passed",
    ]
    if release_version is not None:
        lines.append(f"release_version: {release_version}")
    lines.extend(
        [
            f"attempt_seq: {sequence_value}",
            f'attempt_id: "{record_id or attempt_id(gate_key, attempt_seq)}"',
        ]
    )
    return frontmatter(lines, body or complete_evidence_body(gate_kind))


def write_reservation(
    root: Path,
    attempt_seq: int = 1,
    *,
    timestamp: str = FILE_TIMESTAMP,
    gate_key: str = "phase4",
    record_id: str | None = None,
    content: str | None = None,
) -> str:
    """予約レコードを受入証跡ディレクトリ直下へ書く。

    Args:
        root: 一時リポジトリのルート。
        attempt_seq: 予約の連番。
        timestamp: ファイル名に使う UTC 時刻。
        gate_key: frontmatter とファイル名へ使う合成ゲートキー。
        record_id: frontmatter の attempt_id。
        content: 書く内容。省略時は適合する予約を作る。

    Returns:
        書き込んだリポジトリ相対パス。
    """
    if gate_key == "phase4":
        gate_kind = "phase4"
        release_version = None
    else:
        gate_kind = "release"
        release_version = gate_key.removeprefix("release-")
    path = acceptance_path(
        reservation_filename(
            attempt_seq,
            timestamp,
            gate_kind,
            release_version,
        )
    )
    write_text(
        root,
        path,
        content or reservation_text(attempt_seq, gate_key, record_id=record_id),
    )
    return path


def write_evidence(
    root: Path,
    attempt_seq: int = 1,
    *,
    timestamp: str = FILE_TIMESTAMP,
    record_id: str | None = None,
    content: str | None = None,
) -> str:
    """結果証跡を受入証跡ディレクトリ直下へ書く。

    Args:
        root: 一時リポジトリのルート。
        attempt_seq: 結果証跡の連番。
        timestamp: ファイル名に使う UTC 時刻。
        record_id: frontmatter の attempt_id。
        content: 書く内容。省略時は完全な結果証跡を作る。

    Returns:
        書き込んだリポジトリ相対パス。
    """
    path = acceptance_path(evidence_filename(attempt_seq, timestamp))
    write_text(root, path, content or evidence_text(attempt_seq, record_id=record_id))
    return path


def run_check(
    root: Path,
    base: str,
    head: str,
    *,
    event_name: str | None = None,
    event_data: object | None = None,
) -> subprocess.CompletedProcess[str]:
    """append-only 検査 CLI を一時リポジトリに対して起動する。

    Args:
        root: 検査対象リポジトリのルート。
        base: 比較元 revision。
        head: 比較先 revision。
        event_name: 指定時は GITHUB_EVENT_NAME に設定するイベント名。
        event_data: PR イベント JSON として書く値。指定時だけ GITHUB_EVENT_PATH を設定する。

    Returns:
        標準出力・標準エラーを取得したサブプロセス結果。
    """
    environment = os.environ.copy()
    environment.pop("GITHUB_EVENT_NAME", None)
    environment.pop("GITHUB_EVENT_PATH", None)
    if event_name is not None:
        environment["GITHUB_EVENT_NAME"] = event_name
    if event_data is not None:
        event_path = root / "event.json"
        event_path.write_text(json.dumps(event_data), encoding="utf-8")
        environment["GITHUB_EVENT_PATH"] = str(event_path)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(root),
            "--base",
            base,
            "--head",
            head,
        ],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        env=environment,
    )


def pull_request_event(base: str, head: str, base_ref: str = "develop") -> dict[str, object]:
    """テスト用の最小 pull_request イベント JSON を作る。

    Args:
        base: PR base commit OID。
        head: PR head commit OID。
        base_ref: PR base ブランチ名。

    Returns:
        GitHub event payload として使う辞書。
    """
    return {
        "pull_request": {
            "base": {"ref": base_ref, "sha": base},
            "head": {"sha": head},
        }
    }


def test_allows_no_new_acceptance_records(tmp_path: Path) -> None:
    """新規追加が 0 件なら過去のツリーを再検査せず成功する。"""
    root, base = init_repository(tmp_path)

    result = run_check(root, base, base)

    assert result.returncode == 0
    assert result.stderr == ""


def test_allows_a_normative_new_reservation_without_evidence_completeness(
    tmp_path: Path,
) -> None:
    """予約だけの PR は (a) の証跡完全性を適用せず成功する。"""
    root, base = init_repository(tmp_path)
    write_reservation(root)
    head = commit_all(root, "docs: reserve phase4")

    result = run_check(root, base, head)

    assert result.returncode == 0


def test_allows_evidence_when_matching_reservation_is_in_base(tmp_path: Path) -> None:
    """base の予約を完全な新規結果証跡で閉じる経路を許可する。"""
    root, initial = init_repository(tmp_path)
    write_reservation(root)
    base = commit_all(root, "docs: reserve phase4")
    assert initial != base
    write_evidence(root)
    head = commit_all(root, "docs: close phase4")

    result = run_check(root, base, head)

    assert result.returncode == 0


def test_allows_new_reservation_after_base_reservation_is_closed(tmp_path: Path) -> None:
    """base で閉塞済みの seq001 の後に seq002 を追加できる。"""
    root, _ = init_repository(tmp_path)
    write_reservation(root)
    write_evidence(root)
    base = commit_all(root, "docs: close phase4")
    write_reservation(root, 2)
    head = commit_all(root, "docs: reserve phase4 retry")

    result = run_check(root, base, head)

    assert result.returncode == 0


def test_allows_first_reservation_at_sequence_one(tmp_path: Path) -> None:
    """base に予約がない最初の seq001 予約を許可する。"""
    root, base = init_repository(tmp_path)
    write_reservation(root, 1)
    head = commit_all(root, "docs: first reservation")

    result = run_check(root, base, head)

    assert result.returncode == 0


def test_does_not_recheck_historic_incomplete_evidence(tmp_path: Path) -> None:
    """過去の不完全証跡があっても正しい新規予約を恒久閉塞しない。"""
    root, _ = init_repository(tmp_path)
    write_reservation(root)
    write_evidence(root, content=evidence_text(body="# 過去の不完全な結果"))
    base = commit_all(root, "docs: historic incomplete result")
    write_reservation(root, 2)
    head = commit_all(root, "docs: reserve retry")

    result = run_check(root, base, head)

    assert result.returncode == 0


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (evidence_text(body="# 不完全"), "証跡表の形式"),
        (
            evidence_text(body=complete_evidence_body(placeholder="<未記入>")),
            "プレースホルダ",
        ),
        (
            evidence_text(
                body=complete_evidence_body(acceptance_placeholder="<TBD>")
            ),
            "プレースホルダ",
        ),
    ],
)
def test_rejects_incomplete_new_evidence(
    tmp_path: Path,
    content: str,
    expected: str,
) -> None:
    """新規結果証跡だけには (a) の完全性検査を適用する。"""
    root, _ = init_repository(tmp_path)
    write_reservation(root)
    base = commit_all(root, "docs: reserve phase4")
    write_evidence(root, content=content)
    head = commit_all(root, "docs: add incomplete evidence")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert expected in result.stderr


@pytest.mark.parametrize(
    "relative_path",
    [
        "docs/ops/nfr021-acceptance/record.yaml",
        "docs/ops/nfr021-acceptance/record",
        "docs/ops/nfr021-acceptance/archive/record.md",
    ],
)
def test_rejects_noncanonical_new_tree_items(tmp_path: Path, relative_path: str) -> None:
    """拡張子違い・拡張子なし・サブディレクトリ配下を fail-closed にする。"""
    root, base = init_repository(tmp_path)
    write_text(root, relative_path, "not a record\n")
    head = commit_all(root, "docs: add invalid evidence item")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "閉じた命名文法" in result.stderr or "直下の項目" in result.stderr


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (reservation_text(omit_operator=True), "必須キーがない"),
        (reservation_text(attempt_seq_value='"1"'), "引用符なしの 10 進整数"),
    ],
)
def test_rejects_schema_invalid_new_records(
    tmp_path: Path,
    content: str,
    expected: str,
) -> None:
    """必須キー欠落と文字列 attempt_seq を新規スキーマ違反として拒否する。"""
    root, base = init_repository(tmp_path)
    write_reservation(root, content=content)
    head = commit_all(root, "docs: add invalid reservation")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert expected in result.stderr


def test_rejects_orphan_new_evidence(tmp_path: Path) -> None:
    """統合後ツリーに対応予約がない新規結果証跡を拒否する。"""
    root, base = init_repository(tmp_path)
    write_evidence(root)
    head = commit_all(root, "docs: add orphan evidence")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "対応する予約" in result.stderr


def test_rejects_second_evidence_for_the_same_attempt_id(tmp_path: Path) -> None:
    """同一 attempt_id の結果証跡が 2 件目になることを拒否する。"""
    root, _ = init_repository(tmp_path)
    write_reservation(root)
    base = commit_all(root, "docs: reserve phase4")
    record_id = attempt_id()
    write_evidence(root, 1, record_id=record_id)
    write_evidence(
        root,
        1,
        timestamp=OTHER_FILE_TIMESTAMP,
        record_id=record_id,
    )
    head = commit_all(root, "docs: add duplicate evidences")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "結果証跡が 2 件目" in result.stderr


def test_rejects_second_reservation_for_the_same_gate_and_sequence(tmp_path: Path) -> None:
    """異なる attempt_id でも同じ gate_key と seq の予約重複を拒否する。"""
    root, base = init_repository(tmp_path)
    write_reservation(root, 1, record_id=attempt_id())
    write_reservation(
        root,
        1,
        timestamp=OTHER_FILE_TIMESTAMP,
        record_id=attempt_id(timestamp=OTHER_ATTEMPT_TIMESTAMP),
    )
    head = commit_all(root, "docs: add duplicate reservations")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "gate_key と attempt_seq の予約が一意ではない" in result.stderr


def test_rejects_reservation_and_evidence_added_in_the_same_pr(tmp_path: Path) -> None:
    """(e-1) により同一 PR の予約だけで新規結果証跡を正当化できない。"""
    root, base = init_repository(tmp_path)
    write_reservation(root)
    write_evidence(root)
    head = commit_all(root, "docs: reserve and close in one pr")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "base ツリーにちょうど 1 件ない" in result.stderr


def test_rejects_new_reservation_while_base_has_an_unclosed_reservation(
    tmp_path: Path,
) -> None:
    """(e-2) により base の未閉塞予約がある間の新規予約を拒否する。"""
    root, _ = init_repository(tmp_path)
    write_reservation(root)
    base = commit_all(root, "docs: unclosed reservation")
    write_reservation(root, 2)
    head = commit_all(root, "docs: illegal next reservation")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "未閉塞の予約" in result.stderr


def test_rejects_same_pr_closure_and_next_reservation(tmp_path: Path) -> None:
    """(e-2) は同一 PR の閉塞を base の閉塞として扱わない。"""
    root, _ = init_repository(tmp_path)
    write_reservation(root)
    base = commit_all(root, "docs: unclosed reservation")
    write_evidence(root)
    write_reservation(root, 2)
    head = commit_all(root, "docs: close and reserve in one pr")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "未閉塞の予約" in result.stderr


def test_rejects_reservation_after_base_evidence_with_the_same_attempt_id(
    tmp_path: Path,
) -> None:
    """(e-3) により base の孤児結果へ後から予約を足す逆順を拒否する。"""
    root, _ = init_repository(tmp_path)
    write_evidence(root)
    base = commit_all(root, "docs: historic orphan evidence")
    write_reservation(root)
    head = commit_all(root, "docs: add reservation after evidence")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "結果証跡が base ツリーに既にある" in result.stderr


@pytest.mark.parametrize("new_sequence", [1, 2])
def test_rejects_invalid_first_or_nonincreasing_reservation_sequence(
    tmp_path: Path,
    new_sequence: int,
) -> None:
    """(e-4) の初回 seq001 と base より厳密に大きい採番を強制する。"""
    root, initial = init_repository(tmp_path)
    if new_sequence == 2:
        base = initial
    else:
        write_reservation(root)
        write_evidence(root)
        base = commit_all(root, "docs: closed seq001")
    if new_sequence == 2:
        write_reservation(root, new_sequence)
    else:
        write_reservation(
            root,
            new_sequence,
            timestamp=OTHER_FILE_TIMESTAMP,
            record_id=attempt_id(timestamp=OTHER_ATTEMPT_TIMESTAMP),
        )
    head = commit_all(root, "docs: invalid reservation sequence")

    result = run_check(root, base, head)

    assert result.returncode == 1
    expected = "attempt_seq は 1" if new_sequence == 2 else "厳密に大きくない"
    assert expected in result.stderr


@pytest.mark.parametrize("reservation_count", [2, 3])
def test_rejects_multiple_new_reservations_for_the_same_gate_in_one_pr(
    tmp_path: Path,
    reservation_count: int,
) -> None:
    """(e-5) により閉塞済み base 後でも同一ゲートの複数予約を拒否する。"""
    root, _ = init_repository(tmp_path)
    write_reservation(root, 1)
    write_evidence(root, 1)
    base = commit_all(root, "docs: close phase4 seq001")
    for attempt_seq in range(2, reservation_count + 2):
        write_reservation(root, attempt_seq)
    head = commit_all(root, "docs: reserve multiple phase4 attempts")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "同一 gate_key の新規予約が同一 PR に複数ある: phase4" in result.stderr


def test_allows_one_new_reservation_for_each_distinct_gate_in_one_pr(
    tmp_path: Path,
) -> None:
    """(e-5) は phase4 と release の独立した予約を拒否しない。"""
    root, base = init_repository(tmp_path)
    write_reservation(root, 1)
    write_reservation(root, 1, gate_key="release-v1.0.0")
    head = commit_all(root, "docs: reserve phase4 and release")

    result = run_check(root, base, head)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("operation", ["modify", "delete", "rename", "type_change"])
def test_rejects_all_existing_record_changes(
    tmp_path: Path,
    operation: str,
) -> None:
    """M・D・rename 由来の D/A・T を非 A の既存証跡変更として拒否する。"""
    root, _ = init_repository(tmp_path)
    record_path = write_reservation(root)
    base = commit_all(root, "docs: existing reservation")
    path = root / record_path
    if operation == "modify":
        path.write_text(reservation_text() + "\n変更\n", encoding="utf-8")
    elif operation == "delete":
        path.unlink()
    elif operation == "rename":
        git(root, "mv", record_path, acceptance_path("renamed-reservation.md"))
    else:
        path.unlink()
        path.symlink_to("other-record.md")
    head = commit_all(root, f"docs: {operation} existing reservation")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert "追加以外の状態" in result.stderr


@pytest.mark.parametrize("status", ["C100", "R100", "T", "U", "X"])
def test_parses_all_nonadded_name_status_kinds(status: str) -> None:
    """C・R・T・U・X を含む非 A 状態を解析し、追加扱いにしない。"""
    path = acceptance_path("2026-08-20T101500Z-phase4-phase4-seq001-reservation.md")
    output = (
        f"{status}\0old.md\0{path}\0"
        if status[0] in {"C", "R"}
        else f"{status}\0{path}\0"
    )

    changes = append_only.parse_name_status(output)

    assert changes[0].status != append_only.GIT_STATUS_ADDED
    assert any(append_only.is_acceptance_path(item) for item in changes[0].paths)


@pytest.mark.parametrize("status", ["C", "U", "X"])
def test_rejects_each_nonadded_copy_unmerged_and_unknown_status(status: str) -> None:
    """C・U・X の既存証跡変更を check_append_only の拒否経路で固定する。"""
    existing_path = acceptance_path(
        "2026-08-20T101500Z-phase4-phase4-seq001-reservation.md"
    )
    paths = (
        existing_path,
        acceptance_path("copied-reservation.md"),
    ) if status == "C" else (existing_path,)
    change = append_only.ChangedPath(status=status, paths=paths)

    with (
        patch.object(append_only, "changed_paths", return_value=(change,)),
        patch.object(append_only, "parse_new_records", return_value=((), ())),
        patch.object(append_only, "tree_records", return_value=()),
    ):
        violations = append_only.check_append_only(Path("unused"), "base", "head")

    assert violations
    assert all("追加以外の状態" in violation for violation in violations)
    assert all(f"{status}" in violation for violation in violations)


def test_rejects_noncanonical_new_item_with_a_non_ascii_filename(tmp_path: Path) -> None:
    """Git の引用を経由せず、日本語名の未知項目を fail-closed にする。"""
    root, base = init_repository(tmp_path)
    invalid_path = acceptance_path("未知の項目.bin")
    write_text(root, invalid_path, "unknown\n")
    head = commit_all(root, "docs: add non-ascii unknown item")

    result = run_check(root, base, head)

    assert result.returncode == 1
    assert invalid_path in result.stderr
    assert "閉じた命名文法" in result.stderr


@pytest.mark.parametrize("filename", ["README.md", "reservation-template.md"])
def test_allows_modifying_canonical_acceptance_documents(
    tmp_path: Path,
    filename: str,
) -> None:
    """README とテンプレートの正当な改訂を append-only 拒否の対象外にする。"""
    root, _ = init_repository(tmp_path)
    canonical_path = acceptance_path(filename)
    write_text(root, canonical_path, "# 初版\n")
    base = commit_all(root, "docs: add canonical acceptance document")
    write_text(root, canonical_path, "# 改訂版\n")
    head = commit_all(root, "docs: revise canonical acceptance document")

    result = run_check(root, base, head)

    assert result.returncode == 0


def test_existing_gaps_and_duplicates_do_not_block_new_reservation(tmp_path: Path) -> None:
    """既存の欠番・重複を理由に正しい新規予約を不合格にしない。"""
    root, _ = init_repository(tmp_path)
    write_reservation(root, 1)
    write_evidence(root, 1)
    first_duplicate_id = attempt_id(3, timestamp=OTHER_ATTEMPT_TIMESTAMP)
    write_reservation(
        root,
        3,
        timestamp=OTHER_FILE_TIMESTAMP,
        record_id=first_duplicate_id,
    )
    write_evidence(
        root,
        3,
        timestamp=OTHER_FILE_TIMESTAMP,
        record_id=first_duplicate_id,
    )
    second_duplicate_id = attempt_id(3, timestamp="20260820T101502Z")
    write_reservation(
        root,
        3,
        timestamp="2026-08-20T101502Z",
        record_id=second_duplicate_id,
    )
    write_evidence(
        root,
        3,
        timestamp="2026-08-20T101502Z",
        record_id=second_duplicate_id,
    )
    base = commit_all(root, "docs: historic gap")
    write_reservation(root, 4)
    head = commit_all(root, "docs: reserve after historic gap")

    result = run_check(root, base, head)

    assert result.returncode == 0


def test_allows_an_old_feature_branch_with_develop_only_evidence(tmp_path: Path) -> None:
    """develop 側だけの証跡を削除扱いにしない三点差分で古いブランチを検査する。"""
    root, branch_point = init_repository(tmp_path)
    git(root, "branch", "feature/old", branch_point)
    develop_only_path = acceptance_path(
        reservation_filename(
            1,
            timestamp="2026-08-19T090000Z",
            gate_kind="release",
            release_version="v1.0.0",
        )
    )
    write_text(
        root,
        develop_only_path,
        reservation_text(gate_key="release-v1.0.0"),
    )
    base = commit_all(root, "docs: add release reservation on develop")
    git(root, "checkout", "-q", "feature/old")
    feature_path = write_reservation(root)
    head = commit_all(root, "docs: add phase4 reservation on old feature")

    result = run_check(root, base, head)
    changes = append_only.changed_paths(root, base, head)

    assert result.returncode == 0
    assert len(changes) == 1
    assert changes[0].status == append_only.GIT_STATUS_ADDED
    assert changes[0].paths == (feature_path,)


def test_develop_pull_request_event_runs_the_check(tmp_path: Path) -> None:
    """develop 宛 pull_request はスキップせず、孤児結果を不合格にする。"""
    root, base = init_repository(tmp_path)
    write_evidence(root)
    head = commit_all(root, "docs: orphan evidence")

    result = run_check(
        root,
        base,
        head,
        event_name="pull_request",
        event_data=pull_request_event(base, head),
    )

    assert result.returncode == 1
    assert "対応する予約" in result.stderr


def test_main_pull_request_event_is_skipped(tmp_path: Path) -> None:
    """main 宛 PR は既存証跡の全追加差分を誤検査しないためスキップする。"""
    root, base = init_repository(tmp_path)
    write_evidence(root)
    head = commit_all(root, "docs: orphan evidence")

    result = run_check(
        root,
        base,
        head,
        event_name="pull_request",
        event_data=pull_request_event(base, head, base_ref="main"),
    )

    assert result.returncode == 0
    assert "スキップ" in result.stdout


@pytest.mark.parametrize("event_name", ["push", "workflow_dispatch"])
def test_non_pull_request_events_are_skipped(tmp_path: Path, event_name: str) -> None:
    """push と workflow_dispatch は stdout に理由を出して成功終了する。"""
    root, base = init_repository(tmp_path)
    write_evidence(root)
    head = commit_all(root, "docs: orphan evidence")

    result = run_check(root, base, head, event_name=event_name)

    assert result.returncode == 0
    assert "スキップ" in result.stdout


@pytest.mark.parametrize("event_data", [{"pull_request": {}}, {"pull_request": {"base": {}}}])
def test_invalid_pull_request_event_fails_closed_without_cli_fallback(
    tmp_path: Path,
    event_data: dict[str, object],
) -> None:
    """壊れた PR イベントを --base/--head の値で救済せず fail-closed にする。"""
    root, base = init_repository(tmp_path)
    write_reservation(root)
    head = commit_all(root, "docs: reservation")

    result = run_check(
        root,
        base,
        head,
        event_name="pull_request",
        event_data=event_data,
    )

    assert result.returncode == 1
    assert "check_nfr021_append_only:" in result.stderr
