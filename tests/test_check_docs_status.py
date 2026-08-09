"""check_docs_status.py の単体・統合テスト。"""
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "check_docs_status.py"


def run_check(root: Path) -> subprocess.CompletedProcess[str]:
    """指定した最小リポジトリに対して検査スクリプトを起動する。

    Args:
        root: 検査対象リポジトリのルート。

    Returns:
        標準出力・標準エラーを取得したサブプロセスの結果。
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )


def write_text(root: Path, relative_path: str, content: str) -> None:
    """最小リポジトリ内へ UTF-8 のテキストファイルを書き出す。

    Args:
        root: 最小リポジトリのルート。
        relative_path: root からの相対パス。
        content: 書き込む内容。
    """
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def frontmatter(status: str) -> str:
    """指定 status を持つ最小の Markdown 文書を作る。

    Args:
        status: frontmatter に設定する status。

    Returns:
        最小の Markdown 文書内容。
    """
    return f"---\nstatus: {status}\n---\n# 文書\n"


def write_index(root: Path, entries: list[tuple[str, str, str]]) -> None:
    """正本一覧を含む最小の docs/README.md を作る。

    Args:
        root: 最小リポジトリのルート。
        entries: ``(表示名, docs/README.md からのリンク先, 状態セル)`` の配列。
    """
    rows = [
        "# ドキュメントマップ",
        "",
        "## 正本",
        "",
        "| 文書 | 状態 |",
        "| --- | --- |",
    ]
    rows.extend(f"| [{title}]({target}) | {status} |" for title, target, status in entries)
    write_text(root, "docs/README.md", "\n".join(rows) + "\n")


def make_minimal_repo(tmp_path: Path) -> Path:
    """正本 1 件を持つ最小リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。

    Returns:
        作成した最小リポジトリのルート。
    """
    root = tmp_path / "repo"
    write_index(root, [("仕様", "requirements/spec.md", "draft")])
    write_text(root, "docs/requirements/spec.md", frontmatter("draft"))
    return root


def test_accepts_matching_primary_documents_and_feature_plan(tmp_path):
    root = tmp_path / "repo"
    write_index(
        root,
        [
            ("要件", "requirements/spec.md", "**in-review**(注記)"),
            ("ADR", "adr/decision.md", "approved(記録)"),
        ],
    )
    write_text(root, "docs/requirements/spec.md", frontmatter("in-review"))
    write_text(root, "docs/adr/decision.md", frontmatter("approved"))
    write_text(
        root,
        "docs/features/example/plan.md",
        "---\nstatus: active  # feature の作業中状態\n---\n# 計画\n",
    )
    write_text(root, "docs/features/review/plan.md", frontmatter("in-review"))

    result = run_check(root)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("# frontmatter なし\n", "先頭行"),
        ("---\ntitle: 文書\n---\n# status なし\n", "2 行目"),
        ("---\nstatus: draft\nstatus: approved\n---\n# 重複\n", "終端 `---` が 3 行目"),
        (frontmatter("obsolete"), "語彙が不正"),
    ],
)
def test_rejects_invalid_primary_frontmatter(tmp_path, content, reason):
    root = make_minimal_repo(tmp_path)
    write_text(root, "docs/requirements/spec.md", content)

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/requirements/spec.md:" in result.stderr
    assert reason in result.stderr


@pytest.mark.parametrize(
    "content",
    [
        "---\ntitle: 任意キー\nstatus: draft\n---\n# 追加キー\n",
        "---\nstatus: draft # コメント\n---\n# 行末コメント\n",
        "---\nstatus: draft\n\n---\n# 空行\n",
        "---\nstatus: draft\nupdated: 2026-08-10\n---\n# 終端が4行目\n",
    ],
)
def test_rejects_primary_frontmatter_that_is_not_exactly_three_lines(tmp_path, content):
    root = make_minimal_repo(tmp_path)
    write_text(root, "docs/requirements/spec.md", content)

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/requirements/spec.md:" in result.stderr


def test_rejects_index_status_mismatch_after_normalization(tmp_path):
    root = make_minimal_repo(tmp_path)
    write_index(root, [("仕様", "requirements/spec.md", "**in-review**(注記)")])
    write_text(root, "docs/requirements/spec.md", frontmatter("approved"))

    result = run_check(root)

    assert result.returncode == 1
    assert "索引の状態(in-review)" in result.stderr


def test_rejects_active_status_on_primary_document(tmp_path):
    root = make_minimal_repo(tmp_path)
    write_index(root, [("仕様", "requirements/spec.md", "active")])
    write_text(root, "docs/requirements/spec.md", frontmatter("active"))

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/requirements/spec.md:" in result.stderr
    assert "語彙が不正: active" in result.stderr


def test_rejects_document_status_on_feature_plan(tmp_path):
    root = make_minimal_repo(tmp_path)
    write_text(root, "docs/features/example/plan.md", frontmatter("approved"))

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/features/example/plan.md:" in result.stderr
    assert "語彙が不正: approved" in result.stderr


def test_accepts_plan_frontmatter_with_other_keys_and_status_comment(tmp_path):
    root = make_minimal_repo(tmp_path)
    write_text(
        root,
        "docs/features/example/plan.md",
        "---\nfeature: example\nstatus: active # 作業中\nbranch: feature/example\n---\n# 計画\n",
    )

    result = run_check(root)

    assert result.returncode == 0, result.stderr


def test_rejects_duplicate_status_on_feature_plan(tmp_path):
    root = make_minimal_repo(tmp_path)
    write_text(
        root,
        "docs/features/example/plan.md",
        "---\nfeature: example\nstatus: active\nstatus: in-review\n---\n# 計画\n",
    )

    result = run_check(root)

    assert result.returncode == 1
    assert "docs/features/example/plan.md:" in result.stderr
    assert "ちょうど 1 行" in result.stderr


def test_excludes_worklog_legacy_and_templates(tmp_path):
    root = tmp_path / "repo"
    write_index(
        root,
        [
            ("仕様", "requirements/spec.md", "draft"),
            ("作業ログ", "worklog/bad.md", "draft"),
            ("旧資料", "legacy/bad.md", "draft"),
            ("テンプレート", "development/templates/bad.md", "draft"),
        ],
    )
    write_text(root, "docs/requirements/spec.md", frontmatter("draft"))
    write_text(root, "docs/worklog/bad.md", "# frontmatter なし\n")
    write_text(root, "docs/legacy/bad.md", "# frontmatter なし\n")
    write_text(root, "docs/development/templates/bad.md", "# frontmatter なし\n")

    result = run_check(root)

    assert result.returncode == 0, result.stderr


def test_current_repository_passes_integration_check():
    result = run_check(REPO)

    assert result.returncode == 0, result.stderr
