"""作者cache 0046候補のowned PG構文実測。正式asset受理ではない。"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.p3_binding_sql import candidate_sql as binding_sql
from pitchlog.authz.p3_projection_sql import candidate_current_read_sql
from pitchlog.authz.p3_projection_sql import candidate_sql as persist_sql
from pitchlog.authz.p3_projection_trigger_patch import candidate_sql as trigger_sql
from pitchlog.authz.p3_right_sql import candidate_sql as right_sql
from pitchlog.authz.stats_primitive_sql import candidate_function_bodies
from pitchlog.domaingen.core import generate_native_primitive_sql_bundle

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
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_terminal_pitch_storage import _lineup_script

pytestmark = pytest.mark.requires_db
_PACKET = Path.home() / ".cache/pitchlog/mvp-past-correction-product-20261106"
_STAGES = frozenset(
    {
        "p3-post",
        "p3-get",
        "p3-replay",
        "p3-conflict",
        "next-pitch-math",
        "next-pitch-post",
        "next-pitch-replay",
        "next-pitch-get",
        "complete",
    }
)


def _diagnostic_stats_body(body: str) -> str:
    """同じ拒否条件を維持してowned診断に固定位置だけ記録する。"""
    if "save_primitive_source" not in body.split("\n", 1)[0]:
        return body
    rejection_number = 0

    def label_rejection(match: re.Match[str]) -> str:
        """固定の拒否位置ラベルだけを返す。"""
        nonlocal rejection_number
        rejection_number += 1
        return "stats primitive boundary rejected " f"P3S{rejection_number:02d}"

    return re.sub("stats primitive boundary rejected", label_rejection, body)


def _write_stage(result: dict, path: Path) -> dict:
    """失敗応答から原文を捨て、固定段/status/script行だけを実ファイルへ書く。"""
    diagnostic = result.get("runtime_diagnostics")
    if type(diagnostic) is not dict:
        diagnostic = {}
    stage = diagnostic.get("stage")
    status = diagnostic.get("status")
    frames = result.get("frames")
    record = {
        "stage": stage if type(stage) is str and stage in _STAGES else "unknown",
        "status": status if type(status) is int and 100 <= status <= 599 else None,
        "last_script_line": frames[-1][1]
        if type(frames) is list
        and frames
        and type(frames[-1]) in (list, tuple)
        and len(frames[-1]) == 2
        and type(frames[-1][1]) is int
        else None,
        "failed": "exception" in result,
    }
    path.write_text(json.dumps(record, indent=2))
    return record


def test_owned_candidate_0046_compiles(vertical_database) -> None:
    """正式profile/数学を差し替えず、候補のDB本文を別owned DBへ配備する。"""
    ddl = (_PACKET / "0046-p3-projection.candidate.sql").read_text()
    selector = (_PACKET / "p3-play_primitives_native.sql").read_text()
    profile = json.loads(
        (_PACKET / "play-export-p3-selection.model.candidate.json").read_text()
    )
    root = Path(__file__).resolve().parents[3]
    generated = generate_native_primitive_sql_bundle(
        json.loads((root / "backend/domain/play-export.model.json").read_text()),
        json.loads((root / "backend/domain/stats.model.json").read_text()),
        profile,
    )
    assert selector == generated[
        "backend/src/pitchlog/exports/generated/play_primitives_native.sql"
    ]
    parts = selector.split("-- pitchlog-query: ")[1:]
    health = {part.split("\n", 1)[0]: part.split("\n", 1)[1].strip() for part in parts}[
        "canonical_health"
    ]
    statements = "\n".join(
        line for line in ddl.splitlines() if not line.lstrip().startswith("--")
    ).split(";")
    with psycopg.connect(vertical_database.authority.database.business_admin) as conn:
        with conn.cursor() as cursor:
            for statement in statements:
                if statement.strip():
                    cursor.execute(sql.SQL(cast(LiteralString, statement)))
            for statement in right_sql().values():
                cursor.execute(sql.SQL(cast(LiteralString, statement)), prepare=False)
            cursor.execute(sql.SQL(cast(LiteralString, binding_sql())), prepare=False)
            cursor.execute(sql.SQL(cast(LiteralString, trigger_sql())), prepare=False)
            cursor.execute(
                sql.SQL(cast(LiteralString, persist_sql(health_sql=health))),
                prepare=False,
            )
            cursor.execute(
                sql.SQL(
                    cast(LiteralString, candidate_current_read_sql(health_sql=health))
                ),
                prepare=False,
            )
            for body in candidate_function_bodies(p3_selector_profile=profile).values():
                body = _diagnostic_stats_body(body)
                replacement = body.replace(
                    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
                )
                cursor.execute(
                    sql.SQL(cast(LiteralString, replacement)),
                    prepare=False,
                )
            cursor.execute(
                "SELECT pg_catalog.to_regprocedure("
                "'sync_right_api.persist_p3_projection(uuid,uuid,uuid,bytea,uuid,uuid,text,text)')"
            )
            installed = cursor.fetchone()
            assert installed is not None and installed[0] is not None
            cursor.execute(
                "SELECT pg_catalog.to_regprocedure("
                "'sync_right_api.read_p3_current(uuid,uuid,bigint)')"
            )
            installed = cursor.fetchone()
            assert installed is not None and installed[0] is not None


def _three_ball_p3_script() -> str:
    """既create/start/v3本文を使い、三球の第一球だけP3で変更する。"""
    script = _lineup_script()
    marker = "async def run():"
    assert script.count(marker) == 1
    trace = """_actual_p3_apply = actual_sync_router._apply_e1_p3
