"""既play_rows二段triggerへP3同TX印の有限分岐を候補生成する。"""

from __future__ import annotations

from pitchlog.authz.first_ball_write_stamp import _ADMIT, _LOCK

_REJECT = (
    "RAISE EXCEPTION 'first ball write admission rejected' "
    "USING ERRCODE='42501';"
)

_LOCK_P3 = """
 IF current_user='pitchlog_sync_right_fn_owner' THEN
 PERFORM 1 FROM sync_fence.p3_projection_write_admissions a
 JOIN sync_fence.writer_bindings b ON
 (b.tenant_id,b.attempt_id,b.phase_id)=(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE a.tenant_id=NEW.tenant_id AND a.game_id=NEW.game_id
 AND a.play_row_id=NEW.id AND a.change_event_id=NEW.source_event_id
 AND a.expected_play_row=pg_catalog.to_jsonb(NEW) AND a.state='ready'
 AND a.transaction_id=pg_catalog.pg_current_xact_id()::text
 AND a.xmin::text::numeric=pg_catalog.mod(
 pg_catalog.pg_current_xact_id()::text::numeric,4294967296::numeric)
 AND b.state='open' AND b.transaction_id=a.transaction_id
 AND b.device_id IS NOT NULL AND b.expires_at>pg_catalog.clock_timestamp()
 FOR SHARE OF a;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 play row admission rejected' USING ERRCODE='42501'; END IF;
 RETURN NEW;
 END IF;
"""

_ADMIT_P3 = """
 IF current_user='pitchlog_sync_right_fn_owner' AND
 EXISTS(SELECT 1 FROM sync_fence.p3_projection_write_admissions a
 WHERE a.tenant_id=NEW.tenant_id AND a.game_id=NEW.game_id
 AND a.play_row_id=NEW.id AND a.change_event_id=NEW.source_event_id
 AND a.state='ready') THEN
 IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'play_rows' OR TG_OP<>'INSERT'
 OR TG_WHEN<>'BEFORE' OR TG_LEVEL<>'ROW' OR TG_NARGS<>0
 OR session_user<>'pitchlog_app' OR NEW.tenant_id IS NULL
 OR NEW.tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR NEW.import_batch_id IS NOT NULL OR NEW.legacy_row_identifier IS NOT NULL
 OR NEW.migration_unverified IS DISTINCT FROM false
 OR NOT EXISTS(SELECT 1 FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN sync_fence.p3_projection_write_admissions a ON
 (a.tenant_id,a.game_id,a.change_event_id)=(e.tenant_id,e.game_id,e.id)
 JOIN sync_fence.writer_bindings b ON
 (b.tenant_id,b.attempt_id,b.phase_id)=(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE (e.tenant_id,e.game_id,e.id)=(NEW.tenant_id,NEW.game_id,NEW.source_event_id)
 AND e.event_kind='play_change' AND e.ledger_kind='accepted'
 AND e.d1 IS NULL AND e.d2 IS NULL AND e.generation IS NULL
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND NOT e.is_tombstone
 AND l.kind='accepted' AND l.source_fingerprint=a.ledger_fingerprint
 AND l.retired_at IS NULL AND b.state='open'
 AND b.transaction_id=pg_catalog.pg_current_xact_id()::text
 AND b.expires_at>pg_catalog.clock_timestamp()
 AND a.expected_play_row=pg_catalog.to_jsonb(NEW)
 AND a.transaction_id=b.transaction_id AND a.state='ready'
 AND a.xmin::text::numeric=pg_catalog.mod(
 pg_catalog.pg_current_xact_id()::text::numeric,4294967296::numeric))
 THEN RAISE EXCEPTION 'P3 play row admission rejected' USING ERRCODE='42501';
 END IF;
 UPDATE sync_fence.p3_projection_write_admissions a SET state='consumed'
 WHERE a.tenant_id=NEW.tenant_id AND a.game_id=NEW.game_id
 AND a.play_row_id=NEW.id AND a.change_event_id=NEW.source_event_id
 AND a.expected_play_row=pg_catalog.to_jsonb(NEW) AND a.state='ready'
 AND a.transaction_id=pg_catalog.pg_current_xact_id()::text
 RETURNING a.xmin::text INTO row_xmin;
 IF NOT FOUND OR row_xmin::numeric IS DISTINCT FROM pg_catalog.mod(
 pg_catalog.pg_current_xact_id()::text::numeric,4294967296::numeric)
 THEN RAISE EXCEPTION 'P3 play row admission rejected' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
 END IF;
"""


def candidate_sql() -> str:
    """旧trigger本文を固定点で一回ずつだけ拡張し、候補DDLを返す。"""
    current_role = "OR current_user<>'pitchlog_app'"
    game_lock = " -- 既核と同じgame→current generationの順。資格GUCを設定しない。"
    admit_start = "BEGIN\n -- 読取/照合だけをEXCEPTION付き内側blockへ閉じる。"
    if (
        _LOCK.count(current_role) != 1
        or _LOCK.count(game_lock) != 1
        or _ADMIT.count(admit_start) != 1
        or _ADMIT_P3.count(_REJECT) != 0
    ):
        raise ValueError("既play_rows triggerの拡張境界が不一致")
    lock = _LOCK.replace(
        current_role,
        "OR current_user NOT IN ('pitchlog_app','pitchlog_sync_right_fn_owner')",
        1,
    ).replace(game_lock, _LOCK_P3 + game_lock, 1)
    admit = _ADMIT.replace(admit_start, "BEGIN\n" + _ADMIT_P3 + admit_start[6:], 1)
    return (
        lock.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        + "\n"
        + admit.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    )
