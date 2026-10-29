"""E1初球P2の隔離縦断（開始→実HTTP 1球→実PG→記録後状態）をowned PGで確認する。

試合・名簿・語彙・ログイン資格はfixture準備であり、画面や運用の証拠ではない。
開始は実HTTP worker、1球は実HTTP同期入口（実Cookie・実端末資格・実broker・
実writer・実権利・実artifact評価）を通す。V7/V8は同じartifact評価と実名簿から
作る試験入力で、実画面の操作証拠や正式V7採用ではない。
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from .sync_writer_binding_support import binding_broker, owned_binding_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_game_start import start_database as _start_database
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db

_PITCH_TYPE = "u06-first-ball-fastball"
_PASSWORD = "public-owned-vertical-password-A1"
_COURSE = (132, 131)
_BATTER = UUID(int=110)
_PITCHER = UUID(int=201)
_CATCHER = UUID(int=202)


@pytest.fixture
def initial_scope_database(monkeypatch: pytest.MonkeyPatch):
    """本試験の縦断に必要な実binding制御PGも含めたowned3PGを供給する。"""
    from db_fixtures import _dsn_names

    with owned_binding_database(monkeypatch) as owner:
        admin_name, role_name = _dsn_names()
        monkeypatch.setenv(admin_name, owner.authority.database.primary_admin)
        monkeypatch.setenv(role_name, owner.authority.database.endpoints.primary_dsn)
        yield owner


@pytest.fixture
def vertical_database(initial_scope_database: Any, product_node_binary, monkeypatch):
    """既start fixtureの公式選手/実Node/canonical規則を同じowned PGへ供給する。"""
    db = cast(Any, _start_database).__wrapped__(
        initial_scope_database, product_node_binary, monkeypatch
    )
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.ball','batting_result','ボール') "
            "ON CONFLICT(key) DO NOTHING"
        )
        admin.execute(
            "INSERT INTO public.tenant_vocabularies"
            "(tenant_id,key,category,display_name,pitch_family) "
            "VALUES (%s,%s,'pitch_type','直球','fastball')",
            (db.tenant_id, _PITCH_TYPE),
        )
        for key, value in {
            "auth.token_ttl_seconds": 3600,
            "auth.team_login.window_seconds": 3600,
            "auth.team_login.throttle_threshold": 3,
            "auth.team_login.throttle_step_ms": 25,
            "auth.team_login.throttle_max_ms": 200,
        }.items():
            admin.execute(
                "INSERT INTO public.system_settings(key,value) VALUES (%s,%s) "
                "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                (key, str(value)),
            )
        subject = uuid4()
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(id,tenant_id) VALUES (%s,%s)",
            (subject, db.tenant_id),
        )
        admin.execute(
            "INSERT INTO public.tenant_credentials"
            "(auth_subject_id,password_hash) "
            "VALUES (%s,authn_crypto.crypt(%s,authn_crypto.gen_salt('bf',12)))",
            (subject, _PASSWORD),
        )
        row = admin.execute(
            "SELECT name FROM public.tenants WHERE id=%s", (db.tenant_id,)
        ).fetchone()
        assert row is not None
        db.team_name = row[0]
    return db


def _prepare_app_configuration(db: Any) -> None:
    """app容器が見る非秘密のroot配置と、app向けbroker endpointを用意する。"""
    from .durable_rights_ledger_support import docker

    docker(
        *db.authority.command(root=True),
        "-c",
        """
import json,os
from pathlib import Path
from uuid import UUID
from pitchlog.durable_rights_ledger.authority import _write_root_json
public=Path('/control/public')
# app容器は同じcontrol volumeを/controlと/run/pitchlogの両方へ見る。
client=dict(schema_version=1,
 broker_endpoint='/control/public/binding-broker.json',
 control_instance=str(UUID(int=7101)),
 business_instance=str(UUID(int=7102)),
 restore_epoch=str(UUID(int=7103)),
 control_version=1)
