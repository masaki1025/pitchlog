"""U13の実Cookie→開始→0球再取得を所有3PGで確認する。作成はfixtureのみ。"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from .test_api_auth_exit_entry import TestInitialGameStartHttpOwned as _StartFixtures

pytestmark = pytest.mark.requires_db


def _clone_started(db: Any, changes: dict[str, dict[str, Any]]) -> UUID:
    """Owned fixtureに不可視/破損例を新規構築し、製品の不変UPDATEを迂回しない。"""
    game = uuid4()
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for table in ("games", "recording_generations", "game_lineups"):
            key = "id" if table == "games" else "game_id"
            rows = admin.execute(
                sql.SQL(
                    "SELECT to_jsonb(r) FROM public.{} r WHERE tenant_id=%s AND {}=%s"
                ).format(sql.Identifier(table), sql.Identifier(key)),
                (db.tenant_id, db.game_id),
            ).fetchall()
            for index, (row,) in enumerate(rows):
                selected = changes.get(table, {})
                if (
                    selected.get("omit_all")
                    or selected.get("omit_first")
                    and index == 0
                ):
                    continue
                row[key] = str(game)
                if table == "game_lineups":
                    row["id"] = str(uuid4())
                row.update(
                    {k: v for k, v in selected.items() if not k.startswith("omit_")}
                )
                admin.execute(
                    sql.SQL(
                        "INSERT INTO public.{} SELECT "
                        "(jsonb_populate_record(NULL::public.{},%s)).*"
                    ).format(sql.Identifier(table), sql.Identifier(table)),
                    (Jsonb(row),),
                )
    return game


def _digests(db: Any) -> dict[str, str]:
    """要求前後の実表全行digestだけを返し、DB値や資格を報告へ出さない。"""
    result = {}
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for table in (
            "games",
            "recording_generations",
            "event_slots",
            "operation_events",
            "play_rows",
        ):
            rows = admin.execute(
                sql.SQL(
                    "SELECT to_jsonb(r)::text FROM public.{} r "
                    "ORDER BY to_jsonb(r)::text"
                ).format(sql.Identifier(table))
            ).fetchall()
            result[table] = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    return result


def _assert_no_log_leak(
    text: str, known: tuple[str, ...], fingerprints: tuple[tuple[int, str], ...] = ()
) -> None:
    """実識別値/資格/SQL診断を拒否し、反例自体の値は例外へ含めない。"""
    for value in known:
        assert value and value not in text, "既知の入力/資格がログへ漏洩"
    assert not re.search(
        r"(?i)\b(?:SELECT|INSERT|UPDATE|DELETE)\s|permission denied|"
        r"psycopg|sqlalchemy|SQLSTATE|OperationalError|ProgrammingError",
        text,
    ), "SQL/原例外診断がログへ漏洩"
    for length, expected in fingerprints:
        for index in range(max(0, len(text) - length + 1)):
            actual = hashlib.sha256(text[index : index + length].encode()).hexdigest()
            assert actual != expected, "前段peerの実資格がログへ漏洩"


class TestStartedGameReadHttpOwned:
    """既owned3PG/worker/app UID fixtureを変更せず委譲する。"""

    initial_scope_database = _StartFixtures.initial_scope_database
    admin_connection = _StartFixtures.admin_connection
    tested_role_connection = _StartFixtures.tested_role_connection
    start_database = _StartFixtures.start_database

    def test_h1_h8_real_start_then_initial_read(self, start_database: Any) -> None:
        """H1〜H8: 実開始・再取得・拒否・書込0・実TX特性をowned PGで観測する。"""
        db = start_database
        password = "public-owned-u13-password-A1"
        names = {}
        with psycopg.connect(db.authority.database.business_admin) as admin:
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
            for tenant in (db.tenant_id, db.other_tenant_id):
                subject = uuid4()
                admin.execute(
                    "INSERT INTO public.tenant_auth_subjects(id,tenant_id) "
                    "VALUES (%s,%s)",
                    (subject, tenant),
                )
                admin.execute(
                    "INSERT INTO public.tenant_credentials"
                    "(auth_subject_id,password_hash) "
                    "VALUES (%s,authn_crypto.crypt(%s,authn_crypto.gen_salt('bf',12)))",
                    (subject, password),
                )
                row = admin.execute(
                    "SELECT name FROM public.tenants WHERE id=%s", (tenant,)
                ).fetchone()
                assert row is not None
                names[str(tenant)] = row[0]
        args = db._broker_arguments(uid=20003)
        args[1:1] = [
            "--volume",
            f"{db.authority.database.business_socket}:/business-socket:ro",
        ]
        prefix = rf"""
