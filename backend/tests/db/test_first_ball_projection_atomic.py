"""正式登録PlayRowの同TX原本/印/全41列と拒否・rollbackをowned PGで確認する。

記録済みevent/ledger/slotのadmin投入は使わない。ゲーム/名簿/語彙/認証は
fixture準備であり、実画面・同評価frame・実Port・HTTPの完成証拠ではない。
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from db_fixtures import _dsn_names

from pitchlog.repositories.initial_recording_right import _credential_digest

from .first_ball_stamp_support import require_formal_activation
from .sync_writer_binding_support import (
    binding_app,
    binding_broker,
    owned_binding_database,
)
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture(scope="module")
def projection_env() -> Iterator[Any]:
    """正規installerと初期権を持つ自己所有PGを準備する。"""
    with pytest.MonkeyPatch.context() as patch:
        with owned_binding_database(patch) as owner:
            admin_name, role_name = _dsn_names()
            patch.setenv(admin_name, owner.authority.database.primary_admin)
            patch.setenv(role_name, owner.authority.database.endpoints.primary_dsn)
            require_formal_activation(owner)
            issued = owner.actor("grant=issue(); print(json.dumps(receipt(grant)))")
            proof = bytes.fromhex(issued["proof_digest"])
            env = SimpleNamespace(
                owner=owner,
                ctx=SimpleNamespace(
                    admin_dsn=owner.authority.database.business_admin,
                    tenant=owner.tenant_id,
                    device=owner.device_id,
                    game=owner.game_id,
                    generation=int(issued["generation"]),
                    epoch=int(issued["epoch"]),
                    proof=proof,
                ),
                good=_credential_digest("credential-a"),
                bad=_credential_digest("credential-b"),
                bad_proof=bytes([proof[0] ^ 1]) + proof[1:],
            )
            token, subject = uuid4(), uuid4()
            players = [uuid4() for _ in range(3)]
            with psycopg.connect(env.ctx.admin_dsn) as admin:
                admin.execute(
                    "INSERT INTO public.system_settings(key,value) VALUES "
                    "('auth.token_ttl_seconds','3600') ON CONFLICT(key) "
                    "DO UPDATE SET value=EXCLUDED.value"
                )
                admin.execute(
                    "INSERT INTO public.tenant_auth_subjects(tenant_id,id) "
                    "VALUES (%s,%s)",
                    (owner.tenant_id, subject),
                )
                admin.execute(
                    "INSERT INTO public.tenant_credentials"
                    "(auth_subject_id,password_hash,"
                    "generation) VALUES (%s,'public-unused-login-vector',1)",
                    (subject,),
                )
                admin.execute(
                    "INSERT INTO public.tenant_tokens(tenant_id,id,auth_subject_id,"
                    "credential_generation,expires_at,last_used_at) VALUES "
                    "(%s,%s,%s,1,clock_timestamp()+interval '1 hour',"
                    "clock_timestamp())",
                    (owner.tenant_id, token, subject),
                )
                admin.execute(
                    "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                    "VALUES ('batting-result.ball','batting_result','ボール') "
                    "ON CONFLICT(key) DO NOTHING"
                )
                admin.execute(
                    "INSERT INTO public.tenant_vocabularies"
                    "(tenant_id,key,category,display_name,pitch_family) "
                    "VALUES (%s,'u06-fastball','pitch_type','直球','fastball')",
                    (owner.tenant_id,),
                )
                team = admin.execute(
                    "SELECT id FROM public.team_records WHERE tenant_id=%s "
                    "AND kind='self'",
                    (owner.tenant_id,),
                ).fetchone()
                assert team is not None
                status = admin.execute(
                    "SELECT key FROM public.system_vocabularies "
                    "WHERE category='roster_status' ORDER BY key LIMIT 1"
                ).fetchone()
                assert status is not None
                for player in players:
                    admin.execute(
                        "INSERT INTO public.players(tenant_id,id,team_record_id,"
                        "name,roster_status_key) VALUES (%s,%s,%s,'U06試験選手',%s)",
                        (owner.tenant_id, player, team[0], status[0]),
                    )
            env.token_id, env.players = token, players
            foreign_game, foreign_device = uuid4(), uuid4()
            foreign_token, foreign_subject = uuid4(), uuid4()
            foreign_players, foreign_teams = (
                [uuid4() for _ in range(3)],
                [uuid4(), uuid4()],
            )
            with psycopg.connect(env.ctx.admin_dsn) as admin:
                for idx, team in enumerate(foreign_teams):
                    admin.execute(
                        "INSERT INTO public.team_records(tenant_id,id,kind,name) "
                        "VALUES (%s,%s,%s,'別tenant試験チーム')",
                        (
                            owner.other_tenant_id,
                            team,
                            "self" if idx == 0 else "opponent",
                        ),
                    )
                admin.execute(
                    "INSERT INTO public.tenant_vocabularies"
                    "(tenant_id,key,category,display_name) VALUES "
                    "(%s,'u06-foreign-tournament','tournament','別tenant大会')",
                    (owner.other_tenant_id,),
                )
                admin.execute(
                    "INSERT INTO public.tenant_vocabularies"
                    "(tenant_id,key,category,display_name,pitch_family) VALUES "
                    "(%s,'u06-fastball','pitch_type','直球','fastball')",
                    (owner.other_tenant_id,),
                )
                admin.execute(
                    "INSERT INTO public.games(tenant_id,id,scheduled_at,game_type_key,"
                    "tournament_key,away_team_record_id,home_team_record_id,"
                    "applied_rules) "
                    "SELECT %s,%s,CURRENT_TIMESTAMP,'game_official',"
                    "'u06-foreign-tournament',%s,%s,applied_rules FROM public.games "
                    "WHERE tenant_id=%s AND id=%s",
                    (
                        owner.other_tenant_id,
                        foreign_game,
                        *foreign_teams,
                        owner.tenant_id,
                        owner.game_id,
                    ),
                )
                admin.execute(
                    "INSERT INTO public.trusted_devices"
                    "(tenant_id,device_id,credential_digest) VALUES (%s,%s,%s)",
                    (owner.other_tenant_id, foreign_device, env.good),
                )
                for player in foreign_players:
                    admin.execute(
                        "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
                        "roster_status_key) VALUES (%s,%s,%s,'別tenant選手',%s)",
                        (owner.other_tenant_id, player, foreign_teams[0], status[0]),
                    )
                admin.execute(
                    "INSERT INTO public.tenant_auth_subjects(tenant_id,id) "
                    "VALUES (%s,%s)",
                    (owner.other_tenant_id, foreign_subject),
                )
                admin.execute(
                    "INSERT INTO public.tenant_credentials"
                    "(auth_subject_id,password_hash,"
                    "generation) VALUES (%s,'public-unused-login-vector',1)",
                    (foreign_subject,),
                )
                admin.execute(
                    "INSERT INTO public.tenant_tokens(tenant_id,id,auth_subject_id,"
                    "credential_generation,expires_at,last_used_at) VALUES "
                    "(%s,%s,%s,1,clock_timestamp()+interval '1 hour',"
                    "clock_timestamp())",
                    (owner.other_tenant_id, foreign_token, foreign_subject),
                )
            # 初期記録権は実issuer、印は実bind/right、端末資格は上のfixture seed。
            foreign_grant = owner.actor(
                "selected=replace(owner,tenant_id=UUID('"
                + str(owner.other_tenant_id)
                + "'),game_id=UUID('"
                + str(foreign_game)
                + "'),device_id=UUID('"
                + str(foreign_device)
                + "'),start_request_id=uuid4(),attempt_id=uuid4())\n"
                "grant=issue(selected=selected,selected_context="
                "make_tenant_context(selected.tenant_id))\n"
                "print(json.dumps(receipt(grant)))"
            )
            env.foreign_game, env.foreign_device = foreign_game, foreign_device
            env.foreign_token, env.foreign_players = foreign_token, foreign_players
            env.foreign_grant = foreign_grant
            with binding_broker(owner, token):
                # 同じ実brokerが認証する別tenant Cookieで正規にnative投影を作る。
                body = f"""
