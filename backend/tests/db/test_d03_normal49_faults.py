"""通常49の実writer完了直後の例外で全保存が取り消されることを確認する。"""

import json
import selectors
import subprocess
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from . import test_ordinary_pitch_vertical_http as ordinary
from .owned_pg_network_lock import owned_pg_browser_network_lock
from .sync_writer_binding_support import binding_broker
from .test_d03_normal49_http import _assert_normal49
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
from .test_substitution_vertical_http import _script as substitution_script
from .test_terminal_pitch_storage import _lineup_script

pytestmark = pytest.mark.requires_db

_OBSERVER = r"""
from pitchlog.repositories import transaction as fault_transaction
from pitchlog.repositories.nonplay_prefix import _ConsumeNonplaySubstitution
from pitchlog.sync import stats_native_flush as fault_native

class PlannedD03WriterRollback(Exception):
    pass

fault_armed = False
fault_reached = []

def fault_capture(handle):
    runtime = fault_transaction._TRANSACTION_RUNTIMES[handle._state_key]
    lifetime = handle._writer_lifetime()
    assert runtime[0].in_transaction()
    return runtime, lifetime, runtime[0].get_transaction()

def fault_after(handle, captured, point):
    runtime, lifetime, top = captured
    assert fault_transaction._TRANSACTION_RUNTIMES[handle._state_key] is runtime
    observed = handle._writer_lifetime()
    assert observed[0] is lifetime[0] and observed[1] is lifetime[1]
    assert runtime[0].get_transaction() is top and runtime[0].in_transaction()
    fault_reached.append({"point": point, "same_runtime": True,
                          "same_top": True, "real_writer_returned": True})
    raise PlannedD03WriterRollback()

_fault_original_native = fault_native._flush_native_stats

def fault_native_flush(handle, writer, *args, **kwargs):
    captured = fault_capture(handle) if fault_armed else None
    result = _fault_original_native(handle, writer, *args, **kwargs)
    if fault_armed:
        fault_after(handle, captured, "after_native_d03_csv")
    return result

fault_native._flush_native_stats = fault_native_flush
_fault_original_run = fault_transaction._TenantTransaction.run_function

def fault_run(handle, operation, *args, **kwargs):
    target = fault_armed and type(operation) is _ConsumeNonplaySubstitution
    captured = fault_capture(handle) if target else None
    result = _fault_original_run(handle, operation, *args, **kwargs)
    if target:
        assert result.rows == ((True,),)
        fault_after(handle, captured, "after_substitution_d03_cp")
    return result

fault_transaction._TenantTransaction.run_function = fault_run
"""


def _barrier(stage):
    return (
        '        print("D03_FAULT:" + json.dumps({"stage":'
        + repr(stage)
        + ',"game":game}), flush=True)\n'
        '        assert input() == "continue"\n'
    )


def fault_script(kind):
    """既真正要求形成を保持し、最終新要求一件だけを故障対象にする。"""
    if kind == "native":
        script = _lineup_script().replace("if index in (1, 9):", "if index in ():", 1)
        anchor = (
            "            posted = await client.post(\n"
            '                "/games/" + game + "/sync/events", '
            "headers=h, json=payload\n"
            "            )\n"
        )
        assert script.count(anchor) == 1
        fault = _fault_flow(
            kind,
            'client.post("/games/" + game + "/sync/events", headers=h, json=payload)',
        )
        script = script.replace(
            anchor,
            "            if index == 9:\n"
            + "\n".join(
                "        " + line if line else "" for line in fault.splitlines()
            )
            + "\n"
            + anchor,
            1,
        )
    elif kind == "substitution":
        script = substitution_script()
        begin = script.index("        posted = await send(body, attempt)\n")
        end = script.index("\n\ntry:\n", begin)
        script = (
            script[:begin] + _fault_flow(kind, "send(body, attempt)") + script[end:]
        )
    else:
        raise ValueError("未知writer")
    anchor = "async def run():\n"
    assert script.count(anchor) == 1
    return script.replace(
        anchor, _OBSERVER + "\n" + anchor + "    global fault_armed\n", 1
    )


