"""自分が所有する外部primary/standbyと業務clusterだけを管理する。"""

from __future__ import annotations

import socket
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import psycopg
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
            "sed -i '1ilocal ledger_fixture pitchlog_ledger_identity_probe "
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

    def probe(self, statement: str, *, refused: bool = False) -> str:
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
                "ledger_fixture",
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
