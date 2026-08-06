"""main/develop 保護フック(PreToolUse / Bash|PowerShell)。

設計書 6.2/8.3: 保護ブランチ上での commit/merge/rebase、保護ブランチへの push
(カレントブランチ経由・refspec 経由の両方)、force push を検知してブロックする(exit 2)。
判定できない場合は通す(fail-open)。敵対レビュー P1-8 対応: refspec 検査・空白入り -C パス対応。
2周目 P0 対応: 複合コマンドをセグメント単位で評価(-C を個別解決)し、
`cd` と git 操作の複合はブランチ判定不能として保守的にブロックする。
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

from guard_common import effective_command

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


def extract_c_path(command: str) -> str | None:
    m = re.search(r"-C\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", command)
    if not m:
        return None
    return m.group(1) or m.group(2) or m.group(3)


def push_targets_protected(command: str) -> bool:
    """push の宛先 ref が保護ブランチかを引数から推定する(HEAD:develop 等)。"""
    m = re.search(r"\bpush\b(.*)$", command)
    if not m:
        return False
    tokens = [t for t in m.group(1).split() if not t.startswith("-")]
    # tokens[0] は通常リモート名。以降(および単独指定)を refspec として検査する
    for tok in tokens:
        dest = tok.split(":", 1)[1] if ":" in tok else tok
        dest = dest.removeprefix("refs/heads/")
        if dest in PROTECTED:
            return True
    return False


def main() -> int:
    try:
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む(fail-open 防止)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    command = str(data.get("tool_input", {}).get("command", ""))
    if "git" not in command:
        return 0
    # 正規ラッパーへの stdin(プロンプト本文)はデータ — 本文中の git 記述で誤ブロックしない(3周目 P1)
    command = effective_command(command)
    if "git" not in command:
        return 0

    if re.search(r"git\b[^\n|;&]*\bpush\b[^\n|;&]*(--force\b|--force-with-lease\b|\s-f\b)", command):
        print("ブロック: force push は禁止です(設計書 8.2/8.3)。", file=sys.stderr)
        return 2

    # ブランチの強制削除は同義オプションも含めて遮断(3周目 P1 — settings の deny は語順・別名で迂回可能)
    if re.search(r"\bgit\b[^\n|;&]*\bbranch\b", command) and (
        re.search(r"\s-D\b", command)
        or (re.search(r"--delete\b", command) and re.search(r"--force\b", command))
    ):
        print(
            "ブロック: ブランチの強制削除(-D / --delete --force)は禁止です"
            "(未マージ履歴の喪失防止 — 設計書 8.2)。安全な -d を使うか、人間が実行してください。",
            file=sys.stderr,
        )
        return 2

    if re.search(r"git\b[^\n|;&]*\bpush\b", command) and push_targets_protected(command):
        print(
            "ブロック: 保護ブランチ(main/develop)への push は禁止です。"
            "PR 経由でマージしてください(設計書 6.2)。",
            file=sys.stderr,
        )
        return 2

    if not re.search(r"git\b[^\n|;&]*\b(commit|merge|push|rebase)\b", command):
        return 0

    # 複合コマンド対応(2周目 P0): セグメントごとに実行ディレクトリを解決する
    cd_seen = False
    for seg in re.split(r"&&|\|\||\||;|\n", command):
        if re.match(r"\s*cd\b", seg):
            cd_seen = True
            continue
        if not re.search(r"\bgit\b.*\b(commit|merge|push|rebase)\b", seg):
            continue
        if cd_seen:
            print(
                "ブロック: `cd` と git 操作の複合コマンドはブランチ判定ができません。"
                "`git -C <path>` を使うか、コマンドを分けて実行してください(設計書 8.3)。",
                file=sys.stderr,
            )
            return 2
        cwd = extract_c_path(seg) or data.get("cwd", "")
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
