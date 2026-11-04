"""新規POST作成/開始から無走者4安打を既sameTXの実PGへ保存する。"""

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
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import admin_connection as admin_connection
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)
from .test_ordinary_pitch_vertical_http import vertical_database as vertical_database
from .test_terminal_pitch_storage import _lineup_script

pytestmark = pytest.mark.requires_db

_RESULTS = [
    "batting-result.single",
    "batting-result.double",
    "batting-result.triple",
    "batting-result.home-run",
]


def _replace_once(script, old, new):
    """共通witnessの固定点変更を検知し、別試験の期待を黙って緩めない。"""
    assert script.count(old) == 1
    return script.replace(old, new, 1)


def _batted_script():
    """既実認証/作成/開始/queue/原子性witnessを新しい2球系列へ再利用する。"""
    script = _lineup_script()
    begin = script.index("        results = [")
    end = script.index("        for index, result in enumerate(results, 1):", begin)
    script = (
        script[:begin]
        + '        results = [case["hit_result"], "batting-result.ball"]\n'
        + script[end:]
    )
    script = _replace_once(
        script,
        '                                "before": current["after"],',
        """                                "before": current["after"],
                                **({
                                    "officialScoringPayload": "no-error",
                                    "interferenceRuling": "not-required",
                                    "runnerAdvanceOverrides": "not-applied",
                                    "thirdOutObservation": "none",
                                } if index == 1 else {}),""",
    )
    script = _replace_once(
        script,
        "                v7 = {",
        """
                before_people = (
                    response.value.before_participants.model_dump(
                        mode="json", by_alias=True
                    )
                )
                observation = {
                    "pitchTypeKey": case["pitch_type"],
                    "course": {"unit": "1/263", "x": "100", "y": "150"},
                    "pitchSpeed": {
                        "kmh": None,
                        "outsideRangeConfirmed": False,
                    },
                    "stance": None,
                    "battingSide": None,
                }
                if index == 1:
                    field_team = next(
                        t
                        for t in current["roster"]["teams"]
                        if t["side"] == "home"
                    )
                    fielder = next(
                        p["player"]["player_id"]
                        for p in field_team["participants"]
                        if any(
                            r["kind"] == "fielding" and r["position"] == "9"
                            for r in p["roles"]
                        )
                    )
                    ball = {
                        "typeKey": "batted.fixture.line",
                        "strengthKey": "batted.fixture.hard",
                        "hitX": "0.25",
                        "hitY": "0.75",
                        "rawFielderPosition": "9",
                        "resolvedFielderId": fielder,
                    }
                    if case.get("nullable"):
                        ball = {key: None for key in ball}
                    damage = case.get("damage")
                    if damage == "wrong-category":
                        ball["typeKey"] = "batted.fixture.season"
                    elif damage == "disabled":
                        ball["strengthKey"] = "batted.fixture.disabled"
                    elif damage == "foreign-vocab":
                        observation["pitchTypeKey"] = (
                            "batted.fixture.other-pitch"
                        )
                    elif damage == "foreign-player":
                        ball["resolvedFielderId"] = case["foreign_player"]
                    elif damage == "offense-player":
                        ball["resolvedFielderId"] = current["lineup"][
                            "away"
                        ]["pitcherId"]
                    elif damage == "dh-player":
                        ball["resolvedFielderId"] = next(
                            p["player"]["player_id"]
                            for p in field_team["participants"]
                            if all(
                                r["kind"] != "fielding" for r in p["roles"]
                            )
                        )
                    observation.update(
                        {
                            "resultId": result,
                            "battedBall": ball,
                            "officialScoringPayload": {
                                "kind": "no-error",
                                "errorCount": "0",
                                "fielders": [],
                            },
                            "interferenceRuling": {"kind": "not-required"},
                            "runnerAdvanceOverridesByRunner": {
                                "kind": "not-applied",
                                "overrides": [],
                            },
                            "thirdOutObservation": {"kind": "none"},
                            "thirdOutTimingByRunner": {},
                        }
                    )
                v7 = {
""",
    )
    begin = script.index(
        '                    "observations": {', script.index("        results = [")
    )
    end = script.index('                    "participants":', begin)
    script = (
        script[:begin]
        + '                    "observations": observation,\n'
        + script[end:]
    )
    script = _replace_once(
        script,
        "            if index in (1, 9):",
        '            if index == 1 and not case.get("damage"):',
    )
    script = _replace_once(
        script,
        "            posted = await client.post(",
        """
            if case.get("damage"):
                refused = await client.post(
                    "/games/" + game + "/sync/events",
                    headers=h,
                    json=payload,
                )
                assert refused.status_code in (409, 422, 500, 503), (
                    "batted-refusal",
                    refused.status_code,
                    runtime_diagnostics,
                )
                assert all(
                    x.get("a5Result") not in ("受理", "重複")
                    for x in refused.json().get("eventResults", [])
                )
                assert runtime_diagnostics.get("sqlstate") == "42501", (
                    runtime_diagnostics
                )
                assert (
                    runtime_diagnostics.get("fixed_sql_error")
                    == "batted hit physical source rejected"
                ), runtime_diagnostics
                rolled = await client.get(
                    "/games/"
                    + game
                    + "/started?projection=play-prefix-v3&limit=100",
                    headers=headers(),
                )
                assert (
                    rolled.status_code == 200
                    and rolled.json() == current
                )
                return {
                    "game": game,
                    "refused": True,
                    "status": refused.status_code,
                    "d5s": [d5],
                }
            posted = await client.post(
""",
    )
    begin = script.index("            if index == 9:")
    end = script.index("        reload = await client.get(", begin)
    script = (
        script[:begin]
        + """
            sf = current["after"]["stateFields"]
            result = case["hit_result"]
            expected_base = {
                "batting-result.single": "1",
                "batting-result.double": "2",
                "batting-result.triple": "3",
            }.get(result)
            expected_runner = {
                "1": "first",
                "2": "second",
                "3": "third",
            }.get(expected_base, "empty")
            assert sf == {
                "state.half": "top",
                "state.count.strikes": "0",
                "state.count.balls": "0" if index == 1 else "1",
                "state.outs": "0",
                "state.runners": expected_runner,
                "state.battingOrder": "2",
                "state.tiebreakActive": False,
                "state.gameEnded": False,
                "state.inning": "1",
                "state.score": {
                    "home": "0",
                    "away": "1"
                    if result == "batting-result.home-run"
                    else "0",
                },
            }
            assert current["after"]["scoreboard"] == {
                "inningScores": sf["state.score"],
                "hits": "1",
                "errors": "0",
                "strikeouts": "0",
                "walks": "0",
            }
            assert current["after"]["battingOrderBySide"] == {
                "away": "2",
                "home": "1",
            }
            first = current["page"]["items"][0]
            assert first["play_runners"] == []
            row = first["play_row"]
            assert (
                row["event_kind"] == "pitch"
                and row["batting_result_key"] == result
            )
            expected_ball = (
                v7["observations"]["battedBall"]
                if index == 1
                else saved_ball
            )
            assert (
                row["raw_fielder_position"]
                == expected_ball["rawFielderPosition"]
            )
            assert (
                row["resolved_fielder_id"]
                == expected_ball["resolvedFielderId"]
            )
            assert row["batted_ball_type"] == expected_ball["typeKey"]
            assert (
                row["batted_ball_strength"]
                == expected_ball["strengthKey"]
            )
            assert row["hit_x"] == (
                None if case.get("nullable") else 0.25
            )
            assert row["hit_y"] == (
                None if case.get("nullable") else 0.75
            )
            if index == 1:
                saved_ball = v7["observations"]["battedBall"]
            if expected_base is None:
                assert current["runners"] == []
                assert (
                    current["page"]["items"][-1]["play_runners"] == []
                )
            else:
                initial_player = current["lineup"]["away"][
                    "battingOrder"
                ]["1"]
                pitcher = current["lineup"]["home"]["pitcherId"]
                assert current["runners"] == [
                    {
                        "runnerId": initial_player,
                        "responsiblePitcherId": pitcher,
                        "base": expected_base,
                        "status": "継続",
                        "statusSource": "auto",
                    }
                ]
                physical = current["page"]["items"][-1]["play_runners"]
                if index == 2:
                    assert len(physical) == 1
                    assert physical[0]["runner_id"] == initial_player
                    assert (
                        physical[0]["responsible_pitcher_id"] == pitcher
                    )
                    assert physical[0]["base"] == int(expected_base)
"""
        + script[end:]
    )
    script = _replace_once(
        script,
        "            previous_d5.append(d5)",
        """
            replay_new_attempt = await client.post(
                "/games/" + game + "/sync/events",
                headers=device_headers(pair, str(uuid4())), json=payload,
            )
            assert replay_new_attempt.status_code == 200
            assert replay_new_attempt.json()["eventResults"][0]["a5Result"] == "重複"
            previous_d5.append(d5)""",
    )
    return script


