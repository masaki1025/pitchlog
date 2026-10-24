"""自分が所有する外部primary/standbyと業務clusterだけを管理する。"""

from __future__ import annotations

import socket
import subprocess
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy import URL, create_engine

from pitchlog.durable_rights_ledger import LedgerEndpoints

_IMAGE = "postgres:17.11-bookworm"
# 公開された隔離試験用素材。運用資格として利用しない。
_PUBLIC_FIXTURE_PASSWORD = "pitchlog-public-disposable-ledger-fixture"
_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "src/pitchlog/durable_rights_ledger/schema.sql"
)


def docker(*args: str, check: bool = True) -> str:
    """期限付きで所有資源だけを操作し、資格入りstderrを表示しない。"""
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=45
    )
    if check and result.returncode:
        raise AssertionError("isolated ledger docker operation failed")
    return result.stdout.strip()


def _wait(dsn: str) -> None:
    deadline = monotonic() + 25
    while monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=1):
                return
        except psycopg.Error:
            sleep(0.1)
    raise AssertionError("isolated ledger did not start")


def _install_product_business(dsn: str) -> None:
    """秘密新発行なしに正規migration/製品認可を実業務clusterへ適用する。"""
    from alembic import command
    from alembic.config import Config

    from pitchlog.authz.product_provisioning import apply_product_authz_ddl

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            "CREATE ROLE pitchlog_owner NOLOGIN NOSUPERUSER "
            "NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION"
        )
        connection.execute("ALTER DATABASE ledger_fixture OWNER TO pitchlog_owner")
    params = conninfo_to_dict(dsn)

    def required(key: str) -> str:
        value = params.get(key)
        if type(value) is not str or not value:
            raise AssertionError("isolated product DSN incomplete")
        return value

    url = URL.create(
        "postgresql+psycopg",
        username=required("user"),
        password=required("password"),
        host=required("host"),
        port=int(required("port")),
        database=required("dbname"),
    )
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET ROLE pitchlog_owner")
            config = Config(str(_SCHEMA.parents[3] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0033_game_rules_immutable")
            connection.commit()
    finally:
        engine.dispose()
    with psycopg.connect(dsn) as connection:
        apply_product_authz_ddl(connection)
        # 製品app/observerを拡張せず、rollback検証専用subjectはTEMPだけ許可する。
        connection.execute(
            "CREATE ROLE pitchlog_fixture_business_writer LOGIN "
            "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
            "NOREPLICATION PASSWORD 'pitchlog-public-disposable-ledger-fixture'"
        )
        connection.execute(
            "GRANT CONNECT,TEMPORARY ON DATABASE ledger_fixture "
            "TO pitchlog_fixture_business_writer"
        )


@dataclass(frozen=True, slots=True, repr=False)
class LedgerDatabase:
    """公開fixture資格を含む所有clusterの接続情報。"""

    primary: str
    standby: str
    business: str
    primary_admin: str
    standby_admin: str
    business_admin: str
    endpoints: LedgerEndpoints
    network: str
    volumes: tuple[str, ...]
    business_socket: str

    def standby_running(self, running: bool) -> None:
        """自分のstandbyだけを停止/再起動する。"""
        docker("start" if running else "stop", self.standby)
        if running:
            _wait(self.standby_admin)


@contextmanager
def isolated_ledger_database() -> Iterator[LedgerDatabase]:
    """三clusterと物理standbyを作り、失敗時も全所有資源を破棄する。"""
    token = uuid4().hex[:12]
    network = f"pitchlog-ledger-{token}"
    names = tuple(f"{network}-{part}" for part in ("primary", "standby", "business"))
    volumes = tuple(
        f"{network}-{part}-data" for part in ("primary", "standby", "business")
    )
    business_socket = f"{network}-business-socket"
    created: list[str] = []

    def start(name: str, volume: str, *, standby: bool = False) -> str:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            host_port = listener.getsockname()[1]
        args = [
            "run",
            "--detach",
            "--name",
            name,
            "--network",
            network,
            "--publish",
            f"127.0.0.1:{host_port}:5432",
            "--volume",
            f"{volume}:/var/lib/postgresql/data",
        ]
        if name == names[2]:
            args += ["--volume", f"{business_socket}:/var/run/postgresql"]
        if not standby:
            args += [
                "--env",
                "POSTGRES_USER=ledger_fixture_admin",
                "--env",
                f"POSTGRES_PASSWORD={_PUBLIC_FIXTURE_PASSWORD}",
                "--env",
                "POSTGRES_DB=ledger_fixture",
            ]
        args += [
            _IMAGE,
            "-c",
            "wal_level=replica",
            "-c",
            "max_wal_senders=5",
            "-c",
            "fsync=on",
            "-c",
            "full_page_writes=on",
        ]
        docker(*args)
        created.append(name)
        port = docker("port", name, "5432/tcp").rsplit(":", 1)[1]
        dsn = make_conninfo(
            host="127.0.0.1",
            port=port,
            dbname="ledger_fixture",
            user="ledger_fixture_admin",
            password=_PUBLIC_FIXTURE_PASSWORD,
        )
        _wait(dsn)
        return dsn

    try:
        docker("network", "create", network)
        for volume in (*volumes, business_socket):
            docker("volume", "create", volume)
        primary_admin = start(names[0], volumes[0])
        business_admin = start(names[2], volumes[2])
        _install_product_business(business_admin)
        with psycopg.connect(business_admin, autocommit=True) as connection:
            connection.execute((_SCHEMA.parent / "business_identity.sql").read_bytes())
        docker(
            "exec",
            names[2],
            "bash",
            "-c",
            "groupadd -g 20001 witness_authority && "
            "useradd -u 20001 -g 20001 -M witness_authority && "
            "sed -i '1ilocal all pitchlog_ledger_identity_probe "
            "peer map=witness_probe' "
            "/var/lib/postgresql/data/pg_hba.conf && "
            "echo 'witness_probe witness_authority "
            "pitchlog_ledger_identity_probe' "
            ">> /var/lib/postgresql/data/pg_ident.conf",
        )
        with psycopg.connect(business_admin, autocommit=True) as connection:
            connection.execute("SELECT pg_reload_conf()")
        with psycopg.connect(primary_admin, autocommit=True) as connection:
            connection.execute(_SCHEMA.read_bytes())
            connection.execute(
                "ALTER ROLE pitchlog_ledger_app PASSWORD "
                "'pitchlog-public-disposable-ledger-fixture'"
            )
            connection.execute(
                "ALTER ROLE pitchlog_ledger_control PASSWORD "
                "'pitchlog-public-disposable-ledger-fixture'"
            )
            connection.execute(
                "CREATE ROLE pitchlog_ledger_replicator LOGIN REPLICATION"
            )
        docker(
            "exec",
            names[0],
            "bash",
            "-c",
            "echo 'host replication pitchlog_ledger_replicator all trust' "
            ">> /var/lib/postgresql/data/pg_hba.conf",
        )
        with psycopg.connect(primary_admin, autocommit=True) as connection:
            connection.execute("SELECT pg_reload_conf()")
        docker(
            "run",
            "--rm",
            "--network",
            network,
            "--volume",
            f"{volumes[1]}:/var/lib/postgresql/data",
            "--user",
            "postgres",
            _IMAGE,
            "pg_basebackup",
            "-d",
            f"host={names[0]} user=pitchlog_ledger_replicator "
            "application_name=ledger_standby",
            "-D",
            "/var/lib/postgresql/data",
            "-R",
            "-X",
            "stream",
            "-w",
            "--checkpoint=fast",
        )
        standby_admin = start(names[1], volumes[1], standby=True)
        with psycopg.connect(primary_admin, autocommit=True) as connection:
            connection.execute(
                "ALTER SYSTEM SET synchronous_standby_names = "
                "'FIRST 1 (ledger_standby)'"
            )
            connection.execute("SELECT pg_reload_conf()")
        deadline = monotonic() + 15
        while monotonic() < deadline:
            with psycopg.connect(primary_admin, autocommit=True) as connection:
                row = connection.execute(
                    "SELECT sync_state FROM pg_stat_replication "
                    "WHERE application_name='ledger_standby'"
                ).fetchone()
                if row == ("sync",):
                    break
            sleep(0.05)
        else:
            raise AssertionError("real synchronous peer not available")
        app_primary = make_conninfo(primary_admin, user="pitchlog_ledger_app")
        app_standby = make_conninfo(standby_admin, user="pitchlog_ledger_app")
        control = make_conninfo(primary_admin, user="pitchlog_ledger_control")
        yield LedgerDatabase(
            names[0],
            names[1],
            names[2],
            primary_admin,
            standby_admin,
            business_admin,
            LedgerEndpoints(app_primary, app_standby, business_admin, control, 1.5),
            network,
            volumes,
            business_socket,
        )
    finally:
        for name in reversed(created):
            docker("rm", "--force", name, check=False)
        for volume in (*volumes, business_socket):
            docker("volume", "rm", volume, check=False)
        docker("network", "rm", network, check=False)


class AuthorityDatabase:
    """専用volume/実UID/実Unix peerで製品authorityを呼ぶ。"""

    def __init__(self, database: LedgerDatabase) -> None:
        """このfixtureが所有する名前だけを先に固定する。"""
        self.database = database
        self.token = "pitchlog-authority-" + uuid4().hex[:12]
        self.control = self.token + "-control"
        self.witness = self.token + "-witness"
        self.service = self.token + "-service"
        self._names: list[str] = []
        self._backups: list[str] = []

    def command(
        self, *, root: bool = False, persistent: bool = False, uid: int = 20002
    ) -> list[str]:
        """実workerとclientのmount/UID/capabilityを分離する。"""
        name = self.service if persistent else self.token + "-" + uuid4().hex[:6]
        self._names.append(name)
        source = _SCHEMA.parents[2]
        dependencies = Path(sys.prefix) / "lib/python3.12/site-packages"
        args = [
            "run",
            "--detach" if persistent else "--rm",
            "--name",
            name,
            "--label",
            "pitchlog.owner=ledger-authority-test",
            "--network",
            self.database.network,
            "--volume",
            f"{self.control}:/control" + ("" if root else ":ro"),
            "--mount",
            f"type=bind,src={sys.base_prefix},dst=/runtime,readonly",
            "--mount",
            f"type=bind,src={source},dst=/code,readonly",
            "--mount",
            f"type=bind,src={dependencies},dst=/deps,readonly",
            "--env",
            "PYTHONPATH=/code:/deps",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
        ]
        if root:
            args += [
                "--cap-add",
                "LINUX_IMMUTABLE",
                "--volume",
                f"{self.witness}:/w",
                "--volume",
                f"{self.database.business_socket}:/business-socket",
            ]
        else:
            args += [
                "--user",
                f"{uid}:{uid}",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
            ]
        return [*args, _IMAGE, "/runtime/bin/python3.12"]

    def client(self, code: str, *, uid: int = 20002, check: bool = True) -> str:
        """公開endpointだけを渡し、実署名等を偽装せずUnix資格を照合する。"""
        prefix = (
            "from pathlib import Path; from uuid import UUID, uuid4; "
            "from pitchlog.durable_rights_ledger import DurableLedger, "
            "LedgerUnavailable, LedgerOutcomeUnconfirmed; "
            "s=DurableLedger(Path('/control/public/endpoint.json'));\n"
        )
        return docker(*self.command(uid=uid), "-c", prefix + code, check=check)

    def client_process(self, code: str) -> subprocess.Popen[str]:
        """実clientのstdin/stdoutを制御し、lease中の実排他lockを別主体で照合する。"""
        prefix = (
            "from pathlib import Path; from uuid import UUID, uuid4; "
            "from pitchlog.durable_rights_ledger import DurableLedger, "
            "FreshActivationAttestation,LedgerUnavailable,LedgerOutcomeUnconfirmed; "
            "s=DurableLedger(Path('/control/public/endpoint.json'));\n"
        )
        command = self.command()
        command.insert(1, "--interactive")
        return subprocess.Popen(
            ["docker", *command, "-u", "-c", prefix + code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def event_counts(self) -> dict[str, int]:
        """所有する実journalのframe数を読取り、期待集合をauthorityへ供給しない。"""
        import json

        code = """
import json,os
from pitchlog.durable_rights_ledger.witness import _frames
fd=os.open('/w/state/journal',os.O_RDONLY|os.O_NOFOLLOW)
try:
    counts={}
    for frame in _frames(fd,os.fstat(fd).st_size):
        event=json.loads(frame.payload)['event']
        counts[event]=counts.get(event,0)+1
    print(json.dumps(counts))
finally: os.close(fd)
"""
        return json.loads(docker(*self.command(root=True), "-c", code))

    def journal_state(self) -> tuple[int, str]:
        """所有journalの実サイズと全byte digestだけをroot読取で観測する。"""
        import json

        code = """
import hashlib,json,os
fd=os.open('/w/state/journal',os.O_RDONLY|os.O_NOFOLLOW)
try:
    size=os.fstat(fd).st_size
    digest=hashlib.sha256()
    while block:=os.read(fd,65536): digest.update(block)
    assert os.fstat(fd).st_size==size
    print(json.dumps([size,digest.hexdigest()]))
finally: os.close(fd)
"""
        values = json.loads(docker(*self.command(root=True), "-c", code))
        assert type(values) is list and len(values) == 2
        assert type(values[0]) is int and type(values[1]) is str
        return values[0], values[1]

    def limit_worker_journal_growth(self, size: int) -> dict[str, Any]:
        """所有containerの実UID20001 workerだけを同UIDのprlimitで制限する。"""
        import json

        assert type(size) is int and size > 0
        code = """
import json,os,resource,sys
from pathlib import Path
assert os.getuid()==os.geteuid()==20001 and os.getgid()==os.getegid()==20001
def status(pid):
    lines=Path(f'/proc/{pid}/status').read_text().splitlines()
    return dict(line.split(':',1) for line in lines)
self_status=status(os.getpid())
assert all(int(self_status[key],16)==0 for key in ('CapEff','CapPrm','CapAmb'))
parent=status(1)
assert [int(v) for v in parent['Uid'].split()]==[0]*4
children=[int(v) for v in Path('/proc/1/task/1/children').read_text().split()]
workers=[]
for pid in children:
    value=status(pid)
    if pid!=os.getpid() and [int(v) for v in value['Uid'].split()]==[20001]*4:
        assert int(value['PPid'])==1
        assert [int(v) for v in value['Gid'].split()]==[20001]*4
        assert value['Name'].strip()==Path(sys.executable).name
        workers.append(pid)
assert len(workers)==1
pid=workers[0]
start=Path(f'/proc/{pid}/stat').read_text().split()[21]
size=int(sys.argv[1])
try:
    original=resource.prlimit(pid,resource.RLIMIT_FSIZE)
    assert original[0]==resource.RLIM_INFINITY or original[0]>size
    resource.prlimit(pid,resource.RLIMIT_FSIZE,(size,original[1]))
    actual=resource.prlimit(pid,resource.RLIMIT_FSIZE)
    assert actual==(size,original[1])
    assert Path(f'/proc/{pid}/stat').read_text().split()[21]==start
    print(json.dumps({'worker_pid':pid,'worker_ppid':1,'worker_uid':20001,
        'worker_gid':20001,'caller_uid':os.geteuid(),'launcher_uid':0,
        'original_limits':original,'limited_limits':actual,'journal_size':size}))
except PermissionError as error:
    print(json.dumps({'error':'PermissionError','errno':error.errno}))
"""
        value = json.loads(
            docker(
                "exec",
                "--user",
                "20001:20001",
                self.service,
                "/runtime/bin/python3.12",
                "-c",
                code,
                str(size),
            )
        )
        assert type(value) is dict and "error" not in value, (
            "所有workerへの同UID prlimitが拒否された",
            value,
        )
        return value

    def fresh_process_file_size_limit(self) -> int:
        """再起動へ使う新processには旧workerの局所limitが残らないと確認する。"""
        return int(
            docker(
                *self.command(root=True),
                "-c",
                "import resource;print(resource.getrlimit(resource.RLIMIT_FSIZE)[0])",
            )
        )

    def start(self, *, check: bool = True) -> bool:
        """既存の保護journalを照合して起動し、失敗を成功扱いしない。"""
        docker(
            *self.command(root=True, persistent=True),
            "-m",
            "pitchlog.durable_rights_ledger.authority",
            "serve",
            "--config",
            "/control/settings/config.json",
        )
        deadline = monotonic() + 15
        while monotonic() < deadline:
            state = docker("inspect", "--format", "{{.State.Running}}", self.service)
            if state != "true":
                if check:
                    raise AssertionError(
                        "real authority startup refused: " + self.diagnostic()
                    )
                return False
            # 明示ACKを最後まで検査する。stdout空を成功と推測しない。
            result = self.client(
                "assert s.current_recovery_generation() == 1; print('AUTHORITY_READY')",
                check=False,
            )
            if result == "AUTHORITY_READY":
                return True
            sleep(0.1)
        raise AssertionError("real authority readiness deadline exceeded")

    def diagnostic(self) -> str:
        """失敗後の実構築で例外型/関数/行だけを観測し、資格/原因文を出さない。"""
        code = """
import traceback
from pathlib import Path
from pitchlog.durable_rights_ledger.authority import _config
from pitchlog.durable_rights_ledger.adapter import _AuthorityRuntime
from pitchlog.durable_rights_ledger.witness import ProtectedJournal
try:
    value=_config(Path('/control/settings/config.json'))
    with ProtectedJournal.open(Path('/w/state'),timeout=2) as journal:
        _AuthorityRuntime(value,journal)
    print('DIAGNOSTIC_READY')
except Exception as exc:
    print(type(exc).__name__)
    for frame in traceback.extract_tb(exc.__traceback__):
        print(frame.name,frame.lineno)
"""
        command = self.command(root=True)
        return docker(
            *command[:-1],
            "/usr/bin/setpriv",
            "--reuid=20001",
            "--regid=20001",
            "--clear-groups",
            "--bounding-set=-all",
            "--inh-caps=-all",
            "--ambient-caps=-all",
            "--no-new-privs",
            command[-1],
            "-c",
            code,
            check=False,
        )

    def stop(self) -> None:
        """所有root launcherが子workerを停止する。"""
        docker("stop", "--time", "3", self.service, check=False)
        docker("rm", "--force", self.service, check=False)

    def provision(self) -> None:
        """固定の公開試験資格と実空pairをrootの一回登録へ渡す。"""
        docker("volume", "create", self.control)
        docker("volume", "create", self.witness)
        database = self.database

        def dsn(user: str, host: str) -> str:
            return make_conninfo(
                host=host,
                user=user,
                dbname="ledger_fixture",
                password=_PUBLIC_FIXTURE_PASSWORD,
            )

        value = dict(
            schema_version=1,
            authority_uid=20001,
            authority_gid=20001,
            client_uid=20002,
            client_gid=20002,
            socket_path="/control/run/service.sock",
            endpoint_path="/control/public/endpoint.json",
            witness_path="/w/state",
            timeout=2.0,
            primary_dsn=dsn("pitchlog_ledger_app", database.primary),
            standby_dsn=dsn("pitchlog_ledger_app", database.standby),
            business_dsn=make_conninfo(
                host="/business-socket",
                user="pitchlog_ledger_identity_probe",
                dbname="ledger_fixture",
            ),
            control_dsn=dsn("pitchlog_ledger_control", database.primary),
            enrollment_state="new",
        )
        code = (
            "from pathlib import Path; "
            "from pitchlog.durable_rights_ledger.authority import _write_root_json; "
            "[Path('/control/'+p).mkdir(mode=0o755) "
            "for p in ('settings','public','run')]; "
            f"_write_root_json(Path('/control/settings/config.json'),{value!r},0o640,20001)"
        )
        docker(*self.command(root=True), "-c", code)
        docker(
            *self.command(root=True),
            "-m",
            "pitchlog.durable_rights_ledger.authority",
            "enroll",
            "--config",
            "/control/settings/config.json",
        )
        self.start()

    def probe(
        self, statement: str, *, refused: bool = False, database: str = "ledger_fixture"
    ) -> str:
        """実OS UID→PG peerを通し、製品表/authnの実拒否を検査する。"""
        result = subprocess.run(
            [
                "docker",
                "exec",
                "--user",
                "20001:20001",
                self.database.business,
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-At",
                "-U",
                "pitchlog_ledger_identity_probe",
                "-d",
                database,
                "-c",
                statement,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if refused:
            assert result.returncode != 0 and "permission denied" in result.stderr
            assert not result.stdout
            return "DENIED"
        assert result.returncode == 0, "actual identity probe failed"
        return result.stdout.strip()

    def journal_digest(self, store: str = "state") -> str:
        """所有journalのbyte不変を確認し、資格を出力しない。"""
        assert store in ("state", "legacy")
        return docker(
            *self.command(root=True),
            "-c",
            "import hashlib; "
            f"f=open('/w/{store}/journal','rb'); "
            "print(hashlib.file_digest(f,'sha256').hexdigest())",
        )

    def switch_business_database(self, database: str) -> None:
        """所有したimmutable fixture設定だけを別DBへ向ける負例を作る。"""
        assert database in ("ledger_fixture", "ledger_other")
        code = f"""
from pathlib import Path
from psycopg.conninfo import make_conninfo
from pitchlog.durable_rights_ledger.authority import _config,_write_root_json
path=Path('/control/settings/config.json')
v=_config(path)
v['business_dsn']=make_conninfo(v['business_dsn'],dbname={database!r})
_write_root_json(path,v,0o640,v['authority_gid'])
"""
        docker(*self.command(root=True), "-c", code)

    def prepare_legacy_genesis(self, *, restore: bool = False) -> None:
        """旧database欠落frameを別の所有dirへ構成し、現journalは変更しない。"""
        code = f"""
import json,os
from pathlib import Path
from pitchlog.durable_rights_ledger.authority import (
    _config,_create_store,_write_root_json)
from pitchlog.durable_rights_ledger.witness import _frames,_encoded
path=Path('/control/settings/config.json')
v=_config(path)
if {restore!r}:
    v['witness_path']='/w/state'
else:
    fd=os.open('/w/state/journal',os.O_RDONLY|os.O_NOFOLLOW)
    try: genesis=json.loads(next(_frames(fd,os.fstat(fd).st_size)).payload)
    finally: os.close(fd)
    assert genesis['event']=='enrolled' and 'database' in genesis['business']
    v['witness_path']='/w/legacy'
    _create_store(v)
    descriptor=json.loads(Path('/w/legacy/enrollment.json').read_bytes())
    genesis['authority_id']=descriptor['authority_id']
    del genesis['business']['database']
    encoded,_=_encoded(1,bytes(32),json.dumps(genesis).encode())
    fd=os.open('/w/legacy/journal',os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
    try:
        offset=0
        while offset<len(encoded):
            count=os.write(fd,encoded[offset:])
            assert count>0
            offset+=count
        os.fsync(fd)
    finally: os.close(fd)
    fd=os.open('/w/legacy',os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
_write_root_json(path,v,0o640,v['authority_gid'])
"""
        docker(*self.command(root=True), "-c", code)

    def copy_pair(self, *, restore: bool = False) -> None:
        """停止した自分の二data volumeだけを退避/復元しwitnessへ触れない。"""
        self.stop()
        database = self.database
        for name in (database.primary, database.standby):
            docker("stop", name)
        try:
            if not restore:
                if self._backups:
                    raise AssertionError("backup already exists")
                for index in range(2):
                    backup = self.token + "-backup-" + str(index)
                    docker("volume", "create", backup)
                    self._backups.append(backup)
            if len(self._backups) != 2:
                raise AssertionError("owned backup missing")
            for original, backup in zip(
                database.volumes[:2], self._backups, strict=True
            ):
                source, destination = (
                    (backup, original) if restore else (original, backup)
                )
                docker(
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--label",
                    "pitchlog.owner=ledger-authority-test",
                    "--volume",
                    source + ":/from:ro",
                    "--volume",
                    destination + ":/to",
                    _IMAGE,
                    "bash",
                    "-c",
                    "find /to -mindepth 1 -maxdepth 1 "
                    "-exec rm -rf -- {} + && cp -a /from/. /to/",
                )
        finally:
            for name, dsn in (
                (database.primary, database.primary_admin),
                (database.standby, database.standby_admin),
            ):
                docker("start", name)
                _wait(dsn)
            deadline = monotonic() + 15
            while monotonic() < deadline:
                with psycopg.connect(database.primary_admin) as connection:
                    if connection.execute(
                        "SELECT sync_state FROM pg_stat_replication "
                        "WHERE application_name='ledger_standby'"
                    ).fetchone() == ("sync",):
                        break
                sleep(0.1)
            else:
                raise AssertionError("restored synchronous peer unavailable")

    def close(self) -> None:
        """自分の子process/保護flag/volumeだけを解放する。"""
        self.stop()
        cleanup = """
import os
from pathlib import Path
from pitchlog.durable_rights_ledger.authority import _set_flags
from pitchlog.durable_rights_ledger.witness import _flags
for top in ('/w', '/control'):
    for directory, dirs, files in os.walk(top):
        for path in [Path(directory), *(Path(directory)/name for name in files)]:
            if path.is_symlink() or path.is_socket(): continue
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            _set_flags(fd, _flags(fd) & ~0x30)
            os.close(fd)
"""
        docker(*self.command(root=True), "-c", cleanup, check=False)
        for name in self._names:
            docker("rm", "--force", name, check=False)
        for volume in (*self._backups, self.control, self.witness):
            docker("volume", "rm", volume, check=False)


@contextmanager
def isolated_authority_database() -> Iterator[AuthorityDatabase]:
    """実3PG＋復元外witness＋別UID authorityを所有し、必ず掃除する。"""
    with isolated_ledger_database() as database:
        authority = AuthorityDatabase(database)
        try:
            authority.provision()
            yield authority
        finally:
            authority.close()


class AuthorityResources:
    """試験シナリオが変わる前に旧所有3PGを片付け、重い起動を直列化する。"""

    def __init__(self) -> None:
        """同一normal群だけ共有する所有contextを初期化する。"""
        self._key: str | None = None
        self._value: AuthorityDatabase | None = None
        self._stack = ExitStack()

    def get(self, key: str) -> AuthorityDatabase:
        """新シナリオは別cluster/witnessで開始し、既存pairをfreshへ再初期化しない。"""
        if key != self._key:
            self.close()
            self._stack = ExitStack()
            self._value = self._stack.enter_context(isolated_authority_database())
            self._key = key
        assert self._value is not None
        return self._value

    def close(self) -> None:
        """登録済み所有contextだけを閉じる。"""
        self._stack.close()
        self._key = None
        self._value = None


@dataclass(frozen=True)
class ReserveCommitFault:
    """所有台帳の実COMMIT故障をrollbackされないsequenceで観測する。"""

    database: LedgerDatabase

    def observed(self) -> tuple[int, int, int, int]:
        """到達数/予約行可視数/予約世代/highwaterの実観測を返す。"""
        values: list[int] = []
        with psycopg.connect(self.database.primary_admin) as observer:
            for name in ("reached", "row_visible", "generation", "highwater"):
                row = observer.execute(
                    sql.SQL(
                        "SELECT CASE WHEN is_called THEN last_value ELSE 0 END "
                        "FROM pitchlog_ledger_fault.{}"
                    ).format(sql.Identifier(name))
                ).fetchone()
                assert row is not None and type(row[0]) is int
                values.append(row[0])
        return values[0], values[1], values[2], values[3]


@contextmanager
def reserve_commit_failure(database: LedgerDatabase) -> Iterator[ReserveCommitFault]:
    """実reserve SQL後のCOMMITだけを拒否し、製品処理を差し替えない。"""
    with psycopg.connect(database.primary_admin) as admin:
        admin.execute("CREATE SCHEMA pitchlog_ledger_fault")
        admin.execute("REVOKE ALL ON SCHEMA pitchlog_ledger_fault FROM PUBLIC")
        for name in ("reached", "row_visible", "generation", "highwater"):
            admin.execute(
                sql.SQL("CREATE SEQUENCE pitchlog_ledger_fault.{}").format(
                    sql.Identifier(name)
                )
            )
        admin.execute("""
CREATE FUNCTION pitchlog_ledger_fault.abort_reserve() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pitchlog_ledger_fault, pg_temp AS $fault$
DECLARE h bigint;
BEGIN
    PERFORM pg_catalog.nextval('pitchlog_ledger_fault.reached');
    IF EXISTS (
        SELECT 1 FROM pitchlog_ledger.reservations r
        WHERE r.attempt_id = NEW.attempt_id AND r.tenant_id = NEW.tenant_id
          AND r.game_id = NEW.game_id AND r.start_request_id = NEW.start_request_id
          AND r.generation = NEW.generation AND NOT r.claimed AND NOT r.quarantined
    ) THEN
        PERFORM pg_catalog.nextval('pitchlog_ledger_fault.row_visible');
    END IF;
    SELECT value INTO STRICT h FROM pitchlog_ledger.highwater WHERE singleton;
    PERFORM pg_catalog.setval('pitchlog_ledger_fault.generation', NEW.generation, true);
    PERFORM pg_catalog.setval('pitchlog_ledger_fault.highwater', h, true);
    RAISE EXCEPTION 'PITCHLOG_PRIVATE_RESERVE_COMMIT_FAULT' USING ERRCODE = 'P0001';
END
$fault$;
REVOKE ALL ON FUNCTION pitchlog_ledger_fault.abort_reserve() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER reserve_commit_fault
AFTER INSERT ON pitchlog_ledger.reservations DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION pitchlog_ledger_fault.abort_reserve();
""")
    try:
        yield ReserveCommitFault(database)
    finally:
        with psycopg.connect(database.primary_admin) as admin:
            admin.execute(
                "DROP TRIGGER reserve_commit_fault ON pitchlog_ledger.reservations"
            )
            admin.execute("DROP SCHEMA pitchlog_ledger_fault CASCADE")
