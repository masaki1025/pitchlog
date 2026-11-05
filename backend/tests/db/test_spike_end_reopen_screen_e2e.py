"""実画面の終了→再開→再終了→reloadをowned PGと実HTTPSで観測する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import apply_product_authz_ddl

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import (
    _browser_environment,
    _run_playwright,
)
from .test_screen_start_e2e import (
    admin_connection as admin_connection,
)
from .test_screen_start_e2e import (
    initial_scope_database as initial_scope_database,
)
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db

ROOT = Path(__file__).resolve().parents[3]


def _partial_output(value: str | bytes | None) -> bytes:
    """TimeoutExpiredのtext指定時にも返るbytesをそのまま保持する。"""
    return value.encode("utf-8") if isinstance(value, str) else value or b""


def _run_lifecycle_playwright(db, origin: str, extra_env: dict[str, str]):
    """失敗時も実測logを残し、元の失敗を再送出する。"""
    try:
        return _run_playwright(
            db,
            "GameScreenEndReopen.playwright.config.ts",
            origin,
            "game-lifecycle",
            extra_env,
            900,
        )
    except Exception as error:
        logs = Path("/tmp/opencode/pitchlog-screen-e2e")
        try:
            logs.mkdir(parents=True, exist_ok=True)
            if hasattr(error, "stdout"):
                (logs / "game-lifecycle-playwright.log").write_bytes(
                    _partial_output(getattr(error, "stdout", None))
                    + b"\n"
                    + _partial_output(getattr(error, "stderr", None))
                )
        finally:
            raise


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS証明書/鍵PATH未供給のため終了再開の画面縦断は未実証",
)
def test_screen_end_reopen_reend_reload(
    vertical_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """対象試合は画面だけで作成・開始し、実APIと実DBで終了版を照合する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file()
    monkeypatch.setenv("PITCHLOG_SPIKE_END_REOPEN", "1")
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        apply_product_authz_ddl(admin)
        identity = admin.execute(
            "SELECT oid FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert identity is not None
        report = inspect_product_authz_catalog(
            admin, privileged_role_oids=frozenset({identity[0]})
        )
        assert report.ok, [v.check_id for v in report.violations]
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.home-run','batting_result','本塁打') "
            "ON CONFLICT(key) DO NOTHING"
        )
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            "GameScreenEndReopen.playwright.config.ts",
            "game-lifecycle",
            https=True,
        ) as origin:
            completed = _run_lifecycle_playwright(
                db,
                origin,
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                    "PITCHLOG_E2E_OTHER_TEAM": db.other_team_name,
                    "PITCHLOG_E2E_OTHER_TENANT": str(db.other_tenant_id),
                },
            )
            assert completed.returncode == 0, (
                completed.stdout[-12000:],
                completed.stderr[-4000:],
            )
            observed = [
                json.loads(value)
                for value in re.findall(
                    r"PITCHLOG_LIFECYCLE_SCREEN_RESULT=(\{[^\n]+\})",
                    completed.stdout,
                )
            ]
            assert len(observed) == 1
            result = observed[0]
            game = result["game"]
            assert str(db.game_id) != game
            assert result["score"] == {"home": "0", "away": "1"}
            assert result["end"]["a5"] == "受理"
            assert result["fault"]["status"] in (500, 503)
            assert result["fault"]["watermarkAfter"] == "1"
            assert result["duplicate"] == {"status": 200, "a5": "重複"}
            assert result["reopen"]["a5"] == "受理"
            assert result["reend"]["a5"] == "受理"
            assert result["finalVersion"] == "v2"
            assert result["finalWatermark"] == "4"
            assert result["finalizations"] == [
                {"version": 1, "d1": 2, "invalidatedBy": {"d1": 3}},
                {"version": 2, "d1": 4, "invalidatedBy": None},
            ]
            assert result["reloaded"] == {
                "status": "finished",
                "version": "v2",
                "watermark": "4",
            }
            assert result["badV12"]["status"] == 200
            assert result["badV12"]["a5"] == "退避"
            assert result["badV12"]["watermarkAfter"] == "4"
            assert result["otherTenantStatus"] == 404
            assert result["otherTenantFaultStatus"] == 404
            with psycopg.connect(db.authority.database.business_admin) as admin:
                rows = admin.execute(
                    "SELECT d1,d2,event_kind,payload->>'formatVersion',"
                    "payload->>'action' FROM public.operation_events "
                    "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
                    (db.tenant_id, UUID(game)),
                ).fetchall()
                assert rows == [
                    (1, 1, "play_input", "play-prefix-play-v3", None),
                    (2, 1001, "game_end_declaration", "game-lifecycle-spike-v1", "end"),
                    (
                        3,
                        2001,
                        "game_end_declaration",
                        "game-lifecycle-spike-v1",
                        "reopen",
                    ),
                    (4, 3001, "game_end_declaration", "game-lifecycle-spike-v1", "end"),
                ]
                for table, expected in (
                    ("play_rows", 1),
                    ("idempotency_ledger", 4),
                    ("invalidation_intents", 20),
                ):
                    if table == "idempotency_ledger":
                        count = admin.execute(
                            "SELECT count(*) FROM public.idempotency_ledger l "
                            "JOIN public.operation_events e "
                            "ON e.tenant_id=l.tenant_id AND e.d5=l.d5 "
                            "WHERE e.tenant_id=%s AND e.game_id=%s",
                            (db.tenant_id, UUID(game)),
                        ).fetchone()
                    elif table == "invalidation_intents":
                        count = admin.execute(
                            "SELECT count(*) FROM public.invalidation_intents i "
                            "JOIN public.operation_events e "
                            "ON e.tenant_id=i.tenant_id "
                            "AND starts_with(i.intent_id, "
                    "'sync:' || e.d5::text || ':') "
                            "WHERE e.tenant_id=%s AND e.game_id=%s",
                            (db.tenant_id, UUID(game)),
                        ).fetchone()
                    else:
                        count = admin.execute(
                            sql.SQL(
                                "SELECT count(*) FROM public.{} "
                                "WHERE tenant_id=%s AND game_id=%s"
                            ).format(sql.Identifier(table)),
                            (db.tenant_id, UUID(game)),
                        ).fetchone()
                    assert count == (expected,), (table, count)
                bad_d5 = UUID(result["badV12"]["d5"])
                assert admin.execute(
                    "SELECT kind FROM public.idempotency_ledger "
                    "WHERE tenant_id=%s AND d5=%s",
                    (db.tenant_id, bad_d5),
                ).fetchone() == ("evacuated",)
                assert admin.execute(
                    "SELECT count(*) FROM public.operation_events "
                    "WHERE tenant_id=%s AND d5=%s",
                    (db.tenant_id, bad_d5),
                ).fetchone() == (0,)
                # 本spikeはgames.statusを更新しない。製品投影の残件を明示する。
                status = admin.execute(
                    "SELECT status FROM public.games WHERE tenant_id=%s AND id=%s",
                    (db.tenant_id, UUID(game)),
                ).fetchone()
                assert status == ("in_progress",)
