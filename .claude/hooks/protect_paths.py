"""版固定領域・シークレットの書き込み保護フック(PreToolUse / Write|Edit)。

設計書 8.3: docs/legacy/**(版固定・不可変)と .env 系への書き込みをブロックする。
permissions の deny と二重化した多層防御。判定不能時は通す(fail-open)。
敵対レビュー P1-8 対応: 相対パス解決・`..` 正規化・大文字小文字を無視した判定。
"""
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def normalize(file_path: str, cwd: str) -> str:
    raw = file_path
    if not os.path.isabs(raw) and cwd:
        raw = os.path.join(cwd, raw)
    return os.path.normpath(raw).replace("\\", "/").casefold()


def main() -> int:
    try:
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む(fail-open 防止)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    file_path = str(data.get("tool_input", {}).get("file_path", ""))
    if not file_path:
        return 0
    p = normalize(file_path, str(data.get("cwd", "")))
    name = p.rsplit("/", 1)[-1]

    if "/docs/legacy/" in p or p.endswith("/docs/legacy"):
        print("ブロック: docs/legacy/ は版固定アーカイブです。変更禁止(設計書 7.1)。", file=sys.stderr)
        return 2
    if name.startswith(".env") and name != ".env.example":
        print("ブロック: .env 系ファイルへの書き込みは禁止です(NFR-014)。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
