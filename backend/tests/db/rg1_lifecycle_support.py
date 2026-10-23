"""正式S3上でRG1制御primitiveだけを実行する隔離PG補助。"""

from __future__ import annotations

import os
import selectors
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, LiteralString, cast

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from pitchlog.db.stage_a_startup import advance_stage_a_from_s0

from .conftest import DisposablePostgres
from .test_stage_a_rule_candidates import _fresh_schema_database

_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "src/pitchlog/recording_rights/rg1_lifecycle.sql"
)
ACTOR = "pitchlog_rg1_control_actor"
APP = "pitchlog_app"
NAMESPACE = 1380397379


def docker(*arguments: str, body: str | None = None) -> str:
    """この試験が所有するコンテナへ有限時間で命令する。"""
    result = subprocess.run(
        ["docker", *arguments],
        input=body,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return result.stdout


class PeerSession:
    """コンテナ内の実peer認証を保つpsql session。"""

    def __init__(self, cluster: DisposablePostgres, database: str, role: str) -> None:
        """SET ROLEを使わずOS peerから対象LOGIN roleへ接続する。"""
        if role not in {ACTOR, APP}:
            raise ValueError("試験用peerの対象外")
        self._process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                "--user",
                "postgres",
                cluster.container_name,
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
            # stderrとstdoutを混ぜると拒否メッセージが次の応答へ遅延する。
            # 拒否判定はpsqlのSQLSTATEを必須にし、行protocolはstdoutへ閉じる。
            stderr=subprocess.DEVNULL,
        )
        self._buffer = b""
        self._sequence = 0
        try:
            assert self.query("SELECT session_user, current_user") == (
                f"{role}|{role}",
            )
        except BaseException:
            self.close()
            raise

    def execute(self, statement: str) -> tuple[tuple[str, ...], str]:
        """SQLSTATEと行を返し、拒否時にも同じsessionを保持する。"""
        self._sequence += 1
        marker = f"__rg1_test_done_{self._sequence}__"
        process = self._process
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(f"{statement};\n\\echo {marker} :SQLSTATE\n".encode())
        process.stdin.flush()
        deadline = time.monotonic() + 12
        lines: list[str] = []
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                while b"\n" in self._buffer:
                    line, self._buffer = self._buffer.split(b"\n", 1)
                    decoded = line.decode()
                    if decoded.startswith(marker + " "):
                        return tuple(lines), decoded.removeprefix(marker + " ")
                    if decoded:
                        lines.append(decoded)
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise AssertionError("peer SQLの期限超過")
                data = os.read(process.stdout.fileno(), 65536)
                if not data:
                    raise AssertionError(f"peer SQL接続が終了: {lines!r}")
                self._buffer += data

    def query(self, statement: str) -> tuple[str, ...]:
        """成功したSQLの行だけを取得する。"""
        rows, state = self.execute(statement)
        assert state == "00000", (state, rows)
        return rows

    def close(self) -> None:
        """接続断・server再起動後も所有する子プロセスを回収する。"""
        process = self._process
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stdout is not None:
            process.stdout.close()

    def __enter__(self) -> PeerSession:
        """所有sessionを返す。"""
        return self

    def __exit__(self, *_args: object) -> None:
        """sessionを終了する。"""
        self.close()


@dataclass(frozen=True)
class LifecycleDatabase:
    """製品S3と候補SQLを適用した一時DB。fresh証明ではない。"""

    cluster: DisposablePostgres = field(repr=False)
    admin_dsn: str = field(repr=False)
    database: str

    def peer(self, role: str = ACTOR, *, database: str | None = None) -> PeerSession:
        """専用peer接続を新規取得する。"""
        return PeerSession(self.cluster, database or self.database, role)

    def restart(self) -> LifecycleDatabase:
        """実serverを再起動し所有containerの現在の動的portへ再束縛する。"""
        docker("restart", self.cluster.container_name)
        port = docker("port", self.cluster.container_name, "5432/tcp").strip()
        assert port.startswith("127.0.0.1:") and "\n" not in port
        return replace(
            self,
            admin_dsn=make_conninfo(
                self.admin_dsn, host="127.0.0.1", port=port.rsplit(":", 1)[1]
            ),
        )


@contextmanager
def lifecycle_database(
    factory: Callable[[], AbstractContextManager[DisposablePostgres]],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[LifecycleDatabase]:
    """既存S0→正式S3と製品ACLを再利用し候補SQLを一度だけ適用する。"""
    clusters: list[DisposablePostgres] = []

    @contextmanager
    def tracked_factory() -> Iterator[DisposablePostgres]:
        with factory() as cluster:
            clusters.append(cluster)
            yield cluster

    with _fresh_schema_database(tracked_factory, monkeypatch) as (owner_dsn, admin_dsn):
        result = advance_stage_a_from_s0(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
        assert result.completed_stage == "S3" and result.publishable is False
        with psycopg.connect(admin_dsn) as admin:
            admin.execute(sql.SQL(cast(LiteralString, _SOURCE.read_text())))
        cluster = clusters[0]
        # 一時container内だけを変更する。対象2 LOGIN以外へpeer認証を広げない。
        docker(
            "exec",
            "-i",
            "--user",
            "postgres",
            cluster.container_name,
            "sh",
            "-eu",
            "-c",
            'cat > "$PGDATA/pg_ident.conf"; '
            'sed -i "1i local all pitchlog_app,pitchlog_rg1_control_actor '
            'peer map=rg1_test_peer" "$PGDATA/pg_hba.conf"',
            body=f"rg1_test_peer postgres {ACTOR}\nrg1_test_peer postgres {APP}\n",
        )
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            assert admin.execute("SELECT pg_catalog.pg_reload_conf()").fetchone() == (
                True,
            )
            assert admin.execute(
                "SELECT count(*) FROM pg_catalog.pg_hba_file_rules "
                "WHERE error IS NOT NULL"
            ).fetchone() == (0,)
        database = conninfo_to_dict(admin_dsn)["dbname"]
        assert isinstance(database, str)
        yield LifecycleDatabase(cluster, admin_dsn, database)


def observed_identity(
    connection: psycopg.Connection[Any], pid: int
) -> dict[str, object]:
    """adminの実観測と指定した実sessionのPIDで期待値を作る。"""
    row = connection.execute(
        "SELECT c.system_identifier::text, d.oid::bigint, d.datname::text, "
        "pg_catalog.to_char(pg_catalog.pg_postmaster_start_time() AT TIME ZONE 'UTC', "
        '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') '
        "FROM pg_catalog.pg_control_system() c CROSS JOIN pg_catalog.pg_database d "
        "WHERE d.datname = pg_catalog.current_database()"
    ).fetchone()
    assert row is not None
    return dict(
        zip(
            (
                "system_identifier",
                "database_oid",
                "database_name",
                "postmaster_started_at",
                "backend_pid",
            ),
            (*row, pid),
            strict=True,
        )
    )


def wait_until(predicate: Callable[[], bool]) -> None:
    """並行SQLの観測を短い期限内で待つ。"""
    deadline = time.monotonic() + 8
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("PG状態の観測期限超過")
        time.sleep(0.025)