from pitchlog.sync.tokens import (IdempotencyLedgerInsertToken,
 EventSlotInsertToken,OperationEventInsertToken)
from pitchlog.sync.first_ball_tokens import (FirstBallPlayRowInsertToken,
 FirstBallPlayRowReadToken)
cookie=signer.encode(UUID('{foreign_token}'))
verified=issue_tenant_context_from_presented_token(cookie,signer)
assert verified is not None
context,_=verified
a=AttemptBinding(AuthorityBinding(UUID(int=7101),UUID(int=7102),UUID(int=7103)),
 context.tenant_id,UUID('{foreign_device}'),UUID('{foreign_game}'),
 'fixture-foreign',{foreign_grant["generation"]},uuid4(),1,'public-foreign',1)
d5,event_id,row_id=uuid4(),uuid4(),uuid4()
fp='wire-v1:'+'c'*64
phase=EventPhaseBinding(a,uuid4(),1,1,d5,fp)
with tenant_transaction_scope(context) as tx:
 b=control.bind_writer(tx,context,phase,cookie=cookie)
 assert tx.run_function(_BindFirstBallDeviceToken(a.attempt_id,phase.phase_id,
  b._lease.nonce,a.device_id,a.game_id,bytes.fromhex('{env.good.hex()}'))).rows==((True,),)
 assert tx.run_function(_CheckFirstBallRightToken(a.attempt_id,phase.phase_id,
  b._lease.nonce,a.device_id,a.game_id,a.internal_generation,
  {foreign_grant["epoch"]},bytes.fromhex('{foreign_grant["proof_digest"]}'))).rows==((True,True),)
 assert tx.run(IdempotencyLedgerInsertToken(d5,'accepted',fp,'{{}}')).rows==((1,),)
 assert tx.run(EventSlotInsertToken(a.game_id,a.internal_generation,1)).rows==((1,),)
 assert tx.run(OperationEventInsertToken(event_id,a.game_id,d5,'play_input','{{}}',
  a.internal_generation,1,1,'{{}}')).rows==((1,),)
 value=FirstBallPlayRowInsertToken(row_id,a.game_id,event_id,a.internal_generation,
  1,1,d5,fp,UUID('{foreign_players[0]}'),UUID('{foreign_players[1]}'),
  UUID('{foreign_players[2]}'),'u06-fastball',0.0,1.0)
 assert tx.run(value).rows==((1,),)
 assert len(tx.run(FirstBallPlayRowReadToken(a.game_id,event_id)).rows)==1