import re

def traced_p3_apply(*args, **kwargs):
    try:
        return _actual_p3_apply(*args, **kwargs)
    except Exception as error:
        chain = []
        seen = set()
        current = error
        while current is not None and len(chain) < 8 and id(current) not in seen:
            seen.add(id(current))
            original = getattr(current, "orig", None)
            diagnostic = getattr(original, "diag", None)
            primary = getattr(diagnostic, "message_primary", None)
            context = getattr(diagnostic, "context", None)
            detail = getattr(diagnostic, "message_detail", None)
            try:
                guard = json.loads(detail) if detail is not None else None
            except (TypeError, ValueError):
                guard = None
            allowed = {"payload", "history", "play", "runners", "evaluation", "rule",
                       "play_link", "d2_source", "d2_item", "play_id", "event_id",
                       "eval_digest"}
            guard = guard if type(guard) is dict and set(guard) == allowed and all(
                type(value) is bool for value in guard.values()) else None
            line = re.search(
                r"PL/pgSQL function sync_right_api\\.persist_p3_projection"
                r"\\([^)]*\\) line (\\d+)",
                context or "")
            chain.append({
                "exception_type": type(current).__name__,
                "database_exception_type": type(original).__name__,
                "sqlstate": getattr(original, "sqlstate", None),
                "sql_primary_class": (
                    "p3-closed-rejection" if primary == "P3 projection rejected"
                    else "permission-denied" if type(primary) is str
                        and primary.startswith("permission denied")
                    else "other" if primary is not None else None),
                "plpgsql_line": int(line.group(1)) if line else None,
                "p3_guard_flags": guard,
                "frames": [(f.name, f.lineno)
                           for f in traceback.extract_tb(current.__traceback__)],
            })
            current = current.__cause__ or current.__context__
        runtime_diagnostics["p3"] = {
            "chain": chain,
        }
        raise

actual_sync_router._apply_e1_p3 = traced_p3_apply

"""
    read_trace = r"""from pitchlog.api.routers import started_games
actual_started_router = started_games
_actual_p3_read = actual_started_router.read_lineup_prefix

def traced_p3_read(*args, **kwargs):
    try:
        return _actual_p3_read(*args, **kwargs)
    except Exception as error:
        chain = []
        seen = set()
        current = error
        while current is not None and len(chain) < 8 and id(current) not in seen:
            seen.add(id(current))
            original = getattr(current, "orig", None)
            diagnostic = getattr(original, "diag", None)
            primary = getattr(diagnostic, "message_primary", None)
            context = getattr(diagnostic, "context", None)
            name = re.fullmatch(
                r'column reference "([a-z_][a-z0-9_]*)" is ambiguous',
                primary or "")
            line = re.search(
                r"PL/pgSQL function sync_right_api\.read_p3_current"
                r"\([^)]*\) line (\d+)", context or "")
            chain.append({
                "exception_type": type(current).__name__,
                "database_exception_type": type(original).__name__,
                "sqlstate": getattr(original, "sqlstate", None),
                "sql_identifier": name.group(1) if name else None,
                "plpgsql_line": int(line.group(1)) if line else None,
                "frames": [(f.name, f.lineno)
                           for f in traceback.extract_tb(current.__traceback__)],
            })
            current = current.__cause__ or current.__context__
        runtime_diagnostics["p3_read"] = chain
        raise

