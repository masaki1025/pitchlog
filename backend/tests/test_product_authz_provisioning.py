"""製品認可 DDL の適用器が閉じた実行経路だけを持つことを検査する。

対象モジュール外では公開名 exact-set の名前付き from import だけを許し、対象モジュール
名の属性参照と module・star・集合外 import を拒否する。内部では末端参照 exact-set と
単一リテラルの __all__ を構造で検査し、値の流れは追わない。
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any, cast

import psycopg
import pytest
from first_ball_expected_source_pins import read_ci_followup_inputs
from psycopg import pq

from pitchlog.authz import product_provisioning
from pitchlog.authz.asset_spec import (
    PRODUCT_SPEC,
    ProductApplicationSteps,
    load_product_application_steps,
)
from pitchlog.authz.ddl import DDLStatement
from pitchlog.authz.product_provisioning import (
    ProductOperation,
    ProductProvisioningError,
    apply_product_authz_ddl,
)

# 終端prefixの正式7関数・runner有限10列（旧集合は維持）。
_TERMINAL_FUNCTION_IDS = frozenset(
    {
        "FUNCTION:sync_right_api:assert_play_prefix_projection(jsonb)",
        "FUNCTION:sync_right_api:finish_play_prefix_projection()",
        "FUNCTION:sync_right_api:guard_play_prefix_runner_insert()",
        (
            "FUNCTION:sync_right_api:lock_play_prefix_checkpoint(uuid, uuid, "
            "uuid, bytea, uuid, uuid, bigint)"
        ),
        (
            "FUNCTION:sync_right_api:prepare_play_prefix_projection(uuid, "
            "uuid, uuid, bytea, uuid, uuid, text)"
        ),
        "FUNCTION:sync_right_api:read_play_prefix_checkpoint(uuid, uuid, bigint)",
        (
            "FUNCTION:sync_right_api:read_play_prefix_history_page(uuid, "
            "uuid, bigint, bigint, uuid, bigint, bigint, bigint, bigint, "
            "bigint, uuid, integer)"
        ),
    }
)
_TERMINAL_COLUMN_ACL_IDS = frozenset(
    f"COLUMN-ACL:public:play_runners:{column}:pitchlog_sync_right_fn_owner"
    for column in (
        "tenant_id",
        "id",
        "play_id",
        "base",
        "runner_id",
        "status",
        "status_source",
        "responsible_pitcher_id",
        "import_batch_id",
        "retired_at",
    )
)


_LINEUP_FUNCTION_IDS = frozenset(
    {
        "FUNCTION:sync_right_api:read_lineup_started_origin(uuid, uuid, bigint)",
    }
)
_LINEUP_POLICY_IDS = frozenset(
    {
        "POLICY:game_start_attempts:lineup_prefix_game_start_attempts_select",
        "POLICY:game_start_requests:lineup_prefix_game_start_requests_select",
    }
)
_LINEUP_COLUMN_ACL_IDS = frozenset(
    f"COLUMN-ACL:public:{table}:{column}:pitchlog_sync_right_fn_owner"
    for table, columns in (
        (
            "game_start_attempts",
            ("tenant_id", "game_id", "device_id", "start_request_id", "outcome"),
        ),
        (
            "game_start_requests",
            ("tenant_id", "game_id", "device_id", "start_request_id"),
        ),
    )
    for column in columns
)


_LEGACY_CONTACT_SQL = {
    "current_database": "-- ELEMENT-TYPE: database\n"
    "-- ELEMENT-ID: current_database\n"
    "\n"
    "DO $authz$\n"
    "DECLARE\n"
    "    database_name TEXT := "
    "pg_catalog.current_database();\n"
    "BEGIN\n"
    "    EXECUTE pg_catalog.format(\n"
    "        'ALTER DATABASE %I OWNER TO "
    "pitchlog_owner',\n"
    "        database_name\n"
    "    );\n"
    "    EXECUTE pg_catalog.format(\n"
    "        'REVOKE ALL PRIVILEGES ON DATABASE %I "
    "FROM PUBLIC, pitchlog_app, "
    "pitchlog_shared_fn_owner, "
    "pitchlog_management_fn_owner',\n"
    "        database_name\n"
    "    );\n"
    "    EXECUTE pg_catalog.format(\n"
    "        'GRANT CONNECT ON DATABASE %I TO "
    "pitchlog_app',\n"
    "        database_name\n"
    "    );\n"
    "    EXECUTE pg_catalog.format('REVOKE CREATE, "
    "TEMPORARY ON DATABASE %I FROM "
    "pitchlog_rg1_control_actor', database_name);\n"
    "    EXECUTE pg_catalog.format('GRANT CONNECT ON "
    "DATABASE %I TO pitchlog_rg1_control_actor', "
    "database_name);\n"
    "    EXECUTE pg_catalog.format('REVOKE CREATE, "
    "TEMPORARY ON DATABASE %I FROM "
    "pitchlog_ledger_identity_probe', "
    "database_name);\n"
    "    EXECUTE pg_catalog.format('GRANT CONNECT ON "
    "DATABASE %I TO pitchlog_ledger_identity_probe', "
    "database_name);\n"
    "    EXECUTE pg_catalog.format('REVOKE CREATE, "
    "TEMPORARY ON DATABASE %I FROM "
    "pitchlog_initial_actor', database_name);\n"
    "    EXECUTE pg_catalog.format('GRANT CONNECT ON "
    "DATABASE %I TO pitchlog_initial_actor', "
    "database_name);\n"
    "END;\n"
    "$authz$;\n"
    "DO $authz$ BEGIN EXECUTE "
    "pg_catalog.format('GRANT CONNECT ON DATABASE %I "
    "TO pitchlog_initial_auth_verifier', "
    "pg_catalog.current_database()); EXECUTE "
    "pg_catalog.format('REVOKE CREATE, TEMPORARY ON "
    "DATABASE %I FROM "
    "pitchlog_initial_auth_verifier', "
    "pg_catalog.current_database()); END; $authz$;\n",
    "public": "-- ELEMENT-TYPE: schema\n"
    "-- ELEMENT-ID: public\n"
    "\n"
    "ALTER SCHEMA public OWNER TO pg_database_owner;\n"
    "REVOKE ALL PRIVILEGES ON SCHEMA public\n"
    "    FROM PUBLIC, pitchlog_app, pitchlog_shared_fn_owner, "
    "pitchlog_management_fn_owner, pitchlog_auth_fn_owner, "
    "pitchlog_rg1_fn_owner, pitchlog_rule_resolution_fn_owner;\n"
    "GRANT USAGE ON SCHEMA public TO pitchlog_app, "
    "pitchlog_shared_fn_owner, pitchlog_auth_fn_owner, "
    "pitchlog_rg1_fn_owner, pitchlog_rule_resolution_fn_owner;\n"
    "GRANT USAGE ON SCHEMA public TO "
    "pitchlog_rg1_control_owner;\n"
    "GRANT USAGE ON SCHEMA public TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE CREATE ON SCHEMA public FROM "
    "pitchlog_initial_fn_owner;\n"
    "GRANT USAGE ON SCHEMA public TO pitchlog_initial_actor;\n"
    "REVOKE CREATE ON SCHEMA public FROM "
    "pitchlog_initial_actor;\n",
}
_FIRST_BALL_CONTACT_SUFFIX = {
    "current_database": "\n"
    "DO $sync_connect$ BEGIN\n"
    " EXECUTE pg_catalog.format('GRANT CONNECT ON "
    "DATABASE %I TO "
    "pitchlog_sync_binding_actor',pg_catalog.current_database());\n"
    " EXECUTE pg_catalog.format('REVOKE "
    "CREATE,TEMPORARY ON DATABASE %I FROM "
    "pitchlog_sync_binding_actor',pg_catalog.current_database());\n"
    "END;$sync_connect$;\n",
    "public": "\n"
    "GRANT USAGE ON SCHEMA public TO "
    "pitchlog_sync_binding_fn_owner, "
    "pitchlog_sync_right_fn_owner;\n",
}
_RECORDING_VOCAB_PUBLIC_USAGE = (
    "\nGRANT USAGE ON SCHEMA public TO pitchlog_recording_vocab_fn_owner;\n"
)

# 新語彙readの1関数と既保存に必要な参照7列、専用ownerの4列だけ。
_BATTED_FUNCTION_IDS = frozenset(
    {"FUNCTION:recording_vocab_api:read_batted_ball_options(uuid, integer, text)"}
)
_BATTED_COLUMN_ACL_IDS = frozenset(
    f"COLUMN-ACL:public:{table}:{column}:{owner}"
    for table, columns, owner in (
        (
            "admin_vocabularies",
            ("category", "disabled", "key"),
            "pitchlog_sync_right_fn_owner",
        ),
        (
            "tenant_vocabularies",
            ("category", "disabled", "key", "tenant_id"),
            "pitchlog_sync_right_fn_owner",
        ),
        (
            "admin_vocabularies",
            ("category", "disabled", "display_name", "key"),
            "pitchlog_recording_vocab_fn_owner",
        ),
    )
    for column in columns
)


@pytest.fixture
def legacy_product_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[None]:
    """忠実な固定0036データを実公開適用器へ渡し、旧義務を検査する。"""
    from product_authz_legacy_profile import legacy_profile_context

    with legacy_profile_context(monkeypatch, tmp_path / "legacy-profile") as root:
        assert product_provisioning._REPOSITORY_ROOT == root
        legacy = json.loads((root / PRODUCT_SPEC.ddl_elements_path).read_text())
        assert [
            len(legacy[k]) for k in ("roles", "schemas", "tables", "functions")
        ] == [14, 8, 50, 79]
        assert PRODUCT_SPEC.application_steps_path is not None
        current_steps = json.loads(
            (_REPOSITORY_ROOT / PRODUCT_SPEC.application_steps_path).read_text()
        )
        helper_step = next(
            row for row in current_steps["application_steps"] if row["sequence"] == 3
        )
        assert helper_step["element_groups"].count("functions:invoker") == 1
        keys = {
            (section.element_type, row[section.id_field])
            for section in PRODUCT_SPEC.element_sections
            for row in legacy[section.section_name]
        }
        historical = product_provisioning.generate_authz_ddl(root, PRODUCT_SPEC)
        generated = product_provisioning.generate_authz_ddl(
            _REPOSITORY_ROOT, PRODUCT_SPEC
        )
        for statement in generated:
            if (
                statement.element_type in {"database", "schema"}
                and statement.element_id in _LEGACY_CONTACT_SQL
            ):
                key = statement.element_id
                current_sql = statement.sql
                if key == "public":
                    assert current_sql.count(_RECORDING_VOCAB_PUBLIC_USAGE) == 1
                    current_sql = current_sql.removesuffix(
                        _RECORDING_VOCAB_PUBLIC_USAGE
                    )
                assert (
                    current_sql
                    == _LEGACY_CONTACT_SQL[key] + _FIRST_BALL_CONTACT_SUFFIX[key]
                )
        assert {
            (statement.element_type, statement.element_id) for statement in historical
        } == keys
        yield


_EXPECTED_DEFERRED_ORDINARY_IDS = frozenset(
    {
        "COLUMN-ACL:public:operation_events:change_order:pitchlog_sync_right_fn_owner",
        (
            "COLUMN-ACL:public:operation_events:expected_version:pitchlog"
            "_sync_right_fn_owner"
        ),
        "COLUMN-ACL:public:operation_events:payload:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:state_diff:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:target_d1:pitchlog_sync_right_fn_owner",
        (
            "COLUMN-ACL:public:operation_events:target_generation:pitchlo"
            "g_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:public:play_rows:batted_ball_strength:pitchlog_sy"
            "nc_right_fn_owner"
        ),
        "COLUMN-ACL:public:play_rows:batted_ball_type:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:batter_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:batter_status:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:batting_order:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:batting_result_key:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:batting_side:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:catcher_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:comment:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:course_x:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:course_y:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:error_type:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:event_kind:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:fake_run:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:game_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:hidden_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:hit_x:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:hit_y:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:import_batch_id:pitchlog_sync_right_fn_owner",
        (
            "COLUMN-ACL:public:play_rows:legacy_row_identifier:pitchlog_s"
            "ync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:public:play_rows:migration_unverified:pitchlog_sy"
            "nc_right_fn_owner"
        ),
        "COLUMN-ACL:public:play_rows:pickoff_detail:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:pickoff_type:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:pitch_speed:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:pitch_type_key:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:pitcher_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:play_number:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:press:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:raw_error_position:pitchlog_sync_right_fn_owner",
        (
            "COLUMN-ACL:public:play_rows:raw_fielder_position:pitchlog_sy"
            "nc_right_fn_owner"
        ),
        (
            "COLUMN-ACL:public:play_rows:resolved_error_player_id:pitchlo"
            "g_sync_right_fn_owner"
        ),
        "COLUMN-ACL:public:play_rows:resolved_fielder_id:pitchlog_sync_right_fn_owner",
        (
            "COLUMN-ACL:public:play_rows:secondary_batting_result_key:pit"
            "chlog_sync_right_fn_owner"
        ),
        "COLUMN-ACL:public:play_rows:source_event_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:stance:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:strategy_detail_key:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:strategy_key:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:strategy_result_key:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:tenant_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:play_rows:version:pitchlog_sync_right_fn_owner",
        (
            "COLUMN-ACL:public:recording_generations:applied_prefix:pitch"
            "log_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:public:recording_generations:confirmed_watermark:"
            "pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:applied_wat"
            "ermark:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:confirmed_w"
            "atermark:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:content:pit"
            "chlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:content_dig"
            "est:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:game_id:pit"
            "chlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:history_ver"
            "sion:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:id:pitchlog"
            "_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:internal_ge"
            "neration:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:recovery_ge"
            "neration:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:revision:pi"
            "tchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:roster:pitc"
            "hlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:saved_at:pi"
            "tchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:state:pitch"
            "log_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:tenant_id:p"
            "itchlog_sync_right_fn_owner"
        ),
        "COLUMN-ACL:sync_fence:ordinary_pitch_history:d1:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:ordinary_pitch_history:d2:pitchlog_sync_right_fn_owner",
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_history:entry:pitchlog_"
            "sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_history:game_id:pitchlo"
            "g_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_history:history_version"
            ":pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_history:internal_genera"
            "tion:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_history:source_event_id"
            ":pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_history:tenant_id:pitch"
            "log_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:artifa"
            "ct_sha256:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:attemp"
            "t_id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:author"
            "ity_id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:backen"
            "d_pid:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:backen"
            "d_start:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:busine"
            "ss_instance:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:checkp"
            "oint_content:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:checkp"
            "oint_digest:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:checkp"
            "oint_id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:checkp"
            "oint_revision:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:codec_"
            "version:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:consum"
            "ed_at:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:contro"
            "l_instance:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:contro"
            "l_version:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:d5:pit"
            "chlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:databa"
            "se_oid:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:device"
            "_id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:event_"
            "fingerprint:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:expect"
            "ed_play_row:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:expire"
            "s_at:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:frame_"
            "digest:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:frame_"
            "id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:game_i"
            "d:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:histor"
            "y_entry:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:intern"
            "al_generation:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:issuer"
            ":pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:lease_"
            "id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:next_c"
            "heckpoint_content:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:nonce_"
            "digest:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:phase_"
            "id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:play_r"
            "ow_id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:postma"
            "ster_started_at:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:prefix"
            "_length:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:recove"
            "ry_generation:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:reques"
            "t_fingerprint:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:restor"
            "e_epoch:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:roster"
            "_snapshot:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:source"
            "_d1:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:source"
            "_d2:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:source"
            "_event_id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:state:"
            "pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:system"
            "_identifier:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:tenant"
            "_id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:transa"
            "ction_id:pitchlog_sync_right_fn_owner"
        ),
        (
            "COLUMN-ACL:sync_fence:ordinary_pitch_write_admissions:wire_d"
            "4:pitchlog_sync_right_fn_owner"
        ),
        (
            "FUNCTION:sync_right_api:bind_ordinary_device(uuid, uuid, uui"
            "d, bytea, uuid, uuid, bytea)"
        ),
        (
            "FUNCTION:sync_right_api:check_ordinary_right(uuid, uuid, uui"
            "d, bytea, uuid, uuid, bigint, bigint, bytea)"
        ),
        "FUNCTION:sync_right_api:consume_ordinary_projection(jsonb)",
        (
            "FUNCTION:sync_right_api:lock_ordinary_checkpoint(uuid, uuid,"
            " uuid, bytea, uuid, uuid, bigint)"
        ),
        (
            "FUNCTION:sync_right_api:prepare_ordinary_projection(uuid, uu"
            "id, uuid, bytea, uuid, uuid, text)"
        ),
        "FUNCTION:sync_right_api:read_ordinary_checkpoint(uuid, uuid, bigint)",
        (
            "FUNCTION:sync_right_api:read_ordinary_history_page(uuid, uui"
            "d, bigint, bigint, uuid, bigint, bigint, bigint, bigint, uui"
            "d, integer)"
        ),
        "FUNCTION:sync_right_api:read_ordinary_order_summary(uuid, uuid)",
    }
)


_EXPECTED_DEFERRED_FIRST_BALL_IDS = frozenset(
    {
        "COLUMN-ACL:public:idempotency_ledger:d5:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:idempotency_ledger:import_batch_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:idempotency_ledger:kind:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:idempotency_ledger:retired_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:idempotency_ledger:source_fingerprint:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:idempotency_ledger:tenant_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:d1:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:d2:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:d5:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:event_kind:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:game_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:generation:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:import_batch_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:is_tombstone:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:ledger_kind:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:legacy_row_identifier:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:migration_unverified:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:replaced_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:retired_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:operation_events:tenant_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:game_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:generation:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:holder_device:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:import_batch_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:kind:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:proof_digest:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:recovery_generation:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:retired_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:revoked_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:recording_generations:tenant_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:pitchlog_sync_binding_fn_owner",
        "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_sync_binding_fn_owner",
        "COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:rg1_restore_gate:state:pitchlog_sync_binding_fn_owner",
        "COLUMN-ACL:public:rg1_restore_gate:state:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:trusted_devices:credential_digest:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:trusted_devices:device_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:trusted_devices:revoked_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:public:trusted_devices:tenant_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:attempt_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:authority_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:backend_pid:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:backend_start:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:business_instance:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:codec_version:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:consumed_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:control_instance:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:control_version:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:d5:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:database_oid:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:device_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:event_fingerprint:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:expires_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:game_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:internal_generation:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:issuer:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:lease_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:nonce_digest:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:phase_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:play_row_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:postmaster_started_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:recovery_generation:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:request_fingerprint:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:restore_epoch:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:source_event_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:state:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:system_identifier:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:tenant_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:transaction_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:first_ball_write_admissions:wire_d4:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:attempt_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:authority_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:backend_pid:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:backend_start:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:business_instance:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:close_id:pitchlog_sync_binding_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:close_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:codec_version:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:control_instance:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:control_version:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:d5:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:database_oid:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:device_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:event_fingerprint:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:expires_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:game_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:internal_generation:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:issuer:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:lease_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:nonce_digest:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:phase_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:postmaster_started_at:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:recovery_generation:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:request_fingerprint:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:restore_epoch:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:state:pitchlog_sync_binding_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:state:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:system_identifier:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:tenant_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:transaction_id:pitchlog_sync_right_fn_owner",
        "COLUMN-ACL:sync_fence:writer_bindings:wire_d4:pitchlog_sync_right_fn_owner",
        "FUNCTION:sync_fence_api:assert_writer_binding(uuid, uuid, uuid, "
        "bytea, uuid, uuid)",
        "FUNCTION:sync_fence_api:close_writer_binding(uuid, uuid, uuid, uuid, uuid)",
        "FUNCTION:sync_fence_api:guard_writer_records()",
        "FUNCTION:sync_fence_api:observe_writer_binding(uuid, uuid, uuid, uuid, uuid)",
        "FUNCTION:sync_fence_api:publish_writer_binding(uuid, uuid, uuid, "
        "jsonb, bytea)",
        "FUNCTION:sync_fence_api:read_writer_database_identity(uuid)",
        "FUNCTION:sync_fence_api:read_writer_identity(uuid)",
        "FUNCTION:sync_right_api:bind_device(uuid, uuid, uuid, bytea, uuid, "
        "uuid, bytea)",
        "FUNCTION:sync_right_api:check_current_right(uuid, uuid, uuid, bytea, "
        "uuid, uuid, bigint, bigint, bytea)",
        "FUNCTION:sync_right_api:guard_first_ball_projection_admission()",
        "FUNCTION:sync_right_api:guard_first_ball_projection_lock()",
        "FUNCTION:sync_right_api:read_device_state(uuid, uuid)",
    }
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _REPOSITORY_ROOT / "backend/src"
_SOURCE_PATH = _REPOSITORY_ROOT / "backend/src/pitchlog/authz/product_provisioning.py"
_TERMINAL_MODULE = "pitchlog.authz.product_provisioning"
_TERMINAL_NAME = "_run_product_operation"
_TARGET_MODULE_ATTRIBUTE = "product_provisioning"
_PUBLIC_IMPORT_NAMES = frozenset(
    {
        "ProductOperation",
        "apply_product_authz_ddl",
        "apply_product_authz_before_rule_placement",
        "unapply_product_authz_ddl",
    }
)
_CURRENT_STARTUP_INTERNAL_IMPORTS = frozenset(
    {"_load_product_elements", "_selected_product_ddl"}
)
_EXPECTED_TERMINAL_SIGNATURE = (
    "_run_product_operation(connection: psycopg.Connection[Any], "
    "operation: ProductOperation) -> None"
)
_DB_METHOD_NAMES = {"cursor", "execute", "commit", "rollback"}


class _FakeInfo:
    """Psycopg 接続情報のうち適用器が読む状態だけを持つ。"""

    def __init__(
        self,
        connection: _FakeConnection,
        transaction_status: pq.TransactionStatus,
    ) -> None:
        self._connection = connection
        self.transaction_status = transaction_status

    def parameter_status(self, name: str) -> str | None:
        """サーバーが通知する接続主体の状態を試験値から返す。"""
        self._connection.parameter_status_calls.append(name)
        if name == "session_authorization":
            return self._connection.session_user
        if name == "is_superuser":
            return "on" if self._connection.is_superuser else "off"
        return None


class _FakeCursor:
    """識別問い合わせと生成 DDL を区別して記録する cursor。"""

    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection
        self._rows: tuple[tuple[object, ...], ...] = ()

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        del exc_type, exc_value, traceback

    def __iter__(self) -> Iterator[tuple[object, ...]]:
        return iter(self._rows)

    def execute(self, query: object) -> None:
        """識別問い合わせへ行を返し、それ以外を生成 DDL として記録する。"""
        self._connection.execute_calls.append(query)
        if query == product_provisioning._IDENTITY_QUERY:
            self._connection.identity_query_count += 1
            default_row = (
                self._connection.current_user,
                self._connection.session_user,
                self._connection.is_superuser,
            )
            self._rows = (
                self._connection.identity_overrides.get(
                    self._connection.identity_query_count,
                    default_row,
                ),
            )
            return
        self._rows = ()
        self._connection.executed_statements.append(query)


class _FakeConnection:
    """公開経路の前提・commit・rollback を観測する最小接続。"""

    def __init__(
        self,
        *,
        closed: bool = False,
        autocommit: bool = False,
        transaction_status: pq.TransactionStatus = pq.TransactionStatus.IDLE,
        current_user: str = "external_superuser",
        session_user: str = "external_superuser",
        is_superuser: bool = True,
    ) -> None:
        self.closed = closed
        self.autocommit = autocommit
        self.current_user = current_user
        self.session_user = session_user
        self.is_superuser = is_superuser
        self.info = _FakeInfo(self, transaction_status)
        self.execute_calls: list[object] = []
        self.executed_statements: list[object] = []
        self.parameter_status_calls: list[str] = []
        self.identity_query_count = 0
        self.identity_overrides: dict[int, tuple[object, ...]] = {}
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self) -> _FakeCursor:
        """試験用 cursor を返す。"""
        return _FakeCursor(self)

    def execute(self, query: object) -> _FakeCursor:
        """Connection.execute も cursor と同じ全数記録へ含める。"""
        cursor = self.cursor()
        cursor.execute(query)
        return cursor

    def commit(self) -> None:
        """Commit 呼び出し回数を記録する。"""
        self.commit_count += 1

    def rollback(self) -> None:
        """Rollback 呼び出し回数を記録する。"""
        self.rollback_count += 1


@pytest.fixture(scope="module")
def application_steps() -> ProductApplicationSteps:
    """正規の単一 transaction 手順を返す。"""
    return load_product_application_steps(_REPOSITORY_ROOT, PRODUCT_SPEC)


def _small_operation_plan(
    steps: ProductApplicationSteps,
) -> tuple[ProductApplicationSteps, tuple[product_provisioning._ProductStatement, ...]]:
    """公開経路の制御だけを観測する 7 手順の小さな計画を返す。"""
    statements = tuple(
        product_provisioning._ProductStatement(
            sequence=sequence,
            sql=f"SELECT {sequence}",
        )
        for sequence in range(1, len(steps.application_steps) + 1)
    )
    return steps, statements


def _module_name(source_root: Path, path: Path) -> str:
    """Backend source のパスを import 可能なモジュール名へ変換する。"""
    relative = path.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _source_modules(source_root: Path) -> dict[str, tuple[Path, str]]:
    """Source root 以下の全 Python モジュールを機械的に読む。"""
    return {
        _module_name(source_root, path): (path, path.read_text(encoding="utf-8"))
        for path in source_root.rglob("*.py")
    }


def _parse_source(source: str) -> ast.Module:
    """製品適用器ソースを AST として読む。"""
    return ast.parse(source, filename=str(_SOURCE_PATH))


def _as_psycopg_connection(
    connection: _FakeConnection,
) -> psycopg.Connection[Any]:
    """試験用接続を公開 API の型境界へ明示的に渡す。"""
    return cast(psycopg.Connection[Any], connection)


def _function_ancestors(tree: ast.Module) -> dict[ast.AST, str]:
    """各 AST node を包含する最内の関数名へ対応付ける。"""
    result: dict[ast.AST, str] = {}

    def visit(node: ast.AST, function_name: str = "<module>") -> None:
        next_name = node.name if isinstance(node, ast.FunctionDef) else function_name
        result[node] = next_name
        for child in ast.iter_child_nodes(node):
            visit(child, next_name)

    visit(tree)
    return result


def _absolute_import_from(
    module_name: str,
    path: Path,
    node: ast.ImportFrom,
) -> str | None:
    """ImportFrom の level と現在位置から import 元の絶対名を返す。"""
    if node.level == 0:
        return node.module
    current_package = (
        module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
    )
    package_parts = current_package.split(".") if current_package else []
    parent_count = node.level - 1
    if parent_count > len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - parent_count]
    if node.module is not None:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts) if base_parts else None


def _assert_external_import_shape(
    module_name: str,
    path: Path,
    tree: ast.Module,
) -> None:
    """対象外モジュールでは公開 exact-set の名前付き import だけを許可する。"""
    if module_name == _TERMINAL_MODULE:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == _TARGET_MODULE_ATTRIBUTE:
            raise AssertionError("製品適用器名の属性参照は禁止")
        if isinstance(node, ast.Import):
            if any(
                alias.name == _TERMINAL_MODULE
                or alias.name.startswith(f"{_TERMINAL_MODULE}.")
                for alias in node.names
            ):
                raise AssertionError("製品適用器モジュール自体の import は禁止")
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        imported_from = _absolute_import_from(module_name, path, node)
        if imported_from is None:
            continue
        if imported_from == _TERMINAL_MODULE:
            if any(alias.name == "*" for alias in node.names):
                raise AssertionError("製品適用器モジュールの import * は禁止")
            permitted = _PUBLIC_IMPORT_NAMES | (
                _CURRENT_STARTUP_INTERNAL_IMPORTS
                if module_name == "pitchlog.db.current_product_startup"
                else frozenset()
            )
            unexpected_names = {
                alias.name for alias in node.names if alias.name not in permitted
            }
            if unexpected_names:
                raise AssertionError(
                    "製品適用器モジュールの公開名 exact-set 外の import は禁止: "
                    f"{sorted(unexpected_names)}"
                )
            continue
        if any(
            f"{imported_from}.{alias.name}" == _TERMINAL_MODULE for alias in node.names
        ):
            raise AssertionError("製品適用器モジュール自体の from import は禁止")


def _assert_public_import_names_exist(tree: ast.Module) -> None:
    """許可した公開名が対象モジュールの最上位にすべて存在することを検査する。"""
    defined_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }
    if not _PUBLIC_IMPORT_NAMES <= defined_names:
        raise AssertionError("製品適用器の公開名 exact-set に存在しない名前がある")


def _assert_literal_module_all(tree: ast.Module) -> None:
    """__all__ を最上位の単一文字列リテラル代入だけに限定する。"""
    all_uses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "__all__"
    ]
    if not all_uses:
        return
    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
        and any(
            isinstance(target_node, ast.Name) and target_node.id == "__all__"
            for target in (
                node.targets if isinstance(node, ast.Assign) else (node.target,)
            )
            for target_node in ast.walk(target)
        )
    ]
    mutations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "__all__"
    ]
    if (
        len(writes) != 1
        or writes[0] not in tree.body
        or not isinstance(writes[0], ast.Assign)
        or len(writes[0].targets) != 1
        or not isinstance(writes[0].targets[0], ast.Name)
        or mutations
    ):
        raise AssertionError("製品適用器の __all__ は最上位の単一代入が必要")
    value = writes[0].value
    if not isinstance(value, (ast.List, ast.Tuple)) or not all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in value.elts
    ):
        raise AssertionError("製品適用器の __all__ は文字列リテラルだけが必要")
    exported_names = tuple(cast(ast.Constant, element).value for element in value.elts)
    if _TERMINAL_NAME in exported_names:
        raise AssertionError("製品適用器の末端を __all__ へ公開できない")


def _internal_terminal_references(
    tree: ast.Module,
) -> tuple[tuple[ast.expr, str], ...]:
    """対象モジュール内部にある末端名・属性の参照を全数返す。"""
    ancestors = _function_ancestors(tree)
    return tuple(
        (node, ancestors[node])
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == _TERMINAL_NAME
        )
        or (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == _TERMINAL_NAME
        )
    )


def _validate_terminal_boundary(source_root: Path) -> None:
    """全 backend/src で末端のシグネチャ・参照集合を検査する。"""
    modules = _source_modules(source_root)
    if _TERMINAL_MODULE not in modules:
        raise AssertionError("製品適用器モジュールが存在しない")
    trees = {
        module_name: ast.parse(source, filename=str(path))
        for module_name, (path, source) in modules.items()
    }
    tree = trees[_TERMINAL_MODULE]
    terminals = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_product_operation"
    ]
    if len(terminals) != 1:
        raise AssertionError("製品適用器の末端関数が一意でない")
    terminal = terminals[0]
    if terminal.returns is None:
        raise AssertionError("製品適用器の末端に戻り値注釈がない")
    rendered_signature = (
        f"{terminal.name}({ast.unparse(terminal.args)}) -> "
        f"{ast.unparse(terminal.returns)}"
    )
    if rendered_signature != _EXPECTED_TERMINAL_SIGNATURE:
        raise AssertionError("製品適用器の末端シグネチャが登録値と一致しない")

    for observed_module, module_tree in trees.items():
        _assert_external_import_shape(
            observed_module,
            modules[observed_module][0],
            module_tree,
        )
    _assert_public_import_names_exist(tree)
    _assert_literal_module_all(tree)

    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    references: list[str] = []
    for node, function_name in _internal_terminal_references(tree):
        parent = parents.get(node)
        if not isinstance(parent, ast.Call) or parent.func is not node:
            raise AssertionError("製品適用器の末端が直接呼び出し以外で参照された")
        references.append(function_name)
    if sorted(references) != [
        "apply_product_authz_before_rule_placement",
        "apply_product_authz_ddl",
        "unapply_product_authz_ddl",
    ]:
        raise AssertionError("製品適用器の末端を参照する関数が exact-set でない")

    ancestors = _function_ancestors(tree)
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _DB_METHOD_NAMES
        ):
            continue
        if ancestors[node] != "_run_product_operation":
            raise AssertionError("DB 呼び出しが製品適用器の末端外にある")


def test_terminal_boundary_is_closed_and_has_exact_references() -> None:
    """末端は登録シグネチャを持ち、公開 2 関数だけから直接参照される。"""
    _validate_terminal_boundary(_SOURCE_ROOT)


def test_adding_statement_or_asset_path_argument_is_red(tmp_path: Path) -> None:
    """末端に文や資産の置き場を渡せる引数を足す変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = source.replace(
        "    operation: ProductOperation,\n) -> None:",
        "    operation: ProductOperation,\n    asset_root: Path,\n) -> None:",
        1,
    )
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")
    with pytest.raises(AssertionError, match="シグネチャ"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "extra_reference",
    [
        pytest.param("_run_product_operation", id="name"),
        pytest.param(
            "product_provisioning._run_product_operation",
            id="attribute",
        ),
    ],
)
def test_adding_a_terminal_reference_is_red(
    extra_reference: str,
    tmp_path: Path,
) -> None:
    """同じモジュール内に末端の名前・属性参照を足す変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = f"{source}\n_EXTRA_RUNNER = {extra_reference}\n"
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")
    with pytest.raises(AssertionError, match="直接呼び出し"):
        _validate_terminal_boundary(tmp_path)


def test_calling_terminal_through_an_alias_is_red(tmp_path: Path) -> None:
    """公開関数が末端を別名へ代入して呼ぶ変異を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = source.replace(
        "    _run_product_operation(connection, ProductOperation.APPLY)",
        "    runner = _run_product_operation\n"
        "    runner(connection, ProductOperation.APPLY)",
        1,
    )
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")
    with pytest.raises(AssertionError, match="直接呼び出し"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "rogue_source",
    [
        pytest.param(
            "import pitchlog.authz.product_provisioning\n",
            id="absolute-module-import",
        ),
        pytest.param(
            "from pitchlog.authz import product_provisioning\n",
            id="from-parent-module-import",
        ),
        pytest.param(
            "from . import product_provisioning\n",
            id="relative-module-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import *\n",
            id="star-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import _run_product_operation\n",
            id="terminal-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import _ProductStatement\n",
            id="other-private-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import _load_product_elements\n",
            id="current-startup-private-from-other-module",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import PRODUCT_SPEC\n",
            id="asset-spec-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import "
            "load_product_application_steps\n",
            id="asset-loader-import",
        ),
        pytest.param(
            "from pitchlog.authz.product_provisioning import generate_authz_ddl\n",
            id="statement-generator-import",
        ),
    ],
)
def test_external_import_shapes_outside_the_closed_rule_are_red(
    rogue_source: str,
    tmp_path: Path,
) -> None:
    """外部では公開名の名前付き from import 以外をすべて拒否する。"""
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    rogue = tmp_path / "pitchlog/authz/rogue.py"
    rogue.write_text(rogue_source, encoding="utf-8")

    with pytest.raises(AssertionError, match="import"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize("public_name", sorted(_PUBLIC_IMPORT_NAMES))
def test_public_named_import_from_another_module_is_green(
    public_name: str,
    tmp_path: Path,
) -> None:
    """外部から公開 exact-set の部分集合を名前付き import する形は許可する。"""
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    consumer = tmp_path / "pitchlog/consumer.py"
    consumer.write_text(
        "from pitchlog.authz.product_provisioning import "
        f"{public_name} as public_api\n",
        encoding="utf-8",
    )

    _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "rogue_source",
    [
        pytest.param(
            "import pitchlog.authz\n_MODULE = pitchlog.authz.product_provisioning\n",
            id="absolute-parent-attribute",
        ),
        pytest.param(
            "import pitchlog\n_MODULE = pitchlog.authz.product_provisioning\n",
            id="absolute-root-attribute",
        ),
        pytest.param(
            "from .. import authz\n_MODULE = authz.product_provisioning\n",
            id="relative-parent-attribute",
        ),
    ],
)
def test_target_module_name_attribute_reference_is_red(
    rogue_source: str,
    tmp_path: Path,
) -> None:
    """対象モジュール名と同じ属性の参照を由来によらず拒否する。"""
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    rogue = tmp_path / "pitchlog/authz/rogue.py"
    rogue.write_text(rogue_source, encoding="utf-8")

    with pytest.raises(AssertionError, match="属性参照"):
        _validate_terminal_boundary(tmp_path)


