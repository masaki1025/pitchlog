"""取消の接続spikeを、実認証・実記録権・同期核・owned PGで通す。

事前投入のplayを使わず、実POSTで試合作成・開始・通常1球保存を行い、
取消・再取得・再送・拒否・故障全取消・監査行保持を観測する。
"""

from __future__ import annotations

import json
import subprocess
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
from pitchlog.api.request_presentation import require_presented_token
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.sync.spike_undo_http import install as install_undo_spike

install_undo_spike(
    app,
    tenant_access=require_tenant_access,
    presented_token=require_presented_token,
)


def spike_headers(expected):
    value = headers()
    value['X-Pitchlog-Expected-Tenant'] = expected
    return value


async def read_spike(client, expected):
    return await client.get('/spike/games/' + game + '/state',
        headers=spike_headers(expected))


async def ordinary_save(client, started, pair, current):
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
    from pitchlog.domainrt.ordinary_pitch_continuation import (
        OrdinaryContinuationRequest,
        decode_ordinary_continuation_response,
    )
    from pitchlog.sync.first_ball_payload import FirstBallObservations
    from pitchlog.sync.ordinary_pitch_payload import (
        OrdinaryPitchCalculation,
        format_ordinary_pitch_payload,
        select_ordinary_pitch_participants,
    )

    result_id = 'batting-result.ball'
    request = OrdinaryContinuationRequest.model_validate_json(json.dumps({
        'version': '1',
        'prefixRef': current['prefix_ref'],
        'rules': current['rules'],
        't1': {
            'eventKind': 'batting-result',
            'resultId': result_id,
            'pitchEventKind': 'pitch-event',
            'before': current['after'],
        },
        'prior': {
            'kind': 'started-initial',
            'prefixRef': current['prefix_ref'],
            'rules': current['rules'],
            'after': current['after'],
            't2': current['t2'],
        },
    }))
    with open_domain_host() as host:
        digest = hashlib.sha256(host._source.encode()).hexdigest()
        response = decode_ordinary_continuation_response(host.call(
            'deriveOrdinaryPitchWithContinuation',
            request.model_dump_json(by_alias=True, exclude_unset=True)))
    assert response.ok is True
    calculation = OrdinaryPitchCalculation(
        formatVersion='ordinary-pitch-calculation-v1',
        artifactSha256=digest,
        request=request,
        response=response,
    )
    roster = InitialRosterProjection.model_validate_json(json.dumps(current['roster']))
    people = select_ordinary_pitch_participants(roster, request.t1.before)
    obs = FirstBallObservations.model_validate_json(json.dumps({
        'pitchTypeKey': case['pitch_type'],
        'course': {'unit': '1/263', 'x': '100', 'y': '150'},
        'pitchSpeed': {'kmh': None, 'outsideRangeConfirmed': False},
        'stance': None,
        'battingSide': None,
    }))
    v7, v8 = format_ordinary_pitch_payload(obs, people, calculation)
    d5 = str(uuid4())
    event = {
        'game_id': game,
        'd4': started['d4'],
        'd1': int(current['next_position']['d1']),
        'd2': int(current['next_position']['d2']),
        'd5': d5,
        'event_kind': '1',
        'payload': json.loads(v7),
        'state_diff': json.loads(v8),
    }
    posted = await client.post('/games/' + game + '/sync/events',
        json={'recording_right_proof': started['recording_right_proof'],
              'events': [event]},
        headers=device_headers(pair, str(uuid4())))
    assert posted.status_code == 200, ('ordinary-save', posted.status_code, posted.text)
    assert posted.json()['eventResults'][0]['a5Result'] == '受理'
    return d5


