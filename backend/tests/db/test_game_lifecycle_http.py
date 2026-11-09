"""実app/owned PGの新規試合終了再開縦断。作者は収集のみでPG実行しない。"""

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
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import admin_connection as admin_connection
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)
from .test_ordinary_pitch_vertical_http import _SCRIPT as _ORDINARY_SCRIPT

pytestmark = pytest.mark.requires_db

# 実create/start/通常球送信は既縦断と同じ製品部品を使う。ループを一球に制限する。
_BOOTSTRAP = _ORDINARY_SCRIPT.split('        fields = current["after"]["stateFields"]')[
    0
]
_BOOTSTRAP = _BOOTSTRAP.replace(
    '                "batting-result.called-pitch",\n'
    '                "batting-result.ball",\n',
    "",
    1,
)

_SCRIPT = (
    _BOOTSTRAP
    + r"""

        import copy
        from pitchlog.domainrt.lineup_play_prefix_continuation import (
            decode_nonplay_lineup_prefix_request,
            evaluate_nonplay_lineup_prefix_continuation,
        )
        from pitchlog.sync.terminal_pitch_payload import (
            NonplayPitchCalculation,
            LineupPitchPlayPayload,
        )
        from pitchlog.sync import lifecycle_prefix_bridge

        async def read_full():
            # 有限pageを全て取得し、別anchor/欠落/重複をsourceへ補完しない。
            packet = None
            frames = []
            cursor = None
            cursors = set()
            while True:
                params = {"projection": "lifecycle-prefix-v1", "limit": 25}
                if cursor is not None:
                    assert cursor not in cursors
                    cursors.add(cursor)
                    params["cursor"] = cursor
                response = await client.get(
                    "/games/" + game + "/started", params=params, headers=headers()
                )
                assert response.status_code == 200, (
                    "lifecycle-read",
                    response.status_code,
                )
                page = response.json()
                assert page["profile"] == "nonplay-prefix-read-v1"
                assert page["lifecycle"]["status"] == page["status"]
                if packet is None:
                    packet = page
                else:
                    for key in (
                        "checkpoint",
                        "after",
                        "next_position",
                        "lifecycle",
                        "current_d4",
                    ):
                        assert page[key] == packet[key], ("page-anchor", key)
                frames.extend(page["page"]["items"])
                cursor = page["page"]["next_cursor"]
                if cursor is None:
                    break
            assert len(frames) == int(
                packet["checkpoint"]["content"]["activeDepth"]
            )
            identities = [frame["play"]["source"]["eventId"] for frame in frames]
            assert len(identities) == len(set(identities))
            return packet, frames

        async def send(body, attempt=None):
            return await client.post(
                "/games/" + game + "/sync/events",
                json=body,
                headers=device_headers(pair, attempt or str(uuid4())),
            )

        async def lifecycle(action, before):
            preceding = before["checkpoint"]["content"]["d1Head"]["source"]
            if action == "reopen":
                assert preceding["eventKind"] == "game_end_declaration"
                target = {
                    "kind": "queued_end",
                    "d4": preceding["generation"],
                    "d1": int(preceding["d1"]),
                    "d5": preceding["d5"],
                    "eventId": before["lifecycle"]["active"]["eventId"],
                    "receiptId": before["lifecycle"]["active"]["receiptId"],
                }
                checkpoint_ref = {
                    "kind": "queued_predecessor",
                    "d4": preceding["generation"],
                    "d1": int(preceding["d1"]),
                    "d5": preceding["d5"],
                }
            else:
                target = None
                checkpoint_ref = {"kind": "confirmed", **before["checkpoint"]["ref"]}
            event = {
                "game_id": game,
                "d4": before["current_d4"],
                "d1": int(before["next_position"]["d1"]),
                "d2": int(before["next_position"]["d2"]),
                "d5": str(uuid4()),
                "event_kind": "game_end_declaration"
                if action == "end"
                else "game_reopen",
                "payload": {
                    "formatVersion": "native-game-lifecycle-v1",
                    "action": action,
                    "checkpointRef": checkpoint_ref,
                    "target": target,
                    "event": {"eventId": str(uuid4()), "receiptId": str(uuid4())},
                },
            }
            body = {
                "recording_right_proof": started["recording_right_proof"],
                "events": [event],
            }
            attempt = str(uuid4())
            response = await send(body, attempt)
            assert response.status_code == 200, (action, response.status_code)
            assert response.json()["eventResults"][0]["a5Result"] == "受理", action
            after, _ = await read_full()
            for replay_attempt in (attempt, str(uuid4())):
                replay = await send(body, replay_attempt)
                assert replay.status_code == 200, (
                    "replay",
                    action,
                    replay.status_code,
                )
                assert replay.json()["eventResults"][0]["a5Result"] == "重複"
                replayed, _ = await read_full()
                for key in ("checkpoint", "after", "next_position", "lifecycle"):
                    assert replayed[key] == after[key], ("replay-increased", key)
            return after, event["d5"]

        async def additional_play():
            current, frames = await read_full()
            assert current["status"] == "in_progress"
            cp = current["checkpoint"]
            request = decode_nonplay_lineup_prefix_request(
                json.dumps(
                    {
                        "version": "nonplay-continuation-v1",
                        "prefixRef": cp["ref"],
                        "rules": cp["content"]["restored"]["rules"],
                        "t1": {
                            "eventKind": "batting-result",
                            "resultId": "batting-result.ball",
                            "pitchEventKind": "pitch-event",
                            "before": current["after"],
                        },
                        "source": {
                            "formatVersion": "nonplay-prefix-source-v1",
                            "checkpoint": cp,
                            "activeStack": frames,
                        },
                        "sourcePosition": {
                            "d1": current["next_position"]["d1"],
                            "d2": current["next_position"]["d2"],
                            "appliedWatermark": cp["content"]["d3"],
                        },
                        "playIdentity": {
                            "eventId": str(uuid4()),
                            "d5": str(uuid4()),
                            "playId": str(uuid4()),
                        },
                        "nextCheckpoint": {
                            "id": str(uuid4()),
                            "revision": str(int(cp["ref"]["revision"]) + 1),
                            "digest": "f" * 64,
                        },
                    }
                )
            )
            response = evaluate_nonplay_lineup_prefix_continuation(request)
            assert response.ok is True
            calc = NonplayPitchCalculation.model_validate_json(
                json.dumps(
                    {
                        "formatVersion": "nonplay-prefix-calculation-v1",
                        "artifactSha256": cp["content"]["executionArtifactSha256"],
                        "request": request.model_dump(
                            mode="json", by_alias=True, exclude_unset=True
                        ),
                        "response": response.model_dump(
                            mode="json", by_alias=True, exclude_unset=True
                        ),
                    }
                )
            )
            payload = LineupPitchPlayPayload.model_validate_json(
                json.dumps(
                    {
                        "formatVersion": "play-prefix-play-v3",
                        "observations": {
                            "pitchTypeKey": case["pitch_type"],
                            "course": {"unit": "1/263", "x": "100", "y": "150"},
                            "pitchSpeed": {
                                "kmh": None,
                                "outsideRangeConfirmed": False,
                            },
                            "stance": None,
                            "battingSide": None,
                        },
                        "participants": response.value.before_participants.model_dump(
                            mode="json", by_alias=True
                        ),
                        "calculation": calc.model_dump(
                            mode="json", by_alias=True, exclude_unset=True
                        ),
                    }
                )
            )
            event = {
                "game_id": game,
                "d4": current["current_d4"],
                "d1": int(current["next_position"]["d1"]),
                "d2": int(current["next_position"]["d2"]),
                "d5": request.play_identity.d5,
                "event_kind": "play_input",
                "payload": payload.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
                "state_diff": response.value.new_history_entry.difference.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
            }
            posted = await send(
                {
                    "recording_right_proof": started["recording_right_proof"],
                    "events": [event],
                }
            )
            assert posted.status_code == 200, (
                "additional-play",
                posted.status_code,
            )
            assert posted.json()["eventResults"][0]["a5Result"] == "受理"
            actual, _ = await read_full()
            assert actual["after"] == response.value.t1.after.model_dump(
                mode="json", by_alias=True
            )
            return actual

        current, _ = await read_full()
        assert current["lifecycle"]["lastVersion"] == "0"
        ended, end_d5 = await lifecycle("end", current)
        assert (
            ended["status"] == "finished"
            and ended["lifecycle"]["lastVersion"] == "1"
        )
        reopened, reopen_d5 = await lifecycle("reopen", ended)
        assert (
            reopened["status"] == "in_progress"
            and reopened["lifecycle"]["active"] is None
        )
        assert reopened["lifecycle"]["lastVersion"] == "1"
        for expected_balls in ("2", "3"):
            current = await additional_play()
            assert (
                current["after"]["stateFields"]["state.count.balls"]
                == expected_balls
            )

        # 正規prepare/consume/CP/head/stats更新を全て実行した後、例外だけを注入する。
        # 成功応答・資格・SQLを差し替えず、実HTTPの同TX全rollbackを検査する。
        prior = copy.deepcopy(current)
        original_project = lifecycle_prefix_bridge.project_game_lifecycle
        fault_seen = []

        def fail_after_actual_project(*args, **kwargs):
            original_project(*args, **kwargs)
            fault_seen.append(True)
            raise RuntimeError("planned lifecycle rollback")

        lifecycle_prefix_bridge.project_game_lifecycle = fail_after_actual_project
        fault_d5 = str(uuid4())
        try:
            fault = await send(
                {
                    "recording_right_proof": started["recording_right_proof"],
                    "events": [
                        {
                            "game_id": game,
                            "d4": prior["current_d4"],
                            "d1": int(prior["next_position"]["d1"]),
                            "d2": int(prior["next_position"]["d2"]),
                            "d5": fault_d5,
                            "event_kind": "game_end_declaration",
                            "payload": {
                                "formatVersion": "native-game-lifecycle-v1",
                                "action": "end",
                                "checkpointRef": {
                                    "kind": "confirmed",
                                    **prior["checkpoint"]["ref"],
                                },
                                "target": None,
                                "event": {
                                    "eventId": str(uuid4()),
                                    "receiptId": str(uuid4()),
                                },
                            },
                        }
                    ],
                }
            )
            assert fault.status_code == 503, ("fault", fault.status_code)
            assert fault_seen == [True], "正規consume後の故障点まで到達していない"
        finally:
            lifecycle_prefix_bridge.project_game_lifecycle = original_project
        rolled_back, _ = await read_full()
        for key in ("checkpoint", "after", "next_position", "lifecycle"):
            assert rolled_back[key] == prior[key], ("rollback", key)
        final, reend_d5 = await lifecycle("end", rolled_back)
        assert (
            final["status"] == "finished"
            and final["lifecycle"]["lastVersion"] == "2"
        )
        assert (
            final["lifecycle"]["active"]["eventId"]
            != ended["lifecycle"]["active"]["eventId"]
        )
        assert (
            final["lifecycle"]["activeStatsVersionId"]
            != ended["lifecycle"]["activeStatsVersionId"]
        )
        reload, _ = await read_full()
        for key in ("checkpoint", "after", "next_position", "lifecycle"):
            assert reload[key] == final[key], ("reload", key)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as foreign:
            logged = await login(foreign, case["other_team_name"])
            assert logged.status_code == 200
            foreign_headers = {
                "Origin": "https://test",
                "X-Pitchlog-Request": "1",
                "X-Pitchlog-Expected-Tenant": case["other_tenant"],
                "X-Pitchlog-Tenant-Challenge": str(uuid4()),
            }
            invisible = await foreign.get(
                "/games/" + game + "/started?projection=lifecycle-prefix-v1",
                headers=foreign_headers,
            )
            assert invisible.status_code == 404, ("foreign", invisible.status_code)
        return {
            "game": game,
            "version": reload["lifecycle"]["lastVersion"],
            "balls": reload["after"]["stateFields"]["state.count.balls"],
            "fault_d5": fault_d5,
            "controls": [end_d5, reopen_d5, reend_d5],
        }

try:
    out = asyncio.run(run())
except BaseException:
    out = {
        "exception_type": type(sys.exc_info()[1]).__name__,
        "runtime_diagnostics": runtime_diagnostics,
        "frames": [(f.name, f.lineno) for f in traceback.extract_tb(sys.exc_info()[2])],
    }
print(json.dumps(out))
"""
)


