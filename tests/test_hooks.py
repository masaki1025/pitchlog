"""hooks の単体テスト(敵対レビュー P1-13 対応。NFR-019)。

各フックをサブプロセスとして起動し、stdin の JSON 入力に対する exit code を検証する。
exit 0 = 許可 / exit 2 = ブロック。
"""
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).parent.parent / ".claude" / "hooks"
SETTINGS = Path(__file__).parent.parent / ".claude" / "settings.json"
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


def load_git_guard(monkeypatch: pytest.MonkeyPatch):
    """テスト用に git_guard.py をモジュールとして読み込む。"""
    script = HOOKS / "git_guard.py"
    monkeypatch.syspath_prepend(str(HOOKS))
    spec = importlib.util.spec_from_file_location("git_guard_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


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


@pytest.mark.parametrize("command", [
    "git push origin --delete feature/x",
    "git push origin HEAD:feature/x",
    "git push origin feature/x:feature/x",
    "git push -u origin fix/x",
    "git push origin feature/a",
    "git push --set-upstream origin feature/x",
    "git push origin feature/a feature/b",
])
def test_git_guard_allows_explicit_nonprotected_push_on_protected_branch(tmp_path, command):
    # H-2: カレントが develop でも、宛先を非保護と証明できる push は許可する。
    repo = make_repo(tmp_path, "develop")
    assert run_hook("git_guard.py", bash(command, cwd=str(repo))).returncode == 0


@pytest.mark.parametrize("command", [
    "git log --grep merge",
    "git help push",
])
def test_git_guard_allows_git_verbs_in_argument_position(tmp_path, command):
    # H-11: merge / push は実サブコマンドではなく引数であり、develop 上でも遮断しない。
    repo = make_repo(tmp_path, "develop")
    assert run_hook("git_guard.py", bash(command, cwd=str(repo))).returncode == 0


@pytest.mark.parametrize("command", [
    'echo "git push; ls"',
    "git log --oneline -5",
])
def test_git_guard_allows_quoted_text_and_read_only_command(command):
    assert run_hook("git_guard.py", bash(command)).returncode == 0


@pytest.mark.parametrize(("command", "message"), [
    ("git commit -m x", "保護ブランチへの直接操作"),
    ("git push origin HEAD:develop", "保護ブランチ(main/develop)宛て"),
    ("git push --force origin feature/x", "force push"),
    ("git push", "宛先を静的に解決できません"),
    ("git push origin", "宛先を静的に解決できません"),
    ("git push origin HEAD", "宛先を静的に解決できません"),
    ("git push --all origin", "宛先を静的に解決できません"),
    ("git push --mirror origin", "宛先を静的に解決できません"),
    ("git -c foo=bar commit -m x", "保護ブランチへの直接操作"),
])
def test_git_guard_blocks_step3_protected_or_unresolved_operation(tmp_path, command, message):
    # 計画書 7 節の負例 9 件。push の宛先未解決はカレントに関係なく遮断する。
    repo = make_repo(tmp_path, "develop")
    result = run_hook("git_guard.py", bash(command, cwd=str(repo)))
    assert result.returncode == 2
    assert message in result.stderr.decode("utf-8")


def test_git_guard_allows_feature_branch_commit(tmp_path):
    repo = make_repo(tmp_path, "feature/x")
    assert run_hook("git_guard.py", bash("git commit -m test", cwd=str(repo))).returncode == 0


def test_git_guard_blocks_branch_resolution_failure_after_successful_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """worktree プローブ成功後のブランチ解決失敗は理由付きで遮断する。"""
    repo = make_repo(tmp_path, "feature/x")
    module = load_git_guard(monkeypatch)

    def fail_branch_resolution(args, **kwargs):
        if args == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(args, 0, stdout="true\n", stderr="")
        assert args == ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="解決失敗")

    monkeypatch.setattr(module.subprocess, "run", fail_branch_resolution)

    result = module.check_git_invocation(
        module.GitInvocation("commit", str(repo), []), cd_seen=False,
    )

    assert result == 2
    assert "現在のブランチを解決できませんでした" in capsys.readouterr().err


def test_git_guard_allows_existing_non_repository_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Git 管理外を積極確認できる既存 cwd では commit 判定を許可する。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    # 親の共有 tmp が持つ `.git` を拾わないよう、Git 自身の探索境界を fixture に固定する。
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    result = run_hook("git_guard.py", bash("git commit -m x", cwd=str(outside)))

    assert result.returncode == 0


