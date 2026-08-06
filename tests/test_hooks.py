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


# ---- secret_guard ----------------------------------------------------------

@pytest.mark.parametrize("command", [
    "cat .env",
    "node -e \"console.log(require('fs').readFileSync('.env','utf8'))\"",
    "uv run python -c \"print(open('.env').read())\"",
    "type .env.local",
])
def test_secret_guard_blocks(command):
    assert run_hook("secret_guard.py", bash(command)).returncode == 2


@pytest.mark.parametrize("command", [
    "cat .env.example",
    "echo environment ready",
    "python -c \"import os; print(os.environ)\"",
    "uv run pytest tests/",
])
def test_secret_guard_allows(command):
    assert run_hook("secret_guard.py", bash(command)).returncode == 0


# ---- session_context -------------------------------------------------------

def test_session_context_emits_json():
    r = run_hook("session_context.py", {"cwd": REPO})
    assert r.returncode == 0
    out = json.loads(r.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
