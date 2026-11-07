"""D03内部helperをowned実開始の同TXへ接合する候補検査。正式配備ではない。"""

from __future__ import annotations

import json
import selectors
import subprocess
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.product_function_acl import generate_initial_function_sql
from pitchlog.repositories.stats_appearance import (
    candidate_appearance_read_install_sql,
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
    admin.execute(sql.SQL(cast(LiteralString, candidate_appearance_read_install_sql())))
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
            "d3":after["checkpoint"]["content"]["d3"],
            "checkpoint_before":cp["ref"],
            "checkpoint_after":after["checkpoint"]["ref"]}
"""
            + marker,
            1,
        )
    if scenario == "zero-pitch-sub":
        helper = """        async def actual_appearance_stats():
            response = await client.get(
                "/games/" + game + "/stats?mode=current&limit=200", headers=headers())
            assert response.status_code == 200, ("D03 stats HTTP", response.status_code,
                                                response.text)
            return {row["player_id"]: next(m for m in row["pitching"]
                    if m["metric_id"] == "appearances")
                    for row in response.json()["players"]}
        before_appearances = await actual_appearance_stats()
        assert before_appearances["00000000-0000-0000-0000-0000000000c9"]["value"] == 1
        assert before_appearances["00000000-0000-0000-0000-0000000000d3"]["value"] == 0
        assert all(item["state"] == "available" and item["value"] == 0
                   for player_id,item in before_appearances.items()
                   if player_id != "00000000-0000-0000-0000-0000000000c9")
"""
        anchor = '        incoming = "00000000-0000-0000-0000-0000000000d3"'
        assert script.count(anchor) == 1
        script = script.replace(anchor, helper + anchor, 1)
        anchor = '        return {"game":game,"pitcher":incoming,'
        assert script.count(anchor) == 1
        after = """        after_appearances = await actual_appearance_stats()
        assert after_appearances["00000000-0000-0000-0000-0000000000c9"]["value"] == 1
        assert after_appearances["00000000-0000-0000-0000-0000000000d3"]["value"] == 1
        assert all(item["state"] == "available" and item["value"] == 0
                   for player_id,item in after_appearances.items() if player_id not in
                   ["00000000-0000-0000-0000-0000000000c9",
                    "00000000-0000-0000-0000-0000000000d3"])
        csv_response = await client.get("/games/" + game + "/stats.csv?mode=current",
                                        headers=headers())
        assert csv_response.status_code == 200, ("D03 CSV", csv_response.status_code)
        import csv, io
        csv_rows = {r["player_id"]: r for r in csv.DictReader(
                    io.StringIO(csv_response.content.decode("utf-8-sig")))}
        for player_id in ["00000000-0000-0000-0000-0000000000c9",
                          "00000000-0000-0000-0000-0000000000d3"]:
            assert csv_rows[player_id]["pitching_appearances"] == "1"
