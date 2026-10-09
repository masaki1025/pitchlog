"""アプリ用認証関数の DB 挙動、失敗経路、並行境界を検査する。"""

from __future__ import annotations

import json
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any, Iterator, LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_ROOT = Path(__file__).resolve().parents[3]
_LOGIN_BODY = (
    _ROOT
    / "contracts/authz/product/function-bodies/functions"
    / "FUNCTION:authn:login_attempt(text, text, text).sql"
)
_SETTINGS = {
    "auth.token_ttl_seconds": 3600,
    "auth.team_login.window_seconds": 3600,
    "auth.team_login.throttle_threshold": 3,
    "auth.team_login.throttle_step_ms": 25,
    "auth.team_login.throttle_max_ms": 200,
}
_TEAM_LOGIN_SETTING_KEYS = (
    "auth.team_login.window_seconds",
    "auth.team_login.throttle_threshold",
    "auth.team_login.throttle_step_ms",
    "auth.team_login.throttle_max_ms",
)


@dataclass(frozen=True, slots=True)
class _Identity:
    tenant_id: UUID
    subject_id: UUID
    name: str
    password: str
    app_dsn: str


def _app_dsn(catalog: ProvisionedProductCatalog) -> str:
    """使い捨てアプリロールへ試験内だけの資格情報を与える。"""
    password = secrets.token_urlsafe(24)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER ROLE pitchlog_app PASSWORD {}").format(sql.Literal(password))
        )
    catalog.applicator.commit()
    return make_conninfo(catalog.owner_dsn, user="pitchlog_app", password=password)


def _setting(catalog: ProvisionedProductCatalog, key: str, value: object) -> None:
    """設定値を試験用 DB で更新する。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.system_settings(key, value)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, json.dumps(value)),
        )
    catalog.applicator.commit()


def _seed_settings(catalog: ProvisionedProductCatalog) -> None:
    """発行と計数に必要な有効な設定値を置く。"""
    for key, value in _SETTINGS.items():
        _setting(catalog, key, value)


def _seed_identity(
    catalog: ProvisionedProductCatalog,
    app_dsn: str,
    *,
    name: str | None = None,
    enabled: bool = True,
    retired: bool = False,
) -> _Identity:
    """Superuser で認証主体を作り、実アプリ接続で使う情報を返す。"""
    tenant_id = uuid4()
    subject_id = uuid4()
    team_name = name or f"team{tenant_id.hex[:12]}"
    password = secrets.token_urlsafe(24) + "A1"
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.tenants(id, name, enabled, disabled_at, retired_at)
            VALUES (%s, %s, %s,
                    CASE WHEN %s THEN NULL ELSE pg_catalog.clock_timestamp() END,
                    CASE WHEN %s THEN pg_catalog.clock_timestamp() ELSE NULL END)
            """,
            (tenant_id, team_name, enabled, enabled, retired),
        )
        cursor.execute(
            "INSERT INTO public.tenant_auth_subjects(id, tenant_id) VALUES (%s, %s)",
            (subject_id, tenant_id),
        )
        cursor.execute(
            """
            INSERT INTO public.tenant_credentials(auth_subject_id, password_hash)
            VALUES (%s, authn_crypto.crypt(%s, authn_crypto.gen_salt('bf', 12)))
            """,
            (subject_id, password),
        )
    catalog.applicator.commit()
    return _Identity(tenant_id, subject_id, team_name, password, app_dsn)


def _scalar(dsn: str, statement: LiteralString, params: tuple[object, ...]) -> Any:
    """実アプリ接続で 1 つの認証関数を呼び、変更を確定する。"""
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(statement, params)
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def _login(
    identity: _Identity,
    *,
    name: str | None = None,
    password: str | None = None,
    source: str | None = None,
) -> UUID | None:
    """アプリ用ロールでログインする。"""
    return _scalar(
        identity.app_dsn,
        "SELECT token_id FROM authn.login_attempt(%s, %s, %s)",
        (
            identity.name if name is None else name,
            identity.password if password is None else password,
            identity.tenant_id.hex if source is None else source,
        ),
    )


