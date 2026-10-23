"""実freshとRG1 controllerの接合を検査する。正式提供/HTTP成功ではない。"""

from __future__ import annotations

from collections.abc import Iterator
from time import monotonic, sleep

import psycopg
import pytest
from db_fixtures import _dsn_names

from .durable_rights_ledger_support import (
    AuthorityDatabase,
    isolated_authority_database,
)
from .rg1_fresh_controller_support import FreshControllerDatabase

pytestmark = pytest.mark.requires_db


@pytest.fixture
def authority_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[AuthorityDatabase]:
    """外部DSNを消してから所有3PG/実peer/witnessだけを構築する。"""
    admin_name, role_name = _dsn_names()
    monkeypatch.delenv(admin_name, raising=False)
    monkeypatch.delenv(role_name, raising=False)
    with isolated_authority_database() as authority:
        monkeypatch.setenv(admin_name, authority.database.primary_admin)
        monkeypatch.setenv(role_name, authority.database.endpoints.primary_dsn)
        yield authority


@pytest.fixture
def admin_connection(
    authority_database: AuthorityDatabase,
) -> Iterator[psycopg.Connection]:
    """共通identity autouseへ所有primaryの実admin接続を渡す。"""
    with psycopg.connect(authority_database.database.primary_admin) as connection:
        yield connection


@pytest.fixture
def tested_role_connection(
    authority_database: AuthorityDatabase,
) -> Iterator[psycopg.Connection]:
    """共通identity autouseへ所有primaryの実制限app接続を渡す。"""
    with psycopg.connect(
        authority_database.database.endpoints.primary_dsn
    ) as connection:
        yield connection


def test_actual_fresh_controller_borrow_heartbeat_release_and_disconnect(
    authority_database: AuthorityDatabase,
) -> None:
    """実fresh一回から借用を保持/解放し、未終端切断でclosedへ戻す。"""
    controller = FreshControllerDatabase(authority_database)
    try:
        controller.prepare()
        closed = controller.application("""
from uuid import uuid4
import psycopg
with psycopg.connect(host='/business-socket',dbname='ledger_fixture',
                     user='pitchlog_app',passfile='/dev/null',connect_timeout=3) as pg:
    tenant=uuid4()
    pg.execute("SELECT pg_catalog.set_config('app.tenant_id',%s,true)",(str(tenant),))
    assert pg.execute('SELECT rg1_api.rg1_read_open(%s)',(tenant,)).fetchone()==(False,)
    commit_read=pg.execute(
        'SELECT rg1_api.rg1_assert_open_before_commit(%s)',(tenant,)
    ).fetchone()
    assert commit_read==(False,)
    pg.rollback()
print('CLOSED_BEFORE_FRESH')
""")
        assert closed == "CLOSED_BEFORE_FRESH"
        controller.start()
        output = controller.application("""
import os,time
from pathlib import Path
from uuid import uuid4
import psycopg
from pitchlog.recording_rights.rg1_lifecycle import (
    BusinessBinding,configure_runtime,borrow_gate,
)
assert os.geteuid()==20003
configure_runtime(Path('/control/rg1/client.json'))
with psycopg.connect(host='/business-socket',dbname='ledger_fixture',
                     user='pitchlog_app',passfile='/dev/null',connect_timeout=3) as pg:
    assert pg.execute('SELECT session_user,current_user').fetchone()==(
        'pitchlog_app','pitchlog_app')
    tenant=uuid4()
    pg.execute("SELECT pg_catalog.set_config('app.tenant_id',%s,true)",(str(tenant),))
    assert pg.execute('SELECT rg1_api.rg1_read_open(%s)',(tenant,)).fetchone()==(True,)
    commit_read=pg.execute(
        'SELECT rg1_api.rg1_assert_open_before_commit(%s)',(tenant,)
    ).fetchone()
    assert commit_read==(True,)
    body=pg.execute('SELECT rg1_control.scope_binding(%s)',(tenant,)).fetchone()
    assert body is not None and type(body[0]) is str
    binding=BusinessBinding.from_text(body[0])
    assert binding.backend_pid==pg.execute('SELECT pg_backend_pid()').fetchone()[0]
    loan=borrow_gate(binding)
    assert loan.binding==binding
    loan.assert_held()
    print('BORROWED',flush=True)
    started=time.monotonic()
    time.sleep(3.2)
    assert time.monotonic()-started>3
    loan.assert_held()
    print('HELD_AFTER_IDLE',flush=True)
    pg.rollback()
    loan.release()
    print('RELEASED',flush=True)
    # 正常解放後も同じ実activationを借用でき、切断を正常releaseへ補完しない。
    loan=borrow_gate(binding)
    loan.assert_held()
    loan.abandon()
    print('ABANDONED',flush=True)
""")
        assert output.splitlines() == [
            "BORROWED",
            "HELD_AFTER_IDLE",
            "RELEASED",
            "ABANDONED",
        ]
        deadline = monotonic() + 10
        while controller.running():
            if monotonic() >= deadline:
                raise AssertionError("実client切断後controller停止の期限超過")
            sleep(0.05)
        with psycopg.connect(authority_database.database.business_admin) as connection:
            assert connection.execute(
                "SELECT singleton_id,state FROM public.rg1_restore_gate"
            ).fetchall() == [(1, "closed")]
            assert connection.execute(
                "SELECT count(*) FROM pg_catalog.pg_locks WHERE locktype='advisory' "
                "AND database=(SELECT oid FROM pg_catalog.pg_database "
                "WHERE datname=current_database()) AND classid=1380397379::oid "
                "AND objid IN (1::oid,2::oid) AND objsubid=2 AND granted"
            ).fetchone() == (0,)
        assert authority_database.event_counts().get("activation_open") == 1
        assert authority_database.event_counts().get("lease_close", 0) == 0
        assert (
            authority_database.client("""
try: s.current_recovery_generation()
except LedgerUnavailable: print('UNTERMINATED_CLOSED')
else: raise AssertionError('unterminated activation treated as normal')
""")
            == "UNTERMINATED_CLOSED"
        )
    finally:
        controller.close()
