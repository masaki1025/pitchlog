"""実POSTの受理source→同TX T5保存→登録唯一readerを所有PGで検証する。"""

import json
import subprocess
from importlib import import_module
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
from .test_first_ball_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_first_ball_vertical_http import vertical_database as vertical_database
from .test_initial_game_start import product_node_binary as product_node_binary
from .test_initial_recording_right_scope import admin_connection as admin_connection
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)
from .test_ordinary_pitch_vertical_http import _SCRIPT as _ORDINARY_SCRIPT

pytestmark = pytest.mark.requires_db

_READ = r"""
        from pitchlog.repositories.tenant_context_issuance import issue_tenant_context_from_presented_token
        from pitchlog.repositories.transaction import stats_primitive_read_scope
        from pitchlog.repositories.play_export_primitives import (
            ReadPlayExportPrimitives,PrimitiveScope,PrimitiveReadError,PrimitiveCursor)
        from pitchlog.repositories.stats import read_primitive_totals
        from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
        issued=issue_tenant_context_from_presented_token(
            client.cookies.get('__Host-pitchlog_token'),app.state.token_presentation)
        assert issued is not None
        context,_=issued
        from pitchlog.repositories.transaction import tenant_transaction_scope
        with tenant_transaction_scope(context) as writable:
            try:
                ReadPlayExportPrimitives(writable,maximum_integer_chars=20000)
            except PrimitiveReadError:
                pass
            else:
                raise AssertionError('通常writable scopeをRR ROとして受理した')
        with stats_primitive_read_scope(context) as handle:
            reader=ReadPlayExportPrimitives(handle,maximum_integer_chars=20000)
            scope=PrimitiveScope(UUID(game),UUID(people.pitcher_id),SOURCE_MODEL_HASH)
            receipt=reader.open(scope)
            assert receipt.source_count==case['stats_expected_sources']
            assert receipt.row_count==26*case['stats_expected_sources']
            pages=list(reader.pages(receipt,page_size=2))
            assert sum(len(page.rows) for page in pages)==receipt.row_count
            totals=read_primitive_totals(reader,receipt)
            assert totals['pitch_count']['value']==str(case['stats_expected_sources'])
            assert totals['pitching_outs']['value']=='0'
            assert totals['runs']['state']=='source_unavailable'
            assert totals['runs']['value'] is None
            assert pages[-1].rows[-1]['value'] is not None or pages[-1].rows[-1]['state']=='source_unavailable'
            batter_receipt=reader.open(PrimitiveScope(UUID(game),UUID(people.batter_id),SOURCE_MODEL_HASH))
            batting=read_primitive_totals(reader,batter_receipt)
            assert batting['pa']['value']==str(case['stats_expected_pa'])
            assert batting['bb']['value']==str(case['stats_expected_bb'])
            assert batting['hbp']['value']==str(case['stats_expected_hbp'])
            first=pages[0].next_cursor
            try:
                reader.read_page(receipt,cursor=PrimitiveCursor(first.d2,first.source_event_id,first.metric_id))
            except PrimitiveReadError:
                pass
            else:
                raise AssertionError('自由cursorを同snapshotとして受理した')
            second_receipt=reader.open(scope)
            try:
                reader.read_page(second_receipt,cursor=first)
            except PrimitiveReadError:
                pass
            else:
                raise AssertionError('別receiptのcursorを混用した')
            read_summary={'source_count':receipt.source_count,'row_count':receipt.row_count,
                          'revision':receipt.revision,'pitch_count':totals['pitch_count']['value'],
                          'pa':batting['pa']['value'],'bb':batting['bb']['value'],'hbp':batting['hbp']['value'],
                          'window_final_pitch_count':next(row['value'] for page in reversed(pages)
                              for row in reversed(page.rows) if row['metric_id']=='pitch_count')}
        try:
            reader.read_page(receipt)
        except PrimitiveReadError:
            pass
        else:
            raise AssertionError('終了handleを再使用した')
"""  # noqa: E501 — 実app容器へ渡す有限試験script

_SCRIPT = _ORDINARY_SCRIPT.replace(
    '        return {\n            "game": game,',
    _READ
    + '        return {\n            "stats": read_summary,\n'
    + '            "game": game,',
)
assert _SCRIPT != _ORDINARY_SCRIPT


def _run_native_reader(vertical_database, native_variant="ordinary-v1"):
    """DB事前投入のaccepted eventや自由receiptで成功を代替しない。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as conn:
        conn.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
    expected_sources = 3 if native_variant == "ordinary-v1" else 5
    script = _SCRIPT
    if native_variant != "ordinary-v1":
        _script = import_module(".test_terminal_pitch_storage", __package__)._script

        result = (
            "batting-result.walk"
            if native_variant == "v2-walk"
            else "batting-result.hit-by-pitch"
        )
        with psycopg.connect(db.authority.database.business_admin) as conn:
            conn.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (result, "四球" if native_variant == "v2-walk" else "死球"),
            )
        original = _script(result)
        # 終端後の次打者ではなく、実終端入力の当人へPA寄与を照合する。
        loop = '        for result in [terminal_result, "batting-result.ball"]:'
        assert original.count(loop) == 1
        original = original.replace(loop, "        completed_batter_id = None\n" + loop)
        participants = (
            "                roster, "
            "StateSnapshot.model_validate_json(json.dumps(roster_before))\n"
            "            )"
        )
        assert original.count(participants) == 1
        original = original.replace(
            participants,
            participants + "\n            if result == terminal_result:\n"
            "                completed_batter_id = people.batter_id",
        )
        completed_read = _READ.replace(
            "UUID(people.batter_id)", "UUID(completed_batter_id)"
        )
        assert completed_read != _READ
        marker = '        return {\n            "game": game,'
        assert original.count(marker) == 1
        script = original.replace(
            marker,
            completed_read
            + '        return {\n            "stats": read_summary,\n'
            + '            "game": game,',
            1,
        )
    case = {
        "stats_expected_sources": expected_sources,
        "stats_expected_pa": int(native_variant != "ordinary-v1"),
        "stats_expected_bb": int(native_variant == "v2-walk"),
        "stats_expected_hbp": int(native_variant == "v2-hbp"),
        "other_tenant_id": str(db.other_tenant_id),
        "other_team_name": db.other_team_name,
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", script],
            capture_output=True,
            text=True,
            timeout=300,
        )
    assert process.returncode == 0, (process.stdout[-800:], process.stderr[-800:])
    result = json.loads(process.stdout)
    assert "exception" not in result, result
    assert result["stats"]["source_count"] == expected_sources
    assert result["stats"]["row_count"] == 26 * expected_sources
    assert result["stats"]["pitch_count"] == str(expected_sources)
    assert result["stats"]["window_final_pitch_count"] == str(expected_sources)


@pytest.mark.parametrize("native_variant", ["ordinary-v1", "v2-walk", "v2-hbp"])
def test_real_accepted_native_source_and_registered_reader(
    vertical_database, native_variant
):
    """真正nativeの球数だけでなくPA/BB/HBPも同じreaderのDB値で閉じる。"""
    _run_native_reader(vertical_database, native_variant)
