"""通常49の正式配置だけで新規試合の実出場/成績/CSVを接続する。"""

from __future__ import annotations

import json
import selectors
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.db import current_product_startup as current

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
from .test_stats_appearance_http import _lifecycle_appearance_script
from .test_substitution_vertical_http import _script as substitution_script

pytestmark = pytest.mark.requires_db
_STARTER = "00000000-0000-0000-0000-000000000065"
_RELIEF = "00000000-0000-0000-0000-00000000006f"


@pytest.fixture(autouse=True)
def _whole_owned_lifetime_lock():
    """PG配置より前から破棄後まで共通network lockを維持する。"""
    with owned_pg_browser_network_lock():
        yield


def _stage(name: str) -> str:
    """hostの原本観測は読取だけとし、続行の合図以外をAPIへ渡さない。"""
    return (
        '        print("D03_NORMAL49:" + json.dumps({"stage":'
        + repr(name)
        + ',"game":game}), flush=True)\n'
        '        assert input() == "continue"\n'
    )


def normal49_script() -> str:
    """既r20と交代の実要求形成を再利用し、同一試合へ直列接続する。"""
    script = _lifecycle_appearance_script()
    before = (
        '        results = [\n            "batting-result.called-pitch",\n'
        '            "batting-result.called-pitch",\n        ]'
    )
    assert script.count(before) == 1
    script = script.replace(
        before,
        before.replace("        ]", '            "batting-result.ball",\n        ]'),
        1,
    )
    script = script.replace(
        "assert pitch_count(first_stats) == 2",
        "assert pitch_count(first_stats) == 3",
        1,
    )
    script = script.replace(
        "assert pitch_count(final_stats) == 3",
        "assert pitch_count(final_stats) == 4",
        1,
    )
    old = (
        '                expected = int(row["player_id"] ==\n'
        '                               "00000000-0000-0000-0000-000000000065")'
    )
    assert script.count(old) == 1
    script = script.replace(
        old,
        '                expected = int(row["player_id"] in '
        + repr((_STARTER, _RELIEF))
        + ")",
        1,
    )
    source = substitution_script()
    start = source.index("        before, frames = await read_full()\n")
    end = source.index("        pitched = await additional_play()\n", start)
    sub = source[start:end]
    assert sub.count("assert len(frames) == 2") == 1
    assert sub.count("assert len(after_frames) == 2") == 1
    sub = sub.replace("assert len(frames) == 2", "assert len(frames) == 3", 1)
    sub = sub.replace(
        "assert len(after_frames) == 2", "assert len(after_frames) == 3", 1
    )
    sub = sub.replace("00000000-0000-0000-0000-0000000000d3", _RELIEF)
    sub = sub.replace("00000000-0000-0000-0000-0000000000c9", _STARTER)
    reads = """        async def current_appearances(expected):
            response = await client.get('/games/' + game +
                '/stats?mode=current&limit=200', headers=headers())
            assert response.status_code == 200, ('current-stats', response.status_code)
            values = {row['player_id']: next(m for m in row['pitching']
                if m['metric_id'] == 'appearances')
                for row in response.json()['players']}
            assert set(expected) <= set(values)
            for player, metric in values.items():
                assert metric['state'] == 'available', (player, metric)
                assert metric['value'] == int(player in expected), (player, metric)
"""
    marker = "        current_lifecycle, _ = await read_full()\n"
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        reads
        + "        await current_appearances("
        + repr((_STARTER,))
        + ")\n"
        + _stage("before-sub")
        + sub
        + "        await current_appearances("
        + repr((_STARTER, _RELIEF))
        + ")\n"
        + _stage("after-sub")
        + marker,
        1,
    )
    marker = '        assert final["lifecycle"]["lastVersion"] == "2"\n'
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker
        + "        reloaded, _ = await read_full()\n"
        + '        assert reloaded["checkpoint"] == final["checkpoint"]\n'
        + '        assert reloaded["lifecycle"] == final["lifecycle"]\n',
        1,
    )
    marker = (
        '            "stats_pitch_counts": [pitch_count(first_stats), '
        "pitch_count(final_stats)],"
    )
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker
        + '\n            "normal49_versions": {"first":ended["lifecycle"],'
        + '"reopened":reopened["lifecycle"],"final":reloaded["lifecycle"]},',
        1,
    )
    marker = '            "stats_pitch_counts": '
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        '            "normal49_substitution": {"eventId":event["payload"]["eventId"],'
        '"d5":event["d5"]},\n' + marker,
        1,
    )
    for rows in ("csv_rows", "season_csv_rows"):
        marker = (
            f"        assert next(r for r in {rows} if r['player_id'] == "
            f"'{_STARTER}')['pitching_appearances'] == '1'\n"
        )
        assert script.count(marker) == 1
        relief_check = marker.replace(_STARTER, _RELIEF)
        script = script.replace(marker, marker + relief_check, 1)
    marker = "        started = start.json()"
    assert script.count(marker) == 1
    script = script.replace(marker, marker + "\n" + _stage("start-zero"), 1)
    return script


