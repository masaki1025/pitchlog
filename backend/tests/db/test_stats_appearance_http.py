"""D03内部helperをowned実開始の同TXへ接合する候補検査。正式配備ではない。"""

from __future__ import annotations

import json
import subprocess
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.product_function_acl import generate_initial_function_sql
from pitchlog.repositories.stats_appearance import (
    candidate_entry_table_install_sql,
    candidate_private_entry_install_sql,
)

from . import test_ordinary_pitch_vertical_http as ordinary
from .owned_pg_network_lock import owned_pg_browser_network_lock
from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import _PASSWORD, _PITCH_TYPE
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import admin_connection as admin_connection
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _whole_owned_lifetime_lock():
    """PG生成前から破棄後までネットワーク変更と競合させない。"""
    with owned_pg_browser_network_lock():
        yield


def _install_candidate(admin, *, fault=False):
    """正式catalogを更新せず、明示候補としてownedだけへ接合する。"""
    admin.execute(sql.SQL(cast(LiteralString, candidate_entry_table_install_sql())))
    admin.execute(sql.SQL(cast(LiteralString, candidate_private_entry_install_sql())))
    identity = (
        "FUNCTION:initial_right_api:insert_initial_grant(uuid, uuid, "
        "uuid, uuid, uuid, bigint, bigint, bytea, text, bytea, bytea)"
    )
    body = generate_initial_function_sql(identity)
    marker = "    RETURN true;\nEXCEPTION"
    assert body.count(marker) == 1
    body = body.replace(
        marker,
        """    IF EXISTS(SELECT 1 FROM public.games g
      WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id
      AND g.status='in_progress' AND g.started_at IS NOT NULL) THEN
      PERFORM initial_right_api.persist_start_pitcher_entry(
        p_tenant_id,p_attempt_id,p_generation);
    END IF;
"""
        + marker,
    )
    if fault:
        point = "        p_tenant_id,p_attempt_id,p_generation);"
        assert body.count(point) == 1
        body = body.replace(
            point,
            point + "\n      RAISE EXCEPTION "
            "'D03 after entry injected fault' USING ERRCODE='42501';",
        )
    admin.execute(sql.SQL(cast(LiteralString, body)))


def _diagnostic_script():
    """認証値/SQL引数を出さずDBの静的停止理由だけを保全する。"""
    observation = """
from sqlalchemy.orm import Session
_original_session_execute = Session.execute

def _entry_observed_execute(self, *args, **kwargs):
    try:
        return _original_session_execute(self, *args, **kwargs)
    except Exception as error:
        original = getattr(error, "orig", None)
        code = getattr(original, "sqlstate", None)
        diagnostic = getattr(original, "diag", None)
        runtime_diagnostics.update(
            entry_sqlstate=code,
            entry_primary=(getattr(diagnostic, "message_primary", None)
                if code in {"42501", "42703", "42883", "42P01", "42804",
                            "42702", "42601", "P0002", "22P02", "23514"}
                else None),
        )
        raise
Session.execute = _entry_observed_execute

"""
    marker = "async def run():"
    assert ordinary._SCRIPT.count(marker) == 1
    script = ordinary._SCRIPT.replace(marker, observation + marker, 1)
    saved = "        started = start.json()"
    assert script.count(saved) == 1
    script = script.replace(
        saved, saved + "\n        return {'game':game,'prefix':'0'}", 1
    )
    start = "        start = await client.post("
    assert script.count(start) == 1
    return script.replace(
        start, "        runtime_diagnostics['created_game'] = game\n" + start, 1
    )


