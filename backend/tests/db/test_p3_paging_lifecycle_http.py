"""真正v3通常26球からP3/再掲/次球を測る隔離HTTP driver生成候補。"""

from __future__ import annotations

# 旧作者の26球操作脚本だけを再利用し、後付candidate DDLは呼ばない。
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.db.current_product_startup import CURRENT_REVISION

from . import durable_rights_ledger_support as _ledger_support
from . import initial_recording_right_scope_support as _initial_support
from . import test_first_ball_vertical_http as _vertical_fixtures
from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_first_ball_vertical_http import (
    vertical_database as vertical_database,
)
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)
from .test_p3_candidate_compile_author import _three_ball_p3_script
from .test_terminal_pitch_storage import _lineup_script

pytestmark = pytest.mark.requires_db


def build_p3_26_script() -> str:
    """既create/start/実host/実POST脚本の有限改変だけを返す。"""
    script = _lineup_script()
    traced = _three_ball_p3_script()
    trace_start = traced.index("_actual_p3_apply = actual_sync_router._apply_e1_p3")
    trace_end = traced.index("async def run():", trace_start)
    trace = traced[trace_start:trace_end]
    paged_trace = """from pitchlog.sync import past_correction_execution
actual_p3_execution = past_correction_execution
_actual_p3_visit = actual_p3_execution.visit_p3_lineup_correction_pages
_actual_p3_content_result = actual_p3_execution.p3_content_result

def traced_p3_visit(*args, **kwargs):
    try:
        return _actual_p3_visit(*args, **kwargs)
    except Exception as error:
        chain = []
        current = error
        seen = set()
        while current is not None and len(chain) < 8 and id(current) not in seen:
            seen.add(id(current))
            chain.append({
                "exception_type": type(current).__name__,
                "frames": [(frame.name, frame.lineno)
                           for frame in traceback.extract_tb(current.__traceback__)],
            })
            current = current.__cause__ or current.__context__
        runtime_diagnostics["paged_preparation"] = {"chain": chain}
        raise

def traced_p3_content_result(*args, **kwargs):
    result = _actual_p3_content_result(*args, **kwargs)
    runtime_diagnostics["p3_content_result"] = result
    return result

actual_p3_execution.visit_p3_lineup_correction_pages = traced_p3_visit
actual_p3_execution.p3_content_result = traced_p3_content_result

from time import monotonic
from pitchlog.sync import past_correction_paged as _p3_paged
from pitchlog.sync.control_provider import binding_control as _p3_control
_p3_started = monotonic()
_p3_last_guard = None
_p3_unfinished = {}
_p3_lifecycle = {"opened": 0, "finished": 0, "abandoned": 0}
_p3_original_init = _p3_control._BindingLease.__init__
_p3_original_finish = _p3_control._BindingLease.finish
_p3_original_abandon = _p3_control._BindingLease.abandon
_p3_original_guard = _p3_paged._assert_page_binding

def _p3_init(self, *args, **kwargs):
    result = _p3_original_init(self, *args, **kwargs)
    _p3_unfinished[self] = monotonic()
    _p3_lifecycle["opened"] += 1
    return result

def _p3_finish(self):
    result = _p3_original_finish(self)
    _p3_unfinished.pop(self, None)
    _p3_lifecycle["finished"] += 1
    return result

def _p3_abandon(self):
    try:
        return _p3_original_abandon(self)
    finally:
        _p3_unfinished.pop(self, None)
        _p3_lifecycle["abandoned"] += 1

def _p3_guard(*args, **kwargs):
    global _p3_last_guard
    now = monotonic()
    marks = runtime_diagnostics.setdefault("page_binding_checks", [])
    record = {"elapsed_ms": round((now - _p3_started) * 1000),
              "gap_ms": (round((now - _p3_last_guard) * 1000)
                         if _p3_last_guard is not None else None),
              "unfinished": len(_p3_unfinished),
              "oldest_open_ms": (round((now - min(_p3_unfinished.values())) * 1000)
                                 if _p3_unfinished else None),
              "lifecycle": dict(_p3_lifecycle)}
    _p3_last_guard = now
    try:
        result = _p3_original_guard(*args, **kwargs)
    except Exception as error:
        record["error_type"] = type(error).__name__
        raise
    else:
        record["success"] = True
        return result
    finally:
        if len(marks) < 80:
            marks.append(record)
        else:
            runtime_diagnostics["page_binding_checks_truncated"] = True

_p3_control._BindingLease.__init__ = _p3_init
_p3_control._BindingLease.finish = _p3_finish
_p3_control._BindingLease.abandon = _p3_abandon
_p3_paged._assert_page_binding = _p3_guard

"""
    marker = "async def run():"
    assert script.count(marker) == 1
    script = script.replace(marker, trace + paged_trace + marker, 1)
    crash_start = script.index("            if index in (1, 9):")
    crash_end = script.index("            posted = await client.post(", crash_start)
    script = script[:crash_start] + script[crash_end:]
    old = (
        'results = [\n            "batting-result.called-pitch",\n'
        '            "batting-result.called-pitch",\n'
        '            "batting-result.called-strikeout",\n'
        '        ] * 3 + ["batting-result.ball"]'
    )
    assert script.count(old) == 1
    script = script.replace(
        old,
        'results = ["batting-result.called-pitch"] * 2 '
        '+ ["batting-result.foul"] * 23 '
        '+ ["batting-result.called-strikeout"]',
        1,
    )
    assert script.count('assert len(current["page"]["items"]) == index') == 1
    script = script.replace(
        'assert len(current["page"]["items"]) == index',
        'assert len(current["page"]["items"]) == min(index, 25)',
        1,
    )
    old_replay = """            replay = await client.post(
                "/games/" + game + "/sync/events", headers=h, json=payload
            )
            assert (
                replay.status_code == 200
                and replay.json()["eventResults"][0]["a5Result"] == "重複"
            )
"""
    assert script.count(old_replay) == 1
    script = script.replace(old_replay, "", 1)
    old_switch = """            if index == 9:
                sf = current["after"]["stateFields"]
                assert sf["state.half"] == "bottom" and sf["state.outs"] == "0"
                assert current["after"]["battingOrderBySide"] == {
                    "away": "4",
                    "home": "1",
                }
                assert (
                    current["participants"]["pitcherId"]
                    == current["lineup"]["away"]["pitcherId"]
                )
                assert (
                    current["participants"]["batterId"]
                    == current["lineup"]["home"]["battingOrder"]["1"]
                )
"""
    assert script.count(old_switch) == 1
    script = script.replace(old_switch, "", 1)
    assert script.count('assert pages == current["page"]["items"]') == 1
    script = script.replace(
        'assert pages == current["page"]["items"]',
        'assert len(pages) == 26 and pages[:25] == current["page"]["items"]',
        1,
    )
    old_return = """        return {
            "game": game,
            "prefix": current["prefix_ref"]["length"],
            "history": len(pages),
            "d5s": previous_d5,
            "after": current["after"]["stateFields"],
        }"""
    assert script.count(old_return) == 1
    loop_start = script.index("        for index, result in enumerate(results, 1):")
    loop_end = script.index("        reload = await client.get(", loop_start)
    next_pitch = script[loop_start:loop_end].replace(
        "for index, result in enumerate(results, 1):",
        'for index, result in enumerate(["batting-result.ball"], 27):',
        1,
    )
    assert (
        next_pitch.count('assert len(current["page"]["items"]) == min(index, 25)') == 1
    )
    next_pitch = next_pitch.replace(
        'assert len(current["page"]["items"]) == min(index, 25)',
        'assert len(current["page"]["items"]) == 25',
        1,
    )
    p3 = """        target_d1 = 26
        target = pages[25]["play_row"]
        runtime_diagnostics.update(stage="26-target", status=None)
        target_read = await client.get(
            "/games/" + game + "/sync/change-target/26", headers=headers())
        runtime_diagnostics["status"] = target_read.status_code
        assert target_read.status_code == 200, (
            "26-target", target_read.status_code)
        offer = target_read.json()
        assert offer["target_reference"] == {
            "game": game, "d4": started["d4"], "d1": 26}
        assert offer["expected_version"] == 1
        assert offer["expected_prefix_ref"] == current["prefix_ref"]
        assert offer["target_event_id"] == target["source_event_id"]
        assert offer["target_play_id"] == target["id"]
        assert offer["original_result_id"] == "batting-result.called-strikeout"
        change = {
            "d5": str(uuid4()), "game_id": game, "event_kind": "play_change",
            "target_reference": offer["target_reference"],
            "expected_version": offer["expected_version"],
            "payload": {
                "formatVersion": "p3-lineup-pitch-change-v1",
                "expectedPrefixRef": current["prefix_ref"],
                "targetEventId": target["source_event_id"],
                "targetPlayId": target["id"],
                "originalResultId": "batting-result.called-strikeout",
                "replacementResultId": "batting-result.ball",
                "replacementObservations": {
                    "pitchTypeKey": case["pitch_type"],
                    "course": {"unit": "1/263", "x": "100", "y": "150"},
                    "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                    "stance": None, "battingSide": None,
                },
            },
        }
        p3_payload = {
            "recovery_generation": current["recovery_generation"],
            "recording_right_proof": started["recording_right_proof"],
            "change": change,
        }
        class PlannedPageRollback(Exception):
            pass
        for crash in ("after_t2_event", "after_t4_projection"):
            reached = []
            def fail(point):
                if point == crash:
                    reached.append(point)
                    raise PlannedPageRollback()
            runtime_diagnostics.update(stage="26-fault-" + crash, status=None)
            failed = None
            try:
                with testing_crash_hook(fail):
                    failed = await client.post(
                        "/games/" + game + "/sync/change",
                        headers=device_headers(pair, str(uuid4())), json=p3_payload)
            except PlannedPageRollback:
                pass
            runtime_diagnostics["fault_reached_count"] = len(reached)
            runtime_diagnostics["fault_response_status"] = (
                failed.status_code if failed is not None else None)
            assert reached == [crash], ("26-fault", crash)
            if failed is not None:
                assert failed.status_code in (500, 503), (
                    "26-fault-status", crash, failed.status_code)
            rolled = await client.get(
                "/games/" + game + "/started?projection=play-prefix-v3&limit=100",
                headers=headers())
            assert rolled.status_code == 200 and rolled.json() == current, (
                "26-fault-rollback", crash, rolled.status_code)
        runtime_diagnostics.update(stage="26-post", status=None)
        changed = await client.post(
            "/games/" + game + "/sync/change",
            headers=device_headers(pair, str(uuid4())), json=p3_payload)
        runtime_diagnostics["status"] = changed.status_code
        assert changed.status_code == 200, ("26-change", changed.status_code)
        runtime_diagnostics.update(stage="26-get-first", status=None)
        first = await client.get(
            "/games/" + game + "/started?projection=play-prefix-v3&limit=100",
            headers=headers())
        runtime_diagnostics["status"] = first.status_code
        assert first.status_code == 200, ("26-first", first.status_code)
        corrected_current = first.json()
        assert len(corrected_current["page"]["items"]) == 25
        cursor = corrected_current["page"]["next_cursor"]
        assert type(cursor) is str and cursor
        runtime_diagnostics.update(stage="26-get-second", status=None)
        second = await client.get(
            "/games/" + game + "/started", headers=headers(),
            params={"projection":"play-prefix-v3", "limit":25, "cursor":cursor})
        runtime_diagnostics["status"] = second.status_code
        assert second.status_code == 200, ("26-second", second.status_code)
        second_page = second.json()
        assert len(second_page["page"]["items"]) == 1
        assert second_page["page"]["next_cursor"] is None
        effective = second_page["page"]["items"][0]["play_row"]
        assert effective["id"] != target["id"]
        assert effective["source_event_id"] != target["source_event_id"]
        assert effective["batting_result_key"] == "batting-result.ball"
        assert second_page["prefix_ref"] == corrected_current["prefix_ref"]
        assert second_page["after"] == corrected_current["after"]
        runtime_diagnostics.update(stage="26-confirmation", status=None)
        confirmation = await client.get(
            "/games/" + game + "/sync/change-confirmation/26",
            headers=headers())
        runtime_diagnostics["status"] = confirmation.status_code
        assert confirmation.status_code == 200, (
            "26-confirmation", confirmation.status_code)
        confirmed = confirmation.json()
        assert confirmed["target_reference"] == offer["target_reference"]
        assert confirmed["confirmed_version"] == 2
        assert confirmed["d5"] == change["d5"]
        assert confirmed["source_event_id"] == effective["source_event_id"]
        assert confirmed["target_play_id"] == effective["id"]
        assert confirmed["current_prefix_ref"] == corrected_current["prefix_ref"]
        assert confirmed["current_after"] == corrected_current["after"]
        runtime_diagnostics.update(stage="26-replay", status=None)
        replayed = await client.post(
            "/games/" + game + "/sync/change",
            headers=device_headers(pair, str(uuid4())), json=p3_payload)
        runtime_diagnostics["status"] = replayed.status_code
        assert replayed.status_code == 200 and replayed.json() == changed.json(), (
            "26-replay", replayed.status_code)
        current = corrected_current
__NEXT_PITCH__
        runtime_diagnostics.update(stage="27-get-second", status=None)
        cursor = current["page"]["next_cursor"]
        assert type(cursor) is str and cursor
        final_page = await client.get(
            "/games/" + game + "/started", headers=headers(),
            params={"projection":"play-prefix-v3", "limit":25, "cursor":cursor})
        runtime_diagnostics["status"] = final_page.status_code
        assert final_page.status_code == 200, (
            "27-second", final_page.status_code)
        latest = final_page.json()
        assert len(latest["page"]["items"]) == 2
        assert latest["page"]["next_cursor"] is None
        assert latest["page"]["items"][0]["play_row"] == effective
        assert latest["prefix_ref"] == current["prefix_ref"]
        runtime_diagnostics.update(stage="complete", status=200)
        return {
            "game": game,
            "prefix": current["prefix_ref"]["length"],
            "p3_d5": change["d5"],
            "old_play_id": target["id"],
            "effective_play_id": effective["id"],
            "last_play_id": latest["page"]["items"][1]["play_row"]["id"],
            "source_origin": {
                "sync_router": actual_sync_router.__file__,
                "read_router": actual_started_router.__file__,
            },
        }"""
    assert p3.count("__NEXT_PITCH__") == 1
    p3 = p3.replace("__NEXT_PITCH__", next_pitch.rstrip(), 1)
    script = script.replace(old_return, p3, 1)
    # 通常v3 readerはlimit=100の26件を返し、P3完成版だけ25件窓へ入る。
    assert script.count('assert len(current["page"]["items"]) == min(index, 25)') == 1
    script = script.replace(
        'assert len(current["page"]["items"]) == min(index, 25)',
        'assert len(current["page"]["items"]) == index',
        1,
    )
    assert (
        script.count(
            'assert len(pages) == 26 and pages[:25] == current["page"]["items"]'
        )
        == 1
    )
    script = script.replace(
        'assert len(pages) == 26 and pages[:25] == current["page"]["items"]',
        'assert len(pages) == 26 and pages == current["page"]["items"]',
        1,
    )
    initial_loop = "for index, result in enumerate(results, 1):\n"
    final_loop = 'for index, result in enumerate(["batting-result.ball"], 27):\n'
    assert script.count(initial_loop) == script.count(final_loop) == 1
    script = script.replace(
        initial_loop,
        initial_loop
        + '            runtime_diagnostics.update(stage="ordinary-" + str(index), '
        "status=None)\n",
        1,
    ).replace(
        final_loop,
        final_loop
        + '            runtime_diagnostics.update(stage="ordinary-27", status=None)\n',
        1,
    )
    compile(script, "<p3-26-generated-http>", "exec")
    return script


