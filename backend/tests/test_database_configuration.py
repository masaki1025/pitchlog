"""アプリと Alembic のデータベース設定契約を検証する。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, event

from pitchlog.db.config import DatabaseConfigurationError
from pitchlog.db.engine import (
    create_database_engine,
    engine_connect_args,
    engine_connect_args_violations,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PRODUCT_SOURCE_ROOTS = (
    _BACKEND_ROOT / "src",
    _BACKEND_ROOT / "migrations",
)
_DATABASE_SETTINGS = (
    "PITCHLOG_DATABASE_URL",
    "PITCHLOG_DATABASE_POOLED",
    "PITCHLOG_MIGRATION_DATABASE_URL",
)
_DIRECT_DATABASE_URL = "postgresql://user:password@db.example/pitchlog"


class _ConnectionIntercepted(Exception):
    """DBAPI 接続直前の引数を取得したことを表す。"""


def _clear_database_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """3 つの製品 DB 設定を未設定にする。

    Args:
        monkeypatch: 環境変数をテスト終了時に復元する fixture。
    """
    for variable_name in _DATABASE_SETTINGS:
        monkeypatch.delenv(variable_name, raising=False)


def _alembic_config() -> Config:
    """Backend 配下の Alembic 設定を返す。

    Returns:
        Offline migration に用いる設定。
    """
    return Config(str(_BACKEND_ROOT / "alembic.ini"))


def _run_offline_upgrade() -> None:
    """DB 接続なしで Alembic の設定消費経路を実行する。"""
    command.upgrade(_alembic_config(), "head", sql=True)


def _observe_connection_parameters(engine: Engine) -> dict[str, object]:
    """DBAPI 接続直前に engine が渡すキーワード引数を取得する。

    Args:
        engine: 検査対象の実 Engine。

    Returns:
        Psycopg の connect 関数へ渡されるキーワード引数。
    """
    observed: dict[str, object] = {}

    def capture_parameters(
        dialect: object,
        connection_record: object,
        positional_arguments: list[object],
        keyword_arguments: dict[str, object],
    ) -> None:
        observed.update(keyword_arguments)
        raise _ConnectionIntercepted

    event.listen(engine, "do_connect", capture_parameters)
    with pytest.raises(_ConnectionIntercepted):
        engine.connect()
    return observed


def _product_python_sources() -> Iterator[Path]:
    """製品コード領域で見つかった全 Python ファイルを返す。

    Yields:
        ``backend/src`` または ``backend/migrations`` 配下の Python ファイル。
    """
    for source_root in _PRODUCT_SOURCE_ROOTS:
        yield from source_root.rglob("*.py")


def _setting_consumer_paths(variable_name: str) -> set[str]:
    """設定キー名が現れる製品コードのモジュール集合を返す。

    Args:
        variable_name: 探索する設定キー名。

    Returns:
        Backend ルートからの相対パス集合。
    """
    return {
        path.relative_to(_BACKEND_ROOT).as_posix()
        for path in _product_python_sources()
        if variable_name in path.read_text(encoding="utf-8")
    }


def test_all_unset_database_settings_fail_with_named_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3 キーがすべて未設定なら各消費経路を明示的に失敗させる。"""
    _clear_database_settings(monkeypatch)

    with pytest.raises(DatabaseConfigurationError, match="PITCHLOG_DATABASE_URL"):
        create_database_engine()
    with pytest.raises(
        DatabaseConfigurationError,
        match="PITCHLOG_MIGRATION_DATABASE_URL",
    ):
        _run_offline_upgrade()


def test_application_url_does_not_fall_back_to_migration_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration URL だけではアプリ engine を生成しない。"""
    _clear_database_settings(monkeypatch)
    monkeypatch.setenv("PITCHLOG_MIGRATION_DATABASE_URL", _DIRECT_DATABASE_URL)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")

    with pytest.raises(DatabaseConfigurationError, match="PITCHLOG_DATABASE_URL"):
        create_database_engine()


def test_migration_url_does_not_fall_back_to_application_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """アプリ URL だけでは Alembic を実行しない。"""
    _clear_database_settings(monkeypatch)
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", _DIRECT_DATABASE_URL)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")

    with pytest.raises(
        DatabaseConfigurationError,
        match="PITCHLOG_MIGRATION_DATABASE_URL",
    ):
        _run_offline_upgrade()


def test_pooled_flag_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pooler フラグ未設定ではアプリ engine を生成しない。"""
    _clear_database_settings(monkeypatch)
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", _DIRECT_DATABASE_URL)

    with pytest.raises(
        DatabaseConfigurationError,
        match="PITCHLOG_DATABASE_POOLED",
    ):
        create_database_engine()


def test_pooled_flag_accepts_only_explicit_boolean_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pooler フラグの推測可能な別表記を拒否する。"""
    _clear_database_settings(monkeypatch)
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", _DIRECT_DATABASE_URL)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "yes")

    with pytest.raises(DatabaseConfigurationError, match="true または false"):
        create_database_engine()


def test_same_direct_url_is_valid_when_not_pooled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 pooler 構成ではアプリと Alembic が同じ direct URL を利用できる。"""
    _clear_database_settings(monkeypatch)
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", _DIRECT_DATABASE_URL)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    monkeypatch.setenv("PITCHLOG_MIGRATION_DATABASE_URL", _DIRECT_DATABASE_URL)

    engine = create_database_engine()
    try:
        assert engine.dialect.driver == "psycopg"
        assert engine_connect_args(False) == {}
        assert "prepare_threshold" not in _observe_connection_parameters(engine)
        _run_offline_upgrade()
    finally:
        engine.dispose()


def test_pooled_engine_has_prepare_threshold_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実 Engine が pooler 利用時の psycopg 接続引数を保持すると示す。"""
    _clear_database_settings(monkeypatch)
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", _DIRECT_DATABASE_URL)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "true")

    engine = create_database_engine()
    try:
        connect_args = _observe_connection_parameters(engine)
        assert connect_args["prepare_threshold"] is None
        assert engine_connect_args_violations(True, connect_args) == []
    finally:
        engine.dispose()


def test_missing_prepare_threshold_is_reported_as_a_violation() -> None:
    """Pooler 用接続引数から prepare_threshold を落とす負例を拒否する。"""
    assert engine_connect_args_violations(True, {}) == [
        "pooler 利用時は prepare_threshold=None が必要"
    ]


def test_prepare_threshold_for_non_pooled_engine_is_reported_as_a_violation() -> None:
    """非 pooler 用接続引数への prepare_threshold 追加を拒否する。"""
    assert engine_connect_args_violations(False, {"prepare_threshold": None}) == [
        "pooler 非利用時は prepare_threshold を指定しない"
    ]


@pytest.mark.parametrize(
    ("variable_name", "expected_consumer"),
    [
        ("PITCHLOG_DATABASE_URL", "src/pitchlog/db/engine.py"),
        ("PITCHLOG_DATABASE_POOLED", "src/pitchlog/db/engine.py"),
        ("PITCHLOG_MIGRATION_DATABASE_URL", "migrations/env.py"),
    ],
)
def test_database_setting_has_exactly_one_product_consumer(
    variable_name: str,
    expected_consumer: str,
) -> None:
    """ディレクトリ全走査で設定キーの製品側消費者を一意に保つ。"""
    assert _setting_consumer_paths(variable_name) == {expected_consumer}