def _assert_normal49(admin) -> None:
    """正式49/fullcatalogとowner-only helper/親hookを追加DDL無しで確認する。"""
    assert admin.execute("SELECT version_num FROM alembic_version").fetchall() == [
        ("0049_pitcher_entry_sources",)
    ]
    current._check_current_structure(admin)
    current._check_pitcher_entry_guards(admin, "full")
    assert current._catalog(admin).ok
    for identity, owner in (
        (
            "initial_right_api.persist_start_pitcher_entry(uuid,uuid,bigint)",
            "pitchlog_initial_fn_owner",
        ),
        (
            "stats_api.persist_writer_pitcher_entry(uuid,uuid,uuid,bytea)",
            "pitchlog_sync_right_fn_owner",
        ),
        ("stats_api.protect_pitcher_entry_sources()", "pitchlog_sync_right_fn_owner"),
        (
            "stats_api.read_pitcher_appearance_context(uuid,uuid)",
            "pitchlog_sync_right_fn_owner",
        ),
        (
            "stats_api.read_pitcher_appearance_source(uuid,uuid,boolean)",
            "pitchlog_sync_right_fn_owner",
        ),
    ):
        assert admin.execute(
            "SELECT r.rolname,p.prosecdef,EXISTS(SELECT 1 FROM pg_catalog.aclexplode("
            "COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a "
            "WHERE a.grantee=0 AND a.privilege_type='EXECUTE') "
            "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles r ON r.oid=p.proowner "
            "WHERE p.oid=pg_catalog.to_regprocedure(%s)",
            (identity,),
        ).fetchone() == (owner, True, False)
        for role in (
            "pitchlog_app",
            "pitchlog_initial_actor",
            "pitchlog_sync_binding_actor",
            "pitchlog_rg1_control_actor",
        ):
            assert admin.execute(
                "SELECT has_function_privilege(%s,%s,'EXECUTE')", (role, identity)
            ).fetchone() == (False,)
    for identity, helper, count in (
        (
            "initial_right_api.insert_initial_grant(uuid,uuid,uuid,uuid,uuid,bigint,bigint,bytea,text,bytea,bytea)",
            "persist_start_pitcher_entry",
            1,
        ),
        (
            "stats_api.save_primitive_source(uuid,uuid,uuid,text,bigint,text,jsonb,bytea)",
            "persist_writer_pitcher_entry",
            2,
        ),
        (
            "sync_right_api.consume_nonplay_substitution(uuid,uuid,uuid,bytea,uuid,uuid,text)",
            "persist_writer_pitcher_entry",
            1,
        ),
    ):
        row = admin.execute(
            "SELECT pg_get_functiondef(%s::regprocedure)", (identity,)
        ).fetchone()
        assert (
            row is not None
            and row[0].count(
                "PERFORM "
                + (
                    "initial_right_api."
                    if count == 1 and helper == "persist_start_pitcher_entry"
                    else "stats_api."
                )
                + helper
            )
            == count
        )


def _observe(admin, tenant, game, stage) -> dict:
    """真正entry/native source/CPを同観測取引で取得し、期待sourceを保存しない。"""
    entries = admin.execute(
        "SELECT origin_kind,d1,player_id,defending_side,inning,half "
        "FROM sync_fence.pitcher_entry_sources WHERE tenant_id=%s AND game_id=%s "
        "ORDER BY d1 NULLS FIRST",
        (tenant, game),
    ).fetchall()
    assert entries[0] == ("start", None, UUID(_STARTER), "home", 1, "top")
    if stage == "start-zero":
        assert len(entries) == 1
        assert admin.execute(
            "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s AND game_id=%s",
            (tenant, game),
        ).fetchone() == (0,)
        return {"entries": entries}
    versions = admin.execute(
        "SELECT id,revision,source_set_sha256,source_count "
        "FROM sync_fence.stats_fact_versions "
        "WHERE tenant_id=%s AND game_id=%s AND is_current AND invalidated_at IS NULL",
        (tenant, game),
    ).fetchall()
    assert len(versions) == 1 and versions[0][3] == 3
    sources = admin.execute(
        "SELECT source_event_id,recording_generation,d1,d2,slot_version,play_row_id,"
        "play_row_version,source_fingerprint FROM sync_fence.stats_primitive_sources "
        "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s "
        "ORDER BY d1,d2,source_event_id",
        (tenant, game, versions[0][0]),
    ).fetchall()
    assert len(sources) == 3
    cp = admin.execute(
        "SELECT id,revision,content_digest FROM sync_fence.ordinary_pitch_checkpoints "
        "WHERE tenant_id=%s AND game_id=%s AND state='current'",
        (tenant, game),
    ).fetchone()
    if stage == "after-sub":
        assert len(entries) == 2
        assert entries[1] == ("substitution", 4, UUID(_RELIEF), "home", 1, "top")
        assert admin.execute(
            "SELECT count(*) FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s AND pitcher_id=%s",
            (tenant, game, UUID(_RELIEF)),
        ).fetchone() == (0,)
    return {
        "entries": entries,
        "versions": versions,
        "sources": sources,
        "checkpoint": cp,
    }