def test_git_guard_blocks_broken_git_metadata(tmp_path: Path):
    """壊れた `.git` は非リポジトリと推定せず、安全側で遮断する。"""
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / ".git").mkdir()

    result = run_hook("git_guard.py", bash("git commit -m x", cwd=str(broken)))

    assert result.returncode == 2
    assert "現在のブランチを解決できませんでした" in result.stderr.decode("utf-8")


def test_git_guard_blocks_nonexistent_cwd(tmp_path: Path):
    """存在しない cwd はブランチ判定不能として安全側で遮断する。"""
    missing = tmp_path / "missing"

    result = run_hook("git_guard.py", bash("git commit -m x", cwd=str(missing)))

    assert result.returncode == 2
    assert "現在のブランチを解決できませんでした" in result.stderr.decode("utf-8")


def test_git_guard_blocks_push_when_any_destination_is_protected(tmp_path):
    repo = make_repo(tmp_path, "develop")
    result = run_hook("git_guard.py", bash("git push origin feature/a develop", cwd=str(repo)))
    assert result.returncode == 2
    assert "保護ブランチ(main/develop)宛て" in result.stderr.decode("utf-8")


def test_settings_json_hook_wiring():
    """settings.json のフック設定が実在するスクリプトを参照することを確認する。"""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))

    for event_name, entries in settings["hooks"].items():
        for entry in entries:
            for hook in entry["hooks"]:
                command = hook["command"]
                scripts = re.findall(r"\.claude/hooks/([A-Za-z0-9_-]+\.py)", command)
                assert scripts, f"{event_name} のフックコマンドにスクリプト参照がない: {command}"
                for script in scripts:
                    assert (HOOKS / script).is_file(), (
                        f"{event_name} のフックコマンドが存在しないスクリプトを参照している: "
                        f"{script}"
                    )


def test_git_guard_fail_open_on_broken_json():
    assert run_hook("git_guard.py", "{not json").returncode == 0


def test_git_guard_blocks_with_japanese_in_command():
    # 日本語混在でも stdin の UTF-8 読みが機能し fail-open しないこと(Windows エンコーディング回帰)
    cmd = 'git commit -m "修正: 状況計算" && git push origin HEAD:develop  # 日本語コメント'
    assert run_hook("git_guard.py", bash(cmd)).returncode == 2


def test_git_guard_parses_global_option_before_merge(tmp_path):
    repo = make_repo(tmp_path, "develop")
    assert run_hook("git_guard.py", bash("git --no-pager merge x", cwd=str(repo))).returncode == 2


@pytest.mark.parametrize("global_option", [
    "-c foo=bar",
    "-C .",
    "--git-dir /tmp",
    "--work-tree /tmp",
    "--namespace team-a",
    "--exec-path /tmp",
    "--git-dir=/tmp",
    "--work-tree=/tmp",
    "--namespace=team-a",
    "--exec-path=/tmp",
])
def test_git_guard_skips_value_taking_global_options(tmp_path, global_option):
    # 値を取るグローバルオプションの値をサブコマンドと誤認しない。
    repo = make_repo(tmp_path, "develop")
    command = f"git {global_option} log --grep merge"
    assert run_hook("git_guard.py", bash(command, cwd=str(repo))).returncode == 0


@pytest.mark.parametrize("global_option", [
    "--no-pager",
    "--paginate",
    "--bare",
    "--literal-pathspecs",
])
def test_git_guard_skips_flag_global_options(tmp_path, global_option):
    repo = make_repo(tmp_path, "develop")
    command = f"git {global_option} log --grep merge"
    assert run_hook("git_guard.py", bash(command, cwd=str(repo))).returncode == 0


@pytest.mark.parametrize("command", [
    "git commit -m x",
    "git merge x",
    "git rebase x",
])
def test_git_guard_keeps_current_branch_check_for_mutating_verbs(tmp_path, command):
    repo = make_repo(tmp_path, "develop")
    assert run_hook("git_guard.py", bash(command, cwd=str(repo))).returncode == 2


def test_git_guard_uses_last_dash_c_and_relative_path(tmp_path):
    # 2 個目の相対 -C は 1 個目の cwd を基準に解決され、develop を見つけなければならない。
    repo = make_repo(tmp_path, "develop")
    command = f'git -C "{tmp_path}" -C "{repo.name}" commit -m x'
    assert run_hook("git_guard.py", bash(command, cwd=REPO)).returncode == 2


