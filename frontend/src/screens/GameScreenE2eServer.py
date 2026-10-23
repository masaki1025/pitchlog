"""封鎖画面 E2E 用に、製品認証と使い捨て製品 DB を起動する。"""

from __future__ import annotations

import base64
import inspect
import json
import os
import secrets
import signal
import socket
import stat
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from threading import Thread
from types import FrameType
from typing import cast
from uuid import uuid4

import psycopg
import pytest
import uvicorn
from db.test_api_auth_exit_entry import (
    _PreparingReadDb,
    _seed_read_game,
)
from db.test_api_auth_exit_entry import (
    preparing_read_database as preparing_read_database,
)
from db.test_product_authz_authn_app import (
    _app_dsn,
    _Identity,
    _seed_identity,
    _seed_settings,
)
from db_fixtures import (
    DisposablePostgres,
    ProvisionedProductCatalog,
    _dsn_names,
    _product_migration_url,
    disposable_postgres_cluster,
)
from fastapi import FastAPI
from GameScreenE2eSupport import validated_browser_mode_origin
from psycopg.conninfo import conninfo_to_dict, make_conninfo

pytest_plugins = ("db_fixtures",)
pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _configure_browser_read_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """readモードだけ既存の非秘密固定試験素材をApp生成前に置く。"""
    if os.environ.get("PITCHLOG_E2E_MODE") == "preparing-read":
        monkeypatch.setenv(
            "PITCHLOG_TOKEN_SIGNING_KEY_B64",
            base64.b64encode(b"r" * 32).decode("ascii"),
        )


def test_preparing_read_product_server(
    preparing_read_database: _PreparingReadDb,
) -> None:
    """実login用Appと保存済みread fixtureをブラウザ終了まで保持する。"""
    db = preparing_read_database
    for number in range(41, 66):
        _seed_read_game(db, number)
    _serve_browser_app(db.app, (db.identity, db.other), str(_seed_read_game(db, 66)))


