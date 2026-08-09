"""hooks の単体テスト(敵対レビュー P1-13 対応。NFR-019)。

各フックをサブプロセスとして起動し、stdin の JSON 入力に対する exit code を検証する。
exit 0 = 許可 / exit 2 = ブロック。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).parent.parent / ".claude" / "hooks"
REPO = str(Path(__file__).parent.parent)


def run_hook(name: str, payload) -> subprocess.CompletedProcess:
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOKS / name)],
        input=data.encode("utf-8"), capture_output=True, timeout=30,
    )


def bash(command: str, cwd: str = REPO) -> dict:
    return {"cwd": cwd, "tool_input": {"command": command}}


def filepath(path: str, cwd: str = REPO) -> dict:
    return {"cwd": cwd, "tool_input": {"file_path": path}}


# ---- git_guard -------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "git push --force origin main",
    "git push -f origin feature/x",
    "git push origin HEAD:develop",
    "git push origin develop",
    "git push origin feature/x:main",
    "git push origin refs/heads/develop",
])
def test_git_guard_blocks_protected_push(command):
    assert run_hook("git_guard.py", bash(command)).returncode == 2


def test_git_guard_allows_feature_push_and_commit():
    # このリポジトリのカレントブランチは feature/*(CI の detached HEAD でも保護名ではない)
    assert run_hook("git_guard.py", bash("git push -u origin feature/x")).returncode == 0
    assert run_hook("git_guard.py", bash("git commit -m test")).returncode == 0


def test_git_guard_fail_open_on_broken_json():
    assert run_hook("git_guard.py", "{not json").returncode == 0


def test_git_guard_blocks_with_japanese_in_command():
    # 日本語混在でも stdin の UTF-8 読みが機能し fail-open しないこと(Windows エンコーディング回帰)
    cmd = 'git commit -m "修正: 状況計算" && git push origin HEAD:develop  # 日本語コメント'
    assert run_hook("git_guard.py", bash(cmd)).returncode == 2


# ---- protect_paths ---------------------------------------------------------

@pytest.mark.parametrize("path", [
    r"C:\python_git\pitchlog\docs\legacy\foo.md",
    "C:/python_git/pitchlog/docs/legacy/foo.md",
    r"C:\python_git\pitchlog\DOCS\LEGACY\foo.md",   # 大文字(Windows は同一パス)
    "docs/legacy/foo.md",                            # 相対(cwd 起点で解決)
    r"C:\python_git\pitchlog\backend\.env",
    ".env.local",
])
def test_protect_paths_blocks(path):
    assert run_hook("protect_paths.py", filepath(path)).returncode == 2


@pytest.mark.parametrize("path", [
    "C:/python_git/pitchlog/docs/README.md",
    ".env.example",
    "backend/src/env_utils.py",
])
def test_protect_paths_allows(path):
    assert run_hook("protect_paths.py", filepath(path)).returncode == 0


# ---- codex_guard -----------------------------------------------------------

@pytest.mark.parametrize("command", [
    "codex exec -s workspace-write 'do it'",
    "codex review --base develop",
    "codex exec resume 0123abcd 'more'",
    "codex e 'quick'",
    'node "C:/plug/scripts/codex-companion.mjs" task "fix stuff"',
    "python .claude/scripts/codex_run.py implement plan.md - --yolo",  # ラッパーでも危険フラグは遮断
])
def test_codex_guard_blocks(command):
    assert run_hook("codex_guard.py", bash(command)).returncode == 2


@pytest.mark.parametrize("command", [
    "python .claude/scripts/codex_run.py research -",
    "python .claude/scripts/codex_run.py implement docs/features/x/plan.md -",
    'node "C:/plug/scripts/codex-companion.mjs" adversarial-review "--base develop"',
    "codex --version",
    "codex login status",
    "echo codex is a tool",
])
def test_codex_guard_allows(command):
    assert run_hook("codex_guard.py", bash(command)).returncode == 0


@pytest.mark.parametrize("command", [
    "/home/u/.nvm/versions/node/v22.18.0/bin/codex exec 'x'",  # 絶対パス起動(2周目 P0)
    "echo codex_run.py; codex exec 'x'",                        # 文字列混入によるチェーン迂回
    "npx @openai/codex exec 'x'",                               # npm 系ランチャー
    "pnpm dlx @openai/codex e 'x'",
    "bash -lc 'codex exec x'",                                  # 引用内の生起動(3周目 P0)
    "uv run bash <<'EOF'\ncodex exec --yolo x\nEOF",            # 非ラッパー heredoc は本文も検査(3周目 P0)
    '"codex" exec x',                                           # 引用符付き実行ファイル(4周目 P0)
    "'/usr/bin/codex' review foo",
    # 正規ラッパー heredoc の後ろに別 heredoc を連ねる迂回(4周目 P0)
    "python .claude/scripts/codex_run.py review normal - <<'EOF'\nok\nEOF\nbash <<'RUN'\ncodex exec x\nRUN",
    # 5周目 P0: # コメントで heredoc を無効化して正規形に見せる迂回
    "python .claude/scripts/codex_run.py bogus - # <<'EOF'\ncodex exec x\nEOF",
    # 5周目 P0: グローバルオプション前置・対話起動・大文字
    "codex -s workspace-write 'edit'",
    "codex --no-alt-screen exec x",
    "codex -c x=y exec x",
    "CODEX.CMD exec x",
    "node companion/codex-companion.mjs task 'do'",
])
def test_codex_guard_blocks_bypass_attempts(command):
    assert run_hook("codex_guard.py", bash(command)).returncode == 2


def test_codex_guard_ignores_heredoc_body_and_messages():
    # ヒアドキュメント本文は「データ」— プロンプト中の `codex exec` 文字列で誤ブロックしない
    heredoc = (
        "python .claude/scripts/codex_run.py review normal - <<'EOF'\n"
        "生の codex exec がブロックされることを確認する(--yolo も禁止)\n"
        "EOF"
    )
    assert run_hook("codex_guard.py", bash(heredoc)).returncode == 0
    # コミットメッセージ中の言及も誤ブロックしない
    assert run_hook("codex_guard.py", bash('git commit -m "codex 連携の修正"')).returncode == 0


# ---- secret_guard ----------------------------------------------------------

@pytest.mark.parametrize("command", [
    "cat .env",
    "node -e \"console.log(require('fs').readFileSync('.env','utf8'))\"",
    "uv run python -c \"print(open('.env').read())\"",
    "type .env.local",
    "cat backend/.env.example.local",   # 例外は exact .env.example のみ(3周目 P0)
    "cat .env.example.backup",
    "cat .env.example-prod",             # トークン境界での派生(4周目 P0)
    "cat .env.example~",
    "cat .env.example/secret",
    "cat .env.example,prod",             # comma はファイル名文字(5周目 P0)
    "cat .env.example,secret",
    "type .ENV",                         # 大小文字差(5周目 P0)
])
def test_secret_guard_blocks(command):
    assert run_hook("secret_guard.py", bash(command)).returncode == 2


def _load_guard_common():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "guard_common", Path(__file__).parent.parent / ".claude" / "hooks" / "guard_common.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_effective_command_canonical_vs_bypass():
    gc = _load_guard_common()
    # 正規形: 本文はデータ扱い(先頭行だけ返る)
    ok = "python .claude/scripts/codex_run.py review normal - <<'EOF'\ncodex exec x\nEOF"
    assert "codex exec" not in gc.effective_command(ok)
    # # コメントで heredoc を無効化 → 正規形でない → 全文
    bypass = "python .claude/scripts/codex_run.py bogus - # <<'EOF'\ncodex exec x\nEOF"
    assert "codex exec" in gc.effective_command(bypass)
    # 2つ目の heredoc → 全文
    dbl = ok + "\nbash <<'RUN'\ncodex exec x\nRUN"
    assert "codex exec" in gc.effective_command(dbl)
    # 非ラッパー → 全文
    non = "uv run bash <<'EOF'\ncodex exec x\nEOF"
    assert "codex exec" in gc.effective_command(non)


def test_shell_tokens_strips_quotes_and_comments():
    gc = _load_guard_common()
    assert gc.shell_tokens("git push origin 'HEAD:develop'") == ["git", "push", "origin", "HEAD:develop"]
    assert gc.shell_tokens("cat x # codex exec") == ["cat", "x"]
    assert gc.shell_tokens("echo 'unbalanced") is None  # 解析不能 → None(安全側判定は各ガード)


def test_guards_treat_wrapper_stdin_as_data():
    # 正規ラッパーへの heredoc 本文(プロンプト)はデータ — 本文中の .env / force push 記述で
    # 誤ブロックしない(3周目 P1: /finalize-doc が設計書全文を渡せること)
    body = (
        "python .claude/scripts/codex_run.py review adversarial - <<'EOF'\n"
        "設計書には .env の遮断と git push --force origin main の禁止が書かれている\n"
        "EOF"
    )
    assert run_hook("secret_guard.py", bash(body)).returncode == 0
    assert run_hook("git_guard.py", bash(body)).returncode == 0


@pytest.mark.parametrize("command", [
    "cat .env.example",
    "echo environment ready",
    "python -c \"import os; print(os.environ)\"",
    "uv run pytest tests/",
])
def test_secret_guard_allows(command):
    assert run_hook("secret_guard.py", bash(command)).returncode == 0


def make_repo(tmp_path, branch: str):
    """実ブランチ判定テスト用の一時リポジトリ(2周目 P1: 実リポジトリ非依存化)。"""
    repo = tmp_path / f"repo-{branch.replace('/', '-')}"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", branch, str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init", "-q"],
        check=True,
    )
    return repo


def test_git_guard_blocks_commit_on_protected_repo(tmp_path):
    repo = make_repo(tmp_path, "main")
    assert run_hook("git_guard.py", bash("git commit -m x", cwd=str(repo))).returncode == 2


def test_git_guard_resolves_dash_c_per_segment(tmp_path):
    # 後段セグメントの -C(保護ブランチ)も見落とさない(2周目 P0)
    protected = make_repo(tmp_path, "develop")
    feature = make_repo(tmp_path, "feature/x")
    cmd = f'git -C "{feature}" status && git -C "{protected}" commit -m x'
    assert run_hook("git_guard.py", bash(cmd, cwd=REPO)).returncode == 2


def test_git_guard_blocks_cd_git_compound():
    # cd 後はブランチ判定不能 — 保守的にブロック(git -C を使わせる)
    assert run_hook("git_guard.py", bash("cd ../somewhere && git commit -m x")).returncode == 2


def test_git_guard_allows_cd_without_protected_verb():
    assert run_hook("git_guard.py", bash("cd backend && git status")).returncode == 0


@pytest.mark.parametrize("command", [
    "git branch -D feature/x",
    "git branch --delete --force feature/x",   # -D の同義形も遮断(3周目 P1)
    "git branch --force --delete feature/x",
    "git branch -d -f feature/x",              # 分離した短縮形(4周目 P1)
    "git branch --delete -f feature/x",
    "git branch -df feature/x",                # 短縮クラスタ(5周目 P1)
    "git branch -fd feature/x",
])
def test_git_guard_blocks_force_branch_delete(command):
    assert run_hook("git_guard.py", bash(command)).returncode == 2


def test_git_guard_allows_safe_branch_delete_d_only():
    assert run_hook("git_guard.py", bash("git branch -d feature/x")).returncode == 0


@pytest.mark.parametrize("command", [
    "git push origin +feature/x",              # force refspec(4周目 P1)
    "git push origin +HEAD:develop",
    "git push -fu origin feature/x",           # 短縮クラスタ(5周目 P1)
    "git push -uf origin feature/x",
    "git push origin '+feature/x'",            # 引用符付き force refspec(5周目 P1)
])
def test_git_guard_blocks_force_refspec(command):
    assert run_hook("git_guard.py", bash(command)).returncode == 2


@pytest.mark.parametrize("command", [
    "git push origin 'HEAD:develop'",          # 引用符付き保護 refspec(5周目 P1)
    'git push origin "feature/x:main"',
])
def test_git_guard_blocks_quoted_protected_refspec(command):
    assert run_hook("git_guard.py", bash(command)).returncode == 2


def test_git_guard_allows_safe_branch_delete():
    assert run_hook("git_guard.py", bash("git branch -d feature/x")).returncode == 0


# ---- session_context -------------------------------------------------------

def test_session_context_emits_json():
    r = run_hook("session_context.py", {"cwd": REPO})
    assert r.returncode == 0
    out = json.loads(r.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"


# ---- codex_run.py(ラッパーの検証ロジック。codex 本体は起動しない経路のみ) ----

WRAPPER = Path(__file__).parent.parent / ".claude" / "scripts" / "codex_run.py"


def run_wrapper(args: list[str], stdin: str = "", cwd: str = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(WRAPPER), *args],
        input=stdin.encode("utf-8"), capture_output=True, timeout=30, cwd=cwd,
    )


def test_wrapper_rejects_missing_plan():
    r = run_wrapper(["implement", "docs/features/no-such/plan.md", "-"], "prompt")
    assert r.returncode == 2
    assert "見つからない".encode("utf-8") in r.stderr


def test_wrapper_rejects_unapproved_plan(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nfeature: x\nstatus: active\n承認: 未\n重さ分類: 通常\n"
        "worktree: ../wt\nbranch: feature/x\n---\n# 計画\n",
        encoding="utf-8",
    )
    r = run_wrapper(["implement", str(plan), "-"], "prompt")
    assert r.returncode == 2
    assert "未承認".encode("utf-8") in r.stderr


def test_wrapper_rejects_approved_plan_without_worktree(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nfeature: x\nstatus: active\n承認: 済(2026-08-07)\n重さ分類: 通常\n"
        "worktree: ../no-such-worktree\nbranch: feature/x\n---\n# 計画\n",
        encoding="utf-8",
    )
    r = run_wrapper(["implement", str(plan), "-"], "prompt")
    assert r.returncode == 2
    assert "worktree".encode("utf-8") in r.stderr


def test_wrapper_rejects_plan_without_steps(tmp_path):
    # 段階実装(設計書 6.1): 実装ステップの表が無い計画書は拒否する
    wt = tmp_path / "pitchlog-worktrees" / "feature-x"
    wt.mkdir(parents=True)
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nfeature: x\nstatus: active\n承認: 済(2026-08-07)\n重さ分類: 通常\n"
        f"worktree: {wt}\nbranch: feature/x\n---\n# 計画\n",
        encoding="utf-8",
    )
    r = run_wrapper(["implement", str(plan), "-"], "prompt")
    assert r.returncode == 2
    assert "実装ステップ".encode("utf-8") in r.stderr


def test_implement_argv_puts_exec_options_before_resume():
    # resume はサブコマンド — exec レベルオプションの後置は 0.146.1 で引数エラーになる
    import importlib.util

    spec = importlib.util.spec_from_file_location("codex_run", WRAPPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    base = ["-C", "/wt", "-s", "workspace-write"]
    argv = mod.implement_argv(base, "abc-123")
    assert argv.index("resume") > argv.index("-s")
    assert argv[-1] == "abc-123"
    assert mod.implement_argv(base, None) == ["exec", *base]


def test_wrapper_rejects_fast_outside_worktree():
    r = run_wrapper(["fast", "-"], "prompt", cwd=REPO)  # メインツリーは worktree でない
    assert r.returncode == 2


def test_wrapper_rejects_unregistered_worktree(tmp_path):
    # パス文字列の自己申告だけでは通さない — git worktree 登録を照合する(2周目 P0)
    wt = tmp_path / "pitchlog-worktrees" / "feature-x"
    wt.mkdir(parents=True)
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nfeature: x\nstatus: active\n承認: 済(2026-08-07)\n重さ分類: 通常\n"
        f"worktree: {wt}\nbranch: feature/x\n---\n# 計画\n\n"
        "### 実装ステップ(コミット単位)\n| 1 | x | y |\n",
        encoding="utf-8",
    )
    r = run_wrapper(["implement", str(plan), "-"], "prompt")
    assert r.returncode == 2
    assert "登録".encode("utf-8") in r.stderr


def test_wrapper_rejects_research_with_env(tmp_path):
    # live search 併用の /research は秘密ファイルのある場所で実行しない(2周目 P0)
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    r = run_wrapper(["research", "-"], "p", cwd=str(tmp_path))
    assert r.returncode == 2
    assert "秘密".encode("utf-8") in r.stderr


def test_wrapper_rejects_research_with_nested_env(tmp_path):
    # 直下だけでなく配下も再帰検査する(3周目 P0: backend/.env の見落とし)
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / ".env.local").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / ".env.example").write_text("KEY=", encoding="utf-8")  # 正本は除外される
    r = run_wrapper(["research", "-"], "p", cwd=str(tmp_path))
    assert r.returncode == 2
    assert "backend/.env.local".encode("utf-8") in r.stderr


def test_wrapper_research_scans_vcs_ignored_dirs(tmp_path):
    # .venv 等も除外しない(4/5周目 P0: 「cwd 配下に存在すれば拒否」が仕様)
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / ".env").write_text("SECRET=1", encoding="utf-8")
    r = run_wrapper(["research", "-"], "p", cwd=str(tmp_path))
    assert r.returncode == 2


def test_wrapper_research_fail_closed_on_unreadable_dir(tmp_path):
    # 走査失敗は握り潰さず fail-closed(5周目 P0)。読めないサブディレクトリを作る
    import os
    if os.geteuid() == 0:
        pytest.skip("root では権限エラーを作れない")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "sub").mkdir()
    os.chmod(locked, 0o000)
    try:
        r = run_wrapper(["research", "-"], "p", cwd=str(tmp_path))
        assert r.returncode == 2  # fail-closed(許可して継続しない)
    finally:
        os.chmod(locked, 0o755)


def test_wrapper_rejects_empty_step_table(tmp_path):
    # テンプレの空行(| 1 |  |  |)だけでは通さない — 記入済み行を構造検証(3周目 P1)
    wt = tmp_path / "pitchlog-worktrees" / "feature-x"
    wt.mkdir(parents=True)
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nfeature: x\nstatus: active\n承認: 済(2026-08-07)\n重さ分類: 通常\n"
        f"worktree: {wt}\nbranch: feature/x\n---\n# 計画\n\n"
        "### 実装ステップ(コミット単位)\n| # | ステップ | 合格条件 |\n| --- | --- | --- |\n| 1 |  |  |\n",
        encoding="utf-8",
    )
    r = run_wrapper(["implement", str(plan), "-"], "prompt")
    assert r.returncode == 2
    assert "実装ステップ".encode("utf-8") in r.stderr


def test_wrapper_rejects_worktree_in_different_repo(tmp_path):
    # git-common-dir 照合(4/5周目 P1): 同名 pitchlog-worktrees でも別リポジトリなら拒否
    other = tmp_path / "pitchlog-worktrees" / "feature-x"
    other.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "feature/x", str(other)], check=True)
    subprocess.run(
        ["git", "-C", str(other), "-c", "user.email=t@e.co", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "i", "-q"], check=True,
    )
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nfeature: x\nstatus: active\n承認: 済(2026-08-07)\n重さ分類: 通常\n"
        f"worktree: {other}\nbranch: feature/x\n---\n# 計画\n\n"
        "### 実装ステップ(コミット単位)\n| 1 | 何か作る | pytest green |\n",
        encoding="utf-8",
    )
    r = run_wrapper(["implement", str(plan), "-"], "prompt")
    assert r.returncode == 2
    assert "リポジトリ".encode("utf-8") in r.stderr


def test_wrapper_rejects_invalid_branch(tmp_path):
    # branch は feature/* | fix/* を必須とする(3周目 P1 — 空でも検査を省略しない)
    wt = tmp_path / "pitchlog-worktrees" / "feature-x"
    wt.mkdir(parents=True)
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nfeature: x\nstatus: active\n承認: 済(2026-08-07)\n重さ分類: 通常\n"
        f"worktree: {wt}\n---\n# 計画\n\n"
        "### 実装ステップ(コミット単位)\n| 1 | worktree照合 | pytest |\n",
        encoding="utf-8",
    )
    r = run_wrapper(["implement", str(plan), "-"], "prompt")
    assert r.returncode == 2
    assert "branch".encode("utf-8") in r.stderr


def test_security_overrides_pin_network_and_require_reason(monkeypatch):
    # 安全キーは config 層に依存せず毎回明示上書き。ネット例外は理由の記録が必須
    import importlib.util

    spec = importlib.util.spec_from_file_location("codex_run_sec", WRAPPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delenv("PITCHLOG_ALLOW_NET", raising=False)
    flags = mod.security_overrides(may_allow_net=True)
    assert "sandbox_workspace_write.network_access=false" in flags
    assert "sandbox_workspace_write.writable_roots=[]" in flags  # 書込境界も明示固定(3周目 P0)
    monkeypatch.setenv("PITCHLOG_ALLOW_NET", "1")
    monkeypatch.delenv("PITCHLOG_NET_REASON", raising=False)
    with pytest.raises(SystemExit):
        mod.security_overrides(may_allow_net=True)
    monkeypatch.setenv("PITCHLOG_NET_REASON", "依存追加の検証")
    assert "sandbox_workspace_write.network_access=true" in mod.security_overrides(may_allow_net=True)
    # read-only 系(research/review)は ALLOW_NET でも有効化しない
    assert "sandbox_workspace_write.network_access=false" in mod.security_overrides(may_allow_net=False)


def test_wrapper_rejects_review_base_flag():
    # --base は実装されていない — 受理したふりをして無視しない(敵対レビュー2周目 P1)
    r = run_wrapper(["review", "normal", "--base", "develop", "-"], "prompt")
    assert r.returncode == 2
    assert "--base".encode("utf-8") in r.stderr


def test_wrapper_rejects_unknown_mode():
    r = run_wrapper(["deploy"], "")
    assert r.returncode == 2
