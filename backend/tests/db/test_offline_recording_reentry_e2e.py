"""production SWで断中cold再起動→未送信2球→実認証後の順序同期を確認する。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示loopback TLS証明書/鍵PATH未供給。実SW断中再起動は未実証",
)
def test_offline_recording_cold_reentry_and_ordered_sync(vertical_database) -> None:
    """Fixture gameを流用せずUI作成gameの2球だけを実GET/DBに照合する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file(), "loopback TLS資材が不正"
    db = vertical_database
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
    assert teams is not None
    token = uuid4()
    config = "GameScreenOfflineRecording.playwright.config.ts"
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            config,
            f"offline-recording-{token}",
            https=True,
            production=True,
        ) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                f"offline-recording-{token}",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
    assert result.returncode == 0, (
        result.stdout[-12000:],
        result.stderr[-3000:],
    )
    match = re.search(
        r"PITCHLOG_OFFLINE_RECORDING_GAME_ID=([0-9a-f-]{36})", result.stdout
    )
    assert match is not None, "実画面新規作成gameの非秘密markerがない"
    created = match.group(1)
    assert created != str(db.game_id), "fixture gameを新規作成に数えない"
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        for table in ("play_rows", "operation_events", "event_slots"):
            count = admin.execute(
                sql.SQL(
                    "SELECT count(*) FROM public.{} WHERE tenant_id=%s AND game_id=%s"
                ).format(sql.Identifier(table)),
                (db.tenant_id, created),
            ).fetchone()
            assert count == (2,), table
        accepted = admin.execute(
            "SELECT count(*) FROM public.idempotency_ledger AS ledger "
            "JOIN public.operation_events AS op "
            "ON ledger.tenant_id=op.tenant_id AND ledger.d5=op.d5 "
            "WHERE op.tenant_id=%s AND op.game_id=%s "
            "AND ledger.kind='accepted'",
            (db.tenant_id, created),
        ).fetchone()
        assert accepted == (2,)
        positions = admin.execute(
            "SELECT d1,d2 FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            (db.tenant_id, created),
        ).fetchall()
        assert positions == [(1, 1), (2, 1001)]
        results = admin.execute(
            "SELECT batting_result_key FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY play_number",
            (db.tenant_id, created),
        ).fetchall()
        assert results == [("batting-result.ball",), ("batting-result.ball",)]