actual_started_router.read_lineup_prefix = traced_p3_read

"""
    script = script.replace(marker, trace + read_trace + marker, 1)
    # 元driverの故障・foreign対向は別case。ここはP3実接合の最小経路に限定する。
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
        'results = ["batting-result.ball", "batting-result.called-pitch"]',
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
    third = script[loop_start:loop_end].replace(
        "for index, result in enumerate(results, 1):",
        'for index, result in enumerate(["batting-result.ball"], 3):',
        1,
    )
    third = third.replace(
        '                response = decode_lineup_prefix_response(\n'
        '                    host.call(',
        '                runtime_diagnostics.update('
        'stage="next-pitch-math", status=None)\n'
        '                response = decode_lineup_prefix_response(\n'
        '                    host.call(',
        1,
    )
    for needle, stage in (
        ("            posted = await client.post(", "next-pitch-post"),
        ("            replay = await client.post(", "next-pitch-replay"),
        ("            saved = await client.get(", "next-pitch-get"),
    ):
        assert third.count(needle) == 1
        third = third.replace(
            needle,
            f'            runtime_diagnostics.update(stage="{stage}", status=None)\n'
            + needle,
            1,
        )
    for needle, name in (
        ("            assert posted.status_code == 200, (", "posted"),
        ("            assert (\n                replay.status_code == 200", "replay"),
        ("            assert saved.status_code == 200,", "saved"),
    ):
        assert third.count(needle) == 1
        third = third.replace(
            needle,
            f'            runtime_diagnostics["status"] = {name}.status_code\n'
            + needle,
            1,
        )
    p3 = """        target = current["page"]["items"][0]["play_row"]
        assert (current["checkpoint_anchor"]["id"]
                != current["prefix_ref"]["checkpoint"]["id"])
        change = {
            "d5": str(uuid4()), "game_id": game, "event_kind": "play_change",
            "target_reference": {"game": game, "d4": 1, "d1": 1},
            "expected_version": 1,
            "payload": {
                "formatVersion": "p3-lineup-pitch-change-v1",
                "expectedPrefixRef": current["prefix_ref"],
                "targetEventId": target["source_event_id"],
                "targetPlayId": target["id"],
                "originalResultId": "batting-result.ball",
                "replacementResultId": "batting-result.called-pitch",
                "replacementObservations": {
                    "pitchTypeKey": case["pitch_type"],
                    "course": {"unit": "1/263", "x": "100", "y": "150"},
                    "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                    "stance": None, "battingSide": None,
                },
            },
        }
        p3_payload = {"recovery_generation": current["recovery_generation"],
                      "recording_right_proof": started["recording_right_proof"],
                      "change": change}
        p3_headers = device_headers(pair, str(uuid4()))
        runtime_diagnostics.update(stage="p3-post", status=None)
        changed = await client.post("/games/" + game + "/sync/change",
                                    headers=p3_headers, json=p3_payload)
        runtime_diagnostics["status"] = changed.status_code
        assert changed.status_code == 200, (
            "p3-change", changed.status_code, changed.text[:300], runtime_diagnostics)
        runtime_diagnostics.update(stage="p3-get", status=None)
        reread = await client.get(
            "/games/" + game + "/started?projection=play-prefix-v3&limit=100",
            headers=headers())
        runtime_diagnostics["status"] = reread.status_code
        assert reread.status_code == 200, (
            "p3-get", reread.status_code, reread.text[:300], runtime_diagnostics)
        corrected_current = reread.json()
        assert corrected_current["page"]["items"][0]["play_row"]["id"] != target["id"]
        assert (corrected_current["checkpoint_anchor"]["id"]
                == current["checkpoint_anchor"]["id"])
        assert (corrected_current["checkpoint_anchor"]["id"]
                != corrected_current["prefix_ref"]["checkpoint"]["id"])
        runtime_diagnostics.update(stage="p3-replay", status=None)
        replayed = await client.post("/games/" + game + "/sync/change",
                                     headers=device_headers(pair, str(uuid4())),
                                     json=p3_payload)
        runtime_diagnostics["status"] = replayed.status_code
        assert replayed.status_code == 200 and replayed.json() == changed.json(), (
            "p3-replay", replayed.status_code, replayed.text[:300])
        conflict_payload = json.loads(json.dumps(p3_payload))
        conflict_payload["change"]["payload"]["replacementResultId"] = (
            "batting-result.ball")
        runtime_diagnostics.update(stage="p3-conflict", status=None)
        conflicted = await client.post("/games/" + game + "/sync/change",
                                       headers=device_headers(pair, str(uuid4())),
                                       json=conflict_payload)
        runtime_diagnostics["status"] = conflicted.status_code
        assert (conflicted.status_code == 200
                and conflicted.json()["boundary"] == "B13"), (
            "p3-conflict", conflicted.status_code, conflicted.text[:300])
        current = corrected_current
