"""作者cache 0048候補のowned PG構文実測。正式asset受理ではない。"""

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
from pitchlog.authz.p3_nonplay_bridge_sql import (
    candidate_function_bodies_p3_nonplay_bridge,
    candidate_lifecycle_p3_body,
)
from pitchlog.authz.p3_projection_sql import candidate_current_read_sql
from pitchlog.authz.p3_projection_sql import candidate_sql as persist_sql
from pitchlog.authz.p3_projection_trigger_patch import candidate_sql as trigger_sql
from pitchlog.authz.p3_right_sql import candidate_sql as right_sql
from pitchlog.authz.stats_primitive_sql import candidate_function_bodies
from pitchlog.domaingen.core import generate_native_primitive_sql_bundle
from pitchlog.stats.generated.receiver import METRIC_IDS

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
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)
from .test_terminal_pitch_storage import _lineup_script

pytestmark = pytest.mark.requires_db
_PACKET = Path.home() / ".cache/pitchlog/mvp-past-correction-product-20261106"
_STAGES = frozenset(
    {
        "p3-post",
        "p3-target-read",
        "p3-invalid-numeric",
        "p3-invalid-tampered",
        "p3-invalid-other-game",
        "p3-invalid-read",
        "p3-get",
        "p3-replay",
        "p3-conflict",
        "p3-fault-after_t2_event",
        "p3-fault-after_t4_projection",
        "p3-fault-read-after_t2_event",
        "p3-fault-read-after_t4_projection",
        "next-pitch-math",
        "next-pitch-post",
        "next-pitch-replay",
        "next-pitch-get",
        "foreign-login",
        "foreign-read",
        "foreign-p3-replay",
        "owner-final-get",
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
        return f"stats primitive boundary rejected P3S{rejection_number:02d}"

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


def _assert_stats27_catalog(vertical_database) -> None:
    """実0045後の版/source/credit全制約を単一生成27キーへ照合する。"""
    with psycopg.connect(vertical_database.authority.database.business_admin) as admin:
        for table, constraint in (
            ("stats_fact_versions", "ck_stats_version_metric_keys"),
            ("stats_primitive_sources", "ck_stats_source_metric_keys"),
            ("stats_primitive_facts", "ck_stats_fact_metric"),
        ):
            rows = admin.execute(
                "SELECT pg_catalog.pg_get_constraintdef(c.oid),c.convalidated "
                "FROM pg_catalog.pg_constraint c "
                "JOIN pg_catalog.pg_class t ON t.oid=c.conrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace "
                "WHERE n.nspname='sync_fence' AND t.relname=%s "
                "AND c.conname=%s AND c.contype='c'",
                (table, constraint),
            ).fetchall()
            assert len(rows) == 1 and rows[0][1] is True
            definition = rows[0][0]
            keys = tuple(re.findall(r"'([a-z][a-z0-9_]*)'::text", definition))
            assert keys == METRIC_IDS and len(keys) == 27, (table, constraint)
            if table == "stats_primitive_facts":
                admin.execute("CREATE TEMP TABLE metric27_probe(metric_id text)")
                admin.execute(
                    sql.SQL(
                        "ALTER TABLE pg_temp.metric27_probe ADD CONSTRAINT "
                        "ck_metric27_probe {}"
                    ).format(sql.SQL(cast(LiteralString, definition)))
                )
                for metric in METRIC_IDS:
                    admin.execute(
                        "INSERT INTO pg_temp.metric27_probe(metric_id) VALUES (%s)",
                        (metric,),
                    )
                with pytest.raises(psycopg.errors.CheckViolation):
                    with admin.transaction():
                        admin.execute(
                            "INSERT INTO pg_temp.metric27_probe(metric_id) "
                            "VALUES ('unknown_metric')"
                        )


def test_owned_candidate_0048_compiles(vertical_database) -> None:
    """正式profile/数学を差し替えず、候補のDB本文を別owned DBへ配備する。"""
    _assert_stats27_catalog(vertical_database)
    ddl = (_PACKET / "0048-p3-projection.candidate.sql").read_text()
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
    assert (
        selector
        == generated[
            "backend/src/pitchlog/exports/generated/play_primitives_native.sql"
        ]
    )
    parts = selector.split("-- pitchlog-query: ")[1:]
    sections = {
        part.split("\n", 1)[0]: part.split("\n", 1)[1].strip() for part in parts
    }
    health = sections["canonical_health"]
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
            for body in candidate_function_bodies_p3_nonplay_bridge().values():
                replacement = body.replace(
                    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
                )
                cursor.execute(
                    sql.SQL(cast(LiteralString, replacement)),
                    prepare=False,
                )
            lifecycle_body = candidate_lifecycle_p3_body(
                health, sections["canonical_source_members"]
            )
            cursor.execute(
                sql.SQL(
                    cast(
                        LiteralString,
                        lifecycle_body.replace(
                            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
                        ),
                    )
                ),
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
from pitchlog.sync import past_correction_preparation as actual_p3_prep
_actual_p3_snapshot = actual_p3_prep.read_past_correction_v3_source_snapshot
_p3_source_scope = {}

def traced_p3_snapshot(scope, game_id, target_d1):
    snapshot = _actual_p3_snapshot(scope, game_id, target_d1)
    _p3_source_scope["snapshot"] = snapshot
    _p3_source_scope["tenant"] = scope._bound_tenant_id
    return snapshot

actual_p3_prep.read_past_correction_v3_source_snapshot = traced_p3_snapshot

def traced_p3_apply(*args, **kwargs):
    try:
        return _actual_p3_apply(*args, **kwargs)
    except Exception as error:
        try:
            if "snapshot" in _p3_source_scope:
                original_event = args[2].events[0]
                expected_generation = kwargs["phase"].attempt.internal_generation
                snapshot = _p3_source_scope["snapshot"]
                last_ref = snapshot.rows[-1].calculation.response.value.next_prefix_ref
                runtime_diagnostics["p3_binding_flags"] = {
                    "generation_equal": (
                        snapshot.internal_generation == expected_generation),
                    "tenant_equal": (
                        last_ref.tenant_id == str(_p3_source_scope["tenant"])),
                    "game_equal": last_ref.game_id == original_event.game_id,
                }
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            runtime_diagnostics["p3_binding_flags"] = "unavailable"
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
        "                response = decode_lineup_prefix_response(\n"
        "                    host.call(",
        "                runtime_diagnostics.update("
        'stage="next-pitch-math", status=None)\n'
        "                response = decode_lineup_prefix_response(\n"
        "                    host.call(",
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
        target_d1 = 1
        runtime_diagnostics.update(stage="p3-target-read", status=None)
        target_read = await client.get(
            "/games/" + game + "/sync/change-target/" + str(target_d1),
            headers=headers())
        runtime_diagnostics["status"] = target_read.status_code
        assert target_read.status_code == 200, (
            "p3-target-read", target_read.status_code)
        offer = target_read.json()
        assert set(offer) == {
            "target_reference", "expected_version", "expected_prefix_ref",
            "target_event_id", "target_play_id", "original_result_id"}
        assert offer["target_reference"] == {
            "game": game, "d4": started["d4"], "d1": target_d1}
        assert offer["expected_version"] == 1
        assert offer["expected_prefix_ref"] == current["prefix_ref"]
        assert offer["target_event_id"] == target["source_event_id"]
        assert offer["target_play_id"] == target["id"]
        unconfirmed = await client.get(
            "/games/" + game + "/sync/change-confirmation/" + str(target_d1),
            headers=headers())
        assert unconfirmed.status_code == 409
        assert (current["checkpoint_anchor"]["id"]
                != current["prefix_ref"]["checkpoint"]["id"])
        change = {
            "d5": str(uuid4()), "game_id": game, "event_kind": "play_change",
            "target_reference": offer["target_reference"],
            "expected_version": offer["expected_version"],
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
        assert offer["original_result_id"] == change["payload"]["originalResultId"]
        negative_d5s = []
        for variant in ("numeric", "tampered", "other-game"):
            invalid = json.loads(json.dumps(p3_payload))
            invalid_d5 = str(uuid4())
            invalid["change"]["d5"] = invalid_d5
            negative_d5s.append(invalid_d5)
            if variant == "numeric":
                invalid["change"]["target_reference"]["d4"] = 1
            elif variant == "tampered":
                wire = started["d4"]
                invalid["change"]["target_reference"]["d4"] = (
                    wire[:5] + ("B" if wire[5] == "A" else "A") + wire[6:])
            else:
                invalid["change"]["target_reference"]["game"] = case["game"]
            runtime_diagnostics.update(stage="p3-invalid-" + variant, status=None)
            denied = await client.post(
                "/games/" + game + "/sync/change",
                headers=device_headers(pair, str(uuid4())), json=invalid)
            runtime_diagnostics["status"] = denied.status_code
            assert denied.status_code == 422, (
                "p3-invalid-wire", variant, denied.status_code)
        runtime_diagnostics.update(stage="p3-invalid-read", status=None)
        after_invalid = await client.get(
            "/games/" + game + "/started?projection=play-prefix-v3&limit=100",
            headers=headers())
        runtime_diagnostics["status"] = after_invalid.status_code
        assert after_invalid.status_code == 200 and after_invalid.json() == current, (
            "p3-invalid-no-write", after_invalid.status_code)
        class PlannedP3Rollback(Exception):
            pass

        for crash in ("after_t2_event", "after_t4_projection"):
            reached = []

            def fail(point):
                if point == crash:
                    reached.append(point)
                    raise PlannedP3Rollback()

            runtime_diagnostics.update(stage="p3-fault-" + crash, status=None)
            failed = None
            try:
                with testing_crash_hook(fail):
                    failed = await client.post(
                        "/games/" + game + "/sync/change",
                        headers=device_headers(pair, str(uuid4())),
                        json=p3_payload)
            except PlannedP3Rollback:
                pass
            assert reached == [crash], ("p3-fault-not-reached", crash)
            if failed is not None:
                assert failed.status_code in (500, 503), (
                    "p3-fault-response", crash, failed.status_code)
            runtime_diagnostics.update(stage="p3-fault-read-" + crash,
                                       status=None)
            rolled = await client.get(
                "/games/" + game + "/started?projection=play-prefix-v3&limit=100",
                headers=headers())
            runtime_diagnostics["status"] = rolled.status_code
            assert rolled.status_code == 200 and rolled.json() == current, (
                "p3-fault-rollback", crash, rolled.status_code)
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
        runtime_diagnostics.update(stage="p3-confirmation", status=None)
        confirmation = await client.get(
            "/games/" + game + "/sync/change-confirmation/" + str(target_d1),
            headers=headers())
        runtime_diagnostics["status"] = confirmation.status_code
        assert confirmation.status_code == 200, (
            "p3-confirmation", confirmation.status_code)
        confirmed = confirmation.json()
        assert set(confirmed) == {
            "target_reference", "confirmed_version", "d5", "source_event_id",
            "target_play_id", "stats_version_id", "current_prefix_ref",
            "current_after"}
        effective = corrected_current["page"]["items"][target_d1-1]["play_row"]
        assert str(UUID(confirmed["stats_version_id"])) == confirmed["stats_version_id"]
        assert {k: v for k, v in confirmed.items() if k != "stats_version_id"} == {
            "target_reference": offer["target_reference"],
            "confirmed_version": 2,
            "d5": change["d5"],
            "source_event_id": effective["source_event_id"],
            "target_play_id": effective["id"],
            "current_prefix_ref": corrected_current["prefix_ref"],
            "current_after": corrected_current["after"],
        }
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
        runtime_diagnostics.update(stage="foreign-login", status=None)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as foreign_client:
            foreign_login = await login(foreign_client, case["other_team_name"])
            runtime_diagnostics["status"] = foreign_login.status_code
            assert foreign_login.status_code == 200, (
                "foreign-login", foreign_login.status_code)
            foreign_headers = headers()
            foreign_headers["X-Pitchlog-Expected-Tenant"] = (
                case["other_tenant_id"])
            runtime_diagnostics.update(stage="foreign-read", status=None)
            denied_read = await foreign_client.get(
                "/games/" + game + "/started?projection=play-prefix-v3&limit=100",
                headers=foreign_headers)
            runtime_diagnostics["status"] = denied_read.status_code
            assert denied_read.status_code == 404, (
                "foreign-read", denied_read.status_code)
            assert not {"after", "runners", "prefix_ref", "page"} & set(
                denied_read.json())
            enrolled_foreign = await foreign_client.post(
                "/devices/enroll", headers=foreign_headers)
            assert enrolled_foreign.status_code == 200, (
                "foreign-enroll", enrolled_foreign.status_code)
            foreign_device = device_headers(enrolled_foreign.json(), str(uuid4()))
            foreign_device["X-Pitchlog-Expected-Tenant"] = (
                case["other_tenant_id"])
            runtime_diagnostics.update(stage="foreign-p3-replay", status=None)
            denied_replay = await foreign_client.post(
                "/games/" + game + "/sync/change",
                headers=foreign_device, json=p3_payload)
            runtime_diagnostics["status"] = denied_replay.status_code
            assert denied_replay.status_code == 404, (
                "foreign-p3-replay", denied_replay.status_code)
            assert "confirmedContent" not in denied_replay.json()
        runtime_diagnostics.update(stage="owner-final-get", status=None)
        owner_again = await client.get(
            "/games/" + game + "/started?projection=play-prefix-v3&limit=100",
            headers=headers())
        runtime_diagnostics["status"] = owner_again.status_code
        assert owner_again.status_code == 200 and owner_again.json() == current, (
            "owner-final-get", owner_again.status_code)
        runtime_diagnostics.update(stage="complete", status=200)
        from pitchlog.authz import p3_projection_sql as actual_p3_sql
        from pitchlog.repositories import past_correction_source as actual_p3_source
        return {"game": game, "change": changed.json(),
                "negative_d5s": negative_d5s,
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


def _t5_changing_p3_script() -> str:
    """既同一driverで三振最終球をballへ改め、T5寄与差を実測する。"""
    script = _three_ball_p3_script()

    def once(old: str, new: str) -> None:
        nonlocal script
        assert script.count(old) == 1, old
        script = script.replace(old, new, 1)

    third_start = script.index(
        '        for index, result in enumerate(["batting-result.ball"], 3):'
    )
    third_end = script.index(
        '        runtime_diagnostics.update(stage="foreign-login"', third_start
    )
    third = script[third_start:third_end]
    script = script[:third_start] + script[third_end:]
    third = third.replace(
        'enumerate(["batting-result.ball"], 3)',
        'enumerate(["batting-result.called-strikeout"], 3)',
        1,
    )
    once(
        'results = ["batting-result.ball", "batting-result.called-pitch"]',
        'results = ["batting-result.called-pitch", "batting-result.called-pitch"]',
    )
    once(
        '        target = current["page"]["items"][0]["play_row"]',
        third + '        target = current["page"]["items"][2]["play_row"]',
    )
    once("        target_d1 = 1", "        target_d1 = 3")
    once(
        '"originalResultId": "batting-result.ball"',
        '"originalResultId": "batting-result.called-strikeout"',
    )
    once(
        '"replacementResultId": "batting-result.called-pitch"',
        '"replacementResultId": "batting-result.ball"',
    )
    once(
        'corrected_current["page"]["items"][0]["play_row"]["id"]',
        'corrected_current["page"]["items"][2]["play_row"]["id"]',
    )
    once(
        'conflict_payload["change"]["payload"]["replacementResultId"] = (\n'
        '            "batting-result.ball")',
        'conflict_payload["change"]["payload"]["replacementResultId"] = (\n'
        '            "batting-result.called-strikeout")',
    )
    return script


def test_owned_candidate_actual_http_p3(vertical_database) -> None:
    """候補DDL/本文をowned実DBへ適用し、真正開始後のHTTP訂正を検査する。"""
    test_owned_candidate_0048_compiles(vertical_database)
    db = vertical_database
    control_catalog = subprocess.run(
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
            "-A",
            "-t",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "binding_control_fixture",
            "-c",
            """
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'signature', p.oid::regprocedure::text,
                'owner', pg_get_userbyid(p.proowner),
                'definer', p.prosecdef,
                'volatile', p.provolatile,
                'language', l.lanname,
                'path', to_jsonb(p.proconfig),
                'result', pg_get_function_result(p.oid),
                'actor', has_function_privilege(
                    'pitchlog_sync_binding_actor', p.oid, 'EXECUTE'),
                'app', CASE WHEN to_regrole('pitchlog_app') IS NULL THEN false
                    ELSE has_function_privilege(
                        to_regrole('pitchlog_app'), p.oid, 'EXECUTE') END,
                'unexpectedGrant', EXISTS (
                    SELECT FROM aclexplode(
                        COALESCE(p.proacl, acldefault('f', p.proowner))) AS acl
                    WHERE acl.privilege_type = 'EXECUTE'
                      AND acl.grantee NOT IN (
                          p.proowner,
                          (SELECT oid FROM pg_roles
                           WHERE rolname = 'pitchlog_sync_binding_actor'))
                )
            ) ORDER BY p.proname), '[]'::jsonb)::text
            FROM pg_proc AS p
            JOIN pg_language AS l ON l.oid = p.prolang
            WHERE p.oid IN (
                to_regprocedure(
                    'sync_control.register_d1less_phase(uuid,jsonb)'),
                to_regprocedure(
                    'sync_control.read_d1less_phase(uuid,uuid,uuid)'))
            """,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert control_catalog.returncode == 0, control_catalog.stderr[-500:]
    assert json.loads(control_catalog.stdout) == [
        {
            "signature": "sync_control.read_d1less_phase(uuid,uuid,uuid)",
            "owner": "pitchlog_sync_binding_fn_owner",
            "definer": True,
            "volatile": "v",
            "language": "plpgsql",
            "path": ["search_path=pg_catalog, pg_temp"],
            "result": "TABLE(context_json text)",
            "actor": True,
            "app": False,
            "unexpectedGrant": False,
        },
        {
            "signature": "sync_control.register_d1less_phase(uuid,jsonb)",
            "owner": "pitchlog_sync_binding_fn_owner",
            "definer": True,
            "volatile": "v",
            "language": "plpgsql",
            "path": ["search_path=pg_catalog, pg_temp"],
            "result": "void",
            "actor": True,
            "app": False,
            "unexpectedGrant": False,
        },
    ]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch',"
            "'batting_result','見逃し') ON CONFLICT(key) DO NOTHING"
        )
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-strikeout',"
            "'batting_result','見逃し三振') ON CONFLICT(key) DO NOTHING"
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
        t5_process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _t5_changing_p3_script()],
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
        assert len(result["negative_d5s"]) == 3
        assert admin.execute(
            "SELECT count(*) FROM public.idempotency_ledger "
            "WHERE tenant_id=%s AND d5=ANY(%s)",
            (db.tenant_id, [UUID(value) for value in result["negative_d5s"]]),
        ).fetchone() == (0,)
        assert admin.execute(
            "SELECT count(*) FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (4,)
        assert admin.execute(
            "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (4,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (1,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsule_items "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (2,)
        current = admin.execute(
            "SELECT id,source_count FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND is_current "
            "AND invalidated_at IS NULL",
            key,
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
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone()
        assert p3 is not None and sources[0][0] == p3[0]

    try:
        t5_result = json.loads(t5_process.stdout)
    except json.JSONDecodeError:
        t5_result = {"exception": "remote-json-unavailable"}
    (_PACKET / "owned-http-t5-diagnostic.json").write_text(
        json.dumps(t5_result.get("runtime_diagnostics", {}), indent=2)
    )
    _write_stage(t5_result, _PACKET / "owned-http-t5-failure-stage.json")
    assert t5_process.returncode == 0, ("t5-remote-process", t5_process.returncode)
    assert "exception" not in t5_result, t5_result
    assert t5_result["prefix"] == "3"
    with psycopg.connect(db.authority.database.business_admin) as admin:
        key = (db.tenant_id, UUID(t5_result["game"]))
        assert len(t5_result["negative_d5s"]) == 3
        assert admin.execute(
            "SELECT count(*) FROM public.idempotency_ledger "
            "WHERE tenant_id=%s AND d5=ANY(%s)",
            (db.tenant_id, [UUID(value) for value in t5_result["negative_d5s"]]),
        ).fetchone() == (0,)
        assert admin.execute(
            "SELECT count(*) FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (4,)
        assert admin.execute(
            "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (4,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (1,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsule_items "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (3,)
        versions = admin.execute(
            "SELECT id,is_current,source_count FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND source_count=3 "
            "ORDER BY created_at",
            key,
        ).fetchall()
        assert len(versions) == 2 and [row[1] for row in versions] == [False, True]
        assert [row[2] for row in versions] == [3, 3]
        old_source = admin.execute(
            "SELECT metric_states FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s AND d1=3",
            (*key, versions[0][0]),
        ).fetchone()
        new_source = admin.execute(
            "SELECT metric_states FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s AND d1=3",
            (*key, versions[1][0]),
        ).fetchone()
        assert old_source is not None and new_source is not None
        old_metrics = old_source[0]["metrics"]
        new_metrics = new_source[0]["metrics"]
        assert old_metrics["k"]["value"] == "1"
        assert new_metrics["k"]["value"] == "0"
        assert old_metrics["pitcher_k"]["value"] == "1"
        assert new_metrics["pitcher_k"]["value"] == "0"
        current_sources = admin.execute(
            "SELECT source_event_id,d1 FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s ORDER BY d1",
            (*key, versions[1][0]),
        ).fetchall()
        assert len(current_sources) == 3
        assert [row[1] for row in current_sources] == [1, 2, 3]
        changed = admin.execute(
            "SELECT change_event_id FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone()
        assert changed is not None and current_sources[2][0] == changed[0]
