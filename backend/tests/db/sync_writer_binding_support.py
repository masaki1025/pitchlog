"""製品migration/認可適用済みowned DBでだけ限定SQLを検査する。"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from . import initial_recording_right_scope_support as initial_support
from .initial_recording_right_scope_support import InitialGrantDatabase
from .rg1_lifecycle_support import PeerSession, docker

ACTOR = "pitchlog_sync_binding_actor"
APP = "pitchlog_app"


class BindingPeer(PeerSession):
    """SET ROLEなしの実app/制御UID・peer LOGINを保持する。"""

    def __init__(self, container: str, database: str, role: str) -> None:
        """製品で既登録された2role以外を開かない。"""
        if role not in {ACTOR, APP}:
            raise ValueError("binding試験の対象外role")
        uid = 20005 if role == ACTOR else 20003
        self._process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                "--user",
                f"{uid}:{uid}",
                container,
                "psql",
                "-X",
                "-A",
                "-t",
                "-q",
                "-h",
                "/var/run/postgresql",
                "-U",
                role,
                "-d",
                database,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._buffer = b""
        self._sequence = 0
        try:
            assert self.query("SELECT session_user,current_user") == (f"{role}|{role}",)
        except BaseException:
            self.close()
            raise


def _literal(value: object) -> str:
    """試験の固定値をpsycopgのSQL quotingだけで表現する。"""
    return sql.Literal(value).as_string()


@dataclass(frozen=True)
class BindingDatabase:
    """正式migration/製品認可を通った単一ownedDB。実外部lease証明とは別。"""

    owner: InitialGrantDatabase
    database: str

    def peer(self, role: str = APP) -> BindingPeer:
        """実LOGIN主体の独立接続を返す。"""
        return BindingPeer(self.owner.authority.database.business, self.database, role)


@contextmanager
def owned_binding_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InitialGrantDatabase]:
    """既実3PG/初期controllerを使い、製品のactual新migrationだけへ進める。"""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "migrations")
    )
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1 and heads[0] != "0036_initial_right_storage", (
        "U2正規migrationが未供給"
    )
    with monkeypatch.context() as patch:
        # fixtureの旧固定targetだけをactual製品headへ追随。製品処理/ACLを差し替えない。
        patch.setattr(initial_support, "_INITIAL_REVISION", heads[0])
        patch.setattr(
            initial_support.ledger_support,
            "AuthorityDatabase",
            BindingAuthorityDatabase,
        )
        with initial_support.isolated_initial_grant_database(patch) as owner:
            yield owner


def prepare_binding_database(owner: InitialGrantDatabase) -> BindingDatabase:
    """実fresh controller/RG1とcanonical表/関数を必須にする。代替DDL0。"""
    cluster = owner.authority.database
    with psycopg.connect(cluster.business_admin) as admin:
        assert admin.execute(
            "SELECT pg_catalog.to_regclass('sync_fence.writer_bindings') IS NOT NULL,"
            "pg_catalog.to_regclass('sync_fence.writer_admissions') IS NOT NULL,"
            "pg_catalog.to_regprocedure('sync_fence_api.assert_writer_binding("
            "uuid,uuid,uuid,bytea,uuid,uuid)') IS NOT NULL"
        ).fetchone() == (True, True, True)
        assert admin.execute(
            "SELECT state,recovery_generation FROM public.rg1_restore_gate"
        ).fetchall() == [("open", 1)]
    # 自分のowned containerに非秘密peer名を追加する。DBrole/鍵/資格発行0。
    docker(
        "exec",
        "--user",
        "root",
        cluster.business,
        "sh",
        "-eu",
        "-c",
        "getent passwd 20005 >/dev/null || "
        "echo 'pitchlog_binding_actor:x:20005:20005::/nonexistent:/bin/false' "
        ">> /etc/passwd",
    )
    app_name = docker("exec", cluster.business, "getent", "passwd", "20003").split(
        ":", 1
    )[0]
    assert app_name == "initial_app"
    docker(
        "exec",
        "-i",
        "--user",
        "postgres",
        cluster.business,
        "sh",
        "-eu",
        "-c",
        'cat >> "$PGDATA/pg_ident.conf"; '
        'sed -i "1i local all pitchlog_app,pitchlog_sync_binding_actor '
        'peer map=binding_test_peer" "$PGDATA/pg_hba.conf"',
        body=(
            "binding_test_peer initial_app pitchlog_app\n"
            "binding_test_peer pitchlog_binding_actor "
            "pitchlog_sync_binding_actor\n"
        ),
    )
    with psycopg.connect(cluster.business_admin, autocommit=True) as admin:
        assert admin.execute("SELECT pg_catalog.pg_reload_conf()").fetchone() == (True,)
    database = conninfo_to_dict(cluster.business_admin)["dbname"]
    assert isinstance(database, str)
    return BindingDatabase(owner, database)


def assert_statement(
    tenant: UUID, attempt: UUID, phase: UUID, nonce: bytes, device: UUID, game: UUID
) -> str:
    """U1固定assert ABIのSQLだけを作る。"""
    return (
        "SELECT sync_fence_api.assert_writer_binding("
        + ",".join(_literal(v) for v in (tenant, attempt, phase, nonce, device, game))
        + ")"
    )


class BindingAuthorityDatabase(initial_support.AuthorityDatabase):
    """初回start前にv3/control実PGを配置し、稼働中v2を書き換えない。"""

    def __init__(self, database, *, dual_peer=False):
        """既ownerの資源名にだけ新control資源を従属させる。"""
        super().__init__(database, dual_peer=dual_peer)
        self.binding_control = self.token + "-binding-pg"
        self.binding_control_socket = self.token + "-binding-socket"
        self._binding_created = False
        self._binding_prepared = False

    def command(self, **kwargs):
        """Root workerだけにowned control Unix socketを渡す。"""
        args = super().command(**kwargs)
        if kwargs.get("root"):
            args[2:2] = [
                "--volume",
                self.binding_control_socket + ":/binding-control-socket",
            ]
        return args

    def provision(self):
        """公開disposable vector/専用PG17のみ。製品表をfixtureで複製しない。"""
        import time

        from .durable_rights_ledger_support import _IMAGE

        docker("volume", "create", self.binding_control_socket)
        docker(
            "run",
            "-d",
            "--name",
            self.binding_control,
            "--network",
            self.database.network,
            "--volume",
            self.binding_control_socket + ":/var/run/postgresql",
            "--env",
            "POSTGRES_DB=binding_control_fixture",
            "--env",
            "POSTGRES_PASSWORD=pitchlog-public-disposable-ledger-fixture",
            _IMAGE,
        )
        self._binding_created = True
        for _ in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    self.binding_control,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "postgres",
                ],
                capture_output=True,
                timeout=5,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise AssertionError("owned control PG起動期限超過")
        package = (
            Path(__file__).resolve().parents[2]
            / "src/pitchlog/sync/control_provider/sql"
        )
        source = (
            (package / "control-phase-schema.sql").read_text()
            + "\n"
            + (package / "writer-binding-control.sql").read_text()
        )
        docker(
            "exec",
            "-i",
            self.binding_control,
            "psql",
            "-X",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "binding_control_fixture",
            body=source,
        )
        self._prepare_binding_peer(
            self.binding_control, "witness_authority", "postgres"
        )
        self._prepare_binding_peer(
            self.database.business, "witness_authority", "ledger_fixture_admin"
        )
        super().provision()

    @staticmethod
    def _prepare_binding_peer(container, authority_name, postgres_role):
        """新制御専用peer以外へPG主体を広げない。既appは開かない。"""
        docker(
            "exec",
            "--user",
            "root",
            container,
            "sh",
            "-eu",
            "-c",
            "getent passwd 20001 >/dev/null || "
            "echo 'witness_authority:x:20001:20001::/nonexistent:/bin/false' "
            ">> /etc/passwd; "
            "getent passwd 20005 >/dev/null || "
            "echo 'pitchlog_binding_actor:x:20005:20005::/nonexistent:/bin/false' "
            ">> /etc/passwd",
        )
        docker(
            "exec",
            "-i",
            "--user",
            "postgres",
            container,
            "sh",
            "-eu",
            "-c",
            'cat >> "$PGDATA/pg_ident.conf"; '
            'sed -i "1i local all pitchlog_sync_binding_actor '
            'peer map=binding_control_peer" "$PGDATA/pg_hba.conf"',
            body=(
                f"binding_control_peer {authority_name} "
                "pitchlog_sync_binding_actor\n"
                "binding_control_peer pitchlog_binding_actor "
                "pitchlog_sync_binding_actor\n"
            ),
        )
        docker(
            "exec",
            container,
            "psql",
            "-X",
            "-q",
            "-U",
            postgres_role,
            "-d",
            "postgres",
            "-c",
            "SELECT pg_reload_conf()",
        )

    def start(self, *, check=True):
        """初回enrollment後・最初のworker前だけroot固定v3を配置する。"""
        if not self._binding_prepared:
            # これらUUIDは隔離の公開相関値。実PG/epochの証拠は別途rootpairが照合する。
            binding_authority = {
                "control_instance": str(UUID(int=7101)),
                "business_instance": str(UUID(int=7102)),
                "restore_epoch": str(UUID(int=7103)),
                "control_version": 1,
            }
            code = f"""
