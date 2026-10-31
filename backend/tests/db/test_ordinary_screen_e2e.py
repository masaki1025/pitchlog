"""同一owned環境の実HTTPS画面で通常3球・原要求再送・reloadを実測する。

TLSは供給されたPATHをViteへ渡すだけで、生成・内容読取・秘密のログ出力はしない。
未供給skipとcollect成功は画面縦断の実証に数えない。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from manual_e2e_hold_support import hold_manual_environment, manual_hold_seconds

from .ordinary_screen_e2e_support import write_browser_assets
from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import (
    _PASSWORD,
    ROOT,
    _browser_environment,
)
from .test_screen_start_e2e import (
    admin_connection as admin_connection,
)
from .test_screen_start_e2e import (
    initial_scope_database as _initial_scope_database,
)
from .test_screen_start_e2e import (
    product_node_binary as product_node_binary,
)
from .test_screen_start_e2e import (
    tested_role_connection as tested_role_connection,
)
from .test_screen_start_e2e import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db


def _source_snapshot() -> dict[str, str]:
    """秘密を含まない製品sourceの対象集合を固定し、実行後の同一性を調べる。"""
    suffixes = {".py", ".ts", ".vue", ".js", ".json", ".sql"}
    files = []
    for relative in (
        "backend/src",
        "backend/migrations",
        "contracts",
        "frontend/src",
        "frontend/public/domain",
    ):
        directory = ROOT / relative
        if directory.exists():
            files.extend(
                path
                for path in directory.rglob("*")
                if path.is_file() and not path.is_symlink() and path.suffix in suffixes
            )
    files.extend(
        (Path(__file__), Path(__file__).with_name("ordinary_screen_e2e_support.py"))
    )
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    }


@pytest.fixture
def initial_scope_database(monkeypatch: pytest.MonkeyPatch):
    """autouseの識別確認より先に共有DSNを拒否し、owned環境だけを供給する。"""
    assert not os.environ.get("PITCHLOG_TEST_ADMIN_DSN"), (
        "共有admin DSNをunsetする必要がある"
    )
    assert not os.environ.get("PITCHLOG_TEST_ROLE_DSN"), (
        "共有role DSNをunsetする必要がある"
    )
    yield from cast(Any, _initial_scope_database).__wrapped__(monkeypatch)


@pytest.fixture
def owned_ordinary_database(vertical_database):
    """共有DSN拒否済みのowned環境を返す。"""
    return vertical_database


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS証明書/鍵PATH未供給のため通常3球HTTPS画面縦断は未実証",
)
@pytest.mark.parametrize("scenario", ["ordinary", "walk", "hit-by-pitch"])
def test_screen_three_ordinary_pitches_https_save_replay_reload(
    owned_ordinary_database,
    tmp_path: Path,
    scenario: str,
) -> None:
    """画面で新規保存した3件だけを、実prefixとnative4表に照合する。"""
    import psycopg
    from psycopg import sql

    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file(), (
            "明示された既存TLS証明書/鍵の絶対PATHが両方必要"
        )
    browser_tmp = os.environ.get("PITCHLOG_E2E_BROWSER_TMPDIR")
    browser_env = {}
    if browser_tmp:
        browser_path = Path(browser_tmp)
        assert browser_path.is_absolute() and browser_path.is_dir(), (
            "browser専用TMPDIRは明示した既存絶対ディレクトリが必要"
        )
        browser_env["TMPDIR"] = browser_tmp
    db = owned_ordinary_database
    frontend = ROOT / "frontend"
    config = write_browser_assets(
        tmp_path / "ordinary-browser",
        frontend,
        terminal=None if scenario == "ordinary" else scenario,
    )
    results = (
        ["batting-result.ball", "batting-result.called-pitch", "batting-result.ball"]
        if scenario == "ordinary"
        else (["batting-result.ball"] * 3 if scenario == "walk" else [])
        + [f"batting-result.{scenario}", "batting-result.ball"]
    )
    expected_count = len(results)
    snapshot = _source_snapshot()
    head = subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    evidence = tmp_path / "ordinary-screen-source-before.json"
    evidence.write_text(json.dumps({"head": head, "sha256": snapshot}, indent=2) + "\n")
    # これは試合結果ではなく、結果選択肢の既規範語彙のfixture準備だけである。
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        if scenario != "ordinary":
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (
                    f"batting-result.{scenario}",
                    "四球" if scenario == "walk" else "死球",
                ),
            )
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            str(config),
            f"ordinary-{token}",
            https=True,
        ) as origin:
            result = subprocess.run(  # noqa: S603
                ["pnpm", "exec", "playwright", "test", "--config", str(config)],
                cwd=frontend,
                env={
                    **os.environ,
                    **browser_env,
                    "PITCHLOG_E2E_BASE_URL": origin,
                    "PITCHLOG_E2E_TEAM_NAME": db.team_name,
                    "PITCHLOG_E2E_PASSWORD": _PASSWORD,
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
                capture_output=True,
                text=True,
                timeout=600,
            )
            # request原値/資格/traceは出さない。specの公開markerと通常成否だけ保存する。
            (tmp_path / "ordinary-screen-playwright.log").write_text(
                result.stdout + result.stderr,
                encoding="utf-8",
            )
            assert result.returncode == 0, "通常3球の実画面試験に失敗（専用logを確認）"
            match = re.search(
                r"PITCHLOG_ORDINARY_GAME_ID=([0-9a-f-]{36})", result.stdout
            )
            assert match is not None, "画面新規作成した試合の非秘密markerがない"
            game_id = match.group(1)
            assert game_id != str(db.game_id), "fixture試合を新規作成の証拠に数えない"
            with psycopg.connect(db.authority.database.business_admin) as admin:
                for table in ("play_rows", "operation_events", "event_slots"):
                    count = admin.execute(
                        sql.SQL(
                            "SELECT count(*) FROM public.{} "
                            "WHERE tenant_id=%s AND game_id=%s"
                        ).format(sql.Identifier(table)),
                        (db.tenant_id, game_id),
                    ).fetchone()
                    assert count == (expected_count,), table
                assert admin.execute(
                    "SELECT count(*) FROM public.idempotency_ledger AS ledger "
                    "JOIN public.operation_events AS op "
                    "ON ledger.tenant_id=op.tenant_id AND ledger.d5=op.d5 "
                    "WHERE op.tenant_id=%s AND op.game_id=%s "
                    "AND ledger.kind='accepted'",
                    (db.tenant_id, game_id),
                ).fetchone() == (expected_count,)
                assert admin.execute(
                    "SELECT d1,d2 FROM public.operation_events "
                    "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
                    (db.tenant_id, game_id),
                ).fetchall() == [
                    (n, 1 + (n - 1) * 1000) for n in range(1, expected_count + 1)
                ]
                assert admin.execute(
                    "SELECT batting_result_key FROM public.play_rows "
                    "WHERE tenant_id=%s AND game_id=%s ORDER BY play_number",
                    (db.tenant_id, game_id),
                ).fetchall() == [(result,) for result in results]
                if scenario != "ordinary":
                    rows = admin.execute(
                        "SELECT r.base,r.runner_id,r.responsible_pitcher_id,"
                        "p.batter_id,"
                        "p.pitcher_id FROM public.play_runners r "
                        "JOIN public.play_rows p "
                        "ON r.tenant_id=p.tenant_id AND r.play_id=p.id "
                        "WHERE p.tenant_id=%s AND p.game_id=%s ORDER BY p.play_number",
                        (db.tenant_id, game_id),
                    ).fetchall()
                    assert len(rows) == 1
                    terminal = admin.execute(
                        "SELECT batter_id,pitcher_id FROM public.play_rows "
                        "WHERE tenant_id=%s AND game_id=%s AND batting_result_key=%s",
                        (db.tenant_id, game_id, f"batting-result.{scenario}"),
                    ).fetchone()
                    assert terminal is not None
                    assert rows[0][:3] == (1, *terminal)
                    assert rows[0][3] != terminal[0]
                    assert rows[0][4] == terminal[1]
            hold_manual_environment(origin, manual_hold_seconds(), db.team_name)
    assert _source_snapshot() == snapshot, (
        "実行中に製品sourceが変わったため同一候補実証にできない"
    )
