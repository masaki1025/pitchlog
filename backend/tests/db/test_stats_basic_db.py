"""基本成績候補SQLをowned隔離PGで構文・所有者・実行境界まで確認する。"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any, LiteralString, cast

import psycopg
import pytest

from pitchlog.db import current_product_startup as current
from pitchlog.stats.basic_sql import candidate_sql

from .test_stage_a_rule_candidates import _fresh_schema_database

pytestmark = pytest.mark.requires_db


def test_candidate_basic_stats_functions_install_on_current_product(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """現行0041の後に候補関数だけを置き、owner/ACL/構文を実DBで確認する。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        current.advance_current_product_from_s0(owner_dsn=owner, applicator_dsn=admin)
        with psycopg.connect(admin) as connection:
            connection.execute(cast(LiteralString, candidate_sql()))
            rows = connection.execute(
                "SELECT n.nspname,p.proname,r.rolname,p.prosecdef,"
                "p.provolatile,pg_catalog.pg_get_userbyid(p.proowner) "
                "FROM pg_catalog.pg_proc p "
                "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
                "JOIN pg_catalog.pg_roles r ON r.oid=p.proowner "
                "WHERE n.nspname='stats_basic_api' ORDER BY p.proname"
            ).fetchall()
            assert [row[1] for row in rows] == [
                "finalize_game_stats",
                "read_basic_stats",
            ]
            assert all(row[3] is True for row in rows)
            assert {row[1]: row[4] for row in rows} == {
                "finalize_game_stats": "v",
                "read_basic_stats": "s",
            }
            assert all(row[5] == "pitchlog_sync_right_fn_owner" for row in rows)
            acl = connection.execute(
                "SELECT has_function_privilege('pitchlog_app', "
                "'stats_basic_api.read_basic_stats(uuid,uuid,text,text,text,text,"
                "boolean,text,integer,text)', 'EXECUTE'), "
                "has_function_privilege('pitchlog_app', "
                "'stats_basic_api.finalize_game_stats(uuid,uuid,uuid,uuid,text)', "
                "'EXECUTE'), "
                "has_schema_privilege('pitchlog_app', 'stats_basic_api', 'USAGE')"
            ).fetchone()
            assert acl == (True, True, True)


def test_candidate_finalize_promotes_only_current_opening_version(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """候補finalizeがcurrent_openだけを昇格し、同receipt再実行を冪等にする。"""
    from uuid import uuid4

    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        current.advance_current_product_from_s0(owner_dsn=owner, applicator_dsn=admin)
        tenant, game, version = uuid4(), uuid4(), uuid4()
        receipt, pointer = uuid4(), uuid4()
        with psycopg.connect(admin) as connection:
            connection.execute(cast(LiteralString, candidate_sql()))
            connection.execute(
                "INSERT INTO public.tenants(id,name) VALUES (%s,%s)",
                (tenant, "basic-stats-" + tenant.hex),
            )
            teams = (uuid4(), uuid4())
            for index, team in enumerate(teams):
                connection.execute(
                    "INSERT INTO public.team_records(tenant_id,id,kind,name) "
                    "VALUES (%s,%s,%s,%s)",
                    (tenant, team, "self" if index == 0 else "opponent", "成績試験"),
                )
            connection.execute(
                "INSERT INTO public.tenant_vocabularies(tenant_id,key,category,"
                "display_name) VALUES(%s,'basic-stats-tournament','tournament','成績試験')",
                (tenant,),
            )
            connection.execute(
                "INSERT INTO public.games(tenant_id,id,scheduled_at,game_type_key,"
                "tournament_key,away_team_record_id,home_team_record_id,applied_rules,"
                "status) SELECT %s,%s,pg_catalog.now(),'game_other',"
                "'basic-stats-tournament',%s,%s,pg_catalog.jsonb_build_object("
                "'ruleSetId',r.id,'regulationInnings',r.regulation_innings,"
                "'cold',r.called_game_conditions,'overtime',r.extra_innings_limit,"
                "'tiebreak',r.tiebreak_rule,'dh',r.uses_dh),'finished' "
                "FROM public.rule_sets r JOIN public.game_type_rule_defaults d "
                "ON d.rule_set_id=r.id WHERE d.game_type_key='game_other'",
                (tenant, game, *teams),
            )
            connection.execute(
                "INSERT INTO sync_fence.stats_fact_versions("
                "tenant_id,game_id,id,model_sha256,rule_sha256,"
                "t5_artifact_set_sha256,source_set_sha256,source_count,revision,"
                "last_generation,last_d1,last_d2,updated_at,computed_metric_keys,"
                "is_current,completion_state,completion_receipt_id,"
                "public_pointer_receipt_id,created_at,invalidated_at) VALUES("
                "%s,%s,%s,%s,%s,%s,%s,0,1,NULL,NULL,NULL,pg_catalog.now(),"
                "'{}'::text[],true,'current_open',NULL,NULL,pg_catalog.now(),NULL)",
                (
                    tenant,
                    game,
                    version,
                    "sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d",
                    "0" * 64,
                    "1" * 64,
                    "2" * 64,
                ),
            )
            connection.execute(
                "GRANT UPDATE(completion_state,completion_receipt_id,"
                "public_pointer_receipt_id) ON sync_fence.stats_fact_versions "
                "TO pitchlog_sync_right_fn_owner"
            )
            connection.execute(
                "CREATE POLICY stats_basic_finalize ON "
                "sync_fence.stats_fact_versions FOR UPDATE TO "
                "pitchlog_sync_right_fn_owner USING ("
                "tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid "
                "AND session_user='pitchlog_app' AND completion_state='current_open') "
                "WITH CHECK ("
                "tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid "
                "AND session_user='pitchlog_app' AND completion_state='confirmed_ended' "
                "AND completion_receipt_id IS NOT NULL AND "
                "public_pointer_receipt_id IS NOT NULL)"
            )
            connection.execute("SET SESSION AUTHORIZATION pitchlog_app")
            connection.execute(
                "SELECT set_config('app.tenant_id',%s,false)", (str(tenant),)
            )
            first = connection.execute(
                "SELECT fact_version_id,revision,completion_state "
                "FROM stats_basic_api.finalize_game_stats(%s,%s,%s,%s,%s)",
                (
                    tenant,
                    game,
                    receipt,
                    pointer,
                    "sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d",
                ),
            ).fetchall()
            second = connection.execute(
                "SELECT fact_version_id,revision,completion_state "
                "FROM stats_basic_api.finalize_game_stats(%s,%s,%s,%s,%s)",
                (
                    tenant,
                    game,
                    receipt,
                    pointer,
                    "sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d",
                ),
            ).fetchall()
            assert first == second == [(version, 1, "confirmed_ended")]