import os,sys,json,asyncio,base64,traceback,io,logging,hashlib
from time import perf_counter
from uuid import uuid4
assert os.geteuid()==20003 and os.getegid()==20003
os.environ['PITCHLOG_TOKEN_SIGNING_KEY_B64']=base64.b64encode(bytes(range(32))).decode()
os.environ['PITCHLOG_ALLOWED_ORIGINS']='https://test'
os.environ['PITCHLOG_DATABASE_URL']='postgresql+psycopg://pitchlog_app@/ledger_fixture?host=%2Fbusiness-socket&sslmode=disable'
os.environ['PITCHLOG_DATABASE_POOLED']='false'
sys.path.insert(0,'/fixture/backend/tests')
from httpx import AsyncClient,ASGITransport
from pitchlog.api.app import create_app
from pitchlog.api.schemas.started_games import StartedGameRead
from test_initial_game_start_components import _body
from db.test_started_game_read_http import _assert_no_log_leak
_stderr=io.StringIO();sys.stderr=_stderr
_log_records=[]
class Capture(logging.Handler):
    def emit(self,record):
        _log_records.append(logging.Formatter().format(record))
_product_log=logging.getLogger('pitchlog')
_product_log.setLevel(logging.DEBUG)
_product_log.addHandler(Capture())
_product_log.warning('U13 capture control')
app=create_app()
tenant='{db.tenant_id}';other='{db.other_tenant_id}';game='{db.game_id}'
names={names!r};password={password!r}
def error_hook(kind,value,tb):
    print(json.dumps({{'fixture_failure':kind.__name__,
        'phase':globals().get('phase','initial'),
        'frames':[(f.name,f.lineno) for f in traceback.extract_tb(tb)]}}),flush=True)
sys.excepthook=error_hook
def headers(selected=tenant):
    return {{'Origin':'https://test','X-Pitchlog-Request':'1',
        'X-Pitchlog-Expected-Tenant':selected,'X-Pitchlog-Tenant-Challenge':str(uuid4())}}
def metadata(response,h,success):
    assert response.headers['cache-control']=='no-store'
    if success:
        assert response.headers['X-Pitchlog-Tenant-Match']=='1'
        challenge=h['X-Pitchlog-Tenant-Challenge']
        assert response.headers['X-Pitchlog-Tenant-Challenge']==challenge
    else:
        assert 'X-Pitchlog-Tenant-Match' not in response.headers
        assert 'X-Pitchlog-Tenant-Challenge' not in response.headers
def checked_logs(values=(),fingerprints=()):
    assert 'U13 capture control' in _log_records
    known=(tenant,other,game,password,*names.values(),
           *[str(__import__('uuid').UUID(int=x)) for x in range(101,111)],
           *[str(__import__('uuid').UUID(int=x)) for x in range(201,211)],*values)
    _assert_no_log_leak('\n'.join(_log_records)+_stderr.getvalue(),known,
                        tuple(tuple(x) for x in fingerprints))