@pytest.mark.parametrize("fault", [False, True])
def test_actual_http_start_proves_only_current_defending_pitcher(
    vertical_database, monkeypatch, fault
):
    """実作成/開始直後0球の後攻投手出場と未守備先攻不計上を確認する。"""
    db = vertical_database
    from . import initial_recording_right_scope_support as support

    original_docker = support.docker

    def observed_docker(*args, **kwargs):
        args = list(args)
        if (
            args
            and isinstance(args[-1], str)
            and "serve_initial_broker(Path" in args[-1]
        ):
            observe = _diagnostic_script().split(
                "from sqlalchemy.orm import Session", 1
            )[1]
            observe = (
                "from sqlalchemy.orm import Session"
                + observe.split("async def run():", 1)[0]
            )
            observe = observe.replace(
                "from sqlalchemy.orm import Session",
                "from sqlalchemy.engine import Connection as Session",
            )
            observe = observe.replace("runtime_diagnostics.update(", "print(dict(")
            observe = observe.replace(
                "        )\n        raise", "        ),flush=True)\n        raise"
            )
            args[-1] = observe + args[-1]
        return original_docker(*args, **kwargs)

    monkeypatch.setattr(support, "docker", observed_docker)
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _install_candidate(admin, fault=fault)
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        assert admin.execute(
            "SELECT has_function_privilege('pitchlog_app',"
            "'initial_right_api.persist_start_pitcher_entry(uuid,uuid,bigint)',"
            "'EXECUTE')"
        ).fetchone() == (False,)
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
    }
    token = uuid4()
    with db.broker_worker(token) as worker, binding_broker(db, token):
        ordinary._prepare_app_configuration(db)
        result = subprocess.run(
            [
                "docker",
                *ordinary._app_arguments(db, case),
                "-u",
                "-c",
                _diagnostic_script(),
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        diagnostic = subprocess.run(
            ["docker", "logs", worker], capture_output=True, text=True, check=False
        )
    assert result.returncode == 0, (result.stdout[-1000:], result.stderr[-1000:])
    output = json.loads(result.stdout)
    if fault:
        assert "('start', 503" in output["exception"], output
        assert "D03 after entry injected fault" in diagnostic.stdout
        game = UUID(output["runtime_diagnostics"]["created_game"])
        assert game != db.game_id
        with psycopg.connect(db.authority.database.business_admin) as admin:
            assert admin.execute(
                "SELECT status FROM public.games WHERE tenant_id=%s AND id=%s",
                (db.tenant_id, game),
            ).fetchone() == ("preparing",)
            for relation in (
                "sync_fence.pitcher_entry_sources",
                "public.game_lineups",
                "public.recording_generations",
                "public.operation_events",
            ):
                assert admin.execute(
                    sql.SQL(
                        "SELECT count(*) FROM {} WHERE tenant_id=%s AND game_id=%s"
                    ).format(sql.Identifier(*relation.split("."))),
                    (db.tenant_id, game),
                ).fetchone() == (0,)
        return
    assert "exception" not in output, (
        output,
        diagnostic.stdout[-2000:],
        diagnostic.stderr[-2000:],
    )
    assert output["prefix"] == "0"
    game = UUID(output["game"])
    assert game != db.game_id
    with psycopg.connect(db.authority.database.business_admin) as admin:
        proofs = admin.execute(
            "SELECT origin_kind,start_attempt_id,source_event_id,d1,slot_version,"
            "player_id,defending_side,inning,half,context_sha256 "
            "FROM sync_fence.pitcher_entry_sources WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, game),
        ).fetchall()
        assert len(proofs) == 1
        proof = proofs[0]
        assert proof[0] == "start" and proof[1] is not None
        assert proof[2:5] == (None, None, None)
        assert proof[6:9] == ("home", 1, "top") and len(proof[9]) == 64
        pitcher = admin.execute(
            "SELECT (e.value->>'player_id')::uuid FROM public.game_lineups l "
            "JOIN public.games g ON (g.tenant_id,g.id)=(l.tenant_id,l.game_id) "
            "CROSS JOIN LATERAL jsonb_array_elements("
            "l.entries_with_uniform_number_snapshot) e(value) "
            "WHERE g.tenant_id=%s AND g.id=%s "
            "AND l.team_record_id=g.home_team_record_id "
            "AND e.value->'fielding_position'="
            '\'{"kind":"fielding","position":1}\'::jsonb',
            (db.tenant_id, game),
        ).fetchone()
        assert pitcher == (proof[5],)

    # 実ownerでも監査原本の破壊は拒否され、actor/appからhelperを直呼出できない。
    for statement in (
        "UPDATE sync_fence.pitcher_entry_sources SET inning=2 WHERE game_id=%s",
        "DELETE FROM sync_fence.pitcher_entry_sources WHERE game_id=%s",
        "TRUNCATE sync_fence.pitcher_entry_sources",
    ):
        with psycopg.connect(db.authority.database.business_admin) as admin:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with admin.transaction():
                    admin.execute("SET LOCAL ROLE pitchlog_sync_right_fn_owner")
                    admin.execute(
                        "SELECT set_config('app.tenant_id',%s,true)",
                        (str(db.tenant_id),),
                    )
                    admin.execute(
                        sql.SQL(statement), (game,) if "%s" in statement else ()
                    )
    with psycopg.connect(db.authority.database.business_admin) as actor:
        actor.execute("SET SESSION AUTHORIZATION pitchlog_initial_actor")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            actor.execute(
                "SELECT * FROM initial_right_api.persist_start_pitcher_entry(%s,%s,1)",
                (db.tenant_id, proof[1]),
            )
