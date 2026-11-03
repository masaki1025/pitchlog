"""初球のV5原値を保持したまま、内容判定用DB種別だけを解決する。

privileged同期核向けの純部品であり、registered Portのimport入口ではない。
Event/Requestの書換え、D5指紋の生成、HTTP/DBへの接続は行わない。
"""

from pitchlog.db.sync_protocol.event_kinds import PLAY_INPUT_EVENT_KIND


class FirstBallV5Error(ValueError):
    """初球V5の閉じた対応外。入力値を例外へ含めない。"""


def first_ball_database_kind(value: object) -> str:
    """安定ID1を既一次対応の毎球入力literalへ解決する。

    Args:
        value: 受信後も書き換えないV5の原値。

    Returns:
        既OPERATION_EVENT_PARTICIPATIONSから導出済みのDB種別。

    Raises:
        FirstBallV5Error: exact strの安定ID1以外の場合。
    """
    if type(value) is not str or value != "1":
        raise FirstBallV5Error("初球V5は安定ID1だけに対応しています")
    return PLAY_INPUT_EVENT_KIND
