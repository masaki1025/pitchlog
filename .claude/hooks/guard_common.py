"""ガード共通の字句処理(5周目敵対レビュー P0 対応)。

方針の転換: 生文字列への正規表現マッチは、シェルの引用符・コメント・
グローバルオプション位置・区切りの多様性を取りこぼす(2〜5周目で繰り返し露呈)。
本モジュールは **shlex による字句解析**を土台にし、各ガードはトークン列で判定する。

- `shell_tokens`: コメント除去つきトークン化。解析不能(引用符の不整合など)は
  None を返し、呼び出し側は**安全側(ブロック)**に倒す。
- `effective_command`: ヒアドキュメント本文をデータ扱いできるのは
  「正規ラッパー単独 + 末尾 stdin ヒアドキュメント1つ」に完全一致する時だけ。
  それ以外は本文を含む全文を検査対象に残す。
"""
import re
import shlex

# 正規形: [PITCHLOG_* env]* python[3] <path>/codex_run.py 引数* [<<マーカー] [リダイレクト]*
# 引数・パスに # を許さない(# 以降がコメント化してヒアドキュメント誤認する迂回を排除 — 5周目 P0)
_ARG = r"[^\s;|&()`<>'\"#]+"
CANONICAL_WRAPPER = re.compile(
    r"^\s*(?:PITCHLOG_\w+=(?:\"[^\"]*\"|'[^']*'|" + _ARG + r"?)\s+)*"
    r"python3?\s+(?:" + _ARG + r"[/\\])?\.claude[/\\]scripts[/\\]codex_run\.py"
    r"(?:\s+" + _ARG + r")*"
    r"(?:\s+<<-?\s*(?:'(?P<q1>[^']+)'|\"(?P<q2>[^\"]+)\"|(?P<u>[A-Za-z_][\w-]*)))?"
    r"(?:\s+<\s*" + _ARG + r"|\s+2?>>?\s*" + _ARG + r"|\s+2>&1)*"
    r"\s*$"
)


def shell_tokens(command: str) -> list[str] | None:
    """コメント除去つきでトークン化する。解析不能なら None(呼び出し側で安全側に倒す)。"""
    try:
        return shlex.split(command, comments=True)
    except ValueError:
        return None


def basename(token: str) -> str:
    """トークンのパス末尾要素を返す(引用符は shlex が除去済み)。"""
    return re.split(r"[/\\]", token)[-1]


def effective_command(command: str) -> str:
    """検査対象のコマンド文字列を返す(正規形のラッパー呼び出しの stdin 本文のみ除外)。"""
    lines = command.split("\n")
    m = CANONICAL_WRAPPER.match(lines[0])
    if not m:
        return command
    marker = m.group("q1") or m.group("q2") or m.group("u")
    if marker is None:
        return lines[0] if len(lines) == 1 else command
    body = lines[1:]
    for i, ln in enumerate(body):
        if ln.strip() == marker:
            if any(t.strip() for t in body[i + 1:]):
                return command  # 終端後に残余 → 正規形でない
            return lines[0]
    return command  # 終端マーカーなし(不完全) → 全文検査
