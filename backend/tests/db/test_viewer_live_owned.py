"""新規開始・二球・終了の保存値を別Cookie閲覧contextから非ロックで読む。"""

import json
import subprocess
from pathlib import Path
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
from .test_game_lifecycle_v3_http import _v3_script
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


def _host_source_paths():
    """editable環境の旧WT混入を実行前に拒否する。"""
    from pitchlog.authz import product_provisioning
    from pitchlog.domainrt import lineup_play_prefix_continuation
    from pitchlog.repositories import function_operations

    root = (Path(__file__).resolve().parents[2] / "src").resolve()
    paths = {
        "product_provisioning": product_provisioning.__file__,
        "lineup_play_prefix_continuation": lineup_play_prefix_continuation.__file__,
        "function_operations": function_operations.__file__,
    }
    assert all(Path(path).resolve().is_relative_to(root) for path in paths.values())
    return paths


_HOST_SOURCE_PATHS = _host_source_paths()


def _insert_after(source: str, anchor: str, inserted: str) -> str:
    """既縦断sourceの一意な位置へ閲覧対向を挿入する。"""
    assert source.count(anchor) == 1
    return source.replace(anchor, anchor + inserted, 1)


def _script():
    """既製品縦断へ別Cookieの同チーム閲覧照合だけを挿入する。"""
    source = _v3_script()
    before = """    ) as client:
        logged = await login(client, team)"""
    after = """    ) as client, AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as viewer, AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as anonymous:
        from time import perf_counter
        viewer_checks = []
        logged_viewer = await login(viewer, team)
        assert logged_viewer.status_code == 200, (
            "viewer-login", logged_viewer.status_code)
        anonymous_head = await anonymous.get(
            "/games/" + game + "/viewer-head")
        assert anonymous_head.status_code == 401, (
            "anonymous-viewer-head", anonymous_head.status_code)
        unavailable_head = await viewer.get(
            "/games/" + case["unavailable_game"] + "/viewer-head",
            headers=headers())
        assert unavailable_head.status_code == 503, (
            "unavailable-viewer-head", unavailable_head.status_code)
        unavailable_body = await viewer.get(
            "/games/" + case["unavailable_game"] + "/viewer",
            headers=headers())
        assert unavailable_body.status_code == 503, (
            "unavailable-viewer-body", unavailable_body.status_code)

        async def verify_viewer(expected, after, status):
            started = perf_counter()
            seen = await viewer.get(
                "/games/" + game + "/viewer-head", headers=headers())
            assert seen.status_code == 200, (
                "viewer-head", seen.status_code, seen.text)
            hint = seen.json()
            assert hint["watermark"] == expected and hint["status"] == status
            displayed = await viewer.get(
                "/games/" + game + "/viewer", headers=headers())
            assert displayed.status_code == 200, (
                "viewer-body", displayed.status_code, displayed.text)
            body = displayed.json()
            assert body["after"] == after
            assert body["status"] == status
            assert body["last_saved_at"]
            assert len(body["page"]["items"]) <= 25
            viewer_checks.append({"d3": expected, "status": status,
                "elapsed_ms": round((perf_counter() - started) * 1000, 1)})

        logged = await login(client, team)"""
    assert source.count(before) == 1
    source = source.replace(before, after, 1)
    source = _insert_after(
        source,
        "        current = read.json()",
        '\n        await verify_viewer("0", current["after"], "in_progress")',
    )
    source = _insert_after(
        source,
        "            current = saved.json()",
        '\n            await verify_viewer(str(index), current["after"], '
        '"in_progress")',
    )
    source = _insert_after(
        source,
        '        assert final["status"] == "finished"',
        "\n        await verify_viewer("
        'final["checkpoint"]["content"]["d3"], '
        'final["after"], "finished")',
    )
    source = _insert_after(
        source,
        '            "after": current["after"]["stateFields"],',
        '\n            "viewer_checks": viewer_checks,',
    )
    source = _insert_after(
        source,
        '            assert "eventResults" not in invisible_replay.json()',
        """
            denied_viewer = await foreign_client.get(
                "/games/" + game + "/viewer", headers=foreign_headers
            )
            assert denied_viewer.status_code == 404, (
                "foreign-viewer", denied_viewer.status_code
            )""",
    )
    return source


