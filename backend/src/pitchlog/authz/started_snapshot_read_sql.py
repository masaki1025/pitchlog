"""既有限readerから行lockを外しRR/ROを閉じるGET専用候補。"""

import hashlib

from pitchlog.authz.ordinary_prefix_sql import (
    candidate_read_function_bodies as ordinary,
)
from pitchlog.authz.p3_nonplay_bridge_sql import (
    candidate_function_bodies_p3_nonplay_bridge as nonplay,
)
from pitchlog.authz.terminal_pitch_write_stamp import candidate_function_bodies as play

_SOURCE = (
    ("read_ordinary_history_page", ordinary, 1),
    ("read_play_prefix_history_page", play, 1),
    ("read_nonplay_active_history", nonplay, 2),
)
_PINNED_ORIGIN_SHA256 = {
    "read_ordinary_history_page": (
        "2b247185a6cdea7a57e3749c3ac3daf7de0630e4d88db881d991074c0154706b"
    ),
    "read_play_prefix_history_page": (
        "2346ea918bfa470ae69add54c31572667451814498383164ecb5870e59f30f5e"
    ),
    "read_nonplay_active_history": (
        "c3ac7df727897194de6e8426aa72be495d35ffb6d501b18243d889bd9d6cca74"
    ),
}
_RR_RO_GUARD = (
    " IF pg_catalog.current_setting('transaction_isolation') "
    "IS DISTINCT FROM 'repeatable read'\n"
    " OR pg_catalog.current_setting('transaction_read_only') "
    "IS DISTINCT FROM 'on' THEN\n"
    " RAISE EXCEPTION 'started snapshot read requires RR/RO' "
    "USING ERRCODE='42501';\n"
    " END IF;\n"
)


def candidate_started_read_function_bodies() -> dict[str, str]:
    """旧SQLの集合/順序を保持し、別identity/行lock/RR条件だけを変更する。"""
    result = {}
    for old, factory, count in _SOURCE:
        sql = factory()[old]
        if (
            hashlib.sha256(sql.encode()).hexdigest() != _PINNED_ORIGIN_SHA256[old]
            or sql.count("sync_right_api." + old + "(") != 1
            or sql.count("FOR SHARE") != count
            or "FOR UPDATE" in sql
        ):
            raise ValueError("元reader本文の固定構造が変化しました")
        new = "read_started_" + old.removeprefix("read_")
        body = (
            sql.replace("sync_right_api." + old + "(", "sync_right_api." + new + "(", 1)
            .replace(" FOR SHARE OF c", "")
            .replace(" FOR SHARE", "")
        )
        if body.count("BEGIN\n") < 1 or _RR_RO_GUARD in body:
            raise ValueError("GET専用readerの開始位置が不正です")
        body = body.replace("BEGIN\n", "BEGIN\n" + _RR_RO_GUARD, 1)
        if "FOR SHARE" in body or "FOR UPDATE" in body or body.count(_RR_RO_GUARD) != 1:
            raise ValueError("GET専用readerに行lockが残っています")
        result[new] = body
    return result
