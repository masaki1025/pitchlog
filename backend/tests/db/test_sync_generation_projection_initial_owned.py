"""所有初期scopeの実appで世代12列と保護列拒否を検査する。"""

from __future__ import annotations

import json
import subprocess
from uuid import uuid4

import psycopg
import pytest

from .durable_rights_ledger_support import docker
from .initial_recording_right_scope_support import InitialGrantDatabase
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    initial_scope_database as initial_scope_database,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db


def _run_initial_app(owner: InitialGrantDatabase, body: str) -> dict[str, object]:
    """既所有容器のapp peerを起動し、資格を含む例外本文を捨てる。"""
    args = owner._broker_arguments(uid=20003)
    args[1:1] = [
        "--volume",
        owner.authority.database.business_socket + ":/business-socket:ro",
    ]
    setup = """
import json,os,sys,traceback
# 製品import/認証より先に例外値の出力を遮断する。
def error_hook(kind,value,tb):
 print(json.dumps({'fixture_failure':kind.__name__,
  'frames':[(f.name,f.lineno) for f in traceback.extract_tb(tb)]}),flush=True)
sys.excepthook=error_hook
os.environ['PITCHLOG_DATABASE_URL']=('postgresql+psycopg://pitchlog_app@/'
 'ledger_fixture?host=%2Fbusiness-socket&sslmode=disable')
os.environ['PITCHLOG_DATABASE_POOLED']='false'
from pathlib import Path
from uuid import UUID
import psycopg
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import _activate_presentation
from pitchlog.repositories.tenant_context_issuance import (
 issue_tenant_context_from_presented_token)
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.recording_rights.rg1_lifecycle import configure_runtime
assert os.geteuid()==20003
signer=TokenPresentation(bytes(range(32)));_activate_presentation(signer)
cookie=Path('/control/public/worker-cookie').read_text()
issued=issue_tenant_context_from_presented_token(cookie,signer)
assert issued is not None
context,_=issued
configure_runtime(Path('/control/initial/app-generation-read-client.json'))
"""
    try:
        result = subprocess.run(
            ["docker", *args, "-u", "-c", setup + body],
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise AssertionError("実初期scope appの起動/期限が非成功") from None
    if result.returncode:
        try:
            failure = json.loads(result.stdout)
            assert type(failure) is dict and set(failure) == {
                "fixture_failure",
                "frames",
            }
        except (ValueError, AssertionError):
            raise AssertionError("実初期scope appの検査が非成功") from None
        raise AssertionError(f"実初期scope appの検査が非成功: {failure}")
    value = json.loads(result.stdout)
    assert type(value) is dict
    return value


def test_initial_owned_generation_projection_lock_and_column_denials(
    initial_scope_database: InitialGrantDatabase,
) -> None:
    """実Cookie/正規scopeの三token、別peer lock競合、保護2列拒否を分ける。"""
    owner = initial_scope_database
    # 既actorの低水準準備。画面/開始HTTPによる生成の成功証拠ではない。
    issued = owner.actor("grant=issue(); print(json.dumps(receipt(grant)))")
    token, subject = uuid4(), uuid4()
    with psycopg.connect(owner.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.system_settings(key,value) VALUES "
            "('auth.token_ttl_seconds','3600') ON CONFLICT(key) "
            "DO UPDATE SET value=EXCLUDED.value"
        )
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(tenant_id,id) VALUES (%s,%s)",
            (owner.tenant_id, subject),
        )
        admin.execute(
            "INSERT INTO public.tenant_credentials(auth_subject_id,password_hash,"
            "generation) VALUES (%s,'public-unused-login-vector',1)",
            (subject,),
        )
        admin.execute(
            "INSERT INTO public.tenant_tokens(tenant_id,id,auth_subject_id,"
            "credential_generation,expires_at,last_used_at) VALUES "
            "(%s,%s,%s,1,clock_timestamp()+interval '1 hour',clock_timestamp())",
            (owner.tenant_id, token, subject),
        )
        assert admin.execute(
            "SELECT has_column_privilege('pitchlog_app', "
            "'public.recording_generations','proof_digest','SELECT'), "
            "has_column_privilege('pitchlog_app', "
            "'public.recording_generations','recovery_generation','SELECT')"
        ).fetchone() == (False, False)
    # rootの既設定をコピーしapp UIDだけ指定。ACL/role/正本DDLを修復しない。
    docker(
        *owner.authority.command(root=True),
        "-c",
        "import json,os; from pathlib import Path; "
        "p=Path('/control/initial/client.json'); c=json.loads(p.read_text()); "
        "assert c['application_uid']==20002; c['application_uid']=20003; "
        "p=Path('/control/initial/app-generation-read-client.json'); "
        "p.write_text(json.dumps(c)); p.chmod(0o644); assert p.stat().st_uid==0",
    )
    body = f"""
from pitchlog.sync.tokens import (RECORDING_GENERATION_READ_COLUMNS,
 RecordingGenerationReadToken,RecordingGenerationByNumberReadToken,
 RecordingGenerationLockToken)
expected=('tenant_id','game_id','generation','kind','issuance_order',
 'holder_device','confirmed_watermark','applied_prefix','granted_at',
 'revoked_at','import_batch_id','retired_at')
assert RECORDING_GENERATION_READ_COLUMNS==expected
assert context.tenant_id==UUID('{owner.tenant_id}')
game=UUID('{owner.game_id}'); generation={issued["generation"]}
params=(context.tenant_id,game,generation)
peer=dict(host='/business-socket',dbname='ledger_fixture',
 user='pitchlog_app',passfile='/dev/null',autocommit=True)
with tenant_transaction_scope(context) as tx:
 rows=[tx.run(t).rows for t in (RecordingGenerationReadToken(game),
  RecordingGenerationByNumberReadToken(game,generation),
  RecordingGenerationLockToken(game,generation))]
 assert all(len(r)==1 and len(r[0])==12 for r in rows)
 assert rows[0]==rows[1]==rows[2]
 assert rows[0][0][expected.index('generation')]==generation
 assert rows[0][0][expected.index('tenant_id')]==context.tenant_id
 assert rows[0][0][expected.index('game_id')]==game
 # 別app peerも同一transactionへtenantを束縛し、行可視性を先に確認する。
 with psycopg.connect(**peer) as observer:
  assert observer.execute('SELECT session_user,current_user').fetchone()==(
   'pitchlog_app','pitchlog_app')
  try:
   with observer.transaction():
    observer.execute("SELECT set_config('app.tenant_id',%s,true)",
     (str(context.tenant_id),))
    assert observer.execute('SELECT generation FROM public.recording_generations '
     'WHERE tenant_id=%s AND game_id=%s AND generation=%s',params
    ).fetchone()==(generation,)
    observer.execute('SELECT generation FROM public.recording_generations '
     'WHERE tenant_id=%s AND game_id=%s AND generation=%s FOR UPDATE NOWAIT',params)
  except psycopg.errors.LockNotAvailable as error:
   # transaction contextは例外でrollback済み。失敗TXを次の観測へ流用しない。
   assert error.sqlstate=='55P03'
  else: raise AssertionError('generation token did not retain row lock')
# scope終了後の新TXでtenantを再束縛してlock取得を確認する。
with psycopg.connect(**peer) as observer:
 with observer.transaction():
  observer.execute("SELECT set_config('app.tenant_id',%s,true)",
   (str(context.tenant_id),))
  assert observer.execute('SELECT generation FROM public.recording_generations '
   'WHERE tenant_id=%s AND game_id=%s AND generation=%s FOR UPDATE NOWAIT',params
  ).fetchone()==(generation,)
 # 各列を別TXで確認し、42501による失敗TXも次の列へ流用しない。
 for column in ('proof_digest','recovery_generation'):
  statement=psycopg.sql.SQL('SELECT {{}} FROM public.recording_generations LIMIT 0'
   ).format(psycopg.sql.Identifier(column))
  try:
   with observer.transaction():
    observer.execute("SELECT set_config('app.tenant_id',%s,true)",
     (str(context.tenant_id),))
    observer.execute(statement)
  except psycopg.errors.InsufficientPrivilege as error:
   assert error.sqlstate=='42501'
  else: raise AssertionError('protected column SELECT acknowledged')
print(json.dumps(dict(three_actual_tokens=True,held_lock_conflict=True,
 released_lock=True,protected_select_denied=2)))
"""
    with owner.broker_worker(token):
        assert _run_initial_app(owner, body) == {
            "three_actual_tokens": True,
            "held_lock_conflict": True,
            "released_lock": True,
            "protected_select_denied": 2,
        }
