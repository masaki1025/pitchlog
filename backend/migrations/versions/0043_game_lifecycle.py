"""終了再開の専用印/headをdefault-denyで配置し、旧42を変更しない。"""

from alembic import op

revision = "0043_game_lifecycle"
down_revision = "0042_nonplay_write_admission"
branch_labels = None
depends_on = None

_OPERATION_EVENT_13_CHECKS = {
    "ck_operation_events_event_kind": (
        "event_kind IN ('play_input', 'undo', 'substitution', 'tiebreak_start',"
        " 'game_end_declaration', 'player_registration', 'play_change', 'play_d"
        "elete', 'substitution_change', 'game_reopen')"
    ),
    "ck_operation_events_state_diff_by_kind": (
        "(NOT (event_kind = 'play_input' AND NOT is_tombstone) OR (state_diff I"
        "S NOT NULL)) AND (NOT (event_kind = 'undo' AND NOT is_tombstone) OR (s"
        "tate_diff IS NULL)) AND (NOT (event_kind = 'substitution' AND NOT is_t"
        "ombstone) OR (state_diff IS NULL)) AND (NOT (event_kind = 'tiebreak_st"
        "art' AND NOT is_tombstone) OR (state_diff IS NULL)) AND (NOT (event_ki"
        "nd = 'game_end_declaration' AND NOT is_tombstone) OR (state_diff IS NU"
        "LL)) AND (NOT (event_kind = 'player_registration' AND NOT is_tombstone"
        ") OR (state_diff IS NULL)) AND (NOT (event_kind = 'state_correction' A"
        "ND NOT is_tombstone) OR (state_diff IS NOT NULL)) AND (NOT (is_tombsto"
        "ne) OR (state_diff IS NULL)) AND (NOT (event_kind = 'play_change') OR "
        "(state_diff IS NULL)) AND (NOT (event_kind = 'play_delete') OR (state_"
        "diff IS NULL)) AND (NOT (event_kind = 'substitution_change') OR (state"
        "_diff IS NULL)) AND (NOT (event_kind = 'game_reopen' AND NOT is_tombst"
        "one) OR (state_diff IS NULL))"
    ),
    "ck_operation_events_tombstone": (
        "((NOT (event_kind = 'play_change') OR (NOT is_tombstone)) AND (NOT (ev"
        "ent_kind = 'play_delete') OR (NOT is_tombstone)) AND (NOT (event_kind "
        "= 'substitution_change') OR (NOT is_tombstone))) AND (NOT is_tombstone"
        " OR payload = '{}'::jsonb)"
    ),
    "ck_operation_events_d2_by_kind": (
        "(NOT (event_kind = 'play_input' AND NOT is_tombstone) OR (d2 IS NOT NU"
        "LL)) AND (NOT (event_kind = 'undo' AND NOT is_tombstone) OR (d2 IS NUL"
        "L)) AND (NOT (event_kind = 'substitution' AND NOT is_tombstone) OR (d2"
        " IS NOT NULL)) AND (NOT (event_kind = 'tiebreak_start' AND NOT is_tomb"
        "stone) OR (d2 IS NOT NULL)) AND (NOT (event_kind = 'game_end_declarati"
        "on' AND NOT is_tombstone) OR (d2 IS NOT NULL)) AND (NOT (event_kind = "
        "'player_registration' AND NOT is_tombstone) OR (d2 IS NULL)) AND (NOT "
        "(is_tombstone) OR (d2 IS NULL)) AND (NOT (event_kind = 'play_change') "
        "OR (d2 IS NULL)) AND (NOT (event_kind = 'play_delete') OR (d2 IS NULL)"
        ") AND (NOT (event_kind = 'substitution_change') OR (d2 IS NULL)) AND ("
        "NOT (event_kind = 'game_reopen' AND NOT is_tombstone) OR (d2 IS NOT NU"
        "LL))"
    ),
    "ck_operation_events_target_by_kind": (
        "(NOT (event_kind = 'undo' AND NOT is_tombstone) OR (target_generation "
        "IS NOT NULL AND target_d1 IS NOT NULL)) AND (NOT (event_kind = 'play_c"
        "hange') OR (target_generation IS NOT NULL AND target_d1 IS NOT NULL)) "
        "AND (NOT (event_kind = 'play_delete') OR (target_generation IS NOT NUL"
        "L AND target_d1 IS NOT NULL)) AND (NOT (event_kind = 'substitution_cha"
        "nge') OR (target_generation IS NOT NULL AND target_d1 IS NOT NULL)) AN"
        "D (NOT (event_kind = 'game_reopen' AND NOT is_tombstone) OR (target_ge"
        "neration IS NULL AND target_d1 IS NULL))"
    ),
    "ck_operation_events_expected_version_by_kind": (
        "(NOT (event_kind = 'play_input' AND NOT is_tombstone) OR (expected_ver"
        "sion IS NULL)) AND (NOT (event_kind = 'undo' AND NOT is_tombstone) OR "
        "(expected_version IS NULL)) AND (NOT (event_kind = 'substitution' AND "
        "NOT is_tombstone) OR (expected_version IS NULL)) AND (NOT (event_kind "
        "= 'tiebreak_start' AND NOT is_tombstone) OR (expected_version IS NULL)"
        ") AND (NOT (event_kind = 'game_end_declaration' AND NOT is_tombstone) "
        "OR (expected_version IS NULL)) AND (NOT (event_kind = 'player_registra"
        "tion' AND NOT is_tombstone) OR (expected_version IS NULL)) AND (NOT (e"
        "vent_kind = 'state_correction' AND NOT is_tombstone) OR (expected_vers"
        "ion IS NULL)) AND (NOT (is_tombstone) OR (expected_version IS NULL)) A"
        "ND (NOT (event_kind = 'play_change') OR (expected_version IS NOT NULL)"
        ") AND (NOT (event_kind = 'play_delete') OR (expected_version IS NOT NU"
        "LL)) AND (NOT (event_kind = 'substitution_change') OR (expected_versio"
        "n IS NOT NULL)) AND (NOT (event_kind = 'game_reopen' AND NOT is_tombst"
        "one) OR (expected_version IS NULL))"
    ),
}


