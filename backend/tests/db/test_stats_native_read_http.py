"""実HTTP保存3球と同owned DBの真正RRRO Open/Page/Totalsを接続する。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH

from . import test_stats_native_vertical_http as native
from .test_stats_native_vertical_http import (
    admin_connection as admin_connection,
)
from .test_stats_native_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_stats_native_vertical_http import (
    product_node_binary as product_node_binary,
)
from .test_stats_native_vertical_http import (
    tested_role_connection as tested_role_connection,
)
from .test_stats_native_vertical_http import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db

_READ_SCRIPT = r"""
        from sqlalchemy import text
        from sqlalchemy.exc import DBAPIError
        from pitchlog.repositories import transaction as read_runtime
        from pitchlog.repositories.play_export_primitives import (
            PrimitiveReadError, PrimitiveScope, ReadPlayExportPrimitives,
        )
        from pitchlog.repositories.stats import read_primitive_totals
        from pitchlog.repositories.tenant_context_issuance import (
            issue_tenant_context_from_presented_token,
        )
        from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH

        def actual_context(selected_client, expected_tenant):
            cookie = selected_client.cookies.get('__Host-pitchlog_token')
            assert type(cookie) is str and cookie
            issued = issue_tenant_context_from_presented_token(
                cookie, app.state.token_presentation
            )
            assert issued is not None
            context = issued[0]
            assert context.tenant_id == UUID(expected_tenant)
            return context

        def require_closed_rejection(callback):
            try:
                callback()
            except PrimitiveReadError as error:
                assert error.args == () and error.__cause__ is None
                return True
            raise AssertionError('実reader資格の閉拒否がありません')

        context = actual_context(client, tenant)
        primitive_scope = PrimitiveScope(
            UUID(game), UUID(str(people.pitcher_id)), SOURCE_MODEL_HASH
        )
        read_rows = []
        rejected = {}
        with read_runtime.stats_primitive_read_scope(context) as read_handle:
            read_runtime._require_stats_primitive_read_scope(read_handle)
            # 観測だけであり、Session/設定を差替えず実driver/DB設定を読む。
            session = read_runtime._TRANSACTION_RUNTIMES[read_handle._state_key][0]
            rrro = tuple(session.execute(text(
                "SELECT session_user,current_user,"
                "current_setting('transaction_isolation'),"
                "current_setting('transaction_read_only')"
            )).one())
            assert rrro == ('pitchlog_app', 'pitchlog_app', 'repeatable read', 'on')
            reader = ReadPlayExportPrimitives(read_handle, maximum_integer_chars=20000)
            receipt = reader.open(primitive_scope)
            assert receipt.source_count == receipt.revision == 3
            assert receipt.completion_state == 'current_open'
            assert receipt.row_count == 3 * len(METRIC_IDS)
            cursor = None
            first_cursor = None
            page_calls = 0
            # 全78行と終端空pageだけ。DB COUNTを自由な反復上限に使わない。
            for _ in range(3 * len(METRIC_IDS) + 1):
                page = reader.read_page(receipt, cursor=cursor, page_size=1)
                page_calls += 1
                if not page.rows:
                    assert page.next_cursor is None
                    break
                assert len(page.rows) == 1 and page.next_cursor is not None
                if first_cursor is None:
                    first_cursor = page.next_cursor
                row = dict(page.rows[0])
                row['source_event_id'] = str(row['source_event_id'])
                read_rows.append(row)
                cursor = page.next_cursor
            else:
                raise AssertionError('有限pageの終端がありません')
            assert len(read_rows) == receipt.row_count
            totals = read_primitive_totals(reader, receipt)
            assert totals['pitch_count'] == {
                'metric_id': 'pitch_count', 'state': 'available',
                'value': '3', 'display': '3',
            }
            with read_runtime.stats_primitive_read_scope(context) as second_handle:
                second = ReadPlayExportPrimitives(
                    second_handle, maximum_integer_chars=20000
                )
                second_receipt = second.open(primitive_scope)
                # snapshot文字列が同値でも、別handle/readerの実receiptは移植不可。
                same_snapshot_value = (
                    receipt.transaction_id == second_receipt.transaction_id
                )
                rejected['other_scope_page'] = require_closed_rejection(
                    lambda: second.read_page(receipt, page_size=1)
                )
                rejected['other_scope_totals'] = require_closed_rejection(
                    lambda: read_primitive_totals(second, receipt)
                )
                rejected['other_scope_cursor'] = require_closed_rejection(
                    lambda: second.read_page(
                        second_receipt, cursor=first_cursor, page_size=1
                    )
                )
            receipt_values = {
                'fact_version_id': str(receipt.fact_version_id),
                'revision': receipt.revision,
                'source_set_sha256': receipt.source_set_sha256,
                'model_sha256': receipt.scope.model_sha256,
                'source_count': receipt.source_count,
                'row_count': receipt.row_count,
                'completion_state': receipt.completion_state,
            }
        rejected['expired_open'] = require_closed_rejection(
            lambda: reader.open(primitive_scope)
        )
        rejected['expired_page'] = require_closed_rejection(
            lambda: reader.read_page(receipt, page_size=1)
        )
        rejected['expired_totals'] = require_closed_rejection(
            lambda: read_primitive_totals(reader, receipt)
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url='https://test'
        ) as foreign_client:
            foreign_login = await login(foreign_client, case['other_team_name'])
            assert foreign_login.status_code == 200
            foreign_context = actual_context(foreign_client, case['other_tenant'])
        assert foreign_context.tenant_id != context.tenant_id
        try:
            with read_runtime.stats_primitive_read_scope(
                foreign_context
            ) as foreign_handle:
                foreign = ReadPlayExportPrimitives(
                    foreign_handle, maximum_integer_chars=20000
                )
                foreign.open(primitive_scope)
        except DBAPIError as error:
            # 一般ACL不足/関数未供給を「別tenant拒否」へ読み替えない。
            assert getattr(error.orig, 'sqlstate', None) == '42501'
            diagnostic = getattr(error.orig, 'diag', None)
            assert getattr(diagnostic, 'message_primary', None) == (
                'stats primitive boundary rejected'
            )
            rejected['foreign_tenant'] = True
        else:
            raise AssertionError('別tenantで原本が見えました')
        real_read = {
            'game': game, 'player': str(primitive_scope.player_id),
            'rrro': rrro, 'receipt': receipt_values, 'rows': read_rows,
            'page_calls': page_calls, 'page_size': 1, 'totals': totals,
            'rejected': rejected, 'same_snapshot_value': same_snapshot_value,
        }
