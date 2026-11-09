"""真正v3通常26球からP3/再掲/次球を測る隔離HTTP driver生成候補。"""

from __future__ import annotations

# 旧作者の26球操作脚本だけを再利用し、後付candidate DDLは呼ばない。
import json
import subprocess
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.db.current_product_startup import CURRENT_REVISION

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import (
    vertical_database as vertical_database,
)
from .test_game_lifecycle_http import _SCRIPT as _LIFECYCLE_SCRIPT
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


def build_p3_26_script(*, stop_after_p3: bool = False) -> str:
    """既create/start/実host/実POST脚本の有限改変だけを返す。"""
    script = _lineup_script()
    traced = _three_ball_p3_script()
    traced = traced.replace(
        "except BaseException as error:\n",
        "except BaseException as error:\n"
        "    runtime_diagnostics['failed_at']=__import__('datetime').datetime.now("
        "__import__('datetime').timezone.utc).isoformat()\n",
        1,
    )
    trace_start = traced.index("_actual_p3_apply = actual_sync_router._apply_e1_p3")
    trace_end = traced.index("async def run():", trace_start)
    trace = traced[trace_start:trace_end]
    trace = (
        "from pitchlog.repositories import nonplay_prefix_read as _lc_read\n"
        "_lc_actual = _lc_read.read_undo_prefix\n"
        "def _lc_traced(*args, **kwargs):\n"
        "    try:\n"
        "        return _lc_actual(*args, **kwargs)\n"
        "    except BaseException as error:\n"
        "        chain=[]; seen=set(); cur=error\n"
        "        while cur is not None and len(chain)<8 and id(cur) not in seen:\n"
        "            seen.add(id(cur))\n"
        "            chain.append(type(cur).__name__ + ':' + str(cur)[:120])\n"
        "            cur=cur.__cause__ or cur.__context__\n"
        "        runtime_diagnostics['lifecycle_read_error']=chain\n"
        "        raise\n"
        "_lc_read.read_undo_prefix=_lc_traced\n"
        + trace
    )
    paged_trace = """from pitchlog.sync import past_correction_execution
actual_p3_execution = past_correction_execution
_actual_p3_visit = actual_p3_execution.visit_p3_lineup_correction_pages
_actual_p3_content_result = actual_p3_execution.p3_content_result

from pitchlog.exports import p3_coverage as _p3_coverage
_p3_actual_coverage_need = _p3_coverage._need

def _p3_coverage_need(ok):
    if not ok:
        import inspect
        runtime_diagnostics["coverage_fail_line"] = (
            inspect.currentframe().f_back.f_lineno)
    return _p3_actual_coverage_need(ok)

_p3_coverage._need = _p3_coverage_need

from pitchlog.api.routers import game_exports as _p3_exports
_p3_actual_read_export = _p3_exports.read_play_export
_p3_actual_build_tables = _p3_exports.build_play_export_tables
_p3_actual_prepare_archive = _p3_exports.prepare_play_archive

def _p3_trace_export(name, original):
    def traced(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except BaseException as error:
            runtime_diagnostics["export_error"] = {
                "stage": name, "type": type(error).__name__,
                "message": str(error)[:160]}
            raise
    return traced

_p3_exports.read_play_export = _p3_trace_export("read", _p3_actual_read_export)
_p3_exports.build_play_export_tables = _p3_trace_export(
    "tables", _p3_actual_build_tables)
_p3_exports.prepare_play_archive = _p3_trace_export(
    "archive", _p3_actual_prepare_archive)

from pitchlog.api.routers import sync as _p3_sync_router
_actual_recover_attempt = _p3_sync_router.recover_sync_attempt

def traced_recover_attempt(*args, **kwargs):
    try:
        result = _actual_recover_attempt(*args, **kwargs)
    except BaseException as error:
        runtime_diagnostics["recover_exception"] = type(error).__name__
        raise
    runtime_diagnostics["recover_result"] = result
    return result

_p3_sync_router.recover_sync_attempt = traced_recover_attempt

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

from datetime import datetime as _p3_datetime, timezone as _p3_timezone
from time import monotonic
from pitchlog.sync import past_correction_paged as _p3_paged
from pitchlog.sync.control_provider import binding_control as _p3_control
from pitchlog.sync.control_provider import writer_binding as _p3_writer
_p3_started = monotonic()
_p3_last_guard = None
_p3_unfinished = {}
_p3_binding_meta = {}
_p3_lifecycle = {"opened": 0, "finished": 0, "abandoned": 0}
_p3_original_init = _p3_control._BindingLease.__init__
_p3_original_finish = _p3_control._BindingLease.finish
_p3_original_abandon = _p3_control._BindingLease.abandon
_p3_original_guard = _p3_paged._assert_page_binding

def _p3_init(self, *args, **kwargs):
    result = _p3_original_init(self, *args, **kwargs)
    now = monotonic()
    _p3_unfinished[self] = now
    _p3_binding_meta[self] = {
        "opened": now,
        "opened_at": _p3_datetime.now(_p3_timezone.utc).isoformat(),
        "authority_expires_at": self._expires.isoformat(),
    }
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
        if len(marks) < 200:
            marks.append(record)
        else:
            runtime_diagnostics["page_binding_checks_truncated"] = True

_p3_original_check = _p3_control._BindingLease.check
_p3_original_assert_current = _p3_writer._LiveWriterBinding.assert_current

def _p3_check(self):
    info = _p3_binding_meta.get(self)
    started = monotonic()
    try:
        result = _p3_original_check(self)
    except BaseException as error:
        runtime_diagnostics.setdefault("authority_check_failures", []).append({
            "at": _p3_datetime.now(_p3_timezone.utc).isoformat(),
            "elapsed_ms": round((monotonic() - started) * 1000),
            "binding_age_ms": (
                round((started - info["opened"]) * 1000) if info else None),
            "authority_expires_at": (
                info["authority_expires_at"] if info else None),
            "error_type": type(error).__name__,
        })
        raise
    if info is not None:
        info["authority_expires_at"] = self._expires.isoformat()
    return result

def _p3_assert_current(self):
    info = _p3_binding_meta.get(self._lease)
    started = monotonic()
    record = {
        "at": _p3_datetime.now(_p3_timezone.utc).isoformat(),
        "binding_age_ms": (
            round((started - info["opened"]) * 1000) if info else None),
        "authority_expires_at": (
            info["authority_expires_at"] if info else None),
    }
    try:
        result = _p3_original_assert_current(self)
    except BaseException as error:
        record["elapsed_ms"] = round((monotonic() - started) * 1000)
        record["error_type"] = type(error).__name__
        record["failed_at"] = _p3_datetime.now(_p3_timezone.utc).isoformat()
        marks = runtime_diagnostics.setdefault("precommit_checks", [])
        if len(marks) < 200:
            marks.append(record)
        runtime_diagnostics["precommit_failed_at"] = record["failed_at"]
        runtime_diagnostics["precommit_failure"] = record
        raise
    record["elapsed_ms"] = round((monotonic() - started) * 1000)
    record["success"] = True
    marks = runtime_diagnostics.setdefault("precommit_checks", [])
    if len(marks) < 200:
        marks.append(record)
    else:
        runtime_diagnostics["precommit_checks_truncated"] = True
    return result

_p3_control._BindingLease.__init__ = _p3_init
_p3_control._BindingLease.check = _p3_check
_p3_control._BindingLease.finish = _p3_finish
_p3_control._BindingLease.abandon = _p3_abandon
_p3_writer._LiveWriterBinding.assert_current = _p3_assert_current
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
        def fresh_p3(payload):
            value = json.loads(json.dumps(payload))
            value["change"]["d5"] = str(uuid4())
            return value
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
                        headers=device_headers(pair, str(uuid4())),
                        json=fresh_p3(p3_payload))
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
        ack = changed.json()
        assert set(ack) == {
            "boundary", "target_reference", "expected_version", "d5",
            "confirmed_content", "accepted_at"}, sorted(ack)
        assert ack["boundary"] == "変更受理"
        assert ack["target_reference"] == {
            "試合": game, "対象の D4": started["d4"],
            "対象の D1": target_d1}
        assert ack["expected_version"] == offer["expected_version"]
        assert ack["d5"] == change["d5"]
        assert ack["confirmed_content"] == change["payload"]
        assert type(ack["accepted_at"]) is str and ack["accepted_at"]
        runtime_diagnostics["ack"] = {
            "boundary": ack["boundary"], "d5": ack["d5"]}
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
        lifecycle_p3 = await client.get(
            "/games/" + game + "/started?projection=lifecycle-prefix-v1&limit=25",
            headers=headers())
        runtime_diagnostics["lifecycle_after_p3"] = lifecycle_p3.status_code
        if lifecycle_p3.status_code != 200:
            runtime_diagnostics["lifecycle_after_p3_body"] = lifecycle_p3.text[:400]
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
        lifecycle_27 = await client.get(
            "/games/" + game + "/started?projection=lifecycle-prefix-v1&limit=25",
            headers=headers())
        runtime_diagnostics["lifecycle_after_27"] = lifecycle_27.status_code
        if lifecycle_27.status_code != 200:
            runtime_diagnostics["lifecycle_after_27_body"] = lifecycle_27.text[:400]
        runtime_diagnostics.update(stage="complete", status=200)
        return {
            "game": game,
            "prefix": current["prefix_ref"]["length"],
            "p3_d5": change["d5"],
            "ack_accepted_at": ack["accepted_at"],
            "old_play_id": target["id"],
            "effective_play_id": effective["id"],
            "effective_event_id": effective["source_event_id"],
            "stats_version_id": confirmed["stats_version_id"],
            "last_play_id": latest["page"]["items"][1]["play_row"]["id"],
            "runtime_diagnostics": runtime_diagnostics,
            "source_origin": {
                "sync_router": actual_sync_router.__file__,
                "read_router": actual_started_router.__file__,
            },
        }"""
    assert p3.count("__NEXT_PITCH__") == 1
    old_post = """            posted = await client.post(
                "/games/" + game + "/sync/events", headers=h, json=payload
            )
            assert posted.status_code == 200, (
                "v3-save",
                index,
                posted.status_code,
                runtime_diagnostics,
            )
"""
    new_post = """            posted = await client.post(
                "/games/" + game + "/sync/events", headers=h, json=payload
            )
            assert posted.status_code == 200, (
                "v3-save",
                index,
                posted.status_code,
                runtime_diagnostics,
            )
"""
    assert next_pitch.count(old_post) == 1
    next_pitch = next_pitch.replace(old_post, new_post, 1)
    if stop_after_p3:
        cut = p3.index("__NEXT_PITCH__")
        p3 = p3[:cut] + """
        exported = await client.get(
            "/games/" + game + "/exports/plays.zip", headers=headers())
        assert exported.status_code == 200, ("p3-zip", exported.status_code)
        import csv
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            name = next(
                n for n in archive.namelist() if n.endswith("plays.csv"))
            text = archive.read(name).decode("utf-8-sig")
        csv_rows = list(csv.DictReader(io.StringIO(text)))
        target_csv = next(
            row for row in csv_rows
            if row["入力項目"]
            and json.loads(row["入力項目"])["sourceEventId"]
            == effective["source_event_id"])
        assert target_csv["打撃結果"] == "ボール"
        runtime_diagnostics["p3_zip_rows"] = len(csv_rows)
        runtime_diagnostics["p3_zip_label"] = target_csv["打撃結果"]
        runtime_diagnostics.update(stage="complete", status=200)
        return {
            "game": game,
            "prefix": current["prefix_ref"]["length"],
            "p3_d5": change["d5"],
            "old_play_id": target["id"],
            "effective_play_id": effective["id"],
            "effective_event_id": effective["source_event_id"],
            "stats_version_id": confirmed["stats_version_id"],
            "p3_zip_rows": len(csv_rows),
            "p3_zip_label": target_csv["打撃結果"],
            "runtime_diagnostics": runtime_diagnostics,
            "source_origin": {
                "sync_router": actual_sync_router.__file__,
                "read_router": actual_started_router.__file__,
            },
        }
"""
    else:
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
    if stop_after_p3:
        compile(script, "<p3-26-stop>", "exec")
        return script
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