async def run():
    async with AsyncClient(
        transport=ASGITransport(app=app),base_url='https://test'
    ) as client:
        response=await client.post('/auth/login',json={{'team_name':names[tenant],
            'password':password}},headers={{'Origin':'https://test','X-Pitchlog-Request':'1'}})
        assert response.status_code==200
        assert '__Host-pitchlog_token' in client.cookies
        assert 'Secure' in response.headers['set-cookie']
        assert 'HttpOnly' in response.headers['set-cookie']
        h=headers();enrolled=await client.post('/devices/enroll',headers=h)
        assert enrolled.status_code==200;metadata(enrolled,h,True)
        pair=enrolled.json()
        h=headers();pre=await client.get('/games/'+game,headers=h)
        assert pre.status_code==200;metadata(pre,h,True)
        h=headers();absent=await client.get('/games/'+game+'/started',headers=h)
        assert absent.status_code==404;metadata(absent,h,False)
        body=_body(10);body.update(device_id=pair['device_id'],
            device_credential=pair['device_credential'],start_request_id='{db.start_request_id}')
        h=headers()
        started=await client.post('/games/'+game+'/start',json=body,headers=h)
        assert started.status_code==200;metadata(started,h,True)
        first=started.json()
        h=headers();pre=await client.get('/games/'+game,headers=h)
        assert pre.status_code==404;metadata(pre,h,False)
        assert pre.content==absent.content
        times=[];values=[]
        for _ in range(10):
            h=headers();begin=perf_counter()
            read=await client.get('/games/'+game+'/started',headers=h)
            times.append(perf_counter()-begin)
            assert read.status_code==200;metadata(read,h,True)
            value=read.json();values.append(value)
            assert set(value)==set(StartedGameRead.model_fields)
            assert value['status']=='in_progress' and value['read_kind']=='initial'
            assert value['started_at']==first['started_at']
            assert value['current_d4']==first['d4']
            assert value['lineups']['away']['lineup_id']==first['away_lineup_id']
            assert value['lineups']['home']['lineup_id']==first['home_lineup_id']
            fields=value['state']['stateFields']
            assert [fields[k] for k in (
                'state.count.balls','state.count.strikes','state.outs')]==['0']*3
            assert fields['state.inning']=='1' and fields['state.half']=='top'
            for side in ('away','home'):
                assert [r['player_id'] for r in value['lineups'][side]['entries']]==[
                    r['player_id'] for r in body[side]]
                projected=value['roster']['teams'][0 if side=='away' else 1]
                assert projected['side']==side
                assert projected['team_id']==value[side+'_team_record_id']
                expected=[]
                for entry in body[side]:
                    role=dict(entry['fielding_position'])
                    if role['kind']=='fielding':
                        role['position']=str(role['position'])
                    slot=entry['batting_order']
                    expected.append({{'player':{{'kind':'official',
                        'player_id':entry['player_id']}},
                        'batting_slot':{{'kind':'none'}} if slot is None else {{
                            'kind':'slot','slot':str(slot)}},
                        'roles':[role],'entry_origin':{{'kind':'initial'}}}})
                assert projected['participants']==expected
            for secret in (pair['device_id'],pair['device_credential'],
                           first['recording_right_proof']):
                assert secret not in read.text
            for key in ('device_id','device_credential','recording_right_proof',
                        'recovery_generation',
                        'watermark','prefix','holder_device'):
                assert key not in read.text
        assert all(v==values[0] for v in values)
        from sqlalchemy import event,Engine
        observed=[]
        def observe(conn,cursor,statement,parameters,context,executemany):
            import re
            if re.search(r'\b(?:public\.)?games\b',statement,re.I):
                observed.append(1)
        event.listen(Engine,'before_cursor_execute',observe)
        try:
            control=await client.get('/games/'+game+'/started',headers=headers())
            assert control.status_code==200 and len(observed)>0
            observed.clear()
            async with AsyncClient(
                transport=ASGITransport(app=app),base_url='https://test'
            ) as anonymous:
                unauth=await anonymous.get('/games/'+game+'/started',headers=headers())
                assert unauth.status_code==401
            bad_challenge={{**headers(),'X-Pitchlog-Tenant-Challenge':'bad'}}
            for bad in (headers(other),bad_challenge):
                denied=await client.get('/games/'+game+'/started',headers=bad)
                assert denied.status_code==404;metadata(denied,bad,False)
            assert observed==[]
        finally:
            event.remove(Engine,'before_cursor_execute',observe)
        import psycopg
        probe_dsn=('host=/business-socket dbname=ledger_fixture '
                   'user=pitchlog_app sslmode=disable')
        with psycopg.connect(probe_dsn) as probe:
            who=probe.execute('SELECT current_user,session_user').fetchone()
            assert who==('pitchlog_app','pitchlog_app')
            probe.rollback()
            probe.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ WRITE')
            lock='SELECT id FROM public.games WHERE false FOR UPDATE'
            probe.execute(lock).fetchall()
            assert probe.execute('SHOW transaction_read_only').fetchone()==('off',)
            probe.rollback()
            probe.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            try:
                probe.execute(lock).fetchall()
            except psycopg.Error as exc:
                assert exc.sqlstate=='25006'
                probe_state=exc.sqlstate
                probe_message=exc.diag.message_primary
                assert 'read-only' in str(exc).lower()
            else:
                raise AssertionError('READ ONLYがlock読取を拒否しなかった')
            finally:
                probe.rollback()
        raw_values=(pair['device_id'],pair['device_credential'],
                    first['recording_right_proof'],first['away_lineup_id'],
                    first['home_lineup_id'],value['away_team_record_id'],
                    value['home_team_record_id'],
                    client.cookies.get('__Host-pitchlog_token'))
        checked_logs((pair['device_id'],*raw_values))
        fingerprints=[(len(v),hashlib.sha256(v.encode()).hexdigest())
                      for v in raw_values]
        print(json.dumps({{'secret_fingerprints':fingerprints,
            'h1':True,'h3':True,'h4':True,'h7':True,'h8':True,
            'readonly_sqlstate':probe_state,'readonly_message':probe_message,
            'games_sql_on_denial':len(observed),'read_seconds':times}}),flush=True)
