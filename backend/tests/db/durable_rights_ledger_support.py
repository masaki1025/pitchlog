"""自分が所有する外部primary/standbyと業務clusterだけを管理する。"""

from __future__ import annotations

import socket
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo

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
        for volume in volumes:
            docker("volume", "create", volume)
        primary_admin = start(names[0], volumes[0])
        business_admin = start(names[2], volumes[2])
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
        )
    finally:
        for name in reversed(created):
            docker("rm", "--force", name, check=False)
        for volume in volumes:
            docker("volume", "rm", volume, check=False)
        docker("network", "rm", network, check=False)
