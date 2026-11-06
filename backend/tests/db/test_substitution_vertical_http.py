"""新規試合の交代を実HTTP・owned PGで保存し次球へ連結する。"""

import json
import subprocess
from uuid import UUID, uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_game_lifecycle_v3_http import _v3_script
from .test_terminal_pitch_storage import (
    admin_connection as admin_connection,
)
from .test_terminal_pitch_storage import (
    initial_scope_database as initial_scope_database,
)
from .test_terminal_pitch_storage import (
    product_node_binary as product_node_binary,
)
from .test_terminal_pitch_storage import (
    tested_role_connection as tested_role_connection,
)
from .test_terminal_pitch_storage import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db


def _script() -> str:
    """既HTTP開始・二球後に交代を送り、保存CPから次球を評価する。"""
    original = _v3_script()
    original = original.replace(
        "fixed_sql_error=safe_primary,\n",
        "fixed_sql_error=safe_primary,\n"
        "            function_line=(getattr(diagnostic, 'context', '') "
        "or '').splitlines()[-1][:180] if code == '42501' "
        "and getattr(diagnostic, 'context', None) else None,\n",
        1,
    )
    start = original.index("        current_lifecycle, _ = await read_full()")
    end = original.index("\n\ntry:\n", start)
    trace = r"""
from pitchlog.repositories import nonplay_prefix_read as actual_nonplay_read
from pitchlog.repositories import game_lifecycle as actual_lifecycle_read
_actual_nonplay_read = actual_nonplay_read.read_undo_prefix
_actual_display_scope = actual_lifecycle_read.lifecycle_display_scope

def _trace_read(name, operation):
    def traced(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except Exception as error:
            original = getattr(error, "orig", None)
            code = getattr(original, "sqlstate", None)
            diagnostic = getattr(original, "diag", None)
            context = getattr(diagnostic, "context", None)
            runtime_diagnostics.update(
                read_stage=name,
                read_error=type(error).__name__,
                read_sqlstate=code,
                read_primary=(getattr(diagnostic, "message_primary", None)
                    if code in {"42501", "42703", "42883", "42P01",
                                 "42804", "42702", "42601"}
                    else None),
                read_function_line=(
                    context.splitlines()[-1][:180]
                    if type(context) is str and " at RAISE" in context
                    else None),
                read_frames=[(f.name, f.lineno)
                    for f in traceback.extract_tb(error.__traceback__)],
            )
            raise
    return traced

actual_nonplay_read.read_undo_prefix = _trace_read(
    "undo", _actual_nonplay_read)
from contextlib import contextmanager

@contextmanager
def traced_display(*args, **kwargs):
    try:
        with _actual_display_scope(*args, **kwargs) as value:
            yield value
    except Exception as error:
        runtime_diagnostics["display_error"] = repr(error)[:1200]
        raise

actual_lifecycle_read.lifecycle_display_scope = traced_display
actual_lifecycle_read._read_lifecycle_display = _trace_read(
    "lifecycle_sql", actual_lifecycle_read._read_lifecycle_display)
from pitchlog.repositories import ordinary_prefix_read as actual_ordinary_read
actual_ordinary_read._read_nonplay_projection = _trace_read(
    "nonplay_projection", actual_ordinary_read._read_nonplay_projection)
actual_nonplay_read._read_active_page_bound = _trace_read(
    "active_page", actual_nonplay_read._read_active_page_bound)

from pitchlog.api.routers import started_games as actual_started_route
_actual_model_validate = (
    actual_started_route.StartedNonplayPrefixGameRead.model_validate_json
)

def traced_model_validate(*args, **kwargs):
    try:
        return _actual_model_validate(*args, **kwargs)
    except Exception as error:
        runtime_diagnostics["response_model_error"] = repr(error)[:1200]
        raise

actual_started_route.StartedNonplayPrefixGameRead.model_validate_json = (
    traced_model_validate
)

from pitchlog.sync import native_ledger_insert as actual_native_insert
from pitchlog.sync import substitution_execution as actual_substitution
_actual_fresh_substitution = actual_native_insert._fresh_substitution

def traced_fresh_substitution(minimum, writer, event, token, expected):
    try:
        return _actual_fresh_substitution(minimum, writer, event, token, expected)
    except Exception:
        state = actual_substitution._EXECUTIONS.get(minimum.key)
        if state is not None:
            source = state.source
            runtime_diagnostics["fresh_state"] = {
                "phase": state.phase,
                "same_event": state.event is event,
                "same_writer": state.writer is writer,
                "same_context": source.context is minimum.context,
                "same_runtime": state.runtime is minimum.runtime,
                "write_started": source.write_started,
                "same_payload": state.payload.to_wire() == event.v7,
                "same_event_id": (
                    state.payload.to_wire()["eventId"]
                    == state.after["checkpoint"]["content"]["d1Head"]["source"][
                        "eventId"
                    ]
                ),
            }
        raise

actual_native_insert._fresh_substitution = traced_fresh_substitution

from pitchlog.repositories import nonplay_prefix as actual_nonplay_sql
_actual_nonplay_run = actual_nonplay_sql._run

def traced_nonplay_run(*args, **kwargs):
    try:
        return _actual_nonplay_run(*args, **kwargs)
    except Exception as error:
        original = getattr(error, "orig", error)
        code = getattr(original, "sqlstate", None)
        diagnostic = getattr(original, "diag", None)
        context = getattr(diagnostic, "context", None)
        runtime_diagnostics["first_nonplay_sql"] = {
            "type": type(error).__name__,
            "sqlstate": code,
            "primary": (
                getattr(diagnostic, "message_primary", None)
                if code in {"42501", "42703", "42883", "42P01", "42804",
                             "42702", "42601", "23502", "23505", "23514", "P0001"}
                else None
            ),
            "function_line": (
                context.splitlines()[-1][:180]
                if type(context) is str and " at RAISE" in context
                else None
            ),
            "frames": [(f.name, f.lineno)
                for f in traceback.extract_tb(error.__traceback__)[:9]],
        }
        raise

actual_nonplay_sql._run = traced_nonplay_run
from pitchlog.sync import substitution_bridge as actual_substitution_bridge
actual_substitution_bridge._run = traced_nonplay_run

"""
    flow = r"""
        before, frames = await read_full()
        assert before["status"] == "in_progress"
        assert len(frames) == 2
        cp = before["checkpoint"]
        fields = cp["content"]["restored"]["current"]["stateFields"]
        incoming = "00000000-0000-0000-0000-0000000000d3"
        outgoing = "00000000-0000-0000-0000-0000000000c9"
        event = {
            "game_id": game,
            "d4": before["current_d4"],
            "d1": int(before["next_position"]["d1"]),
            "d2": int(before["next_position"]["d2"]),
            "d5": str(uuid4()),
            "event_kind": "substitution",
            "payload": {
                "formatVersion": "substitution-event-v1",
                "expectedCheckpoint": cp["ref"],
                "eventId": str(uuid4()),
                "operation": {
                    "kind": "pitcher",
                    "side": "home",
                    "outgoingId": outgoing,
                    "incomingId": incoming,
                    "count": {
                        "strikes": fields["state.count.strikes"],
                        "balls": fields["state.count.balls"],
                    },
                    "dh": "retain",
                },
                "incomingSnapshots": [
                    {"playerId": incoming, "uniformNumber": "11"}
                ],
            },
        }
        body = {
            "recording_right_proof": started["recording_right_proof"],
            "events": [event],
        }
        attempt = str(uuid4())
        posted = await send(body, attempt)
        assert posted.status_code == 200, (
            "substitution-http", posted.status_code, posted.text
        )
        assert posted.json()["eventResults"][0]["a5Result"] == "受理", (
            "substitution-ack", posted.json(), runtime_diagnostics
        )
        after, after_frames = await read_full()
        assert len(after_frames) == 2
        assert after["checkpoint"]["ref"]["revision"] == str(
            int(cp["ref"]["revision"]) + 1
        )
        assert len(after["checkpoint"]["content"]["substitutionFrames"]) == 1
        assert after["checkpoint"]["content"]["restored"]["participants"][
            "pitcherId"
        ] == incoming
        replay = await send(body, attempt)
        assert replay.status_code == 200
        assert replay.json()["eventResults"][0]["a5Result"] == "重複"
        pitched = await additional_play()
        assert pitched["checkpoint"]["content"]["restored"][
            "substitutionState"
        ]["home"]["fielding"]["1"] == incoming
        reload, reload_frames = await read_full()
        assert reload["checkpoint"] == pitched["checkpoint"]
        assert len(reload_frames) == 3
        return {
            "game": game,
            "substitution_d5": event["d5"],
            "substitution_event_id": event["payload"]["eventId"],
            "pitcher": incoming,
            "d3": reload["checkpoint"]["content"]["d3"],
        }
"""
    return (
        original[:start].replace("async def run():", trace + "async def run():", 1)
        + flow
        + original[end:]
    )