def _scope(identity: _Identity) -> str:
    """認証試験で固定する試行元のカウンタ鍵を返す。"""
    return f"src:{identity.tenant_id.hex}"


def _verify(identity: _Identity, token: UUID) -> UUID | None:
    """アプリ用ロールでトークンを検証する。"""
    return _scalar(identity.app_dsn, "SELECT authn.verify_token(%s)", (token,))


def _change(
    identity: _Identity, token: UUID, current: str | None, new: str | None
) -> bool:
    """アプリ用ロールでパスワード変更を呼ぶ。"""
    return _scalar(
        identity.app_dsn,
        "SELECT authn.change_password(%s, %s, %s)",
        (token, current, new),
    )


def _credential(
    catalog: ProvisionedProductCatalog, subject_id: UUID
) -> tuple[int, str, datetime]:
    """世代・ハッシュ・変更日時を内部側から観測する。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT generation, password_hash, password_changed_at
            FROM public.tenant_credentials WHERE auth_subject_id = %s
            """,
            (subject_id,),
        )
        row = cursor.fetchone()
    catalog.observer.rollback()
    assert row is not None
    generation, password_hash, changed_at = row
    assert isinstance(generation, int)
    assert isinstance(password_hash, str)
    assert isinstance(changed_at, datetime)
    return generation, password_hash, changed_at


def _token(
    catalog: ProvisionedProductCatalog, token_id: UUID
) -> tuple[datetime, datetime]:
    """期限と最終使用時刻を内部側から観測する。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT expires_at, last_used_at FROM public.tenant_tokens WHERE id = %s",
            (token_id,),
        )
        row = cursor.fetchone()
    catalog.observer.rollback()
    assert row is not None
    expires_at, last_used_at = row
    assert isinstance(expires_at, datetime)
    assert isinstance(last_used_at, datetime)
    return expires_at, last_used_at


def _counter(catalog: ProvisionedProductCatalog, scope: str) -> list[tuple[Any, ...]]:
    """同じ単位の計数行を内部側から読む。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT window_start, attempt_count FROM public.rate_limit_counters
            WHERE scope_key = %s ORDER BY window_start
            """,
            (scope,),
        )
        rows = cursor.fetchall()
    catalog.observer.rollback()
    return rows


def test_login_verify_logout_and_failure_count_commit(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """発行・延長・失効と、NULL 失敗が例外なしでコミットされることを検査する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    wrong = secrets.token_urlsafe(24)
    assert _login(identity, password=wrong) is None
    assert _counter(catalog, _scope(identity))[0][1] == 1
    token = _login(identity)
    assert isinstance(token, UUID)
    before = _token(catalog, token)
    assert _verify(identity, token) == identity.tenant_id
    after = _token(catalog, token)
    assert after[0] >= before[0]
    assert after[1] >= before[1]
    assert _scalar(identity.app_dsn, "SELECT authn.logout(%s)", (token,)) == ""
    logged_out = _token(catalog, token)
    assert _verify(identity, token) is None
    assert _token(catalog, token) == logged_out
    assert logged_out[0] >= logged_out[1]


