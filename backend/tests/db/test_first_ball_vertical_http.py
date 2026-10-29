"""E1初球P2の隔離縦断（開始→実HTTP 1球→実PG→記録後状態）をowned PGで確認する。

試合・名簿・語彙・ログイン資格はfixture準備であり、画面や運用の証拠ではない。
開始は実HTTP worker、1球は実HTTP同期入口（実Cookie・実端末資格・実broker・
実writer・実権利・実artifact評価）を通す。V7/V8は同じartifact評価と実名簿から
作る試験入力で、実画面の操作証拠や正式V7採用ではない。

記録後GETの負例は、2球目・訂正・墓標=409、別tenant=404、破損=503 を固定する
（破損は保存値と再評価値の不一致と、payloadに由来しない列の非NULL）。
2球目と墓標の保存状態は、製品triggerが正しく拒否するため、状態の構成に限り
同じowned PGのtriggerを無効化して作り、観測後に戻す。製品経路の迂回ではない。
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
        # 別tenantの404を実HTTPで確かめるためのログイン資格（fixture準備）。
        foreign = uuid4()
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(id,tenant_id) VALUES (%s,%s)",
            (foreign, db.other_tenant_id),
        )
        admin.execute(
            "INSERT INTO public.tenant_credentials"
            "(auth_subject_id,password_hash) "
            "VALUES (%s,authn_crypto.crypt(%s,authn_crypto.gen_salt('bf',12)))",
            (foreign, _PASSWORD),
        )
        other = admin.execute(
            "SELECT name FROM public.tenants WHERE id=%s", (db.other_tenant_id,)
        ).fetchone()
        assert other is not None
        db.other_team_name = other[0]
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
phase=case.get('phase','record')
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
    '''記録後readの製品入口で同じ初球状態を再読込する（HTTP 200は別phaseで検査）。'''
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

async def login(client,name):
    return await client.post('/auth/login',json={'team_name':name,
        'password':password},headers={'Origin':'https://test',
        'X-Pitchlog-Request':'1'})

async def read_once(client,name,expected):
    response=await login(client,name)
    out['stages'].append(['login',response.status_code])
    if response.status_code!=200:
        out['login_body']=response.text[:400]
        return out
    h={'Origin':'https://test','X-Pitchlog-Request':'1',
        'X-Pitchlog-Expected-Tenant':expected,
        'X-Pitchlog-Tenant-Challenge':str(uuid4())}
    read=await client.get('/games/'+game+'/started',headers=h)
    out['stages'].append(['started_read',read.status_code])
    out['read_status']=read.status_code
    out['read_body']=read.json() if read.status_code==200 else None
    out['read_text']=read.text
    return out

async def run():
    transport=ASGITransport(app=app)
    if phase=='read':
        async with AsyncClient(transport=transport,base_url='https://test') as client:
            return await read_once(client,team,tenant)
    if phase=='foreign':
        async with AsyncClient(transport=transport,base_url='https://test') as client:
            return await read_once(client,case['other_team_name'],
                case['other_tenant'])
    async with AsyncClient(transport=transport,base_url='https://test') as client:
        response=await login(client,team)
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
        out['started_after']=after.json() if after.status_code==200 else None
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


def _run_case(db: Any, case: dict[str, Any]) -> dict[str, Any]:
    """製品app容器を1回起動し、phaseどおりの実HTTP結果を受け取る。"""
    process = subprocess.run(
        ["docker", *_app_arguments(db, case), "-u", "-c", _APP_SCRIPT],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert process.returncode == 0, (process.stdout[-600:], process.stderr[-600:])
    return cast(dict[str, Any], json.loads(process.stdout))


def _read_case(db: Any) -> dict[str, Any]:
    """記録後のGETだけを行うphaseの入力。"""
    return {
        "phase": "read",
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
    }


def _tamper(db: Any, statement: str, parameters: tuple[Any, ...]) -> None:
    """負例を構成するfixture操作。製品経路の書込みではない。"""
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(statement, parameters)


def _second_play_row(db: Any) -> UUID:
    """保存初球の写しを2球目として1行足す（2球目以降の記録を構成する）。

    製品の初球admission triggerは2行目を正しく拒否するため、状態の構成に限り
    同じowned PGでtriggerを無効化する。読取の拒否だけを観測し、製品経路の
    成功や迂回の証拠にはしない。
    """
    row_id = uuid4()
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "CREATE TEMP TABLE saved_play AS SELECT * FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, db.game_id),
        )
        admin.execute("UPDATE saved_play SET id=%s, play_number=2", (row_id,))
        admin.execute(
            "ALTER TABLE public.play_rows DISABLE TRIGGER trg_first_ball_10_lock"
        )
        admin.execute(
            "ALTER TABLE public.play_rows DISABLE TRIGGER trg_first_ball_20_admit"
        )
        try:
            admin.execute("INSERT INTO public.play_rows SELECT * FROM saved_play")
        finally:
            admin.execute(
                "ALTER TABLE public.play_rows ENABLE TRIGGER trg_first_ball_10_lock"
            )
            admin.execute(
                "ALTER TABLE public.play_rows ENABLE TRIGGER trg_first_ball_20_admit"
            )
    return row_id


def _tombstone_once(db: Any, action: Any) -> Any:
    """墓標の保存状態を作り、実HTTPの観測後に元の行へ戻す。

    墓標（is_tombstone）は製品triggerで不変のため、状態の構成に限り同じ
    owned PGのtriggerを無効化する。製品行の意味は変えず、読取の拒否だけを見る。
    """
    admin = psycopg.connect(db.authority.database.business_admin)
    try:
        admin.execute(
            "CREATE TEMP TABLE saved_event AS SELECT * FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, db.game_id),
        )
        admin.execute(
            "ALTER TABLE public.operation_events "
            "DISABLE TRIGGER trg_operation_events_content_immutable"
        )
        admin.commit()
        try:
            admin.execute(
                "UPDATE public.operation_events SET is_tombstone=true,"
                "payload='{}'::jsonb,state_diff=NULL,d2=NULL "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, db.game_id),
            )
            admin.commit()
            return action()
        finally:
            admin.execute(
                "UPDATE public.operation_events e SET is_tombstone=s.is_tombstone,"
                "payload=s.payload,state_diff=s.state_diff,d2=s.d2 "
                "FROM saved_event s "
                "WHERE e.tenant_id=s.tenant_id AND e.id=s.id"
            )
            admin.execute(
                "ALTER TABLE public.operation_events "
                "ENABLE TRIGGER trg_operation_events_content_immutable"
            )
            admin.commit()
    finally:
        admin.close()


_EXCLUDED_PLAY_COLUMNS = (
    "tenant_id",
    "hidden_at",
    "import_batch_id",
    "legacy_row_identifier",
    "migration_unverified",
)


def _exposed_columns(play: dict[str, Any]) -> set[str]:
    """応答の公開keyを物理列名へ戻す（座標2列はcourse 1値へ統合済み）。"""
    return (set(play) - {"course"}) | {"course_x", "course_y"}


def test_first_ball_vertical_http_records_and_refuses_reload(
    vertical_database: Any,
) -> None:
    """開始→1球→ACK→実PG保存→記録後200を実HTTPで確認し、負例を固定する。"""
    from pitchlog.repositories.recorded_snapshot_operations import (
        RECORDED_PLAY_ROW_COLUMNS,
    )

    db = vertical_database
    token = uuid4()
    case = {
        "phase": "record",
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
        value = _run_case(db, case)
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
            ["started_after", 200],
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
        # 記録後GETは initial と同形＋after/history/23flags/T2/PlayRow を返す。
        read_back = value["started_after"]
        assert read_back["read_kind"] == "recorded"
        assert read_back["status"] == "in_progress"
        assert read_back["id"] == case["game"]
        assert read_back["current_d4"] == value["d4"]
        assert read_back["started_at"] == value["started_at"]
        # `state` は initial と同じ before（0-0）で、記録後は after に分かれる。
        assert read_back["state"]["stateFields"]["state.count.balls"] == "0"
        after = read_back["after"]["stateFields"]
        assert {
            key: after[key]
            for key in (
                "state.count.balls",
                "state.count.strikes",
                "state.outs",
                "state.inning",
                "state.half",
                "state.battingOrder",
            )
        } == {
            "state.count.balls": "1",
            "state.count.strikes": "0",
            "state.outs": "0",
            "state.inning": "1",
            "state.half": "top",
            "state.battingOrder": "1",
        }
        assert read_back["lineups"]["away"]["lineup_id"] == value["away_lineup_id"]
        assert read_back["lineups"]["home"]["lineup_id"] == value["home_lineup_id"]
        assert len(read_back["history"]) == 1
        assert len(read_back["stat_flags"]) == 23
        assert all(isinstance(flag, bool) for flag in read_back["stat_flags"].values())
        assert sorted(read_back["t2"]) == ["basis", "evaluation_point", "kind"]
        (play,) = read_back["play_rows"]
        # 公開36列 = 41列 − 5列。座標は正準整数kの1値へ統合し、Doubleを出さない。
        exposed = _exposed_columns(play)
        assert len(exposed) == 36
        assert exposed == set(RECORDED_PLAY_ROW_COLUMNS) - set(_EXCLUDED_PLAY_COLUMNS)
        assert set(play) == exposed - {"course_x", "course_y"} | {"course"}
        assert play["course"] == {"unit": "1/263", "x": "132", "y": "131"}
        assert (play["play_number"], play["batting_order"], play["version"]) == (
            1,
            1,
            1,
        )
        assert play["event_kind"] == "pitch"
        assert play["batting_result_key"] == "batting-result.ball"
        assert play["pitch_type_key"] == _PITCH_TYPE
        assert (play["pitch_speed"], play["stance"], play["batting_side"]) == (
            None,
            None,
            None,
        )
        assert (play["press"], play["fake_run"]) == (None, None)
        assert (play["batter_id"], play["pitcher_id"], play["catcher_id"]) == (
            str(_BATTER),
            str(_PITCHER),
            str(_CATCHER),
        )
        assert UUID(play["source_event_id"])
        # 記録後200の本文にも、保持者・資格・証明・tenantを出さない。
        recorded_text = json.dumps(read_back, ensure_ascii=False)
        assert case["tenant"] not in recorded_text
        lowered = recorded_text.lower()
        for word in (
            "tenant_id",
            "holder_device",
            "device_id",
            "credential",
            "recording_right_proof",
            "watermark",
            "prefix",
            "issuance_order",
            "granted_at",
        ):
            assert word not in lowered
        # 同じ初球を製品リーダーでも再読込し、HTTP側と同じ値であることを確かめる。
        recorded = value["recorded"]
        assert UUID(recorded["source_event_id"])
        assert recorded["lineup_ids"] == [
            value["away_lineup_id"],
            value["home_lineup_id"],
        ]
        assert recorded["history"] == 1
        assert recorded["stat_flag_count"] == 23
        assert recorded["t2_keys"] == ["basis", "evaluation_point", "kind"]
        assert recorded["play_row_columns"] == 41
        assert recorded["play_number"] == 1 and recorded["event_kind"] == "pitch"
        assert recorded["state"]["state.count.balls"] == "1"
        _assert_recorded_once(db, value["d5"])

        # 負例1: 2球目（保存初球の写しを1行足す）。
        row_id = _second_play_row(db)
        try:
            second = _run_case(db, _read_case(db))
        finally:
            _tamper(
                db,
                "DELETE FROM public.play_rows WHERE tenant_id=%s AND id=%s",
                (db.tenant_id, row_id),
            )
        # 負例2: 訂正（保存イベントの置換印）。
        _tamper(
            db,
            "UPDATE public.operation_events SET replaced_at=now() "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, db.game_id),
        )
        try:
            corrected = _run_case(db, _read_case(db))
        finally:
            _tamper(
                db,
                "UPDATE public.operation_events SET replaced_at=NULL "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, db.game_id),
            )
        # 負例3: 墓標（is_tombstone=true の保存状態）。
        tombstone = _tombstone_once(db, lambda: _run_case(db, _read_case(db)))
        # 負例4: 破損（保存PlayRowの座標が再評価値と食い違う）。
        _tamper(
            db,
            "UPDATE public.play_rows SET course_x=0.25 "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, db.game_id),
        )
        try:
            corrupt = _run_case(db, _read_case(db))
        finally:
            _tamper(
                db,
                "UPDATE public.play_rows SET course_x=%s "
                "WHERE tenant_id=%s AND game_id=%s",
                (_COURSE[0] / 263, db.tenant_id, db.game_id),
            )
        # 負例5: payloadに由来しない列の非NULL（writerのNULL固定に反する＝破損）。
        _tamper(
            db,
            "UPDATE public.play_rows SET press='3プレス' "
            "WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, db.game_id),
        )
        try:
            nullable = _run_case(db, _read_case(db))
        finally:
            _tamper(
                db,
                "UPDATE public.play_rows SET press=NULL "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, db.game_id),
            )
        # 負例6: 別tenant（実ログインした別tenantからは404で非開示）。
        foreign = _run_case(
            db,
            {
                "phase": "foreign",
                "tenant": str(db.tenant_id),
                "game": str(db.game_id),
                "team_name": db.team_name,
                "password": _PASSWORD,
                "other_tenant": str(db.other_tenant_id),
                "other_team_name": db.other_team_name,
            },
        )

    assert second["read_status"] == corrected["read_status"] == 409
    assert tombstone["read_status"] == 409
    # 409は記録後GETの固定外形で、どの記録でも同じ本文になる。
    assert second["read_text"] == corrected["read_text"] == tombstone["read_text"]
    assert "game_id" not in second["read_text"]
    assert corrupt["read_status"] == nullable["read_status"] == 503
    assert corrupt["read_text"] == nullable["read_text"]
    assert "game_id" not in corrupt["read_text"]
    assert foreign["read_status"] == 404
    assert case["game"] not in foreign["read_text"]
    assert case["tenant"] not in foreign["read_text"]
    # 負例の後片付けが効いていることを、同じ製品入口で再確認する。
    restored = _run_case(db, _read_case(db))
    assert restored["read_status"] == 200
    assert restored["read_body"]["read_kind"] == "recorded"
    # 状態構成に使った製品triggerが有効へ戻っていることを、DBの実値で確かめる。
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT tgname,tgenabled FROM pg_trigger "
            "WHERE tgname IN ('trg_first_ball_10_lock','trg_first_ball_20_admit',"
            "'trg_operation_events_content_immutable') ORDER BY tgname"
        ).fetchall() == [
            ("trg_first_ball_10_lock", "O"),
            ("trg_first_ball_20_admit", "O"),
            ("trg_operation_events_content_immutable", "O"),
        ]


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
