"""実fresh supplierと実RG1 controllerを所有3PGだけへ接続する。"""

from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep
from typing import Any

import psycopg

from .durable_rights_ledger_support import AuthorityDatabase, docker

_SQL = (
    Path(__file__).resolve().parents[2]
    / "src/pitchlog/recording_rights/rg1_lifecycle.sql"
)
CONTROLLER_UID = 20002
APPLICATION_UID = 20003


class FreshControllerDatabase:
    """新規controllerと所有business上の固定SQLだけを管理する。"""

    def __init__(self, authority: AuthorityDatabase) -> None:
        """authorityの既存service名を使わず、新container名を後で取得する。"""
        self.authority = authority
        self.container: str | None = None

    def prepare(self) -> None:
        """既存製品表/ACLを確認しSQL一回と所有container内peer設定を適用する。"""
        database = self.authority.database
        with psycopg.connect(database.business_admin) as connection:
            assert connection.execute(
                "SELECT singleton_id,state FROM public.rg1_restore_gate"
            ).fetchall() == [(1, "closed")]
            assert connection.execute(
                "SELECT rolname,rolcanlogin,rolsuper,rolbypassrls "
                "FROM pg_catalog.pg_roles "
                "WHERE rolname IN ('pitchlog_app','pitchlog_rg1_fn_owner') "
                "ORDER BY rolname"
            ).fetchall() == [
                ("pitchlog_app", True, False, False),
                ("pitchlog_rg1_fn_owner", False, False, False),
            ]
            assert connection.execute(
                "SELECT pg_catalog.has_table_privilege('pitchlog_app', "
                "'public.rg1_restore_gate','SELECT'), "
                "pg_catalog.has_column_privilege('pitchlog_rg1_fn_owner', "
                "'public.rg1_restore_gate','state','SELECT'), "
                "pg_catalog.has_column_privilege('pitchlog_rg1_fn_owner', "
                "'public.rg1_restore_gate','state','UPDATE')"
            ).fetchone() == (False, True, False)
            assert connection.execute(
                "SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname IN "
                "('pitchlog_rg1_control_owner','pitchlog_rg1_control_actor')"
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT pg_catalog.to_regnamespace('rg1_control')"
            ).fetchone() == (None,)
            # migration/role重複をfixtureで補完せず、この実sourceを一度だけ実行する。
            connection.execute(_SQL.read_bytes())

        docker(
            "exec",
            database.business,
            "bash",
            "-eu",
            "-c",
            "groupadd -g 20002 rg1_controller && "
            "useradd -u 20002 -g 20002 -M rg1_controller && "
            "groupadd -g 20003 rg1_application && "
            "useradd -u 20003 -g 20003 -M rg1_application && "
            "sed -i '1ilocal all pitchlog_rg1_control_actor,pitchlog_app "
            "peer map=rg1_controller_test' /var/lib/postgresql/data/pg_hba.conf && "
            "printf '%s\\n' "
            "'rg1_controller_test rg1_controller pitchlog_rg1_control_actor' "
            "'rg1_controller_test rg1_application pitchlog_app' "
            ">> /var/lib/postgresql/data/pg_ident.conf",
        )
        with psycopg.connect(database.business_admin, autocommit=True) as connection:
            assert connection.execute(
                "SELECT pg_catalog.pg_reload_conf()"
            ).fetchone() == (True,)
            assert connection.execute(
                "SELECT count(*) FROM pg_catalog.pg_hba_file_rules "
                "WHERE error IS NOT NULL"
            ).fetchone() == (0,)

        # PGserverの実PID1所有UIDを観測し、imageの既定UIDを仮定しない。
        server_uid = int(
            docker("exec", database.business, "stat", "-c", "%u", "/proc/1")
        )
        assert server_uid > 0 and server_uid not in {CONTROLLER_UID, APPLICATION_UID}
        client: dict[str, Any] = {
            "schema_version": 1,
            "socket_path": "/control/rg1/controller.sock",
            "controller_uid": CONTROLLER_UID,
            "application_uid": APPLICATION_UID,
        }
        controller = {
            **client,
            "business_socket_directory": "/business-socket",
            "business_port": 5432,
            "business_database": "ledger_fixture",
            "business_server_uid": server_uid,
            "ledger_endpoint": "/control/public/endpoint.json",
        }
        code = (
            "import json,os; from pathlib import Path; "
            "p=Path('/control/rg1'); p.mkdir(mode=0o755); "
            "assert p.stat().st_uid==0 and p.stat().st_mode & 0o777 == 0o755; "
            f"values={{'client.json':{client!r},'controller.json':{controller!r}}}; "
            "[(p/name).write_text(json.dumps(value)) "
            "for name,value in values.items()]; "
            "[os.chmod(p/name,0o644) for name in values]"
        )
        docker(*self.authority.command(root=True), "-c", code)

    def start(self) -> None:
        """実固定entrypointをroot起動し、実freshで行openになるまで待つ。"""
        arguments = self.authority.command(root=True)
        assert arguments[1] == "--rm"
        arguments[1] = "--detach"
        self.container = arguments[arguments.index("--name") + 1]
        assert self.container != self.authority.service
        # 例外の資格入り本文をログへ出さず、実sourceの型/関数/行だけを保存する。
        code = """
from pathlib import Path
import traceback
from pitchlog.recording_rights.rg1_lifecycle import serve_fresh_controller
try:
    serve_fresh_controller(Path('/control/rg1/controller.json'))
except BaseException as error:
    print(type(error).__name__,flush=True)
    for frame in traceback.extract_tb(error.__traceback__):
        print(frame.name,frame.lineno,flush=True)
    raise SystemExit(1)
"""
        docker(*arguments, "-u", "-c", code)
        deadline = monotonic() + 15
        while monotonic() < deadline:
            assert self.running(), "実controller起動拒否: " + self.diagnostic()
            with psycopg.connect(self.authority.database.business_admin) as connection:
                if connection.execute(
                    "SELECT state FROM public.rg1_restore_gate WHERE singleton_id=1"
                ).fetchone() == ("open",):
                    return
            sleep(0.1)
        raise AssertionError("実controller ready期限超過: " + self.diagnostic())

    def running(self) -> bool:
        """このfixtureのcontrollerだけを観測する。"""
        assert self.container is not None
        return (
            docker("inspect", "--format", "{{.State.Running}}", self.container)
            == "true"
        )

    def diagnostic(self) -> str:
        """Source wrapperが保存した資格なし型/関数/行だけを読む。"""
        assert self.container is not None
        return docker("logs", "--tail", "30", self.container, check=False)

    def application(self, code: str) -> str:
        """UID20003の実clientから、同Sessionの実PG bindingを取得する。"""
        arguments = self.authority.command(uid=APPLICATION_UID)
        arguments[1:1] = [
            "--volume",
            f"{self.authority.database.business_socket}:/business-socket:ro",
        ]
        return docker(*arguments, "-u", "-c", code)

    def close(self) -> None:
        """authority/witnessの掃除より先に所有controllerだけを停止する。"""
        if self.container is not None:
            docker("rm", "--force", self.container, check=False)
