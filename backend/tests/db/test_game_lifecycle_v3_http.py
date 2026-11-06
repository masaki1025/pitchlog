"""既存v3実HTTPの保存2球から終了再開を検証する。"""

import json
import subprocess
from uuid import uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_game_lifecycle_http import _SCRIPT as _LIFECYCLE_SCRIPT
from .test_terminal_pitch_storage import _lineup_script
from .test_terminal_pitch_storage import (
    admin_connection as admin_connection,
)
from .test_terminal_pitch_storage import (
    initial_scope_database as initial_scope_database,
)
from .test_terminal_pitch_storage import (
    product_node_binary as product_node_binary,
)
from .test_terminal_pitch_storage import (
    tested_role_connection as tested_role_connection,
)
from .test_terminal_pitch_storage import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db


def _v3_script():
    """既存v3作成実経路と終了再開実経路を同workerで接続する。"""
    script = _lineup_script()
    old = '''        results = [
            "batting-result.called-pitch",
            "batting-result.called-pitch",
            "batting-result.called-strikeout",
        ] * 3 + ["batting-result.ball"]'''
    new = '''        results = [
            "batting-result.called-pitch",
            "batting-result.called-pitch",
        ]'''
    assert script.count(old) == 1
    script = script.replace(old, new, 1)
    assert script.count("if index in (1, 9):") == 1
    script = script.replace("if index in (1, 9):", "if index in ():", 1)
    start = _LIFECYCLE_SCRIPT.index("        import copy")
    end = _LIFECYCLE_SCRIPT.index("        current, _ = await read_full()", start)
    functions = _LIFECYCLE_SCRIPT[start:end]
    marker = "        return {\n            \"game\": game,"
    assert script.count(marker) == 1
    flow = '''        current_lifecycle, _ = await read_full()
        assert current_lifecycle["lifecycle"]["lastVersion"] == "0"
        ended, _ = await lifecycle("end", current_lifecycle)
        assert ended["status"] == "finished"
        reopened, _ = await lifecycle("reopen", ended)
        assert reopened["status"] == "in_progress"
        added = await additional_play()
        assert added["status"] == "in_progress"
        final, _ = await lifecycle("end", added)
        assert final["status"] == "finished"
        assert final["lifecycle"]["lastVersion"] == "2"
'''
    return script.replace(marker, functions + flow + marker, 1)


def test_actual_v3_two_ball_end_reopen_append_reend(vertical_database):
    """隔離PG上のv3同一版を実HTTPで終了・再開・追記・再終了する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for key, name in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.ball", "ボール"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, name),
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
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _v3_script()],
            capture_output=True,
            text=True,
            timeout=400,
        )
    assert process.returncode == 0, "v3 worker異常終了"
    result = json.loads(process.stdout)
    assert "exception" not in result, result.get("runtime_diagnostics", {})
    assert result["prefix"] == "2" and result["history"] == 2