print(json.dumps(dict(event_id=str(event_id),d5=str(d5),row_id=str(row_id))))
"""
                env.foreign = binding_app(owner, body)
                yield env


@pytest.fixture
def initial_scope_database(projection_env: Any) -> Any:
    """既identity autouseを同じowned PGへ束縛する。"""
    return projection_env.owner


@pytest.mark.parametrize(
    "mode",
    [
        "no-stamp",
        "bind-only",
        "bad-credential",
        "bad-proof",
        "other-d5",
        "other-tenant",
        "other-event",
        "other-game",
        "other-fingerprint",
        "prior-projection",
        "after-insert-fault",
        "accepted",
    ],
)
def test_owned_registered_projection_atomic(projection_env: Any, mode: str) -> None:
    """実token保存・読取と不正資格/別原本/途中故障の全取消を検証する。"""
    env = projection_env
    body = f"""
from dataclasses import replace
from pitchlog.repositories.first_ball_operations import PLAY_ROW_COLUMNS
from pitchlog.repositories.first_ball_operations import FirstBallOperationError
from pitchlog.sync.first_ball_tokens import (
 FirstBallPlayRowInsertToken,FirstBallPlayRowReadToken)
from pitchlog.sync.tokens import (
 EventSlotInsertToken,OperationEventInsertToken,IdempotencyLedgerInsertToken)
from sqlalchemy.exc import DBAPIError
MODE={mode!r}
FP='wire-v1:'+'a'*64
authority=AuthorityBinding(UUID(int=7101),UUID(int=7102),UUID(int=7103))
attempt=AttemptBinding(authority,context.tenant_id,UUID('{env.ctx.device}'),
 UUID('{env.ctx.game}'),'fixture-first-ball',{env.ctx.generation},uuid4(),1,'public-u06-request-fp',1)
d5,event_id,row_id=uuid4(),uuid4(),uuid4()
phase=EventPhaseBinding(attempt,uuid4(),1,1,d5,FP)
value=FirstBallPlayRowInsertToken(row_id,attempt.game_id,event_id,
 attempt.internal_generation,1,1,d5,FP,UUID('{env.players[0]}'),UUID('{env.players[1]}'),
 UUID('{env.players[2]}'),'u06-fastball',0.0,1.0)