async def undo_body(client, expected):
    state = await read_spike(client, expected)
    assert state.status_code == 200, ('spike-state', state.status_code, state.text)
    value = state.json()
    target = value['undoTarget']
    assert target is not None
    from pitchlog.domainrt.host import open_domain_host
    current = {
        'stateFields': value['state']['stateFields'],
        'scoreboard': value['state']['scoreboard'],
    }
    if 'battingOrderBySide' in value['state']:
        current['battingOrderBySide'] = value['state']['battingOrderBySide']
    with open_domain_host() as host:
        raw = host.call('applyUndo', json.dumps({
            'current': current,
            'history': {'stack': [item['entry'] for item in value['history']]},
        }, ensure_ascii=False, sort_keys=True))
    result = json.loads(raw)['value']
    reference = {key: target[key] for key in ('game', 'd4', 'd1')}
    return value, {
        'recording_right_proof': started['recording_right_proof'],
        'd5': str(uuid4()),
        'd1': value['nextD1'],
        'target': reference,
        'payload': {
            'formatVersion': 'undo-connection-spike-v1',
            'target': reference,
            'result': result,
        },
    }


async def run():
    global game, started
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url='https://test'
    ) as client:
        logged = await login(client, team)
        assert logged.status_code == 200, ('login', logged.status_code)
        preparation = await client.get('/games/' + game, headers=headers())
        assert preparation.status_code == 200
        source = preparation.json()
        created = await client.post('/games', headers=headers(), json={
            'scheduled_at': source['scheduled_at'],
            'game_type_key': source['game_type_key'],
            'away_team_record_id': source['away_team_record_id'],
            'home_team_record_id': source['home_team_record_id'],
            'tournament': {'kind': 'existing', 'key': source['tournament_key']},
        })
        assert created.status_code == 201, ('create', created.status_code, created.text)
        game = created.json()['id']
        assert game != case['game']
        enrolled = await client.post('/devices/enroll', headers=headers())
        assert enrolled.status_code == 200
        pair = enrolled.json()
        body = _body(10)
        body.update(
            device_id=pair['device_id'],
            device_credential=pair['device_credential'],
            start_request_id=str(uuid4()),
        )
        start = await client.post('/games/' + game + '/start', json=body,
            headers=headers())
        assert start.status_code == 200, ('start', start.status_code, start.text)
        started = start.json()
        read = await client.get(
            '/games/' + game + '/started?projection=ordinary-prefix-v1&limit=2',
            headers=headers())
        assert read.status_code == 200, ('initial-read', read.status_code, read.text)
        before = read.json()
        assert before['after']['stateFields']['state.count.balls'] == '0'
        d5 = await ordinary_save(client, started, pair, before)

        state = await read_spike(client, tenant)
        assert state.status_code == 200, (
            'state-after-play', state.status_code, state.text
        )
        value = state.json()
        assert value['watermark'] == 1
        assert value['state']['stateFields']['state.count.balls'] == '1'
        assert len(value['history']) == 1
        assert value['undoTarget']['d1'] == 1
        assert value['events'] == [{
            'd1': 1, 'd5': d5, 'eventKind': 'play_input', 'targetD1': None,
        }]

        # 故障注入: 投影後の名付き境界で例外を出し、取消イベント全体を戻す。
        value, payload = await undo_body(client, tenant)
        attempt_fail = str(uuid4())
        from pitchlog.sync.crash_points import testing_crash_hook

        def fail(point):
            if point == 'after_t4_projection':
                raise RuntimeError('spike-undo-injected-failure')

        crashed = False
        try:
            with testing_crash_hook(fail):
                failed = await client.post('/spike/games/' + game + '/undo',
                    json=payload, headers=device_headers(pair, attempt_fail))
            crashed = failed.status_code >= 500
        except BaseException:
            crashed = True
        assert crashed
        after_failure = (await read_spike(client, tenant)).json()
        assert after_failure['watermark'] == 1
        assert after_failure['state']['stateFields']['state.count.balls'] == '1'
        assert len(after_failure['events']) == 1

        # 記録権不成立: 提示V12を変え、取消イベントを保存しない。
        value, payload = await undo_body(client, tenant)
        broken = json.loads(json.dumps(payload))
        broken['recording_right_proof'] = broken['recording_right_proof'] + 'x'
        denied = await client.post('/spike/games/' + game + '/undo',
            json=broken, headers=device_headers(pair, str(uuid4())))
        assert denied.status_code == 200, ('rights', denied.status_code, denied.text)
        assert denied.json()['eventResults'][0]['a5Result'] == '退避'
        assert (await read_spike(client, tenant)).json()['watermark'] == 1

        # 正常な取消と再取得。
        value, payload = await undo_body(client, tenant)
        attempt = str(uuid4())
        posted = await client.post('/spike/games/' + game + '/undo',
            json=payload, headers=device_headers(pair, attempt))
        assert posted.status_code == 200, ('undo', posted.status_code, posted.text)
        assert posted.json()['eventResults'][0]['a5Result'] == '受理'
        after = (await read_spike(client, tenant)).json()
        assert after['watermark'] == 2
        assert after['state']['stateFields'] == before['after']['stateFields']
        assert after['state']['scoreboard'] == before['after']['scoreboard']
        assert after['history'] == []
        assert after['undoTarget'] is None
        assert [item['eventKind'] for item in after['events']] == [
            'play_input', 'undo',
        ]

        # 同一D5・同一内容の再送は保存済み結果を再掲し、二重取消しない。
        replay = await client.post('/spike/games/' + game + '/undo',
            json=payload, headers=device_headers(pair, attempt))
        assert replay.status_code == 200, ('replay', replay.status_code, replay.text)
        assert replay.json()['eventResults'][0]['a5Result'] == '重複'
        replay_state = (await read_spike(client, tenant)).json()
        assert replay_state['watermark'] == 2
        assert replay_state['state'] == after['state']

        # 取消不能: 同じ対象をもう一度名指す新しいD5は内容拒否で保存しない。
        stale = json.loads(json.dumps(payload))
        stale['d5'] = str(uuid4())
        stale['d1'] = 3
        stale_post = await client.post('/spike/games/' + game + '/undo',
            json=stale, headers=device_headers(pair, str(uuid4())))
        assert stale_post.status_code == 200
        assert stale_post.json()['eventResults'][0]['a5Result'] == '拒否'
        assert (await read_spike(client, tenant)).json()['watermark'] == 2

        # 越境: 別tenantの実loginでは自tenantの取消状態を取得できない。
        foreign_login = await login(client, case['other_team_name'])
        assert foreign_login.status_code == 200
        foreign = await read_spike(client, case['other_tenant'])
        assert foreign.status_code == 404, ('foreign', foreign.status_code)

        return {
            'game': game,
            'd5': d5,
            'watermark': after['watermark'],
            'events': after['events'],
            'state': after['state'],
        }


