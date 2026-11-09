"""P3故障取消がRG1 controller/gateを停止させないことを実DBで切り分ける。"""

from __future__ import annotations

import json
import subprocess
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
from .test_p3_candidate_compile_author import _three_ball_p3_script

pytestmark = pytest.mark.requires_db


def _probe_script() -> str:
    """既3球P3脚本の故障取消直後とP3受理直後にRG1生存照会を挿す。"""
    script = _three_ball_p3_script()
    rollback = (
        '            assert rolled.status_code == 200 and rolled.json() == current, (\n'
        '                "p3-fault-rollback", crash, rolled.status_code)\n'
    )
    assert script.count(rollback) == 1
    script = script.replace(
        rollback,
        rollback
        + """            probe_payload = json.loads(json.dumps(p3_payload))
            probe_payload["change"]["d5"] = str(uuid4())
            gate_probe = await client.post(
                "/games/" + game + "/sync/attempts/recover",
                headers=device_headers(pair, str(uuid4())),
                json=probe_payload)
            runtime_diagnostics.setdefault("gate_probes", []).append(
                ["fault-" + crash, gate_probe.status_code])
""",
        1,
    )
    # 故障ごとに新D5を発行し、旧要求の再掲として故障点を飛ばさない。
    loop = '        for crash in ("after_t2_event", "after_t4_projection"):\n'
    assert script.count(loop) == 1
    script = script.replace(
        loop,
        "        def fresh_p3(payload):\n"
        "            value = json.loads(json.dumps(payload))\n"
        "            value[\"change\"][\"d5\"] = str(uuid4())\n"
        "            return value\n"
        + loop,
        1,
    )
    fault_post = (
        "                    failed = await client.post(\n"
        '                        "/games/" + game + "/sync/change",\n'
        "                        headers=device_headers(pair, str(uuid4())),\n"
        "                        json=p3_payload)\n"
    )
    assert script.count(fault_post) == 1
    script = script.replace(
        fault_post,
        fault_post.replace("json=p3_payload)", "json=fresh_p3(p3_payload))"),
        1,
    )
    marker = '        runtime_diagnostics.update(stage="p3-get", status=None)\n'
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        """        probe_payload = json.loads(json.dumps(p3_payload))
        probe_payload["change"]["d5"] = str(uuid4())
        gate_probe = await client.post(
            "/games/" + game + "/sync/attempts/recover",
            headers=device_headers(pair, str(uuid4())),
            json=probe_payload)
        runtime_diagnostics.setdefault("gate_probes", []).append(
            ["after-p3", gate_probe.status_code])
"""
        + marker,
        1,
    )
    compile(script, "<p3-fault-probe>", "exec")
    return script


def test_p3_fault_rollback_keeps_rg1_controller_alive(vertical_database, tmp_path):
    """故障取消とP3受理の各直後に、実RG1 gateが開いたままである。"""
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
    script = _probe_script()
    with (
        db.broker_worker(token),
        binding_broker(db, token),
    ):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", script],
            capture_output=True,
            text=True,
            timeout=600,
        )
        observed = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}} {{.State.ExitCode}}",
                db.controller,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        (tmp_path / "controller-state.txt").write_text(
            (observed.stdout or "") + (observed.stderr or "")
        )
        logs = subprocess.run(
            ["docker", "logs", "--tail", "40", db.controller],
            capture_output=True,
            text=True,
            check=False,
        )
        (tmp_path / "controller-log.txt").write_text(
            (logs.stdout or "") + (logs.stderr or "")
        )
        if process.returncode:
            (tmp_path / "app-stdout.txt").write_text(process.stdout[-4000:])
            (tmp_path / "app-stderr.txt").write_text(process.stderr[-4000:])
    assert process.returncode == 0, "owned HTTP脚本が非成功終了"
    result = json.loads(process.stdout)
    (tmp_path / "p3-fault-probe.json").write_text(json.dumps(result, indent=2))
    assert "exception" not in result, result.get("runtime_diagnostics", {}).get(
        "stage"
    )
    probes = result["runtime_diagnostics"].get("gate_probes")
    assert probes == [
        ["fault-after_t2_event", 200],
        ["fault-after_t4_projection", 200],
        ["after-p3", 200],
    ], result["runtime_diagnostics"].get("cause_frames")
    with psycopg.connect(db.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT state,recovery_generation FROM public.rg1_restore_gate "
            "WHERE singleton_id=1"
        ).fetchall() == [("open", 1)]
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.writer_bindings "
            "WHERE tenant_id=%s AND state='open'",
            (db.tenant_id,),
        ).fetchone() == (0,)
    assert UUID(result["game"]).int != 0
