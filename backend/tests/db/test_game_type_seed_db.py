"""試合区分のシード資産と migration の投入結果を検証する。"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError

from pitchlog.authz.product_provisioning import apply_product_authz_ddl

from .conftest import DisposablePostgres, ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent
_SEED_PATH = _REPO_ROOT / "contracts" / "seeds" / "game-type.json"
_MIGRATION_PATH = _BACKEND_ROOT / "migrations" / "versions" / "0030_seed_game_type.py"
_ROSTER_KEYS = {"active", "other", "ob"}


def _seed_rows() -> list[dict[str, str]]:
    """シード資産の 5 行を読む。"""
    rows: list[dict[str, str]] = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    return rows


def _migration_rows() -> list[dict[str, str]]:
    """固定投入値を migration の AST から取り出す。"""
    source = ast.parse(_MIGRATION_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(source)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        and node.func.attr == "bulk_insert"
    ]
    assert len(calls) == 1
    rows: list[dict[str, str]] = ast.literal_eval(calls[0].args[1])
    return rows


def _sqlalchemy_url(dsn: str) -> str:
    """使い捨て DB の接続先を Alembic 用 URL に変える。"""
    values = conninfo_to_dict(dsn)
    required = {key: values.get(key) for key in ("host", "port", "dbname", "user")}
    assert all(value is not None for value in required.values())
    password = values.get("password")
    return URL.create(
        "postgresql",
        username=str(required["user"]),
        password=None if password is None else str(password),
        host=str(required["host"]),
        port=int(str(required["port"])),
        database=str(required["dbname"]),
    ).render_as_string(hide_password=False)


def _migration_config(
    cluster: DisposablePostgres, monkeypatch: pytest.MonkeyPatch
) -> Config:
    """使い捨て DB だけを Alembic の接続先に設定する。"""
    monkeypatch.setenv(
        "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
    )
    return Config(str(_BACKEND_ROOT / "alembic.ini"))


def _owner_migration_config(owner_dsn: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    """製品 DB の所有者接続を Alembic に渡す。"""
    monkeypatch.setenv("PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(owner_dsn))
    return Config(str(_BACKEND_ROOT / "alembic.ini"))


def test_game_type_seed_matches_migration_and_database(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """資産・固定投入値・実 DB の 5 行を全数で比較する。"""
    expected = _seed_rows()
    assert len(expected) == 5
    assert {row["display_name"] for row in expected} == {
        "公式戦",
        "準公式戦",
        "オープン戦",
        "紅白戦",
        "その他",
    }
    assert {row["category"] for row in expected} == {"game_type"}
    keys = {row["key"] for row in expected}
    assert len(keys) == 5
    assert keys.isdisjoint(_ROSTER_KEYS)
    assert _migration_rows() == expected

    with disposable_postgres_cluster() as cluster:
        command.upgrade(_migration_config(cluster, monkeypatch), "0030_seed_game_type")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key, category, display_name FROM system_vocabularies "
                    "WHERE category = %s ORDER BY key",
                    ("game_type",),
                )
                actual = cursor.fetchall()

    assert actual == sorted(
        (row["key"], row["category"], row["display_name"]) for row in expected
    )


def test_product_rls_keeps_system_vocabulary_write_closed(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """所有者とアプリのポリシー分離と FORCE RLS を確認する。"""
    connection = provisioned_product_catalog.observer
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relation.relowner::regrole::text, "
            "relation.relrowsecurity, relation.relforcerowsecurity "
            "FROM pg_catalog.pg_class AS relation "
            "WHERE relation.oid = 'public.system_vocabularies'::regclass"
        )
        assert cursor.fetchone() == ("pitchlog_owner", True, True)
        cursor.execute(
            "SELECT rolname, rolbypassrls FROM pg_catalog.pg_roles "
            "WHERE rolname IN ('pitchlog_owner', 'pitchlog_app') "
            "ORDER BY rolname"
        )
        assert cursor.fetchall() == [
            ("pitchlog_app", False),
            ("pitchlog_owner", False),
        ]
        cursor.execute(
            "SELECT policy.policyname, policy.cmd, policy.roles "
            "FROM pg_catalog.pg_policies AS policy "
            "WHERE policy.schemaname = 'public' "
            "AND policy.tablename = 'system_vocabularies' "
            "ORDER BY policy.policyname"
        )
        assert cursor.fetchall() == [
            ("pitchlog_app_global_read_only", "SELECT", ["pitchlog_app"]),
            ("pitchlog_owner_game_type_seed_delete", "DELETE", ["pitchlog_owner"]),
            ("pitchlog_owner_game_type_seed_insert", "INSERT", ["pitchlog_owner"]),
            ("pitchlog_owner_game_type_seed_select", "SELECT", ["pitchlog_owner"]),
        ]
        cursor.execute(
            "SELECT has_table_privilege(%s, %s, %s)",
            ("pitchlog_app", "public.system_vocabularies", "INSERT"),
        )
        assert cursor.fetchone() == (False,)
    connection.rollback()


def test_game_type_seed_round_trip_and_reapply(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """無関係な行を残して往復し、再適用でも 5 行だけを投入する。"""
    with disposable_postgres_cluster() as cluster:
        config = _migration_config(cluster, monkeypatch)
        command.upgrade(config, "0029_system_vocab_category_fk")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO system_vocabularies (key, category, display_name) "
                    "VALUES (%s, %s, %s)",
                    ("unrelated-game-type", "game_type", "既存区分"),
                )

        command.upgrade(config, "0030_seed_game_type")
        command.upgrade(config, "head")
        command.current(config, check_heads=True)
        command.check(config)
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key FROM system_vocabularies WHERE category = %s",
                    ("game_type",),
                )
                assert {row[0] for row in cursor.fetchall()} == {
                    *(row["key"] for row in _seed_rows()),
                    "unrelated-game-type",
                }

        command.downgrade(config, "0029_system_vocab_category_fk")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key, display_name FROM system_vocabularies "
                    "WHERE category = %s",
                    ("game_type",),
                )
                assert cursor.fetchall() == [("unrelated-game-type", "既存区分")]

        command.upgrade(config, "0030_seed_game_type")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key FROM system_vocabularies WHERE category = %s",
                    ("game_type",),
                )
                assert {row[0] for row in cursor.fetchall()} == {
                    *(row["key"] for row in _seed_rows()),
                    "unrelated-game-type",
                }


def test_game_type_seed_collision_is_atomic(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既存キーとの衝突で失敗し、先行する投入行も残さない。"""
    with disposable_postgres_cluster() as cluster:
        config = _migration_config(cluster, monkeypatch)
        command.upgrade(config, "0029_system_vocab_category_fk")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO system_vocabularies (key, category, display_name) "
                    "VALUES (%s, %s, %s)",
                    ("game_open", "game_type", "既存の表示名"),
                )

        with pytest.raises(SQLAlchemyIntegrityError) as collision:
            command.upgrade(config, "0030_seed_game_type")
        assert isinstance(collision.value.orig, psycopg.errors.UniqueViolation)
        assert collision.value.orig.diag.constraint_name == "pk_system_vocabularies"

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key, display_name FROM system_vocabularies "
                    "WHERE category = %s",
                    ("game_type",),
                )
                assert cursor.fetchall() == [("game_open", "既存の表示名")]
                cursor.execute("SELECT version_num FROM alembic_version")
                assert cursor.fetchone() == ("0029_system_vocab_category_fk",)


