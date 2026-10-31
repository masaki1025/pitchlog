"""正式source資産だけを用いるowned PG v2保存試験。作者はPG未実行。"""

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
from .test_ordinary_pitch_vertical_http import _SCRIPT as _ORDINARY_SCRIPT
from .test_ordinary_pitch_vertical_http import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db

# 実新規作成/開始/通常3球を既writerで保存する準備は既witnessを再利用する。
# 期待をartifactから生成せず、終端の規範結果は下のassertで独立固定する。
_EXTRA = r"""
        from pitchlog.domainrt.play_prefix_continuation import (
            PlayPrefixRequest,
            PlayPrefixSuccess,
            decode_play_prefix_response,
        )
        from pitchlog.domainrt.first_pitch import StateSnapshot
        from pitchlog.sync.idempotency import source_fingerprint
        from pitchlog.sync.terminal_pitch_payload import (
            TerminalPitchCalculation,
            seal_play_prefix_metadata,
            format_terminal_pitch_payload,
        )

        for result in [terminal_result, "batting-result.ball"]:
            read = await client.get(
                "/games/" + game + "/started?projection=play-prefix-v2&limit=100",
                headers=headers(),
            )
            assert read.status_code == 200, (
                "v2-read-before",
                read.status_code,
                read.text,
            )
            current = read.json()
            roster = InitialRosterProjection.model_validate_json(
                json.dumps(current["roster"])
            )
            before = current["after"]
            roster_before = json.loads(json.dumps(before))
            roster_before["stateFields"]["state.runners"] = "empty"
            people = select_ordinary_pitch_participants(
                roster, StateSnapshot.model_validate_json(json.dumps(roster_before))
            )
            with open_domain_host() as host:
                digest = host.artifact_sha256
                prior = current["prefix_ref"]
                bridge = None
                if prior["version"] == "1":
                    ref = {
                        "version": "2",
                        "scope": "play-prefix-v2",
                        "tenantId": prior["tenantId"],
                        "gameId": game,
                        "generation": prior["generation"],
                        "length": prior["length"],
                        "checkpoint": current["bridge_checkpoint"],
                        "historyVersion": "1",
                        "origin": prior,
                    }
                    bridge = {
                        "kind": "ordinary-only-confirmed",
                        "v1Ref": prior,
                        "ordinaryPlayCount": prior["length"],
                        "allPlayCount": prior["length"],
                        "historyDepth": prior["length"],
                        "lastSource": current["last_source"],
                        "priorArtifactSha256": current["prior_artifact_sha256"],
                        "rulesDigest": source_fingerprint(current["rules"]),
                        "layoutDigest": source_fingerprint(current["roster"]),
                        "checkpoint": current["bridge_checkpoint"],
                    }
                else:
                    ref = prior
                next_batter = None
                if result in {"batting-result.walk", "batting-result.hit-by-pitch"}:
                    # このowned試験の真正開始打順1に対する規範期待2。
                    # 製品選択規則ではない。
                    next_before = json.loads(json.dumps(roster_before))
                    next_before["stateFields"]["state.battingOrder"] = "2"
                    next_people = select_ordinary_pitch_participants(
                        roster,
                        StateSnapshot.model_validate_json(json.dumps(next_before)),
                    )
                    next_batter = {
                        "batterId": next_people.batter_id,
                        "battingOrder": "2",
                    }
                d5 = str(uuid4())
                source = {
                    "kind": "bridged-v1" if bridge else "evaluated-prefix-v2",
                    "prefixRef": ref,
                    "rules": current["rules"],
                    "after": before,
                    "t2": current["t2"],
                    "historyDepth": ref["length"],
                    "playCount": ref["length"],
                    "lastSource": current["last_source"],
                    "position": {
                        **current["next_position"],
                        "appliedWatermark": str(
                            int(current["next_position"]["d1"]) - 1
                        ),
                    },
                    "priorArtifactSha256": current["prior_artifact_sha256"],
                    "executionArtifactSha256": digest,
                    "rulesDigest": source_fingerprint(current["rules"]),
                    "layoutDigest": source_fingerprint(current["roster"]),
                    "runners": current["runners"],
                    "participants": {
                        k: v
                        for k, v in people.model_dump(
                            mode="json", by_alias=True
                        ).items()
                        if k != "catcherId"
                    },
                    "nextBatter": next_batter,
                    "bridge": bridge,
                    "responsibility": {
                        "kind": "no-change",
                        "paStartSource": current["pa_start_source"],
                        "previousPitcherId": None,
                        "strikesAtChange": None,
                        "ballsAtChange": None,
                    },
                }
                request = PlayPrefixRequest.model_validate_json(
                    json.dumps(
                        {
                            "version": "2",
                            "prefixRef": ref,
                            "rules": current["rules"],
                            "t1": {
                                "eventKind": "batting-result",
                                "resultId": result,
                                "pitchEventKind": "pitch-event",
                                "before": before,
                            },
                            "source": source,
                            "playIdentity": {
                                "eventId": str(uuid4()),
                                "playId": str(uuid4()),
                                "d5": d5,
                            },
                            "nextCheckpoint": {
                                "id": str(uuid4()),
                                "revision": str(
                                    int(ref["checkpoint"]["revision"]) + 1
                                ),
                                "digest": "0" * 64,
                            },
                        }
                    )
                )
                response = decode_play_prefix_response(
                    host.call(
                        "derivePlayPrefixWithContinuation",
                        request.model_dump_json(by_alias=True, exclude_unset=True),
                    )
                )
                assert type(response) is PlayPrefixSuccess
            request, response = seal_play_prefix_metadata(request, response)
            calc = TerminalPitchCalculation.model_validate_json(
                json.dumps(
                    {
                        "formatVersion": "play-prefix-calculation-v2",
                        "artifactSha256": digest,
                        "request": request.model_dump(
                            mode="json", by_alias=True, exclude_unset=True
                        ),
                        "response": response.model_dump(
                            mode="json", by_alias=True, exclude_unset=True
                        ),
                    }
                )
            )
            v7, v8 = format_terminal_pitch_payload(obs, people, calc)
            event = {
                "game_id": game,
                "d4": started["d4"],
                "d1": int(current["next_position"]["d1"]),
                "d2": int(current["next_position"]["d2"]),
                "d5": d5,
                "event_kind": "1",
                "payload": json.loads(v7),
                "state_diff": json.loads(v8),
            }
            payload = {
                "recording_right_proof": started["recording_right_proof"],
                "events": [event],
            }
            h = device_headers(pair, str(uuid4()))
            from pitchlog.sync.crash_points import testing_crash_hook
            class PlannedV2Rollback(Exception):
                pass
            original_payload = json.dumps(payload, sort_keys=True)
            for crash_point in ("after_t2_event", "after_t4_projection"):
                reached = []
                def fail_at(point):
                    if point == crash_point:
                        reached.append(point)
                        raise PlannedV2Rollback()
                failed = None
                try:
                    with testing_crash_hook(fail_at):
                        failed = await client.post(
                            "/games/"+game+"/sync/events", headers=h, json=payload)
                except PlannedV2Rollback:
                    pass
                assert reached == [crash_point]
                if failed is not None:
                    assert failed.status_code in (500, 503)
                rolled_back = await client.get(
                    "/games/"+game+"/started?projection=play-prefix-v2&limit=100",
                    headers=headers())
                assert rolled_back.status_code == 200
                assert rolled_back.json() == current
                assert json.dumps(payload, sort_keys=True) == original_payload
                # 同D5/同本文/同予約IDは維持し、失効attemptだけを新しい実借用にする。
                h = device_headers(pair, str(uuid4()))
            posted = await client.post(
                "/games/" + game + "/sync/events", headers=h, json=payload
            )
            assert posted.status_code == 200, (
                "v2-save",
                posted.status_code,
                posted.text,
                runtime_diagnostics,
            )
            assert posted.json()["eventResults"][0]["a5Result"] == "受理"
            replay = await client.post(
                "/games/" + game + "/sync/events", headers=h, json=payload
            )
            assert (
                replay.status_code == 200
                and replay.json()["eventResults"][0]["a5Result"] == "重複"
            )
            saved = await client.get(
                "/games/" + game + "/started?projection=play-prefix-v2&limit=100",
                headers=headers(),
            )
            assert saved.status_code == 200, (
                "v2-saved",
                saved.status_code,
                saved.text,
            )
            snapshot = saved.json()
            sf = snapshot["after"]["stateFields"]
            assert (
                sf["state.battingOrder"] == "2" and sf["state.runners"] == "first"
            )
            assert sf["state.count.strikes"] == "0"
            assert sf["state.count.balls"] == (
                "0" if result == terminal_result else "1"
            )
            assert len(snapshot["runners"]) == 1
            assert len(snapshot["page"]["items"][-1]["play_runners"]) == (
                0 if result == terminal_result else 1
            )
            if result == terminal_result:
                assert (
                    snapshot["runners"][0]["runnerId"]
                    == request.source.participants.batter_id
                )
            assert (
                snapshot["storage_anchor"]["id"]
                != snapshot["prefix_ref"]["checkpoint"]["id"]
            )
            previous_d5.append(d5)
        return {
            "game": game,
            "prefix": snapshot["prefix_ref"]["length"],
            "d5s": previous_d5,
            "history": len(snapshot["page"]["items"]),
            "after": snapshot["after"]["stateFields"],
        }
"""