def _fault_flow(kind, request):
    """baseline取得後だけarmし、例外到達と非成功を独立に確認する。"""
    return (
        _barrier("before")
        + "        from pitchlog.sync.wire_fingerprint import (\n"
        + "            freeze_wire_event, wire_event_fingerprint,\n"
        + "            wire_request_fingerprint)\n"
        + "        frozen = freeze_wire_event(event)\n"
        + "        event_fp = wire_event_fingerprint(frozen)\n"
        + "        request_fp = wire_request_fingerprint(\n"
        + "            game_id=game, d4=event['d4'], events=(frozen,))\n"
        + "        fault_armed = True\n"
        + "        failed = None\n"
        + "        caught = False\n"
        + "        try:\n"
        + "            failed = await "
        + request
        + "\n"
        + "        except PlannedD03WriterRollback:\n"
        + "            caught = True\n"
        + "        finally:\n"
        + "            fault_armed = False\n"
        + "        assert len(fault_reached) == 1, fault_reached\n"
        + "        assert caught or (failed is not None "
        + "and failed.status_code in (500, 503))\n"
        + "        assert failed is None or failed.status_code != 200\n"
        + _barrier("after")
        + '        return {"game": game, "kind":'
        + repr(kind)
        + ',"reached":fault_reached,"exception_caught":caught,'
        + '"event_fp":event_fp,"request_fp":request_fp,'
        + '"d5":event["d5"],"attempt":'
        + ('h["X-Pitchlog-Sync-Attempt"]' if kind == "native" else "attempt")
        + ","
        + '"status":None if failed is None else failed.status_code}\n'
    )


@pytest.fixture(autouse=True)
def _whole_owned_lifetime_lock():
    """fixture作成/破棄を含め共有network lockを維持する。"""
    with owned_pg_browser_network_lock():
        yield


@contextmanager
def _worker(*args, **kwargs):
    """観測assert失敗時もstdin待ちworkerを残さない。"""
    worker = subprocess.Popen(*args, **kwargs)
    try:
        yield worker
    finally:
        if worker.poll() is None:
            worker.kill()
        worker.communicate(timeout=15)


def _snapshot(admin, tenant, game):
    """試験専用readでgame所属全表の全列を同一snapshotから比較する。"""
    tables = admin.execute(
        "SELECT c.table_schema,c.table_name,bool_or(c.column_name='tenant_id') "
        "FROM information_schema.columns c "
        "JOIN information_schema.tables t USING(table_schema,table_name) "
        "WHERE c.table_schema IN ('public','sync_fence') AND t.table_type='BASE TABLE' "
        "GROUP BY c.table_schema,c.table_name "
        "HAVING bool_or(c.column_name='game_id') ORDER BY 1,2"
    ).fetchall()
    result = {}
    for schema, table, has_tenant in tables:
        where = sql.SQL("game_id=%s")
        params = [game]
        if has_tenant:
            where += sql.SQL(" AND tenant_id=%s")
            params.append(tenant)
        query = sql.SQL(
            "SELECT to_jsonb(r)::text FROM {}.{} r WHERE {} ORDER BY 1"
        ).format(sql.Identifier(schema), sql.Identifier(table), where)
        result[schema + "." + table] = [r[0] for r in admin.execute(query, params)]
    result["public.games"] = [
        r[0]
        for r in admin.execute(
            "SELECT to_jsonb(g)::text FROM public.games g WHERE tenant_id=%s AND id=%s",
            (tenant, game),
        )
    ]
    for name in (
        "public.operation_events",
        "public.play_rows",
        "sync_fence.pitcher_entry_sources",
        "sync_fence.stats_fact_versions",
        "sync_fence.stats_primitive_sources",
        "sync_fence.ordinary_pitch_checkpoints",
    ):
        assert name in result, name
    assert any("export" in name for name in result)
    assert any("binding" in name for name in result)
    assert any("slot" in name for name in result)
    return result


