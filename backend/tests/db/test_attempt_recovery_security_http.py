"""実旧writerの生存中拒否と認証/端末/tenant境界を同じowned PGで確認する。"""

from __future__ import annotations

import json
import subprocess
from typing import Any, cast
from uuid import uuid4

import pytest

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _COURSE,
    _PASSWORD,
    _PITCH_TYPE,
    _RECOVERY_SCRIPT,
    _app_arguments,
    _assert_recorded_once,
    _prepare_app_configuration,
)
from .test_first_ball_vertical_http import admin_connection as admin_connection
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import product_node_binary as product_node_binary
from .test_first_ball_vertical_http import (
    tested_role_connection as tested_role_connection,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db

_LIVE = r"""
        elif case.get('fault')=='live_t4':
            import threading
            from pitchlog.sync.crash_points import testing_crash_hook
            entered,release=threading.Event(),threading.Event()
            def keep_live(point):
                if point=='after_t4_projection':
                    entered.set()
                    if not release.wait(30):
                        raise RuntimeError('owned live witness deadline exceeded')
            with testing_crash_hook(keep_live):
                original=asyncio.create_task(client.post('/games/'+game+'/sync/events',
                    json=payload,headers=device_headers(pair,original_attempt)))
                try:
                    if not await asyncio.to_thread(entered.wait,10):
                        raise RuntimeError('owned live witness was not reached')
                    live=await client.post('/games/'+game+'/sync/attempts/recover',
                        json=payload,headers=device_headers(pair,original_attempt))
                    out['live_recovery']={'status':live.status_code,
                        'body':live.json() if live.status_code==200 else None}
                finally:
                    release.set()
                accepted=await original
            out['stages'].append(['sync',accepted.status_code])
            if accepted.status_code!=200:
                return out
            out['accepted_ack']=accepted.json()
"""
_NEGATIVES = r"""
        results={}
        async with AsyncClient(transport=ASGITransport(app=app),
            base_url='https://test') as anonymous:
            value=await anonymous.post('/games/'+game+'/sync/attempts/recover',
                json=payload,headers=device_headers(pair,original_attempt))
            results['unauthenticated']=value.status_code
        wrong=device_headers(pair,original_attempt)
        wrong['X-Pitchlog-Device-Id']=str(uuid4())
        value=await client.post('/games/'+game+'/sync/attempts/recover',
            json=payload,headers=wrong)
        results['other_device']=value.status_code
        wrong=device_headers(pair,original_attempt)
        wrong['X-Pitchlog-Device-Credential']=pair['device_credential']+'.altered'
        value=await client.post('/games/'+game+'/sync/attempts/recover',
            json=payload,headers=wrong)
        results['other_credential']=value.status_code
        bad=json.loads(json.dumps(payload));bad['unexpected']=True
        value=await client.post('/games/'+game+'/sync/attempts/recover',
            json=bad,headers=device_headers(pair,original_attempt))
        results['unknown_field']=value.status_code
        async with AsyncClient(transport=ASGITransport(app=app),
            base_url='https://test') as foreign:
            signed=await login(foreign,case['other_team_name'])
            results['foreign_login']=signed.status_code
            foreign_headers=headers()
            foreign_headers['X-Pitchlog-Expected-Tenant']=case['other_tenant']
            enrolled=await foreign.post('/devices/enroll',headers=foreign_headers)
            results['foreign_enroll']=enrolled.status_code
            if enrolled.status_code==200:
                offered=device_headers(enrolled.json(),original_attempt)
                offered['X-Pitchlog-Expected-Tenant']=case['other_tenant']
                value=await foreign.post('/games/'+game+'/sync/attempts/recover',
                    json=payload,headers=offered)
                results['foreign_game']=value.status_code
        out['security']=results
"""
_POST = (
    "        else:\n"
    "            accepted=await client.post('/games/'+game+"
    "'/sync/events',json=payload,"
)
_REPLAY_MARKER = (
    "        # 応答は端末へ渡さなかったものとして、原attempt/原本文だけで権威照会する。"
)
assert _POST in _RECOVERY_SCRIPT and _REPLAY_MARKER in _RECOVERY_SCRIPT
_SCRIPT = _RECOVERY_SCRIPT.replace(_POST, _LIVE + _POST, 1).replace(
    _REPLAY_MARKER, _NEGATIVES + _REPLAY_MARKER, 1
)


def test_live_writer_recovery_and_foreign_presentations_are_closed(
    vertical_database: Any,
) -> None:
    """実T4内の旧writerは未解決、実終結後だけ原本文再送へ進める。"""
    db = vertical_database
    token = uuid4()
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "other_tenant": str(db.other_tenant_id),
        "other_team_name": db.other_team_name,
        "start_request_id": str(db.start_request_id),
        "pitch_type": _PITCH_TYPE,
        "course": list(_COURSE),
        "fault": "live_t4",
    }
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _SCRIPT],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert process.returncode == 0, (process.stdout[-600:], process.stderr[-600:])
        value = cast(dict[str, Any], json.loads(process.stdout))
        assert value["live_recovery"] == {
            "status": 200,
            "body": {"resolution": "unresolved"},
        }, value
        assert value["security"] == {
            "unauthenticated": 401,
            "other_device": 401,
            "other_credential": 401,
            "unknown_field": 422,
            "foreign_login": 200,
            "foreign_enroll": 200,
            "foreign_game": 404,
        }, value
        assert value["stages"] == [
            ["login", 200],
            ["enroll", 200],
            ["start", 200],
            ["sync", 200],
            ["recover", 200],
            ["recover_again", 200],
            ["resend_new_attempt", 200],
        ], value
        assert value["resolution"] == {"resolution": "retry_allowed"}
        assert value["repeated_resolution"] == value["resolution"]
        assert value["mismatched_body_status"] == 200
        assert value["mismatched_body_resolution"] == {"resolution": "unresolved"}
        assert value["resent_ack"]["eventResults"][0]["a5Result"] == "重複"
        _assert_recorded_once(db, value["d5"])