"""


def _read_script(original: str) -> str:
    """元3球・再送・GETの全assert後/return前に実readerだけを接ぐ。"""
    needle = '        return {\n            "game": game,\n'
    if original.count(needle) != 1:
        raise AssertionError("元HTTP return接合点が不一致です")
    original = original.replace(needle, _READ_SCRIPT + "\n" + needle, 1)
    needle = '            "history": len(reload.json()["page"]["items"]),'
    if original.count(needle) != 1:
        raise AssertionError("元HTTP結果の接合点が不一致です")
    original = original.replace(
        needle, needle + '\n            "real_read": real_read,', 1
    )
    compile(original, "<stats-native-real-read>", "exec")
    return original


def _check_observed_read(value, sources, version) -> None:
    """保存sourceの閉対応と既確定球数だけを照合し、未確定意味を足さない。"""
    assert type(value) is dict and set(value) == {
        "game",
        "player",
        "rrro",
        "receipt",
        "rows",
        "page_calls",
        "page_size",
        "totals",
        "rejected",
        "same_snapshot_value",
    }
    assert type(value["same_snapshot_value"]) is bool
    assert type(value["game"]) is type(value["player"]) is str
    assert str(UUID(value["game"])) == value["game"]
    assert str(UUID(value["player"])) == value["player"]
    expected_rejections = {
        "other_scope_page",
        "other_scope_totals",
        "other_scope_cursor",
        "expired_open",
        "expired_page",
        "expired_totals",
        "foreign_tenant",
    }
    if set(value["rejected"]) != expected_rejections or any(
        v is not True for v in value["rejected"].values()
    ):
        raise AssertionError("実readerのscope/失効/別tenant拒否が不足しています")
    assert value["rrro"] == ["pitchlog_app", "pitchlog_app", "repeatable read", "on"]
    assert type(value["page_size"]) is int and value["page_size"] == 1
    assert type(value["page_calls"]) is int
    assert value["page_calls"] == 3 * len(METRIC_IDS) + 1
    receipt = value["receipt"]
    assert receipt == {
        "fact_version_id": str(version[0]),
        "revision": 3,
        "source_set_sha256": version[2],
        "model_sha256": SOURCE_MODEL_HASH,
        "source_count": 3,
        "row_count": 3 * len(METRIC_IDS),
        "completion_state": "current_open",
    }
    assert all(
        type(receipt[key]) is int for key in ("revision", "source_count", "row_count")
    )
    rows = value["rows"]
    assert len(rows) == len(sources) * len(METRIC_IDS) == receipt["row_count"]
    by_source = {str(row[0]): (row[1], set(row[2])) for row in sources}
    assert len(by_source) == 3
    expected_keys = {
        (d2, event, metric)
        for event, (d2, _) in by_source.items()
        for metric in METRIC_IDS
    }
    observed_keys = []
    for row in rows:
        assert set(row) == {
            "metric_id",
            "state",
            "value",
            "display",
            "d2",
            "source_event_id",
        }
        event, metric = row["source_event_id"], row["metric_id"]
        assert event in by_source and metric in METRIC_IDS
        d2, computed = by_source[event]
        assert type(row["d2"]) is int and row["d2"] == d2
        observed_keys.append((d2, event, metric))
        # 未決metricを0と仮定しない。保存済sourceの供給有無をそのまま尊重する。
        if metric not in computed:
            assert row["state"] == "source_unavailable"
            assert row["value"] is row["display"] is None
        else:
            assert row["state"] == "available"
            assert type(row["value"]) is str and row["display"] == row["value"]
        if metric == "pitch_count":
            assert row["state"] == "available" and row["value"] == row["display"] == "1"
    assert len(set(observed_keys)) == len(observed_keys)
    assert set(observed_keys) == expected_keys
    assert observed_keys == sorted(
        observed_keys, key=lambda k: (k[0], UUID(k[1]).int, k[2])
    )
    totals = value["totals"]
    assert set(totals) == set(METRIC_IDS)
    assert totals["pitch_count"] == {
        "metric_id": "pitch_count",
        "state": "available",
        "value": "3",
        "display": "3",
    }
    for metric, row in totals.items():
        assert set(row) == {"metric_id", "state", "value", "display"}
        assert row["metric_id"] == metric
        if any(metric not in computed for _, computed in by_source.values()):
            assert row["state"] == "source_unavailable"
            assert row["value"] is row["display"] is None
        else:
            assert row["state"] == "available"
            assert type(row["value"]) is str and row["display"] == row["value"]


def test_actual_saved_native_has_real_rrro_open_pages_and_totals(
    vertical_database, monkeypatch, tmp_path: Path
) -> None:
    """元実HTTP3球を保存し、同実DBの読取と資格拒否を検査する。"""
    db = vertical_database
    ordinary = native.ordinary
    arguments = ordinary._app_arguments

    def read_arguments(database, case):
        # ログイン名/tenant UUIDだけを既owned caseへ追加。資格値をhostへ取り出さない。
        case = dict(
            case,
            other_team_name=db.other_team_name,
            other_tenant=str(db.other_tenant_id),
        )
        return arguments(database, case)

    directory = tmp_path / "native-save-and-read"
    directory.mkdir()
    with monkeypatch.context() as patch:
        patch.setattr(ordinary, "_SCRIPT", _read_script(ordinary._SCRIPT))
        patch.setattr(ordinary, "_app_arguments", read_arguments)
        native.test_native_http_three_pitch_has_same_tx_stats_sources(
            db, patch, directory
        )
    path = directory / "stats-native-three-pitch-observed.json"
    observed = json.loads(path.read_text(encoding="utf-8"))
    game = UUID(observed["game"])
    assert game != db.game_id
    value = observed["http_result"]["real_read"]
    assert value["game"] == observed["game"]
    player = UUID(value["player"])
    with psycopg.connect(db.authority.database.business_admin) as admin:
        sources = admin.execute(
            "SELECT source_event_id,d2,computed_metric_keys "
            "FROM sync_fence.stats_primitive_sources WHERE tenant_id=%s AND game_id=%s "
            "ORDER BY d2,source_event_id",
            (db.tenant_id, game),
        ).fetchall()
        versions = admin.execute(
            "SELECT id,revision,source_set_sha256,source_count,completion_state "
            "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s AND game_id=%s "
            "AND is_current AND invalidated_at IS NULL",
            (db.tenant_id, game),
        ).fetchall()
        facts = admin.execute(
            "SELECT source_event_id,amount FROM sync_fence.stats_primitive_facts "
            "WHERE tenant_id=%s AND game_id=%s AND player_id=%s "
            "AND metric_id='pitch_count' AND state='available' "
            "ORDER BY source_event_id",
            (db.tenant_id, game, player),
        ).fetchall()
    assert len(versions) == 1 and versions[0][1] == versions[0][3] == 3
    assert versions[0][4] == "current_open"
    assert len(facts) == 3 and {r[0] for r in facts} == {r[0] for r in sources}
    assert all(r[1] == 1 for r in facts)
    _check_observed_read(value, sources, versions[0])
    (tmp_path / "stats-native-real-read-observed.json").write_text(
        json.dumps(
            {
                "scope": "ordinary current_open / real RRRO 3 read entries only",
                "observed": value,
                "not_established": [
                    "unsettled_metric_meanings",
                    "official_ended_stats",
                    "UI",
                    "all_profiles",
                    "all_atomicity",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
