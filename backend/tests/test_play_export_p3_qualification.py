"""P3 CSV世代境界と表示式の純検査。実PG保存資格は模倣しない。"""

import ast
import json
import re
import sqlite3
from pathlib import Path

import pytest

from pitchlog.authz import play_export_p3_direct_sql as direct
from pitchlog.authz import play_export_p3_product as product
from pitchlog.authz.play_export_p3_read_product import candidate_read_body
from pitchlog.exports.generated.coordinate_transform import plate_result_display
from pitchlog.exports.record_projection import _native_before, _native_completion

_ROOT = Path(__file__).resolve().parents[2]


def _evaluate(expression, payload, **parameters):
    """SQLiteで生成CASE/文字列写像だけを実行し、PG権限成功とは扱わない。"""

    def lookup(raw, path, as_json):
        value = json.loads(raw)
        for key in path[1:-1].split(","):
            if type(value) is not dict or key not in value:
                return None
            value = value[key]
        if as_json:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return value

    sql = re.sub(
        r"ctx\.payload#(>>|>)('(?:''|[^'])*')",
        lambda m: (
            ("pg_text" if m[1] == ">>" else "pg_json") + "(:payload," + m[2] + ")"
        ),
        expression,
    ).replace("::jsonb", "")
    sql = re.sub(
        r"ctx\.payload->>('(?:''|[^'])*')",
        lambda m: "pg_text(:payload,'{" + m[1][1:-1] + "}')",
        sql,
    )
    for name in parameters:
        sql = re.sub(r"\b" + name + r"\b", ":" + name, sql)
    with sqlite3.connect(":memory:") as connection:
        connection.create_function(
            "pg_text", 2, lambda raw, path: lookup(raw, path, False)
        )
        connection.create_function(
            "pg_json", 2, lambda raw, path: lookup(raw, path, True)
        )
        return connection.execute(
            "SELECT " + sql, {"payload": json.dumps(payload), **parameters}
        ).fetchone()[0]


def test_generation_is_bound_before_limit_without_changing_global_source_health():
    """前世代25件以上でも現世代を頁送り前に絞り、全Sの健康値は保持する。"""
    query = product._generation_source_query(_ROOT)
    bounded = query.split("bounded_members AS (", 1)[1].split("\n)\nSELECT", 1)[0]
    assert bounded.index(
        "s.recording_generation=:recording_generation"
    ) < bounded.index("LIMIT :page_size")
    assert (
        "FROM source_members g WHERE g.recording_generation=:recording_generation"
        in query
    )
    assert "v.source_count" in query and "WHERE h.actual_count=h.source_count" in query
    prior = product.candidate_prior_read_body()
    assert "v.source_count=p_watermark" in prior
    assert "sync_fence.stats_primitive_sources s" in prior
    assert "ORDER BY v.revision DESC LIMIT 1" in prior
    assert "s.source_count=p_watermark" not in prior
    assert "game_source_count bigint,generation_source_count bigint" in prior
    # 読取headは先頭S世代に左右されず、既tenant/game/gen JOINへ束縛される。
    body = candidate_read_body()
    assert "COALESCE(h.capsule_id=x.capsule_id,false)" in body
    assert "x.internal_generation=s.recording_generation" not in body