def _setup(db):
    """参照語彙/他tenant選手を投入し、対象game/play/event/権利は実APIで生成する。"""
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for result in _RESULTS:
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (result, result),
            )
        for key, category, disabled in [
            ("batted.fixture.line", "batted_ball", False),
            ("batted.fixture.hard", "batted_ball", False),
            ("batted.fixture.disabled", "batted_ball", True),
            ("batted.fixture.season", "season", False),
        ]:
            admin.execute(
                "INSERT INTO public.admin_vocabularies("
                "key,category,display_name,disabled) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, category, key, disabled),
            )
        admin.execute(
            "INSERT INTO public.tenant_vocabularies(tenant_id,key,category,"
            "display_name,pitch_family) VALUES (%s,'batted.fixture.other-pitch',"
            "'pitch_type','他tenantの球種','fastball') "
            "ON CONFLICT(tenant_id,key) DO NOTHING",
            (db.other_tenant_id,),
        )
        # 越境拒否は実在する他tenant選手で検査する。対象試合には登録しない。
        foreign_team = UUID("00000000-0000-4000-8000-00000000b401")
        foreign_player = UUID("00000000-0000-4000-8000-00000000b402")
        admin.execute(
            "INSERT INTO public.team_records(tenant_id,id,kind,name) "
            "VALUES (%s,%s,'self','打球保存試験の他tenantチーム')",
            (db.other_tenant_id, foreign_team),
        )
        admin.execute(
            "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
            "roster_status_key) VALUES (%s,%s,%s,'他tenantの実在選手','active')",
            (db.other_tenant_id, foreign_player, foreign_team),
        )
        player = admin.execute(
            "SELECT id FROM public.players WHERE tenant_id=%s LIMIT 1",
            (db.other_tenant_id,),
        ).fetchone()
    assert player is not None
    return {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "other_team_name": db.other_team_name,
        "other_tenant_id": str(db.other_tenant_id),
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
        "foreign_player": str(player[0]),
    }