import json
from pathlib import Path
from pitchlog.durable_rights_ledger.authority import _config,_write_root_json
path=Path('/control/settings/config.json')
v=_config(path)
assert v['schema_version']==2
v['schema_version']=3
v['peers'].append(dict(role='sync_binding',client_uid=20005,client_gid=20005,
 socket_path='/control/run/binding.sock',
 endpoint_path='/control/public/binding-endpoint.json'))
v['binding_business_dsn']=('host=/business-socket dbname=ledger_fixture '
 'user=pitchlog_sync_binding_actor')
v['binding_control_dsn']=('host=/binding-control-socket '
 'dbname=binding_control_fixture user=pitchlog_sync_binding_actor')
v['binding_authority']={binding_authority!r}
_write_root_json(path,v,0o640,20001)
print(json.loads(Path('/w/state/enrollment.json').read_text())['authority_id'])
"""
            issuer = docker(*self.command(root=True), "-c", code).strip()
            UUID(issuer)
            statement = (
                sql.SQL(
                    "INSERT INTO sync_control.authorities(authority_id,"
                    "control_instance,business_instance,restore_epoch,"
                    "control_version,state) VALUES ({},{},{},{},1,'active')"
                )
                .format(
                    *(
                        sql.Literal(v)
                        for v in (
                            issuer,
                            binding_authority["control_instance"],
                            binding_authority["business_instance"],
                            binding_authority["restore_epoch"],
                        )
                    )
                )
                .as_string()
            )
            docker(
                "exec",
                self.binding_control,
                "psql",
                "-X",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                "binding_control_fixture",
                "-c",
                statement,
            )
            self._binding_prepared = True
        return super().start(check=check)

    def close(self):
        """既owner全cleanup後、新control資源も必ず回収する。"""
        try:
            super().close()
        finally:
            initial_support.ledger_support.docker(
                "rm", "-f", "-v", self.binding_control, check=False
            )
            initial_support.ledger_support.docker(
                "volume", "rm", self.binding_control_socket, check=False
            )


@contextmanager
def binding_broker(owner: InitialGrantDatabase, token_id: UUID):
    """実専用verifier/UID20005 workerを既公開vectorだけで配置する。"""
    import time

    # 既verifierへは20002/20005だけ。appのverifier LOGINは引き続き拒否する。
    docker(
        "exec",
        "-i",
        "--user",
        "postgres",
        owner.authority.database.business,
        "sh",
        "-eu",
        "-c",
        'cat >> "$PGDATA/pg_ident.conf"; '
        'sed -i "1i local all pitchlog_initial_auth_verifier '
        'peer map=binding_verifier_peer" "$PGDATA/pg_hba.conf"',
        body=(
            "binding_verifier_peer initial_actor "
            "pitchlog_initial_auth_verifier\n"
            "binding_verifier_peer pitchlog_binding_actor "
            "pitchlog_initial_auth_verifier\n"
        ),
    )
    with psycopg.connect(
        owner.authority.database.business_admin, autocommit=True
    ) as admin:
        admin.execute("SELECT pg_reload_conf()")
    args = owner._broker_arguments(root=True)
    args[args.index("--rm")] = "--detach"
    name = args[args.index("--name") + 1]
    code = f"""
