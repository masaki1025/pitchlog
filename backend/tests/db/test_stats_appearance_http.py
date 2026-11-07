"""D03内部helperをowned実開始の同TXへ接合する候補検査。正式配備ではない。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
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
    hook = "PERFORM initial_right_api.persist_start_pitcher_entry("
    if hook not in body:
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
        point = "p_tenant_id,p_attempt_id,p_generation);"
        assert body.count(point) == 1
        body = body.replace(
            point,
            point + "\n      RAISE EXCEPTION "
            "'D03 after entry injected fault' USING ERRCODE='42501';",
        )
    admin.execute(sql.SQL(cast(LiteralString, body)))


def _install_csv_candidate(admin):
    """6a基線の既CSV3providerを再利用する候補owned配置。通常47ではない。"""
    from pitchlog.authz.play_export_source_read_product import (
        candidate_read_bundle,
    )
    from pitchlog.authz.play_export_writer_product import candidate_install_sql

    root = Path(__file__).resolve().parents[3]
    admin.execute(
        sql.SQL(
            cast(
                LiteralString,
                (
                    root
                    / "docs/features/ud2-csv-export/candidates"
                    / "play_export_snapshots.sql"
                ).read_text(),
            )
        )
    )
    admin.execute(sql.SQL(cast(LiteralString, candidate_install_sql())))
    admin.execute(sql.SQL(cast(LiteralString, candidate_read_bundle()[1])))


def _diagnostic_script(*, pitch_count=0):
    """認証値/SQL引数を出さずDBの静的停止理由だけを保全する。"""
    observation = """
from sqlalchemy.engine import Connection as Session
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
    assert pitch_count in (0, 3)
    if pitch_count == 0:
        script = script.replace(
            saved, saved + "\n        return {'game':game,'prefix':'0'}", 1
        )
    start = "        start = await client.post("
    assert script.count(start) == 1
    return script.replace(
        start, "        runtime_diagnostics['created_game'] = game\n" + start, 1
    )


@pytest.mark.parametrize(
    ("pitch_count", "fault"),
    [(0, False), (0, True), (3, False)],
    ids=["start-zero", "start-fault", "three-pitch"],
)
def test_actual_http_start_proves_only_current_defending_pitcher(
    vertical_database, monkeypatch, fault, pitch_count
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
                "from sqlalchemy.engine import Connection as Session", 1
            )[1]
            observe = (
                "from sqlalchemy.engine import Connection as Session"
                + observe.split("async def run():", 1)[0]
            )
            observe = observe.replace(
                "from sqlalchemy.engine import Connection as Session",
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
        if pitch_count == 3:
            _install_csv_candidate(admin)
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
                _diagnostic_script(pitch_count=pitch_count),
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
    diagnostic_path = (
        Path.home()
        / ".cache/pitchlog/stats-d03-appearance-author-20261107/entry-connection"
    )
    diagnostic_path.mkdir(parents=True, exist_ok=True)
    (diagnostic_path / f"last-output-{pitch_count}-{fault}.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
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
    assert output["prefix"] == str(pitch_count)
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


@pytest.mark.parametrize("scenario", ["half-entry", "zero-pitch-sub"])
def test_actual_v3_half_and_zero_pitch_substitution_produce_true_entries(
    vertical_database, scenario
):
    """唯一v3の半回遷移/真正0球交代だけから追加entryを保存する。"""
    from .test_substitution_vertical_http import _script as substitution_script
    from .test_terminal_pitch_storage import _lineup_script

    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _install_candidate(admin)
        _install_csv_candidate(admin)
        for key, name in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "見逃し三振"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, name),
            )
        home = admin.execute(
            "SELECT home_team_record_id FROM public.games WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert home is not None
        admin.execute(
            "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
            "uniform_number,roster_status_key) "
            "VALUES(%s,%s,%s,'交代試験選手','11','active')",
            (db.tenant_id, UUID(int=211), home[0]),
        )
        hook_row = admin.execute(
            "SELECT pg_get_functiondef('stats_api.save_primitive_source("
            "uuid,uuid,uuid,text,bigint,text,jsonb,bytea)'::regprocedure)"
        ).fetchone()
        assert hook_row is not None
        assert "persist_writer_pitcher_entry" in hook_row[0], (
            "sourcefactory hook未供給を成功にしない"
        )
    script = _lineup_script() if scenario == "half-entry" else substitution_script()
    if scenario == "zero-pitch-sub":
        marker = "        pitched = await additional_play()"
        assert script.count(marker) == 1
        script = script.replace(
            marker,
            """        return {"game":game,"pitcher":incoming,
            "substitution_event_id":event["payload"]["eventId"],
            "d3":after["checkpoint"]["content"]["d3"]}
"""
            + marker,
            1,
        )
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "other_team_name": db.other_team_name,
        "other_tenant_id": str(db.other_tenant_id),
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        ordinary._prepare_app_configuration(db)
        result = subprocess.run(
            ["docker", *ordinary._app_arguments(db, case), "-u", "-c", script],
            capture_output=True,
            text=True,
            timeout=400,
            check=False,
        )
    assert result.returncode == 0, (result.stdout[-1000:], result.stderr[-1000:])
    output = json.loads(result.stdout)
    path = (
        Path.home()
        / ".cache/pitchlog/stats-d03-appearance-author-20261107/entry-connection"
    )
    (path / f"last-v3-{scenario}.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
    assert "exception" not in output and "exception_type" not in output, output
    game = UUID(output["game"])
    assert game != db.game_id
    with psycopg.connect(db.authority.database.business_admin) as admin:
        entries = admin.execute(
            "SELECT origin_kind,source_event_id,d1,player_id,"
            "defending_side,inning,half "
            "FROM sync_fence.pitcher_entry_sources WHERE tenant_id=%s AND game_id=%s "
            "ORDER BY d1 NULLS FIRST",
            (db.tenant_id, game),
        ).fetchall()
        assert len(entries) == 2
        assert entries[0][0] == "start" and entries[0][4:] == ("home", 1, "top")
        if scenario == "half-entry":
            assert output["prefix"] == "10"
            assert entries[1][0] == "play" and entries[1][2] == 9
            assert entries[1][4:] == ("away", 1, "bottom")
        else:
            assert output["d3"] == "3"
            assert entries[1][0] == "substitution" and entries[1][2] == 3
            assert entries[1][1] == UUID(output["substitution_event_id"])
            assert entries[1][3] == UUID(int=211) and entries[1][4:] == (
                "home",
                1,
                "top",
            )
            assert admin.execute(
                "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s "
                "AND game_id=%s AND pitcher_id=%s",
                (db.tenant_id, game, UUID(int=211)),
            ).fetchone() == (0,)