def test_sealed_ui_product_server(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """自分の DB と実 App を立て、Playwright の終了まで保持する。"""
    catalog = provisioned_product_catalog
    cluster = catalog.cluster
    if not cluster.container_name.startswith("pitchlog-authz-"):
        pytest.fail("使い捨て DB の所有識別が不正")
    if conninfo_to_dict(catalog.owner_dsn).get("dbname") != "pitchlog_product":
        pytest.fail("製品 DB の所有識別が不正")

    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    first = _seed_identity(catalog, app_dsn)
    second = _seed_identity(catalog, app_dsn)
    # 既存製品migrationの表へ、この専用DBだけの識別可能な対戦相手値を置く。
    with catalog.applicator.cursor() as cursor:
        for identity in (first, second):
            cursor.execute(
                "INSERT INTO public.team_records (tenant_id, id, kind, name) "
                "VALUES (%s, %s, %s, %s)",
                (identity.tenant_id, uuid4(), "opponent", identity.name),
            )
    catalog.applicator.commit()
    with psycopg.connect(app_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user, current_database()")
            if cursor.fetchone() != ("pitchlog_app", "pitchlog_product"):
                pytest.fail("製品アプリロールの接続確認に失敗")

    os.environ["PITCHLOG_DATABASE_URL"] = (
        f"{_product_migration_url(app_dsn)}?sslmode=disable"
    )
    os.environ["PITCHLOG_DATABASE_POOLED"] = "false"
    os.environ["PITCHLOG_TOKEN_SIGNING_KEY_B64"] = base64.b64encode(
        secrets.token_bytes(32)
    ).decode("ascii")
    from pitchlog.api.app import create_app

    _serve_browser_app(create_app(), (first, second))


def _serve_browser_app(
    app: FastAPI,
    identities: tuple[_Identity, ...],
    preparing_game_id: str | None = None,
) -> None:
    """実Appを専用loopbackで起動し、停止通知まで所有資源だけを保持する。"""
    ready = Path(os.environ["PITCHLOG_E2E_READY_FILE"])
    stop = Path(os.environ["PITCHLOG_E2E_STOP_FILE"])
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_config=None,
        )
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("製品 App を起動できない")

    # 一時ディレクトリは呼び出し元が 0700 で作る。資格情報は標準出力へ出さない。
    ready_content = json.dumps(
        {
            "port": port,
            **({"preparingGameId": preparing_game_id} if preparing_game_id else {}),
            "identities": [
                {
                    "name": item.name,
                    "password": item.password,
                    "tenantId": str(item.tenant_id),
                }
                for item in identities
            ],
        }
    )
    descriptor = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as ready_file:
        ready_file.write(ready_content)
    try:
        deadline = time.monotonic() + 600
        while not stop.exists() and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not stop.exists():
            pytest.fail("E2E 停止通知がないか製品 App が終了した")
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        if thread.is_alive():
            pytest.fail("製品 App の停止期限を超過")


def main() -> int:
    """Pytest 前に外側の専用クラスタを作り、既存 autouse の実認証を成立させる。

    Returns:
        既存 pytest 設定で実行した試験の終了値。
    """
    # pytest fixture と二つの専用クラスタの with/finally を通して停止する。
    signal.signal(signal.SIGTERM, _graceful_termination)
    ready = Path(os.environ["PITCHLOG_E2E_READY_FILE"])
    stop = Path(os.environ["PITCHLOG_E2E_STOP_FILE"])
    directory = ready.parent
    if (
        ready.name != "backend-ready.json"
        or stop != directory / "stop"
        or not directory.name.startswith("pitchlog-e2e-")
        or directory.stat().st_uid != os.getuid()
        or stat.S_IMODE(directory.stat().st_mode) != 0o700
    ):
        raise AssertionError("E2E 資格情報の保存先が自分専用 0700 領域ではない")

    mode, origin = validated_browser_mode_origin()

    for name in tuple(os.environ):
        if name.startswith("PITCHLOG_") and name not in {
            "PITCHLOG_E2E_READY_FILE",
            "PITCHLOG_E2E_STOP_FILE",
            "PITCHLOG_E2E_FRONTEND_ORIGIN",
            "PITCHLOG_E2E_MODE",
        }:
            os.environ.pop(name)
    os.environ["PITCHLOG_ALLOWED_ORIGINS"] = origin

    admin_name, role_name = _dsn_names()
    role_user = f"pitchlog_e2e_{secrets.token_hex(8)}"
    role_password = secrets.token_urlsafe(24)
    os.environ[role_name] = make_conninfo(
        host="127.0.0.1",
        port=1,
        dbname="pitchlog_disposable",
        user=role_user,
        password=role_password,
    )
    fixture_function = cast(
        Callable[[], Callable[[], AbstractContextManager[DisposablePostgres]]],
        inspect.unwrap(disposable_postgres_cluster),
    )
    factory = fixture_function()
    try:
        with factory() as outer:
            admin = conninfo_to_dict(outer.admin_dsn)
            if (
                not outer.container_name.startswith("pitchlog-authz-")
                or not str(admin.get("user", "")).startswith("pitchlog_disposable_")
                or admin.get("host") != "127.0.0.1"
                or admin.get("dbname") != "pitchlog_disposable"
            ):
                raise AssertionError("外側の専用クラスタの所有識別が不正")
            role_dsn = make_conninfo(
                outer.role_dsn_template,
                user=role_user,
                password=role_password,
            )
            role = conninfo_to_dict(role_dsn)
            if any(
                role.get(key) != admin.get(key) for key in ("host", "port", "dbname")
            ):
                raise AssertionError("外側の管理接続と被検査ロールのクラスタが異なる")
            os.environ[admin_name] = outer.admin_dsn
            os.environ[role_name] = role_dsn
            return int(
                pytest.main(
                    [
                        "-c",
                        str(
                            Path(__file__).resolve().parents[3]
                            / "backend/pyproject.toml"
                        ),
                        str(Path(__file__).resolve()),
                        "-q",
                        "-s",
                        "-k",
                        (
                            "test_preparing_read_product_server"
                            if mode == "preparing-read"
                            else "test_sealed_ui_product_server"
                        ),
                    ]
                )
            )
    finally:
        os.environ.pop(admin_name, None)
        os.environ.pop(role_name, None)


def _graceful_termination(_signum: int, _frame: FrameType | None) -> None:
    """SIGTERMをpytestの通常の割込み・fixture後始末へ渡す。"""
    raise KeyboardInterrupt


if __name__ == "__main__":
    raise SystemExit(main())