_write_root_json(public/'binding-client.json',client,0o644,20003)
rg1=json.loads(Path('/control/initial/app-client.json').read_text())
rg1['socket_path']='/run/pitchlog/initial/rg1.sock'
Path('/control/rg1-client.json').write_text(json.dumps(rg1))
os.chmod('/control/rg1-client.json',0o644)
os.chown('/control/rg1-client.json',0,0)
""",
    )


_APP_SCRIPT = r"""
import asyncio,base64,hashlib,json,os,sys,traceback
from pathlib import Path
from uuid import UUID,uuid4

case=json.loads(os.environ['PITCHLOG_VERTICAL_CASE'])
assert os.geteuid()==20003 and os.getegid()==20003
os.environ['PITCHLOG_TOKEN_SIGNING_KEY_B64']=base64.b64encode(bytes(range(32))).decode()
os.environ['PITCHLOG_ALLOWED_ORIGINS']='https://test'
os.environ['PITCHLOG_DATABASE_URL']='postgresql+psycopg://pitchlog_app@/ledger_fixture?host=%2Fbusiness-socket&sslmode=disable'
os.environ['PITCHLOG_DATABASE_POOLED']='false'
os.environ['PITCHLOG_BINDING_CLIENT_CONFIG']='/run/pitchlog/public/binding-client.json'
sys.path.insert(0,'/fixture/backend/tests')
from httpx import AsyncClient,ASGITransport
from pitchlog.api.app import create_app
from test_initial_game_start_components import _body

def error_hook(kind,value,tb):
    print(json.dumps({'fixture_failure':kind.__name__,
        'frames':[(f.name,f.lineno) for f in traceback.extract_tb(tb)]}),flush=True)
sys.excepthook=error_hook
app=create_app()
tenant=case['tenant'];game=case['game'];team=case['team_name']
password=case['password']
out={'stages':[]}

def headers():
    return {'Origin':'https://test','X-Pitchlog-Request':'1',
        'X-Pitchlog-Expected-Tenant':tenant,
        'X-Pitchlog-Tenant-Challenge':str(uuid4())}

def device_headers(pair,attempt):
    value=headers()
    value.update({'X-Pitchlog-Device-Id':pair['device_id'],
        'X-Pitchlog-Device-Credential':pair['device_credential'],
        'X-Pitchlog-Sync-Attempt':attempt})
    return value

def payload_from_artifact(cookie):
    '''実artifact評価と実名簿から、画面が送るV7/V8を同じ製品部品で作る。'''
    from pitchlog.domainrt.first_ball_projection import (
        FirstBallCalculationValue,format_first_ball_calculation)
    from pitchlog.domainrt.first_pitch import FirstPitchRequest
    from pitchlog.domainrt.first_pitch_continuation import (
        CombinedRequest,_check_frozen_members,decode_combined_response)
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.repositories.started_snapshot import read_initial_started_snapshot
    from pitchlog.repositories.tenant_context_issuance import (
        issue_tenant_context_from_presented_token)
    from pitchlog.repositories.transaction import tenant_transaction_scope
    from pitchlog.sync.first_ball_execution import _participants
    from pitchlog.sync.first_ball_payload import (
        FirstBallObservations,format_first_ball_payload)
    signer=app.state.token_presentation
    issued=issue_tenant_context_from_presented_token(cookie,signer)
    assert issued is not None
    context,_=issued
    with tenant_transaction_scope(context) as scope:
        snapshot=read_initial_started_snapshot(scope,UUID(game))
    request=CombinedRequest(
        t1=FirstPitchRequest(eventKind='batting-result',
            resultId='batting-result.ball',pitchEventKind='pitch-event',
            before=snapshot.before),
        rules=snapshot.rules)
    _check_frozen_members(request)
    request=CombinedRequest.model_validate(request)
    with open_domain_host() as host:
        digest=hashlib.sha256(host._source.encode('utf-8')).hexdigest()
        response=decode_combined_response(host.call(
            'deriveFirstPitchWithContinuation',
            request.model_dump_json(by_alias=True)))
    calculation=FirstBallCalculationValue.model_validate_json(
        format_first_ball_calculation(request,response,artifact_sha256=digest))
    participants=_participants(snapshot.roster.model_dump_json(by_alias=True))
    observations=FirstBallObservations.model_validate_json(json.dumps({
        'pitchTypeKey':case['pitch_type'],
        'course':{'unit':'1/263','x':str(case['course'][0]),
            'y':str(case['course'][1])},
        'pitchSpeed':{'kmh':None,'outsideRangeConfirmed':False},
        'stance':None,'battingSide':None}))
    v7,v8=format_first_ball_payload(observations,participants,calculation)
    return v7,v8,dict(participants.model_dump(mode='json',by_alias=True))