def test_normal49_new_game_zero_pitch_relief_reopen_stats_and_csv(vertical_database):
    """候補DDLを追加せず、同一新規試合の出場/終了版/CSVを実経路で通す。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _assert_normal49(admin)
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        fixture = admin.execute(
            "SELECT scheduled_at,away_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert fixture is not None and isinstance(fixture[0], datetime)
        admin.execute(
            "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
            "uniform_number,"
            "roster_status_key) VALUES(%s,%s,%s,'継投試験選手','11','active')",
            (db.tenant_id, UUID(_RELIEF), fixture[1]),
        )
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "other_team_name": db.other_team_name,
        "other_tenant_id": str(db.other_tenant_id),
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
        "year": fixture[0].astimezone(timezone(timedelta(hours=9))).year,
    }
    observations = {}
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        ordinary._prepare_app_configuration(db)
        args = [
            "docker",
            *ordinary._app_arguments(db, case),
            "-u",
            "-c",
            normal49_script(),
        ]
        assert args[1] == "run"
        args.insert(2, "-i")
        with subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as worker:
            assert worker.stdout is not None
            for stage in ("start-zero", "before-sub", "after-sub"):
                with selectors.DefaultSelector() as ready:
                    ready.register(worker.stdout, selectors.EVENT_READ)
                    if not ready.select(timeout=400):
                        worker.kill()
                        worker.communicate(timeout=10)
                        pytest.fail("通常49の原本観測点に到達しない: " + stage)
                line = worker.stdout.readline()
                assert line.startswith("D03_NORMAL49:"), line
                value = json.loads(line.split(":", 1)[1])
                assert value["stage"] == stage
                game = UUID(value["game"])
                assert game != db.game_id
                with psycopg.connect(db.authority.database.business_admin) as admin:
                    observations[stage] = _observe(admin, db.tenant_id, game, stage)
                assert worker.stdin is not None
                worker.stdin.write("continue\n")
                worker.stdin.flush()
            stdout, stderr = worker.communicate(timeout=400)
            assert worker.returncode == 0, (stdout[-1500:], stderr[-1500:])
    output = json.loads(stdout)
    assert "exception" not in output and "exception_type" not in output, output
    assert output["stats_pitch_counts"] == [3, 4]
    assert (
        observations["before-sub"]["versions"] == observations["after-sub"]["versions"]
    )
    assert observations["before-sub"]["sources"] == observations["after-sub"]["sources"]
    assert (
        observations["before-sub"]["checkpoint"]
        != observations["after-sub"]["checkpoint"]
    )
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _assert_normal49(admin)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.pitcher_entry_sources "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, UUID(output["game"])),
        ).fetchone() == (2,)
        proof_event = output["normal49_substitution"]
        assert admin.execute(
            "SELECT source_event_id FROM sync_fence.pitcher_entry_sources "
            "WHERE tenant_id=%s AND game_id=%s AND origin_kind='substitution' "
            "AND d1=4 AND player_id=%s",
            (db.tenant_id, UUID(output["game"]), UUID(_RELIEF)),
        ).fetchone() == (UUID(proof_event["eventId"]),)
        assert admin.execute(
            "SELECT d5,event_kind,d1 FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s AND id=%s",
            (db.tenant_id, UUID(output["game"]), UUID(proof_event["eventId"])),
        ).fetchone() == (UUID(proof_event["d5"]), "substitution", 4)
        versions = output["normal49_versions"]
        assert versions["first"]["lastVersion"] == "1"
        assert versions["reopened"]["active"] is None
        assert versions["reopened"]["activeStatsVersionId"] is None
        assert versions["final"]["lastVersion"] == "2"
        assert (
            versions["first"]["active"]["receiptId"]
            != (versions["final"]["active"]["receiptId"])
        )
        assert admin.execute(
            "SELECT id,source_count,completion_state,completion_receipt_id "
            "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s AND game_id=%s "
            "AND is_current AND invalidated_at IS NULL",
            (db.tenant_id, UUID(output["game"])),
        ).fetchall() == [
            (
                UUID(versions["final"]["activeStatsVersionId"]),
                4,
                "confirmed_ended",
                UUID(versions["final"]["active"]["receiptId"]),
            )
        ]
        assert admin.execute(
            "SELECT is_current,invalidated_at IS NOT NULL "
            "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s AND game_id=%s "
            "AND id=%s AND completion_receipt_id=%s",
            (
                db.tenant_id,
                UUID(output["game"]),
                UUID(versions["first"]["activeStatsVersionId"]),
                UUID(versions["first"]["active"]["receiptId"]),
            ),
        ).fetchone() == (False, True)
    cache = Path.home() / ".cache/pitchlog/d03-normal49-http-child-20261107"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "last-result.json").write_text(
        json.dumps(
            {
                "result": output,
                "observations": observations,
                "normal_revision": current.CURRENT_REVISION,
            },
            default=str,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
