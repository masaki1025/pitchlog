"""Codex 実行経路の強制フック(PreToolUse / Bash|PowerShell)。

敵対レビュー P0-2 対応: Codex の実行は `.claude/scripts/codex_run.py` ラッパー
(計画承認・worktree・sandbox・モデル対応表を検証)のみに限定する。
- 生の `codex exec` / `codex review` / `codex resume` はブロック
- プラグイン companion の task モード(計画ゲートを迂回する書き込み実行)はブロック
- 危険フラグ(danger-full-access / --yolo 等)は無条件ブロック(設計書 12.1)
- 情報系(codex --version / login / features 等)は許可
"""
import json
import re
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
DIRECT_CODEX = re.compile(r"(?:^|[\s;|&])codex(?:\.exe|\.cmd)?\s+(exec|review|resume|e)\b")


def main() -> int:
    try:
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む(fail-open 防止)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
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

    if "codex_run.py" in command:
        return 0  # ラッパー経由 — 検証はラッパー自身が行う

    if "codex-companion.mjs" in command:
        if re.search(r"codex-companion\.mjs\"?\s+task\b", command):
            print(
                "ブロック: プラグインの task モードは計画書ゲートを迂回します。"
                "実装委任は /implement(codex_run.py 経由)を使ってください(設計書 6.1/12.1)。",
                file=sys.stderr,
            )
            return 2
        return 0  # review / adversarial-review / status 等は read-only 系のため許可

    if DIRECT_CODEX.search(command):
        print(
            "ブロック: 生の codex 実行は禁止です。"
            "python .claude/scripts/codex_run.py <implement|fast|research|review> を使ってください"
            "(設計書 12.1 — 計画承認・worktree・sandbox の検証をラッパーが担う)。",
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