@pytest.mark.parametrize(
    "invalid",
    ["expired", "logged_out", "old_generation", "disabled", "retired", "wrong_tenant"],
)
def test_change_password_requires_the_same_valid_token_as_verify(
    provisioned_product_catalog: ProvisionedProductCatalog,
    invalid: str,
) -> None:
    """期限・世代・状態・所属が無効なら検証も PW 更新も拒否する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    token = _login(identity)
    assert isinstance(token, UUID)
    target = token
    other = (
        _seed_identity(catalog, identity.app_dsn) if invalid == "wrong_tenant" else None
    )
    with catalog.applicator.cursor() as cursor:
        if invalid == "expired":
            cursor.execute(
                """
                UPDATE public.tenant_tokens
                SET last_used_at = pg_catalog.clock_timestamp() - interval '2 seconds',
                    expires_at = pg_catalog.clock_timestamp() - interval '1 second'
                WHERE id = %s
                """,
                (token,),
            )
        elif invalid == "old_generation":
            cursor.execute(
                "UPDATE public.tenant_credentials "
                "SET generation = generation + 1 WHERE auth_subject_id = %s",
                (identity.subject_id,),
            )
        elif invalid == "disabled":
            cursor.execute(
                "UPDATE public.tenants SET enabled = false, "
                "disabled_at = pg_catalog.clock_timestamp() WHERE id = %s",
                (identity.tenant_id,),
            )
        elif invalid == "retired":
            cursor.execute(
                "UPDATE public.tenants SET retired_at = "
                "pg_catalog.clock_timestamp() WHERE id = %s",
                (identity.tenant_id,),
            )
        elif invalid == "wrong_tenant":
            assert other is not None
            cursor.execute(
                "ALTER TABLE public.tenant_tokens "
                "DROP CONSTRAINT fk_tenant_tokens_subject"
            )
            target = uuid4()
            cursor.execute(
                """
                INSERT INTO public.tenant_tokens
                    (id, tenant_id, auth_subject_id, credential_generation,
                     expires_at, last_used_at)
                VALUES (%s, %s, %s, 1,
                        pg_catalog.clock_timestamp() + interval '1 hour',
                        pg_catalog.clock_timestamp())
                """,
                (target, other.tenant_id, identity.subject_id),
            )
    catalog.applicator.commit()
    if invalid == "logged_out":
        assert _scalar(identity.app_dsn, "SELECT authn.logout(%s)", (token,)) == ""
    before = _credential(catalog, identity.subject_id)
    token_before = _token(catalog, target)
    assert _verify(identity, target) is None
    assert (
        _change(identity, target, identity.password, secrets.token_urlsafe(24) + "A1")
        is False
    )
    assert _credential(catalog, identity.subject_id) == before
    assert _token(catalog, target) == token_before


def test_change_password_policy_and_subject_binding(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """誤った現行 PW・未入力・7/8 文字境界と 72 バイト超を検査する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    other = _seed_identity(catalog, identity.app_dsn)
    token = _login(identity)
    assert isinstance(token, UUID)
    before = _credential(catalog, identity.subject_id)
    candidates = ("A123456", "12345678", "abcdefgh", None)
    for candidate in candidates:
        assert _change(identity, token, identity.password, candidate) is False
    assert _change(identity, token, secrets.token_urlsafe(24), "A1234567") is False
    assert _change(identity, token, None, "A1234567") is False
    assert _credential(catalog, identity.subject_id) == before
    assert _change(identity, token, identity.password, "A1234567") is True
    after = _credential(catalog, identity.subject_id)
    assert after[0] == before[0] + 1
    assert after[2] >= before[2]
    assert _credential(catalog, other.subject_id)[0] == 1
    assert _verify(identity, token) is None
    new_token = _login(identity, password="A1234567")
    assert isinstance(new_token, UUID)
    long_password = "A1" + "é" * 40
    assert len(long_password.encode("utf-8")) > 72
    assert _change(identity, new_token, "A1234567", long_password) is True
    assert _login(identity, password=long_password) is not None