__THIRD_PITCH__
        runtime_diagnostics.update(stage="complete", status=200)
        from pitchlog.authz import p3_projection_sql as actual_p3_sql
        from pitchlog.repositories import past_correction_source as actual_p3_source
        return {"game": game, "change": changed.json(),
                "prefix": current["prefix_ref"]["length"],
                "source_origin": {
                    "sync_router": actual_sync_router.__file__,
                    "p3_sql": actual_p3_sql.__file__,
                    "p3_source": actual_p3_source.__file__}}"""
    assert p3.count("__THIRD_PITCH__") == 1
    p3 = p3.replace("__THIRD_PITCH__", third.rstrip(), 1)
    script = script.replace(old_return, p3, 1)
    foreign_start = script.index("        # 別tenantの実ログイン")
    foreign_end = script.index("        target = current", foreign_start)
    return script[:foreign_start] + script[foreign_end:]


def test_owned_candidate_actual_http_p3(vertical_database) -> None:
    """候補DDL/本文をowned実DBへ適用し、真正開始後のHTTP訂正を検査する。"""
    test_owned_candidate_0046_compiles(vertical_database)
    db = vertical_database
    control_sql = (_PACKET / "p3-d1less-control-functions.candidate.sql").read_text()
    control_apply = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "--user",
            "postgres",
            db.authority.binding_control,
            "psql",
            "-X",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "binding_control_fixture",
        ],
        input=control_sql,
        capture_output=True,
        text=True,
        check=False,
    )
    assert control_apply.returncode == 0, control_apply.stderr[-500:]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch',"
            "'batting_result','見逃し') ON CONFLICT(key) DO NOTHING"
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
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _three_ball_p3_script()],
            capture_output=True,
            text=True,
            timeout=300,
        )
    assert process.returncode == 0, (process.stdout[-1200:], process.stderr[-1200:])
    result = json.loads(process.stdout)
    (_PACKET / "owned-http-diagnostic.json").write_text(
        json.dumps(result.get("runtime_diagnostics", {}), indent=2)
    )
    _write_stage(result, _PACKET / "owned-http-failure-stage.json")
    assert "exception" not in result, result
    assert result["prefix"] == "3"
    assert result["source_origin"]["sync_router"].endswith(
        "/pitchlog/api/routers/sync.py"
    )
    assert result["source_origin"]["p3_sql"].endswith(
        "/pitchlog/authz/p3_projection_sql.py"
    )
    assert result["source_origin"]["p3_source"].endswith(
        "/pitchlog/repositories/past_correction_source.py"
    )
    (_PACKET / "owned-http-source-origin.json").write_text(
        json.dumps(result["source_origin"], indent=2)
    )
    with psycopg.connect(db.authority.database.business_admin) as admin:
        key = (db.tenant_id, UUID(result["game"]))
        assert admin.execute(
            "SELECT count(*) FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s", key
        ).fetchone() == (4,)
        assert admin.execute(
            "SELECT count(*) FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s", key
        ).fetchone() == (4,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s", key
        ).fetchone() == (1,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsule_items "
            "WHERE tenant_id=%s AND game_id=%s", key
        ).fetchone() == (2,)
        current = admin.execute(
            "SELECT id,source_count FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND is_current "
            "AND invalidated_at IS NULL", key
        ).fetchall()
        assert len(current) == 1 and current[0][1] == 3
        sources = admin.execute(
            "SELECT source_event_id,d1 FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s ORDER BY d1",
            (*key, current[0][0]),
        ).fetchall()
        assert len(sources) == 3 and [row[1] for row in sources] == [1, 2, 3]
        p3 = admin.execute(
            "SELECT change_event_id FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s", key
        ).fetchone()
        assert p3 is not None and sources[0][0] == p3[0]