class PlannedRollback(RuntimeError): pass
out={{}}
try:
 with tenant_transaction_scope(context) as tx:
  bound=control.bind_writer(tx,context,phase,cookie=cookie)
  if MODE!='no-stamp':
   digest=(bytes.fromhex('{env.good.hex()}') if MODE!='bad-credential'
    else bytes.fromhex('{env.bad.hex()}'))
   device=tx.run_function(_BindFirstBallDeviceToken(attempt.attempt_id,phase.phase_id,
    bound._lease.nonce,attempt.device_id,attempt.game_id,digest))
   assert device.rows==((MODE!='bad-credential',),)
  if MODE not in ('no-stamp','bind-only'):
   proof=(bytes.fromhex('{env.ctx.proof.hex()}') if MODE!='bad-proof'
    else bytes.fromhex('{env.bad_proof.hex()}'))
   right=tx.run_function(_CheckFirstBallRightToken(attempt.attempt_id,phase.phase_id,
    bound._lease.nonce,attempt.device_id,attempt.game_id,attempt.internal_generation,
    {env.ctx.epoch},proof))
   assert right.rows==((True,MODE!='bad-proof'),)
  assert tx.run(IdempotencyLedgerInsertToken(d5,'accepted',FP,'{{}}')).rows==((1,),)
  assert tx.run(EventSlotInsertToken(
   attempt.game_id,attempt.internal_generation,1)).rows==((1,),)
  assert tx.run(OperationEventInsertToken(
   event_id,attempt.game_id,d5,'play_input','{{}}',
   attempt.internal_generation,1,1,'{{}}')).rows==((1,),)
  if MODE=='other-d5': value=replace(value,d5=uuid4())
  elif MODE=='other-tenant':
   assert tx.run(FirstBallPlayRowReadToken(UUID('{env.foreign_game}'),
    UUID('{env.foreign["event_id"]}'))).rows==()
   value=replace(value,game_id=UUID('{env.foreign_game}'),
    source_event_id=UUID('{env.foreign["event_id"]}'),d5=UUID('{env.foreign["d5"]}'))
  elif MODE=='other-event': value=replace(value,source_event_id=uuid4())
  elif MODE=='other-game': value=replace(value,game_id=uuid4())
  elif MODE=='other-fingerprint':
   value=replace(value,source_fingerprint='wire-v1:'+'b'*64)
  result=tx.run(value)
  assert result.rows==((1,),)
  read=tx.run(FirstBallPlayRowReadToken(attempt.game_id,event_id))
  expected={{name:getattr(value,name) for name in (
   'id','game_id','source_event_id','batter_id','pitcher_id','catcher_id',
   'pitch_type_key','course_x','course_y','pitch_speed','stance','batting_side')}}
  expected.update(tenant_id=context.tenant_id,play_number=1,batting_order=1,
   event_kind='pitch',batting_result_key='batting-result.ball',version=1,
   migration_unverified=False)
  expected.update(dict.fromkeys((
   'strategy_key','strategy_detail_key','strategy_result_key','batter_status',
   'secondary_batting_result_key','raw_fielder_position','resolved_fielder_id',
   'batted_ball_type','batted_ball_strength','hit_x','hit_y','pickoff_type',
   'pickoff_detail','error_type','raw_error_position','resolved_error_player_id',
   'press','fake_run','comment','hidden_at','legacy_row_identifier','import_batch_id')))
  assert len(PLAY_ROW_COLUMNS)==41 and set(expected)==set(PLAY_ROW_COLUMNS)
  assert read.rows==(tuple(expected[c] for c in PLAY_ROW_COLUMNS),)
  if MODE=='prior-projection': tx.run(replace(value,id=uuid4()))
  if MODE=='after-insert-fault': raise PlannedRollback
  assert MODE=='accepted', '拒否対象が保存された'
except FirstBallOperationError:
 assert MODE in ('other-d5','other-tenant','other-event','other-game',
  'other-fingerprint','prior-projection')
 out['rejected']='preflight'
except DBAPIError as error:
 assert MODE in ('no-stamp','bind-only','bad-credential','bad-proof')
 assert error.orig.sqlstate=='42501'
 out['rejected']='db-stamp'
