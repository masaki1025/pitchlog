"""通常投球profileの有限ACL候補。実DB適用の証拠とは別。"""

import re

import pytest

from pitchlog.authz.ordinary_pitch_product import (
    candidate_declarations,
    candidate_profile,
)


def test_function_set_and_app_execute_are_closed():
    """consumeのapp直接呼出を開けず、限定六入口だけ公開する。"""
    declarations, bodies = candidate_declarations()
    names = {row["function_name"] for row in declarations["functions"]}
    assert names == {
        "read_ordinary_order_summary",
        "bind_ordinary_device",
        "check_ordinary_right",
        "prepare_ordinary_projection",
        "consume_ordinary_projection",
        "read_ordinary_checkpoint",
        "lock_ordinary_checkpoint",
        "read_ordinary_history_page",
    }
    for row in declarations["functions"]:
        assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["search_path"] == ["pg_catalog", "pg_temp"]
        sql = bodies["function|" + row["function_id"]]
        assert "FROM PUBLIC,pitchlog_app" in sql
        if row["function_name"] == "consume_ordinary_projection":
            assert row["acl_expectations"] == []
            assert "GRANT EXECUTE" not in sql
        else:
            assert row["acl_expectations"] == [
                {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
            ]
            assert "TO pitchlog_app;" in sql
        # descriptorの引数と実SQL引数は一致する（SQLは閉集合の実源から描画）。
        match = re.search(
            r"FUNCTION\s+sync_right_api\.\w+\((.*?)\)\s*RETURNS", sql, re.S
        )
        assert match
        actual = ", ".join(part.strip().split()[-1] for part in match[1].split(","))
        assert actual == row["identity_args"]


def test_private_table_default_deny_and_no_delete_grants():
    """owner固定/FORCE RLS、app直接DML禁止、更新は可変列だけ。"""
    profile = candidate_profile()
    declarations, bodies = candidate_declarations()
    assert len(profile["tables"]) == 3
    for table in profile["tables"]:
        assert table["owner"] == "pitchlog_owner"
        assert table["enable_row_level_security"] is True
        assert table["force_row_level_security"] is True
        sql = bodies["table|" + table["table_id"]]
        assert "REVOKE ALL" in sql
        assert "PUBLIC,pitchlog_app" in sql
    for row in declarations["column_acl_expectations"]:
        assert row["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
        assert set(row["privilege_ids"]) <= {"SELECT", "INSERT", "UPDATE"}
        if row["object_schema"] == "public":
            assert row["privilege_ids"] == ["SELECT"]
        if row["object_id"] == "ordinary_pitch_history":
            assert "UPDATE" not in row["privilege_ids"]
    assert len(declarations["acl_expectations"]) == 1
    assert (
        declarations["acl_expectations"][0]["object_id"]
        == "ordinary_pitch_write_admissions"
    )
    assert declarations["acl_expectations"][0]["privilege_ids"] == ["SELECT"]


@pytest.mark.parametrize("command", ["SELECT", "INSERT", "UPDATE"])
def test_private_policies_require_tenant_and_real_app_session(command):
    """自由GUCだけの権限ではなくdefiner role/app実sessionも限定する。"""
    declarations, _ = candidate_declarations()
    selected = [row for row in declarations["policies"] if row["command"] == command]
    assert selected
    for row in selected:
        assert row["role_ids"] == ["pitchlog_sync_right_fn_owner"]
        for expression in (row["using_expression"], row["with_check_expression"]):
            if expression is not None:
                assert "tenant_id = NULLIF" in expression
                assert "session_user = 'pitchlog_app'" in expression


def test_profile_returns_fresh_values():
    """呼出側の候補変更で次の正式候補を汚さない。"""
    first, _ = candidate_declarations()
    first["functions"][0]["acl_expectations"].clear()
    later, _ = candidate_declarations()
    assert later["functions"][0]["acl_expectations"]


def test_json_roundtrip_retains_exact_declaration_types():
    """quoted_nameを許すためexact検査を緩めず、生成時にplain str化する。"""
    import json

    from pitchlog.authz.first_ball_product import _exact

    declarations, _ = candidate_declarations()
    assert _exact(declarations, json.loads(json.dumps(declarations)))


def test_all_eight_bodies_use_existing_installer_parser():
    """文法を緩めず正式installerへ渡すCREATE FUNCTION形を成立させる。"""
    from pitchlog.authz.first_ball_product import application_function_sql, body

    declarations, _ = candidate_declarations()
    assert len(declarations["functions"]) == 8
    for row in declarations["functions"]:
        key = row["function_id"]
        sql = body("function", key)
        assert isinstance(sql, str)
        assert "CREATE OR REPLACE FUNCTION" not in sql
        assert application_function_sql(key, sql) is not None


def test_prefix_guard_receives_only_actual_watermark_read_columns():
    """実PGで不足した二水位だけSELECTし、app権限/DMLを広げない。"""
    declarations, _ = candidate_declarations()
    rows = [
        row
        for row in declarations["column_acl_expectations"]
        if row["object_id"] == "recording_generations"
    ]
    assert {row["column_id"] for row in rows} == {
        "confirmed_watermark",
        "applied_prefix",
    }
    for row in rows:
        assert row["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["privilege_ids"] == ["SELECT"]
