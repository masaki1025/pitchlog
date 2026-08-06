"""Codex 実行経路の強制フック(PreToolUse / Bash|PowerShell)。

敵対レビュー P0-2・2周目 P0 対応: Codex の実行は `.claude/scripts/codex_run.py`
ラッパー(計画承認・worktree・sandbox・モデル対応表を検証)のみに限定する。

設計(2周目で substring 許可を全廃・3周目でデータ扱いを正規ラッパー stdin に限定):
- 「コマンド文字列に codex_run.py を含めば許可」はしない — 生起動の**検出**に一本化し、
  ラッパー呼び出しは生起動トークンを含まないため自然に通る(チェーン混入 `...; codex exec` は検出される)
- 生起動はパス前置(`/usr/bin/codex`)・`.exe/.cmd`・引用内(`bash -lc 'codex exec …'`)・
  npm 系ランチャー(`@openai/codex`)も捕捉
- ヒアドキュメント本文をデータとして除外するのは**正規ラッパーへの stdin のみ**
  (guard_common — `bash <<EOF` の本文は実行され得るため全文検査する)
- プラグイン companion の task モード(計画ゲートを迂回する書き込み実行)はブロック
- 危険フラグ(danger-full-access / --yolo 等)は無条件ブロック(設計書 12.1)
- 情報系(codex --version / login 等)は許可
"""
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from guard_common import effective_command

FORBIDDEN = [
    "danger-full-access",
    "--dangerously-bypass-approvals-and-sandbox",
    "--yolo",
]
# 生の codex 起動: 区切り文字(行頭・空白・引用符・; | & ( `)+ 任意のパス前置 + codex + サブコマンド
DIRECT_CODEX = re.compile(
    r"(?:^|[\s;|&(`'\"])(?:[^\s;|&()`'\"]*[/\\])?codex(?:\.exe|\.cmd)?\s+(?:exec|review|resume|e)\b"
)
# npm 系ランチャー経由(npx / pnpm dlx / yarn dlx — いずれも @openai/codex を指定する)
NPM_CODEX = re.compile(r"@openai/codex\b")


def main() -> int:
    try:
        # パイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む(fail-open 防止)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    command = str(data.get("tool_input", {}).get("command", ""))
    if "codex" not in command:
        return 0
    text = effective_command(command)

    for flag in FORBIDDEN:
        if flag in text:
            print(
                f"ブロック: {flag} は本プロジェクトで使用禁止です"
                "(設計書 12.1 の sandbox 固定ポリシー)。",
                file=sys.stderr,
            )
            return 2

    if re.search(r"codex-companion\.mjs\"?\s+task\b", text):
        print(
            "ブロック: プラグインの task モードは計画書ゲートを迂回します。"
            "実装委任は /implement(codex_run.py 経由)を使ってください(設計書 6.1/12.1)。",
            file=sys.stderr,
        )
        return 2

    if DIRECT_CODEX.search(text) or NPM_CODEX.search(text):
        print(
            "ブロック: 生の codex 実行は禁止です(パス指定・npx 経由・チェーン混入を含む)。"
            "python .claude/scripts/codex_run.py <implement|fast|research|review> を使ってください"
            "(設計書 12.1 — 計画承認・worktree・sandbox の検証をラッパーが担う)。",
            file=sys.stderr,
        )
        return 2

    if "network_access=true" in text:
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