@pytest.mark.parametrize(
    "all_source",
    [
        pytest.param(
            '__all__ = ("_run_product_operation",)\n',
            id="terminal-literal",
        ),
        pytest.param(
            '_EXPORTED = ("_run_product_operation",)\n__all__ = _EXPORTED\n',
            id="name-indirection",
        ),
        pytest.param(
            '__all__ = ("_run_" + "product_operation",)\n',
            id="string-concatenation",
        ),
        pytest.param(
            '__all__ = ("apply_product_authz_ddl",)\n'
            '__all__ += ("_run_product_operation",)\n',
            id="augmented-assignment",
        ),
        pytest.param(
            '__all__ = ["apply_product_authz_ddl"]\n'
            '__all__.append("_run_product_operation")\n',
            id="append",
        ),
        pytest.param(
            '__all__ = ["apply_product_authz_ddl"]\n'
            '__all__.extend(["_run_product_operation"])\n',
            id="extend",
        ),
    ],
)
def test_nonliteral_or_terminal_module_all_is_red(
    all_source: str,
    tmp_path: Path,
) -> None:
    """__all__ の間接構築・追記・末端公開を拒否する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    mutated = f"{source}\n{all_source}"
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(mutated, encoding="utf-8")

    with pytest.raises(AssertionError, match="__all__"):
        _validate_terminal_boundary(tmp_path)


def test_literal_public_module_all_is_green(tmp_path: Path) -> None:
    """公開名だけの単一リテラル __all__ は許可する。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    exports = ", ".join(repr(name) for name in sorted(_PUBLIC_IMPORT_NAMES))
    target = tmp_path / "pitchlog/authz/product_provisioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(f"{source}\n__all__ = ({exports},)\n", encoding="utf-8")

    _validate_terminal_boundary(tmp_path)