@pytest.mark.parametrize("kind", ("native", "substitution"))
def test_normal49_real_writer_failure_rolls_back_all_game_rows(vertical_database, kind):
    """真正Save/交代消費が戻った後でも新D5の全部分保存を残さない。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        _assert_normal49(admin)
        for key, display in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "見逃し三振"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, display),
            )
        home_row = admin.execute(
            "SELECT home_team_record_id FROM public.games WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert home_row is not None
        home = home_row[0]
        admin.execute(
            "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
            "uniform_number,roster_status_key) "
            "VALUES(%s,%s,%s,'故障対向継投選手','11','active')",
            (db.tenant_id, UUID(int=211), home),
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
    observed = {}
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        ordinary._prepare_app_configuration(db)
        args = [
            "docker",
            *ordinary._app_arguments(db, case),
            "-u",
            "-c",
            fault_script(kind),
        ]
        assert args[1] == "run"
        args.insert(2, "-i")
        with _worker(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as worker:
            assert worker.stdout is not None and worker.stdin is not None
            for stage in ("before", "after"):
                with selectors.DefaultSelector() as ready:
                    ready.register(worker.stdout, selectors.EVENT_READ)
                    if not ready.select(timeout=450):
                        worker.kill()
                        stdout, stderr = worker.communicate(timeout=10)
                        pytest.fail(
                            "故障観測点未到達: "
                            + stage
                            + stdout[-1500:]
                            + stderr[-1500:]
                        )
                line = worker.stdout.readline()
                assert line.startswith("D03_FAULT:"), line
                value = json.loads(line.split(":", 1)[1])
                assert value["stage"] == stage
                game = UUID(value["game"])
                assert game != db.game_id
                with psycopg.connect(db.authority.database.business_admin) as admin:
                    admin.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                    observed[stage] = _snapshot(admin, db.tenant_id, game)
                worker.stdin.write("continue\n")
                worker.stdin.flush()
            stdout, stderr = worker.communicate(timeout=60)
            assert worker.returncode == 0, (stdout[-1500:], stderr[-1500:])
    output = json.loads(stdout)
    assert "exception" not in output and "exception_type" not in output, output
    cache = Path.home() / ".cache/pitchlog/d03-normal49-faults-child-20261107"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / (kind + "-result.json")).write_text(
        json.dumps(
            {"output": output, "snapshots": observed}, ensure_ascii=False, indent=2
        )
        + "\n"
    )
    _assert_closed_binding_audit(observed, output)
    changed = [
        name
        for name in observed["before"]
        if name != "sync_fence.writer_bindings"
        if observed["before"][name] != observed["after"][name]
    ]
    assert changed == [], changed
    assert len(observed["before"]["sync_fence.pitcher_entry_sources"]) == 1
    assert len(observed["before"]["public.play_rows"]) == (8 if kind == "native" else 2)


def _assert_closed_binding_audit(observed, output):
    """別actorで残す正規終結監査を、業務保存の全取消とは別に全値照合する。"""
    name = "sync_fence.writer_bindings"
    before = set(observed["before"][name])
    after = set(observed["after"][name])
    assert before <= after, "既監査行の変更/削除を許さない"
    added = after - before
    assert len(added) == 1, "新要求以外の監査行を許さない"
    row = json.loads(added.pop())
    assert row["game_id"] == output["game"]
    assert row["d5"] == output["d5"]
    assert row["attempt_id"] == output["attempt"]
    assert row["event_fingerprint"] == output["event_fp"]
    assert row["request_fingerprint"] == output["request_fp"]
    assert row["state"] == "closed" and row["close_id"] is not None
    assert all(json.loads(value)["state"] == "closed" for value in after)
