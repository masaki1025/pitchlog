"""feature_status.py の単体・Git 故障系テスト。"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "feature_status.py"
MISSING = object()


def load_feature_status():
    """テスト対象スクリプトをモジュールとして読み込む。"""
    spec = importlib.util.spec_from_file_location("feature_status_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


feature_status = load_feature_status()


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """テスト用一時リポジトリに Git コマンドを実行する。"""
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )


def init_repository(tmp_path: Path) -> tuple[Path, Path]:
    """origin/develop と feature worktree を持つ一時リポジトリを作る。"""
    root = tmp_path / "repository"
    root.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "develop", str(root)],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-qm", "chore: base")
    git(root, "update-ref", "refs/remotes/origin/develop", "HEAD")

    feature_worktree = tmp_path / "feature-foo"
    git(root, "worktree", "add", "-q", "-b", "feature/foo", str(feature_worktree))
    return root, feature_worktree


def plan_text(
    *,
    status_lines: list[str] | None = None,
    branch: str | None = "feature/foo",
    approval: str | None = "済",
    review_round: object = MISSING,
    final_gate_round: object = MISSING,
    execution_mode: object = MISSING,
    steps: tuple[int, ...] = (1, 2),
    body_lines: tuple[str, ...] = (),
) -> str:
    """テスト用の最小 plan.md を作る。"""
    lines = ["---", "feature: foo"]
    lines.extend(status_lines if status_lines is not None else ["status: active"])
    if approval is not None:
        lines.append(f"承認: {approval}")
    if branch is not None:
        lines.append(f"branch: {branch}")
    if review_round is not MISSING:
        lines.append(f"計画レビュー周回: {review_round}")
    if final_gate_round is not MISSING:
        lines.append(f"確定ゲート周回: {final_gate_round}")
    if execution_mode is not MISSING:
        lines.append(f"実行方式: {execution_mode}")
    lines.extend(
        [
            "---",
            "# 計画",
            "### 実装ステップ(コミット単位)",
            "| # | ステップ | 合格条件 |",
            "| --- | --- | --- |",
        ]
    )
    lines.extend(f"| {number} | 実装 {number} | pytest |" for number in steps)
    lines.extend(body_lines)
    return "\n".join(lines) + "\n"


def write_plan(
    worktree: Path,
    name: str = "foo",
    **kwargs: object,
) -> Path:
    """worktree 内に指定内容の feature plan を書く。"""
    path = worktree / "docs" / "features" / name / "plan.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan_text(**kwargs), encoding="utf-8")
    return path


def commit_all(worktree: Path, subject: str) -> None:
    """worktree の全変更を指定件名でコミットする。"""
    git(worktree, "add", "-A")
    git(worktree, "commit", "-qm", subject)


def commit_implementation(worktree: Path, number: int, subject: str) -> None:
    """実装系パスを 1 件変更してコミットする。"""
    path = worktree / "implementation" / f"change-{number}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{number}\n", encoding="utf-8")
    commit_all(worktree, subject)


def run_status(
    root: Path,
    output_format: str = "text",
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """CLI を実行し、標準出力を返す。"""
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--format",
            output_format,
            "--cwd",
            str(root),
        ],
        capture_output=True,
        encoding="utf-8",
        env=env,
        text=True,
        timeout=30,
    )


def feature_block(output: str, name: str) -> str:
    """text 出力から 1 feature 分のブロックを取り出す。"""
    marker = f"feature: {name} "
    start = output.index(marker)
    end = output.find("\n\nfeature: ", start)
    return output[start:] if end == -1 else output[start:end]


def hook_line(output: str, name: str) -> str:
    """hook 出力から 1 feature 分の行を取り出す。"""
    return next(line for line in output.splitlines() if line.startswith(f"{name}("))


def setup_committed_plan(
    tmp_path: Path,
    *,
    status: str = "active",
    approval: str = "済",
    steps: tuple[int, ...] = (1, 2),
) -> tuple[Path, Path, Path]:
    """計画系コミット済みの feature worktree を作る。"""
    root, worktree = init_repository(tmp_path)
    plan = write_plan(
        worktree,
        status_lines=[f"status: {status}"],
        approval=approval,
        steps=steps,
    )
    commit_all(worktree, "docs: 承認・起票")
    return root, worktree, plan


def gh_environment(tmp_path: Path, source: str | None) -> dict[str, str]:
    """git と任意の gh スタブだけを PATH に持つ環境を作る。"""
    tools = tmp_path / "tools"
    tools.mkdir(parents=True)
    git_path = shutil.which("git")
    assert git_path is not None
    linked_git = tools / Path(git_path).name
    try:
        os.symlink(git_path, linked_git)
    except OSError:
        shutil.copy2(git_path, linked_git)
        linked_git.chmod(0o755)

    if source is not None:
        if os.name == "nt":
            script = tools / "gh_stub.py"
            script.write_text(source, encoding="utf-8")
            launcher = tools / "gh.cmd"
            launcher.write_text(
                f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
                encoding="utf-8",
            )
        else:
            launcher = tools / "gh"
            launcher.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
            launcher.chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = str(tools)
    return environment


def feature_plan_for_direct_call(worktree: Path, plan_path: Path):
    """gh タイムアウト試験用の FeaturePlan を組み立てる。"""
    frontmatter = feature_status.read_frontmatter(plan_path)
    assert frontmatter is not None
    return feature_status.FeaturePlan(
        name=plan_path.parent.name,
        plan_path=plan_path,
        relative_plan_path=plan_path.relative_to(worktree).as_posix(),
        worktree=feature_status.Worktree(path=worktree, branch="feature/foo"),
        frontmatter=frontmatter,
    )


def test_frontmatter_extensions_defaults_comments_and_invalid_values(tmp_path: Path):
    """拡張キーの既定値・行末コメント・不正値表示を固定する。"""
    parsed = feature_status.parse_frontmatter_body(
        "\n".join(
            [
                "status: active # コメント",
                "branch: feature/foo",
                "承認: 済",
                "計画レビュー周回: 3 # コメント",
                "確定ゲート周回: 2 # コメント",
                "実行方式: 通常 # コメント",
            ]
        )
    )
    assert parsed is not None
    assert parsed.plan_review_round == 3
    assert parsed.final_gate_round == 2
    assert parsed.execution_mode == "通常"

    defaults = feature_status.parse_frontmatter_body(
        "status: active\nbranch: feature/foo\n"
    )
    assert defaults is not None
    assert defaults.plan_review_round == 0
    assert defaults.final_gate_round == 0
    assert defaults.execution_mode == "通常"

    root, worktree = init_repository(tmp_path / "invalid-values")
    write_plan(
        worktree,
        review_round="abc",
        final_gate_round="-1",
        approval="未",
    )
    completed = run_status(root)
    assert completed.returncode == 0
    block = feature_block(completed.stdout, "foo")
    assert "計画レビュー周回: 不正値" in block
    assert "確定ゲート周回: 不正値" in block
    invalid_hook = hook_line(run_status(root, "hook").stdout, "foo")
    assert "計画レビュー周回 不正値" in invalid_hook
    assert "確定ゲート周回 不正値" in invalid_hook


def test_selection_matrix_and_parse_failure_priority(tmp_path: Path):
    """worktree・branch・厳密 status の選別順を検証する。"""
    root, worktree = init_repository(tmp_path)
    write_plan(worktree, "valid", approval="未")
    write_plan(
        worktree,
        "comment",
        status_lines=["status: active # 行末コメント"],
        approval="未",
    )
    write_plan(
        worktree,
        "body-match",
        approval="未",
        body_lines=("status: activeX",),
    )
    write_plan(worktree, "branch-mismatch", branch="feature/other", approval="未")
    write_plan(worktree, "branch-missing", branch=None, approval="未")

    invalid_statuses = {
        "active-x": ["status: activeX"],
        "extra-token": ["status: active 余剰"],
        "duplicate": ["status: active", "status: active"],
        "space-before-colon": ["status : active"],
        "coexisting": ["status: active", "status : active"],
        "missing-status": [],
        "parse-before-branch": ["status: activeX"],
    }
    for name, status_lines in invalid_statuses.items():
        write_plan(
            worktree,
            name,
            status_lines=status_lines,
            branch="feature/other" if name == "parse-before-branch" else "feature/foo",
            approval="未",
        )

    # develop/main worktree は plan があっても先に無言除外する。
    write_plan(root, "develop-only", approval="未")
    git(root, "branch", "main")
    main_worktree = tmp_path / "main"
    git(root, "worktree", "add", "-q", str(main_worktree), "main")
    write_plan(main_worktree, "main-only", approval="未")

    completed = run_status(root)
    assert completed.returncode == 0
    output = completed.stdout
    for name in ("valid", "comment", "body-match"):
        assert f"feature: {name} " in output
    for name in ("branch-mismatch", "branch-missing", "develop-only", "main-only"):
        assert f"feature: {name} " not in output
    for name in invalid_statuses:
        assert "未取得(frontmatter 解析失敗)" in feature_block(output, name)
    assert output.count("未取得(frontmatter 解析失敗)") == len(invalid_statuses)


def test_approval_values_select_plan_or_implementation_stage(tmp_path: Path):
    """承認の startswith('済') 判定と欠落時の計画段階を検証する。"""
    root, worktree = init_repository(tmp_path)
    write_plan(worktree, "approved-short", approval="済")
    write_plan(worktree, "approved-full", approval="済(2026-08-10・承認者)")
    write_plan(worktree, "not-approved", approval="未")
    write_plan(worktree, "approval-missing", approval=None)

    output = run_status(root).stdout
    assert "実装前(全 2 ステップ)" in feature_block(output, "approved-short")
    assert "実装前(全 2 ステップ)" in feature_block(output, "approved-full")
    assert "計画段階" in feature_block(output, "not-approved")
    assert "計画段階" in feature_block(output, "approval-missing")


@pytest.mark.parametrize("steps", [(1, 3), (1, 1), (0,)])
def test_invalid_step_table_wins_over_commit_count(tmp_path: Path, steps: tuple[int, ...]):
    """欠番・重複・N=0 の表はコミットがあっても不整合にする。"""
    root, worktree = init_repository(tmp_path)
    write_plan(worktree, steps=steps)
    commit_all(worktree, "docs: 不正な表を起票")
    commit_implementation(worktree, 1, "feat: 実装 (ステップ 1/3)")

    output = run_status(root).stdout
    assert "実装状況: 不整合(要確認)" in feature_block(output, "foo")


@pytest.mark.parametrize(
    "subject",
    [
        "feat: 未閉止 (ステップ 7",
        "feat: 括弧種不一致 （ステップ 7)",
        "feat: 非境界 (ステップ 2abc)",
        "feat: ゼロ (ステップ 0)",
        "feat: 総数不一致 (ステップ 4/3)",
    ],
)
def test_malformed_step_tokens_are_inconsistent(tmp_path: Path, subject: str):
    """数値まで書かれた不完全トークンを黙って無視しない。"""
    root, worktree, _ = setup_committed_plan(tmp_path, steps=(1, 2, 3, 4, 5, 6))
    commit_implementation(worktree, 1, subject)

    output = run_status(root).stdout
    assert "実装状況: 不整合(要確認)" in feature_block(output, "foo")


@pytest.mark.parametrize(
    "subject",
    ["docs: ステップ 2 の補足", "docs: (ステップ実行の見直し)"],
)
def test_non_tokens_do_not_count_as_steps(tmp_path: Path, subject: str):
    """括弧なし・数値なしの記述は算入せず実装系なら不明にする。"""
    root, worktree, _ = setup_committed_plan(tmp_path)
    commit_implementation(worktree, 1, subject)

    output = run_status(root).stdout
    assert "実装状況: 不明" in feature_block(output, "foo")


def test_two_tokens_in_one_subject_are_inconsistent(tmp_path: Path):
    """1 コミットに複数の有効トークンを許可しない。"""
    root, worktree, _ = setup_committed_plan(tmp_path)
    commit_implementation(
        worktree,
        1,
        "feat: まとめて実装 (ステップ 1/2) (ステップ 2/2)",
    )

    output = run_status(root).stdout
    assert "実装状況: 不整合(要確認)" in feature_block(output, "foo")


def test_fullwidth_and_halfwidth_tokens_and_contiguous_progress(tmp_path: Path):
    """同種の全半角括弧による連続トークンを正しく採用する。"""
    root, worktree, _ = setup_committed_plan(tmp_path)
    commit_implementation(worktree, 1, "feat: 前半 (ステップ 1/2)")
    commit_implementation(worktree, 2, "feat: 後半 （ステップ 2/2）")

    output = run_status(root).stdout
    assert "実装完了・/pr 前" in feature_block(output, "foo")


def test_duplicate_step_in_different_commits_is_normal(tmp_path: Path):
    """異なるコミット間の同一ステップ再委任は正常に扱う。"""
    root, worktree, _ = setup_committed_plan(tmp_path)
    commit_implementation(worktree, 1, "feat: 初回 (ステップ 1/2)")
    commit_implementation(worktree, 2, "fix: 再委任 (ステップ 1/2)")

    output = run_status(root).stdout
    assert "実装中(ステップ 1/2 完了)" in feature_block(output, "foo")


@pytest.mark.parametrize(
    ("steps", "subjects"),
    [
        ((1, 2, 3), ("feat: 1 (ステップ 1/3)", "feat: 3 (ステップ 3/3)")),
        ((1, 2), ("feat: 範囲外 (ステップ 3)",)),
    ],
)
def test_step_gap_and_out_of_range_are_inconsistent(
    tmp_path: Path,
    steps: tuple[int, ...],
    subjects: tuple[str, ...],
):
    """欠番と表範囲外の k は不整合にする。"""
    root, worktree, _ = setup_committed_plan(tmp_path, steps=steps)
    for number, subject in enumerate(subjects, start=1):
        commit_implementation(worktree, number, subject)

    output = run_status(root).stdout
    assert "実装状況: 不整合(要確認)" in feature_block(output, "foo")


def test_planning_commits_are_excluded_then_first_step_is_adopted(tmp_path: Path):
    """承認・起票だけは実装前、最初の記法付き実装は k=1 にする。"""
    root, worktree, _ = setup_committed_plan(tmp_path, steps=(1, 2, 3, 4, 5, 6))
    initial = run_status(root).stdout
    assert "実装前(全 6 ステップ)" in feature_block(initial, "foo")

    commit_implementation(worktree, 1, "feat: 最初の実装 (ステップ 1/6)")
    progressed = run_status(root).stdout
    assert "実装中(ステップ 1/6 完了)" in feature_block(progressed, "foo")


def test_unmarked_implementation_and_empty_commit_are_unknown(tmp_path: Path):
    """実装系の無記法コミットと空コミットを保守的に不明にする。"""
    root, worktree, _ = setup_committed_plan(tmp_path / "implementation")
    commit_implementation(worktree, 1, "feat: 記法なし実装")
    assert "実装状況: 不明" in feature_block(run_status(root).stdout, "foo")

    empty_root, empty_worktree, _ = setup_committed_plan(tmp_path / "empty")
    git(empty_worktree, "commit", "--allow-empty", "-m", "chore: 空コミット")
    assert "実装状況: 不明" in feature_block(run_status(empty_root).stdout, "foo")


def test_unmarked_two_parent_merge_is_unknown(tmp_path: Path):
    """名前を返さない可能性がある 2 親マージを計画系に倒さない。"""
    root, worktree, _ = setup_committed_plan(tmp_path)
    side_worktree = tmp_path / "side"
    git(
        root,
        "worktree",
        "add",
        "-q",
        "-b",
        "feature/side",
        str(side_worktree),
        "feature/foo",
    )
    side_note = side_worktree / "docs" / "features" / "foo" / "side.md"
    side_note.write_text("side\n", encoding="utf-8")
    commit_all(side_worktree, "docs: side の計画メモ")
    git(worktree, "merge", "--no-ff", "feature/side", "-m", "merge: 記法なし")

    output = run_status(root).stdout
    assert "実装状況: 不明" in feature_block(output, "foo")


def test_execution_modes_and_comments_in_text_and_hook(tmp_path: Path):
    """fast・通常・省略・不正な実行方式を両出力形式で判定する。"""
    root, worktree = init_repository(tmp_path)
    write_plan(worktree, "fast", execution_mode="fast # コメント")
    write_plan(worktree, "normal", execution_mode="通常")
    write_plan(worktree, "omitted")
    write_plan(worktree, "invalid", execution_mode="fastt")
    write_plan(worktree, "empty", execution_mode="")

    text_output = run_status(root, "text").stdout
    hook_output = run_status(root, "hook").stdout
    for output, block_getter in ((text_output, feature_block), (hook_output, hook_line)):
        assert "fast path 実装中" in block_getter(output, "fast")
        assert "実装前(全 2 ステップ)" in block_getter(output, "normal")
        assert "実装前(全 2 ステップ)" in block_getter(output, "omitted")
        assert "未取得(実行方式不正)" in block_getter(output, "invalid")
        assert "未取得(実行方式不正)" in block_getter(output, "empty")
        assert "PR 状態: 未取得" in output
    assert "Notion" not in text_output
    assert "Notion" not in hook_output


def test_rejection_history_overrides_completed_progress_and_returns_to_pr_stage(
    tmp_path: Path,
):
    """in-review→active の往復を base..HEAD 限定で導出する。"""
    root, worktree = init_repository(tmp_path)
    plan = write_plan(
        worktree,
        status_lines=["status: in-review"],
        steps=(1,),
    )
    commit_all(worktree, "docs: PR レビュー開始")
    commit_implementation(worktree, 1, "feat: 完了済み実装 (ステップ 1/1)")
    plan.write_text(
        plan.read_text(encoding="utf-8").replace("status: in-review", "status: active"),
        encoding="utf-8",
    )
    commit_all(worktree, "docs: 差し戻し修正を開始")

    text_output = run_status(root).stdout
    hook_output = run_status(root, "hook").stdout
    assert "実装中(差し戻し修正)" in feature_block(text_output, "foo")
    assert "実装完了・/pr 前" not in feature_block(text_output, "foo")
    assert "ステップ進捗: 1/1" in feature_block(text_output, "foo")
    assert "実装中(差し戻し修正)" in hook_line(hook_output, "foo")

    plan.write_text(
        plan.read_text(encoding="utf-8").replace("status: active", "status: in-review"),
        encoding="utf-8",
    )
    commit_all(worktree, "docs: 再レビュー依頼")
    assert "PR 段階" in feature_block(run_status(root).stdout, "foo")


def test_in_review_only_on_base_side_does_not_trigger_rejection(tmp_path: Path):
    """origin/develop より前の in-review 履歴を差し戻しと誤判定しない。"""
    root = tmp_path / "repository"
    root.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "develop", str(root)],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")
    base_plan = write_plan(root, status_lines=["status: in-review"], steps=(1,))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: base 側の過去レビュー")
    git(root, "update-ref", "refs/remotes/origin/develop", "HEAD")

    worktree = tmp_path / "feature-foo"
    git(root, "worktree", "add", "-q", "-b", "feature/foo", str(worktree))
    feature_plan = worktree / base_plan.relative_to(root)
    feature_plan.write_text(
        feature_plan.read_text(encoding="utf-8").replace("status: in-review", "status: active"),
        encoding="utf-8",
    )
    commit_all(worktree, "docs: feature を開始")

    block = feature_block(run_status(root).stdout, "foo")
    assert "実装前(全 1 ステップ)" in block
    assert "差し戻し修正" not in block


def test_parse_failures_are_visible_without_hiding_healthy_feature(tmp_path: Path):
    """非閉止・8KiB 超過 plan は健全 feature と併存しても表示する。"""
    root, worktree = init_repository(tmp_path)
    write_plan(worktree, "healthy", approval="未")

    unclosed = worktree / "docs" / "features" / "unclosed" / "plan.md"
    unclosed.parent.mkdir(parents=True)
    unclosed.write_text(
        "---\nfeature: unclosed\nstatus: active\nbranch: feature/foo\n",
        encoding="utf-8",
    )
    oversized = worktree / "docs" / "features" / "oversized" / "plan.md"
    oversized.parent.mkdir(parents=True)
    oversized.write_text(
        "---\nfeature: oversized\nstatus: active\nbranch: feature/foo\nnote: "
        + "x" * (feature_status.FRONTMATTER_LIMIT + 1)
        + "\n---\n# 計画\n",
        encoding="utf-8",
    )

    text_output = run_status(root).stdout
    hook_output = run_status(root, "hook").stdout
    assert "feature: healthy " in text_output
    for output, block_getter in ((text_output, feature_block), (hook_output, hook_line)):
        assert "未取得(frontmatter 解析失敗)" in block_getter(output, "unclosed")
        assert "未取得(frontmatter 解析失敗)" in block_getter(output, "oversized")


def test_worktree_and_feature_git_failures_are_visible_and_exit_zero(tmp_path: Path):
    """worktree 列挙失敗・feature 単位 Git 失敗を未取得として返す。"""
    missing_root = tmp_path / "not-a-repository"
    enumeration = run_status(missing_root)
    assert enumeration.returncode == 0
    assert enumeration.stdout.strip() == "進行中 feature: 未取得(worktree 列挙失敗)"

    root, worktree, _ = setup_committed_plan(tmp_path / "git-failure")
    git(root, "update-ref", "-d", "refs/remotes/origin/develop")
    feature_failure = run_status(root)
    assert feature_failure.returncode == 0
    assert "未取得(git 失敗)" in feature_block(feature_failure.stdout, "foo")


def test_gh_missing_is_reported_as_pr_degradation(tmp_path: Path):
    """PATH に gh がない場合は PR 行だけを縮退表示する。"""
    root, _, _ = setup_committed_plan(tmp_path, status="in-review")

    completed = run_status(root, env=gh_environment(tmp_path, None))

    assert completed.returncode == 0
    block = feature_block(completed.stdout, "foo")
    assert "段階: PR 段階" in block
    assert "PR 状態: 未取得(縮退)" in block


def test_gh_nonzero_exit_is_reported_as_pr_degradation(tmp_path: Path):
    """gh の非 0 終了を fail-open で PR 縮退表示へ変換する。"""
    root, _, _ = setup_committed_plan(tmp_path, status="in-review")
    environment = gh_environment(tmp_path, "raise SystemExit(2)\n")

    completed = run_status(root, env=environment)

    assert completed.returncode == 0
    assert "PR 状態: 未取得(縮退)" in feature_block(completed.stdout, "foo")


def test_gh_timeout_is_reported_as_pr_degradation_without_waiting_ten_seconds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """gh のタイムアウトは注入値で短く検証して PR 縮退表示にする。"""
    _, worktree, plan_path = setup_committed_plan(tmp_path, status="in-review")
    environment = gh_environment(
        tmp_path,
        "import time\ntime.sleep(5)\n",
    )
    monkeypatch.setenv("PATH", environment["PATH"])
    started = time.monotonic()
    result = feature_status.derive_feature(
        feature_plan_for_direct_call(worktree, plan_path),
        resolve_pr=True,
        pr_timeout_seconds=0.05,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 1
    assert "PR 状態: 未取得(縮退)" in feature_status.format_text_result(result)


@pytest.mark.parametrize("state", ["OPEN", "MERGED", "CLOSED"])
def test_gh_state_is_reflected_in_text_stage(
    tmp_path: Path,
    state: str,
):
    """gh の OPEN/MERGED/CLOSED を text 出力の段階と PR 行へ反映する。"""
    root, _, _ = setup_committed_plan(tmp_path, status="in-review")
    source = (
        "import json\n"
        "import sys\n"
        "if sys.argv[1:] != ['pr', 'view', 'feature/foo', '--json', 'state,url']:\n"
        "    raise SystemExit(8)\n"
        f"print(json.dumps({{'state': {state!r}, 'url': 'https://example.test/pr/1'}}))\n"
    )
    completed = run_status(root, env=gh_environment(tmp_path, source))

    assert completed.returncode == 0
    block = feature_block(completed.stdout, "foo")
    assert f"PR 状態: {state}" in block
    if state == "MERGED":
        assert "PR 段階(MERGED・/task-done 待ち)" in block
    else:
        assert f"PR 段階({state})" in block


def test_hook_mode_does_not_start_gh(tmp_path: Path):
    """hook 形式では gh スタブを PATH に置いても実行しない。"""
    root, _, _ = setup_committed_plan(tmp_path, status="in-review")
    marker = tmp_path / "gh-called"
    source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('called', encoding='utf-8')\n"
        "print('{\"state\": \"OPEN\", \"url\": \"https://example.test/pr/1\"}')\n"
    )

    completed = run_status(root, output_format="hook", env=gh_environment(tmp_path, source))

    assert completed.returncode == 0
    assert not marker.exists()
    assert "PR 状態: 未取得" in hook_line(completed.stdout, "foo")