def build_p3_26_lifecycle_script() -> str:
    """26球訂正・27球目の後に終了再開追加再終了と成績/CSVを同workerで通す。"""
    script = build_p3_26_script()
    start = _LIFECYCLE_SCRIPT.index("        import copy")
    end = _LIFECYCLE_SCRIPT.index("        current, _ = await read_full()", start)
    functions = _LIFECYCLE_SCRIPT[start:end]
    # 既存26球scriptのrun()本体は4-space。lifecycle関数群は8-spaceなので詰める。
    functions = "\n".join(
        line[4:] if line.startswith("    ") else line
        for line in functions.splitlines()
    ) + "\n"
    run_marker = "async def run():\n"
    assert script.count(run_marker) == 1
    script = script.replace(run_marker, run_marker + functions + "\n", 1)
    final = '''        runtime_diagnostics.update(stage="complete", status=200)
        return {
            "game": game,
            "prefix": current["prefix_ref"]["length"],
            "p3_d5": change["d5"],
'''
    assert script.count(final) == 1
    flow = '''        lifecycle_current, _ = await read_full()
        assert lifecycle_current["lifecycle"]["lastVersion"] == "0"
        ended, _ = await lifecycle("end", lifecycle_current)
        assert ended["status"] == "finished"
        reopened, _ = await lifecycle("reopen", ended)
        assert reopened["status"] == "in_progress"
        added = await additional_play()
        assert added["status"] == "in_progress"
        final_lifecycle, _ = await lifecycle("end", added)
        assert final_lifecycle["status"] == "finished"
        assert final_lifecycle["lifecycle"]["lastVersion"] == "2"
        reloaded, _ = await read_full()
        assert reloaded["checkpoint"] == final_lifecycle["checkpoint"]
        assert reloaded["lifecycle"] == final_lifecycle["lifecycle"]
        stats = await client.get(
            "/games/" + game + "/stats?mode=official&limit=200",
            headers=headers())
        assert stats.status_code == 200, ("stats-read", stats.status_code)
        stats_packet = stats.json()
        assert stats_packet["mode"] == "official"
        for player in stats_packet["players"]:
            assert len(player["batting"]) == 16
            assert len(player["pitching"]) == 11
        game_csv = await client.get(
            "/games/" + game + "/stats.csv?mode=official", headers=headers())
        assert game_csv.status_code == 200, ("game-csv", game_csv.status_code)
        assert game_csv.content.startswith(b"\\xef\\xbb\\xbf")
        import csv as _stats_csv
        import io as _stats_io
        stats_rows = list(_stats_csv.DictReader(_stats_io.StringIO(
            game_csv.content.decode("utf-8-sig"))))
        assert len(stats_rows) == len(stats_packet["players"])
        season_csv = await client.get(
            "/stats/seasons/" + str(case["year"]) + "/stats.csv?category=all",
            headers=headers())
        assert season_csv.status_code == 200, (
            "season-csv", season_csv.status_code)
        season_rows = list(_stats_csv.DictReader(_stats_io.StringIO(
            season_csv.content.decode("utf-8-sig"))))
        assert season_rows
        runtime_diagnostics["lifecycle_final"] = final_lifecycle["lifecycle"]
        runtime_diagnostics["stats_players"] = len(stats_packet["players"])
        runtime_diagnostics["stats_csv_rows"] = len(stats_rows)
        runtime_diagnostics["season_csv_rows"] = len(season_rows)
'''
    script = script.replace(final, flow + final, 1)
    script = script.replace(
        '            "last_play_id": latest["page"]["items"][1]["play_row"]["id"],\n',
        '            "last_play_id": latest["page"]["items"][1]["play_row"]["id"],\n'
        '            "stats_csv_rows": runtime_diagnostics["stats_csv_rows"],\n'
        '            "season_csv_rows": runtime_diagnostics["season_csv_rows"],\n'
        '            "lifecycle_last_version": final_lifecycle["lifecycle"]'
        '["lastVersion"],\n',
        1,
    )
    # DomainRuntimeErrorの安定codeだけを診断へ加え、secret/原値は出さない。
    old_cause = '"exception_type": type(current).__name__,\n'
    assert script.count(old_cause) >= 1
    script = script.replace(
        old_cause,
        old_cause
        + '                "domain_error_code": getattr(current, "code", None),\n'
        + '                "sql_primary": '
        'getattr(getattr(current, "diag", None), "message_primary", None) '
        'or getattr(getattr(getattr(current, "orig", None), "diag", None), '
        '"message_primary", None),\n',
        1,
    )
    compile(script, "<p3-26-lifecycle>", "exec")
    return script