def recorded_read(cookie):
    '''記録後readの製品入口で同じ初球状態を再読込する（HTTP 409は別ステップ）。'''
    from pitchlog.repositories.recorded_snapshot import RECORDED_PLAY_ROW_COLUMNS
    from pitchlog.repositories.started_read import (
        StartedRecordedView,read_started_game)
    from pitchlog.repositories.tenant_context_issuance import (
        issue_tenant_context_from_presented_token)
    from pitchlog.repositories.transaction import tenant_transaction_scope
    issued=issue_tenant_context_from_presented_token(
        cookie,app.state.token_presentation)
    assert issued is not None
    context,_=issued
    with tenant_transaction_scope(context) as scope:
        view=read_started_game(scope,UUID(game))
    assert type(view) is StartedRecordedView
    fields=view.after.model_dump(mode='json',by_alias=True)['stateFields']
    row=dict(zip(RECORDED_PLAY_ROW_COLUMNS,view.play_row,strict=True))
    flags=view.stat_flags.model_dump(mode='json',by_alias=True)
    t2=view.t2.model_dump(mode='json',by_alias=True)
    return {
        'state':fields,
        'lineup_ids':[str(view.lineups[0].id),str(view.lineups[1].id)],
        'history':len(view.history),
        'stat_flag_count':len(flags),
        't2_keys':sorted(t2),
        'play_row_columns':len(row),
        'play_number':row['play_number'],
        'event_kind':row['event_kind'],
        'source_event_id':str(row['source_event_id']),
    }

async def run():
    transport=ASGITransport(app=app)
    async with AsyncClient(transport=transport,base_url='https://test') as client:
        response=await client.post('/auth/login',json={'team_name':team,
            'password':password},headers={'Origin':'https://test',
            'X-Pitchlog-Request':'1'})
        out['stages'].append(['login',response.status_code])
        if response.status_code!=200:
            out['login_body']=response.text[:400]
            return out
        cookie=client.cookies.get('__Host-pitchlog_token')
        h=headers();enrolled=await client.post('/devices/enroll',headers=h)
        out['stages'].append(['enroll',enrolled.status_code])
        if enrolled.status_code!=200:
            out['enroll_body']=enrolled.text[:400]
            return out
        pair=enrolled.json()
        body=_body(10)
        body.update(device_id=pair['device_id'],
            device_credential=pair['device_credential'],
            start_request_id=case['start_request_id'])
        h=headers()
        started=await client.post('/games/'+game+'/start',json=body,headers=h)
        out['stages'].append(['start',started.status_code])
        if started.status_code!=200:
            out['start_body']=started.text[:400]
            return out
        first=started.json()
        out['d4']=first['d4']
        out['started_at']=first['started_at']
        out['away_lineup_id']=first['away_lineup_id']
        out['home_lineup_id']=first['home_lineup_id']
        h=headers();pre=await client.get('/games/'+game+'/started',headers=h)
        out['stages'].append(['started_before',pre.status_code])
        v7,v8,people=payload_from_artifact(cookie)
        out['participants']=people
        event={'d5':str(uuid4()),'d1':1,'d4':first['d4'],'game_id':game,
            'event_kind':'1','d2':1,'payload':json.loads(v7),
            'state_diff':json.loads(v8)}
        payload={'recording_right_proof':first['recording_right_proof'],
            'events':[event]}
        attempt=str(uuid4())
        posted=await client.post('/games/'+game+'/sync/events',json=payload,
            headers=device_headers(pair,attempt))
        out['stages'].append(['sync',posted.status_code])
        out['ack']=posted.json() if posted.status_code==200 else None
        if posted.status_code!=200:
            out['sync_body']=posted.text[:400]
        # 同一attempt・同一内容の再送（ACK消失後の再送）は保存済み結果を再掲する。
        resent=await client.post('/games/'+game+'/sync/events',json=payload,
            headers=device_headers(pair,attempt))
        out['stages'].append(['resend',resent.status_code])
        out['resend_ack']=resent.json() if resent.status_code==200 else None
        if resent.status_code!=200:
            out['resend_body']=resent.text[:400]
        # 同一D5・同一内容を**別attempt**で再送しても、DI2はattempt非依存で再掲する。
        other_attempt=str(uuid4())
        reattempt=await client.post('/games/'+game+'/sync/events',
            json=payload,headers=device_headers(pair,other_attempt))
        out['stages'].append(['resend_other_attempt',reattempt.status_code])
        out['reattempt_ack']=reattempt.json() if reattempt.status_code==200 else None
        if reattempt.status_code!=200:
            out['reattempt_body']=reattempt.text[:400]
        # 同一D5・異なる内容は B3b（A5「拒否」）で再適用しない。
        changed=json.loads(v7)
        changed['observations']['course']={'unit':'1/263','x':'1','y':'2'}
        conflict_event={**event,'payload':changed}
        conflict=await client.post(
            '/games/'+game+'/sync/events',
            json={'recording_right_proof':first['recording_right_proof'],
                'events':[conflict_event]},
            headers=device_headers(pair,attempt))
        out['stages'].append(['conflict',conflict.status_code])
        out['conflict_ack']=conflict.json() if conflict.status_code==200 else None
        if conflict.status_code!=200:
            out['conflict_body']=conflict.text[:400]
        # 同一attemptへ別内容の新D5を割り当てる付替えはACKを返さず閉じる。
        retry_event={**event,'d5':str(uuid4())}
        retried=await client.post(
            '/games/'+game+'/sync/events',
            json={'recording_right_proof':first['recording_right_proof'],
                'events':[retry_event]},
            headers=device_headers(pair,attempt))
        out['stages'].append(['attempt_reuse',retried.status_code])
        if retried.status_code!=200:
            out['attempt_reuse_body']=retried.text[:200]
        out['recorded']=recorded_read(cookie)
        h=headers();after=await client.get('/games/'+game+'/started',headers=h)
        out['stages'].append(['started_after',after.status_code])
        out['d5']=event['d5']
        out['device_id']=pair['device_id']
    return out

