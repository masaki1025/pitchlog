"""現行started読取と同じ原本照合から閲覧用の最新頁だけを派生する。"""

import hashlib

from pitchlog.authz.started_snapshot_read_sql import (
    candidate_started_read_function_bodies,
)

_OLD = "read_started_play_prefix_history_page"
_NEW = "read_viewer_play_prefix_history_page"
_SOURCE_SHA256 = "bc2ba23272874bc0ffba1d8023709a521109ffe6f22cec6c3a16be3a9db8e3a5"
_IDENTITY = (
    "sync_right_api.read_viewer_play_prefix_history_page("
    "uuid,uuid,bigint,bigint,uuid,bigint,bigint,bigint,bigint,bigint,uuid,integer)"
)


def _one(sql: str, old: str, new: str) -> str:
    """固定した1箇所以外を静かに変換しない。"""
    if sql.count(old) != 1:
        raise ValueError("閲覧pageの元本文境界が不一致")
    return sql.replace(old, new, 1)


def candidate_viewer_page_body() -> str:
    """既全値照合を保ち、v3の最新25件だけを降順keysetで読む。"""
    source = candidate_started_read_function_bodies()[_OLD]
    if hashlib.sha256(source.encode()).hexdigest() != _SOURCE_SHA256:
        raise ValueError("閲覧pageの元reader本文が変更されました")
    sql = _one(
        source,
        "sync_right_api." + _OLD + "(",
        "sync_right_api." + _NEW + "(",
    )
    sql = _one(
        sql,
        " next_d1:=p_after_d1;",
        " next_d1:=CASE WHEN p_after_d1=0 THEN p_upper_watermark+1 "
        "ELSE p_after_d1 END;",
    )
    sql = _one(sql, "p_page_size>100", "p_page_size>25")
    sql = _one(
        sql,
        "AND (x.d1,x.d2,x.source_event_id)>(p_after_d1,p_after_d2,p_after_id)",
        "AND (p_after_d1=0 OR (x.d1,x.d2,x.source_event_id)"
        "<(p_after_d1,p_after_d2,p_after_id))",
    )
    sql = _one(
        sql,
        "ORDER BY x.d1,x.d2,x.source_event_id LIMIT p_page_size+1",
        "ORDER BY x.d1 DESC,x.d2 DESC,x.source_event_id DESC LIMIT p_page_size+1",
    )
    sql = _one(
        sql,
        "ORDER BY h.d1,h.d2,h.source_event_id",
        "ORDER BY h.d1 DESC,h.d2 DESC,h.source_event_id DESC",
    )
    sql = _one(
        sql,
        "IF (item.history->>'d1')::bigint-next_d1<>1",
        "IF next_d1-(item.history->>'d1')::bigint<>1",
    )
    sql = _one(
        sql,
        "IF seen_count<=p_page_size AND next_d1<>p_upper_watermark THEN",
        "IF seen_count<=p_page_size AND next_d1<>1 THEN",
    )
    if "FOR UPDATE" in sql or "FOR SHARE" in sql:
        raise ValueError("閲覧pageへ行lockが残っています")
    return (
        sql
        + f"ALTER FUNCTION {_IDENTITY} OWNER TO pitchlog_sync_right_fn_owner;\n"
        + f"REVOKE ALL ON FUNCTION {_IDENTITY} FROM PUBLIC,pitchlog_app;\n"
        + f"GRANT EXECUTE ON FUNCTION {_IDENTITY} TO pitchlog_app;\n"
    )
