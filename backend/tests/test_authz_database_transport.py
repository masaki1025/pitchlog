"""アプリ用 engine の DB 通信経路制限を検証する。"""

import pytest
from sqlalchemy import Engine, event

from pitchlog.authz.database_transport import DatabaseTransportConfigurationError
from pitchlog.db import engine as engine_module

_DATABASE_URL_VARIABLE = "PITCHLOG_DATABASE_URL"


class _ConnectionObserved(Exception):
    """DBAPI 接続前の引数を観測したことを表す。"""


def _create_engine(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Engine:
    """DB へ接続せず製品の engine 生成経路を実行する。

    Args:
        monkeypatch: 環境設定を試験内に閉じる fixture。
        database_url: 試験対象の接続 URL。

    Returns:
        接続前の SQLAlchemy engine。
    """
    monkeypatch.setenv(_DATABASE_URL_VARIABLE, database_url)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    return engine_module.create_database_engine()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://user:password@127.0.0.1/pitchlog?sslmode=disable",
        "postgresql://user:password@[::1]/pitchlog?sslmode=disable",
        "postgresql://user:password@/pitchlog?host=%2Ftmp&sslmode=disable",
        "postgresql://user:password@db.example/pitchlog?sslmode=verify-full",
        "postgresql://user:password@db.example/pitchlog?host=127.0.0.1&sslmode=disable",
    ],
)
def test_engine_accepts_explicit_local_or_verified_tls(
    monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    """正規化後の接続先がローカルか証明書検証付き TLS なら生成する。"""
    engine = _create_engine(monkeypatch, database_url)
    try:
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("database_url", "reason"),
    [
        ("postgresql://user:password@127.0.0.1/pitchlog", "sslmode の明示"),
        ("postgresql://user:password@db.example/pitchlog", "sslmode の明示"),
        (
            "postgresql://user:password@db.example/pitchlog?sslmode=prefer",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@db.example/pitchlog?sslmode=require",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@db.example/pitchlog?sslmode=verify-ca",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@db.example/pitchlog?sslmode=disable",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@localhost/pitchlog?sslmode=disable",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@/pitchlog?sslmode=disable",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@127.0.0.1/pitchlog?host=db.example&sslmode=disable",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@127.0.0.1/pitchlog?hostaddr=203.0.113.1&sslmode=disable",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@127.0.0.1/pitchlog?hostaddr=%2Ftmp&sslmode=disable",
            "ローカルか証明書検証付き TLS",
        ),
        (
            "postgresql://user:password@127.0.0.1/pitchlog?host=127.0.0.1,db.example&sslmode=disable",
            "ローカルか証明書検証付き TLS",
        ),
    ],
)
def test_engine_rejects_unverified_or_ambiguous_transport(
    monkeypatch: pytest.MonkeyPatch, database_url: str, reason: str
) -> None:
    """Engine 生成時に未指定・弱い TLS・不明な接続先を拒否する。"""
    with pytest.raises(DatabaseTransportConfigurationError, match=reason) as error:
        _create_engine(monkeypatch, database_url)
    assert "user:password" not in str(error.value)


def test_engine_checks_connect_args_after_url_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """接続引数の上書き後に不正となる通信経路を拒否する。"""
    monkeypatch.setattr(
        engine_module,
        "engine_connect_args",
        lambda pooled: {"host": "db.example", "sslmode": "disable"},
    )
    with pytest.raises(DatabaseTransportConfigurationError):
        _create_engine(
            monkeypatch,
            "postgresql://user:password@127.0.0.1/pitchlog?sslmode=verify-full",
        )


def test_verified_tls_reaches_dbapi_with_gss_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実 engine が証明書検証と GSS 無効化を DBAPI へ渡す。"""
    engine = _create_engine(
        monkeypatch,
        "postgresql://user:password@db.example/pitchlog?sslmode=verify-full",
    )
    observed: dict[str, object] = {}

    def observe(
        dialect: object,
        connection_record: object,
        positional_arguments: list[object],
        keyword_arguments: dict[str, object],
    ) -> None:
        """接続直前のキーワード引数を記録して実 DB 接続を止める。"""
        observed.update(keyword_arguments)
        raise _ConnectionObserved

    try:
        event.listen(engine, "do_connect", observe)
        with pytest.raises(_ConnectionObserved):
            engine.connect()
        assert observed["sslmode"] == "verify-full"
        assert observed["gssencmode"] == "disable"
    finally:
        engine.dispose()


def test_engine_rejects_environment_hostaddr_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Libpq 環境変数でローカル接続先を変更できない。"""
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.1")
    with pytest.raises(DatabaseTransportConfigurationError):
        _create_engine(
            monkeypatch,
            "postgresql://user:password@127.0.0.1/pitchlog?sslmode=disable",
        )
