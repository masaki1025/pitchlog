"""シークレット参照の遮断フック(PreToolUse / Bash|PowerShell)。

敵対レビュー P0-1 対応: permissions の Read deny はサブプロセス(node/python 等)には
効かないため、コマンド文字列中の `.env` 参照を遮断する。許可する例外は
**exact `.env.example` のみ**(`.env.example.local` 等の派生は遮断 — 3周目 P0)。
正規ラッパーへの stdin(プロンプト本文)はデータとして検査対象外(3周目 P1)。
文字列組み立てによる難読化までは防げない — 残余リスクは設計書 12.1 に記録。
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

# .env / .env.* を遮断。例外は「.env.example の直後にワード・ドットが続かない」場合のみ
ENV_REF = re.compile(r"\.env\b(?!\.example(?![\w.]))")


def main() -> int:
    try:
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む(fail-open 防止)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    command = effective_command(str(data.get("tool_input", {}).get("command", "")))
    if ENV_REF.search(command):
        print(
            "ブロック: コマンドが .env を参照しています(NFR-014 / 設計書 12.1)。"
            "設定の正本は .env.example。実値が必要な処理は人間が行ってください。",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