def test_git_guard_checks_shell_c_body_on_protected_branch(tmp_path):
    repo = make_repo(tmp_path, "develop")
    command = "bash -lc 'echo ok; git commit -m x'"
    assert run_hook("git_guard.py", bash(command, cwd=str(repo))).returncode == 2


@pytest.mark.parametrize("command", [
    "git --unknown-global-option commit -m x",
    "git -c invalid commit -m x",
    "git -c alias.p=push p origin HEAD:develop",
])
def test_git_guard_blocks_unparseable_git_invocation(command):
    # 未知のグローバルオプションと alias 経由は解析不能として fail-closed にする。
    result = run_hook("git_guard.py", bash(command))
    assert result.returncode == 2
    assert "解析できませんでした" in result.stderr.decode("utf-8")


def test_git_guard_blocks_unparseable_top_level_command():
    command = 'git commit -m ' + chr(34) + "unclosed"
    assert run_hook("git_guard.py", bash(command)).returncode == 2


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
    # ラッパーでも危険フラグは遮断
    "python .claude/scripts/codex_run.py implement plan.md - --yolo",
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
    'grep -nE "codex|claude" .claude/hooks/codex_guard.py',
    "grep -n 'codex; ls' README.md",
    'echo "codex & background" > /tmp/x',
])
def test_codex_guard_allows_quoted_separators(command):
    assert run_hook("codex_guard.py", bash(command)).returncode == 0


@pytest.mark.parametrize(("command", "expected"), [
    ("codex exec 'x'", 2),
    ("bash -lc 'echo ok; codex exec x'", 2),
    ("python3 .claude/scripts/codex_run.py review normal -", 0),
])
def test_codex_guard_uses_segments_for_shell_c(command, expected):
    assert run_hook("codex_guard.py", bash(command)).returncode == expected


def test_codex_guard_blocks_unparseable_top_level_command():
    command = 'codex exec ' + chr(34) + 'unclosed'
    assert run_hook("codex_guard.py", bash(command)).returncode == 2


