"""版固定領域・シークレットの書き込み保護フック(PreToolUse / Write|Edit)。

設計書 8.3: docs/legacy/**(版固定・不可変)と .env 系への書き込みをブロックする。
permissions の deny と二重化した多層防御。判定不能時は通す(fail-open)。
"""
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
from pathlib import PurePosixPath


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    file_path = str(data.get("tool_input", {}).get("file_path", ""))
    if not file_path:
        return 0
    p = file_path.replace("\\", "/")
    name = PurePosixPath(p).name

    if "/docs/legacy/" in p or p.rstrip("/").endswith("/docs/legacy"):
        print("ブロック: docs/legacy/ は版固定アーカイブです。変更禁止(設計書 7.1)。", file=sys.stderr)
        return 2
    if name.startswith(".env") and name != ".env.example":
        print("ブロック: .env 系ファイルへの書き込みは禁止です(NFR-014)。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