"""
        script = script.replace(anchor, after + anchor, 1)
    if scenario == "zero-pitch-sub":
        marker = '        incoming = "00000000-0000-0000-0000-0000000000d3"'
        assert script.count(marker) == 1
        script = script.replace(
            marker,
            '        print("D03_OBSERVE:" + json.dumps({"game":game}), flush=True)\n'
            '        assert input() == "continue"\n' + marker,
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
        arguments = ["docker", *ordinary._app_arguments(db, case), "-u", "-c", script]
        native_before = None
        native_sources_before = None
        if scenario == "zero-pitch-sub":
            assert arguments[1] == "run"
            arguments.insert(2, "-i")
            # 実HTTP二球と交代の間にhostが原本を読取るだけ。APIへDB値を渡さない。
            with subprocess.Popen(
                arguments,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ) as worker:
                assert worker.stdout is not None
                with selectors.DefaultSelector() as ready:
                    ready.register(worker.stdout, selectors.EVENT_READ)
                    if not ready.select(timeout=400):
                        worker.kill()
                        worker.communicate(timeout=10)
                        pytest.fail("実二球後の観測地点へ400秒以内に到達しない")
                observation = worker.stdout.readline()
                assert observation.startswith("D03_OBSERVE:"), observation
                observed_game = UUID(json.loads(observation.split(":", 1)[1])["game"])
                with psycopg.connect(db.authority.database.business_admin) as admin:
                    native_before = admin.execute(
                        "SELECT id,revision,source_set_sha256,source_count "
                        "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s "
                        "AND game_id=%s AND is_current AND invalidated_at IS NULL",
                        (db.tenant_id, observed_game),
                    ).fetchall()
                    assert len(native_before) == 1
                    native_sources_before = admin.execute(
                        "SELECT source_event_id,recording_generation,d1,d2,"
                        "slot_version,"
                        "play_row_id,play_row_version,source_fingerprint "
                        "FROM sync_fence.stats_primitive_sources WHERE tenant_id=%s "
                        "AND game_id=%s AND fact_version_id=%s "
                        "ORDER BY d1,d2,source_event_id",
                        (db.tenant_id, observed_game, native_before[0][0]),
                    ).fetchall()
                    assert len(native_sources_before) == 2
                stdout, stderr = worker.communicate("continue\n", timeout=400)
                result = subprocess.CompletedProcess(
                    arguments, worker.returncode, stdout, stderr
                )
        else:
            result = subprocess.run(
                arguments,
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
            native_after = admin.execute(
                "SELECT id,revision,source_set_sha256,source_count "
                "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s "
                "AND game_id=%s AND is_current AND invalidated_at IS NULL",
                (db.tenant_id, game),
            ).fetchall()
            assert native_after == native_before
            native_sources_after = admin.execute(
                "SELECT source_event_id,recording_generation,d1,d2,slot_version,"
                "play_row_id,play_row_version,source_fingerprint "
                "FROM sync_fence.stats_primitive_sources WHERE tenant_id=%s "
                "AND game_id=%s AND fact_version_id=%s ORDER BY d1,d2,source_event_id",
                (db.tenant_id, game, native_after[0][0]),
            ).fetchall()
            assert native_sources_after == native_sources_before
            output["native_observation"] = {
                "before": native_before,
                "after": native_after,
                "sources_before": native_sources_before,
                "sources_after": native_sources_after,
            }
            assert output["checkpoint_before"] != output["checkpoint_after"]
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
            output["source_observation_verified"] = True
            (path / "last-v3-zero-pitch-sub.json").write_text(
                json.dumps(output, ensure_ascii=False, indent=2, default=str) + "\n"
            )


def test_actual_lifecycle_game_and_season_appearance_has_one_current_version(
    vertical_database,
):
    """実終了→通常再開→追記→再終了の試合/暦年/CSVで1登板を維持する。"""
    from datetime import datetime, timedelta, timezone

    from .test_stats_basic_lifecycle_http import _stats_script

    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _install_candidate(admin)
        _install_csv_candidate(admin)
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        scheduled_row = admin.execute(
            "SELECT scheduled_at FROM public.games WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert scheduled_row is not None and isinstance(scheduled_row[0], datetime)
        scheduled = scheduled_row[0]
    script = _stats_script()
    # 正規POSTのチーム選択と開始入力を対で入替え、自チームを後攻にする。
    teams = (
        '"away_team_record_id": source["away_team_record_id"],\n'
        '                "home_team_record_id": source["home_team_record_id"],'
    )
    swapped_teams = (
        '"away_team_record_id": source["home_team_record_id"],\n'
        '                "home_team_record_id": source["away_team_record_id"],'
    )
    assert script.count(teams) == 1
    script = script.replace(teams, swapped_teams, 1)
    source_anchor = "        created = await client.post(\n"
    assert script.count(source_anchor) == 1
    script = script.replace(
        source_anchor,
        '        assert source["game_type_key"] == "game_other"\n' + source_anchor,
        1,
    )
    anchor = "        body = _body(10)\n"
    assert script.count(anchor) == 1
    script = script.replace(
        anchor,
        anchor + '        body["away"], body["home"] = body["home"], body["away"]\n',
        1,
    )
    helper = """        def assert_appearances(packet):
            found = False
            for row in packet["players"]:
                item = next(m for m in row["pitching"]
                            if m["metric_id"] == "appearances")
                expected = int(row["player_id"] ==
                               "00000000-0000-0000-0000-000000000065")
                assert item["state"] == "available" and item["value"] == expected, item
                found = found or expected == 1
            assert found

"""
    anchor = "        current_lifecycle, _ = await read_full()\n"
    assert script.count(anchor) == 1
    script = script.replace(anchor, helper + anchor, 1)
    for anchor in (
        "        assert pitch_count(first_stats) == 2\n",
        "        assert pitch_count(final_stats) == 3\n",
    ):
        assert script.count(anchor) == 1
        packet = "first_stats" if "first_stats" in anchor else "final_stats"
        script = script.replace(
            anchor, anchor + f"        assert_appearances({packet})\n", 1
        )
    anchor = '        assert season_stats["players"]\n'
    assert script.count(anchor) == 1
    script = script.replace(
        anchor,
        anchor + "        assert_appearances(season_stats)\n",
        1,
    )
    anchor = '        assert len(csv_rows) == len(final_stats["players"])\n'
    assert script.count(anchor) == 1
    script = script.replace(
        anchor,
        anchor + "        assert next(r for r in csv_rows if r['player_id'] == "
        "'00000000-0000-0000-0000-000000000065')['pitching_appearances'] == '1'\n",
        1,
    )
    anchor = '        assert len(season_csv_rows) == len(season_stats["players"])\n'
    assert script.count(anchor) == 1
    script = script.replace(
        anchor,
        anchor + "        assert next(r for r in season_csv_rows if r['player_id'] == "
        "'00000000-0000-0000-0000-000000000065')['pitching_appearances'] == '1'\n"
        + "        for category in ['official','practice']:\n"
        + "            selected = await client.get('/stats/seasons/' "
        "+ str(case['year']) "
        "+ '?category=' + category + '&limit=200', headers=headers())\n"
        + "            assert selected.status_code == 200\n"
        + "            if category == 'practice':\n"
        + "                assert_appearances(selected.json())\n"
        + "            else:\n"
        + "                assert selected.json()['players'] == []\n",
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
        "year": scheduled.astimezone(timezone(timedelta(hours=9))).year,
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
    assert result.returncode == 0, (result.stdout[-2000:], result.stderr[-2000:])
    output = json.loads(result.stdout)
    assert "exception" not in output and "exception_type" not in output, output
    assert output["stats_pitch_counts"] == [2, 3]
    cache = (
        Path.home()
        / ".cache/pitchlog/stats-d03-appearance-author-20261107/entry-connection"
    )
    (cache / "last-lifecycle-appearance.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