def test_actual_p3_26_lifecycle_http(vertical_database, tmp_path) -> None:
    """正常current配置で26球変更・故障全取消・再掲・次球を実HTTPへ通す。"""
    db = vertical_database
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
    with (
        db.broker_worker(token) as rg1_broker,
        binding_broker(db, token),
    ):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", script],
            capture_output=True,
            text=True,
            timeout=900,
        )
        for command, label in (
            (["docker", "top", rg1_broker, "-eo", "pid,ppid,args"], "rg1-top"),
            (["docker", "logs", "--tail", "120", rg1_broker], "rg1-log"),
            (
                ["docker", "inspect", "--format",
                 "{{.State.Running}} {{.State.ExitCode}}", db.controller],
                "controller-state",
            ),
            (["docker", "logs", "--tail", "120", db.controller], "controller-log"),
            (
                ["docker", "inspect", "--format",
                 "{{.State.Running}} {{.State.ExitCode}}", db.authority.service],
                "authority-state",
            ),
            (
                ["docker", "logs", "--tail", "120", db.authority.service],
                "authority-log",
            ),
        ):
            observed = subprocess.run(
                command, capture_output=True, text=True, check=False)
            (tmp_path / f"{label}.txt").write_text(
                (observed.stdout or "") + (observed.stderr or ""))
    # stdoutは実HTTP成果JSONだけ。raw stderr/SQL/資格は失敗表示へ載せない。
    assert process.returncode == 0, "owned HTTP脚本が非成功終了"
    result = json.loads(process.stdout)
    (tmp_path / "p3-26-result.json").write_text(json.dumps(result, indent=2))
    if "exception" in result:
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute("SET TRANSACTION READ ONLY")
            diag = {
                "games": [
                    [str(row[0]), row[1], row[2]]
                    for row in admin.execute(
                        "SELECT id,status,hidden_at FROM public.games "
                        "WHERE tenant_id=%s ORDER BY id",
                        (db.tenant_id,),
                    ).fetchall()
                ],
                "generations": [
                    [row[0], row[1], str(row[2]), str(row[3]), str(row[4]), row[5]]
                    for row in admin.execute(
                        "SELECT generation,kind,holder_device,revoked_at,retired_at,"
                        "recovery_generation FROM public.recording_generations "
                        "WHERE tenant_id=%s ORDER BY game_id,generation",
                        (db.tenant_id,),
                    ).fetchall()
                ],
                "versions": [
                    [str(row[0]), row[1], row[2], row[3], row[4], row[5]]
                    for row in admin.execute(
                        "SELECT id,source_count,is_current,completion_state,"
                        "t5_artifact_set_sha256,rule_sha256 "
                        "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s "
                        "ORDER BY revision",
                        (db.tenant_id,),
                    ).fetchall()
                ],
                "gate": [
                    [row[0], row[1]]
                    for row in admin.execute(
                        "SELECT state,recovery_generation "
                        "FROM public.rg1_restore_gate WHERE singleton_id=1"
                    ).fetchall()
                ],
                "bindings": [
                    [str(row[0]), str(row[1]), row[2], str(row[3]), str(row[4])]
                    for row in admin.execute(
                        "SELECT attempt_id,phase_id,state,device_id,expires_at "
                        "FROM sync_fence.writer_bindings WHERE tenant_id=%s "
                        "ORDER BY expires_at,attempt_id,phase_id",
                        (db.tenant_id,),
                    ).fetchall()
                ],
            }
            p3_game = admin.execute(
                "SELECT game_id FROM sync_fence.p3_projection_capsules "
                "WHERE tenant_id=%s LIMIT 1",
                (db.tenant_id,),
            ).fetchone()
            if p3_game is not None:
                p3_key = (db.tenant_id, p3_game[0])
                diag["p3"] = {
                    "capsules": [
                        [str(row[0]), row[1], row[2], str(row[3]), str(row[4])]
                        for row in admin.execute(
                            "SELECT id,target_d1,watermark,stats_version_id,"
                            "change_event_id FROM "
                            "sync_fence.p3_projection_capsules "
                            "WHERE tenant_id=%s AND game_id=%s",
                            p3_key,
                        ).fetchall()
                    ],
                    "heads": [
                        [str(row[0]), row[1], str(row[2])]
                        for row in admin.execute(
                            "SELECT capsule_id,revision,stats_version_id FROM "
                            "sync_fence.p3_projection_heads "
                            "WHERE tenant_id=%s AND game_id=%s",
                            p3_key,
                        ).fetchall()
                    ],
                    "item_count": admin.execute(
                        "SELECT count(*),count(*) FILTER (WHERE state='corrected') "
                        "FROM sync_fence.p3_projection_capsule_items "
                        "WHERE tenant_id=%s AND game_id=%s",
                        p3_key,
                    ).fetchone(),
                    "page_row_count": admin.execute(
                        "SELECT count(*) FROM sync_fence.p3_projection_page_rows "
                        "WHERE tenant_id=%s AND game_id=%s",
                        p3_key,
                    ).fetchone(),
                    "snapshot_count": admin.execute(
                        "SELECT count(*) FROM sync_fence.play_export_p3_snapshots "
                        "WHERE tenant_id=%s AND game_id=%s",
                        p3_key,
                    ).fetchone(),
                    "target": [
                        [str(row[0]), row[1], str(row[2]), str(row[3])]
                        for row in admin.execute(
                            "SELECT d1,state,effective_event_id,"
                            "effective_play_row_id FROM "
                            "sync_fence.p3_projection_capsule_items "
                            "WHERE tenant_id=%s AND game_id=%s AND d1=26",
                            p3_key,
                        ).fetchall()
                    ],
                    "slots": [
                        [row[0], row[1], row[2]]
                        for row in admin.execute(
                            "SELECT generation,d1,confirmed_version FROM "
                            "public.event_slots WHERE tenant_id=%s AND game_id=%s "
                            "AND d1=26",
                            p3_key,
                        ).fetchall()
                    ],
                    "admissions": [
                        [row[0], str(row[1])]
                        for row in admin.execute(
                            "SELECT state,transaction_id FROM "
                            "sync_fence.p3_projection_write_admissions "
                            "WHERE tenant_id=%s AND game_id=%s",
                            p3_key,
                        ).fetchall()
                    ],
                    "change_events": [
                        [str(row[0]), str(row[1]), row[2], row[3]]
                        for row in admin.execute(
                            "SELECT id,d5,event_kind,target_d1 FROM "
                            "public.operation_events WHERE tenant_id=%s "
                            "AND game_id=%s AND event_kind='play_change'",
                            p3_key,
                        ).fetchall()
                    ],
                    "capsule_columns": [
                        row[0]
                        for row in admin.execute(
                            "SELECT column_name FROM "
                            "information_schema.columns "
                            "WHERE table_schema='sync_fence' "
                            "AND table_name='p3_projection_capsules' "
                            "ORDER BY ordinal_position"
                        ).fetchall()
                    ],
                    "capsule": admin.execute(
                        "SELECT to_jsonb(c) FROM "
                        "sync_fence.p3_projection_capsules c "
                        "WHERE c.tenant_id=%s AND c.game_id=%s",
                        p3_key,
                    ).fetchone(),
                    "progress": admin.execute(
                        "SELECT to_jsonb(p) FROM "
                        "sync_fence.p3_projection_page_progress p "
                        "WHERE p.tenant_id=%s AND p.game_id=%s",
                        p3_key,
                    ).fetchone(),
                    "checkpoint": admin.execute(
                        "SELECT to_jsonb(cp) FROM "
                        "sync_fence.ordinary_pitch_checkpoints cp "
                        "WHERE cp.tenant_id=%s AND cp.game_id=%s",
                        p3_key,
                    ).fetchone(),
                }
                head = admin.execute(
                    "SELECT h.stats_version_id,c.target_d1 FROM "
                    "sync_fence.p3_projection_heads h JOIN "
                    "sync_fence.p3_projection_capsules c ON "
                    "(c.tenant_id,c.game_id,c.id)=(h.tenant_id,h.game_id,"
                    "h.capsule_id) WHERE h.tenant_id=%s AND h.game_id=%s",
                    p3_key,
                ).fetchone()
                if head is not None:
                    diag["p3"]["sources"] = [
                        [
                            str(row[0]), str(row[1]), row[2], row[3],
                            row[4], row[5], row[6],
                        ]
                        for row in admin.execute(
                            "SELECT source_event_id,play_row_id,slot_version,"
                            "play_row_version,provider_kind,source_fingerprint,"
                            "artifact_sha256 FROM "
                            "sync_fence.stats_primitive_sources "
                            "WHERE tenant_id=%s AND game_id=%s "
                            "AND fact_version_id=%s AND d1=%s",
                            (*p3_key, head[0], head[1]),
                        ).fetchall()
                    ]
        diag["p3_checkpoints"] = [
            [
                str(row[0]), row[1], row[2], row[3], row[4], row[5],
                row[6], row[7], row[8],
            ]
            for row in admin.execute(
                "SELECT id,revision,history_version,confirmed_watermark,"
                "applied_watermark,state,content_digest,"
                "content->>'formatVersion',content->>'version' "
                "FROM sync_fence.ordinary_pitch_checkpoints "
                "WHERE tenant_id=%s AND game_id=%s ORDER BY revision",
                p3_key,
            ).fetchall()
        ]
        diag["p3_capsule_row"] = admin.execute(
            "SELECT to_jsonb(c) FROM sync_fence.p3_projection_capsules c "
            "WHERE c.tenant_id=%s AND c.game_id=%s",
            p3_key,
        ).fetchone()
        diag["p3_head_row"] = admin.execute(
            "SELECT to_jsonb(h) FROM sync_fence.p3_projection_heads h "
            "WHERE h.tenant_id=%s AND h.game_id=%s",
            p3_key,
        ).fetchone()
        diag["p3_stats_rows"] = [
            [
                str(row[0]), row[1], row[2], row[3], row[4], row[5], row[6],
            ]
            for row in admin.execute(
                "SELECT id,source_count,is_current,invalidated_at,"
                "model_sha256,source_set_sha256,completion_state "
                "FROM sync_fence.stats_fact_versions "
                "WHERE tenant_id=%s AND game_id=%s ORDER BY revision",
                p3_key,
            ).fetchall()
        ]
        (tmp_path / "p3-26-fault-db.json").write_text(
            json.dumps(diag, indent=2, default=str)
        )
    assert "exception" not in result, result.get("runtime_diagnostics", {}).get("stage")
    assert result["prefix"] == "27"
    assert UUID(result["game"]) != db.game_id
    assert result["old_play_id"] != result["effective_play_id"]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute("SET TRANSACTION READ ONLY")
        key = (db.tenant_id, UUID(result["game"]))
        capsule = admin.execute(
            "SELECT id,change_event_id FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchall()
        assert len(capsule) == 1
        capsule_id, capsule_change_event_id = capsule[0]
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsule_items "
            "WHERE tenant_id=%s AND game_id=%s AND capsule_id=%s",
            (*key, capsule_id),
        ).fetchone() == (26,)
        assert admin.execute(
            "SELECT state,original_play_row_id,effective_event_id,"
            "effective_play_row_id FROM "
            "sync_fence.p3_projection_capsule_items "
            "WHERE tenant_id=%s AND game_id=%s AND capsule_id=%s AND d1=26",
            (*key, capsule_id),
        ).fetchall() == [(
            "corrected",
            UUID(result["old_play_id"]),
            UUID(result["effective_event_id"]),
            UUID(result["effective_play_id"]),
        )]
        assert admin.execute(
            "SELECT capsule_id,revision FROM sync_fence.p3_projection_heads "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchall() == [(capsule_id, 1)]
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_page_rows "
            "WHERE tenant_id=%s AND game_id=%s AND capsule_id=%s",
            (*key, capsule_id),
        ).fetchone() == (26,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.play_export_p3_snapshots "
            "WHERE tenant_id=%s AND game_id=%s AND capsule_id=%s",
            (*key, capsule_id),
        ).fetchone() == (26,)
        csv_row = admin.execute(
            "SELECT effective_event_id,effective_play_row_id,"
            "plays_csv_json->>'打撃結果',"
            "plays_csv_json->>'入力項目' "
            "FROM sync_fence.play_export_p3_snapshots "
            "WHERE tenant_id=%s AND game_id=%s AND capsule_id=%s AND d1=26",
            (*key, capsule_id),
        ).fetchone()
        assert csv_row is not None
        assert csv_row[0] == UUID(result["effective_event_id"])
        assert csv_row[1] == UUID(result["effective_play_id"])
        assert csv_row[2] == "ボール"
        csv_origin = json.loads(csv_row[3])
        assert csv_origin["projectionKind"] == "p3-current"
        assert csv_origin["sourceEventId"] == result["effective_event_id"]
        assert csv_origin["capsuleId"] == str(capsule_id)
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


