"""main/develop 直接コミット防止フック(PreToolUse / Bash)。

設計書 6.2/8.3: Git Flow の機構化。保護ブランチ上での commit/merge/push/rebase と、
force push を検知してブロックする(exit 2)。判定できない場合は通す(fail-open)。
"""
import json
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PROTECTED = {"main", "develop"}


def current_branch(cwd: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd or None, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    command = str(data.get("tool_input", {}).get("command", ""))
    if "git" not in command:
        return 0

    # force push は常にブロック
    if re.search(r"git\b[^\n|;&]*\bpush\b[^\n|;&]*(--force\b|--force-with-lease\b|\s-f\b)", command):
        print("ブロック: force push は禁止です(設計書 8.2/8.3)。", file=sys.stderr)
        return 2

    if not re.search(r"git\b[^\n|;&]*\b(commit|merge|push|rebase)\b", command):
        return 0

    # `git -C <path>` があればそのパスを、なければセッションの cwd を対象にする
    m = re.search(r"git\s+-C\s+\"?([^\s\"]+)\"?", command)
    cwd = m.group(1) if m else data.get("cwd", "")
    branch = current_branch(cwd)
    if branch in PROTECTED:
        print(
            f"ブロック: {branch} ブランチへの直接操作は禁止です。"
            "develop から feature/* を切って PR 経由でマージしてください(/task-start)。",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
