"""Alembic の target metadata 配線を構造検査する。"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from pkgutil import walk_packages
from typing import Literal, TypedDict, cast

import alembic
import pytest
from sqlalchemy import Table

from pitchlog import db as db_package
from pitchlog.db.base import Base

_ENVIRONMENT_PATH = Path(__file__).resolve().parents[1] / "migrations" / "env.py"
_BACKEND_PATH = _ENVIRONMENT_PATH.parents[1]
_ALEMBIC_CONFIG_PATH = _BACKEND_PATH / "alembic.ini"


class _HandlerSnapshot(TypedDict):
    """ロギングハンドラの正規化済み状態。"""

    class_name: str
    level: str
    formatter_class_name: str | None
    formatter_format: str | None
    formatter_datefmt: str | None
    has_filters: bool
    stream_name: str


class _RootLoggerSnapshot(TypedDict):
    """root ロガーの正規化済み状態。"""

    level: str
    handlers: list[_HandlerSnapshot]


class _NamedLoggerSnapshot(_RootLoggerSnapshot):
    """名前付きロガーの正規化済み状態。"""

    propagate: bool
    disabled: bool


class _DisabledSnapshot(TypedDict):
    """ロガーの有効・無効だけを表す状態。"""

    disabled: bool


_LoggingSnapshot = TypedDict(
    "_LoggingSnapshot",
    {
        "root": _RootLoggerSnapshot,
        "alembic": _NamedLoggerSnapshot,
        "sqlalchemy.engine": _NamedLoggerSnapshot,
        "pitchlog.api.errors": _DisabledSnapshot,
        "pitchlog_sentinel_disabled": _DisabledSnapshot,
    },
)

_LOGGING_PROBE_SCRIPT = f'''\
import json
import logging
import runpy
from collections.abc import Iterator
from contextlib import contextmanager
from logging.config import fileConfig

import alembic


class ConfigStub:
    """env.py のロギング分岐を通る最小設定。"""

    config_file_name: str = {str(_ALEMBIC_CONFIG_PATH)!r}


class ContextStub:
    """env.py をオフライン実行する最小 Alembic context。"""

    def __init__(self) -> None:
        self.config = ConfigStub()

    def is_offline_mode(self) -> bool:
        """実接続を行わない経路を選ぶ。"""
        return True

    def configure(self, **options: object) -> None:
        """オフライン migration の設定を受け取る。"""

    @contextmanager
    def begin_transaction(self) -> Iterator[None]:
        """テスト用の空トランザクションを供給する。"""
        yield

    def run_migrations(self) -> None:
        """オフライン migration の実行要求を受け取る。"""


def snapshot_handler(handler: logging.Handler) -> dict[str, object]:
    """ハンドラを安定して JSON 化できる形へ正規化する。"""
    formatter = handler.formatter
    stream = getattr(handler, "stream", None)
    return {{
        "class_name": type(handler).__name__,
        "level": logging.getLevelName(handler.level),
        "formatter_class_name": (
            type(formatter).__name__ if formatter is not None else None
        ),
        "formatter_format": getattr(formatter, "_fmt", None),
        "formatter_datefmt": getattr(formatter, "datefmt", None),
        "has_filters": bool(handler.filters),
        "stream_name": getattr(stream, "name", repr(stream)),
    }}


def snapshot_root_logger() -> dict[str, object]:
    """root ロガーの比較対象項目を返す。"""
    root_logger = logging.getLogger()
    return {{
        "level": logging.getLevelName(root_logger.level),
        "handlers": [snapshot_handler(handler) for handler in root_logger.handlers],
    }}


def snapshot_named_logger(name: str) -> dict[str, object]:
    """名前付きロガーの比較対象項目を返す。"""
    logger = logging.getLogger(name)
    return {{
        "level": logging.getLevelName(logger.level),
        "propagate": logger.propagate,
        "disabled": logger.disabled,
        "handlers": [snapshot_handler(handler) for handler in logger.handlers],
    }}


alembic.context = ContextStub()
application_logger = logging.getLogger("pitchlog.api.errors")
sentinel_logger = logging.getLogger("pitchlog_sentinel_disabled")
sentinel_logger.disabled = True

RUN_LOGGING_CONFIGURATION

snapshot = {{
    "root": snapshot_root_logger(),
    "alembic": snapshot_named_logger("alembic"),
    "sqlalchemy.engine": snapshot_named_logger("sqlalchemy.engine"),
    "pitchlog.api.errors": {{"disabled": application_logger.disabled}},
    "pitchlog_sentinel_disabled": {{"disabled": sentinel_logger.disabled}},
}}
print(json.dumps(snapshot, sort_keys=True))
'''


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


def _logging_probe_script(action: Literal["environment", "default"]) -> str:
    """指定したロギング設定経路を実行する子プロセスコードを返す。

    Args:
        action: env.py または fileConfig の既定引数を選ぶ識別子。

    Returns:
        子プロセスへ渡す Python コード。
    """
    if action == "environment":
        statement = f"runpy.run_path({str(_ENVIRONMENT_PATH)!r})"
    else:
        statement = f"fileConfig({str(_ALEMBIC_CONFIG_PATH)!r})"
    return _LOGGING_PROBE_SCRIPT.replace("RUN_LOGGING_CONFIGURATION", statement)


def _run_logging_probe(
    action: Literal["environment", "default"],
) -> _LoggingSnapshot:
    """隔離した子プロセスでロギング状態を取得する。

    Args:
        action: env.py または fileConfig の既定引数を選ぶ識別子。

    Returns:
        比較対象だけを含む正規化済みスナップショット。
    """
    environment = os.environ.copy()
    environment["PITCHLOG_MIGRATION_DATABASE_URL"] = (
        "postgresql://user:password@db.example/pitchlog"
    )
    completed_process = subprocess.run(
        [sys.executable, "-c", _logging_probe_script(action)],
        cwd=_BACKEND_PATH,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed_process.returncode == 0, completed_process.stderr
    return cast(_LoggingSnapshot, json.loads(completed_process.stdout))


@pytest.fixture(scope="module")
def logging_snapshots() -> tuple[_LoggingSnapshot, _LoggingSnapshot]:
    """env.py 経路と既定引数経路の状態を 1 回ずつ取得する。

    Returns:
        env.py 経路、fileConfig の既定引数経路の順に並べた状態。
    """
    return _run_logging_probe("environment"), _run_logging_probe("default")


def test_environment_keeps_application_logger_enabled(
    logging_snapshots: tuple[_LoggingSnapshot, _LoggingSnapshot],
) -> None:
    """env.py の適用後もアプリのロガーが有効だと示す。"""
    environment_snapshot, _ = logging_snapshots

    assert not environment_snapshot["pitchlog.api.errors"]["disabled"]


def test_default_file_config_disables_application_logger(
    logging_snapshots: tuple[_LoggingSnapshot, _LoggingSnapshot],
) -> None:
    """既定引数の fileConfig が対照ロガーを無効化すると示す。"""
    _, default_snapshot = logging_snapshots

    assert default_snapshot["pitchlog.api.errors"]["disabled"]


def test_environment_preserves_alembic_logging_configuration(
    logging_snapshots: tuple[_LoggingSnapshot, _LoggingSnapshot],
) -> None:
    """引数差が Alembic 側の比較対象項目を変えないと示す。"""
    environment_snapshot, default_snapshot = logging_snapshots

    assert environment_snapshot["root"] == default_snapshot["root"]
    assert environment_snapshot["alembic"] == default_snapshot["alembic"]
    assert (
        environment_snapshot["sqlalchemy.engine"]
        == default_snapshot["sqlalchemy.engine"]
    )


def test_environment_reenables_disabled_non_configured_logger(
    logging_snapshots: tuple[_LoggingSnapshot, _LoggingSnapshot],
) -> None:
    """非列挙ロガーを再有効化する現在の副作用を記録する。"""
    environment_snapshot, _ = logging_snapshots

    # 表明 1〜3 が成立したまま本表明だけが落ちた場合は、副作用が消えた
    # (= より安全になった)ことを意味する。副作用を復活させてはならない。
    # 本表明を更新または撤去し、計画書の記述を現況化する。
    assert not environment_snapshot["pitchlog_sentinel_disabled"]["disabled"]