@pytest.mark.parametrize("half", ["top", "bottom"])
@pytest.mark.parametrize(
    "ended,completed,game",
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, True, True),
    ],
)
def test_saved_display_sql_equals_existing_python_all_leaf_values(
    half, ended, completed, game
):
    """保存T1/T2の参照だけを生成式へ写し、旧表示出力を全列比較する。"""
    state = {
        "state.half": half,
        "state.inning": "7",
        "state.score": {"away": "12", "home": "3"},
        "state.count.strikes": "1",
        "state.count.balls": "2",
        "state.outs": "2",
    }
    payload = {
        "formatVersion": "play-prefix-play-v3",
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "request": {
                "t1": {
                    "before": {
                        "stateFields": state,
                        "battingOrderBySide": {"away": "8", "home": "4"},
                    }
                }
            },
            "response": {
                "value": {
                    "t1": {
                        "plateAppearanceEnded": ended,
                        "after": {"stateFields": {"state.gameEnded": game}},
                    },
                    "t2": {
                        "kind": "evaluated-end-condition",
                        "scope": "play-prefix-v3",
                        "facts": {"halfCompleted": completed},
                    },
                }
            },
        },
    }
    from pitchlog.exports.play_rows import CSV_HEADERS

    expected = {**_native_before(payload), **_native_completion(payload)}
    actual = {
        CSV_HEADERS["plays.csv"][n]: _evaluate(expression, payload)
        for n, expression in direct.state_display_expressions(_ROOT).items()
    }
    assert actual == expected


def test_all_plate_model_variants_keep_existing_formatter_bytes():
    """alias/野手形式/通常ラベルの全分岐を旧formatterとSQL CASEで照合する。"""
    sql = direct.plate_display_sql(_ROOT)
    expression = sql.split("display_plate:=", 1)[1].split(";", 1)[0]
    model = json.loads(
        (_ROOT / "backend/domain/play-export-display.model.json").read_bytes()
    )["plateResultDisplay"]
    for label in (*model["aliases"], *model["fielderFormats"], "ボール", "単打"):
        for fielder in ("1", "9"):
            for ball in ("ゴロ", "ライナー"):
                assert _evaluate(
                    expression,
                    {},
                    display_label=label,
                    display_fielder=fielder,
                    display_ball_type=ball,
                ) == plate_result_display(label, True, fielder, ball)


def test_unknown_ast_and_calls_are_rejected_without_execution(tmp_path):
    """原典変更/自由callを評価せず拒否する。"""
    path = tmp_path / "backend/src/pitchlog/exports/record_projection.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        (_ROOT / "backend/src/pitchlog/exports/record_projection.py")
        .read_text()
        .replace('"表" if half', '"未知" if half')
    )
    with pytest.raises(ValueError, match="固定AST"):
        direct.state_display_expressions(tmp_path)
    with pytest.raises(ValueError, match="未知AST"):
        direct._expression(ast.parse("open('forbidden')", mode="eval").body, {})


def test_save_compares_all_dynamic_columns_to_saved_capsule_before_insert():
    """自由JSONは閉列集合だけでなく保存原本との全値比較を通らねば保存しない。"""
    from pitchlog.exports.play_rows import CSV_HEADERS

    sql = product.candidate_save_body()
    suffix = sql.split("P3 CSV follower reference changed", 1)[1]
    before_insert = suffix.split("INSERT INTO sync_fence.play_export_p3_snapshots", 1)[
        0
    ]
    for n in (*range(10, 20), 61, 62, 72, 73, 74):
        assert "p_direct_json->" in before_insert
        assert CSV_HEADERS["plays.csv"][n] in before_insert
    assert "ctx.payload#>>" in before_insert
    assert "ctx.source_event_id::text" in before_insert
    assert "ctx.capsule_id::text" in before_insert
    assert "ctx.item_digest" in before_insert
    assert "expected_origin_text" in before_insert
    assert "digest(p_direct_json" not in sql


def test_unknown_generated_plate_formatter_shape_is_rejected(tmp_path):
    """生成formatterの未知分岐をsuffix抽出で無視しない。"""
    display = tmp_path / "backend/domain/play-export-display.model.json"
    display.parent.mkdir(parents=True)
    display.write_bytes(
        (_ROOT / "backend/domain/play-export-display.model.json").read_bytes()
    )
    source = tmp_path / "backend/src/pitchlog/exports/generated/coordinate_transform.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        (_ROOT / "backend/src/pitchlog/exports/generated/coordinate_transform.py")
        .read_text()
        .replace("return label", 'return "unknown"')
    )
    with pytest.raises(ValueError, match="打席表示原典"):
        direct.plate_display_sql(tmp_path)