except PlannedRollback:
 assert MODE=='after-insert-fault'
 out['rejected']='after-insert-fault'
else:
 assert MODE=='accepted'
 out['accepted']=True
print(json.dumps(out))
"""
    before_foreign = _foreign_snapshot(env)
    result = binding_app(env.owner, body)
    assert _foreign_snapshot(env) == before_foreign
    assert result == (
        {"accepted": True}
        if mode == "accepted"
        else {"rejected": "db-stamp"}
        if mode in {"no-stamp", "bind-only", "bad-credential", "bad-proof"}
        else {"rejected": "after-insert-fault"}
        if mode == "after-insert-fault"
        else {"rejected": "preflight"}
    )
    with psycopg.connect(env.ctx.admin_dsn) as admin:
        for table in (
            "idempotency_ledger",
            "event_slots",
            "operation_events",
            "play_rows",
        ):
            assert admin.execute(
                "SELECT count(*) FROM public." + table + " WHERE tenant_id=%s",
                (env.ctx.tenant,),
            ).fetchone() == (int(mode == "accepted"),)
        stamps = admin.execute(
            "SELECT state,source_event_id IS NOT NULL,play_row_id IS NOT NULL "
            "FROM sync_fence.first_ball_write_admissions WHERE tenant_id=%s",
            (env.ctx.tenant,),
        ).fetchall()
        assert stamps == ([("consumed", True, True)] if mode == "accepted" else [])


def _foreign_snapshot(env: Any) -> str:
    """別tenant業務行/印の全値をhash化し、秘密や原値を失敗へ出さない。"""
    import hashlib
    import json

    values = {}
    with psycopg.connect(env.ctx.admin_dsn) as admin:
        for table in (
            "public.idempotency_ledger",
            "public.event_slots",
            "public.operation_events",
            "public.play_rows",
            "sync_fence.first_ball_write_admissions",
        ):
            values[table] = admin.execute(
                "SELECT to_jsonb(t)::text FROM "
                + table
                + " t WHERE tenant_id=%s ORDER BY to_jsonb(t)::text",
                (env.owner.other_tenant_id,),
            ).fetchall()
            assert len(values[table]) == 1
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def test_owned_fake_and_expired_token_calls_issue_zero_sql(projection_env: Any) -> None:
    """新token偽型・失効writer/handleは実Session SQLへ到達しない。"""
    body = """
from sqlalchemy import event
from pitchlog.repositories.transaction import _TRANSACTION_RUNTIMES
from pitchlog.repositories.base import _TenantOperationError
from pitchlog.sync.first_ball_tokens import (
 FirstBallPlayRowReadToken,FirstBallPlayRowInsertToken)
from pitchlog.sync.ports import _issue_port_writer
class ForgedRead(FirstBallPlayRowReadToken): pass
class ForgedInsert(FirstBallPlayRowInsertToken): pass
statements=[]
with tenant_transaction_scope(context) as tx:
 session,_=_TRANSACTION_RUNTIMES[tx._state_key]
 engine=session.get_bind()
 def observe(*args): statements.append(True)
 event.listen(engine,'before_cursor_execute',observe)
 try:
  writer=_issue_port_writer(tx.run)
  for fake in (ForgedRead,ForgedInsert):
   try: writer.run(object.__new__(fake))
   except _TenantOperationError: pass
   else: raise AssertionError('偽型成功')
  assert statements==[]
  writer._close()
  for kind in (FirstBallPlayRowReadToken,FirstBallPlayRowInsertToken):
   try: writer.run(object.__new__(kind))
   except RuntimeError: pass
   else: raise AssertionError('失効writer成功')
  assert statements==[]
 finally:
  event.remove(engine,'before_cursor_execute',observe)
event.listen(engine,'before_cursor_execute',observe)
try:
 for kind in (FirstBallPlayRowReadToken,FirstBallPlayRowInsertToken):
  try: tx.run(object.__new__(kind))
  except RuntimeError: pass
  else: raise AssertionError('失効handle成功')
 assert statements==[]
finally:
 event.remove(engine,'before_cursor_execute',observe)
print(json.dumps(dict(fake_rejected=True,expired_writer=True,expired_handle=True,sql=0)))
"""
    assert binding_app(projection_env.owner, body) == dict(
        fake_rejected=True, expired_writer=True, expired_handle=True, sql=0
    )