def test_new_game_substitution_saved_get_next_pitch_reload(vertical_database):
    """真正保存receiptとGET CP、次球の責任投手を確認する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT pg_catalog.to_regprocedure("
            "'sync_right_api.read_lifecycle_display(uuid, uuid)') IS NOT NULL"
        ).fetchone() == (True,), "fixture供給後の正式lifecycle表示関数が未配置"
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        home = admin.execute(
            "SELECT home_team_record_id FROM public.games WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert home is not None
        admin.execute(
            "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
            "uniform_number,roster_status_key) "
            "VALUES (%s,%s,%s,'交代試験選手','11','active')",
            (db.tenant_id, UUID(int=211), home[0]),
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
        _prepare_app_configuration(db)
        with psycopg.connect(db.authority.database.business_admin) as admin:
            assert admin.execute(
                "SELECT pg_catalog.to_regprocedure("
                "'sync_right_api.read_lifecycle_display(uuid, uuid)') IS NOT NULL"
            ).fetchone() == (True,), "broker準備後の正式lifecycle表示関数が未配置"
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _script()],
            capture_output=True,
            text=True,
            timeout=500,
        )
    assert process.returncode == 0, process.stderr[-1200:]
    result = json.loads(process.stdout)
    if "exception_type" in result or "exception" in result:
        print("SUBSTITUTION_DIAG", json.dumps(result, ensure_ascii=False))
        with psycopg.connect(db.authority.database.business_admin) as admin:
            catalog = admin.execute(
                "SELECT current_database(),"
                "to_regprocedure('sync_right_api.read_lifecycle_display("
                "uuid, uuid)')::text"
            ).fetchone()
            print("SUBSTITUTION_CATALOG", catalog)
    assert "exception_type" not in result, result
    assert "exception" not in result, result
    assert "game" in result, result
    with psycopg.connect(db.authority.database.business_admin) as admin:
        rows = admin.execute(
            "SELECT source_event_id FROM sync_fence.substitution_write_receipts "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, UUID(result["game"])),
        ).fetchall()
        assert rows == [(UUID(result["substitution_event_id"]),)]
    assert result["d3"] == "4"
