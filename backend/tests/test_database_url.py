"""PostgreSQL URL の正規化と engine 生成を検証する。"""

import pytest
from sqlalchemy.engine import make_url

from pitchlog.db.engine import create_database_engine
from pitchlog.db.url import normalize_postgresql_url


def test_bare_postgresql_scheme_is_rewritten_only_to_psycopg() -> None:
    """裸の scheme だけを psycopg 3 明示形へ書き換える。"""
    source = "postgresql://user:p%40ss@db.example:5432/pitchlog?sslmode=require"

    assert normalize_postgresql_url(source) == (
        "postgresql+psycopg://user:p%40ss@db.example:5432/pitchlog?sslmode=require"
    )


def test_explicit_psycopg_scheme_is_unchanged() -> None:
    """既に psycopg 3 を明示した URL は変更しない。"""
    source = "postgresql+psycopg://user:password@db.example/pitchlog"

    assert normalize_postgresql_url(source) == source


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg2://user:password@db.example/pitchlog",
        "postgresql+asyncpg://user:password@db.example/pitchlog",
    ],
)
def test_explicit_other_postgresql_driver_is_rejected(database_url: str) -> None:
    """Psycopg 以外の明示的な PostgreSQL ドライバを拒否する。"""
    with pytest.raises(ValueError, match="psycopg 以外"):
        normalize_postgresql_url(database_url)


def test_application_engine_uses_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """アプリ用 URL が正規化を経由して psycopg 3 engine になる。"""
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL",
        "postgresql://user:password@db.example/pitchlog",
    )

    engine = create_database_engine()
    try:
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_bypassing_normalization_selects_psycopg2_and_is_red() -> None:
    """裸の URL を直接解釈すると psycopg 3 の検査が red になると示す。"""
    dialect = make_url("postgresql://user:password@db.example/pitchlog").get_dialect()

    assert dialect.driver == "psycopg2"
