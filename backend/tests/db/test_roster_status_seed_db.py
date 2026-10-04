"""使い捨て DB の在籍区分がシード資産と一致することを検査する。"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError

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
    """空 DB を 0027 まで上げ、投入された三列を資産と完全照合する。

    head ではなく 0027 へ固定するのは、後続の seed タスクが game_type を
    正当に投入したときに本試験が落ちないようにするため。

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
        command.upgrade(config, "0027_seed_roster_status")

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key, category, display_name FROM system_vocabularies "
                    "WHERE category = %s ORDER BY key",
                    ("roster_status",),
                )
                actual = cursor.fetchall()
                cursor.execute(
                    "SELECT count(*) FROM system_vocabularies WHERE category = %s",
                    ("game_type",),
                )
                game_type_count = cursor.fetchone()
                cursor.execute(
                    "SELECT disabled FROM system_vocabularies WHERE category = %s",
                    ("roster_status",),
                )
                disabled_values = cursor.fetchall()
    assert actual == expected
    assert game_type_count == (0,)
    assert len(disabled_values) == 3
    assert all(row[0] is False for row in disabled_values)


def test_roster_status_seed_upgrade_rejects_existing_key(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既存行との衝突で失敗するのは意図した設計であり、黙って採用も上書きもしない。

    Args:
        disposable_postgres_cluster: 使い捨て PostgreSQL の factory。
        monkeypatch: Alembic の接続先を差し替える fixture。
    """
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        config = Config(str(_BACKEND_ROOT / "alembic.ini"))
        command.upgrade(config, "0026_operation_event_c12")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO system_vocabularies (key, category, display_name) "
                    "VALUES (%s, %s, %s)",
                    ("active", "roster_status", "別経路"),
                )

        with pytest.raises(
            SQLAlchemyIntegrityError,
            match="pk_system_vocabularies",
        ) as duplicate_key:
            command.upgrade(config, "head")
        assert isinstance(duplicate_key.value.orig, psycopg.errors.UniqueViolation)
        assert duplicate_key.value.orig.diag.constraint_name == "pk_system_vocabularies"

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT display_name FROM system_vocabularies WHERE key = %s",
                    ("active",),
                )
                assert cursor.fetchall() == [("別経路",)]


def _upgrade_seed_database(
    cluster: DisposablePostgres, monkeypatch: pytest.MonkeyPatch
) -> Config:
    """使い捨て DB をシード revision を含む head まで上げる。

    Args:
        cluster: 使い捨て PostgreSQL クラスタ。
        monkeypatch: Alembic の接続先を差し替える fixture。

    Returns:
        downgrade にも使う Alembic 設定。
    """
    monkeypatch.setenv(
        "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
    )
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    return config


def _insert_player_references(cursor: psycopg.Cursor[Any]) -> tuple[UUID, UUID]:
    """選手 INSERT に必要なテナント、チーム、テナント語彙を作る。

    Args:
        cursor: 管理者接続のカーソル。

    Returns:
        テナント ID とチーム ID。
    """
    tenant_id = uuid4()
    team_id = uuid4()
    cursor.execute(
        "INSERT INTO tenants (id, name) VALUES (%s, %s)",
        (tenant_id, "在籍区分テストテナント"),
    )
    cursor.execute(
        "INSERT INTO team_records (tenant_id, id, kind, name) VALUES (%s, %s, %s, %s)",
        (tenant_id, team_id, "self", "在籍区分テストチーム"),
    )
    cursor.execute(
        "INSERT INTO tenant_vocabularies (tenant_id, key, category, display_name) "
        "VALUES (%s, %s, %s, %s)",
        (tenant_id, "roster-test-label", "roster_label", "テスト用"),
    )
    return tenant_id, team_id


def _insert_player(
    cursor: psycopg.Cursor[Any],
    tenant_id: UUID,
    team_id: UUID,
    roster_status_key: str | None,
) -> UUID:
    """指定した在籍キーで選手を作る。

    Args:
        cursor: 管理者接続のカーソル。
        tenant_id: 選手のテナント ID。
        team_id: 選手のチーム ID。
        roster_status_key: 検査する在籍キー。

    Returns:
        新しい選手 ID。
    """
    player_id = uuid4()
    cursor.execute(
        "INSERT INTO players "
        "(tenant_id, id, team_record_id, name, roster_status_key, roster_label_key) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (
            tenant_id,
            player_id,
            team_id,
            "在籍区分テスト選手",
            roster_status_key,
            "roster-test-label",
        ),
    )
    return player_id


def test_seeded_roster_status_player_constraints_and_referenced_downgrade(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3 キーの参照、FK、NOT NULL、参照中 downgrade の拒否を検査する。

    Args:
        disposable_postgres_cluster: 使い捨て PostgreSQL の factory。
        monkeypatch: Alembic の接続先を差し替える fixture。
    """
    with disposable_postgres_cluster() as cluster:
        config = _upgrade_seed_database(cluster, monkeypatch)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                tenant_id, team_id = _insert_player_references(cursor)
                seeded_keys = ("active", "other", "ob")
                for key in seeded_keys:
                    _insert_player(cursor, tenant_id, team_id, key)
                cursor.execute(
                    "SELECT roster_status_key FROM players WHERE tenant_id = %s",
                    (tenant_id,),
                )
                assert {row[0] for row in cursor.fetchall()} == set(seeded_keys)

                with pytest.raises(
                    psycopg.errors.ForeignKeyViolation,
                    match="fk_players_roster_status",
                ) as missing_key:
                    _insert_player(cursor, tenant_id, team_id, "missing-roster-status")
                assert (
                    missing_key.value.diag.constraint_name == "fk_players_roster_status"
                )

                with pytest.raises(
                    psycopg.errors.NotNullViolation,
                    match="roster_status_key",
                ) as null_key:
                    _insert_player(cursor, tenant_id, team_id, None)
                assert null_key.value.diag.column_name == "roster_status_key"

        with pytest.raises(
            SQLAlchemyIntegrityError,
            match="fk_players_roster_status",
        ) as referenced_downgrade:
            command.downgrade(config, "0026_operation_event_c12")
        assert isinstance(
            referenced_downgrade.value.orig, psycopg.errors.ForeignKeyViolation
        )
        assert (
            referenced_downgrade.value.orig.diag.constraint_name
            == "fk_players_roster_status"
        )

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key FROM system_vocabularies WHERE category = %s",
                    ("roster_status",),
                )
                assert {row[0] for row in cursor.fetchall()} == set(seeded_keys)


def test_seeded_roster_status_is_unavailable_after_unreferenced_downgrade(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """参照の無い downgrade 後はシードキーで選手を作れない。

    Args:
        disposable_postgres_cluster: 使い捨て PostgreSQL の factory。
        monkeypatch: Alembic の接続先を差し替える fixture。
    """
    with disposable_postgres_cluster() as cluster:
        config = _upgrade_seed_database(cluster, monkeypatch)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                tenant_id, team_id = _insert_player_references(cursor)

        command.downgrade(config, "0026_operation_event_c12")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key FROM system_vocabularies WHERE category = %s",
                    ("roster_status",),
                )
                assert cursor.fetchall() == []
                with pytest.raises(
                    psycopg.errors.ForeignKeyViolation,
                    match="fk_players_roster_status",
                ) as missing_seed:
                    _insert_player(cursor, tenant_id, team_id, "active")
                assert (
                    missing_seed.value.diag.constraint_name
                    == "fk_players_roster_status"
                )