asyncio.run(run())
"""
        try:
            with db.broker_worker(uuid4()):
                process = subprocess.run(
                    ["docker", *args, "-u", "-c", prefix],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            try:
                value = json.loads(process.stdout)
            except ValueError:
                raise AssertionError("U13 app peerの安全応答が非JSON") from None
            assert process.returncode == 0, value
            assert value["h1"] and value["h3"] and value["h4"]
            assert len(value["read_seconds"]) == 10
            public_players = tuple(
                str(UUID(int=x)) for x in (*range(101, 111), *range(201, 211))
            )
            first_known = (
                str(db.tenant_id),
                str(db.other_tenant_id),
                str(db.game_id),
                password,
                *names.values(),
                *public_players,
            )
            _assert_no_log_leak(
                process.stderr,
                first_known,
                tuple(tuple(x) for x in value["secret_fingerprints"]),
            )
            print(json.dumps(value, sort_keys=True))
            invisible = [
                uuid4(),
                _clone_started(db, {"games": {"hidden_at": "2026-10-28T00:00:00Z"}}),
                _clone_started(db, {"games": {"trashed_at": "2026-10-28T00:00:00Z"}}),
                _clone_started(db, {"games": {"import_batch_id": str(uuid4())}}),
                _clone_started(db, {"games": {"status": "preparing"}}),
                _clone_started(db, {"games": {"status": "finished"}}),
            ]
            teams = (uuid4(), uuid4())
            with psycopg.connect(db.authority.database.business_admin) as admin:
                for index, team in enumerate(teams):
                    admin.execute(
                        "INSERT INTO public.team_records(tenant_id,id,kind,name) "
                        "VALUES (%s,%s,%s,'U13別tenant fixture')",
                        (
                            db.other_tenant_id,
                            team,
                            "self" if index == 0 else "opponent",
                        ),
                    )
                admin.execute(
                    "INSERT INTO public.tenant_vocabularies"
                    "(tenant_id,key,category,display_name) "
                    "SELECT %s,tournament_key,'tournament','U13 fixture' "
                    "FROM public.games WHERE tenant_id=%s AND id=%s",
                    (db.other_tenant_id, db.tenant_id, db.game_id),
                )
            invisible.append(
                _clone_started(
                    db,
                    {
                        "games": {
                            "tenant_id": str(db.other_tenant_id),
                            "away_team_record_id": str(teams[0]),
                            "home_team_record_id": str(teams[1]),
                        },
                        "recording_generations": {"omit_all": True},
                        "game_lineups": {"omit_all": True},
                    },
                )
            )
            corrupt = [
                _clone_started(db, {"game_lineups": {"omit_first": True}}),
                _clone_started(
                    db,
                    {"recording_generations": {"revoked_at": "2026-10-28T00:00:00Z"}},
                ),
                _clone_started(
                    db,
                    {"recording_generations": {"retired_at": "2026-10-28T00:00:00Z"}},
                ),
                _clone_started(
                    db,
                    {
                        "recording_generations": {
                            "kind": "migration",
                            "holder_device": None,
                        }
                    },
                ),
                _clone_started(db, {"recording_generations": {"omit_all": True}}),
            ]
            recorded = _clone_started(db, {})
            with psycopg.connect(db.authority.database.business_admin) as admin:
                admin.execute(
                    "INSERT INTO public.event_slots(tenant_id,game_id,generation,d1) "
                    "VALUES (%s,%s,1,1)",
                    (db.tenant_id, recorded),
                )
            before = _digests(db)
            # 初回成功scriptの共通定義だけを再利用し、開始・登録を重複実行しない。
            check = (
                prefix.split("async def run():", 1)[0]
                + f"""