try:
    out = asyncio.run(run())
except BaseException:
    out = {'exception': traceback.format_exc().splitlines()[-1]}
print(json.dumps(out, ensure_ascii=False))
"""
)


def test_spike_undo_real_http_db_and_audit(vertical_database) -> None:
    """取消の接続spikeを実画面用の実認証・権利・同期核・DBで通す。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.ball','batting_result','ボール') "
            "ON CONFLICT(key) DO NOTHING"
        )
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
        "start_request_id": str(db.start_request_id),
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
    assert process.returncode == 0, (process.stdout[-2000:], process.stderr[-2000:])
    result = json.loads(process.stdout)
    assert "exception" not in result, json.dumps(result, ensure_ascii=False)
    created = result["game"]
    assert created != str(db.game_id)
    assert result["watermark"] == 2
    assert result["state"]["stateFields"]["state.count.balls"] == "0"
    with psycopg.connect(db.authority.database.business_admin) as admin:
        counts = {}
        for table in ("operation_events", "play_rows"):
            counts[table] = admin.execute(
                f"SELECT count(*) FROM public.{table} "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, UUID(created)),
            ).fetchone()
        assert counts["operation_events"] == (2,)
        # 取消は対象の物理行を削除しない（監査履歴を保持する）。
        assert counts["play_rows"] == (1,)
        target = admin.execute(
            "SELECT event_kind, retired_at, replaced_at FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s AND d1=1",
            (db.tenant_id, UUID(created)),
        ).fetchone()
        assert target is not None
        assert target[0] == "play_input"
        assert target[1] is None and target[2] is None
        ledger = admin.execute(
            "SELECT count(*) FROM public.idempotency_ledger AS ledger "
            "JOIN public.operation_events AS op "
            "ON ledger.tenant_id=op.tenant_id AND ledger.d5=op.d5 "
            "WHERE op.tenant_id=%s AND op.game_id=%s",
            (db.tenant_id, UUID(created)),
        ).fetchone()
        assert ledger == (2,)