def upgrade() -> None:
    """同TXで評価済み印を作成し、一回消費する専用表だけを配置する。"""
    for name, expression in _OPERATION_EVENT_13_CHECKS.items():
        op.execute(f"ALTER TABLE public.operation_events DROP CONSTRAINT {name}")
        op.execute(
            f"ALTER TABLE public.operation_events ADD CONSTRAINT {name} "
            f"CHECK ({expression})"
        )
    op.execute(
        (
            "\nCREATE TABLE sync_fence.lifecycle_write_admissions (\n\t"
            "tenant_id UUID NOT NULL, \n\tattempt_id UUID NOT NULL, \n\t"
            "phase_id UUID NOT NULL, \n\tauthority_id UUID NOT NULL, \n"
            "\tcontrol_instance UUID NOT NULL, \n\tbusiness_instance UU"
            "ID NOT NULL, \n\trestore_epoch UUID NOT NULL, \n\tcontrol_v"
            "ersion BIGINT NOT NULL, \n\tissuer UUID NOT NULL, \n\tlease"
            "_id UUID NOT NULL, \n\tdevice_id UUID NOT NULL, \n\tgame_id"
            " UUID NOT NULL, \n\twire_d4 TEXT NOT NULL, \n\tinternal_gen"
            "eration BIGINT NOT NULL, \n\trecovery_generation BIGINT N"
            "OT NULL, \n\tcodec_version BIGINT NOT NULL, \n\trequest_fin"
            "gerprint TEXT NOT NULL, \n\td5 UUID NOT NULL, \n\tevent_fin"
            "gerprint TEXT NOT NULL, \n\tsystem_identifier TEXT NOT NU"
            "LL, \n\tdatabase_oid TEXT NOT NULL, \n\tpostmaster_started_"
            "at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tbackend_pid INT"
            "EGER NOT NULL, \n\tbackend_start TIMESTAMP WITH TIME ZONE"
            " NOT NULL, \n\ttransaction_id TEXT NOT NULL, \n\tnonce_dige"
            "st BYTEA NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZON"
            "E NOT NULL, \n\tstate TEXT NOT NULL, \n\tframe_id UUID, \n\tf"
            "rame_digest TEXT, \n\tartifact_sha256 TEXT, \n\tsource_even"
            "t_id UUID, \n\tsource_d1 BIGINT, \n\tsource_d2 BIGINT, \n\tch"
            "eckpoint_id UUID, \n\tcheckpoint_revision BIGINT, \n\tcheck"
            "point_digest TEXT, \n\treceipt_id UUID, \n\taction TEXT, \n\t"
            "preparation_json TEXT, \n\tpreparation JSONB, \n\tconsumed_"
            "at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (tenant_id, "
            "attempt_id, phase_id), \n\tUNIQUE (tenant_id, frame_id), "
            "\n\tUNIQUE (tenant_id, source_event_id), \n\tUNIQUE (tenant"
            "_id, receipt_id), \n\tCONSTRAINT fk_lifecycle_admission_b"
            "inding FOREIGN KEY(tenant_id, attempt_id, phase_id) REF"
            "ERENCES sync_fence.writer_bindings (tenant_id, attempt_"
            "id, phase_id) MATCH FULL ON DELETE NO ACTION, \n\tCONSTRA"
            "INT fk_lifecycle_admission_game FOREIGN KEY(tenant_id, "
            "game_id) REFERENCES games (tenant_id, id) ON DELETE NO "
            "ACTION, \n\tCONSTRAINT fk_lifecycle_admission_event FOREI"
            "GN KEY(tenant_id, source_event_id) REFERENCES operation"
            "_events (tenant_id, id) ON DELETE NO ACTION DEFERRABLE "
            "INITIALLY DEFERRED, \n\tCONSTRAINT ck_lifecycle_admission"
            "_state CHECK (state IN ('evaluated','consumed')), \n\tCON"
            "STRAINT ck_lifecycle_admission_identity CHECK (octet_le"
            "ngth(nonce_digest)=32 AND internal_generation>0 AND rec"
            "overy_generation>0 AND codec_version=1), \n\tCONSTRAINT c"
            "k_lifecycle_admission_xid CHECK (control_version>0 AND "
            "backend_pid>0 AND transaction_id ~ '^[1-9][0-9]{0,19}$'"
            " AND transaction_id !~ '[^0-9]' AND transaction_id::num"
            "eric<=18446744073709551615), \n\tCONSTRAINT ck_lifecycle_"
            "admission_consumed CHECK ((state='consumed')=(consumed_"
            "at IS NOT NULL)), \n\tCONSTRAINT ck_lifecycle_admission_e"
            "valuated CHECK (state NOT IN ('evaluated','consumed') O"
            "R (frame_id IS NOT NULL AND frame_digest IS NOT NULL AN"
            "D artifact_sha256 IS NOT NULL AND source_event_id IS NO"
            "T NULL AND source_d1 IS NOT NULL AND source_d1>0 AND so"
            "urce_d2 IS NOT NULL AND source_d2>=0 AND checkpoint_id "
            "IS NOT NULL AND checkpoint_revision IS NOT NULL AND che"
            "ckpoint_revision>0 AND checkpoint_digest IS NOT NULL AN"
            "D receipt_id IS NOT NULL AND action IS NOT NULL AND act"
            "ion IN ('end','reopen') AND preparation_json IS NOT NUL"
            "L AND preparation IS NOT NULL)), \n\tCONSTRAINT ck_lifecy"
            "cle_admission_values CHECK (state NOT IN ('evaluated','"
            "consumed') OR (frame_digest ~ '^[a-f0-9]{64}$' AND octe"
            "t_length(frame_digest)=64 AND artifact_sha256 ~ '^[a-f0"
            "-9]{64}$' AND octet_length(artifact_sha256)=64 AND chec"
            "kpoint_digest ~ '^[a-f0-9]{64}$' AND octet_length(check"
            "point_digest)=64 AND jsonb_typeof(preparation)='object'"
            "))\n)\n\n"
        )
    )
    op.execute(
        (
            "CREATE INDEX ix_lifecycle_game_source ON sync_fence.lif"
            "ecycle_write_admissions (tenant_id, game_id, internal_g"
            "eneration, source_d1)"
        )
    )
    op.execute(
        "ALTER TABLE sync_fence.lifecycle_write_admissions OWNER TO pitchlog_owner"
    )
    op.execute(
        "ALTER TABLE sync_fence.lifecycle_write_admissions ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE sync_fence.lifecycle_write_admissions FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        (
            "REVOKE ALL ON TABLE sync_fence.lifecycle_write_admissio"
            "ns FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor"
            ",pitchlog_rg1_control_actor,pitchlog_sync_right_fn_owne"
            "r"
        )
    )
    op.execute(
        (
            "CREATE FUNCTION public.protect_lifecycle_write_admissio"
            "ns() RETURNS trigger\nLANGUAGE plpgsql SET search_path=p"
            "g_catalog,pg_temp AS $guard$\nBEGIN\n IF TG_OP IN ('DELET"
            "E','TRUNCATE') OR current_user<>'pitchlog_sync_right_fn"
            "_owner'\n THEN RAISE EXCEPTION 'lifecycle private row pr"
            "otected' USING ERRCODE='42501'; END IF;\n\n IF TG_OP='INS"
            "ERT' AND (NEW.state<>'evaluated' OR NEW.consumed_at IS "
            "NOT NULL)\n THEN RAISE EXCEPTION 'lifecycle initial stat"
            "e' USING ERRCODE='42501'; END IF;\n IF TG_OP='UPDATE' AN"
            "D (OLD.state<>'evaluated' OR NEW.state<>'consumed'\n OR "
            "NEW.consumed_at IS NULL OR\n (pg_catalog.to_jsonb(NEW)-'"
            "state'-'consumed_at') IS DISTINCT FROM\n (pg_catalog.to_"
            "jsonb(OLD)-'state'-'consumed_at'))\n THEN RAISE EXCEPTIO"
            "N 'lifecycle admission immutable' USING ERRCODE='42501'"
            "; END IF;\n\n RETURN NEW;\nEND;\n$guard$;"
        )
    )
    op.execute(
        (
            "ALTER FUNCTION public.protect_lifecycle_write_admission"
            "s() OWNER TO pitchlog_owner"
        )
    )
    op.execute(
        (
            "REVOKE ALL ON FUNCTION public.protect_lifecycle_write_a"
            "dmissions() FROM PUBLIC,pitchlog_app"
        )
    )
    op.execute(
        (
            "CREATE TRIGGER trg_lifecycle_write_admissions_guard BEF"
            "ORE INSERT OR UPDATE OR DELETE ON sync_fence.lifecycle_"
            "write_admissions FOR EACH ROW EXECUTE FUNCTION public.p"
            "rotect_lifecycle_write_admissions()"
        )
    )
    op.execute(
        (
            "CREATE TRIGGER trg_lifecycle_write_admissions_no_trunca"
            "te BEFORE TRUNCATE ON sync_fence.lifecycle_write_admiss"
            "ions FOR EACH STATEMENT EXECUTE FUNCTION public.protect"
            "_lifecycle_write_admissions()"
        )
    )
    op.execute(
        (
            "\nCREATE TABLE sync_fence.game_lifecycle_heads (\n\ttenant"
            "_id UUID NOT NULL, \n\tgame_id UUID NOT NULL, \n\tlast_vers"
            "ion BIGINT NOT NULL, \n\tis_finished BOOLEAN NOT NULL, \n\t"
            "active_end_event_id UUID, \n\tactive_receipt_id UUID, \n\ta"
            "ctive_stats_version_id UUID, \n\tlast_control_event_id UU"
            "ID NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT "
            "NULL, \n\tPRIMARY KEY (tenant_id, game_id), \n\tCONSTRAINT "
            "fk_lifecycle_head_game FOREIGN KEY(tenant_id, game_id) "
            "REFERENCES games (tenant_id, id) ON DELETE NO ACTION, \n"
            "\tCONSTRAINT fk_lifecycle_head_control FOREIGN KEY(tenan"
            "t_id, last_control_event_id) REFERENCES operation_event"
            "s (tenant_id, id) ON DELETE NO ACTION DEFERRABLE INITIA"
            "LLY DEFERRED, \n\tCONSTRAINT fk_lifecycle_head_end FOREIG"
            "N KEY(tenant_id, active_end_event_id) REFERENCES operat"
            "ion_events (tenant_id, id) ON DELETE NO ACTION DEFERRAB"
            "LE INITIALLY DEFERRED, \n\tCONSTRAINT fk_lifecycle_head_s"
            "tats FOREIGN KEY(tenant_id, game_id, active_stats_versi"
            "on_id) REFERENCES sync_fence.stats_fact_versions (tenan"
            "t_id, game_id, id) ON DELETE NO ACTION DEFERRABLE INITI"
            "ALLY DEFERRED, \n\tCONSTRAINT ck_lifecycle_head_version C"
            "HECK (last_version>0), \n\tCONSTRAINT ck_lifecycle_head_a"
            "ctive CHECK ((is_finished AND active_end_event_id IS NO"
            "T NULL AND active_receipt_id IS NOT NULL AND active_sta"
            "ts_version_id IS NOT NULL) OR (NOT is_finished AND acti"
            "ve_end_event_id IS NULL AND active_receipt_id IS NULL A"
            "ND active_stats_version_id IS NULL))\n)\n\n"
        )
    )
    op.execute("ALTER TABLE sync_fence.game_lifecycle_heads OWNER TO pitchlog_owner")
    op.execute("ALTER TABLE sync_fence.game_lifecycle_heads ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sync_fence.game_lifecycle_heads FORCE ROW LEVEL SECURITY")
    op.execute(
        (
            "REVOKE ALL ON TABLE sync_fence.game_lifecycle_heads FRO"
            "M PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitch"
            "log_rg1_control_actor,pitchlog_sync_right_fn_owner"
        )
    )
    op.execute(
        (
            "CREATE FUNCTION public.protect_game_lifecycle_heads() R"
            "ETURNS trigger\nLANGUAGE plpgsql SET search_path=pg_cata"
            "log,pg_temp AS $guard$\nBEGIN\n IF TG_OP IN ('DELETE','TR"
            "UNCATE') OR current_user<>'pitchlog_sync_right_fn_owner"
            "'\n THEN RAISE EXCEPTION 'lifecycle private row protecte"
            "d' USING ERRCODE='42501'; END IF;\n\n IF TG_OP='UPDATE' A"
            "ND ((NEW.tenant_id,NEW.game_id) IS DISTINCT FROM\n (OLD."
            "tenant_id,OLD.game_id) OR NEW.last_control_event_id=OLD"
            ".last_control_event_id\n OR NEW.is_finished=OLD.is_finis"
            "hed OR\n NEW.last_version IS DISTINCT FROM OLD.last_vers"
            "ion+CASE WHEN NEW.is_finished THEN 1 ELSE 0 END)\n THEN "
            "RAISE EXCEPTION 'lifecycle head transition' USING ERRCO"
            "DE='42501'; END IF;\n IF TG_OP='INSERT' AND NOT EXISTS(S"
            "ELECT 1 FROM sync_fence.game_lifecycle_heads h\n WHERE h"
            ".tenant_id=NEW.tenant_id AND h.game_id=NEW.game_id)\n AN"
            "D (NEW.last_version<>1 OR NOT NEW.is_finished)\n THEN RA"
            "ISE EXCEPTION 'lifecycle head initial state' USING ERRC"
            "ODE='42501'; END IF;\n\n RETURN NEW;\nEND;\n$guard$;"
        )
    )
    op.execute(
        "ALTER FUNCTION public.protect_game_lifecycle_heads() OWNER TO pitchlog_owner"
    )
    op.execute(
        (
            "REVOKE ALL ON FUNCTION public.protect_game_lifecycle_he"
            "ads() FROM PUBLIC,pitchlog_app"
        )
    )
    op.execute(
        (
            "CREATE TRIGGER trg_game_lifecycle_heads_guard BEFORE IN"
            "SERT OR UPDATE OR DELETE ON sync_fence.game_lifecycle_h"
            "eads FOR EACH ROW EXECUTE FUNCTION public.protect_game_"
            "lifecycle_heads()"
        )
    )
    op.execute(
        (
            "CREATE TRIGGER trg_game_lifecycle_heads_no_truncate BEF"
            "ORE TRUNCATE ON sync_fence.game_lifecycle_heads FOR EAC"
            "H STATEMENT EXECUTE FUNCTION public.protect_game_lifecy"
            "cle_heads()"
        )
    )


def downgrade() -> None:
    """監査原本の物理削除を避けるため下降を閉じる。"""
    raise RuntimeError("ライフサイクル履歴の下降は非対応です")
