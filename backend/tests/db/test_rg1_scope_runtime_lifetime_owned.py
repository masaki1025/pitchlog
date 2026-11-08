"""実app/RG1/ownedPGの短い記録経路で、scope終結GCを強制する。"""

from __future__ import annotations

import json
import subprocess
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.db.current_product_startup import CURRENT_REVISION

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

_GC_PROBE_SOURCE = r"""
import gc, weakref
from pitchlog.repositories import transaction as _tx
from pitchlog.recording_rights import rg1_lifecycle as _rg1

def install_gc_probe():
    original_exit = _tx._TenantTransactionScope.__exit__
    original_release = _rg1._GateLoan.release
    observed = weakref.WeakKeyDictionary()
    counts = dict(scopes=0, gc=0, released=0, failed=0, untracked=0,
                  session_missing=0, engine_missing=0, metadata_failed=0)

    def remember(scope):
        handle = scope._handle
        key = None if handle is None else handle._state_key
        runtime = _tx._TRANSACTION_RUNTIMES.get(key)
        loan = _tx._RG1_LOANS.get(key)
        if runtime is None or type(loan) is not _rg1._GateLoan:
            return None
        session = runtime[0]
        observed[loan] = (weakref.ref(session), weakref.ref(session.bind))
        counts['scopes'] += 1
        return loan

    def scope_exit(self, *args, **kwargs):
        loan = None
        try:
            loan = remember(self)
        except BaseException:
            counts['metadata_failed'] += 1
        try:
            return original_exit(self, *args, **kwargs)
        finally:
            try:
                if loan is not None:
                    observed.pop(loan, None)
            except BaseException:
                counts['metadata_failed'] += 1

    def release(self):
        try:
            refs = observed.get(self)
            gc.collect()
            counts['gc'] += 1
            if refs is None:
                counts['untracked'] += 1
            else:
                counts['session_missing'] += refs[0]() is None
                counts['engine_missing'] += refs[1]() is None
        except BaseException:
            counts['metadata_failed'] += 1
        try:
            result = original_release(self)
        except BaseException:
            counts['failed'] += 1
            raise
        counts['released'] += 1
        return result

    _tx._TenantTransactionScope.__exit__ = scope_exit
    _rg1._GateLoan.release = release
    def snapshot():
        return dict(counts)
    def restore():
        _tx._TenantTransactionScope.__exit__ = original_exit
        _rg1._GateLoan.release = original_release
    return snapshot, restore
"""

_SCRIPT = (
    _APP_SCRIPT.split("async def run():", 1)[0]
    + _GC_PROBE_SOURCE
    + r"""
_snapshot, _restore = install_gc_probe()
async def short_run():
    global game
    statuses=[]
    async with AsyncClient(
        transport=ASGITransport(app=app),base_url='https://test'
    ) as client:
        logged=await login(client,team);statuses.append(['login',logged.status_code])
        assert logged.status_code==200
        preparation=await client.get('/games/'+game,headers=headers())
        statuses.append(['preparation',preparation.status_code])
        assert preparation.status_code==200
        saved=preparation.json()
        created=await client.post('/games',headers=headers(),json={
            'scheduled_at':saved['scheduled_at'],'game_type_key':saved['game_type_key'],
            'away_team_record_id':saved['away_team_record_id'],
            'home_team_record_id':saved['home_team_record_id'],
            'tournament':{'kind':'existing','key':saved['tournament_key']}})
        statuses.append(['create',created.status_code]);assert created.status_code==201
        game=created.json()['id'];assert game!=case['game']
        enrolled=await client.post('/devices/enroll',headers=headers())
        statuses.append(['enroll',enrolled.status_code])
        assert enrolled.status_code==200
        pair=enrolled.json();body=_body(10)
        body.update(device_id=pair['device_id'],device_credential=pair['device_credential'],
                    start_request_id=case['start_request_id'])
        started=await client.post('/games/'+game+'/start',json=body,headers=headers())
        statuses.append(['start',started.status_code]);assert started.status_code==200
        first=started.json();cookie=client.cookies.get('__Host-pitchlog_token')
        v7,v8,_people=payload_from_artifact(cookie)
        event={'d5':str(uuid4()),'d1':1,'d4':first['d4'],'game_id':game,
               'event_kind':'1','d2':1,'payload':json.loads(v7),'state_diff':json.loads(v8)}
        posted=await client.post('/games/'+game+'/sync/events',
            json={'recording_right_proof':first['recording_right_proof'],'events':[event]},
            headers=device_headers(pair,str(uuid4())))
        statuses.append(['sync',posted.status_code]);assert posted.status_code==200
        assert posted.json()['eventResults'][0]['a5Result']=='受理'
        after=await client.get('/games/'+game+'/started',headers=headers())
        statuses.append(['read',after.status_code]);assert after.status_code==200
        assert after.json()['after']['stateFields']['state.count.balls']=='1'
        return {'game_id':game,'statuses':statuses,'gc':_snapshot()}
try:
    result=asyncio.run(short_run())
finally:
    _restore()
print('RG1_SCOPE_GC_RESULT='+json.dumps(result))
"""
)


def test_actual_app_scope_gc_releases_same_live_backend(vertical_database, tmp_path):
    """真正UID/C2/loanで新規作成→開始→一球の終結をGC下でも通す。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchall() == [(CURRENT_REVISION,)]
        for table in (
            "public.play_rows",
            "public.operation_events",
            "public.event_slots",
        ):
            admin.execute(
                f"EXPLAIN SELECT count(*) FROM {table} "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, db.game_id),
            )
    case = dict(
        phase="record",
        tenant=str(db.tenant_id),
        game=str(db.game_id),
        team_name=db.team_name,
        password=_PASSWORD,
        start_request_id=str(db.start_request_id),
        pitch_type=_PITCH_TYPE,
        course=[132, 131],
    )
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        completed = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _SCRIPT],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    # 原本文/資格/SQLを含み得るstdout/stderrを失敗表示しない。
    lines = [
        line
        for line in completed.stdout.splitlines()
        if line.startswith("RG1_SCOPE_GC_RESULT=")
    ]
    assert completed.returncode == 0 and len(lines) == 1, "owned短scopeのGC終結が未成立"
    result = json.loads(lines[0].split("=", 1)[1])
    assert result["statuses"] == [
        ["login", 200],
        ["preparation", 200],
        ["create", 201],
        ["enroll", 200],
        ["start", 200],
        ["sync", 200],
        ["read", 200],
    ]
    seen = result["gc"]
    assert seen["scopes"] == seen["gc"] == seen["released"] > 0
    assert all(
        seen[name] == 0
        for name in (
            "failed",
            "untracked",
            "session_missing",
            "engine_missing",
            "metadata_failed",
        )
    )
    game = UUID(result["game_id"])
    assert game != db.game_id
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        for table in (
            "public.play_rows",
            "public.operation_events",
            "public.event_slots",
        ):
            assert admin.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, game),
            ).fetchone() == (1,)
    (tmp_path / "rg1-scope-gc-result.json").write_text(json.dumps(result, indent=2))