def _execute(db, case):
    """既公開試験資格で実app/固定host/正式SQLへ接続する。"""
    process = subprocess.run(
        ["docker", *_app_arguments(db, case), "-u", "-c", _batted_script()],
        capture_output=True,
        text=True,
        timeout=400,
    )
    assert process.returncode == 0, (process.stdout[-1200:], process.stderr[-1200:])
    result = json.loads(process.stdout)
    assert "exception" not in result, json.dumps(result, ensure_ascii=False)
    assert result["game"] != str(db.game_id)
    return result


def test_owned_four_hits_next_pitch_replay_atomicity_reload_and_foreign_rejection(
    vertical_database,
):
    """実作成4試合で安打4種/次球/再送/原子性/越境/再取得の全値を照合する。"""
    db = vertical_database
    base = _setup(db)
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        results = [
            _execute(
                db,
                {
                    **base,
                    "hit_result": result,
                    "nullable": result == "batting-result.home-run",
                },
            )
            for result in _RESULTS
        ]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for result in results:
            assert result["prefix"] == "2" and result["history"] == 2
            for table in ("operation_events", "play_rows", "event_slots"):
                assert admin.execute(
                    f"SELECT count(*) FROM public.{table} "
                    "WHERE tenant_id=%s AND game_id=%s",
                    (db.tenant_id, UUID(result["game"])),
                ).fetchone() == (2,)
            assert admin.execute(
                "SELECT count(*) FROM sync_fence.ordinary_pitch_history "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, UUID(result["game"])),
            ).fetchone() == (2,)
            assert admin.execute(
                "SELECT confirmed_watermark,applied_prefix "
                "FROM public.recording_generations "
                "WHERE tenant_id=%s AND game_id=%s AND generation=1",
                (db.tenant_id, UUID(result["game"])),
            ).fetchone() == (2, 2)


def test_owned_bad_vocabulary_and_fielding_membership_rollback_without_success(
    vertical_database,
):
    """真正な同要求経路で語彙区分/無効/越境/攻撃側/DHを拒否し全取消を観測する。"""
    db = vertical_database
    base = _setup(db)
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        results = [
            _execute(db, {**base, "hit_result": _RESULTS[0], "damage": reason})
            for reason in (
                "wrong-category",
                "disabled",
                "foreign-vocab",
                "foreign-player",
                "offense-player",
                "dh-player",
            )
        ]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for result in results:
            assert result["refused"] is True
            for table in ("operation_events", "play_rows", "event_slots"):
                assert admin.execute(
                    f"SELECT count(*) FROM public.{table} "
                    "WHERE tenant_id=%s AND game_id=%s",
                    (db.tenant_id, UUID(result["game"])),
                ).fetchone() == (0,)
            assert admin.execute(
                "SELECT count(*) FROM sync_fence.ordinary_pitch_history "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, UUID(result["game"])),
            ).fetchone() == (0,)
            assert admin.execute(
                "SELECT count(*) FROM sync_fence.ordinary_pitch_checkpoints "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, UUID(result["game"])),
            ).fetchone() == (0,)
            assert admin.execute(
                "SELECT confirmed_watermark,applied_prefix "
                "FROM public.recording_generations "
                "WHERE tenant_id=%s AND game_id=%s AND generation=1",
                (db.tenant_id, UUID(result["game"])),
            ).fetchone() == (0, 0)
            for d5 in result["d5s"]:
                assert admin.execute(
                    "SELECT count(*) FROM public.idempotency_ledger "
                    "WHERE tenant_id=%s AND d5=%s",
                    (db.tenant_id, UUID(d5)),
                ).fetchone() == (0,)