_CONTROLLER_ENTRY_SHA256 = (
    "52328acbdf7525f5ca1fb69d62cf5cb8510429ea7eb13634873fe4f999998b94"
)
_CONTROLLER_FAILURE_OBSERVER = """import sys as _diag_sys
import time as _diag_time
import json as _diag_json
import threading as _diag_threading
from pitchlog.recording_rights import rg1_lifecycle as _diag_rg1
_diag_original_unavailable=_diag_rg1._unavailable
_diag_original_set=_diag_threading.Event.set
_diag_started=_diag_time.monotonic()
_diag_lock=_diag_threading.Lock()
_diag_count=0
_diag_truncated=False
_diag_functions=frozenset({'assert_live','assert_borrower_backend',
                           'control','session','serve_fresh_controller'})
def _diag_emit(frame, *, stopped=False, error=None):
    global _diag_count,_diag_truncated
    function=frame.f_code.co_name
    if (frame.f_code.co_filename!=_diag_rg1.__file__
        or function not in _diag_functions):
        return
    record={'function':function,'line':frame.f_lineno,
            'elapsed_ms':max(0,round(
                (_diag_time.monotonic()-_diag_started)*1000))}
    if stopped:
        record['stop']=True
        record['exception']=None
        if error is not None:
            module=type(error).__module__
            name=type(error).__name__
            allowed=(module=='builtins' or module.startswith(
                ('pitchlog.','psycopg.','sqlalchemy.')))
            record['exception']={'module':module if allowed else 'unknown',
                                 'class':name if allowed else 'unknown'}
    with _diag_lock:
        if _diag_count<80:
            _diag_count+=1
            print('PITCHLOG_P3_CONTROLLER_FAILURE '+
                  _diag_json.dumps(record),flush=True)
        elif not _diag_truncated:
            _diag_truncated=True
            print('PITCHLOG_P3_CONTROLLER_FAILURE '+_diag_json.dumps(
                {'truncated':True,'limit':80}),flush=True)
def _diag_unavailable():
    result=_diag_original_unavailable()
    frame=None
    try:
        frame=_diag_sys._getframe(1)
        _diag_emit(frame)
    except BaseException:
        pass
    finally:
        del frame
    return result
def _diag_event_set(self):
    frame=None
    try:
        frame=_diag_sys._getframe(1)
        if frame.f_code.co_name in ('session','serve_fresh_controller'):
            _diag_emit(frame,stopped=True,error=_diag_sys.exception())
    except BaseException:
        pass
    finally:
        del frame
    return _diag_original_set(self)
_diag_rg1._unavailable=_diag_unavailable
_diag_threading.Event.set=_diag_event_set
print('PITCHLOG_P3_CONTROLLER_OBSERVER '+_diag_json.dumps(
    {'mode':'factory-and-stop','limit':80}),flush=True)
"""