import ctypes,json,os,socket,threading,time
from pathlib import Path
from uuid import UUID
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import _activate_presentation
from pitchlog.recording_rights.initial_grant import V12Box
from pitchlog.recording_rights.initial_grant_broker import (
 _load_initial_actor_runtime,_load_initial_auth_verifier_runtime,
 _close_initial_actor_runtime)
from pitchlog.durable_rights_ledger.authority import _write_root_json
from pitchlog.sync.control_provider.binding_control import _BindingBroker
# 既公開隔離vectorのみ。運用署名鍵の発行/配置ではない。
presentation=TokenPresentation(bytes(range(32)))
_activate_presentation(presentation)
actor=_load_initial_actor_runtime(Path('/control/initial/actor.json'),V12Box('k1',bytes(range(32))))
verifier=_load_initial_auth_verifier_runtime(actor,presentation)
_close_initial_actor_runtime(actor)
del actor
Path('/control/public/binding-test-cookie').write_text(presentation.encode(UUID('{token_id}')))
run=Path('/control/binding-run');run.mkdir(mode=0o755)
os.chown(run,20005,20005)
readfd,writefd=os.pipe()
pid=os.fork()
if pid==0:
 os.close(readfd)
 os.setgroups([]);os.setgid(20005);os.setuid(20005)
 assert ctypes.CDLL(None).prctl(38,1,0,0,0)==0
 broker=_BindingBroker(Path('/control/public/binding-endpoint.json'),verifier)
 listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
 listener.bind('/control/binding-run/broker.sock');listener.listen(16)
 os.write(writefd,b'B');os.close(writefd)
 while True:
  channel,_=listener.accept();channel.settimeout(10)
  def handle(channel=channel):
   try: broker.handle(channel)
   finally: channel.close()
  threading.Thread(target=handle,daemon=True).start()