@pytest.mark.skip(
    reason="v2 lifecycle read is superseded by the v3 end/reopen/append/re-end test"
)
def test_new_game_end_reopen_two_play_reend_reload_and_atomic_fault(vertical_database):
    """root正式asset接合後、実認可/同D5/別tenant/同TX取消を実appで確認する。"""
    db = vertical_database
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
        "other_tenant": str(db.other_tenant_id),
        "other_team_name": db.other_team_name,
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
    # 資格/実原値/任意例外メッセージをpytestログへ出さない。
    assert process.returncode == 0, "実app workerが異常終了しました"
    result = json.loads(process.stdout)
    assert "exception_type" not in result, result
    assert result["game"] != str(db.game_id)
    assert result["version"] == "2" and result["balls"] == "3"
    with psycopg.connect(db.authority.database.business_admin) as admin:
        params = (db.tenant_id, UUID(result["game"]))
        assert admin.execute(
            "SELECT count(*) FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s",
            params,
        ).fetchone() == (6,)
        assert admin.execute(
            "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s AND game_id=%s",
            params,
        ).fetchone() == (3,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.lifecycle_write_admissions "
            "WHERE tenant_id=%s AND game_id=%s AND state='consumed'",
            params,
        ).fetchone() == (3,)
        assert admin.execute(
            "SELECT last_version,is_finished FROM sync_fence.game_lifecycle_heads "
            "WHERE tenant_id=%s AND game_id=%s",
            params,
        ).fetchone() == (2, True)
        # 通常球3件とcontrol3件だけが版を発行し、故障consumeの孤立版を残さない。
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s",
            params,
        ).fetchone() == (6,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.stats_fact_versions v "
            "JOIN sync_fence.game_lifecycle_heads h ON "
            "(h.tenant_id,h.game_id,h.active_stats_version_id)="
            "(v.tenant_id,v.game_id,v.id) WHERE v.tenant_id=%s AND v.game_id=%s "
            "AND v.is_current AND v.invalidated_at IS NULL "
            "AND v.completion_state='confirmed_ended' "
            "AND v.completion_receipt_id=h.active_receipt_id "
            "AND v.public_pointer_receipt_id=h.active_receipt_id",
            params,
        ).fetchone() == (1,)
        fault = (db.tenant_id, UUID(result["fault_d5"]))
        for statement in (
            "SELECT count(*) FROM public.operation_events WHERE tenant_id=%s AND d5=%s",
            "SELECT count(*) FROM public.idempotency_ledger "
            "WHERE tenant_id=%s AND d5=%s",
            "SELECT count(*) FROM sync_fence.lifecycle_write_admissions "
            "WHERE tenant_id=%s AND d5=%s",
        ):
            assert admin.execute(statement, fault).fetchone() == (0,)