def test_actual_p3_26_csv_export_http(vertical_database, tmp_path) -> None:
    """P3 26球訂正後の実CSV/ZIP取得を、27球目のgate復旧と切り離して照合する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
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
    with db.broker_worker(token, auto_restart=True), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            [
                "docker",
                *_app_arguments(db, case),
                "-u",
                "-c",
                build_p3_26_script(stop_after_p3=True),
            ],
            capture_output=True,
            text=True,
            timeout=900,
        )
    assert process.returncode == 0, "owned HTTP脚本が非成功終了"
    result = json.loads(process.stdout)
    (tmp_path / "p3-26-csv-result.json").write_text(json.dumps(result, indent=2))
    assert "exception" not in result, result.get("runtime_diagnostics", {}).get("stage")
    assert result["prefix"] == "26"
    assert result["p3_zip_rows"] == 26
    assert result["p3_zip_label"] == "ボール"
    with psycopg.connect(db.authority.database.business_admin) as admin:
        key = (db.tenant_id, UUID(result["game"]))
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (1,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.play_export_p3_snapshots "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (26,)
        assert admin.execute(
            "SELECT plays_csv_json->>'打撃結果' "
            "FROM sync_fence.play_export_p3_snapshots "
            "WHERE tenant_id=%s AND game_id=%s AND d1=26",
            key,
        ).fetchone() == (result["p3_zip_label"],)


def test_actual_p3_26_lifecycle_end_reopen_add_reend_stats(
    vertical_database, tmp_path
) -> None:
    """訂正後の27球から終了/再開/追加/再終了と成績/CSVを同一候補で通す。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
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
        "year": datetime.now(timezone(timedelta(hours=9))).year,
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            [
                "docker",
                *_app_arguments(db, case),
                "-u",
                "-c",
                build_p3_26_lifecycle_script(),
            ],
            capture_output=True,
            text=True,
            timeout=1200,
        )
    assert process.returncode == 0, "owned HTTP脚本が非成功終了"
    result = json.loads(process.stdout)
    (tmp_path / "p3-26-lifecycle.json").write_text(json.dumps(result, indent=2))
    if "exception" in result:
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute("SET TRANSACTION READ ONLY")
            diag = {
                "gate": admin.execute(
                    "SELECT state,recovery_generation FROM public.rg1_restore_gate"
                ).fetchall(),
                "versions": [
                    [row[0], row[1], row[2], row[3]]
                    for row in admin.execute(
                        "SELECT source_count,is_current,completion_state,revision "
                        "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s "
                        "ORDER BY revision",
                        (db.tenant_id,),
                    ).fetchall()
                ],
                "p3": [
                    [
                        str(row[0]), row[1], row[2], str(row[3]), str(row[4]),
                        row[5], str(row[6]),
                    ]
                    for row in admin.execute(
                        "SELECT id,target_d1,watermark,next_checkpoint_id,"
                        "stats_version_id,expected_version,change_event_id "
                        "FROM sync_fence.p3_projection_capsules "
                        "WHERE tenant_id=%s",
                        (db.tenant_id,),
                    ).fetchall()
                ],
                "checkpoints": [
                    [
                        str(row[0]), row[1], row[2], str(row[3]), row[4], row[5],
                        row[6], row[7], row[8],
                    ]
                    for row in admin.execute(
                        "SELECT id,revision,history_version,confirmed_watermark,"
                        "applied_watermark,state,content_digest,"
                        "content->>'formatVersion',content->>'version' "
                        "FROM sync_fence.ordinary_pitch_checkpoints "
                        "WHERE tenant_id=%s ORDER BY revision",
                        (db.tenant_id,),
                    ).fetchall()
                ],
                "capsule_json": admin.execute(
                    "SELECT to_jsonb(c) FROM sync_fence.p3_projection_capsules c "
                    "WHERE c.tenant_id=%s",
                    (db.tenant_id,),
                ).fetchone(),
                "stats_json": [
                    [
                        str(row[0]), row[1], row[2], row[3], row[4], row[5],
                    ]
                    for row in admin.execute(
                        "SELECT id,source_count,is_current,invalidated_at,"
                        "model_sha256,source_set_sha256 "
                        "FROM sync_fence.stats_fact_versions "
                        "WHERE tenant_id=%s ORDER BY revision",
                        (db.tenant_id,),
                    ).fetchall()
                ],
            }
        (tmp_path / "p3-26-lifecycle-db.json").write_text(
            json.dumps(diag, default=str)
        )
    assert "exception" not in result, (
        result.get("runtime_diagnostics", {}).get("stage"),
        result.get("runtime_diagnostics", {}).get("cause_frames"),
    )
    assert result["prefix"] == "27"
    assert result["lifecycle_last_version"] == "2"
    assert result["stats_csv_rows"] > 0
    assert result["season_csv_rows"] > 0
    game = UUID(result["game"])
    with psycopg.connect(db.authority.database.business_admin) as admin:
        params = (db.tenant_id, game)
        assert admin.execute(
            "SELECT count(*) FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s AND hidden_at IS NULL",
            params,
        ).fetchone() == (28,)
        current = admin.execute(
            "SELECT v.source_count,v.completion_state,"
            "v.completion_receipt_id=h.active_receipt_id,"
            "v.public_pointer_receipt_id=h.active_receipt_id "
            "FROM sync_fence.stats_fact_versions v "
            "JOIN sync_fence.game_lifecycle_heads h ON "
            "h.tenant_id=v.tenant_id AND h.game_id=v.game_id "
            "AND h.active_stats_version_id=v.id "
            "WHERE v.tenant_id=%s AND v.game_id=%s AND v.is_current "
            "AND v.invalidated_at IS NULL",
            params,
        ).fetchall()
        assert current == [(28, "confirmed_ended", True, True)]
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND is_current",
            params,
        ).fetchone() == (1,)
        assert admin.execute(
            "SELECT max(source_count) FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s",
            params,
        ).fetchone() == (28,)
        assert admin.execute(
            "SELECT state,recovery_generation FROM public.rg1_restore_gate "
            "WHERE singleton_id=1"
        ).fetchall() == [("open", 1)]
