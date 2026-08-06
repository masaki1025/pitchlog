"""ガード共通の前処理(3周目敵対レビュー P0/P1 対応)。

ヒアドキュメント本文を「データ」として検査対象から外せるのは、
**正規ラッパー(`.claude/scripts/codex_run.py`)への stdin** だけ。
それ以外(`bash <<EOF` 等)の本文はシェルが実行し得るため、検査対象に残す。
"""
import re

# 先頭行が正規ラッパーの呼び出しであること(前置は PITCHLOG_* 環境変数のみ許容)
WRAPPER_LINE = re.compile(
    r"^\s*(?:PITCHLOG_\w+=(?:\"[^\"]*\"|'[^']*'|\S*)\s+)*"
    r"python3?\s+(?:\S*[/\\])?\.claude[/\\]scripts[/\\]codex_run\.py\s"
)

HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def strip_heredocs(command: str) -> str:
    """ヒアドキュメント本文を除去する(開始行自体は残す — 後続チェーンの検査は継続)。"""
    out: list[str] = []
    marker: str | None = None
    for line in command.split("\n"):
        if marker is not None:
            if line.strip() == marker:
                marker = None
            continue
        out.append(line)
        m = HEREDOC.search(line)
        if m:
            marker = m.group(2)
    return "\n".join(out)


def effective_command(command: str) -> str:
    """検査対象のコマンド文字列を返す。

    正規ラッパー呼び出し(先頭行判定)の stdin 本文のみをデータとして除外し、
    それ以外はヒアドキュメント本文も含めて全文を返す(bash <<EOF 迂回の遮断)。
    """
    if WRAPPER_LINE.match(command.split("\n", 1)[0]):
        return strip_heredocs(command)
    return command