try:
    asyncio.run(run())
except BaseException:
    out['exception']=traceback.format_exc().splitlines()[-1]
    out['frames']=[(f.name,f.lineno) for f in traceback.extract_tb(sys.exc_info()[2])]
print(json.dumps(out))
"""


def _app_arguments(db: Any, case: dict[str, Any]) -> list[str]:
    """製品app UID20003の容器へ公開設定と業務socketだけを渡す。"""
    args = db._broker_arguments(uid=20003)
    args[1:1] = [
        "--volume",
        f"{db.authority.database.business_socket}:/business-socket:ro",
        "--volume",
        f"{db.authority.control}:/control:ro",
        "--env",
        "PITCHLOG_VERTICAL_CASE=" + json.dumps(case),
    ]
    return args


def test_first_ball_vertical_http_records_and_refuses_reload(
    vertical_database: Any,
) -> None:
    """開始→1球→ACK→実PG保存→記録後409を一つの実HTTP経路で確認する。"""
    db = vertical_database
    token = uuid4()
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "start_request_id": str(db.start_request_id),
        "pitch_type": _PITCH_TYPE,
        "course": list(_COURSE),
    }
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _APP_SCRIPT],
            capture_output=True,
            text=True,
            timeout=300,
        )
    assert process.returncode == 0, (process.stdout[-600:], process.stderr[-600:])
    value = cast(dict[str, Any], json.loads(process.stdout))
    assert value["stages"] == [
        ["login", 200],
        ["enroll", 200],
        ["start", 200],
        ["started_before", 200],
        ["sync", 200],
        ["resend", 200],
        ["resend_other_attempt", 200],
        ["conflict", 200],
        ["attempt_reuse", 503],
        ["started_after", 409],
    ], value
    assert value["participants"] == {
        "batterId": str(_BATTER),
        "pitcherId": str(_PITCHER),
        "catcherId": str(_CATCHER),
        "battingOrder": "1",
    }, value["participants"]
    assert value["ack"] == {
        "advancedD3": 1,
        "eventResults": [
            {"d4": value["d4"], "d1": 1, "d5": value["d5"], "a5Result": "受理"}
        ],
    }, value["ack"]
    assert value["resend_ack"] == {
        "advancedD3": 1,
        "eventResults": [
            {"d4": value["d4"], "d1": 1, "d5": value["d5"], "a5Result": "重複"}
        ],
    }, value["resend_ack"]
    assert value["reattempt_ack"] == {
        "advancedD3": 1,
        "eventResults": [
            {"d4": value["d4"], "d1": 1, "d5": value["d5"], "a5Result": "重複"}
        ],
    }, value["reattempt_ack"]
    assert value["conflict_ack"] == {
        "advancedD3": 1,
        "eventResults": [
            {"d4": value["d4"], "d1": 1, "d5": value["d5"], "a5Result": "拒否"}
        ],
    }, value["conflict_ack"]
    # 保存後の製品リーダー再読込が同じ初球状態を返す（HTTP 409は別単位）。
    recorded = value["recorded"]
    assert UUID(recorded["source_event_id"])
    assert recorded["lineup_ids"] == [value["away_lineup_id"], value["home_lineup_id"]]
    assert recorded["history"] == 1
    assert recorded["stat_flag_count"] > 0
    assert recorded["t2_keys"] == ["basis", "evaluation_point", "kind"]
    assert recorded["play_row_columns"] == 41
    assert recorded["play_number"] == 1 and recorded["event_kind"] == "pitch"
    assert {
        key: recorded["state"][key]
        for key in (
            "state.count.balls",
            "state.count.strikes",
            "state.outs",
            "state.inning",
            "state.half",
        )
    } == {
        "state.count.balls": "1",
        "state.count.strikes": "0",
        "state.outs": "0",
        "state.inning": "1",
        "state.half": "top",
    }
    # ボール1球では打席は継続し、打順は変わらない。
    assert recorded["state"]["state.battingOrder"] == "1"
    _assert_recorded_once(db, value["d5"])


def _assert_recorded_once(db: Any, d5: str) -> None:
    """同じ1球が一度だけ保存され、記録後状態と印が整合することを確認する。"""
    with psycopg.connect(db.authority.database.business_admin) as admin:

        def count(table: str) -> int:
            row = admin.execute(
                sql.SQL("SELECT count(*) FROM public.{} WHERE tenant_id=%s").format(
                    sql.Identifier(table)
                ),
                (db.tenant_id,),
            ).fetchone()
            assert row is not None
            return int(row[0])

        counts = {
            table: count(table)
            for table in (
                "idempotency_ledger",
                "event_slots",
                "operation_events",
                "play_rows",
            )
        }
        assert counts == {
            "idempotency_ledger": 1,
            "event_slots": 1,
            "operation_events": 1,
            "play_rows": 1,
        }, counts
        row = admin.execute(
            "SELECT play_number,batting_order,event_kind,batting_result_key,"
            "pitch_type_key,course_x,course_y,pitch_speed,stance,batting_side,"
            "batter_id,pitcher_id,catcher_id,version "
            "FROM public.play_rows WHERE tenant_id=%s",
            (db.tenant_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == 1 and row[1] == 1
        assert row[2] == "pitch" and row[3] == "batting-result.ball"
        assert row[4] == _PITCH_TYPE
        assert row[5] == _COURSE[0] / 263 and row[6] == _COURSE[1] / 263
        assert row[7] is None and row[8] is None and row[9] is None
        assert (row[10], row[11], row[12]) == (_BATTER, _PITCHER, _CATCHER)
        assert row[13] == 1
        assert admin.execute(
            "SELECT d5 FROM public.idempotency_ledger WHERE tenant_id=%s",
            (db.tenant_id,),
        ).fetchone() == (UUID(d5),)
        assert admin.execute(
            "SELECT state,source_event_id IS NOT NULL,play_row_id IS NOT NULL "
            "FROM sync_fence.first_ball_write_admissions WHERE tenant_id=%s",
            (db.tenant_id,),
        ).fetchall() == [("consumed", True, True)]