else:
 os.close(writefd);assert os.read(readfd,1)==b'B';os.close(readfd)
 os.chown('/control/binding-run/broker.sock',0,20003)
 os.chmod('/control/binding-run/broker.sock',0o660)
 issuer=json.loads(Path('/w/state/enrollment.json').read_text())['authority_id']
 endpoint=dict(schema_version=1,broker_uid=20005,broker_gid=20005,
  application_uid=20003,application_gid=20003,
  socket_path='/control/binding-run/broker.sock',timeout=10,
  authority_id=issuer,control_version=1)
 _write_root_json(Path('/control/public/binding-broker.json'),endpoint,0o644,20003)
 os.waitpid(pid,0)
"""
    try:
        docker(*args, "-u", "-c", code)
        for _ in range(80):
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "test",
                    "-f",
                    "/control/public/binding-broker.json",
                ],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                break
            running = docker("inspect", "--format", "{{.State.Running}}", name).strip()
            assert running == "true", "実binding broker起動が非成功"
            time.sleep(0.1)
        else:
            raise AssertionError("実binding broker起動期限超過")
        yield name
    finally:
        initial_support.ledger_support.docker("rm", "--force", name, check=False)


def binding_app(owner: InitialGrantDatabase, body: str) -> dict:
    """実app20003の正規engine/認証/scopeから製品binderを呼ぶ。"""
    import json

    args = owner._broker_arguments(uid=20003)
    args[1:1] = [
        "--volume",
        owner.authority.database.business_socket + ":/business-socket:ro",
    ]
    setup = """
import json,os,traceback,sys
def error_hook(kind,value,tb):
 print(json.dumps({'fixture_failure':kind.__name__,
  'frames':[(f.name,f.lineno) for f in traceback.extract_tb(tb)]}),flush=True)
sys.excepthook=error_hook
from pathlib import Path
from uuid import UUID,uuid4
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import _activate_presentation
from pitchlog.repositories.tenant_context_issuance import (
 issue_tenant_context_from_presented_token)
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.recording_rights.rg1_lifecycle import configure_runtime
from pitchlog.sync.control_provider.binding_control import BindingControl
from pitchlog.sync.control_provider.evidence import (
 AuthorityBinding,AttemptBinding,EventPhaseBinding)
from pitchlog.repositories.first_ball import (
 _BindFirstBallDeviceToken,_CheckFirstBallRightToken)
os.environ['PITCHLOG_DATABASE_URL']=('postgresql+psycopg://pitchlog_app@/'
 'ledger_fixture?host=%2Fbusiness-socket&sslmode=disable')
os.environ['PITCHLOG_DATABASE_POOLED']='false'
signer=TokenPresentation(bytes(range(32)));_activate_presentation(signer)
cookie=Path('/control/public/binding-test-cookie').read_text()
issued=issue_tenant_context_from_presented_token(cookie,signer)
assert issued is not None
context,_=issued
configure_runtime(Path('/control/initial/app-client.json'))
control=BindingControl(Path('/control/public/binding-broker.json'))
"""
    result = subprocess.run(
        ["docker", *args, "-u", "-c", setup + body],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if result.returncode:
        # 原文のdriver/資格を表示しない。型/行だけの既形式を要求する。
        try:
            failure = json.loads(result.stdout)
            assert type(failure) is dict and set(failure) == {
                "fixture_failure",
                "frames",
            }
        except Exception:
            raise AssertionError("実binding app起動/検証が非成功") from None
        raise AssertionError(f"実binding appが非成功: {failure}")
    value = json.loads(result.stdout)
    assert type(value) is dict
    return value