def test_seeded_game_type_fk_accepts_game_and_rejects_roster_key(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """試合区分の参照は通し、在籍区分のキーを試合には通さない。"""
    with disposable_postgres_cluster() as cluster:
        config = _migration_config(cluster, monkeypatch)
        command.upgrade(config, "0030_seed_game_type")
        tenant_id, home_id, away_id = uuid4(), uuid4(), uuid4()
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO tenants (id, name) VALUES (%s, %s)",
                    (tenant_id, "試合区分テストテナント"),
                )
                cursor.execute(
                    "INSERT INTO team_records (tenant_id, id, kind, name) "
                    "VALUES (%s, %s, %s, %s), (%s, %s, %s, %s)",
                    (
                        tenant_id,
                        home_id,
                        "self",
                        "自チーム",
                        tenant_id,
                        away_id,
                        "opponent",
                        "相手チーム",
                    ),
                )
                cursor.execute(
                    "INSERT INTO tenant_vocabularies "
                    "(tenant_id, key, category, display_name) VALUES (%s, %s, %s, %s)",
                    (tenant_id, "autumn", "tournament", "秋季大会"),
                )
                statement = (
                    "INSERT INTO games "
                    "(tenant_id, id, scheduled_at, game_type_key, tournament_key, "
                    "away_team_record_id, home_team_record_id, applied_rules) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                )
                params = (
                    tenant_id,
                    uuid4(),
                    datetime(2026, 10, 13, tzinfo=UTC),
                    "game_official",
                    "autumn",
                    away_id,
                    home_id,
                    Jsonb({}),
                )
                cursor.execute(statement, params)
                with pytest.raises(
                    psycopg.errors.ForeignKeyViolation
                ) as wrong_category:
                    cursor.execute(
                        statement,
                        (*params[:1], uuid4(), *params[2:3], "active", *params[4:]),
                    )
                assert wrong_category.value.diag.constraint_name == "fk_games_game_type"
                cursor.execute(
                    "SELECT game_type_key FROM games WHERE tenant_id = %s",
                    (tenant_id,),
                )
                assert cursor.fetchall() == [("game_official",)]


def test_game_type_seed_round_trip_under_product_rls(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """製品の FORCE RLS 下で所有者が再適用・往復できる。"""
    catalog = provisioned_product_catalog
    config = _owner_migration_config(catalog.owner_dsn, monkeypatch)
    command.downgrade(config, "0029_system_vocab_category_fk")
    apply_product_authz_ddl(catalog.applicator)
    command.upgrade(config, "0030_seed_game_type")
    command.upgrade(config, "head")
    command.current(config, check_heads=True)

    admin_dsn = make_conninfo(catalog.cluster.admin_dsn, dbname="pitchlog_product")
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.system_vocabularies "
                "(key, category, display_name) "
                "VALUES ('unrelated-game-type', 'game_type', '既存区分')"
            )

    with psycopg.connect(catalog.owner_dsn, autocommit=True) as owner:
        with owner.cursor() as cursor:
            cursor.execute(
                "SELECT key, category, display_name, disabled "
                "FROM public.system_vocabularies "
                "WHERE category = 'game_type' ORDER BY key"
            )
            assert cursor.fetchall() == sorted(
                (row["key"], row["category"], row["display_name"], False)
                for row in _seed_rows()
            )
            for key, category, label, disabled in (
                ("game_official", "game_type", "公式戦", True),
                ("unapproved", "game_type", "未承認", False),
                ("game_other", "game_type", "異なる表示", False),
                ("game_other", "roster_status", "その他", False),
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "INSERT INTO public.system_vocabularies "
                        "(key, category, display_name, disabled) "
                        "VALUES (%s, %s, %s, %s)",
                        (key, category, label, disabled),
                    )
            cursor.execute(
                "DELETE FROM public.system_vocabularies WHERE key = 'active'"
            )
            assert cursor.rowcount == 0
            cursor.execute(
                "DELETE FROM public.system_vocabularies "
                "WHERE key = 'unrelated-game-type'"
            )
            assert cursor.rowcount == 0
            cursor.execute(
                "UPDATE public.system_vocabularies SET disabled = true "
                "WHERE key = 'game_official'"
            )
            assert cursor.rowcount == 0

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT display_name FROM public.system_vocabularies "
                "WHERE key = 'unrelated-game-type'"
            )
            assert cursor.fetchone() == ("既存区分",)

    with psycopg.connect(admin_dsn, autocommit=True) as app:
        with app.cursor() as cursor:
            cursor.execute("SET ROLE pitchlog_app")
            cursor.execute("SELECT current_user")
            assert cursor.fetchone() == ("pitchlog_app",)
            for statement in (
                "INSERT INTO public.system_vocabularies "
                "(key, category, display_name) "
                "VALUES ('app_extra', 'game_type', '追加')",
                "DELETE FROM public.system_vocabularies WHERE key = 'game_official'",
                "UPDATE public.system_vocabularies SET disabled = true "
                "WHERE key = 'game_official'",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(statement)

    tenant_id, home_id, away_id = uuid4(), uuid4(), uuid4()
    with psycopg.connect(admin_dsn) as admin:
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO tenants (id, name) VALUES (%s, %s)",
                (tenant_id, "RLS試合区分テスト"),
            )
            cursor.execute(
                "INSERT INTO team_records (tenant_id, id, kind, name) "
                "VALUES (%s, %s, %s, %s), (%s, %s, %s, %s)",
                (
                    tenant_id,
                    home_id,
                    "self",
                    "自チーム",
                    tenant_id,
                    away_id,
                    "opponent",
                    "相手チーム",
                ),
            )
            cursor.execute(
                "INSERT INTO tenant_vocabularies "
                "(tenant_id, key, category, display_name) VALUES (%s, %s, %s, %s)",
                (tenant_id, "rls-test", "tournament", "RLSテスト大会"),
            )
            statement = (
                "INSERT INTO games "
                "(tenant_id, id, scheduled_at, game_type_key, tournament_key, "
                "away_team_record_id, home_team_record_id, applied_rules) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )
            params = (
                tenant_id,
                uuid4(),
                datetime(2026, 10, 13, tzinfo=UTC),
                "game_official",
                "rls-test",
                away_id,
                home_id,
                Jsonb({}),
            )
            cursor.execute(statement, params)
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with admin.transaction():
                    cursor.execute(
                        statement,
                        (*params[:1], uuid4(), *params[2:3], "active", *params[4:]),
                    )
        admin.rollback()

    command.downgrade(config, "0029_system_vocab_category_fk")
    command.upgrade(config, "0030_seed_game_type")
    with psycopg.connect(catalog.owner_dsn, autocommit=True) as owner:
        with owner.cursor() as cursor:
            cursor.execute(
                "SELECT key FROM public.system_vocabularies "
                "WHERE category = 'game_type'"
            )
            assert {row[0] for row in cursor.fetchall()} == {
                row["key"] for row in _seed_rows()
            }


def test_game_type_seed_collision_is_atomic_under_product_rls(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FORCE RLS 下のキー衝突でも移行全体をロールバックする。"""
    catalog = provisioned_product_catalog
    config = _owner_migration_config(catalog.owner_dsn, monkeypatch)
    command.downgrade(config, "0029_system_vocab_category_fk")
    with psycopg.connect(catalog.owner_dsn, autocommit=True) as owner:
        with owner.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.system_vocabularies "
                "(key, category, display_name) "
                "VALUES ('game_open', 'game_type', 'オープン戦')"
            )

    with pytest.raises(SQLAlchemyIntegrityError) as collision:
        command.upgrade(config, "0030_seed_game_type")
    assert isinstance(collision.value.orig, psycopg.errors.UniqueViolation)
    with psycopg.connect(catalog.owner_dsn, autocommit=True) as owner:
        with owner.cursor() as cursor:
            cursor.execute(
                "SELECT key FROM public.system_vocabularies "
                "WHERE category = 'game_type'"
            )
            assert cursor.fetchall() == [("game_open",)]
            cursor.execute("SELECT version_num FROM alembic_version")
            assert cursor.fetchone() == ("0029_system_vocab_category_fk",)
