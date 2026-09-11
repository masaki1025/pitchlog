"""Alembic の target metadata 配線を構造検査する。"""

from __future__ import annotations

import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from pkgutil import walk_packages

import alembic
import pytest
from sqlalchemy import Table

from pitchlog import db as db_package
from pitchlog.db.base import Base

_ENVIRONMENT_PATH = Path(__file__).resolve().parents[1] / "migrations" / "env.py"


def _discovered_model_module_names() -> set[str]:
    """製品 DB パッケージを走査して models モジュール名を返す。"""
    return {
        module_info.name
        for module_info in walk_packages(
            db_package.__path__,
            prefix=f"{db_package.__name__}.",
        )
        if module_info.name.rsplit(".", maxsplit=1)[-1] == "models"
    }


def _declared_model_table_keys(module_names: set[str]) -> set[str]:
    """Import 済み models モジュールが宣言した表キーを返す。"""
    table_keys: set[str] = set()
    for module_name in module_names:
        module = sys.modules.get(module_name)
        assert module is not None, f"models モジュールが未 import: {module_name}"
        for value in vars(module).values():
            if isinstance(value, Table):
                table_keys.add(value.key)
                continue
            table = getattr(value, "__table__", None)
            if getattr(value, "__module__", None) == module_name and isinstance(
                table, Table
            ):
                table_keys.add(table.key)
    return table_keys


class _ConfigStub:
    """env.py のオフライン読込に必要な最小設定。"""

    config_file_name: str | None = None


class _ContextStub:
    """env.py の target metadata を観測する Alembic context。"""

    def __init__(self) -> None:
        self.config = _ConfigStub()
        self.configured_options: dict[str, object] = {}
        self.migration_was_run = False

    def is_offline_mode(self) -> bool:
        """実接続を行わない経路を選ぶ。"""
        return True

    def configure(self, **options: object) -> None:
        """env.py が Alembic へ渡した設定を記録する。"""
        self.configured_options = options

    @contextmanager
    def begin_transaction(self) -> Iterator[None]:
        """テスト用の空トランザクションを供給する。"""
        yield

    def run_migrations(self) -> None:
        """Migration 実行要求を記録する。"""
        self.migration_was_run = True


def test_target_metadata_is_the_production_base_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """env.py の target_metadata が本番 Base.metadata と同一だと示す。"""
    context_stub = _ContextStub()
    monkeypatch.setattr(alembic, "context", context_stub, raising=False)
    monkeypatch.setenv(
        "PITCHLOG_MIGRATION_DATABASE_URL",
        "postgresql://user:password@db.example/pitchlog",
    )

    environment = runpy.run_path(str(_ENVIRONMENT_PATH))

    assert environment["target_metadata"] is Base.metadata
    assert context_stub.configured_options["target_metadata"] is Base.metadata
    assert context_stub.configured_options["url"] == (
        "postgresql+psycopg://user:password@db.example/pitchlog"
    )
    assert context_stub.migration_was_run


def test_all_model_modules_are_discovered_and_registered() -> None:
    """全 models モジュールが走査され、その全表が Base へ登録されると示す。"""
    from pitchlog.db import all_models

    discovered_module_names = _discovered_model_module_names()

    assert discovered_module_names
    assert set(all_models.IMPORTED_MODEL_MODULE_NAMES) == discovered_module_names
    assert _declared_model_table_keys(discovered_module_names) == set(
        Base.metadata.tables
    )