@pytest.mark.usefixtures("legacy_product_profile")
def test_generated_apply_and_unapply_statements_never_change_subject() -> None:
    """正規資産から作る適用・取り外し文に主体変更が 1 件もない。"""
    for operation in ProductOperation:
        steps, statements = product_provisioning._build_operation_statements(operation)
        assert steps.transaction == "single"
        assert {statement.sequence for statement in statements} == set(
            range(1, len(steps.application_steps) + 1)
        )
        product_provisioning._assert_no_subject_change(statements)

    _, apply_statements = product_provisioning._build_operation_statements(
        ProductOperation.APPLY
    )
    policy_statements = tuple(
        statement for statement in apply_statements if statement.sequence == 5
    )
    assert policy_statements
    assert all(
        statement.sql.startswith("DROP POLICY IF EXISTS")
        for statement in policy_statements
    )

    _, unapply_statements = product_provisioning._build_operation_statements(
        ProductOperation.UNAPPLY
    )
    policy_sequences = {
        statement.sequence
        for statement in unapply_statements
        if "DROP POLICY" in statement.sql
    }
    helper_sequences = {
        statement.sequence
        for statement in unapply_statements
        if "tenant_has_effective_membership" in statement.sql
    }
    assert policy_sequences == {3}
    assert helper_sequences == {5}
    assert all(
        "DROP ROLE IF EXISTS pitchlog_owner" not in row.sql
        for row in unapply_statements
    )


