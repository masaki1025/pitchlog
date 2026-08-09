"""Codex 実行経路の強制フック(PreToolUse / Bash|PowerShell)。

Codex の実行は `.claude/scripts/codex_run.py` ラッパーのみに限定する(P0-2)。
5周目レビュー対応で**トークン+コマンド位置**判定に作り替え:

- セグメント(;・&&・|・改行)ごとに**コマンド語**を特定し、それが codex 実行ファイルなら
  直後が情報系(--version/login 等)以外でブロック(引数中の "codex" 誤検出を排除)
- コマンド語が shell(bash/sh 等)で `-c` を持つ場合は、そのスクリプト文字列を**1段再帰**で検査
  (`bash -lc 'codex exec x'` を捕捉。2段以上のネストは脅威モデル外 — 12.1)
- npm 系(@openai/codex)・companion task・危険フラグはセグメント内で直接検出
- 解析不能な 'codex' 入りセグメントは安全側でブロック
"""
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from guard_common import basename, effective_command, shell_tokens

FORBIDDEN = ("danger-full-access", "--dangerously-bypass-approvals-and-sandbox", "--yolo")
CODEX_EXE = {"codex", "codex.exe", "codex.cmd"}
SAFE_NEXT = {"--version", "-v", "-V", "--help", "-h", "help", "login", "logout", "status", "whoami"}
PREFIXES = {"env", "sudo", "time", "nice", "nohup", "xargs", "command", "builtin", "stdbuf", "setsid", "then", "do"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}


def block(msg: str) -> int:
    print(f"ブロック: {msg}", file=sys.stderr)
    return 2


def command_index(tokens: list[str]) -> int | None:
    """先頭の環境変数代入・コマンド接頭辞をスキップしてコマンド語の位置を返す。"""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^\w+=", t):
            i += 1
            continue
        if basename(t).lower() in PREFIXES:
            i += 1
            continue
        return i
    return None


def is_raw_codex_invocation(tokens: list[str], depth: int = 0) -> bool:
    """トークン列(1コマンド分)が生の codex 実行かを判定する。"""
    ci = command_index(tokens)
    if ci is None:
        return False
    cmd = basename(tokens[ci]).lower()
    if cmd in CODEX_EXE:
        nxt = tokens[ci + 1].lower() if ci + 1 < len(tokens) else None
        return nxt is not None and nxt not in SAFE_NEXT
    if cmd in SHELLS and depth < 1:
        # shell -c/-lc のスクリプト文字列を1段再帰で検査
        for j in range(ci + 1, len(tokens)):
            t = tokens[j]
            if t.startswith("-") and "c" in t[1:]:
                if j + 1 < len(tokens):
                    inner = shell_tokens(tokens[j + 1])
                    if inner is None:
                        return True  # ネスト内が解析不能 → 安全側
                    return any_raw_codex(inner, depth + 1)
    return False


def any_raw_codex(tokens: list[str], depth: int = 0) -> bool:
    """トークン列を shell 演算子で分割し、各コマンドを検査する。"""
    seg: list[str] = []
    for t in tokens + [";"]:
        if t in (";", "&&", "||", "|", "&"):
            if seg and is_raw_codex_invocation(seg, depth):
                return True
            seg = []
        else:
            seg.append(t)
    return False


def main() -> int:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    raw = str(data.get("tool_input", {}).get("command", ""))
    if "codex" not in raw.lower():
        return 0
    text = effective_command(raw)
    if "codex" not in text.lower():
        return 0  # 危険部分は正規ラッパーの stdin 本文だった

    for flag in FORBIDDEN:
        if flag in text:
            return block(f"{flag} は本プロジェクトで使用禁止です(設計書 12.1)。")

    for seg in re.split(r"&&|\|\||\||;|\n|&", text):
        low = seg.lower()
        if "@openai/codex" in low:
            return block("npm 系ランチャー経由の codex 実行は禁止です。codex_run.py を使ってください。")
        if "codex-companion.mjs" in low and re.search(r"codex-companion\.mjs['\"]?\s+task\b", seg):
            return block("プラグインの task モードは計画書ゲートを迂回します。/implement を使ってください(6.1/12.1)。")
        if "codex" not in low:
            continue
        tokens = shell_tokens(seg)
        if tokens is None:
            return block("codex を含むコマンドを字句解析できませんでした(引用符を確認)。安全側で遮断します。")
        if is_raw_codex_invocation(tokens):
            return block("生の codex 実行は禁止です(exec/review/resume・対話起動・オプション前置・shell 経由を含む)。"
                         "python .claude/scripts/codex_run.py <implement|fast|research|review> を使ってください(設計書 12.1)。")

    if "network_access=true" in text:
        print(json.dumps({"systemMessage": (
            "注意: Codex をネットワーク有効で実行します(12.1 の例外運用 — 実行前に理由の報告が必要です)"
        )}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
