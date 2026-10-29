"""実ブラウザで準備中試合の開始を通すE2E（pytestが実app/DB/brokerを所有する）。

appは実UID20003のコンテナでuvicorn常駐し、DB/broker/RG1はowned PGと実workerを使う。
ブラウザはホストのPlaywright、frontendはホストのVite（/apiをappへproxy）。
成功経路に固定応答・仮Port・stubを使わない。
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import pytest

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _prepare_app_configuration,
)
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db

ROOT = Path(__file__).resolve().parents[3]
_FRONTEND = ROOT / "frontend"


def _free_port() -> int:
    """ホストの空きloopbackポートを予約して返す。"""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


def _wait(url: str, process: subprocess.Popen[str], deadline: float) -> None:
    """実HTTPが応答するまで待ち、プロセス終了は失敗にする。"""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"起動前に終了した: {url}")
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (URLError, OSError):
            time.sleep(0.2)
    raise AssertionError(f"起動待ちの期限超過: {url}")


def _app_container(db, app_port: int, origin: str) -> list[str]:
    """実appをUID20003でuvicorn常駐させるdocker引数。"""
    args = db._broker_arguments(uid=20003)
    args[1:1] = [
        "--volume",
        f"{db.authority.database.business_socket}:/business-socket:ro",
        "--volume",
        f"{db.authority.control}:/control:ro",
        "--publish",
        f"127.0.0.1:{app_port}:{app_port}",
        "--env",
        "PITCHLOG_DATABASE_URL=postgresql+psycopg://pitchlog_app@/ledger_fixture"
        "?host=%2Fbusiness-socket&sslmode=disable",
        "--env",
        "PITCHLOG_DATABASE_POOLED=false",
        "--env",
        "PITCHLOG_TOKEN_SIGNING_KEY_B64="
        + base64.b64encode(bytes(range(32))).decode("ascii"),
        "--env",
        f"PITCHLOG_ALLOWED_ORIGINS={origin}",
        "--env",
        "PITCHLOG_BINDING_CLIENT_CONFIG=/run/pitchlog/public/binding-client.json",
    ]
    return [
        *args,
        "-m",
        "uvicorn",
        "pitchlog.api.app:create_app",
        "--factory",
        "--host",
        "0.0.0.0",
        "--port",
        str(app_port),
        "--log-level",
        "warning",
    ]


def test_screen_start_e2e_uses_real_browser_api_db_and_broker(
    vertical_database,
) -> None:
    """画面の端末登録→開始→実GET /startedを、実インフラだけで通す。"""
    db = vertical_database
    token = uuid4()
    app_port, vite_port = _free_port(), _free_port()
    origin = f"http://127.0.0.1:{vite_port}"
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        app_args = _app_container(db, app_port, origin)
        name = app_args[app_args.index("--name") + 1]
        logs = Path(ROOT / ".pytest-tmp" / f"screen-start-{name}.log")
        logs.parent.mkdir(parents=True, exist_ok=True)
        app = subprocess.Popen(  # noqa: S603
            ["docker", *app_args],
            stdout=logs.open("w"),
            stderr=subprocess.STDOUT,
            text=True,
        )
        vite: subprocess.Popen[str] | None = None
        try:
            _wait(f"http://127.0.0.1:{app_port}/health", app, time.monotonic() + 90)
            vite_log = logs.with_suffix(".vite.log")
            vite = subprocess.Popen(  # noqa: S603
                [
                    "pnpm",
                    "exec",
                    "vite",
                    "--config",
                    "src/screens/GameScreenStart.e2e.vite.config.ts",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(vite_port),
                    "--strictPort",
                ],
                cwd=_FRONTEND,
                env={
                    **os.environ,
                    "PITCHLOG_E2E_BACKEND_PORT": str(app_port),
                },
                stdout=vite_log.open("w"),
                stderr=subprocess.STDOUT,
                text=True,
            )
            _wait(origin, vite, time.monotonic() + 60)
            with Path(ROOT / ".pytest-tmp" / "runtime.json").open("w") as runtime:
                json.dump(
                    {
                        "baseURL": origin,
                        "team": db.team_name,
                        "password": _PASSWORD,
                        "game": str(db.game_id),
                    },
                    runtime,
                )
            result = subprocess.run(  # noqa: S603
                [
                    "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "--config",
                    "src/screens/GameScreenStart.playwright.config.ts",
                ],
                cwd=_FRONTEND,
                env={
                    **os.environ,
                    "PITCHLOG_E2E_BASE_URL": origin,
                    "PITCHLOG_E2E_TEAM_NAME": db.team_name,
                    "PITCHLOG_E2E_PASSWORD": _PASSWORD,
                    "PITCHLOG_E2E_GAME_ID": str(db.game_id),
                },
                capture_output=True,
                text=True,
                timeout=600,
            )
            (ROOT / ".pytest-tmp" / "screen-start-playwright.log").write_text(
                result.stdout + "\n" + result.stderr
            )
            assert result.returncode == 0, (
                result.stdout[-12000:],
                result.stderr[-3000:],
            )
        finally:
            if vite is not None:
                vite.terminate()
                try:
                    vite.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    vite.kill()
            subprocess.run(  # noqa: S603
                ["docker", "stop", name], capture_output=True, text=True
            )
            app.wait(timeout=30)
