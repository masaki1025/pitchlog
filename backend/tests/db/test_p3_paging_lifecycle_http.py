"""真正v3通常26球からP3/再掲/次球を測る隔離HTTP driver生成候補。"""

from __future__ import annotations

# 旧作者の26球操作脚本だけを再利用し、後付candidate DDLは呼ばない。
import json
import subprocess
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
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", script],
            capture_output=True,
            text=True,
            timeout=900,
        )
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