@pytest.fixture(autouse=True)
def controller_failure_observer(monkeypatch, tmp_path):
    """元fixtureを書き換えず、当owned controller脚本だけに一回注入する。"""
    mode = os.environ.get("PITCHLOG_E2E_P3_CONTROLLER_DIAGNOSTIC")
    if mode is None:
        yield
        return
    assert mode == "1", "未知のcontroller診断モード"
    original = _initial_support.docker
    injected = []
    controller = []

    def observed_docker(*args, **kwargs):
        if (
            len(args) >= 3
            and args[-2] == "-c"
            and type(args[-1]) is str
            and hashlib.sha256(args[-1].encode()).hexdigest()
            == _CONTROLLER_ENTRY_SHA256
        ):
            assert not injected, "controller診断を二重注入しない"
            injected.append(True)
            controller.append(args[args.index("--name") + 1])
            args = (*args[:-1], _CONTROLLER_FAILURE_OBSERVER + args[-1])
        result = original(*args, **kwargs)
        if (
            controller
            and len(args) == 4
            and args[:3] == ("inspect", "--format", "{{.State.Running}}")
            and args[3] == controller[0]
            and result == "false"
        ):
            _capture_controller_startup(
                controller[0], tmp_path / "controller-startup-failure-safe.json"
            )
        return result

    monkeypatch.setattr(_initial_support, "docker", observed_docker)
    yield
    assert injected == [True], "元controller脚本への一回注入が未成立"


