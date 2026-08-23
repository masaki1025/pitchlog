"""check_plan_docs_sync.py の Git 差分を使う単体テスト。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "check_plan_docs_sync.py"


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """テスト用一時リポジトリに Git コマンドを実行する。

    Args:
        cwd: Git コマンドの実行ディレクトリ。
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
    """最小リポジトリ内へ UTF-8 テキストファイルを書き出す。

    Args:
        root: 最小リポジトリのルート。
        relative_path: root からの相対パス。
        content: 書き込む本文。
    """
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_index(root: Path, entries: list[tuple[str, str]]) -> None:
    """指定文書を掲載した最小の docs/README.md を書く。

    Args:
        root: 最小リポジトリのルート。
        entries: ``(表示名, docs/README.md 基準のリンク先)`` の配列。
    """
    lines = ["# 索引", "", "## 正本", "", "| 文書 |", "| --- |"]
    lines.extend(f"| [{title}]({target}) |" for title, target in entries)
    write_text(root, "docs/README.md", "\n".join(lines) + "\n")


def plan_text(status: str, declaration_lines: list[str] | None = None) -> str:
    """宣言突合に必要な最小の計画書本文を作る。

    Args:
        status: frontmatter に設定する status。
        declaration_lines: 「影響する正本」節に置く行。``None`` なら節を省略する。

    Returns:
        最小の計画書内容。
    """
    lines = ["---", f"status: {status}", "---", "# 計画"]
    if declaration_lines is not None:
        lines.extend(["", "## 3. 影響する正本", *declaration_lines, "", "## 4. 次節"])
    else:
        lines.extend(["", "## 2. 概要"])
    return "\n".join(lines) + "\n"


def write_plan(
    root: Path,
    status: str = "active",
    declaration_lines: list[str] | None = None,
) -> None:
    """docs/features/foo/plan.md に最小の計画書を書く。

    Args:
        root: 最小リポジトリのルート。
        status: frontmatter に設定する status。
        declaration_lines: 「影響する正本」節に置く行。
    """
    write_text(
        root,
        "docs/features/foo/plan.md",
        plan_text(status, declaration_lines),
    )


def commit_all(root: Path, subject: str) -> None:
    """現在の変更をすべてコミットする。

    Args:
        root: テスト用リポジトリのルート。
        subject: コミット件名。
    """
    git(root, "add", "-A")
    git(root, "commit", "-qm", subject)


