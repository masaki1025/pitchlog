"""RG1 brokerのfail-closed停止後に同じsocketへ再起動できることを確認する。"""

from __future__ import annotations

import subprocess
import time
from uuid import uuid4

import pytest

from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary

pytestmark = pytest.mark.requires_db


def test_rg1_broker_supervisor_restarts_endpoint(vertical_database):
    """停止したbroker子processの後に同一endpointが再出現する。"""
    db = vertical_database
    token = uuid4()
    with db.broker_worker(token, auto_restart=True) as name:
        def endpoint():
            return subprocess.run(
                ["docker", "exec", name, "test", "-f",
                 "/run/pitchlog/initial-broker-endpoint.json"],
                capture_output=True,
                text=True,
                check=False,
            ).returncode == 0

        def children() -> list[str]:
            found = subprocess.run(
                [
                    "docker", "exec", name, "/runtime/bin/python3.12", "-c",
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

        assert endpoint()
        old_children = children()
        assert len(old_children) == 1, old_children
        subprocess.run(
            [
                "docker", "exec", name, "/runtime/bin/python3.12", "-c",
                f"import os,signal; os.kill({old_children[0]}, signal.SIGKILL)",
            ],
            check=True,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = children()
            if endpoint() and len(current) == 1 and current[0] != old_children[0]:
                return
            time.sleep(0.2)
        raise AssertionError("broker endpoint did not return")
