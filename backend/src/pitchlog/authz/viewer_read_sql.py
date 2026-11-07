"""既有限履歴readerからRR READ ONLY専用の非ロック本文を派生する。"""

from pitchlog.authz.nonplay_prefix_read_sql import (
    candidate_read_function_bodies as nonplay_bodies,
)
from pitchlog.authz.terminal_pitch_write_stamp import (
    candidate_function_bodies as play_bodies,
)


def candidate_viewer_function_bodies() -> dict[str, str]:
    """既readerのanchor・保存証拠・上限を共有し、行ロックだけを除く。"""
    source = (
        ("read_play_prefix_history_page", play_bodies(), 1),
        ("read_nonplay_active_history", nonplay_bodies(), 2),
    )
    result = {}
    for old, bodies, expected_locks in source:
        sql = bodies[old]
        if sql.count("FOR SHARE") != expected_locks or "FOR UPDATE" in sql:
            raise ValueError("閲覧関数の元SQLが変更されました")
        new = "read_viewer_" + old.removeprefix("read_")
        if sql.count("sync_right_api." + old + "(") != 1:
            raise ValueError("閲覧関数の元宣言が変更されました")
        body = (
            sql.replace("sync_right_api." + old + "(", "sync_right_api." + new + "(", 1)
            .replace("FOR SHARE OF c", "")
            .replace("FOR SHARE", "")
        )
        if old == "read_play_prefix_history_page":
            # 最新pageから旧pageへ遡るため、境界は「以下」で降順に読む。
            before = (
                "AND (x.d1,x.d2,x.source_event_id)>(p_after_d1,p_after_d2,p_after_id)"
            )
            after = (
                "AND (p_after_d1=0 OR (x.d1,x.d2,x.source_event_id)<="
                "(p_after_d1,p_after_d2,p_after_id))"
            )
            if body.count(before) != 1:
                raise ValueError("閲覧履歴の境界式が変更されました")
            body = body.replace(before, after, 1)
            order = "ORDER BY x.d1,x.d2,x.source_event_id LIMIT p_page_size+1"
            if body.count(order) != 1:
                raise ValueError("閲覧履歴の並びが変更されました")
            body = body.replace(
                order,
                "ORDER BY x.d1 DESC,x.d2 DESC,x.source_event_id DESC "
                "LIMIT p_page_size+1",
                1,
            )
            if body.count("next_d1:=p_after_d1;") != 1:
                raise ValueError("閲覧履歴の連続性初期値が変更されました")
            body = body.replace("next_d1:=p_after_d1;", "next_d1:=0;", 1)
            check = " IF (item.history->>'d1')::bigint-next_d1<>1"
            if body.count(check) != 1:
                raise ValueError("閲覧履歴の連続性検査が変更されました")
            body = body.replace(
                check,
                " IF next_d1=0 THEN next_d1:=(item.history->>'d1')::bigint-1; "
                "END IF;\n" + check,
                1,
            )
            tail = (
                " IF seen_count<=p_page_size AND next_d1<>p_upper_watermark THEN\n"
                " RAISE EXCEPTION 'ordinary prefix history tail rejected' "
                "USING ERRCODE='42501';\n"
                " END IF;"
            )
            if body.count(tail) != 1:
                raise ValueError("閲覧履歴の末尾検査が変更されました")
            body = body.replace(tail, "", 1)
        result[new] = body
    return result
