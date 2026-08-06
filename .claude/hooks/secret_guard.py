"""シークレット参照の遮断フック(PreToolUse / Bash|PowerShell)。

permissions の Read deny はサブプロセス(node/python 等)に効かないため、コマンド中の
`.env` 参照を遮断する(P0-1)。5周目レビュー対応で**トークンベース**に作り替え:
`,` を含むファイル名・大小文字差(`.ENV`)・ディレクトリ経由の派生名を字句解析で塞ぐ。

- 許可する例外は **basename が exact `.env.example`(大小無視)** のトークンのみ
- 正規ラッパーへの stdin(プロンプト本文)はデータとして検査対象外
- 解析不能かつ '.env' を含むコマンドは安全側でブロック
- 文字列組み立てによる難読化は防げない — 残余リスクは設計書 12.1(脅威モデルの範囲外)
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

# トークン内のどこかに .env 由来の要素があるか(先頭 or パス区切り直後の .env)
ENV_IN_TOKEN = re.compile(r"(?:^|[/\\])\.env", re.IGNORECASE)
# 生テキスト中の .env ファイル名の連なり(コード文字列内の open('.env') 等も捕捉)。
# `.env` の直後が単語文字なら別名(.environ・.envrc)として除外し、拡張子区切り
# (. , - ~)から続く連なりだけを .env ファイルとみなす。exact `.env.example` のみ許可。
ENV_RUN = re.compile(r"\.env(?![\w])(?:[.,~-][\w.,~-]*)?", re.IGNORECASE)


def is_env_reference(token: str) -> bool:
    if not ENV_IN_TOKEN.search(token):
        return False
    return basename(token).lower() != ".env.example"  # 正本のみ許可(exact・大小無視)


def text_has_env(text: str) -> bool:
    """生テキスト中に exact `.env.example` 以外の .env 連なりがあるか。"""
    return any(run.lower() != ".env.example" for run in ENV_RUN.findall(text))


def block() -> int:
    print(
        "ブロック: コマンドが .env を参照しています(NFR-014 / 設計書 12.1)。"
        "設定の正本は .env.example。実値が必要な処理は人間が行ってください。",
        file=sys.stderr,
    )
    return 2


def main() -> int:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    text = effective_command(str(data.get("tool_input", {}).get("command", "")))
    if ".env" not in text.lower():
        return 0
    # 生テキストの連なり走査(コード文字列内・comma・大小文字差を捕捉)
    if text_has_env(text):
        return block()
    # トークンのパス要素走査(.env.example/secret のようなディレクトリ経由を捕捉)
    tokens = shell_tokens(text)
    if tokens is None:
        return block()  # 解析不能かつ .env を含む → 安全側
    if any(is_env_reference(t) for t in tokens):
        return block()
    return 0


if __name__ == "__main__":
    sys.exit(main())
