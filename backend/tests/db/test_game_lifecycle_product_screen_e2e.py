"""同じ製品候補の実画面で作成・終了・再開・追加球・再終了を確認する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

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
    reason="隔離HTTPS証明書PATH未供給。画面縦断は未実証",
)
def test_screen_create_end_reopen_append_reend_reload(vertical_database):
    """事前game投入を実証にせず、UI作成gameの真正終了版とfactを照合する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
    assert teams is not None
    token = uuid4()
    config = "GameScreenLifecycleProduct.playwright.config.ts"
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, config, "lifecycle-product", https=True
        ) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "lifecycle-product",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
    lines = re.findall(r"PITCHLOG_LIFECYCLE_FINAL=(\{[^\n]+\})", result.stdout)
    assert len(lines) == 1
    observed = json.loads(lines[0])
    game = UUID(observed["gameId"])
    assert game != db.game_id and observed["requests"] == 6
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        final = admin.execute(
            "SELECT g.status,h.last_version,h.is_finished,v.completion_state,"
            "v.is_current,v.source_count FROM public.games g "
            "JOIN sync_fence.game_lifecycle_heads h "
            "ON h.tenant_id=g.tenant_id AND h.game_id=g.id "
            "JOIN sync_fence.stats_fact_versions v ON v.tenant_id=h.tenant_id "
            "AND v.game_id=h.game_id AND v.id=h.active_stats_version_id "
            "WHERE g.tenant_id=%s AND g.id=%s",
            (db.tenant_id, game),
        ).fetchall()
        events = admin.execute(
            "SELECT event_kind,ledger_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            (db.tenant_id, game),
        ).fetchall()
    assert final == [("finished", 2, True, "confirmed_ended", True, 3)]
    assert events == [
        (kind, "accepted")
        for kind in (
            "play_input",
            "game_end_declaration",
            "game_reopen",
            "play_input",
            "play_input",
            "game_end_declaration",
        )
    ]

    # 画面の機能完走と保存原本照合を、最後の性能判定失敗でも観測する。
    print(
        "PITCHLOG_LIFECYCLE_DB_FINAL="
        + json.dumps(
            {
                "status": final[0][0],
                "version": final[0][1],
                "completionState": final[0][3],
                "sourceCount": final[0][5],
                "acceptedEventCount": len(events),
                "syncDurationsMs": observed["syncDurationsMs"],
            }
        )
    )
    assert result.returncode == 0, (
        result.stdout[-12000:],
        result.stderr[-2000:],
    )
