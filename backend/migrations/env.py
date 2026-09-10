"""Alembic の migration 実行環境を構成する。"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from pitchlog.db.base import Base
from pitchlog.db.url import normalize_postgresql_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_MIGRATION_DATABASE_URL_VARIABLE = "PITCHLOG_MIGRATION_DATABASE_URL"


def _migration_database_url() -> str:
    """Alembic 専用 URL を正規化して返す。

    Returns:
        psycopg 3 を明示した migration 用 URL。
    """
    return normalize_postgresql_url(os.environ[_MIGRATION_DATABASE_URL_VARIABLE])


def run_migrations_offline() -> None:
    """接続せずに migration SQL を生成する。"""
    context.configure(
        url=_migration_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Direct connection 上で migration を実行する。"""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _migration_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