@pytest.mark.parametrize("command", [
    "/home/u/.nvm/versions/node/v22.18.0/bin/codex exec 'x'",  # 絶対パス起動(2周目 P0)
    "echo codex_run.py; codex exec 'x'",                        # 文字列混入によるチェーン迂回
    "npx @openai/codex exec 'x'",                               # npm 系ランチャー
    "pnpm dlx @openai/codex e 'x'",
    "bash -lc 'codex exec x'",                                  # 引用内の生起動(3周目 P0)
    # 非ラッパー heredoc は本文も検査(3周目 P0)
    "uv run bash <<'EOF'\ncodex exec --yolo x\nEOF",
    '"codex" exec x',                                           # 引用符付き実行ファイル(4周目 P0)
    "'/usr/bin/codex' review foo",
    # 正規ラッパー heredoc の後ろに別 heredoc を連ねる迂回(4周目 P0)
    (
        "python .claude/scripts/codex_run.py review normal - <<'EOF'\nok\nEOF\n"
        "bash <<'RUN'\ncodex exec x\nRUN"
    ),
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
    assert gc.shell_tokens(
        "git push origin 'HEAD:develop'"
    ) == ["git", "push", "origin", "HEAD:develop"]
    assert gc.shell_tokens("cat x # codex exec") == ["cat", "x"]
    assert gc.shell_tokens("echo 'unbalanced") is None  # 解析不能 → None(安全側判定は各ガード)


@pytest.mark.parametrize("command", [
    'grep -nE "codex|claude" file',
    "grep -n 'codex; ls' README.md",
    'echo "codex & background" > /tmp/x',
])
def test_shell_segments_does_not_split_quoted_separators(command):
    gc = _load_guard_common()
    assert gc.shell_segments(command) == [command]


@pytest.mark.parametrize(("command", "expected"), [
    ("a && b", ["a ", " b"]),
    ("a | b", ["a ", " b"]),
    ("a; b", ["a", " b"]),
    ("a\nb", ["a", "b"]),
    ("a & b", ["a ", " b"]),
])
def test_shell_segments_splits_unquoted_separators(command, expected):
    gc = _load_guard_common()
    assert gc.shell_segments(command) == expected


@pytest.mark.parametrize(("command", "expected"), [
    ("grep -n a#b file; codex exec x", ["grep -n a#b file", " codex exec x"]),
    ("curl http://x#frag; codex exec x", ["curl http://x#frag", " codex exec x"]),
    ("git log a#b; git commit -m x", ["git log a#b", " git commit -m x"]),
])
def test_shell_segments_splits_after_embedded_hash(command, expected):
    gc = _load_guard_common()
    assert gc.shell_segments(command) == expected


def test_shell_segments_treats_word_initial_hash_as_comment():
    gc = _load_guard_common()
    command = "echo hi # note; codex exec x"
    assert gc.shell_segments(command) == [command]


def test_shell_segments_returns_none_for_unparseable_command():
    gc = _load_guard_common()
    assert gc.shell_segments("echo 'unbalanced") is None


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

def make_feature_status_worktree(
    tmp_path: Path,
    frontmatter_prefix: str = "",
) -> tuple[Path, Path]:
    """feature_status.py を呼ぶための feature worktree を作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        frontmatter_prefix: status 行より前に置く frontmatter の追加行。

    Returns:
        develop のメインリポジトリと feature/foo worktree の組。
    """
    root = make_repo(tmp_path, "develop")
    subprocess.run(
        ["git", "-C", str(root), "update-ref", "refs/remotes/origin/develop", "HEAD"],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    worktree = tmp_path / "feature-foo"
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "worktree",
            "add",
            "-q",
            "-b",
            "feature/foo",
            str(worktree),
        ],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    plan = worktree / "docs" / "features" / "foo" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "\n".join(
            [
                "---",
                "feature: foo",
                frontmatter_prefix,
                "status: active",
                "承認: 済",
                "branch: feature/foo",
                "---",
                "# 計画",
                "### 実装ステップ(コミット単位)",
                "| # | ステップ | 合格条件 |",
                "| --- | --- | --- |",
                "| 1 | 実装 | pytest |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root, worktree


def session_context_additional_context(completed: subprocess.CompletedProcess) -> str:
    """SessionStart フックの JSON 出力から additionalContext を取り出す。

    Args:
        completed: session_context.py を起動した結果。

    Returns:
        フックが注入した additionalContext。
    """
    output = json.loads(completed.stdout.decode("utf-8"))
    return output["hookSpecificOutput"]["additionalContext"]


def load_session_context():
    """テスト用に session_context.py をモジュールとして読み込む。"""
    script = HOOKS / "session_context.py"
    spec = importlib.util.spec_from_file_location("session_context_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_session_context_directly(module, cwd: Path, monkeypatch, capsys) -> str:
    """モジュール直接実行で子プロセス故障時の注入内容を取得する。

    Args:
        module: 読み込み済みの session_context モジュール。
        cwd: SessionStart 入力へ渡す基準ディレクトリ。
        monkeypatch: pytest の差し替え機構。
        capsys: pytest の標準出力捕捉機構。

    Returns:
        フックが注入した additionalContext。
    """
    payload = json.dumps({"cwd": str(cwd)}).encode("utf-8")
    stdin = io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stdin)
    assert module.main() == 0
    output = json.loads(capsys.readouterr().out)
    return output["hookSpecificOutput"]["additionalContext"]


def test_session_context_emits_json():
    r = run_hook("session_context.py", {"cwd": REPO})
    assert r.returncode == 0
    out = json.loads(r.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_session_context_injects_feature_status_hook_summary(tmp_path: Path):
    """feature_status.py の 1 feature 1 行要約を追加文脈へ注入する。"""
    root, _ = make_feature_status_worktree(tmp_path)

    completed = run_hook("session_context.py", {"cwd": str(root)})

    assert completed.returncode == 0
    context = session_context_additional_context(completed)
    feature_lines = [line for line in context.splitlines() if line.startswith("foo(")]
    assert len(feature_lines) == 1
    assert "実装前(全 1 ステップ)" in feature_lines[0]
    assert "PR 状態: 未取得" in feature_lines[0]


def test_session_context_detects_frontmatter_longer_than_800_characters(
    tmp_path: Path,
):
    """status 行が 800 文字以降でも feature_status.py の解析結果を注入する。"""
    root, _ = make_feature_status_worktree(tmp_path, "説明: " + "x" * 900)

    completed = run_hook("session_context.py", {"cwd": str(root)})

    assert completed.returncode == 0
    context = session_context_additional_context(completed)
    assert any(line.startswith("foo(feature/foo)") for line in context.splitlines())


def test_session_context_reports_frontmatter_larger_than_8kib(tmp_path: Path):
    """8KiB を超える frontmatter を解析失敗としてそのまま注入する。"""
    root, _ = make_feature_status_worktree(tmp_path, "説明: " + "x" * (8 * 1024))

    completed = run_hook("session_context.py", {"cwd": str(root)})

    assert completed.returncode == 0
    context = session_context_additional_context(completed)
    assert "foo(feature/foo) / 未取得(frontmatter 解析失敗)" in context


def test_session_context_handles_cwd_outside_repository(tmp_path: Path):
    """リポジトリ外 cwd でも未取得を注入して終了コード 0 を維持する。"""
    outside = tmp_path / "outside"
    outside.mkdir()

    completed = run_hook("session_context.py", {"cwd": str(outside)})

    assert completed.returncode == 0
    context = session_context_additional_context(completed)
    assert "進行中 feature: 未取得(worktree 列挙失敗)" in context


def test_session_context_omits_feature_line_when_no_active_feature(tmp_path: Path):
    """正常に feature が 0 件なら現在地の行を増やさない。"""
    root = make_repo(tmp_path, "develop")

    completed = run_hook("session_context.py", {"cwd": str(root)})

    assert completed.returncode == 0
    context = session_context_additional_context(completed)
    assert "進行中 feature:" not in context


def test_session_context_reports_child_nonzero_as_derivation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """feature_status.py の非 0 終了を導出失敗として明示する。"""
    module = load_session_context()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(module, "FEATURE_STATUS_SCRIPT", tmp_path / "missing.py")

    context = run_session_context_directly(module, outside, monkeypatch, capsys)

    assert "進行中 feature: 未取得(導出失敗)" in context


def test_session_context_reports_child_timeout_as_derivation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """feature_status.py のタイムアウトを短時間で導出失敗として明示する。"""
    module = load_session_context()
    outside = tmp_path / "outside"
    outside.mkdir()
    slow_script = tmp_path / "slow_feature_status.py"
    slow_script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    monkeypatch.setattr(module, "FEATURE_STATUS_SCRIPT", slow_script)
    monkeypatch.setattr(module, "FEATURE_STATUS_TIMEOUT_SECONDS", 0.05)

    context = run_session_context_directly(module, outside, monkeypatch, capsys)

    assert "進行中 feature: 未取得(導出失敗)" in context


# ---- codex_run.py(ラッパーの検証ロジック。codex 本体は起動しない経路のみ) ----

WRAPPER = Path(__file__).parent.parent / ".claude" / "scripts" / "codex_run.py"


def run_wrapper(args: list[str], stdin: str = "", cwd: str = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(WRAPPER), *args],
        input=stdin.encode("utf-8"), capture_output=True, timeout=30, cwd=cwd,
    )


def write_wrapper_plan(tmp_path: Path, frontmatter_lines: list[str]) -> Path:
    """ラッパーの前段検証用 plan を書き出す。"""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "\n".join(["---", *frontmatter_lines, "---", "# 計画", ""]),
        encoding="utf-8",
    )
    return plan


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


def test_wrapper_rejects_in_review_plan_with_return_instruction(tmp_path: Path):
    """in-review は承認済みでも /pr の差し戻し手順へ誘導する。"""
    plan = write_wrapper_plan(
        tmp_path,
        [
            "feature: x",
            "status: in-review",
            "承認: 済(2026-08-10・確認者)",
            "重さ分類: 通常",
            f"worktree: {REPO}",
            "branch: feature/codex-plan-status-guard",
        ],
    )

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert "差し戻し".encode("utf-8") in r.stderr


def test_wrapper_rejects_in_review_before_approval_and_resume(tmp_path: Path):
    """status は承認・resume の検証より先に拒否する。"""
    plan = write_wrapper_plan(
        tmp_path,
        [
            "feature: x",
            "status: in-review",
            "承認: 未",
            "重さ分類: 通常",
            f"worktree: {REPO}",
            "branch: feature/codex-plan-status-guard",
        ],
    )

    r = run_wrapper(["implement", str(plan), "--resume", "-"], "prompt")

    assert r.returncode == 2
    assert "差し戻し".encode("utf-8") in r.stderr
    assert "未承認".encode("utf-8") not in r.stderr
    assert "セッション".encode("utf-8") not in r.stderr


def test_wrapper_rejects_plan_without_status(tmp_path: Path):
    plan = write_wrapper_plan(tmp_path, ["feature: x", "承認: 未"])

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert b"status" in r.stderr


def test_wrapper_rejects_duplicate_status(tmp_path: Path):
    plan = write_wrapper_plan(
        tmp_path,
        ["feature: x", "status: active", "status: in-review", "承認: 未"],
    )

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert b"status" in r.stderr
    assert "重複".encode("utf-8") in r.stderr


def test_wrapper_rejects_invalid_status_value(tmp_path: Path):
    plan = write_wrapper_plan(tmp_path, ["feature: x", "status: merged", "承認: 未"])

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert b"status" in r.stderr


@pytest.mark.parametrize("status_line", ["status : active", "status: activeX"])
def test_wrapper_rejects_malformed_status(tmp_path: Path, status_line: str):
    plan = write_wrapper_plan(tmp_path, ["feature: x", status_line, "承認: 未"])

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert b"status" in r.stderr


def test_wrapper_rejects_duplicate_status_after_false_frontmatter_terminator(tmp_path: Path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nfeature: x\nstatus: active\n--- 任意文字列\nstatus: active\n承認: 未\n---\n# 計画\n",
        encoding="utf-8",
    )

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert b"status" in r.stderr
    assert "重複".encode("utf-8") in r.stderr
    assert "未承認".encode("utf-8") not in r.stderr
    assert b"worktree" not in r.stderr


def test_wrapper_accepts_active_status_with_comment(tmp_path: Path):
    plan = write_wrapper_plan(
        tmp_path,
        ["feature: x", "status: active # 行末コメント", "承認: 未"],
    )

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert "未承認".encode("utf-8") in r.stderr
    assert b"status" not in r.stderr
    assert "差し戻し".encode("utf-8") not in r.stderr


def test_wrapper_accepts_active_status_with_crlf_plan(tmp_path: Path):
    plan = tmp_path / "plan.md"
    plan.write_bytes(
        "\r\n".join(["---", "feature: x", "status: active", "承認: 未", "---", "# 計画", ""])
        .encode("utf-8")
    )

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert "未承認".encode("utf-8") in r.stderr
    assert b"status" not in r.stderr
    assert "差し戻し".encode("utf-8") not in r.stderr


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("--- ", "---"),
        ("---\t", "---"),
        ("---", "--- "),
        ("---", "---\t"),
    ],
    ids=["start-space", "start-tab", "end-space", "end-tab"],
)
def test_wrapper_rejects_frontmatter_delimiter_with_trailing_whitespace(
    tmp_path: Path,
    start: str,
    end: str,
):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "\n".join([start, "feature: x", "status: active", "承認: 未", end, "# 計画", ""]),
        encoding="utf-8",
    )

    r = run_wrapper(["implement", str(plan), "-"], "prompt")

    assert r.returncode == 2
    assert b"frontmatter" in r.stderr
    assert "未承認".encode("utf-8") not in r.stderr


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


def test_wrapper_rejects_fast_outside_worktree(tmp_path):
    # worktree 名を含まない一時ディレクトリに固定し、実行場所に依存させない
    r = run_wrapper(["fast", "-"], "prompt", cwd=str(tmp_path))
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
        "### 実装ステップ(コミット単位)\n"
        "| # | ステップ | 合格条件 |\n"
        "| --- | --- | --- |\n"
        "| 1 |  |  |\n",
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
    assert (
        "sandbox_workspace_write.network_access=true"
        in mod.security_overrides(may_allow_net=True)
    )
    # read-only 系(research/review)は ALLOW_NET でも有効化しない
    assert (
        "sandbox_workspace_write.network_access=false"
        in mod.security_overrides(may_allow_net=False)
    )


def test_wrapper_rejects_review_base_flag():
    # --base は実装されていない — 受理したふりをして無視しない(敵対レビュー2周目 P1)
    r = run_wrapper(["review", "normal", "--base", "develop", "-"], "prompt")
    assert r.returncode == 2
    assert "--base".encode("utf-8") in r.stderr


def test_wrapper_rejects_unknown_mode():
    r = run_wrapper(["deploy"], "")
    assert r.returncode == 2