def init_repository(
    tmp_path: Path,
    *,
    branch: str = "feature/foo",
    plan_status: str = "active",
    declaration_lines: list[str] | None = None,
    entries: list[tuple[str, str]] | None = None,
) -> Path:
    """origin/develop を持つ一時 Git リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        branch: 初期ブランチ名。
        plan_status: 計画書 frontmatter の status。
        declaration_lines: 計画書 3 節の行。
        entries: 初期索引に載せる文書。省略時は仕様書 1 件。

    Returns:
        作成したリポジトリのルート。
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
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")

    document_entries = entries or [("仕様", "requirements/spec.md")]
    write_index(root, document_entries)
    for _, target in document_entries:
        write_text(root, f"docs/{target}", "# 正本\n")
    write_plan(
        root,
        plan_status,
        declaration_lines if declaration_lines is not None else [],
    )
    commit_all(root, "chore: base")
    git(root, "update-ref", "refs/remotes/origin/develop", "HEAD")
    return root


def run_check(
    root: Path,
    *args: str,
    plan: bool = True,
) -> subprocess.CompletedProcess[str]:
    """宣言突合スクリプトを一時リポジトリに対して起動する。

    Args:
        root: 検査対象リポジトリのルート。
        *args: スクリプトに追加する引数。
        plan: ``--plan docs/features/foo/plan.md`` を自動指定するか。

    Returns:
        標準出力・標準エラーを取得したサブプロセスの結果。
    """
    command = [sys.executable, str(SCRIPT), "--root", str(root)]
    if plan:
        command.extend(["--plan", "docs/features/foo/plan.md"])
    command.extend(args)
    return subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )


def test_rejects_changed_primary_without_declaration(tmp_path: Path) -> None:
    root = init_repository(tmp_path)
    write_text(root, "docs/requirements/spec.md", "# 変更済み正本\n")
    commit_all(root, "docs: 正本を変更")

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/requirements/spec.md: 計画書 3 節に宣言がない" in result.stderr


def test_rejects_changed_primary_declared_no_change(tmp_path: Path) -> None:
    root = init_repository(
        tmp_path,
        declaration_lines=["| [仕様](../../requirements/spec.md) | 反映なし |"],
    )
    write_text(root, "docs/requirements/spec.md", "# 変更済み正本\n")
    commit_all(root, "docs: 正本を変更")

    result = run_check(root)

    assert result.returncode == 1
    assert (
        "docs/requirements/spec.md: 計画書 3 節で「反映なし」と宣言されている"
        in result.stderr
    )


def test_rejects_reflected_declaration_without_change_in_review(tmp_path: Path) -> None:
    root = init_repository(
        tmp_path,
        plan_status="in-review",
        declaration_lines=["| [仕様](../../requirements/spec.md) | 更新 |"],
    )

    result = run_check(root, plan=False)

    assert result.returncode == 1
    assert "docs/requirements/spec.md: 計画書 3 節で反映すると宣言したが差分にない" in result.stderr


def test_rejects_deleted_primary_when_head_index_also_drops_it(tmp_path: Path) -> None:
    root = init_repository(
        tmp_path,
        declaration_lines=["| [索引](../../README.md) | 更新 |"],
    )
    (root / "docs/requirements/spec.md").unlink()
    write_index(root, [])
    commit_all(root, "docs: 正本と索引行を削除")

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/requirements/spec.md: 計画書 3 節に宣言がない" in result.stderr


def test_rejects_renamed_primary_when_only_new_path_is_declared(tmp_path: Path) -> None:
    root = init_repository(
        tmp_path,
        declaration_lines=[
            "| [索引](../../README.md) / [新仕様](../../requirements/renamed.md) | 更新 |"
        ],
    )
    git(root, "mv", "docs/requirements/spec.md", "docs/requirements/renamed.md")
    write_index(root, [("新仕様", "requirements/renamed.md")])
    commit_all(root, "docs: 正本を改名")

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/requirements/spec.md: 計画書 3 節に宣言がない" in result.stderr


def test_rejects_unindexed_and_undeclared_new_primary_from_filesystem(
    tmp_path: Path,
) -> None:
    root = init_repository(tmp_path)
    write_text(root, "docs/requirements/new.md", "# 新設正本\n")
    commit_all(root, "docs: 索引未掲載の正本を追加")

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/requirements/new.md: 計画書 3 節に宣言がない" in result.stderr


def test_rejects_plan_without_affected_primary_section(tmp_path: Path) -> None:
    root = init_repository(tmp_path)
    write_plan(root, declaration_lines=None)
    write_text(root, "docs/requirements/spec.md", "# 変更済み正本\n")
    commit_all(root, "docs: 計画書の節を削除")

    result = run_check(root)

    assert result.returncode == 1
    assert "計画書に「影響する正本」節がない" in result.stderr


def test_fails_closed_when_git_execution_fails(tmp_path: Path) -> None:
    root = init_repository(tmp_path)

    result = run_check(root, "--base", "missing-base")

    assert result.returncode == 1
    assert "check_plan_docs_sync: git diff に失敗した" in result.stderr


def test_fails_closed_when_plan_cannot_be_derived_from_branch(tmp_path: Path) -> None:
    root = init_repository(tmp_path, branch="chore/foo")

    result = run_check(root, plan=False)

    assert result.returncode == 1
    assert "ブランチ名から計画書を導出できない" in result.stderr


def test_ignores_changes_only_in_excluded_paths(tmp_path: Path) -> None:
    root = init_repository(tmp_path)
    write_text(root, "docs/worklog/log.md", "# 作業ログ\n")
    write_text(root, "docs/legacy/archive.md", "# 旧資料\n")
    write_text(root, "docs/features/other/note.md", "# feature 補助文書\n")
    write_text(root, "docs/development/templates/sample.md", "# テンプレート\n")
    write_text(root, ".claude/rule.md", "# 規約\n")
    write_text(root, "AGENTS.md", "# 規約\n")
    commit_all(root, "docs: 除外文書を更新")

    result = run_check(root)

    assert result.returncode == 0, result.stderr


def test_accepts_markdown_links_and_backtick_paths(tmp_path: Path) -> None:
    entries = [
        ("リンク形式", "requirements/linked.md"),
        ("バッククォート形式", "development/coded.md"),
        ("作業中", "requirements/pending.md"),
    ]
    root = init_repository(
        tmp_path,
        declaration_lines=[
            "| [リンク形式](../../requirements/linked.md) | 更新 |",
            "| `docs/development/coded.md` | 更新 |",
            "| [作業中](../../requirements/pending.md) | 更新予定 |",
        ],
        entries=entries,
    )
    write_text(root, "docs/requirements/linked.md", "# リンク形式を変更\n")
    write_text(root, "docs/development/coded.md", "# バッククォート形式を変更\n")
    commit_all(root, "docs: 宣言済みの正本を変更")

    result = run_check(root)

    assert result.returncode == 0, result.stderr
    assert (
        "docs/requirements/pending.md: 計画書 3 節で反映すると宣言したが差分にない"
        in result.stderr
    )


def test_accepts_all_markdown_links_on_one_line(tmp_path: Path) -> None:
    entries = [("A", "requirements/a.md"), ("B", "requirements/b.md")]
    root = init_repository(
        tmp_path,
        declaration_lines=[
            "| [A](../../requirements/a.md) / [B](../../requirements/b.md) | 更新 |"
        ],
        entries=entries,
    )
    write_text(root, "docs/requirements/a.md", "# A を変更\n")
    write_text(root, "docs/requirements/b.md", "# B を変更\n")
    commit_all(root, "docs: 2 文書を変更")

    result = run_check(root)

    assert result.returncode == 0, result.stderr
