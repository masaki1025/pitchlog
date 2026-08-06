"""シークレット参照の遮断フック(PreToolUse / Bash|PowerShell)。

敵対レビュー P0-1 対応: permissions の Read deny はサブプロセス(node/python 等)には
効かないため、コマンド文字列中の `.env` 参照を遮断する(.env.example は許可)。
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

ENV_REF = re.compile(r"\.env\b(?!\.example\b)")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    command = str(data.get("tool_input", {}).get("command", ""))
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