_AUTHORITY_MONITOR_SHA256 = (
    "e2f855a428b9266b39840ad8a10c6759f8e3fe41773c90178677e21d3ebec1c4"
)
_AUTHORITY_OPERATIONS = frozenset(
    {
        "unknown",
        "epoch",
        "reserve",
        "claim",
        "fence_open",
        "fresh_activation_open",
        "fence_check",
        "fence_close",
        "binding_open",
        "binding_check",
        "binding_close",
        "binding_recover",
    }
)


@pytest.fixture
def authority_failure_observer(monkeypatch):
    """既root起動引数だけへreadonly siteを一回供給し、workerへ継承させる。"""
    mode = os.environ.get("PITCHLOG_E2E_P3_AUTHORITY_MONITOR")
    if mode is None:
        yield
        return
    assert mode == "1", "未知のauthority診断モード"
    assert "PITCHLOG_E2E_RUNNER_AUTHORITY_DIAGNOSTIC_SITE" not in os.environ
    site = (
        Path.home()
        / ".cache/pitchlog/p3-authority-local-monitor-20261108/site/sitecustomize.py"
    )
    assert site.is_file() and not site.is_symlink()
    assert hashlib.sha256(site.read_bytes()).hexdigest() == _AUTHORITY_MONITOR_SHA256
    original = _ledger_support.docker
    injected = []

    def observed_docker(*args, **kwargs):
        if args[-5:] == (
            "-m",
            "pitchlog.durable_rights_ledger.authority",
            "serve",
            "--config",
            "/control/settings/config.json",
        ):
            assert not injected, "authority観測の二重注入"
            values = list(args)
            position = values.index("postgres:17.11-bookworm")
            values[position:position] = [
                "--mount",
                f"type=bind,src={site.parent},dst=/diag,readonly",
            ]
            values[values.index("PYTHONPATH=/code:/deps")] = (
                "PYTHONPATH=/diag:/code:/deps"
            )
            args = tuple(values)
            injected.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(_ledger_support, "docker", observed_docker)
    yield
    assert injected == [True], "authority実workerへの供給が未成立"
    assert hashlib.sha256(site.read_bytes()).hexdigest() == _AUTHORITY_MONITOR_SHA256


