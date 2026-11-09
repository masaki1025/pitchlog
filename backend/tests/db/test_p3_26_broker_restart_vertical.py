"""P3訂正後の27球目を、initial grant broker再起動を挟んで同一候補で通す。"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from uuid import UUID, uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)
from .test_p3_paging_lifecycle_http import build_p3_26_script

pytestmark = pytest.mark.requires_db


def _children(container: str) -> list[str]:
    """supervisor直下のbroker子process PIDだけを返す。"""
    found = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "/runtime/bin/python3.12",
            "-c",
            (
                "import os;print(','.join(p for p in os.listdir('/proc') "
                "if p.isdigit() and p!='1' and "
                "open('/proc/'+p+'/stat').read().split()[3]=='1'))"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in found.stdout.strip().split(",") if p]


def _restart_after(container: str, delay: float, observed: dict[str, object]) -> None:
    """記録中にbroker子を停止し、supervisorの再起動を新しいPIDで確認する。"""
    time.sleep(delay)
    old = _children(container)
    observed["old_children"] = list(old)
    assert len(old) == 1, old
    subprocess.run(
        [
            "docker",
            "exec",
            container,
            "/runtime/bin/python3.12",
            "-c",
            f"import os,signal; os.kill({old[0]}, signal.SIGKILL)",
        ],
        check=True,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        current = _children(container)
        endpoint = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "test",
                "-f",
                "/run/pitchlog/initial-broker-endpoint.json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if (
            endpoint.returncode == 0
            and len(current) == 1
            and current[0] != old[0]
        ):
            observed["new_children"] = current
            return
        time.sleep(0.2)
    raise AssertionError("broker子の再起動を確認できない")


def test_p3_26_and_27_survive_initial_broker_restart(
    vertical_database, tmp_path
) -> None:
    """broker再起動でgate/epoch/既存grantを失わず27球目が成立する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for key, label in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "見逃し三振"),
            ("batting-result.foul", "ファウル"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, label),
            )
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "other_team_name": db.other_team_name,
        "other_tenant_id": str(db.other_tenant_id),
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
    }
    token = uuid4()
    observed: dict[str, object] = {}
    restart_error: list[BaseException] = []

    def restart() -> None:
        try:
            _restart_after(rg1_broker, 60.0, observed)
        except BaseException as error:  # 試験スレッドの失敗を本体へ渡す。
            restart_error.append(error)

    with (
        db.broker_worker(token, auto_restart=True) as rg1_broker,
        binding_broker(db, token),
    ):
        _prepare_app_configuration(db)
        worker = threading.Thread(target=restart, daemon=True)
        worker.start()
        process = subprocess.run(
            [
                "docker",
                *_app_arguments(db, case),
                "-u",
                "-c",
                build_p3_26_script(),
            ],
            capture_output=True,
            text=True,
            timeout=900,
        )
        worker.join(timeout=30)
    if restart_error:
        raise restart_error[0]
    (tmp_path / "broker-restart.json").write_text(json.dumps(observed, indent=2))
    assert process.returncode == 0, "owned HTTP脚本が非成功終了"
    result = json.loads(process.stdout)
    (tmp_path / "p3-26-broker-restart-result.json").write_text(
        json.dumps(result, indent=2)
    )
    assert "exception" not in result, result.get("runtime_diagnostics", {}).get(
        "stage"
    )
    assert result["prefix"] == "27"
    assert observed.get("old_children") and observed.get("new_children")
    game = UUID(result["game"])
    with psycopg.connect(db.authority.database.business_admin) as admin:
        params = (db.tenant_id, game)
        assert admin.execute(
            "SELECT state,recovery_generation FROM public.rg1_restore_gate "
            "WHERE singleton_id=1"
        ).fetchall() == [("open", 1)]
        assert admin.execute(
            "SELECT generation,kind,revoked_at,retired_at,recovery_generation "
            "FROM public.recording_generations "
            "WHERE tenant_id=%s AND game_id=%s",
            params,
        ).fetchall() == [(1, "normal", None, None, 1)]
        assert admin.execute(
            "SELECT count(*) FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s AND hidden_at IS NULL",
            params,
        ).fetchone() == (27,)
        assert admin.execute(
            "SELECT source_count,is_current FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s AND is_current",
            params,
        ).fetchall() == [(27, True)]
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.writer_bindings "
            "WHERE tenant_id=%s AND game_id=%s AND state='open'",
            params,
        ).fetchone() == (0,)
