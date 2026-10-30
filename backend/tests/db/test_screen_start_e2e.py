"""実ブラウザで開始と記録後復元を通すE2E（pytestが実app/DB/brokerを所有する）。

appは実UID20003のコンテナでuvicorn常駐し、DB/broker/RG1はowned PGと実workerを使う。
ブラウザはホストのPlaywright、frontendはホストのVite（/apiをappへproxy）。
成功経路に固定応答・仮Port・stubを使わない。
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import ssl
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import pytest
from manual_e2e_hold_support import hold_manual_environment, manual_hold_seconds

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _APP_SCRIPT,
    _app_arguments,
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
_PASSWORD = "public-owned-vertical-password-A1"
_PITCH_TYPE = "u06-first-ball-fastball"
_LOGS = Path("/tmp/opencode/pitchlog-screen-e2e")


def _free_port() -> int:
    """ホストの空きloopbackポートを予約して返す。"""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


def _wait(
    url: str,
    process: subprocess.Popen[str],
    deadline: float,
    *,
    local_tls: bool = False,
) -> None:
    """実HTTPが応答するまで待ち、プロセス終了は失敗にする。"""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"起動前に終了した: {url}")
        try:
            with urlopen(  # noqa: S310
                url,
                timeout=1,
                context=ssl._create_unverified_context() if local_tls else None,
            ) as response:
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


@contextmanager
def _browser_environment(
    db, spec_config: str, stem: str, *, https: bool = False
) -> Iterator[str]:
    """実appコンテナとViteを起動し、実ブラウザ用のoriginを返す。"""
    app_port, vite_port = _free_port(), _free_port()
    origin = f"{'https' if https else 'http'}://127.0.0.1:{vite_port}"
    _LOGS.mkdir(parents=True, exist_ok=True)
    _prepare_app_configuration(db)
    app_args = _app_container(db, app_port, origin)
    name = app_args[app_args.index("--name") + 1]
    app = subprocess.Popen(  # noqa: S603
        ["docker", *app_args],
        stdout=(_LOGS / f"{stem}-app.log").open("w"),
        stderr=subprocess.STDOUT,
        text=True,
    )
    vite: subprocess.Popen[str] | None = None
    try:
        _wait(f"http://127.0.0.1:{app_port}/health", app, time.monotonic() + 90)
        vite = subprocess.Popen(  # noqa: S603
            [
                "pnpm",
                "exec",
                "vite",
                "--config",
                (
                    "src/screens/GameScreenFirstBall.e2e.vite.config.ts"
                    if https
                    else "src/screens/GameScreenStart.e2e.vite.config.ts"
                ),
                "--host",
                "127.0.0.1",
                "--port",
                str(vite_port),
                "--strictPort",
            ],
            cwd=_FRONTEND,
            env={**os.environ, "PITCHLOG_E2E_BACKEND_PORT": str(app_port)},
            stdout=(_LOGS / f"{stem}-vite.log").open("w"),
            stderr=subprocess.STDOUT,
            text=True,
        )
        _wait(origin, vite, time.monotonic() + 60, local_tls=https)
        yield origin
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


def _run_playwright(
    db,
    spec_config: str,
    origin: str,
    stem: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """実ブラウザspecを実行し、失敗時は実測logを残す。"""
    result = subprocess.run(  # noqa: S603
        [
            "pnpm",
            "exec",
            "playwright",
            "test",
            "--config",
            f"src/screens/{spec_config}",
        ],
        cwd=_FRONTEND,
        env={
            **os.environ,
            "PITCHLOG_E2E_BASE_URL": origin,
            "PITCHLOG_E2E_TEAM_NAME": db.team_name,
            "PITCHLOG_E2E_PASSWORD": _PASSWORD,
            "PITCHLOG_E2E_GAME_ID": str(db.game_id),
            **(extra_env or {}),
        },
        capture_output=True,
        text=True,
        timeout=600,
    )
    (_LOGS / f"{stem}-playwright.log").write_text(result.stdout + "\n" + result.stderr)
    return result


def _record_first_ball(db) -> dict[str, object]:
    """製品の実HTTP縦断（enroll→start→sync）で1球を保存済みにする。"""
    case = {
        "phase": "record",
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "start_request_id": str(db.start_request_id),
        "pitch_type": _PITCH_TYPE,
        "course": [132, 131],
    }
    process = subprocess.run(  # noqa: S603
        ["docker", *_app_arguments(db, case), "-u", "-c", _APP_SCRIPT],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert process.returncode == 0, (process.stdout[-1500:], process.stderr[-1500:])
    return json.loads(process.stdout)


def test_screen_start_e2e_uses_real_browser_api_db_and_broker(
    vertical_database,
) -> None:
    """画面の端末登録→開始→実GET /startedを、実インフラだけで通す。"""
    db = vertical_database
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, "GameScreenStart.playwright.config.ts", "start"
        ) as origin:
            result = _run_playwright(
                db, "GameScreenStart.playwright.config.ts", origin, "start"
            )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-3000:],
            )


def test_screen_recorded_restore_e2e_uses_server_state(
    vertical_database,
) -> None:
    """記録済み1球をページ再読込でサーバーから復元し、失敗時に旧値を残さない。"""
    db = vertical_database
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        recorded = _record_first_ball(db)
        _LOGS.mkdir(parents=True, exist_ok=True)
        (_LOGS / "record.json").write_text(
            json.dumps(recorded, ensure_ascii=False, indent=1)
        )
        assert ["sync", 200] in recorded["stages"], recorded
        assert ["started_after", 200] in recorded["stages"], recorded
        with _browser_environment(
            db, "GameScreenRestore.playwright.config.ts", "restore"
        ) as origin:
            result = _run_playwright(
                db, "GameScreenRestore.playwright.config.ts", origin, "restore"
            )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-3000:],
            )


def test_screen_create_start_e2e_uses_real_browser(
    vertical_database,
) -> None:
    """実画面で新規作成し、その試合を開始して開始済み状態を実APIで確認する。"""
    import psycopg

    db = vertical_database
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with psycopg.connect(db.authority.database.business_admin) as admin:
            teams = admin.execute(
                "SELECT away_team_record_id,home_team_record_id FROM public.games "
                "WHERE tenant_id=%s AND id=%s",
                (db.tenant_id, db.game_id),
            ).fetchone()
        assert teams is not None
        with _browser_environment(
            db, "GameScreenCreateStart.playwright.config.ts", "create"
        ) as origin:
            result = _run_playwright(
                db,
                "GameScreenCreateStart.playwright.config.ts",
                origin,
                "create",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert result.returncode == 0, (
                result.stdout[-10000:],
                result.stderr[-3000:],
            )


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS証明書/鍵PATH未供給のためHTTPS初球縦断は未実証",
)
def test_screen_first_ball_https_create_save_reload(vertical_database) -> None:
    """同じowned環境で画面新規作成から初球保存・再送・reloadを実測する。"""
    import psycopg

    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file(), (
            "HTTPS E2Eには明示した証明書/鍵の既存絶対PATHが両方必要"
        )
    db = vertical_database
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with psycopg.connect(db.authority.database.business_admin) as admin:
            teams = admin.execute(
                "SELECT away_team_record_id,home_team_record_id FROM public.games "
                "WHERE tenant_id=%s AND id=%s",
                (db.tenant_id, db.game_id),
            ).fetchone()
        assert teams is not None
        with _browser_environment(
            db,
            "GameScreenFirstBall.playwright.config.ts",
            "first-ball-https",
            https=True,
        ) as origin:
            result = _run_playwright(
                db,
                "GameScreenFirstBall.playwright.config.ts",
                origin,
                "first-ball-https",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-3000:],
            )
            match = re.search(
                r"PITCHLOG_FIRST_BALL_GAME_ID=([0-9a-f-]{36})", result.stdout
            )
            assert match is not None, "画面作成した試合の非秘密識別値がない"
            created_game = match.group(1)
            assert created_game != str(db.game_id), "fixture試合を新規作成と数えない"
            with psycopg.connect(db.authority.database.business_admin) as admin:
                for table in (
                    "play_rows",
                    "operation_events",
                    "event_slots",
                ):
                    from psycopg import sql

                    count = admin.execute(
                        sql.SQL(
                            "SELECT count(*) FROM public.{} "
                            "WHERE tenant_id=%s AND game_id=%s"
                        ).format(sql.Identifier(table)),
                        (db.tenant_id, created_game),
                    ).fetchone()
                    assert count == (1,), table
                ledger_count = admin.execute(
                    "SELECT count(*) FROM public.idempotency_ledger AS ledger "
                    "JOIN public.operation_events AS op "
                    "ON ledger.tenant_id=op.tenant_id AND ledger.d5=op.d5 "
                    "WHERE op.tenant_id=%s AND op.game_id=%s",
                    (db.tenant_id, created_game),
                ).fetchone()
                assert ledger_count == (1,), "idempotency_ledger"
            hold_manual_environment(origin, manual_hold_seconds(), db.team_name)