async def run():
    async with AsyncClient(
        transport=ASGITransport(app=app),base_url='https://test'
    ) as client:
        response=await client.post('/auth/login',json={{'team_name':names[tenant],
            'password':password}},headers={{'Origin':'https://test','X-Pitchlog-Request':'1'}})
        assert response.status_code==200
        h=headers();pre404=await client.get('/games/'+game,headers=h)
        assert pre404.status_code==404
        fixed_error={{'error':{{'message':'リクエストを処理できません'}}}}
        bodies=[]
        for ident in {[str(x) for x in invisible]!r}:
            h=headers();response=await client.get('/games/'+ident+'/started',headers=h)
            assert response.status_code==404;metadata(response,h,False)
            bodies.append(response.content)
            assert 'd4' not in response.text
        assert len(set(bodies))==1 and bodies[0]==pre404.content
        h=headers();recorded=await client.get('/games/{recorded}/started',headers=h)
        global phase
        phase=['H5',recorded.status_code]
        assert recorded.status_code==409 and recorded.json()==fixed_error
        metadata(recorded,h,False)
        checked_logs(tuple({[str(x) for x in invisible]!r})+('{recorded}',
            client.cookies.get('__Host-pitchlog_token')),{value["secret_fingerprints"]!r})
        cookie=client.cookies.get('__Host-pitchlog_token')
        summary={{'h2':len({[str(x) for x in invisible]!r}),'h5':True,
            'cookie_fingerprint':[len(cookie),hashlib.sha256(cookie.encode()).hexdigest()]}}
        print(json.dumps(summary),flush=True)
asyncio.run(run())
"""
            )
            process = subprocess.run(
                ["docker", *args, "-u", "-c", check],
                capture_output=True,
                text=True,
                timeout=120,
            )
            try:
                summary = json.loads(process.stdout)
            except ValueError:
                raise AssertionError("U13拒否peerの安全応答が非JSON") from None
            assert process.returncode == 0, summary
            cookie_fp = tuple(summary.pop("cookie_fingerprint"))
            assert summary == {"h2": 7, "h5": True}
            after = _digests(db)
            assert after == before, "GET拒否で製品5表へ書き込んだ"
            print(json.dumps({"write_zero_digests": after}, sort_keys=True))
            known = (
                *first_known,
                *tuple(
                    str(x)
                    for x in (
                        db.tenant_id,
                        db.other_tenant_id,
                        db.game_id,
                        recorded,
                        *invisible,
                        *corrupt,
                    )
                ),
            )
            fingerprints = tuple(tuple(x) for x in value["secret_fingerprints"])
            _assert_no_log_leak(process.stderr, known, (*fingerprints, cookie_fp))
            for index, ident in enumerate(corrupt):
                case_before = _digests(db)
                case = (
                    prefix.split("async def run():", 1)[0]
                    + f"""
async def run():
    async with AsyncClient(
        transport=ASGITransport(app=app),base_url='https://test'
    ) as client:
        response=await client.post('/auth/login',json={{'team_name':names[tenant],
            'password':password}},headers={{'Origin':'https://test','X-Pitchlog-Request':'1'}})
        assert response.status_code==200
        h=headers();response=await client.get('/games/{ident}/started',headers=h)
        global phase
        phase=['H6',{index},response.status_code]
        assert response.status_code==503;metadata(response,h,False)
        assert response.json()=={{'error':{{'message':'リクエストを処理できません'}}}}
        checked_logs(('{ident}',client.cookies.get('__Host-pitchlog_token')),
                     {value["secret_fingerprints"]!r})
        cookie=client.cookies.get('__Host-pitchlog_token')
        print(json.dumps({{'cookie_fingerprint':[len(cookie),
            hashlib.sha256(cookie.encode()).hexdigest()],
            'h6_case':{index},'status':response.status_code,
            'body_sha256':hashlib.sha256(response.content).hexdigest()}}),flush=True)
asyncio.run(run())
"""
                )
                process = subprocess.run(
                    ["docker", *args, "-u", "-c", case],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                try:
                    result = json.loads(process.stdout)
                except ValueError:
                    raise AssertionError("U13破損peerの安全応答が非JSON") from None
                assert process.returncode == 0, result
                cookie_fp = tuple(result.pop("cookie_fingerprint"))
                assert result["h6_case"] == index and result["status"] == 503
                case_after = _digests(db)
                assert case_after == case_before, "破損GET1件で製品5表へ書き込んだ"
                _assert_no_log_leak(process.stderr, known, (*fingerprints, cookie_fp))
                print(
                    json.dumps(
                        {
                            "h6_case": index,
                            "before": case_before,
                            "after": case_after,
                            "response": result,
                        },
                        sort_keys=True,
                    )
                )
            print(json.dumps(summary, sort_keys=True))
        finally:
            subprocess.run(
                ["docker", "rm", "--force", args[args.index("--name") + 1]],
                capture_output=True,
                timeout=45,
            )
