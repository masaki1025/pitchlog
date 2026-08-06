"""Codex 危険フラグの遮断フック(PreToolUse / Bash)。

設計書 12.1: danger-full-access / --dangerously-bypass-approvals-and-sandbox(--yolo)を
含む codex 実行をブロックする。network_access=true は許可するが人間に顕在化する。
"""
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

FORBIDDEN = [
    "danger-full-access",
    "--dangerously-bypass-approvals-and-sandbox",
    "--yolo",
]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    command = str(data.get("tool_input", {}).get("command", ""))
    if "codex" not in command:
        return 0
    for flag in FORBIDDEN:
        if flag in command:
            print(
                f"ブロック: {flag} は本プロジェクトで使用禁止です"
                "(設計書 12.1 の sandbox 固定ポリシー)。",
                file=sys.stderr,
            )
            return 2
    if "network_access=true" in command:
        out = {
            "systemMessage": (
                "注意: Codex をネットワーク有効で実行します"
                "(12.1 の例外運用 — 実行前に理由の報告が必要です)"
            )
        }
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
