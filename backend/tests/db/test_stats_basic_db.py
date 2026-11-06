"""基本成績候補SQLをowned隔離PGで構文・所有者・実行境界まで確認する。"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from pitchlog.db import current_product_startup as current

from .test_stage_a_rule_candidates import _fresh_schema_database

pytestmark = pytest.mark.requires_db


def test_basic_stats_read_installs_with_current_product(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """正式製品起動がread関数・owner・ACLを直接配置する。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        current.advance_current_product_from_s0(owner_dsn=owner, applicator_dsn=admin)
        with psycopg.connect(admin) as connection:
            rows = connection.execute(
                "SELECT n.nspname,p.proname,r.rolname,p.prosecdef,"
                "p.provolatile,pg_catalog.pg_get_userbyid(p.proowner) "
                "FROM pg_catalog.pg_proc p "
                "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
                "JOIN pg_catalog.pg_roles r ON r.oid=p.proowner "
                "WHERE n.nspname='stats_basic_api' ORDER BY p.proname"
            ).fetchall()
            assert [row[1] for row in rows] == ["read_basic_stats"]
            assert all(row[3] is True for row in rows)
            assert {row[1]: row[4] for row in rows} == {
                "read_basic_stats": "s",
            }
            assert all(row[5] == "pitchlog_sync_right_fn_owner" for row in rows)
            acl = connection.execute(
                "SELECT has_function_privilege('pitchlog_app', "
                "'stats_basic_api.read_basic_stats(uuid,text,text,text,text,text,"
                "boolean,text,integer,text)', 'EXECUTE'), "
                "has_schema_privilege('pitchlog_app', 'stats_basic_api', 'USAGE')"
            ).fetchone()
            assert acl == (True, True)
            source_row = connection.execute(
                "SELECT pg_catalog.pg_get_functiondef("
                "'stats_basic_api.read_basic_stats(uuid,text,text,text,text,text,"
                "boolean,text,integer,text)'::pg_catalog.regprocedure)"
            ).fetchone()
            assert source_row is not None
            source = source_row[0]
            assert "game_lifecycle_heads" in source
            assert "lifecycle_write_admissions" in source


def test_product_has_no_test_only_finalize_function(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """製品起動に試験専用の終了偽造関数を配置しない。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        current.advance_current_product_from_s0(owner_dsn=owner, applicator_dsn=admin)
        with psycopg.connect(admin) as connection:
            row = connection.execute(
                "SELECT pg_catalog.to_regprocedure("
                "'stats_basic_api.finalize_game_stats(uuid,uuid,uuid,uuid,text)')"
            ).fetchone()
            assert row == (None,)
