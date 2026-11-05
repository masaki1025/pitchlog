"""実POST新規3球の同TX原本保存をowned環境だけで追加観測する。"""

import json
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest

from . import test_ordinary_pitch_vertical_http as ordinary
from .test_ordinary_pitch_vertical_http import (
    admin_connection as admin_connection,
)
from .test_ordinary_pitch_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_ordinary_pitch_vertical_http import (
    product_node_binary as product_node_binary,
)
from .test_ordinary_pitch_vertical_http import (
    tested_role_connection as tested_role_connection,
)
from .test_ordinary_pitch_vertical_http import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db


def test_native_http_three_pitch_has_same_tx_stats_sources(
    vertical_database, monkeypatch, tmp_path
):
    """実記録を再利用し同TX成績原本を照合する。故障時は固定SQL位置だけ採る。"""
    db = vertical_database
    needle = "fixed_sql_error=safe_primary,"
    replacement = r"""fixed_sql_error=safe_primary,
            database_context_frames=__import__("re").findall(
                r"PL/pgSQL function ([A-Za-z_][A-Za-z0-9_.]*"
                r"\([A-Za-z0-9_, ]*\)) line ([0-9]+) at ([A-Z ]+)",
                getattr(diagnostic, "context", None) or "",
            ),"""
    assert ordinary._SCRIPT.count(needle) == 1
    with monkeypatch.context() as patch:
        # 実apply/SQL/例外はそのまま。値・nonceを含まない関数名/行番号だけ追加。
        patch.setattr(
            ordinary, "_SCRIPT", ordinary._SCRIPT.replace(needle, replacement)
        )
        # 元HTTP関数の結果出力だけをこの試験の固有ディレクトリへ分離する。
        patch.setattr(
            ordinary, "tempfile", SimpleNamespace(gettempdir=lambda: str(tmp_path))
        )
        ordinary.test_actual_http_create_start_three_pitches_replay_and_prefix_reload(
            db
        )
    path = (
        tmp_path
        / "pitchlog/ordinary37-runtime-source-candidate-20261030"
        / "newAPI-last-result.json"
    )
    result = json.loads(path.read_text())
    game = UUID(result["game"])
    assert game != db.game_id
    with psycopg.connect(db.authority.database.business_admin) as admin:
        events = admin.execute(
            "SELECT id FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1,d2",
            (db.tenant_id, game),
        ).fetchall()
        sources = admin.execute(
            "SELECT source_event_id,d1,d2,computed_metric_keys,metric_states "
            "FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1,d2",
            (db.tenant_id, game),
        ).fetchall()
        versions = admin.execute(
            "SELECT source_count,revision,completion_state,is_current "
            "FROM sync_fence.stats_fact_versions WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, game),
        ).fetchall()
        totals = admin.execute(
            "SELECT metric_id,SUM(amount) FROM sync_fence.stats_primitive_facts "
            "WHERE tenant_id=%s AND game_id=%s AND state='available' "
            "GROUP BY metric_id ORDER BY metric_id",
            (db.tenant_id, game),
        ).fetchall()
    evidence = {
        "scope": (
            "owned actual HTTP new game/start/3 native pitches/resend/GET, "
            "sameTX source observations; not UI/official stats/API read acceptance"
        ),
        "game": str(game),
        "events": [str(r[0]) for r in events],
        "sources": sources,
        "versions": versions,
        "totals": totals,
        "http_result": result,
    }
    (tmp_path / "stats-native-three-pitch-observed.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    assert len(events) == len(sources) == 3
    assert [r[0] for r in events] == [r[0] for r in sources]
    assert versions == [(3, 3, "current_open", True)]
    assert dict(totals)["pitch_count"] == 3