def _capture_authority_failures(db, target) -> None:
    """実workerの閉probe/例外列だけをcleanup前に保存する。"""
    process = subprocess.run(
        ["docker", "logs", db.authority.service],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert process.returncode == 0, "authority診断logを取得できない"
    ready = 0
    records = []
    functions = {
        "_receive",
        "assert_held",
        "_handle_binding",
        "_handle_binding_recovery",
        "_start_lease",
        "_close_lease",
        "_start_binding_lease",
        "_live_matches",
        "handle",
        "_send_error",
    }
    keys = {
        "function",
        "role",
        "last_operation",
        "receiving",
        "blocked_before",
        "blocked_after",
        "elapsed_ms",
        "chain",
    }
    for line in process.stdout.splitlines():
        if line.startswith("PITCHLOG_P3_AUTHORITY_OBSERVER "):
            assert json.loads(line.split(" ", 1)[1]) == {
                "mode": "failure-only",
                "probe": True,
                "limit": 80,
            }
            ready += 1
        if not line.startswith("PITCHLOG_P3_AUTHORITY_FAILURE "):
            continue
        row = json.loads(line.split(" ", 1)[1])
        if row == {"truncated": True, "limit": 80}:
            records.append(row)
            continue
        assert type(row) is dict and set(row) in (keys, keys | {"response"})
        assert row["function"] in functions
        assert row["role"] in {
            "unknown",
            "generation",
            "fresh_controller",
            "sync_binding",
        }
        assert row["last_operation"] in _AUTHORITY_OPERATIONS
        assert type(row["receiving"]) is bool
        for name in ("blocked_before", "blocked_after"):
            assert row[name] is None or type(row[name]) is bool
        assert type(row["elapsed_ms"]) is int and 0 <= row["elapsed_ms"] < 3600000
        if "response" in row:
            assert row["response"] in {"unconfirmed", "unavailable"}
        assert type(row["chain"]) is list and len(row["chain"]) <= 8
        for error in row["chain"]:
            assert type(error) is dict and set(error) == {
                "module",
                "class",
                "source_frames",
            }
            assert all(
                type(error[k]) is str
                and len(error[k]) <= 200
                and all(part.isidentifier() for part in error[k].split("."))
                for k in ("module", "class")
            )
            assert (
                type(error["source_frames"]) is list
                and len(error["source_frames"]) <= 3
            )
            for frame in error["source_frames"]:
                assert type(frame) is dict and set(frame) == {"function", "line"}
                assert (
                    type(frame["function"]) is str and frame["function"].isidentifier()
                )
                assert type(frame["line"]) is int and 0 < frame["line"] < 10000
        records.append(row)
    assert ready == 1 and len(records) <= 81, "authority実worker観測が未成立"
    target.write_text(json.dumps({"ready": ready, "failures": records}, indent=2))


@pytest.fixture
def initial_scope_database(
    monkeypatch, controller_failure_observer, authority_failure_observer
):
    """identity-autouseより先に診断を束縛し、元owned fixtureをそのまま使う。"""
    yield from cast(Any, _vertical_fixtures.initial_scope_database).__wrapped__(
        monkeypatch
    )


def _capture_controller_startup(controller, target) -> None:
    """起動失敗時だけ既stdoutの閉marker/許可例外classを回収する。"""
    try:
        process = subprocess.run(
            ["docker", "logs", controller],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        classes = []
        records = []
        allowed = {
            "SyntaxError",
            "NameError",
            "TypeError",
            "AttributeError",
            "RuntimeError",
            "RG1ControlUnavailable",
            "LedgerUnavailable",
            "LedgerOutcomeUnconfirmed",
            "OperationalError",
            "ProgrammingError",
            "PermissionError",
            "ModuleNotFoundError",
            "ImportError",
            "ValueError",
            "KeyError",
            "AssertionError",
            "OSError",
        }
        for line in (process.stdout + "\n" + process.stderr).splitlines():
            name = line.split(":", 1)[0]
            if name in allowed and name not in classes:
                classes.append(name)
            if line.startswith("PITCHLOG_P3_CONTROLLER_FAILURE "):
                row = json.loads(line.split(" ", 1)[1])
                if type(row) is dict and set(row) == {"truncated", "limit"}:
                    if row == {"truncated": True, "limit": 80}:
                        records.append(row)
                elif type(row) is dict and set(row) in (
                    {"function", "line", "elapsed_ms"},
                    {"function", "line", "elapsed_ms", "stop", "exception"},
                ):
                    if row["function"] not in {
                        "assert_live",
                        "assert_borrower_backend",
                        "control",
                        "session",
                        "serve_fresh_controller",
                    }:
                        continue
                    if not (
                        type(row["line"]) is int
                        and 0 < row["line"] < 10000
                        and type(row["elapsed_ms"]) is int
                        and 0 <= row["elapsed_ms"] < 3600000
                    ):
                        continue
                    if "stop" in row:
                        error = row["exception"]
                        if row["stop"] is not True:
                            continue
                        if error is not None and not (
                            type(error) is dict
                            and set(error) == {"module", "class"}
                            and all(
                                type(v) is str
                                and len(v) <= 200
                                and all(part.isidentifier() for part in v.split("."))
                                for v in error.values()
                            )
                        ):
                            continue
                    if len(records) < 81:
                        records.append(row)
        target.write_text(
            json.dumps(
                {"startup_classes": classes[:8], "records": records[:81]}, indent=2
            )
        )
    except BaseException:
        # 診断で元fixtureのRunning=falseや起動例外を置換しない。
        return


def _capture_controller_failures(db, target) -> None:
    """controller自身の閉markerだけを保存し、生logを出力しない。"""
    process = subprocess.run(
        ["docker", "logs", db.controller],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert process.returncode == 0, "controller診断logを取得できない"
    ready = 0
    records = []
    allowed = {
        "assert_live",
        "assert_borrower_backend",
        "control",
        "session",
        "serve_fresh_controller",
    }
    for line in process.stdout.splitlines():
        if line.startswith("PITCHLOG_P3_CONTROLLER_OBSERVER "):
            assert json.loads(line.split(" ", 1)[1]) == {
                "mode": "factory-and-stop",
                "limit": 80,
            }
            ready += 1
        if line.startswith("PITCHLOG_P3_CONTROLLER_FAILURE "):
            row = json.loads(line.split(" ", 1)[1])
            if row == {"truncated": True, "limit": 80}:
                records.append(row)
                continue
            assert type(row) is dict
            if "stop" in row:
                assert set(row) == {
                    "function",
                    "line",
                    "elapsed_ms",
                    "stop",
                    "exception",
                }
                assert row["stop"] is True
                error = row["exception"]
                assert error is None or (
                    type(error) is dict
                    and set(error) == {"module", "class"}
                    and all(type(v) is str and len(v) <= 200 for v in error.values())
                )
            else:
                assert set(row) == {"function", "line", "elapsed_ms"}
            assert row["function"] in allowed
            assert type(row["line"]) is int and 0 < row["line"] < 10000
            assert type(row["elapsed_ms"]) is int and 0 <= row["elapsed_ms"] < 3600000
            records.append(row)
    assert ready == 1 and len(records) <= 81, "controller実observerが未成立"
    target.write_text(json.dumps({"ready": ready, "failures": records}, indent=2))


def test_actual_p3_26_lifecycle_http(vertical_database, tmp_path) -> None:
    """正常current配置で26球変更・故障全取消・再掲・次球を実HTTPへ通す。"""
    db = vertical_database
    if os.environ.get("PITCHLOG_E2E_P3_CONTROLLER_DIAGNOSTIC") == "1":
        _capture_controller_failures(db, tmp_path / "controller-ready-safe.json")
    if os.environ.get("PITCHLOG_E2E_P3_AUTHORITY_MONITOR") == "1":
        _capture_authority_failures(db, tmp_path / "authority-ready-safe.json")
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchall() == [(CURRENT_REVISION,)]
        for key, label in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "見逃し三振"),
            ("batting-result.foul", "ファウル"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, label),
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
    script = build_p3_26_script()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        try:
            process = subprocess.run(
                ["docker", *_app_arguments(db, case), "-u", "-c", script],
                capture_output=True,
                text=True,
                timeout=900,
            )
        finally:
            if os.environ.get("PITCHLOG_E2E_P3_CONTROLLER_DIAGNOSTIC") == "1":
                _capture_controller_failures(db, tmp_path / "controller-safe.json")
            if os.environ.get("PITCHLOG_E2E_P3_AUTHORITY_MONITOR") == "1":
                _capture_authority_failures(db, tmp_path / "authority-safe.json")
    # stdoutは実HTTP成果JSONだけ。raw stderr/SQL/資格は失敗表示へ載せない。
    assert process.returncode == 0, "owned HTTP脚本が非成功終了"
    result = json.loads(process.stdout)
    (tmp_path / "p3-26-result.json").write_text(json.dumps(result, indent=2))
    assert "exception" not in result, result.get("runtime_diagnostics", {}).get("stage")
    assert result["prefix"] == "27"
    assert UUID(result["game"]) != db.game_id
    assert result["old_play_id"] != result["effective_play_id"]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute("SET TRANSACTION READ ONLY")
        key = (db.tenant_id, UUID(result["game"]))
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (1,)
        assert admin.execute(
            "SELECT source_count FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND is_current "
            "AND invalidated_at IS NULL",
            key,
        ).fetchall() == [(27,)]
        assert admin.execute(
            "SELECT count(*) FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (28,)
        assert admin.execute(
            "SELECT count(*) FROM public.idempotency_ledger "
            "WHERE tenant_id=%s AND d5=%s",
            (db.tenant_id, UUID(result["p3_d5"])),
        ).fetchone() == (1,)
