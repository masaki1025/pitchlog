"""レート制限行の累積監視を実 DB で検査する。"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import _SETTINGS, _app_dsn, _seed_settings, _setting
from .test_product_authz_authn_limited import _admin_dsn

pytestmark = pytest.mark.requires_db


def _rows(catalog: ProvisionedProductCatalog) -> tuple[tuple[object, ...], ...]:
    """監視前後の全行を同じ順序で読む。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT id, scope_key, window_start, attempt_count, locked_until "
            "FROM public.rate_limit_counters ORDER BY id"
        )
        rows = tuple(cursor.fetchall())
    catalog.observer.rollback()
    return rows


def _observe(catalog: ProvisionedProductCatalog) -> tuple[int, int]:
    """管理関数所有用ロールから観測関数の二値を読む。"""
    with psycopg.connect(_admin_dsn(catalog)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE pitchlog_management_fn_owner")
            cursor.execute("SELECT * FROM authn.observe_rate_limit_counters()")
            row = cursor.fetchone()
    assert row is not None and len(row) == 2
    assert isinstance(row[0], int) and isinstance(row[1], int)
    return row[0], row[1]


def test_observation_counts_all_keys_and_keeps_every_row(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """現窓外の行と鍵の種類を表全体で数え、全行を保つ。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    window_seconds = _SETTINGS["auth.team_login.window_seconds"] * 100_000
    _setting(catalog, "auth.team_login.window_seconds", window_seconds)
    assert _rows(catalog) == ()

    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.to_timestamp(pg_catalog.floor("
            "extract(epoch FROM pg_catalog.clock_timestamp()) / %s::numeric) * %s)",
            (window_seconds, window_seconds),
        )
        row = cursor.fetchone()
        assert row is not None and isinstance(row[0], datetime)
        window_begin = row[0]
        source = f"src:{uuid4().hex}"
        entries = (
            (source, window_begin),
            (source, window_begin - timedelta(seconds=window_seconds)),
            (f"team:{uuid4().hex}", window_begin - timedelta(seconds=window_seconds)),
            (f"admin:{uuid4().hex}", window_begin + timedelta(seconds=window_seconds)),
        )
        cursor.executemany(
            "INSERT INTO public.rate_limit_counters "
            "(id, scope_key, window_start, attempt_count) "
            "VALUES (%s, %s, %s, 1)",
            [(uuid4(), scope, start) for scope, start in entries],
        )
    catalog.applicator.commit()

    before = _rows(catalog)
    assert len(before) == len(entries)
    assert _observe(catalog) == (3, 3)
    assert _rows(catalog) == before


def test_application_role_cannot_execute_observation(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """アプリ用ロールからの監視関数の実行を拒否する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    with psycopg.connect(_app_dsn(catalog)) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SELECT * FROM authn.observe_rate_limit_counters()")
