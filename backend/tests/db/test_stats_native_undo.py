"""root正式登録後の取消S helperの所有/権限/行型確認。"""

import psycopg
import pytest

from .test_stats_storage import admin_connection as admin_connection
from .test_stats_storage import stats_owner as stats_owner
from .test_stats_storage import tested_role_connection as tested_role_connection

pytestmark = pytest.mark.requires_db


@pytest.mark.parametrize("role", ["pitchlog_app", "pitchlog_sync_binding_actor"])
def test_undo_stats_helper_is_invoker_and_not_directly_executable(stats_owner, role):
    """実catalogでprivate helperを確認し、非ownerの直接SQL能力を増やさない。"""
    signature = (
        "stats_api.rebuild_after_nonplay_undo(uuid,uuid,uuid,bytea,uuid,uuid,text)"
    )
    with psycopg.connect(stats_owner.authority.database.business_admin) as conn:
        row = conn.execute(
            "SELECT p.prosecdef,pg_get_function_result(p.oid),r.rolname,"
            "has_function_privilege(%s,p.oid,'EXECUTE'),p.proconfig "
            "FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner "
            "WHERE p.oid=%s::regprocedure",
            (role, signature),
        ).fetchone()
        assert row is not None
        assert row[:4] == (
            False,
            "TABLE(receipt_json text)",
            "pitchlog_sync_right_fn_owner",
            False,
        )
        assert row[4] == ["search_path=pg_catalog, pg_temp"]
        consumed = conn.execute(
            "SELECT pg_get_function_result(p.oid) FROM pg_proc p "
            "WHERE p.oid='sync_right_api.consume_nonplay_undo"
            "(uuid,uuid,uuid,bytea,uuid,uuid,text)'::regprocedure"
        ).fetchone()
        assert consumed == ("TABLE(receipt_json text)",)