@pytest.mark.usefixtures("legacy_product_profile")
def test_generated_unapply_statements_use_structured_quoted_identifiers() -> None:
    """取り外し全文は要素 ID を SQL に流さず全識別子を正しく引用する。"""
    _, statements = product_provisioning._build_operation_statements(
        ProductOperation.UNAPPLY
    )
    sql_texts = tuple(statement.sql for statement in statements)
    assert sql_texts
    assert all(
        "FUNCTION:" not in sql_text and ":" not in sql_text for sql_text in sql_texts
    )

    trigger_function_grants = tuple(
        sql_text
        for sql_text in sql_texts
        if sql_text.startswith("GRANT EXECUTE ON FUNCTION")
    )
    asset = product_provisioning._load_product_elements()
    assert len(trigger_function_grants) == sum(
        element.element_type == "function"
        and element.fields.get("function_kind") == "migration_trigger"
        and element.fields.get("function_id")
        != "FUNCTION:public:protect_initial_right_storage()"
        for element in asset
    )
    trigger_function_pattern = re.compile(
        r'^GRANT EXECUTE ON FUNCTION "public"\."[a-z0-9_]+"\(\) TO PUBLIC;$'
    )
    assert all(
        trigger_function_pattern.fullmatch(sql_text) is not None
        for sql_text in trigger_function_grants
    )
    assert (
        'REVOKE EXECUTE ON FUNCTION "public".'
        '"protect_initial_right_storage"() FROM PUBLIC;' in sql_texts
    )
    assert (
        'DROP FUNCTION IF EXISTS "authz_private".'
        '"tenant_has_effective_membership"(uuid, boolean);' in sql_texts
    )

    assert 'DROP ROLE IF EXISTS "pitchlog_app";' in sql_texts
    assert 'DROP SCHEMA IF EXISTS "authz_private";' in sql_texts
    assert any(
        'ALTER TABLE "public"."tenants" NO FORCE ROW LEVEL SECURITY;' in sql_text
        for sql_text in sql_texts
    )
    assert (
        'DROP POLICY IF EXISTS "pitchlog_app_self_tenant_row" '
        'ON "public"."tenants";' in sql_texts
    )
    assert (
        'REVOKE ALL PRIVILEGES ON TABLE "public"."team_records" '
        'FROM "pitchlog_app";' in sql_texts
    )
    assert (
        'REVOKE SELECT ("id") ON TABLE "public"."tenants" '
        'FROM "pitchlog_shared_fn_owner";' in sql_texts
    )
    assert (
        'REVOKE SELECT ("singleton_id"), UPDATE ("singleton_id") '
        'ON TABLE "public"."rg1_restore_gate" '
        'FROM "pitchlog_rg1_fn_owner";' in sql_texts
    )
    database_statements = tuple(
        sql_text for sql_text in sql_texts if "ON DATABASE %I" in sql_text
    )
    assert len(database_statements) == 1
    for element in asset:
        if element.element_type == "role" and element.fields.get("creation") == (
            "product_ddl"
        ):
            assert f'"{element.element_id}"' in database_statements[0]


def test_unapply_restores_migration_regular_function_initial_acl() -> None:
    """通常関数は残し、直接付与を外して migration 直後の PUBLIC を戻す。"""
    element = product_provisioning._ProductElement(
        element_type="function",
        element_id="FUNCTION:public:step4_ordinary()",
        fields={
            "schema_name": "public",
            "function_name": "step4_ordinary",
            "identity_args": "",
            "function_kind": "migration_function",
        },
    )
    statement = DDLStatement(
        element_type="function",
        element_id=element.element_id,
        source_path=PurePosixPath("test.sql"),
        sql="REVOKE EXECUTE ON FUNCTION public.step4_ordinary() FROM PUBLIC;",
    )
    sql_text = product_provisioning._unapplication_sql(
        statement, element, (element,), ()
    )
    assert sql_text is not None
    assert "pg_catalog.aclexplode(procedure.proacl)" in sql_text
    assert "FROM %I CASCADE" in sql_text
    assert (
        'GRANT EXECUTE ON FUNCTION "public"."step4_ordinary"() TO PUBLIC;' in sql_text
    )
    assert "DROP FUNCTION" not in sql_text


def test_definer_unapplication_never_restores_public_execute() -> None:
    """definerの取り外しは関数を落とし、PUBLIC実行権を復帰しない。"""
    from pitchlog.authz.ddl import DDLStatement

    fields: dict[str, object] = {
        "schema_name": "authn",
        "function_name": "test_definer",
        "identity_args": "text",
        "function_kind": "definer",
    }
    element = product_provisioning._ProductElement(
        "function", "FUNCTION:authn:test_definer(text)", fields
    )
    statement = DDLStatement(
        element_type="function",
        element_id=element.element_id,
        source_path=PurePosixPath(
            "contracts/authz/product/function-bodies/functions/test.sql"
        ),
        sql=(
            "CREATE FUNCTION authn.test_definer(text) RETURNS text "
            "LANGUAGE sql AS 'SELECT $1';"
        ),
    )
    sql_text = product_provisioning._unapplication_sql(
        statement, element, (element,), ()
    )
    assert sql_text == 'DROP FUNCTION IF EXISTS "authn"."test_definer"(text);'
    assert "TO PUBLIC" not in sql_text


def test_product_identifier_quoting_escapes_embedded_double_quotes() -> None:
    """識別子引用は PostgreSQL の二重引用符規則に従う。"""
    assert product_provisioning._quote_identifier('schema"name') == ('"schema""name"')


def _validate_assembly_element_id_reads(source: str) -> None:
    """IDは専用helperへのexact1引渡し以外のSQL組立に使用させない。"""
    tree = _parse_source(source)
    assembly_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_application_statements", "_unapplication_sql"}
    }
    assert set(assembly_functions) == {
        "_application_statements",
        "_unapplication_sql",
    }
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    for function in assembly_functions.values():
        element_id_reads = tuple(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == "element_id"
        )
        if function.name == "_unapplication_sql":
            assert element_id_reads == ()
            continue
        assert len(element_id_reads) == 1
        read = element_id_reads[0]
        call = parents[read]
        assert isinstance(call, ast.Call)
        assert (
            isinstance(call.func, ast.Name)
            and call.func.id == "application_function_sql"
        )
        assert len(call.args) == 2
        assert call.args[0] is read
        assert isinstance(call.args[1], ast.Name) and call.args[1].id == "sql_text"
        assert isinstance(read.value, ast.Name) and read.value.id == "statement"
        assert call.keywords == []


def test_apply_and_unapply_sql_assembly_never_reads_element_id() -> None:
    """専用選択helperへの引渡しを除き、IDをSQLへ流せない。"""
    _validate_assembly_element_id_reads(_SOURCE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "replacement",
    [
        "application_function_sql(statement.element_id.split(':')[0], sql_text)",
        "application_function_sql(sql_text, statement.element_id)",
        "application_function_sql(statement.element_id, statement.element_id)",
        "application_function_sql(statement.element_id + sql_text, sql_text)",
    ],
)
def test_element_id_selection_does_not_allow_sql_construction(replacement: str) -> None:
    """ID分割・順序付替え・複製・連結を一般の許可へ拡張しない。"""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    original = "application_function_sql(statement.element_id, sql_text)"
    assert source.count(original) == 1
    with pytest.raises(AssertionError):
        _validate_assembly_element_id_reads(source.replace(original, replacement))


def test_public_apply_executes_the_canonical_generated_plan() -> None:
    """公開適用経路が正規資産の生成結果を実際の実行文として使う。"""
    connection = _FakeConnection()

    apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert len(connection.executed_statements) == len(
        product_provisioning._build_operation_statements(ProductOperation.APPLY)[1]
    )
    decoded = tuple(
        statement.decode("utf-8")
        for statement in connection.executed_statements
        if isinstance(statement, bytes)
    )
    assert len(decoded) == len(connection.executed_statements)
    helper_position = next(
        index
        for index, statement in enumerate(decoded)
        if "CREATE OR REPLACE FUNCTION authz_private.tenant_has_effective_membership"
        in statement
    )
    first_policy_position = next(
        index
        for index, statement in enumerate(decoded)
        if statement.startswith("DROP POLICY IF EXISTS")
    )
    assert helper_position < first_policy_position
    assert connection.commit_count == 1
    assert connection.rollback_count == 0


def test_apply_uses_one_transaction_and_checks_identity_at_every_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """公開適用経路は 7 手順を 1 回だけ commit し全記録点で主体を検査する。"""
    connection = _FakeConnection()
    checkpoints: list[str] = []
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: _small_operation_plan(application_steps),
    )
    monkeypatch.setattr(
        product_provisioning,
        "_record_product_checkpoint",
        checkpoints.append,
    )

    apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.executed_statements == [
        f"SELECT {sequence}".encode()
        for sequence in range(1, len(application_steps.application_steps) + 1)
    ]
    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    assert connection.autocommit is False
    assert checkpoints == [
        "product:1:after",
        "product:3:after_helper_function_creation",
        "product:4:after",
        "product:5:after_policy_creation",
        "product:6:during",
        "product:7:after_commit",
    ]
    assert connection.identity_query_count == len(checkpoints)
    assert connection.parameter_status_calls == [
        "session_authorization",
        "is_superuser",
    ]


@pytest.mark.parametrize(
    ("identity_query_number", "expected_commit_count", "expected_rollback_count"),
    [
        pytest.param(1, 0, 1, id="step-1"),
        pytest.param(2, 0, 1, id="step-3-helper"),
        pytest.param(3, 0, 1, id="step-4"),
        pytest.param(4, 0, 1, id="step-5-policy"),
        pytest.param(5, 0, 1, id="step-6-during"),
        pytest.param(6, 1, 0, id="after-commit"),
    ],
)
def test_identity_mismatch_at_each_checkpoint_is_red_through_public_path(
    identity_query_number: int,
    expected_commit_count: int,
    expected_rollback_count: int,
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """各記録点で current_user が変わる変異を公開適用経路が拒否する。"""
    connection = _FakeConnection()
    connection.identity_overrides[identity_query_number] = (
        "changed_subject",
        "external_superuser",
        True,
    )
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: _small_operation_plan(application_steps),
    )

    with pytest.raises(ProductProvisioningError, match="current_user"):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.commit_count == expected_commit_count
    assert connection.rollback_count == expected_rollback_count


