"""ガード共通の前処理(3周目/4周目敵対レビュー P0 対応)。

方針: 「悪い形の検出」ではなく「**正規形の受理**」。ヒアドキュメント本文を
データとして検査対象から外せるのは、コマンド全体が

    正規ラッパー(.claude/scripts/codex_run.py)の単独呼び出し
    + 末尾の stdin ヒアドキュメント最大1つ(+出力リダイレクト)

という正規形に**完全一致**する場合だけ。追加コマンド・2つ目のヒアドキュメント・
終端マーカー後の残余・解析不能な形は、本文を除外せず**全文を検査対象に残す**
(`bash <<EOF` 迂回や「ラッパー heredoc の後ろに別 heredoc」を遮断)。
"""
import re

# 正規形: [PITCHLOG_* 環境変数]* python[3] <path>/codex_run.py 引数* [<<マーカー] [リダイレクト]*
CANONICAL_WRAPPER = re.compile(
    r"^\s*(?:PITCHLOG_\w+=(?:\"[^\"]*\"|'[^']*'|\S*)\s+)*"
    r"python3?\s+(?:[^\s;|&()`<>'\"]*[/\\])?\.claude[/\\]scripts[/\\]codex_run\.py"
    r"(?:\s+[^\s;|&()`<>'\"]+)*"                                    # 引数(区切り・リダイレクト・引用符なし)
    r"(?:\s+<<-?\s*(?:'(?P<q1>[^']+)'|\"(?P<q2>[^\"]+)\"|(?P<u>[A-Za-z_][\w-]*)))?"  # heredoc 開始(最大1)
    r"(?:\s+<\s*[^\s;|&()`<>]+|\s+2?>>?\s*[^\s;|&()`<>]+|\s+2>&1)*"  # 入出力リダイレクト
    r"\s*$"
)


def effective_command(command: str) -> str:
    """検査対象のコマンド文字列を返す(正規形のラッパー呼び出しの stdin 本文のみ除外)。"""
    lines = command.split("\n")
    m = CANONICAL_WRAPPER.match(lines[0])
    if not m:
        return command
    marker = m.group("q1") or m.group("q2") or m.group("u")
    if marker is None:
        # heredoc なしの正規形 — 2行目以降があれば正規形でない(全文検査)
        return lines[0] if len(lines) == 1 else command
    body = lines[1:]
    for i, ln in enumerate(body):
        if ln.strip() == marker:
            # 終端マーカーの後に非空行があれば正規形でない — 全文を検査対象に戻す
            if any(t.strip() for t in body[i + 1:]):
                return command
            return lines[0]
    return command  # 終端マーカーなし(不完全な heredoc) — 全文検査