def test_missing_and_invalid_token_ttl_fails_closed(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """有効期限キーの欠落と文字列・0 以下・小数を拒否する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    token = _login(identity)
    assert isinstance(token, UUID)
    for key in ("auth.token_ttl_seconds",):
        good = _SETTINGS[key]
        for bad in (None, "invalid", 0, -1, 1.5):
            with catalog.applicator.cursor() as cursor:
                if bad is None:
                    cursor.execute(
                        "DELETE FROM public.system_settings WHERE key = %s", (key,)
                    )
                else:
                    cursor.execute(
                        "UPDATE public.system_settings "
                        "SET value = %s::jsonb WHERE key = %s",
                        (json.dumps(bad), key),
                    )
            catalog.applicator.commit()
            assert _login(identity) is None
            if key == "auth.token_ttl_seconds":
                before = _token(catalog, token)
                credential_before = _credential(catalog, identity.subject_id)
                assert _verify(identity, token) is None
                assert (
                    _change(
                        identity,
                        token,
                        identity.password,
                        secrets.token_urlsafe(24) + "A1",
                    )
                    is False
                )
                assert _token(catalog, token) == before
                assert _credential(catalog, identity.subject_id) == credential_before
            _setting(catalog, key, good)


def test_token_ttl_upper_bound_is_accepted_and_next_integer_fails_closed(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """トークン期限の上限を受け、上限 + 1 では発行・延長しない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    upper = 2_147_483_647
    for key in ("auth.token_ttl_seconds",):
        good = _SETTINGS[key]
        _setting(catalog, key, upper)
        with catalog.observer.cursor() as cursor:
            cursor.execute("SELECT authn.setting_positive_integer(%s)", (key,))
            assert cursor.fetchone() == (upper,)
        catalog.observer.rollback()
        token = _login(identity)
        assert isinstance(token, UUID)
        if key == "auth.token_ttl_seconds":
            assert _verify(identity, token) == identity.tenant_id

        _setting(catalog, key, upper + 1)
        with catalog.observer.cursor() as cursor:
            cursor.execute("SELECT authn.setting_positive_integer(%s)", (key,))
            assert cursor.fetchone() == (None,)
        catalog.observer.rollback()
        assert _login(identity) is None
        if key == "auth.token_ttl_seconds":
            before = _token(catalog, token)
            assert _verify(identity, token) is None
            assert _token(catalog, token) == before
        _setting(catalog, key, good)


def test_team_login_settings_missing_or_invalid_reject_valid_credentials(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """新 4 キーの欠落・不正値で正しい資格情報の発行を拒否する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    assert isinstance(_login(identity), UUID)
    for key in _TEAM_LOGIN_SETTING_KEYS:
        good = _SETTINGS[key]
        for bad in (None, "invalid", 0, -1, 1.5):
            if bad is None:
                with catalog.applicator.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM public.system_settings WHERE key = %s", (key,)
                    )
                catalog.applicator.commit()
            else:
                _setting(catalog, key, bad)
            assert _login(identity) is None
            _setting(catalog, key, good)
        assert isinstance(_login(identity), UUID)


def test_team_login_settings_upper_bound_and_next_integer(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """新 4 キーの共通上限は受理し、上限超えでは発行しない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    upper = 2_147_483_647
    for key in _TEAM_LOGIN_SETTING_KEYS:
        good = _SETTINGS[key]
        _setting(catalog, key, upper)
        with catalog.observer.cursor() as cursor:
            cursor.execute("SELECT authn.setting_positive_integer(%s)", (key,))
            assert cursor.fetchone() == (upper,)
        catalog.observer.rollback()
        assert isinstance(_login(identity), UUID)

        _setting(catalog, key, upper + 1)
        with catalog.observer.cursor() as cursor:
            cursor.execute("SELECT authn.setting_positive_integer(%s)", (key,))
            assert cursor.fetchone() == (None,)
        catalog.observer.rollback()
        assert _login(identity) is None
        _setting(catalog, key, good)


def test_normalization_boundary_and_failed_burst_does_not_lock(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """NFKC・前後の空白でログインでき、失敗連打も正当な利用を遮らない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog), name="Foo")
    token = _login(identity, name="\tＦＯＯ\n")
    assert isinstance(token, UUID)
    for name in ("\u0085ＦＯＯ\u3000", "\u3000ＦＯＯ\u0085", "\nＦＯＯ\t"):
        assert _login(identity, name=name) is not None
    assert _login(identity, name="F O O") is None
    for _ in range(5):
        assert _login(identity, password=secrets.token_urlsafe(24)) is None
    assert _login(identity) is not None
    assert _verify(identity, token) == identity.tenant_id


def test_previous_window_is_counted_and_counter_query_uses_index(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """直前窓を残し、実関数の二窓条件と索引を EXPLAIN で確かめる。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    scope = _scope(identity)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.rate_limit_counters
                (id, scope_key, window_start, attempt_count)
            VALUES (%s, %s,
                    pg_catalog.to_timestamp(pg_catalog.floor(
                        extract(epoch FROM pg_catalog.clock_timestamp()) / %s) * %s)
                    - %s * interval '1 second', 99)
            """,
            (
                uuid4(),
                scope,
                _SETTINGS["auth.team_login.window_seconds"],
                _SETTINGS["auth.team_login.window_seconds"],
                _SETTINGS["auth.team_login.window_seconds"],
            ),
        )
    catalog.applicator.commit()
    assert _login(identity, password=secrets.token_urlsafe(24)) is None
    assert [row[1] for row in _counter(catalog, scope)] == [99, 1]
    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT routine.prosrc FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = 'authn'
              AND routine.proname = 'login_attempt'
            """
        )
        source = cursor.fetchone()
        assert source is not None
        assert source[0].count("window_begin :=") == 1
        assert source[0].index("pg_advisory_xact_lock") > source[0].index(
            "authn_crypto.crypt"
        )
        assert "pg_catalog.hashtext(source_key)" in source[0]
        assert "counter.scope_key = source_key" in source[0]
        assert "counter.window_start >= window_begin - window_seconds" in source[0]
        assert "counter.window_start <= window_begin" in source[0]
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute("SET LOCAL enable_indexscan = off")
        cursor.execute(
            """
            EXPLAIN SELECT counter.id, counter.attempt_count, counter.locked_until
            FROM public.rate_limit_counters AS counter
            WHERE counter.scope_key = %s
              AND counter.window_start >= %s
              AND counter.window_start <= %s
            ORDER BY counter.id LIMIT 1 FOR UPDATE
            """,
            (scope, cutoff, cutoff),
        )
        plan = "\n".join(str(row[0]) for row in cursor.fetchall())
    catalog.observer.rollback()
    assert "ix_rate_limit_counters_window" in plan
    assert "window_start" in plan


def _maintenance_dsn(catalog: ProvisionedProductCatalog) -> str:
    """統計拡張を置く製品 DB 以外の保守用 DB を指す。"""
    return make_conninfo(catalog.cluster.admin_dsn, dbname="postgres")


def _prepare_statements(catalog: ProvisionedProductCatalog) -> str:
    """統計拡張を保守用 DB にだけ作り、製品 DB に無いことを確かめる。"""
    maintenance_dsn = _maintenance_dsn(catalog)
    with psycopg.connect(maintenance_dsn) as maintenance:
        with maintenance.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_catalog.pg_extension WHERE extname = 'pg_stat_statements'"
        )
        assert cursor.fetchone() is None
    catalog.observer.rollback()
    return maintenance_dsn


@contextmanager
def _temporary_function_sql(
    catalog: ProvisionedProductCatalog, original: str, changed: str
) -> Iterator[None]:
    """使い捨て DB だけで関数本体を差し替え、終了時に復元する。"""
    assert original != changed
    try:
        with catalog.applicator.cursor() as cursor:
            cursor.execute(changed.encode("utf-8"))
        catalog.applicator.commit()
        yield
    finally:
        catalog.applicator.rollback()
        with catalog.applicator.cursor() as cursor:
            cursor.execute(original.encode("utf-8"))
        catalog.applicator.commit()


def _reset_observation(
    catalog: ProvisionedProductCatalog, maintenance_dsn: str
) -> None:
    """次の 1 回だけを観測するため統計をリセットする。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.pg_stat_force_next_flush()")
    catalog.applicator.commit()
    with psycopg.connect(maintenance_dsn) as maintenance:
        with maintenance.cursor() as cursor:
            cursor.execute("SELECT public.pg_stat_statements_reset()")
    with catalog.observer.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.pg_stat_reset()")
    catalog.observer.commit()


def _observation(
    catalog: ProvisionedProductCatalog, maintenance_dsn: str
) -> tuple[int, dict[int, int]]:
    """Crypt 回数と製品 DB 内の関数内部 SQL の queryid・回数を読む。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.pg_stat_clear_snapshot()")
        cursor.execute(
            """
            SELECT COALESCE(pg_catalog.sum(calls), 0)
            FROM pg_catalog.pg_stat_user_functions
            WHERE schemaname = 'authn_crypto' AND funcname = 'crypt'
            """
        )
        crypt_row = cursor.fetchone()
    catalog.observer.rollback()
    assert crypt_row is not None
    with psycopg.connect(maintenance_dsn) as maintenance:
        with maintenance.cursor() as cursor:
            cursor.execute(
                """
                SELECT queryid, calls FROM public.pg_stat_statements
                WHERE dbid = (
                    SELECT oid FROM pg_catalog.pg_database
                    WHERE datname = %s
                ) AND NOT toplevel
                ORDER BY queryid
                """,
                (catalog.observer.info.dbname,),
            )
            statements = {int(row[0]): int(row[1]) for row in cursor.fetchall()}
    return int(crypt_row[0]), statements


def _assert_cost_twelve(value: str) -> None:
    """Bcrypt の実ハッシュとダミーのコストが 12 であることを表明する。"""
    assert re.fullmatch(r"\$2[aby]\$12\$[./A-Za-z0-9]{53}", value)


def test_failed_login_paths_have_equal_count_crypt_and_nested_queries(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """設定が揃った失敗 5 種だけを比較し、欠落設定は別試験で扱う。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    active = _seed_identity(catalog, app_dsn)
    disabled = _seed_identity(catalog, app_dsn, enabled=False)
    retired = _seed_identity(catalog, app_dsn, retired=True)
    missing_name = f"missing{uuid4().hex[:12]}"
    long_name = "x" * 65
    maintenance_dsn = _prepare_statements(catalog)
    wrong = secrets.token_urlsafe(24)
    cases = (
        (active, active.name, wrong),
        (active, missing_name, active.password),
        (disabled, disabled.name, disabled.password),
        (retired, retired.name, retired.password),
        (active, long_name, active.password),
    )
    observations: list[tuple[int, dict[int, int]]] = []
    for index, (identity, name, password) in enumerate(cases):
        source = f"case-{index}-{uuid4().hex}"
        _reset_observation(catalog, maintenance_dsn)
        assert _login(identity, name=name, password=password, source=source) is None
        assert _counter(catalog, f"src:{source}")[0][1] == 1
        observations.append(_observation(catalog, maintenance_dsn))
    assert all(crypt_calls == 1 for crypt_calls, _ in observations)
    assert len(observations[0][1]) > 1  # top-level だけの統計では通さない。
    assert all(statements == observations[0][1] for _, statements in observations)
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            """
            SELECT password_hash FROM public.tenant_credentials
            WHERE auth_subject_id = %s
            """,
            (active.subject_id,),
        )
        row = cursor.fetchone()
    catalog.observer.rollback()
    assert row is not None
    _assert_cost_twelve(row[0])
    body = _LOGIN_BODY.read_text(encoding="utf-8")
    dummy_match = re.search(r"'(?P<hash>\$2a\$12\$[./A-Za-z0-9]{53})'", body)
    assert dummy_match is not None
    dummy = dummy_match.group("hash")
    _assert_cost_twelve(dummy)
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SELECT authn_crypto.crypt(%s, %s)", (wrong, dummy))
        generated = cursor.fetchone()
    catalog.applicator.rollback()
    assert generated is not None
    _assert_cost_twelve(generated[0])
    with pytest.raises(AssertionError):
        _assert_cost_twelve(dummy.replace("$12$", "$10$", 1))


def test_crypt_omission_and_cost_mutations_are_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """照合省略は crypt 回数、コスト変更は実関数定義の検査で拒否する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    maintenance_dsn = _prepare_statements(catalog)
    wrong = secrets.token_urlsafe(24)
    _reset_observation(catalog, maintenance_dsn)
    assert _login(identity, name=f"missing{uuid4().hex[:12]}", password=wrong) is None
    baseline_crypt = _observation(catalog, maintenance_dsn)[0]
    assert baseline_crypt == 1
    body = _LOGIN_BODY.read_text(encoding="utf-8")
    comparison = (
        "password_matches := coalesce(\n"
        "        authn_crypto.crypt(coalesce(p_password, ''), hash_for_check)\n"
        "        = password_hash, false);"
    )
    assert body.count(comparison) == 1
    with _temporary_function_sql(
        catalog, body, body.replace(comparison, "password_matches := false;")
    ):
        _reset_observation(catalog, maintenance_dsn)
        assert (
            _login(identity, name=f"missing{uuid4().hex[:12]}", password=wrong) is None
        )
        assert _observation(catalog, maintenance_dsn)[0] != baseline_crypt
    assert body.count("$2a$12$") == 1
    with _temporary_function_sql(catalog, body, body.replace("$2a$12$", "$2a$10$", 1)):
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.pg_get_functiondef("
                "'authn.login_attempt(text, text, text)'::pg_catalog.regprocedure)"
            )
            definition = cursor.fetchone()
        catalog.observer.rollback()
        assert definition is not None
        cost_ten = re.search(r"\$2a\$10\$[./A-Za-z0-9]{53}", definition[0])
        assert cost_ten is not None
        with pytest.raises(AssertionError):
            _assert_cost_twelve(cost_ten.group(0))
        assert (
            _login(identity, name=f"missing{uuid4().hex[:12]}", password=wrong) is None
        )


def test_omitted_nested_lookup_changes_statement_fingerprint(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """関数内の設定照会を省く変異は queryid・回数の照合で red になる。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    maintenance_dsn = _prepare_statements(catalog)
    _reset_observation(catalog, maintenance_dsn)
    wrong = secrets.token_urlsafe(24)
    assert _login(identity, name=f"missing{uuid4().hex[:12]}", password=wrong) is None
    baseline = _observation(catalog, maintenance_dsn)[1]
    body = _LOGIN_BODY.read_text(encoding="utf-8")
    lookup = "token_ttl := authn.setting_positive_integer('auth.token_ttl_seconds');"
    assert body.count(lookup) == 1
    mutated = body.replace(lookup, "token_ttl := 1;")
    with _temporary_function_sql(catalog, body, mutated):
        _reset_observation(catalog, maintenance_dsn)
        assert (
            _login(identity, name=f"missing{uuid4().hex[:12]}", password=wrong) is None
        )
        assert _observation(catalog, maintenance_dsn)[1] != baseline


def _wait_for_lock(
    catalog: ProvisionedProductCatalog, pids: list[int], *, advisory: bool = False
) -> None:
    """待ち状態を pg_locks で観測し、時間ではなくロックで順序を確定する。"""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_catalog.count(DISTINCT pid)
                FROM pg_catalog.pg_locks
                WHERE pid = ANY(%s) AND NOT granted
                  AND (%s IS FALSE OR locktype = 'advisory')
                """,
                (pids, advisory),
            )
            row = cursor.fetchone()
        catalog.observer.rollback()
        if row == (len(pids),):
            return
        time.sleep(0.02)
    raise AssertionError("期待したロック待ちを観測できない")


def test_first_window_concurrent_failures_are_serialized_by_advisory_lock(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """空の窓の失敗連打を直列化し、その最中の正当な利用を遮らない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    _setting(catalog, "auth.team_login.window_seconds", 2_000_000_000)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    valid_token = _login(identity)
    assert isinstance(valid_token, UUID)
    wrong = secrets.token_urlsafe(24)
    release = Event()
    ready = Event()

    def leader() -> None:
        with (
            psycopg.connect(identity.app_dsn) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT token_id, wait_ms FROM authn.login_attempt(%s, %s, %s)",
                (identity.name, wrong, identity.tenant_id.hex),
            )
            assert cursor.fetchone() == (None, 0)
            ready.set()
            assert release.wait(15)

    def follower() -> int:
        with (
            psycopg.connect(identity.app_dsn) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT pg_catalog.pg_backend_pid()")
            row = cursor.fetchone()
            assert row is not None
            pid = int(row[0])
            pids.append(pid)
            cursor.execute(
                "SELECT token_id, wait_ms FROM authn.login_attempt(%s, %s, %s)",
                (identity.name, wrong, identity.tenant_id.hex),
            )
            result = cursor.fetchone()
            assert result is not None and result[0] is None
            assert isinstance(result[1], int)
            return pid

    pids: list[int] = []
    with ThreadPoolExecutor(max_workers=7) as pool:
        first = pool.submit(leader)
        assert ready.wait(15)
        followers = [pool.submit(follower) for _ in range(4)]
        deadline = time.monotonic() + 15
        while len(pids) < len(followers) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(pids) == len(followers)
        try:
            _wait_for_lock(catalog, pids, advisory=True)
            valid_login = pool.submit(_login, identity)
            valid_verify = pool.submit(_verify, identity, valid_token)
            assert isinstance(valid_login.result(timeout=15), UUID)
            assert valid_verify.result(timeout=15) == identity.tenant_id
        finally:
            release.set()
        first.result(timeout=15)
        assert all(isinstance(item.result(timeout=15), int) for item in followers)
    assert [row[1] for row in _counter(catalog, _scope(identity))] == [5]


def test_removing_advisory_lock_creates_duplicate_first_window_rows(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """ロック除去変異では未コミットの初行が見えず、同じ窓に 2 行できる。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    _setting(catalog, "auth.team_login.window_seconds", 2_000_000_000)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    wrong = secrets.token_urlsafe(24)
    body = _LOGIN_BODY.read_text(encoding="utf-8")
    changed, replacements = re.subn(
        r"    PERFORM pg_catalog\.pg_advisory_xact_lock\([\s\S]*?\n    \);\n",
        "",
        body,
        count=1,
    )
    assert replacements == 1
    release = Event()
    ready = Event()

    def first_failure() -> None:
        with (
            psycopg.connect(identity.app_dsn) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT token_id, wait_ms FROM authn.login_attempt(%s, %s, %s)",
                (identity.name, wrong, identity.tenant_id.hex),
            )
            assert cursor.fetchone() == (None, 0)
            ready.set()
            assert release.wait(15)

    with _temporary_function_sql(catalog, body, changed):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(first_failure)
            assert ready.wait(15)
            try:
                second = pool.submit(_login, identity, password=wrong)
                assert second.result(timeout=15) is None
            finally:
                release.set()
            first.result(timeout=15)
        rows = _counter(catalog, _scope(identity))
        assert len(rows) == 2
        assert len({row[0] for row in rows}) == 1
        assert sum(int(row[1]) for row in rows) == 2


@pytest.mark.parametrize(
    "mutator", ["change_password", "reset_password", "revoke_tenant_tokens", "logout"]
)
def test_revocation_wins_after_verify_waits_on_row_lock(
    provisioned_product_catalog: ProvisionedProductCatalog,
    mutator: str,
) -> None:
    """2 接続で先行失効を保持し、検証のロック待ち後に NULL を返す。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    token = _login(identity)
    assert isinstance(token, UUID)
    if mutator in {"change_password", "logout"}:
        mutator_dsn = identity.app_dsn
    else:
        mutator_dsn = catalog.cluster.admin_dsn
        mutator_dsn = make_conninfo(mutator_dsn, dbname="pitchlog_product")
    with psycopg.connect(mutator_dsn) as first:
        with first.cursor() as cursor:
            if mutator == "change_password":
                cursor.execute(
                    "SELECT authn.change_password(%s, %s, %s)",
                    (token, identity.password, secrets.token_urlsafe(24) + "A1"),
                )
                assert cursor.fetchone() == (True,)
            elif mutator == "reset_password":
                cursor.execute(
                    "SELECT authn.reset_password(%s, %s)",
                    (identity.tenant_id, secrets.token_urlsafe(24) + "A1"),
                )
            elif mutator == "revoke_tenant_tokens":
                cursor.execute(
                    "SELECT authn.revoke_tenant_tokens(%s)", (identity.tenant_id,)
                )
            else:
                cursor.execute("SELECT authn.logout(%s)", (token,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            ready = Event()
            pid_holder: list[int] = []

            def verify_worker() -> UUID | None:
                with (
                    psycopg.connect(identity.app_dsn) as second,
                    second.cursor() as cursor,
                ):
                    cursor.execute("SELECT pg_catalog.pg_backend_pid()")
                    row = cursor.fetchone()
                    assert row is not None
                    pid_holder.append(int(row[0]))
                    ready.set()
                    cursor.execute("SELECT authn.verify_token(%s)", (token,))
                    result = cursor.fetchone()
                    assert result is not None
                    return result[0]

            future = pool.submit(verify_worker)
            assert ready.wait(15)
            try:
                _wait_for_lock(catalog, pid_holder)
            finally:
                first.commit()
            assert future.result(timeout=15) is None
    assert _verify(identity, token) is None