def test_identity_mismatch_after_rollback_is_red_through_public_path(
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """故障後の rollback 記録点でも主体不一致を公開経路が拒否する。"""
    connection = _FakeConnection()
    connection.identity_overrides[2] = (
        "changed_subject",
        "external_superuser",
        True,
    )
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: _small_operation_plan(application_steps),
    )

    def fail_at_checkpoint(checkpoint_id: str) -> None:
        raise RuntimeError(checkpoint_id)

    monkeypatch.setattr(
        product_provisioning,
        "_record_product_checkpoint",
        fail_at_checkpoint,
    )

    with pytest.raises(ProductProvisioningError, match="current_user"):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.commit_count == 0
    assert connection.rollback_count == 1
    assert connection.autocommit is False


@pytest.mark.parametrize(
    ("connection", "message"),
    [
        pytest.param(_FakeConnection(closed=True), "閉じた接続", id="closed"),
        pytest.param(_FakeConnection(autocommit=True), "autocommit", id="autocommit"),
        pytest.param(
            _FakeConnection(transaction_status=pq.TransactionStatus.INTRANS),
            "進行中のトランザクション",
            id="transaction-not-idle",
        ),
        pytest.param(
            _FakeConnection(is_superuser=False),
            "superuser",
            id="not-superuser",
        ),
        pytest.param(
            _FakeConnection(
                current_user="pitchlog_app",
                session_user="pitchlog_app",
                is_superuser=True,
            ),
            "pitchlog_app",
            id="pitchlog-app",
        ),
    ],
)
def test_each_connection_precondition_rejects_before_generated_statements(
    connection: _FakeConnection,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """各接続前提の違反は公開経路で DDL・commit・rollback より先に拒否する。"""
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: _small_operation_plan(application_steps),
    )

    with pytest.raises(ProductProvisioningError, match=message):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.executed_statements == []
    assert connection.execute_calls == []
    assert connection.commit_count == 0
    assert connection.rollback_count == 0


def test_missing_session_authorization_is_fail_closed_without_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """接続主体の通知値が欠けても SQL を使った推測へ進まず拒否する。"""
    connection = _FakeConnection()

    def parameter_status(name: str) -> str | None:
        return None if name == "session_authorization" else "on"

    monkeypatch.setattr(connection.info, "parameter_status", parameter_status)

    with pytest.raises(ProductProvisioningError, match="session_authorization"):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.execute_calls == []
    assert connection.commit_count == 0
    assert connection.rollback_count == 0


def test_subject_change_inside_one_step_is_red_through_public_path(
    monkeypatch: pytest.MonkeyPatch,
    application_steps: ProductApplicationSteps,
) -> None:
    """途中だけ SET/RESET ROLE する文も公開適用経路が実行前に拒否する。"""
    connection = _FakeConnection()
    _, statements = _small_operation_plan(application_steps)
    mutated = tuple(
        product_provisioning._ProductStatement(
            sequence=statement.sequence,
            sql=(
                f"SET ROLE pitchlog_owner;\n{statement.sql};\nRESET ROLE;"
                if statement.sequence == 4
                else statement.sql
            ),
        )
        for statement in statements
    )
    monkeypatch.setattr(
        product_provisioning,
        "_build_operation_statements",
        lambda operation: (application_steps, mutated),
    )

    with pytest.raises(ProductProvisioningError, match="適用主体を変更"):
        apply_product_authz_ddl(_as_psycopg_connection(connection))

    assert connection.executed_statements == []
    assert connection.execute_calls == []
    assert connection.commit_count == 0
    assert connection.rollback_count == 0


_EXPECTED_DEFERRED_INITIAL_IDS = frozenset(
    {
        "COLUMN-ACL:public:game_lineups:team_record_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:game_start_attempts:outcome:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:team_records:hidden_at:pitchlog_initial_actor",
        "COLUMN-ACL:public:team_records:id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:game_start_attempts:tenant_id:pitchlog_initial_fn_owner",
        (
            "COLUMN-ACL:public:recording_right_deliveries:tenant_id:pitchlog_init"
            "ial_fn_owner"
        ),
        "FUNCTION:initial_right_api:lock_device(uuid, uuid)",
        "FUNCTION:public:protect_initial_right_storage()",
        "COLUMN-ACL:public:team_records:id:pitchlog_initial_actor",
        (
            "COLUMN-ACL:public:recording_right_deliveries:ciphertext:pitchlog_ini"
            "tial_fn_owner"
        ),
        (
            "COLUMN-ACL:public:game_lineups:entries_with_uniform_number_snapshot:"
            "pitchlog_initial_fn_owner"
        ),
        "FUNCTION:initial_right_api:lock_current_start(uuid, uuid, uuid)",
        (
            "COLUMN-ACL:public:recording_generations:recovery_generation:pitchlog"
            "_initial_fn_owner"
        ),
        "COLUMN-ACL:public:players:uniform_number:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:games:applied_rules:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:players:hidden_at:pitchlog_initial_actor",
        "COLUMN-ACL:public:players:tenant_id:pitchlog_initial_actor",
        "COLUMN-ACL:public:game_lineups:id:pitchlog_initial_fn_owner",
        "FUNCTION:initial_right_api:read_existing_start(uuid, uuid, uuid)",
        (
            "FUNCTION:initial_right_api:persist_initial_start(uuid, uuid, uuid, u"
            "uid, bytea, text)"
        ),
        (
            "FUNCTION:initial_right_api:insert_initial_grant(uuid, uuid, uuid, uu"
            "id, uuid, bigint, bigint, bytea, text, bytea, bytea)"
        ),
        (
            "COLUMN-ACL:public:recording_right_deliveries:game_id:pitchlog_initia"
            "l_fn_owner"
        ),
        "COLUMN-ACL:public:game_start_attempts:resolved_at:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:team_records:tenant_id:pitchlog_initial_actor",
        "FUNCTION:initial_right_api:check_business_epoch(uuid, bigint)",
        "COLUMN-ACL:public:recording_right_deliveries:key_id:pitchlog_initial_fn_owner",
        (
            "COLUMN-ACL:public:game_start_requests:start_request_id:pitchlog_init"
            "ial_fn_owner"
        ),
        "COLUMN-ACL:public:game_start_attempts:game_id:pitchlog_initial_fn_owner",
        "FUNCTION:initial_right_api:resolve_start_attempt(uuid, uuid, uuid, uuid)",
        "COLUMN-ACL:public:games:hidden_at:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:game_start_requests:device_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:players:roster_status_key:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:trusted_devices:tenant_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:trusted_devices:device_id:pitchlog_initial_fn_owner",
        (
            "COLUMN-ACL:public:game_start_attempts:start_request_id:pitchlog_init"
            "ial_fn_owner"
        ),
        "COLUMN-ACL:public:lineup_memories:id:pitchlog_initial_actor",
        "COLUMN-ACL:public:games:home_team_record_id:pitchlog_initial_fn_owner",
        (
            "FUNCTION:initial_right_api:read_initial_start_context(uuid, uuid, uu"
            "id, uuid, bytea, text)"
        ),
        "COLUMN-ACL:public:players:roster_status_key:pitchlog_initial_actor",
        (
            "COLUMN-ACL:public:recording_generations:proof_digest:pitchlog_initia"
            "l_fn_owner"
        ),
        "COLUMN-ACL:public:players:id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:lineup_memories:lineup:pitchlog_initial_actor",
        (
            "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:pitchlog_init"
            "ial_fn_owner"
        ),
        "COLUMN-ACL:public:players:id:pitchlog_initial_actor",
        (
            "COLUMN-ACL:public:recording_right_deliveries:start_request_id:pitchl"
            "og_initial_fn_owner"
        ),
        "FUNCTION:initial_right_api:lock_preparing_game(uuid, uuid)",
        "COLUMN-ACL:public:game_start_attempts:device_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:game_start_requests:tenant_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:trusted_devices:credential_digest:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:lineup_memories:team_record_id:pitchlog_initial_actor",
        "COLUMN-ACL:public:players:tenant_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:players:hidden_at:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:games:trashed_at:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:game_start_attempts:attempt_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:team_records:hidden_at:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:game_start_requests:game_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:game_lineups:game_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:game_lineups:tenant_id:pitchlog_initial_fn_owner",
        "FUNCTION:initial_right_api:enroll_device(uuid, uuid, bytea)",
        (
            "FUNCTION:initial_right_api:lookup_existing_start_attempt(uuid, uuid,"
            " uuid, uuid, bytea)"
        ),
        "COLUMN-ACL:public:trusted_devices:revoked_at:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:lineup_memories:retired_at:pitchlog_initial_actor",
        "COLUMN-ACL:public:players:team_record_id:pitchlog_initial_fn_owner",
        (
            "COLUMN-ACL:public:game_start_requests:request_digest:pitchlog_initia"
            "l_fn_owner"
        ),
        "COLUMN-ACL:public:recording_right_deliveries:nonce:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:games:started_at:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:team_records:kind:pitchlog_initial_actor",
        "COLUMN-ACL:public:lineup_memories:tenant_id:pitchlog_initial_actor",
        (
            "COLUMN-ACL:public:recording_right_deliveries:generation:pitchlog_ini"
            "tial_fn_owner"
        ),
        (
            "COLUMN-ACL:public:recording_right_deliveries:revoked_at:pitchlog_ini"
            "tial_fn_owner"
        ),
        (
            "FUNCTION:initial_right_api:begin_start_attempt(uuid, uuid, uuid, uui"
            "d, bytea, uuid)"
        ),
        "COLUMN-ACL:public:games:away_team_record_id:pitchlog_initial_fn_owner",
        (
            "COLUMN-ACL:public:lineup_memories:migration_preserved_only:pitchlog_"
            "initial_actor"
        ),
        "COLUMN-ACL:public:team_records:kind:pitchlog_initial_fn_owner",
        "FUNCTION:initial_right_api:read_start_game(uuid, uuid)",
        (
            "COLUMN-ACL:public:recording_right_deliveries:device_id:pitchlog_init"
            "ial_fn_owner"
        ),
        "COLUMN-ACL:public:team_records:tenant_id:pitchlog_initial_fn_owner",
        "COLUMN-ACL:public:players:team_record_id:pitchlog_initial_actor",
    }
)


