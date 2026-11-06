"""実作成保存/RRROと同DBの実生成SQLを有限D11期待へ照合する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from pitchlog.domaincheck.runners import stats_native as runner
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

from . import test_stats_native_read_http as real_read
from .test_stats_native_read_http import admin_connection as admin_connection
from .test_stats_native_read_http import (
    initial_scope_database as initial_scope_database,
)
from .test_stats_native_read_http import product_node_binary as product_node_binary
from .test_stats_native_read_http import (
    tested_role_connection as tested_role_connection,
)
from .test_stats_native_read_http import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db
ROOT = Path(__file__).resolve().parents[3]


def _json_exact(value):
    """PG整数numericだけをlossless文字列へ写し、floatで丸めない。"""
    from decimal import Decimal

    if type(value) is Decimal:
        assert value.is_finite() and value == int(value)
        from pitchlog.stats.generated.receiver import format_count

        return format_count(int(value))
    if type(value) is int:
        from pitchlog.stats.generated.receiver import format_count

        return format_count(value)
    if type(value) is UUID:
        return str(value)
    if type(value) is dict:
        return {k: _json_exact(v) for k, v in value.items()}
    if type(value) in (tuple, list):
        return [_json_exact(v) for v in value]
    return value


@pytest.mark.parametrize("kind", ["invariant", "equivalence"])
def test_d11_evidence_real_sql_rrro_receiver_and_formatter_all27(
    vertical_database,
    monkeypatch,
    tmp_path,
    record_property,
    kind,
):
    """事前投入accepted源なしに3球保存し、同DBの全27fieldと3段を比較する。"""
    db = vertical_database
    manifest = runner.validate_registration(ROOT)
    calc = manifest["calculations"][1]
    target = calc["directTargets"][0]
    vector = runner.read_json(ROOT, calc["vectors"][0]["path"])
    case = vector["cases"][0]
    # 元の実認証/記録権/同TX/再送/読取/移植拒否を一切差し替えない。
    real_read.test_actual_saved_native_has_real_rrro_open_pages_and_totals(
        db, monkeypatch, tmp_path
    )
    saved = json.loads((tmp_path / "stats-native-real-read-observed.json").read_text())
    observed = saved["observed"]
    product = [observed["totals"][mid] for mid in sorted(observed["totals"])]
    expected = case["expected"]["expected"]
    assert product == expected
    receipt = observed["receipt"]
    scope = {
        "tenant_id": db.tenant_id,
        "game_id": UUID(observed["game"]),
        "player_id": UUID(observed["player"]),
        "model_sha256": SOURCE_MODEL_HASH,
        "fact_version_id": UUID(receipt["fact_version_id"]),
        "revision": receipt["revision"],
        "source_set_sha256": receipt["source_set_sha256"],
    }
    with psycopg.connect(db.authority.database.business_admin) as connection:
        actual, raw_rows, calls, execution = runner.execute_sql_composite(
            connection, scope, root=ROOT
        )
        source_rows = connection.execute(
            "SELECT source_event_id,metric_states "
            "FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d2,source_event_id",
            (db.tenant_id, scope["game_id"]),
        ).fetchall()
    assert len(raw_rows) == len(actual) == 27
    assert runner.full_values_match(
        calc["calculation"], case["caseId"], expected, product, actual
    )
    if kind == "invariant":
        assert len({row["metric_id"] for row in actual}) == 27
        for row in actual:
            if row["state"] == "available":
                assert type(row["value"]) is str and row["value"].isdigit()
                assert row["display"] == row["value"]
            else:
                assert row["state"] == "source_unavailable"
                assert row["value"] is row["display"] is None
    # 全帰属は保存原本の全recordを閉確認する。期待を原本から採取しない。
    assert len(source_rows) == 3
    for source_id, evaluation in source_rows:
        assert set(evaluation) == {
            "metrics",
            "pa_row",
            "decisions",
            "selected",
            "source_event_id",
            "native_rule_sha256",
        }
        assert evaluation["selected"] is True and evaluation["source_event_id"] == str(
            source_id
        )
        assert evaluation["pa_row"] is None and len(evaluation["metrics"]) == 27
        for mid, value in evaluation["metrics"].items():
            assert set(value) == {"state", "value", "display", "reason", "credits"}
            wanted = next(row for row in expected if row["metric_id"] == mid)
            if wanted["state"] == "source_unavailable":
                assert value == {
                    "state": "source_unavailable",
                    "value": None,
                    "display": None,
                    "reason": "MISSING_OBSERVATION",
                    "credits": [],
                }
            elif mid == "pitch_count":
                assert value == {
                    "state": "available",
                    "value": "1",
                    "display": "1",
                    "reason": None,
                    "credits": [{"player_id": observed["player"], "quantity": "1"}],
                }
            else:
                assert value == {
                    "state": "available",
                    "value": "0",
                    "display": "0",
                    "reason": None,
                    "credits": [],
                }
    assert calls and any(c["event"] == "return" and c["output"] == "3" for c in calls)
    hashes = {part["stage"]: part["hash"] for part in target["components"]}
    raw = [
        {"metric_id": mid, "state": state, "value": _json_exact(value)}
        for mid, state, value in raw_rows
    ]
    trace = {
        "vector": calc["vectors"][0]["vectorId"],
        "case": case["caseId"],
        "entrypointId": calc["entrypoints"][0]["entrypointId"],
        "directTargetId": target["directTargetId"],
        "expected": expected,
        "entrypointOutput": product,
        "directTargetOutput": actual,
        "artifactHashes": hashes,
        "issuedSqlOrAst": execution["issued_sql"],
        "stageIO": [
            {
                "stage": "sql",
                "artifactHash": hashes["sql"],
                "input": _json_exact(execution["parameters"]),
                "output": raw,
            },
            {
                "stage": "typed-receiver",
                "artifactHash": hashes["typed-receiver"],
                "input": raw,
                "output": actual,
            },
            {
                "stage": "formatter",
                "artifactHash": hashes["formatter"],
                "input": actual,
                "output": actual,
            },
        ],
    }
    runner.validate_stage_trace(trace, calc["calculation"], target)
    bad = copy.deepcopy(trace)
    bad["stageIO"][2]["output"] = []
    with pytest.raises(ValueError):
        runner.validate_stage_trace(bad, calc["calculation"], target)
    for key, value in {
        "calculation": calc["calculation"],
        "propertyId": calc["calculation"] + "-" + kind,
        "propertyKind": kind,
        "generatedCases": 1,
        "status": "passed",
        "trace": trace,
    }.items():
        record_property(key, json.dumps(value) if isinstance(value, dict) else value)
    (tmp_path / "stats-native-d11-actual.json").write_text(
        json.dumps(
            {
                "trace": trace,
                "direct_target_formatter_calls": _json_exact(calls),
                "product_null_branch": (
                    "receiver returns None without calling format_count; "
                    "no product-call claim"
                ),
                "scope": "current_open native27 only; not official-ended/season/UI/CSV",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