def _script(result):
    """既3球の末尾へ本単位だけを追加する。過去witness本文は編集しない。"""
    setup = _ORDINARY_SCRIPT.replace(
        '"batting-result.called-pitch",', '"batting-result.ball",'
    )
    setup = setup.replace(
        'fields["state.count.balls"] == "2" and fields["state.count.strikes"] == "1"',
        'fields["state.count.balls"] == "3" and fields["state.count.strikes"] == "0"',
    )
    marker = '        return {\n            "game": game,'
    assert setup.count(marker) == 1
    start = setup.index(marker)
    end = setup.index("\n\n\ntry:", start)
    return (
        "terminal_result=" + repr(result) + "\n" + setup[:start] + _EXTRA + setup[end:]
    )


@pytest.mark.parametrize(
    "terminal_result", ["batting-result.walk", "batting-result.hit-by-pitch"]
)
def test_actual_owned_terminal_then_ordinary_and_original_d5(
    vertical_database, terminal_result, admin_connection, tested_role_connection
):
    """実HTTP/同TX/GETでBB/HBP後の次打者と同D5再送を照合する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
            (terminal_result, "四球" if terminal_result.endswith("walk") else "死球"),
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
            ["docker", *_app_arguments(db, case), "-u", "-c", _script(terminal_result)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    assert process.returncode == 0, (process.stdout[-1000:], process.stderr[-1000:])
    result = json.loads(process.stdout)
    assert "exception" not in result, result
    assert result["prefix"] == "5" and result["history"] == 5
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for table in ("operation_events", "play_rows"):
            assert admin.execute(
                f"SELECT count(*) FROM public.{table} "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, UUID(result["game"])),
            ).fetchone() == (5,)
        assert admin.execute(
            "SELECT count(*) FROM public.play_runners r JOIN public.play_rows p "
            "ON (p.tenant_id,p.id)=(r.tenant_id,r.play_id) "
            "WHERE p.tenant_id=%s AND p.game_id=%s",
            (db.tenant_id, UUID(result["game"])),
        ).fetchone() == (1,)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.ordinary_pitch_history "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, UUID(result["game"])),
        ).fetchone() == (5,)