def test_pre_rule_preserves_old16_and_defers_exact_epoch_acl() -> None:
    """旧resolver16/epochと初期権・開始の有限保留集合を照合する。"""
    generated = product_provisioning.generate_authz_ddl(
        product_provisioning._REPOSITORY_ROOT, PRODUCT_SPEC
    )
    _, statements = product_provisioning._build_operation_statements(
        ProductOperation.APPLY_PRE_RULE
    )
    sql_text = "\n".join(row.sql for row in statements)
    withheld = tuple(
        row
        for row in generated
        if row.element_type in {"function", "column_acl_expectation"}
        and row.sql not in sql_text
    )
    old = tuple(
        row
        for row in withheld
        if row.element_id == product_provisioning.RULE_RESOLUTION_FUNCTION_ID
        or row.element_id.endswith(
            f":{product_provisioning.RULE_RESOLUTION_OWNER_ROLE_ID}"
        )
    )
    assert len(old) == 16
    # 旧保留列はそのまま、採用済み成績5関数・70列だけを真正Gitの前後差で追加する。
    import subprocess

    asset_path = "contracts/authz/product/ddl-elements.json"
    pins = read_ci_followup_inputs()
    parent = json.loads(
        subprocess.check_output(
            ["git", "show", pins["catalog_before_revision"] + ":" + asset_path],
            cwd=_REPOSITORY_ROOT,
        )
    )
    stats_bytes = subprocess.check_output(
        ["git", "show", pins["catalog_after_revision"] + ":" + asset_path],
        cwd=_REPOSITORY_ROOT,
    )
    assert stats_bytes == (_REPOSITORY_ROOT / asset_path).read_bytes()
    stats = json.loads(stats_bytes)
    old_functions = {row["function_id"]: row for row in parent["functions"]}
    old_columns = {
        row["expectation_id"]: row for row in parent["column_acl_expectations"]
    }
    assert all(stats_row in stats["functions"] for stats_row in old_functions.values())
    assert all(
        stats_row in stats["column_acl_expectations"]
        for stats_row in old_columns.values()
    )
    stats_function_ids = {
        row["function_id"]
        for row in stats["functions"]
        if row["function_id"] not in old_functions
    }
    stats_column_ids = {
        row["expectation_id"]
        for row in stats["column_acl_expectations"]
        if row["expectation_id"] not in old_columns
    }
    assert len(stats_function_ids) == 5 and all(
        value.startswith("FUNCTION:stats_api:") for value in stats_function_ids
    )
    assert len(stats_column_ids) == 70 and all(
        value.endswith(":pitchlog_sync_right_fn_owner") for value in stats_column_ids
    )
    expected_extra = (
        {
            (
                "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:pitchlog_rg1_"
                "control_owner"
            ),
        }
        | _EXPECTED_DEFERRED_INITIAL_IDS
        | _EXPECTED_DEFERRED_FIRST_BALL_IDS
        | _EXPECTED_DEFERRED_ORDINARY_IDS
        | _TERMINAL_FUNCTION_IDS
        | _TERMINAL_COLUMN_ACL_IDS
        | _LINEUP_FUNCTION_IDS
        | _LINEUP_COLUMN_ACL_IDS
        | _BATTED_FUNCTION_IDS
        | _BATTED_COLUMN_ACL_IDS
        | stats_function_ids
        | stats_column_ids
    )
    assert {row.element_id for row in withheld} - {
        row.element_id for row in old
    } == expected_extra
    assert "CREATE OR REPLACE FUNCTION rg1_control.bind_initial_fresh_epoch" in sql_text


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong-kind"])
def test_pre_rule_rejects_nonexact_epoch_dependency(
    mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """新保留依存の欠落・重複・型変更を拒否する。"""
    from dataclasses import replace

    generated = product_provisioning.generate_authz_ddl(
        product_provisioning._REPOSITORY_ROOT, PRODUCT_SPEC
    )
    identifier = (
        "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:"
        "pitchlog_rg1_control_owner"
    )
    selected = next(row for row in generated if row.element_id == identifier)
    changed = tuple(row for row in generated if row.element_id != identifier)
    if mutation == "duplicate":
        changed += (selected, selected)
    elif mutation == "wrong-kind":
        changed += (replace(selected, element_type="acl_expectation"),)
    monkeypatch.setattr(product_provisioning, "generate_authz_ddl", lambda *_: changed)
    with pytest.raises(ProductProvisioningError, match="初回epoch列ACL"):
        product_provisioning._build_operation_statements(
            ProductOperation.APPLY_PRE_RULE
        )


@pytest.mark.parametrize(
    "revision", ["0034_stage_a_rule_defaults", "0035_rg1_initial_fresh_epoch"]
)
def test_startup_resume_epoch_order_without_db(
    revision: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """34だけepoch移行し、35はepoch再適用せず0036を検査して認可へ進む。"""
    from pitchlog.db import stage_a_startup as startup

    events: list[str] = []

    class Owner:
        def __enter__(self) -> Owner:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def cursor(self) -> Owner:
            return self

        def execute(self, _: str) -> None:
            pass

        def fetchone(self) -> tuple[str, str]:
            return ("pitchlog_owner", "pitchlog_owner")

    monkeypatch.setattr(startup.psycopg, "connect", lambda *_: Owner())
    monkeypatch.setattr(startup, "_require_same_database", lambda *_: None)
    monkeypatch.setattr(startup, "_require_placed_state", lambda *_: revision)
    monkeypatch.setattr(startup, "_apply_epoch", lambda *_: events.append("epoch"))
    monkeypatch.setattr(
        startup, "_require_epoch_state", lambda *_: events.append("verify")
    )
    monkeypatch.setattr(
        startup, "_apply_initial_storage", lambda *_: events.append("initial")
    )
    monkeypatch.setattr(
        startup, "_require_initial_state", lambda *_: events.append("verify-initial")
    )
    monkeypatch.setattr(
        startup, "_apply_writer_storage", lambda *_: events.append("writer")
    )
    monkeypatch.setattr(
        startup, "_require_writer_state", lambda *_: events.append("verify-writer")
    )
    monkeypatch.setattr(
        startup, "apply_product_authz_ddl", lambda *_: events.append("authz")
    )
    monkeypatch.setattr(startup, "_require_s3", lambda *_: events.append("s3"))
    result = startup.resume_stage_a_after_placement(
        owner_dsn="owner", applicator_dsn="admin"
    )
    assert events == (["epoch"] if revision.startswith("0034") else []) + [
        "verify",
        "initial",
        "verify-initial",
        "writer",
        "verify-writer",
        "authz",
        "verify-writer",
        "s3",
    ]
    assert result.publishable is False


@pytest.mark.parametrize(
    "mutation",
    [
        "valid",
        "marker",
        "missing-column",
        "wrong-type",
        "not-null",
        "default",
        "missing-check",
        "unvalidated",
    ],
)
def test_startup_checks_real_epoch_metadata(
    mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """35 markerのみ・列型/NULL/default/制約の偽装を全認可前に拒否する。"""
    from pitchlog.db import stage_a_startup as startup

    rows: list[list[tuple[object, ...]]] = [
        [("0035_rg1_initial_fresh_epoch",)],
        [("bigint", False, "", "", None)],
        [
            (
                "CHECK (((recovery_generation IS NULL) OR (recovery_generation > 0)))",
                True,
                False,
            )
        ],
    ]
    if mutation == "marker":
        rows[0] = [("0036_unknown",)]
    elif mutation == "missing-column":
        rows[1] = []
    elif mutation == "wrong-type":
        rows[1] = [("integer", False, "", "", None)]
    elif mutation == "not-null":
        rows[1] = [("bigint", True, "", "", None)]
    elif mutation == "default":
        rows[1] = [("bigint", False, "", "", "1")]
    elif mutation == "missing-check":
        rows[2] = []
    elif mutation == "unvalidated":
        rows[2] = [(rows[2][0][0], False, False)]

    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def cursor(self) -> Cursor:
            return self

        def execute(self, _: str) -> None:
            pass

        def fetchall(self) -> list[tuple[object, ...]]:
            return rows.pop(0)

    monkeypatch.setattr(startup.psycopg, "connect", lambda *_: Cursor())
    if mutation == "valid":
        startup._require_epoch_state("admin")
    else:
        with pytest.raises(startup.StageAStartupError):
            startup._require_epoch_state("admin")


def test_startup_unknown_placed_revision_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既知34/35以外は配置確認や認可へ進まない。"""
    from pitchlog.db import stage_a_startup as startup

    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def cursor(self) -> Cursor:
            return self

        def execute(self, _: str) -> None:
            pass

        def fetchall(self) -> list[tuple[str]]:
            return [("0036_unknown",)]

    monkeypatch.setattr(startup.psycopg, "connect", lambda *_: Cursor())
    with pytest.raises(startup.StageAStartupError, match="revision"):
        startup._require_placed_state("admin")


def test_new_schema_guards_preserve_other_five_and_exact_owner() -> None:
    """旧schemaのSQLを保持し、statsを含む新schemaのownerを保護する。"""
    generated = product_provisioning.generate_authz_ddl(
        product_provisioning._REPOSITORY_ROOT, PRODUCT_SPEC
    )
    _, applied = product_provisioning._build_operation_statements(
        ProductOperation.APPLY
    )
    sql_texts = {row.sql for row in applied}
    elements = product_provisioning._load_product_elements()
    schemas = [row for row in generated if row.element_type == "schema"]
    assert {r.element_id for r in schemas} == {
        "public",
        "authz_private",
        "rg1_api",
        "rg1_control",
        "pitchlog_ledger_observer",
        "initial_right_api",
        "authn",
        "authn_crypto",
        "sync_fence",
        "sync_fence_api",
        "sync_right_api",
        "recording_vocab_api",
        "stats_api",
    }
    assert len(schemas) == 8 + 3 + 1 + 1
    for row in schemas:
        if row.element_id == "stats_api":
            assert row.sql in sql_texts
            assert "n.nspname='stats_api' AND r.rolname='pitchlog_owner'" in row.sql
            assert "RAISE EXCEPTION 'stats schema owner collision'" in row.sql
            assert "ALTER SCHEMA" not in row.sql
            continue
        if row.element_id == "recording_vocab_api":
            assert row.sql in sql_texts
            assert (
                "n.nspname='recording_vocab_api' AND "
                "r.rolname='pitchlog_recording_vocab_fn_owner'"
            ) in row.sql
            assert "RAISE EXCEPTION 'recording vocabulary schema collision'" in row.sql
            assert "ALTER SCHEMA" not in row.sql
            continue
        if row.element_id not in {
            "rg1_control",
            "pitchlog_ledger_observer",
            "initial_right_api",
        }:
            assert row.sql in sql_texts
            continue
        element = product_provisioning._element_for_statement(row, elements)
        guarded = product_provisioning._strict_lifecycle_schema_sql(element, row.sql)
        assert guarded in sql_texts
        assert "r.rolname = '" + str(element.fields["owner"]) + "'" in guarded
        assert "RAISE EXCEPTION 'schema owner collision:" in guarded
        assert "ALTER SCHEMA" not in guarded
        original = (
            f"CREATE SCHEMA {row.element_id} AUTHORIZATION {element.fields['owner']};"
        )
        assert row.sql.replace(original, "") in guarded.replace(
            guarded[
                guarded.index("DO $schema_reapply$") : guarded.index(
                    "$schema_reapply$;"
                )
                + len("$schema_reapply$;")
            ],
            "",
        )


@pytest.mark.parametrize(
    "mutation", ["unknown", "wrong-name", "wrong-owner", "duplicate-create"]
)
def test_new_schema_guard_rejects_noncanonical_inputs(mutation: str) -> None:
    """新閉集合の別schema化や正規CREATEの不一致を拒否する。"""
    from dataclasses import replace

    elements = product_provisioning._load_product_elements()
    element = next(
        row
        for row in elements
        if row.element_type == "schema" and row.element_id == "rg1_control"
    )
    source = "CREATE SCHEMA rg1_control AUTHORIZATION pitchlog_rg1_control_owner;"
    if mutation == "unknown":
        element = replace(
            element,
            element_id="unknown",
            fields={**element.fields, "schema_id": "unknown", "schema_name": "unknown"},
        )
    elif mutation == "wrong-name":
        element = replace(element, fields={**element.fields, "schema_name": "public"})
    elif mutation == "wrong-owner":
        element = replace(element, fields={**element.fields, "owner": "pitchlog_app"})
    else:
        source += source
    with pytest.raises(ProductProvisioningError):
        product_provisioning._strict_lifecycle_schema_sql(element, source)


@pytest.mark.parametrize(
    "function_id,source_path,delimiter",
    [
        (
            "FUNCTION:pitchlog_ledger_observer:identity()",
            "backend/src/pitchlog/durable_rights_ledger/business_identity.sql",
            "$$",
        ),
        (
            "FUNCTION:rg1_control:bind_initial_fresh_epoch(bigint)",
            "backend/src/pitchlog/recording_rights/rg1_lifecycle.sql",
            "$function$",
        ),
    ],
)
def test_lifecycle_function_header_only_is_normalized(
    function_id: str, source_path: str, delimiter: str
) -> None:
    """二つの固定元SQLの引数・戻り値・AS本文は全byte保持して再適用する。"""
    from pitchlog.authz.product_function_acl import generate_lifecycle_function_sql

    root = product_provisioning._REPOSITORY_ROOT
    source = (root / source_path).read_text()
    physical_name = (
        function_id.removeprefix("FUNCTION:").split("(")[0].replace(":", ".")
    )
    start = source.index("CREATE FUNCTION " + physical_name + "(")
    body_start = source.index(delimiter, start)
    end = (
        source.index(delimiter + ";", body_start + len(delimiter)) + len(delimiter) + 1
    )
    original = source[start:end]
    rendered = generate_lifecycle_function_sql(function_id, root)
    normalized = original.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1)
    assert normalized in rendered
    assert (
        original[original.index(delimiter) :].encode()
        == normalized[normalized.index(delimiter) :].encode()
    )


@pytest.mark.parametrize(
    "target",
    [
        "FUNCTION:initial_right_api:enroll_device(uuid, uuid, bytea)",
        "POLICY:trusted_devices:initial_right_trusted_devices_insert",
    ],
)
@pytest.mark.parametrize("mutation", ["valid", "missing", "duplicate", "wrong-kind"])
def test_b2_pre_rule_defers_exact_enrollment_pair(
    target: str,
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0036依存の関数/policyを前段で保留し、片側や型不一致を拒否する。"""
    from dataclasses import replace

    generated = product_provisioning.generate_authz_ddl(
        product_provisioning._REPOSITORY_ROOT, PRODUCT_SPEC
    )
    selected = next(row for row in generated if row.element_id == target)
    changed = tuple(row for row in generated if row.element_id != target)
    if mutation == "valid":
        changed += (selected,)
    elif mutation == "duplicate":
        changed += (selected, selected)
    elif mutation == "wrong-kind":
        changed += (replace(selected, element_type="unknown"),)
    monkeypatch.setattr(product_provisioning, "generate_authz_ddl", lambda *_: changed)
    if mutation == "valid":
        _, statements = product_provisioning._build_operation_statements(
            ProductOperation.APPLY_PRE_RULE
        )
        text = "\n".join(row.sql for row in statements)
        assert selected.sql not in text
        assert "CREATE POLICY initial_right_trusted_devices_insert" not in text
        assert "CREATE OR REPLACE FUNCTION initial_right_api.enroll_device" not in text
        _, applied = product_provisioning._build_operation_statements(
            ProductOperation.APPLY
        )
        assert any(selected.sql in row.sql for row in applied)
    else:
        with pytest.raises(ProductProvisioningError):
            product_provisioning._build_operation_statements(
                ProductOperation.APPLY_PRE_RULE
            )


@pytest.mark.parametrize("mutation", ["valid", "duplicate", "wrong-kind"])
def test_worker_lookup_deferred_until_initial_storage(mutation, monkeypatch):
    """lookupは0036以前に実行せず、型と一意性を維持する。"""
    from dataclasses import replace

    from pitchlog.authz.product_function_acl import LOOKUP_FUNCTION_ID

    generated = product_provisioning.generate_authz_ddl(
        product_provisioning._REPOSITORY_ROOT, PRODUCT_SPEC
    )
    selected = next(row for row in generated if row.element_id == LOOKUP_FUNCTION_ID)
    changed = tuple(r for r in generated if r.element_id != LOOKUP_FUNCTION_ID)
    if mutation == "valid":
        changed += (selected,)
    elif mutation == "duplicate":
        changed += (selected, selected)
    else:
        changed += (replace(selected, element_type="policy"),)
    monkeypatch.setattr(product_provisioning, "generate_authz_ddl", lambda *_: changed)
    if mutation == "valid":
        _, statements = product_provisioning._build_operation_statements(
            ProductOperation.APPLY_PRE_RULE
        )
        assert selected.sql not in "\n".join(r.sql for r in statements)
        _, statements = product_provisioning._build_operation_statements(
            ProductOperation.APPLY
        )
        assert any(selected.sql in r.sql for r in statements)
    else:
        with pytest.raises(ProductProvisioningError):
            product_provisioning._build_operation_statements(
                ProductOperation.APPLY_PRE_RULE
            )


def test_current_profile_unapply_rejects_before_sql_generation_and_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """現profileの未提供unapplyはSQL生成/実行前に拒否する。"""

    def forbidden(*_: object) -> None:
        pytest.fail("未提供unapplyがSQL生成へ到達")

    monkeypatch.setattr(product_provisioning, "generate_authz_ddl", forbidden)
    with pytest.raises(ProductProvisioningError, match="退役は未提供"):
        product_provisioning._build_operation_statements(ProductOperation.UNAPPLY)
    connection = _FakeConnection()
    with pytest.raises(ProductProvisioningError, match="退役は未提供"):
        product_provisioning.unapply_product_authz_ddl(
            _as_psycopg_connection(connection)
        )
    assert connection.executed_statements == []
    assert connection.identity_query_count == 0
    assert connection.commit_count == connection.rollback_count == 0


def test_common_legacy_materializer_preserves_fixed_all_sections_and_sql(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """全JSON/380SQL/stepsを固定Gitへ照合し、現公開readerへ渡す。"""
    import hashlib
    import subprocess

    from product_authz_legacy_profile import (
        legacy_profile_context,
        legacy_profile_metadata,
        verify_legacy_migration_sources,
    )

    from pitchlog.authz import product_catalog

    metadata = legacy_profile_metadata()
    assert (
        metadata["revision"]
        == subprocess.check_output(
            ["git", "rev-parse", "c2e5e4dd"], cwd=_REPOSITORY_ROOT, text=True
        ).strip()
    )
    verify_legacy_migration_sources()
    original_root = product_provisioning._REPOSITORY_ROOT
    with legacy_profile_context(monkeypatch, tmp_path / "fixed-profile") as root:
        for row in metadata["files"]:
            data = (root / row["path"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == row["sha256"]
            assert data == subprocess.check_output(
                ["git", "show", f"{metadata['revision']}:{row['path']}"],
                cwd=_REPOSITORY_ROOT,
            )
        generated = product_provisioning.generate_authz_ddl(root, PRODUCT_SPEC)
        assert len(generated) == 380
        expected = product_catalog._load_product_expectations()
        assert len(expected.table_names) == 50
        assert len(expected.role_ids) == 14
        assert len(expected.schema_names) == 8
        assert len(expected.functions) == 79
        # 固定成功へ置換せず、公開適用器の実SQL構築で旧両操作を検証する。
        for operation in ProductOperation:
            steps, statements = product_provisioning._build_operation_statements(
                operation
            )
            assert steps.transaction == "single"
            assert statements
    assert product_provisioning._REPOSITORY_ROOT == original_root


@pytest.mark.parametrize(
    "mutation", ("unknown", "duplicate", "bool-version", "traversal", "digest")
)
def test_legacy_metadata_is_closed_and_has_no_current_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    """固定metadataの未知field・重複・型・path・hashを閉拒否する。"""
    import product_authz_legacy_profile as legacy

    metadata = legacy.legacy_profile_metadata()
    if mutation == "unknown":
        metadata["unexpected"] = True
    elif mutation == "duplicate":
        metadata["files"].append(dict(metadata["files"][0]))
    elif mutation == "bool-version":
        metadata["schema_version"] = True
    elif mutation == "traversal":
        metadata["files"][0]["path"] = "../forbidden"
    else:
        metadata["files"][0]["sha256"] = "invalid"
    fixture = tmp_path / "metadata.json"
    fixture.write_text(json.dumps(metadata))
    monkeypatch.setattr(legacy, "_FIXTURE", fixture)
    with pytest.raises(ValueError):
        legacy.legacy_profile_metadata()


def test_legacy_reader_rejects_unknown_path_and_wrong_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未知pathと不一致blobを現sourceへfallbackせず拒否する。"""
    import product_authz_legacy_profile as legacy

    with pytest.raises(ValueError, match="未登録"):
        legacy.legacy_file("unknown")
    monkeypatch.setattr(
        legacy.subprocess, "check_output", lambda *args, **kwargs: b"wrong"
    )
    with pytest.raises(ValueError, match="hash"):
        legacy.legacy_file("contracts/authz/product/ddl-elements.json")


def test_current_and_legacy_owned_baselines_do_not_forge_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """current実stage入口と旧0036の独立した段階順を保持する。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    import db_fixtures

    trace = []
    revision = "0041_stats_fact_versions"

    @contextmanager
    def cursor():
        yield SimpleNamespace(
            execute=lambda query: trace.append("marker"), fetchall=lambda: [(revision,)]
        )

    connection = cast(
        psycopg.Connection[Any],
        SimpleNamespace(cursor=cursor, rollback=lambda: trace.append("rollback")),
    )
    monkeypatch.setattr(
        db_fixtures,
        "_close_owned_seed_database_access",
        lambda cluster: trace.append("close"),
    )

    def advance(**kwargs):
        trace.append("real-stage-entry")
        assert kwargs == {
            "owner_dsn": "synthetic-owner",
            "applicator_dsn": "synthetic-applicator",
        }
        return SimpleNamespace(
            completed_revision="0041_stats_fact_versions", publishable=False
        )

    from pitchlog.db import current_product_startup

    monkeypatch.setattr(
        current_product_startup, "advance_current_product_from_s0", advance
    )
    monkeypatch.setattr(
        db_fixtures,
        "unapply_product_authz_ddl",
        lambda conn: pytest.fail("current unapply"),
    )
    cluster = db_fixtures.DisposablePostgres(
        "synthetic-cluster", "synthetic-admin", "synthetic-role"
    )
    db_fixtures._prepare_current_product_baseline(
        cluster=cluster,
        owner_dsn="synthetic-owner",
        applicator_dsn="synthetic-applicator",
        applicator=connection,
    )
    assert trace == ["close", "real-stage-entry", "marker", "rollback"]
    revision = "0039_ordinary_pitch_storage"
    with pytest.raises(AssertionError):
        db_fixtures._prepare_current_product_baseline(
            cluster=cluster,
            owner_dsn="synthetic-owner",
            applicator_dsn="synthetic-applicator",
            applicator=connection,
        )
    revision = "0036_initial_right_storage"
    with pytest.raises(AssertionError):
        db_fixtures._prepare_current_product_baseline(
            cluster=cluster,
            owner_dsn="synthetic-owner",
            applicator_dsn="synthetic-applicator",
            applicator=connection,
        )
    trace.clear()
    monkeypatch.setattr(
        db_fixtures, "verify_legacy_migration_sources", lambda: trace.append("source")
    )
    monkeypatch.setattr(
        db_fixtures,
        "apply_product_authz_before_rule_placement",
        lambda conn: trace.append("pre-rule"),
    )
    monkeypatch.setattr(
        db_fixtures.command, "upgrade", lambda config, target: trace.append(target)
    )
    monkeypatch.setattr(
        db_fixtures, "apply_product_authz_ddl", lambda conn: trace.append("apply")
    )
    monkeypatch.setattr(
        db_fixtures, "unapply_product_authz_ddl", lambda conn: trace.append("unapply")
    )
    db_fixtures._prepare_legacy_product_baseline(
        cluster=cluster,
        owner_dsn="synthetic-owner",
        applicator_dsn="synthetic-applicator",
        applicator=connection,
    )
    assert trace == [
        "source",
        "close",
        "pre-rule",
        "0036_initial_right_storage",
        "marker",
        "rollback",
        "apply",
        "unapply",
    ]


def test_product_snapshot_uses_closed_current_schema_and_private_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公開全行を保つsnapshotのschema/私有6表だけを有限追加する。"""
    import copy
    from contextlib import contextmanager
    from types import SimpleNamespace

    import db_fixtures

    captured = []

    @contextmanager
    def cursor():
        yield SimpleNamespace()

    connection = cast(Any, SimpleNamespace(cursor=cursor))
    monkeypatch.setattr(
        db_fixtures,
        "_fetch_snapshot_rows",
        lambda cursor, query, params=(): captured.append((query, params)) or (),
    )
    asset = json.loads((_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path).read_text())
    db_fixtures._snapshot_product_catalog(connection, (), asset=asset)
    schema_queries = [(q, p) for q, p in captured if "namespace.nspname = ANY(%s)" in q]
    private_queries = [(q, p) for q, p in captured if "relation.relname = ANY(%s)" in q]
    assert len(schema_queries) == 5
    assert len(private_queries) == 4
    assert all(
        set(p[0]) == {r["schema_name"] for r in asset["schemas"]}
        for _, p in schema_queries
    )
    assert all(
        set(p[0])
        == {
            "writer_bindings",
            "writer_admissions",
            "first_ball_write_admissions",
            "ordinary_pitch_checkpoints",
            "ordinary_pitch_write_admissions",
            "ordinary_pitch_history",
            "stats_fact_versions",
            "stats_primitive_sources",
            "stats_primitive_facts",
        }
        for _, p in private_queries
    )
    assert all("namespace.nspname = 'public'" in q for q, _ in private_queries)
    builtin_queries = [
        (q, params) for q, params in captured if "procedure.pronargs = 0" in q
    ]
    assert len(builtin_queries) == 1
    query, params = builtin_queries[0]
    assert "namespace.nspname = 'pg_catalog'" in query
    assert params[1] == ["pg_control_system"]
    assert "privilege.privilege_type, privilege.is_grantable" in query
    for mutate in (
        "schema",
        "table",
        "duplicate",
        "builtin",
        "builtin-signature",
        "builtin-missing",
    ):
        bad = copy.deepcopy(asset)
        if mutate == "schema":
            bad["schemas"][0]["schema_name"] = "unknown"
        elif mutate == "table":
            next(row for row in bad["tables"] if row["table_id"] == "writer_bindings")[
                "schema_name"
            ] = "unknown"
        elif mutate.startswith("builtin"):
            row = next(
                r
                for r in bad["acl_expectations"]
                if r["object_kind"] == "builtin_function"
            )
            if mutate == "builtin":
                row["object_id"] = "unknown"
            elif mutate == "builtin-signature":
                row["acl_id"] = row["acl_id"].replace("()", "(uuid)")
            else:
                bad["acl_expectations"].remove(row)
        else:
            bad["schemas"].append(copy.deepcopy(bad["schemas"][0]))
        before = len(captured)
        with pytest.raises(AssertionError, match="閉集合|builtin exact"):
            db_fixtures._snapshot_product_catalog(connection, (), asset=bad)
        assert len(captured) == before


def test_legacy_materializer_rejects_live_or_stale_destination(tmp_path: Path) -> None:
    """実repository上書きと既存dataによる不足補完を拒否する。"""
    from product_authz_legacy_profile import materialize_legacy_profile

    with pytest.raises(ValueError, match="repository外"):
        materialize_legacy_profile(_REPOSITORY_ROOT)
    (tmp_path / "stale").write_text("not a source")
    with pytest.raises(ValueError, match="fallback"):
        materialize_legacy_profile(tmp_path)


@pytest.mark.parametrize("selection", ("unknown", "mixed-root", "legacy-with-current"))
def test_owned_profile_selection_rejects_unknown_or_mixed_context(
    selection: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """未知profileや新旧root混在をowned cluster生成前に拒否する。"""
    import db_fixtures

    legacy = (
        cast(Any, "unknown")
        if selection == "unknown"
        else selection == "legacy-with-current"
    )
    root = tmp_path if selection == "mixed-root" else _REPOSITORY_ROOT

    def factory():
        pytest.fail("不正選択がcluster生成へ到達")

    with pytest.raises(ValueError):
        with db_fixtures._owned_product_catalog(
            factory, monkeypatch, legacy=legacy, profile_root=root
        ):
            pytest.fail("不正profileを供給")


def test_current_sync_roles_have_strict_all_attribute_collision_sql() -> None:
    """旧3主体と新owner1の全属性衝突拒否の正式SQLを照合する。"""
    from db.test_product_authz_provisioning import (
        _ROLE_ATTRIBUTES,
        _SYNC_COLLISION_ROLES,
    )

    original = {
        "pitchlog_sync_binding_fn_owner",
        "pitchlog_sync_binding_actor",
        "pitchlog_sync_right_fn_owner",
    }
    added = {"pitchlog_recording_vocab_fn_owner"}
    assert set(_SYNC_COLLISION_ROLES) == original | added
    assert len(_SYNC_COLLISION_ROLES) == len(original) + len(added)
    assert len(_ROLE_ATTRIBUTES) == 7
    statements = product_provisioning.generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    roles = {
        row["role_id"]: row
        for row in json.loads(
            (_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path).read_text()
        )["roles"]
    }
    for role_id in _SYNC_COLLISION_ROLES:
        sql = next(
            row.sql
            for row in statements
            if row.element_type == "role" and row.element_id == role_id
        )
        assert f"sync role collision: {role_id}" in sql
        assert "ALTER ROLE" not in sql
        for attribute, column in _ROLE_ATTRIBUTES:
            guard = (
                f"r.{column} IS {'TRUE' if roles[role_id][attribute] else 'FALSE'}"
                if attribute == "login"
                else f"NOT r.{column}"
            )
            assert guard in sql


def test_legacy_snapshot_keeps_old_builtin_targets_and_excludes_private_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧profileのbuiltin2宣言も観測し、current私有表を混ぜない。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    import db_fixtures
    from product_authz_legacy_profile import legacy_file

    captured = []

    @contextmanager
    def cursor():
        yield SimpleNamespace()

    monkeypatch.setattr(
        db_fixtures,
        "_fetch_snapshot_rows",
        lambda cursor, query, params=(): captured.append((query, params)) or (),
    )
    asset = json.loads(legacy_file("contracts/authz/product/ddl-elements.json"))
    db_fixtures._snapshot_product_catalog(
        cast(Any, SimpleNamespace(cursor=cursor)),
        (),
        asset=asset,
    )
    builtins = [
        (query, params)
        for query, params in captured
        if "procedure.pronargs = 0" in query
    ]
    assert len(builtins) == 1 and builtins[0][1][1] == ["pg_control_system"]
    private = [
        params for query, params in captured if "relation.relname = ANY(%s)" in query
    ]
    assert len(private) == 4 and all(params == ([],) for params in private)


def _registered_seed_test_cluster(monkeypatch: pytest.MonkeyPatch):
    """純unitだけの所有registry個体と合成接続座標を作る。"""
    import db_fixtures

    token = "0123456789abcdef"
    dsn = (
        "host=127.0.0.1 port=54321 dbname=pitchlog_disposable "
        f"user=pitchlog_disposable_{token}"
    )
    cluster = db_fixtures.DisposablePostgres(f"pitchlog-authz-{token}", dsn, dsn)
    monkeypatch.setitem(db_fixtures._DISPOSABLE_CLUSTER_OWNERS, id(cluster), cluster)
    return cluster


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "external",
        "foreign",
        "repeat",
        "host",
        "database",
        "owner",
        "session",
        "superuser",
        "bool",
        "revision",
        "guard",
        "real_error",
        "seed_error",
    ],
)
def test_owned_seed_runs_only_after_real_initial_storage(
    monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    """0036実呼出→検査→seed→commitを保ち、外部/座標/主体/guard異常を拒否する。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    import db_fixtures
    from psycopg.conninfo import make_conninfo

    cluster = _registered_seed_test_cluster(monkeypatch)
    completed: list[bool] = [True] if fault == "repeat" else []
    trace: list[str] = []
    identity: list[object] = ["pitchlog_disposable_0123456789abcdef"] * 2 + [
        "pitchlog_product",
        "pitchlog_owner",
        True,
    ]
    if fault == "session":
        identity[1] = "other"
    if fault == "superuser":
        identity[4] = False
    if fault == "bool":
        identity[4] = 1
    if fault == "foreign":
        monkeypatch.delitem(db_fixtures._DISPOSABLE_CLUSTER_OWNERS, id(cluster))
    monkeypatch.setattr(
        db_fixtures,
        "_external_product_catalog",
        object() if fault == "external" else None,
    )

    def real_initial(dsn):
        trace.append("real36")
        if fault == "real_error":
            raise RuntimeError("real migration failure")

    def seed(connection):
        if fault == "seed_error":
            raise RuntimeError("seed failure")
        trace.append("seed")

    monkeypatch.setattr(
        db_fixtures.stage_a_startup, "_apply_initial_storage", real_initial
    )
    responses = iter([tuple(identity), (1,) if fault == "guard" else (0,)])

    @contextmanager
    def cursor():
        yield SimpleNamespace(
            execute=lambda query: trace.append("inspect"),
            fetchone=lambda: next(responses),
            fetchall=lambda: [
                (
                    "0039_ordinary_pitch_storage"
                    if fault == "revision"
                    else "0036_initial_right_storage",
                )
            ],
        )

    @contextmanager
    def connect(dsn):
        trace.append("connect")
        yield SimpleNamespace(cursor=cursor, commit=lambda: trace.append("commit"))

    monkeypatch.setattr(db_fixtures.psycopg, "connect", connect)
    dsn = make_conninfo(
        cluster.admin_dsn, dbname="pitchlog_product", user="pitchlog_owner"
    )
    if fault in {"host", "database", "owner"}:
        key, value = {
            "host": ("host", "192.0.2.1"),
            "database": ("dbname", "other"),
            "owner": ("user", "other"),
        }[fault]
        dsn = make_conninfo(dsn, **{key: value})

    def invoke():
        with db_fixtures._seed_after_real_initial_storage(
            cluster, monkeypatch, seed, completed
        ):
            db_fixtures.stage_a_startup._apply_initial_storage(dsn)
            if fault is None:
                with pytest.raises(AssertionError, match="再実行"):
                    db_fixtures.stage_a_startup._apply_initial_storage(dsn)

    if fault is None:
        invoke()
        assert trace == [
            "real36",
            "connect",
            "inspect",
            "inspect",
            "inspect",
            "seed",
            "commit",
        ]
        assert completed == [True]
    else:
        with pytest.raises(
            RuntimeError if fault in {"real_error", "seed_error"} else AssertionError
        ):
            invoke()
        assert "seed" not in trace and "commit" not in trace
        assert completed == ([True] if fault == "repeat" else [])
        if fault in {"external", "foreign", "repeat", "host", "database", "owner"}:
            assert "real36" not in trace


def test_other_profiles_keeps_all_seed_rows_and_reads_them_after_writer() -> None:
    """全132tupleの順序/値/SQL供給を維持し、配置後は全行の実在だけを読む。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from db.test_product_authz_other_profiles import (
        _seed_other_profiles,
        _seed_rows_before_writer,
    )
    from product_authz_other_profiles_cases import other_profile_seed_rows
    from product_authz_tenant_owned_cases import insert_statement

    rows = other_profile_seed_rows()
    from psycopg.types.json import Jsonb

    def normalized(params):
        return tuple(
            value.obj if isinstance(value, Jsonb) else value for value in params
        )

    expected = [insert_statement(row) for row in rows]
    assert len(rows) == 132
    calls = []
    rollbacks = []

    @contextmanager
    def cursor():
        yield SimpleNamespace(
            execute=lambda statement, params: calls.append((statement, params)),
            fetchone=lambda: (1,),
        )

    connection = SimpleNamespace(cursor=cursor, rollback=lambda: rollbacks.append(True))
    _seed_rows_before_writer(cast(Any, connection))
    assert [
        (statement.as_string(), normalized(params)) for statement, params in calls
    ] == [(statement.as_string(), normalized(params)) for statement, params in expected]
    calls.clear()
    _seed_other_profiles(cast(Any, SimpleNamespace(applicator=connection)))
    assert len(calls) == len(rows)
    assert [normalized(params) for _, params in calls] == [
        normalized(params) for _, params in expected
    ]
    assert all(
        statement.as_string().startswith("SELECT count(*) FROM ")
        for statement, _ in calls
    )
    assert rollbacks == [True]


@pytest.mark.parametrize(
    "fault",
    [None, "owner", "session", "superuser", "bool", "duplicate", "foreign", "port"],
)
def test_builtin_bootstrap_mapping_requires_owned_actual_superuser(
    monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    """builtin実owner/主体/所有座標を証明し、不一致や多義を拒否する。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from db.test_product_authz_round_trip import _verified_builtin_bootstrap

    cluster = _registered_seed_test_cluster(monkeypatch)
    name = "pitchlog_disposable_0123456789abcdef"
    row = [name, True, name, name, True, "OUT system_identifier bigint"]
    if fault == "owner":
        row[0] = "other"
    if fault == "session":
        row[3] = "other"
    if fault == "superuser":
        row[1] = False
    if fault == "bool":
        row[4] = 1
    rows = [tuple(row)] * (2 if fault == "duplicate" else 1)
    rollbacks = []

    @contextmanager
    def cursor():
        yield SimpleNamespace(execute=lambda query: None, fetchall=lambda: rows)

    if fault == "foreign":
        import db_fixtures

        monkeypatch.delitem(db_fixtures._DISPOSABLE_CLUSTER_OWNERS, id(cluster))
    connection = SimpleNamespace(
        cursor=cursor,
        rollback=lambda: rollbacks.append(True),
        info=SimpleNamespace(
            host="127.0.0.1",
            port=54322 if fault == "port" else 54321,
            dbname="pitchlog_product",
        ),
    )
    if fault is None:
        proof = _verified_builtin_bootstrap(cluster, cast(Any, connection))
        assert (proof.name, proof.identity_arguments) == (name, row[5])
        assert rollbacks == [True]
    else:
        with pytest.raises(AssertionError):
            _verified_builtin_bootstrap(cluster, cast(Any, connection))


@pytest.mark.parametrize(
    "fault", [None, "missing", "duplicate", "signature", "other_target"]
)
def test_cross_cluster_builtin_mapping_keeps_every_other_acl_field_and_row(
    fault: str | None,
) -> None:
    """証明した一granteeのみ対応付け、余剰ACLや重複を削除しない。"""
    from dataclasses import replace

    from db.test_product_authz_round_trip import (
        _map_owned_builtin_bootstrap,
        _VerifiedBuiltinBootstrap,
    )
    from db_fixtures import ProductCatalogSnapshot

    signature = "OUT system_identifier bigint"
    source = _VerifiedBuiltinBootstrap("owned_source", signature)
    target = _VerifiedBuiltinBootstrap(
        "owned_target", "other" if fault == "signature" else signature
    )
    owner = ("pg_catalog", "pg_control_system", signature, source.name, "EXECUTE", True)
    other = (
        "pg_catalog",
        "pg_control_system",
        signature,
        "unknown_grantee",
        "EXECUTE",
        False,
    )
    rows = (owner, other, other, ("public", "unknown", "", "PUBLIC", "EXECUTE", False))
    if fault == "missing":
        rows = rows[1:]
    if fault == "duplicate":
        rows = (owner, *rows)
    if fault == "other_target":
        rows = (
            owner,
            ("public", "unknown", "", source.name, "EXECUTE", False),
            *rows[1:],
        )
    snapshot = ProductCatalogSnapshot(
        (), (), (), (), (), (), (), (), (), rows, (), (), ()
    )
    if fault is None:
        result = _map_owned_builtin_bootstrap(snapshot, source, target)
        assert result.function_acl == ((*owner[:3], target.name, *owner[4:]), *rows[1:])
        assert replace(result, function_acl=snapshot.function_acl) == snapshot
    else:
        with pytest.raises(AssertionError):
            _map_owned_builtin_bootstrap(snapshot, source, target)
