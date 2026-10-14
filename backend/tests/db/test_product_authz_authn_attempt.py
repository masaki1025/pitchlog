"""ログイン試行の予約票、成功経路、旧関数の不在を実 DB で検査する。"""

from __future__ import annotations

import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID, uuid4

import psycopg
import pytest

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _SETTINGS,
    _app_dsn,
    _counter,
    _seed_identity,
    _seed_settings,
    _setting,
)

pytestmark = pytest.mark.requires_db


def _attempt(
    dsn: str, name: str, password: str, source: str
) -> tuple[UUID | None, int, float, datetime | None]:
    """接続を閉じてから、発行結果・待ち時間・経過時間・期限を返す。"""
    started = time.monotonic()
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT token_id, wait_ms, expires_at FROM authn.login_attempt(%s, %s, %s)",
            (name, password, source),
        )
        row = cursor.fetchone()
        assert row is not None
        token_id, wait_ms, expires_at = row
    assert isinstance(wait_ms, int)
    assert (token_id is None and expires_at is None) or (
        isinstance(token_id, UUID) and isinstance(expires_at, datetime)
    )
    return token_id, wait_ms, time.monotonic() - started, expires_at


def _reservation(
    catalog: ProvisionedProductCatalog, source: str
) -> tuple[int, datetime]:
    """現在窓の失敗数と予約時刻を内部側から読む。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT attempt_count, locked_until
            FROM public.rate_limit_counters
            WHERE scope_key = %s
            ORDER BY window_start DESC LIMIT 1
            """,
            (f"src:{source}",),
        )
        row = cursor.fetchone()
    catalog.observer.rollback()
    assert row is not None
    count, until = row
    assert isinstance(count, int) and isinstance(until, datetime)
    return count, until


def test_old_login_is_absent_and_token_id_names_issued_row(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """旧 2 引数関数は存在せず、成功がトークン行 ID を返す。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_catalog.to_regprocedure('authn.login(text, text)'),
                   pg_catalog.to_regprocedure(
                       'authn.login_attempt(text, text, text)')
            """
        )
        row = cursor.fetchone()
    catalog.observer.rollback()
    assert row is not None and row[0] is None and row[1] is not None
    token, wait_ms, _, expires_at = _attempt(
        identity.app_dsn, identity.name, identity.password, uuid4().hex
    )
    assert isinstance(token, UUID) and token != identity.tenant_id
    assert wait_ms == 0
    assert isinstance(expires_at, datetime)
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT id, tenant_id, expires_at FROM public.tenant_tokens WHERE id = %s",
            (token,),
        )
        assert cursor.fetchone() == (token, identity.tenant_id, expires_at)
    catalog.observer.rollback()


def test_success_bypasses_failure_lock_and_does_not_change_ticket(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """先行失敗と同じ試行元のロックを保持中でも成功を通す。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    source = uuid4().hex
    wrong = secrets.token_urlsafe(24)
    for _ in range(5):
        assert _attempt(identity.app_dsn, identity.name, wrong, source)[0] is None
    before = _reservation(catalog, source)
    baseline = _attempt(
        identity.app_dsn, identity.name, identity.password, uuid4().hex
    )[2]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(identity.app_dsn) as holder:
            holder.execute(
                "SELECT pg_catalog.pg_advisory_xact_lock(87001224, "
                "pg_catalog.hashtext(%s))",
                (f"src:{source}",),
            )
            future = pool.submit(
                _attempt, identity.app_dsn, identity.name, identity.password, source
            )
            try:
                token, wait_ms, elapsed, expires_at = future.result(timeout=5)
            finally:
                holder.rollback()
    assert isinstance(token, UUID) and wait_ms == 0
    assert isinstance(expires_at, datetime)
    assert elapsed < baseline + 2
    assert _reservation(catalog, source) == before


def test_failure_reservations_serialize_and_return_staggered_waits(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """同一試行元の予約時刻が間隔ずつ進み、待ち時間は戻り値だけになる。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    step_ms = 750
    _setting(catalog, "auth.team_login.throttle_step_ms", step_ms)
    _setting(catalog, "auth.team_login.throttle_max_ms", step_ms * 10)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    source = uuid4().hex
    wrong = secrets.token_urlsafe(24)
    threshold = _SETTINGS["auth.team_login.throttle_threshold"]
    window_seconds = _SETTINGS["auth.team_login.window_seconds"]
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.rate_limit_counters
                (id, scope_key, window_start, attempt_count, locked_until)
            VALUES (
                %s, %s,
                pg_catalog.to_timestamp(pg_catalog.floor(
                    extract(epoch FROM pg_catalog.clock_timestamp()) / %s) * %s),
                %s, pg_catalog.clock_timestamp() + interval '2 seconds'
            )
            """,
            (uuid4(), f"src:{source}", window_seconds, window_seconds, threshold + 1),
        )
    catalog.applicator.commit()
    first = _attempt(identity.app_dsn, identity.name, wrong, source)
    first_count, first_until = _reservation(catalog, source)
    second = _attempt(identity.app_dsn, identity.name, wrong, source)
    second_count, second_until = _reservation(catalog, source)
    assert first[0] is second[0] is None
    assert first_count == threshold + 2 and second_count == threshold + 3
    assert (second_until - first_until).total_seconds() * 1000 == step_ms
    assert second[1] > first[1]
    assert first[2] < first[1] / 1000


def test_previous_window_count_and_ticket_cross_boundary(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """直前窓の失敗数と予約時刻を現窓へ引き継ぐ。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    source = uuid4().hex
    window_seconds = _SETTINGS["auth.team_login.window_seconds"]
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.rate_limit_counters
                (id, scope_key, window_start, attempt_count, locked_until)
            VALUES (
                %s, %s,
                pg_catalog.to_timestamp(pg_catalog.floor(
                    extract(epoch FROM pg_catalog.clock_timestamp()) / %s) * %s)
                    - %s * interval '1 second',
                %s, pg_catalog.clock_timestamp() + interval '2 seconds'
            )
            """,
            (
                uuid4(),
                f"src:{source}",
                window_seconds,
                window_seconds,
                window_seconds,
                _SETTINGS["auth.team_login.throttle_threshold"] + 1,
            ),
        )
    catalog.applicator.commit()
    previous_count, previous_until = _reservation(catalog, source)
    token, wait_ms, _, expires_at = _attempt(
        identity.app_dsn, identity.name, secrets.token_urlsafe(24), source
    )
    assert token is None
    assert expires_at is None
    assert wait_ms == _SETTINGS["auth.team_login.throttle_max_ms"]
    current_count, current_until = _reservation(catalog, source)
    assert previous_count == _SETTINGS["auth.team_login.throttle_threshold"] + 1
    assert current_count == 1 and current_until > previous_until
    assert [row[1] for row in _counter(catalog, f"src:{source}")] == [
        _SETTINGS["auth.team_login.throttle_threshold"] + 1,
        1,
    ]
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_catalog.pg_try_advisory_xact_lock(
                87001224, pg_catalog.hashtext(%s))
            """,
            (f"src:{source}",),
        )
        assert cursor.fetchone() == (True,)
    catalog.observer.rollback()
    time.sleep(wait_ms / 1000)