def _insert_unavailable_game(admin, game_id, tenant_id, source_game_id):
    """開始済みに見えるが確定世代を持たない実DB行を置く。"""
    admin.execute(
        "INSERT INTO public.games (id, scheduled_at, game_type_key, "
        "game_type_category, tournament_key, away_team_record_id, "
        "home_team_record_id, plate_umpire, section_label, week_label, "
        "day_label, game_number_label, started_at, status, applied_rules, "
        "rule_override, trashed_at, hidden_at, tenant_id, import_batch_id) "
        "SELECT %s, scheduled_at, game_type_key, game_type_category, "
        "tournament_key, away_team_record_id, home_team_record_id, "
        "plate_umpire, section_label, week_label, day_label, "
        "game_number_label, now(), 'in_progress', applied_rules, "
        "rule_override, trashed_at, hidden_at, tenant_id, import_batch_id "
        "FROM public.games WHERE tenant_id=%s AND id=%s",
        (game_id, tenant_id, source_game_id),
    )


def _pagination_script():
    """26球保存後、最新25球と旧pageを実HTTPで取得する。"""
    source = _script()
    old_results = """        results = [
            "batting-result.called-pitch",
            "batting-result.called-pitch",
        ]"""
    assert source.count(old_results) == 1
    source = source.replace(
        old_results,
        '        results = ["batting-result.called-pitch"] * 26',
        1,
    )
    start = source.index("        current_lifecycle, _ = await read_full()")
    tail = source.index("try:\n    out = asyncio.run(run())")
    page = """        current_lifecycle, _ = await read_full()
        assert current_lifecycle["status"] == "in_progress"
        first = await viewer.get(
            "/games/" + game + "/viewer", headers=headers())
        assert first.status_code == 200, ("first-page", first.status_code)
        first_body = first.json()
        assert len(first_body["page"]["items"]) == 25
        cursor = first_body["page"]["next_cursor"]
        assert isinstance(cursor, str) and cursor
        second = await viewer.get(
            "/games/" + game + "/viewer",
            params={"cursor": cursor}, headers=headers())
        assert second.status_code == 200, ("second-page", second.status_code)
        second_body = second.json()
        assert len(second_body["page"]["items"]) == 1
        assert second_body["page"]["next_cursor"] is None
        return {
            "game": game,
            "first_numbers": [
                row["play_row"]["play_number"]
                for row in first_body["page"]["items"]
            ],
            "second_numbers": [
                row["play_row"]["play_number"]
                for row in second_body["page"]["items"]
            ],
        }

"""
    return source[:start] + page + source[tail:]


def test_owned_viewer_separate_cookie_start_two_balls_and_end(vertical_database):
    """共有DBを使わず、実app role/C2/保存CPを別Cookieで照合する。"""
    assert len(_HOST_SOURCE_PATHS) == 3
    db = vertical_database
    unavailable_game = uuid4()
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
        # 開始済みに見えるが確定世代を持たない行を実DBへ置き、503を誘発する。
        _insert_unavailable_game(admin, unavailable_game, db.tenant_id, db.game_id)
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "other_team_name": db.other_team_name,
        "other_tenant_id": str(db.other_tenant_id),
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
        "unavailable_game": str(unavailable_game),
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _script()],
            capture_output=True,
            text=True,
            timeout=450,
        )
    assert process.returncode == 0, (process.stdout[-1000:], process.stderr[-1000:])
    result = json.loads(process.stdout)
    assert "exception" not in result, result.get("runtime_diagnostics", {})
    assert [row["d3"] for row in result["viewer_checks"]] == ["0", "1", "2", "6"]


def test_owned_viewer_paginates_latest_25_and_older_page(vertical_database):
    """26球の保存値を、最新25球のpage1と旧page2へ有限取得する。"""
    assert len(_HOST_SOURCE_PATHS) == 3
    db = vertical_database
    unavailable_game = uuid4()
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        _insert_unavailable_game(admin, unavailable_game, db.tenant_id, db.game_id)
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
        "unavailable_game": str(unavailable_game),
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _pagination_script()],
            capture_output=True,
            text=True,
            timeout=450,
        )
    assert process.returncode == 0, (process.stdout[-1000:], process.stderr[-1000:])
    result = json.loads(process.stdout)
    assert "exception" not in result, result.get("runtime_diagnostics", {})
    assert [int(value) for value in result["first_numbers"]] == list(range(2, 27))
    assert [int(value) for value in result["second_numbers"]] == [1]
