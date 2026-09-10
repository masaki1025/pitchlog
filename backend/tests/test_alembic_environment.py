"""Alembic の target metadata 配線を構造検査する。"""

from __future__ import annotations

import runpy
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import alembic
import pytest

from pitchlog.db.base import Base

_ENVIRONMENT_PATH = Path(__file__).resolve().parents[1] / "migrations" / "env.py"


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
