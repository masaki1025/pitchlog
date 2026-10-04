"""使い捨て DB の在籍区分がシード資産と一致することを検査する。"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy.engine import URL

from .conftest import DisposablePostgres

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SEED_PATH = _BACKEND_ROOT.parent / "contracts" / "seeds" / "roster-status.json"


def _sqlalchemy_url(dsn: str) -> str:
    """使い捨てクラスタの conninfo を Alembic 用 URL に変換する。

    Args:
        dsn: クラスタ管理者の libpq conninfo。

    Returns:
        同じ接続先を指す PostgreSQL URL。
    """
    parameters = conninfo_to_dict(dsn)
    required = {key: parameters.get(key) for key in ("host", "port", "dbname", "user")}
    assert all(value is not None for value in required.values())
    password = parameters.get("password")
    return URL.create(
        "postgresql",
        username=str(required["user"]),
        password=None if password is None else str(password),
        host=str(required["host"]),
        port=int(str(required["port"])),
        database=str(required["dbname"]),
    ).render_as_string(hide_password=False)


def test_roster_status_seed_matches_upgraded_database(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空 DB を head まで上げ、投入された三列を資産と完全照合する。

    Args:
        disposable_postgres_cluster: 使い捨て PostgreSQL の factory。
        monkeypatch: Alembic の接続先を差し替える fixture。
    """
    seed_rows: list[dict[str, str]] = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    expected = sorted(
        (row["key"], row["category"], row["display_name"]) for row in seed_rows
    )
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        config = Config(str(_BACKEND_ROOT / "alembic.ini"))
        command.upgrade(config, "head")

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key, category, display_name FROM system_vocabularies "
                    "WHERE category = %s ORDER BY key",
                    ("roster_status",),
                )
                actual = cursor.fetchall()
    assert actual == expected
