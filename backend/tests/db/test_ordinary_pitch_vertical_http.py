"""owned実PGで新規作成/開始/通常3球/同要求再送/新GETを実API接続する。"""

import json
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _APP_SCRIPT,
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
from .test_initial_recording_right_scope import admin_connection as admin_connection
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db

_SCRIPT = (
    _APP_SCRIPT.split("async def run():")[0]
    + r"""
runtime_diagnostics = {}
from pitchlog.api.routers import sync as actual_sync_router

_actual_apply = actual_sync_router._apply_e1_f1


def traced_apply(*args, **kwargs):
    # 原値/資格をログへ出さず、閉じたHTTP失敗の実停止フレームだけを保全する。
    try:
        return _actual_apply(*args, **kwargs)
    except Exception as error:
        original = getattr(error, "orig", None)
        code = getattr(original, "sqlstate", None)
        diagnostic = getattr(original, "diag", None)
        safe_primary = (
            getattr(diagnostic, "message_primary", None)
            if code in {"42501", "42703", "42883", "42P01", "42804", "42702", "42601"}
            else None
        )
        runtime_diagnostics.update(
            exception_type=type(error).__name__,
            database_exception_type=type(original).__name__,
            sqlstate=code,
            fixed_sql_error=safe_primary,
            frames=[
                (f.name, f.lineno) for f in traceback.extract_tb(error.__traceback__)
            ],
        )
        raise


actual_sync_router._apply_e1_f1 = traced_apply


async def run():
    global game
    from pitchlog.domainrt.first_pitch import FirstPitchRequest
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.ordinary_pitch_continuation import (
        OrdinaryContinuationRequest,
        decode_ordinary_continuation_response,
    )
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
    from pitchlog.sync.first_ball_payload import FirstBallObservations
    from pitchlog.sync.ordinary_pitch_payload import (
        OrdinaryPitchCalculation,
        select_ordinary_pitch_participants,
        format_ordinary_pitch_payload,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        logged = await login(client, team)
        assert logged.status_code == 200, ("login", logged.status_code)
        preparation = await client.get("/games/" + game, headers=headers())
        assert preparation.status_code == 200, ("preparing", preparation.status_code)
        source = preparation.json()
        created = await client.post(
            "/games",
            headers=headers(),
            json={
                "scheduled_at": source["scheduled_at"],
                "game_type_key": source["game_type_key"],
                "away_team_record_id": source["away_team_record_id"],
                "home_team_record_id": source["home_team_record_id"],
                "tournament": {"kind": "existing", "key": source["tournament_key"]},
            },
        )
        assert created.status_code == 201, ("create", created.status_code, created.text)
        game = created.json()["id"]
        assert game != case["game"]
        enrolled = await client.post("/devices/enroll", headers=headers())
        assert enrolled.status_code == 200, ("enroll", enrolled.status_code)
        pair = enrolled.json()
        body = _body(10)
        body.update(
            device_id=pair["device_id"],
            device_credential=pair["device_credential"],
            start_request_id=str(uuid4()),
        )
        start = await client.post(
            "/games/" + game + "/start", json=body, headers=headers()
        )
        assert start.status_code == 200, ("start", start.status_code, start.text)
        started = start.json()
        read = await client.get(
            "/games/" + game + "/started?projection=ordinary-prefix-v1&limit=2",
            headers=headers(),
        )
        assert read.status_code == 200, ("initial-read", read.status_code, read.text)
        current = read.json()
        previous_d5 = []
        for index, result in enumerate(
            [
                "batting-result.ball",
                "batting-result.called-pitch",
                "batting-result.ball",
            ],
            1,
        ):
            t1 = {
                "eventKind": "batting-result",
                "resultId": result,
                "pitchEventKind": "pitch-event",
                "before": current["after"],
            }
            prior = {
                "kind": "started-initial" if index == 1 else "evaluated-prefix",
                "prefixRef": current["prefix_ref"],
                "rules": current["rules"],
                "after": current["after"],
                "t2": current["t2"],
            }
            request = OrdinaryContinuationRequest.model_validate_json(
                json.dumps(
                    {
                        "version": "1",
                        "prefixRef": current["prefix_ref"],
                        "rules": current["rules"],
                        "t1": t1,
                        "prior": prior,
                    }
                )
            )
            with open_domain_host() as host:
                digest = hashlib.sha256(host._source.encode()).hexdigest()
                response = decode_ordinary_continuation_response(
                    host.call(
                        "deriveOrdinaryPitchWithContinuation",
                        request.model_dump_json(by_alias=True, exclude_unset=True),
                    )
                )
            assert response.ok is True, ("calculation", index)
            calc = OrdinaryPitchCalculation(
                formatVersion="ordinary-pitch-calculation-v1",
                artifactSha256=digest,
                request=request,
                response=response,
            )
            roster = InitialRosterProjection.model_validate_json(
                json.dumps(current["roster"])
            )
            people = select_ordinary_pitch_participants(roster, request.t1.before)
            obs = FirstBallObservations.model_validate_json(
                json.dumps(
                    {
                        "pitchTypeKey": case["pitch_type"],
                        "course": {"unit": "1/263", "x": "100", "y": "150"},
                        "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                        "stance": None,
                        "battingSide": None,
                    }
                )
            )
            v7, v8 = format_ordinary_pitch_payload(obs, people, calc)
            event = {
                "game_id": game,
                "d4": started["d4"],
                "d1": int(current["next_position"]["d1"]),
                "d2": int(current["next_position"]["d2"]),
                "d5": str(uuid4()),
                "event_kind": "1",
                "payload": json.loads(v7),
                "state_diff": json.loads(v8),
            }
            payload = {
                "recording_right_proof": started["recording_right_proof"],
                "events": [event],
            }
            attempt = str(uuid4())
            h = device_headers(pair, attempt)
            posted = await client.post(
                "/games/" + game + "/sync/events", json=payload, headers=h
            )
            assert posted.status_code == 200, (
                "save",
                index,
                posted.status_code,
                posted.text,
            )
            assert posted.json()["eventResults"][0]["a5Result"] == "受理", (
                "ack",
                index,
                posted.json(),
            )
            replay = await client.post(
                "/games/" + game + "/sync/events", json=payload, headers=h
            )
            assert replay.status_code == 200, ("replay", index, replay.status_code)
            assert replay.json()["eventResults"][0]["a5Result"] == "重複"
            previous_d5.append(event["d5"])
            read = await client.get(
                "/games/" + game + "/started?projection=ordinary-prefix-v1&limit=2",
                headers=headers(),
            )
            assert read.status_code == 200, ("read", index, read.status_code, read.text)
            current = read.json()
            assert current["prefix_ref"]["length"] == str(index)
            assert current["next_position"] == {
                "d1": str(index + 1),
                "d2": str(1 + index * 1000),
            }
            assert current["checkpoint_anchor"] is not None
        fields = current["after"]["stateFields"]
        assert (
            fields["state.count.balls"] == "2" and fields["state.count.strikes"] == "1"
        )
        assert (
            len(current["page"]["items"]) == 2
            and current["page"]["next_cursor"] is not None
        )
        page2 = await client.get(
            "/games/" + game + "/started",
            params={
                "projection": "ordinary-prefix-v1",
                "limit": 2,
                "cursor": current["page"]["next_cursor"],
            },
            headers=headers(),
        )
        assert page2.status_code == 200, ("page2", page2.status_code, page2.text)
        assert len(page2.json()["page"]["items"]) == 1
        assert page2.json()["page"]["next_cursor"] is None
        reload = await client.get(
            "/games/" + game + "/started?projection=ordinary-prefix-v1",
            headers=headers(),
        )
        assert reload.status_code == 200
        assert reload.json()["after"] == current["after"]
        return {
            "game": game,
            "after": fields,
            "prefix": current["prefix_ref"]["length"],
            "d5s": previous_d5,
            "history": len(reload.json()["page"]["items"]),
        }


try:
    out = asyncio.run(run())
except BaseException:
    out = {
        "exception": traceback.format_exc().splitlines()[-1],
        "runtime_diagnostics": runtime_diagnostics,
        "frames": [(f.name, f.lineno) for f in traceback.extract_tb(sys.exc_info()[2])],
    }
print(json.dumps(out))

"""
)


def test_actual_http_create_start_three_pitches_replay_and_prefix_reload(
    vertical_database,
):
    """事前投入gameを成功対象にせず、実POST作成した別gameで3件保存する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _SCRIPT],
            capture_output=True,
            text=True,
            timeout=300,
        )
    assert process.returncode == 0, (process.stdout[-1000:], process.stderr[-1000:])
    result = json.loads(process.stdout)
    report = Path(
        "/home/ymdms/.cache/pitchlog/ordinary37-runtime-source-candidate-20261030/newAPI-last-result.json"
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    assert "exception" not in result, json.dumps(result, ensure_ascii=False)
    assert result["prefix"] == "3" and result["history"] == 3
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for table in ["operation_events", "play_rows"]:
            count = admin.execute(
                f"SELECT count(*) FROM public.{table} "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, UUID(result["game"])),
            ).fetchone()
            assert count == (3,), table
        count = admin.execute(
            "SELECT count(*) FROM sync_fence.ordinary_pitch_history "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, UUID(result["game"])),
        ).fetchone()
        assert count == (3,)
