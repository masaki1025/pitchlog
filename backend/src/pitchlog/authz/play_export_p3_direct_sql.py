"""保存済みCSV表示原典をSQL比較式へ写す。野球計算・任意Python実行はしない。"""

# SQL生成literalの字面を保ち、改行による期待文字列変更を避ける。
# ruff: noqa: E501

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pitchlog.domaingen.play_export_score import _completion_sql
from pitchlog.exports.play_rows import CSV_HEADERS

_PINS = {
    "_native_before": "bb8a54e657f7a9ae557a3fac5f551326722b0c6c07b3030086f20ca0f80e7460",
    "_native_completion": "5693210297d613b57819a0772032e41cfd8f8e181c6aebebbdb4c214d995d565",
}


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class _JsonPath:
    parts: tuple[str, ...]

    def text(self) -> str:
        return "ctx.payload#>>" + _literal("{" + ",".join(self.parts) + "}")


def _expression(node: ast.expr, bindings: dict):
    """閉じた参照・定数・条件式だけを翻訳し、call/任意属性を評価しない。"""
    if isinstance(node, ast.Name) and node.id in bindings:
        return bindings[node.id]
    if isinstance(node, ast.Constant) and type(node.value) is str:
        return _literal(node.value)
    if isinstance(node, ast.Constant) and node.value is None:
        return "NULL"
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        base = _expression(node.value, bindings)
        key = node.slice.value
        if isinstance(base, _JsonPath) and type(key) is str:
            return _JsonPath((*base.parts, key))
        if type(base) is tuple and type(key) is int and 0 <= key < len(base):
            return base[key]
    if isinstance(node, ast.IfExp):
        return (
            "CASE WHEN "
            + _text(_expression(node.test, bindings))
            + " THEN "
            + _text(_expression(node.body, bindings))
            + " ELSE "
            + _text(_expression(node.orelse, bindings))
            + " END"
        )
    if (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and len(node.comparators) == 1
    ):
        return (
            "("
            + _text(_expression(node.left, bindings))
            + "="
            + _text(_expression(node.comparators[0], bindings))
            + ")"
        )
    raise ValueError("P3 CSV表示原典の未知AST")


def _text(value) -> str:
    if isinstance(value, _JsonPath):
        return value.text()
    if type(value) is str:
        return value
    raise ValueError("P3 CSV表示原典の未知値型")


def _segment(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    if segment is None:
        raise ValueError("P3 CSV原典のsource範囲が不明")
    return segment


def _functions(root: Path) -> dict[str, ast.FunctionDef]:
    source = (root / "backend/src/pitchlog/exports/record_projection.py").read_text()
    tree = ast.parse(source)
    selected = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in _PINS
    }
    if set(selected) != set(_PINS) or any(
        hashlib.sha256(_segment(source, node).encode()).hexdigest() != _PINS[name]
        for name, node in selected.items()
    ):
        raise ValueError("P3 CSV表示原典の固定AST不一致")
    return selected


def _named_assignment(function: ast.FunctionDef, name: str) -> ast.expr:
    values = [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name
    ]
    if len(values) != 1:
        raise ValueError("P3 CSV表示原典の代入が一意でない")
    return values[0]


def _dict_columns(node: ast.expr, bindings: dict) -> dict[int, str]:
    if not isinstance(node, ast.Dict):
        raise ValueError("P3 CSV表示原典の列辞書が不正")
    result = {}
    for key, value in zip(node.keys, node.values, strict=True):
        if (
            not isinstance(key, ast.Subscript)
            or not isinstance(key.value, ast.Name)
            or key.value.id != "_HEADER"
            or not isinstance(key.slice, ast.Constant)
            or type(key.slice.value) is not int
        ):
            raise ValueError("P3 CSV表示原典の未知列")
        result[key.slice.value] = _text(_expression(value, bindings))
    return result


def state_display_expressions(root: Path) -> dict[int, str]:
    """既v3表示helperの参照/ラベルをそのままSQLへ投影する。"""
    functions = _functions(root)
    before = _JsonPath(("calculation", "request", "t1", "before", "stateFields"))
    bindings = {
        "before": before,
        "score": _JsonPath((*before.parts, "state.score")),
        "half": _JsonPath((*before.parts, "state.half")),
        "orders": _JsonPath(
            ("calculation", "request", "t1", "before", "battingOrderBySide")
        ),
    }
    field_nodes = _named_assignment(functions["_native_before"], "fields")
    if not isinstance(field_nodes, ast.Tuple):
        raise ValueError("P3 CSV表示原典のfieldsが不正")
    bindings["fields"] = tuple(_expression(n, bindings) for n in field_nodes.elts)
    result = _dict_columns(
        _named_assignment(functions["_native_before"], "result"), bindings
    )
    for node in ast.walk(functions["_native_before"]):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        key = node.targets[0]
        if (
            isinstance(key, ast.Subscript)
            and isinstance(key.value, ast.Name)
            and key.value.id == "result"
            and isinstance(key.slice, ast.Subscript)
            and isinstance(key.slice.slice, ast.Constant)
            and type(key.slice.slice.value) is int
            and key.slice.slice.value in (73, 74)
            and isinstance(node.value, ast.Subscript)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "orders"
        ):
            result[key.slice.slice.value] = _text(_expression(node.value, bindings))
    model = json.loads(
        (root / "backend/domain/play-export-score.model.json").read_bytes()
    )
    complete = _completion_sql(model["scoreboard"]["completeProfiles"]).replace(
        "b.payload", "ctx.payload"
    )
    bindings = {
        "pa_ended": "(ctx.payload#>'{calculation,response,value,t1,plateAppearanceEnded}'='true'::jsonb)",
        "game_ended": "(ctx.payload#>'{calculation,response,value,t1,after,stateFields,state.gameEnded}'='true'::jsonb)",
        "half_completed": "(" + complete + "='true'::jsonb)",
    }
    # bool分岐の唯一代入。not-applicableは今回P3 v3通常/打球には受け入れない。
    candidates = [
        n.value
        for n in ast.walk(functions["_native_completion"])
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.IfExp)
        and any(isinstance(t, ast.Name) and t.id == "pa_display" for t in n.targets)
    ]
    if len(candidates) != 1:
        raise ValueError("P3 CSV完了表示原典が不正")
    bindings["pa_display"] = _expression(candidates[0], bindings)
    returns = [
        n.value
        for n in ast.walk(functions["_native_completion"])
        if isinstance(n, ast.Return)
    ]
    if len(returns) != 1 or returns[0] is None:
        raise ValueError("P3 CSV完了表示のreturnが不正")
    result.update(_dict_columns(returns[0], bindings))
    if set(result) != set(range(10, 20)) | {73, 74}:
        raise ValueError("P3 CSV表示原典の列集合不一致")
    return result


def direct_validation_sql(root: Path) -> str:
    """保存済capsuleから動的列全値を検証するSQLを生成する。"""
    headers = CSV_HEADERS["plays.csv"]
    source = (root / "backend/src/pitchlog/exports/record_projection.py").read_text()
    nodes = [
        n.value
        for n in ast.parse(source).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_NAT" for t in n.targets)
    ]
    if (
        len(nodes) != 1
        or not isinstance(nodes[0], ast.Call)
        or not isinstance(nodes[0].func, ast.Attribute)
        or not isinstance(nodes[0].func.value, ast.Name)
        or nodes[0].func.value.id != "re"
        or nodes[0].func.attr != "compile"
        or len(nodes[0].args) != 1
        or nodes[0].keywords
        or not isinstance(nodes[0].args[0], ast.Constant)
        or type(nodes[0].args[0].value) is not str
    ):
        raise ValueError("P3 CSV原典NATの未知AST")
    natural_pattern = _literal("^" + nodes[0].args[0].value)
    checks = []
    for index, expression in sorted(state_display_expressions(root).items()):
        if index in {10, 12, 13, 14, 15, 16, 73, 74}:
            checks.append(
                f" IF pg_catalog.jsonb_typeof({expression.replace('#>>', '#>')}) IS DISTINCT FROM 'string'"
                f" OR ({expression}) !~ {natural_pattern} THEN\n"
                " RAISE EXCEPTION 'P3 CSV state display type unavailable' USING ERRCODE='42501'; END IF;"
            )
        checks.append(
            f" IF p_direct_json->{_literal(headers[index])} IS DISTINCT FROM "
            f"pg_catalog.to_jsonb({expression}) THEN\n"
            " RAISE EXCEPTION 'P3 CSV saved state display mismatch' USING ERRCODE='42501'; END IF;"
        )
    completion_model = json.loads(
        (root / "backend/domain/play-export-score.model.json").read_bytes()
    )
    completion = _completion_sql(
        completion_model["scoreboard"]["completeProfiles"]
    ).replace("b.payload", "ctx.payload")
    guard = (
        """ IF pg_catalog.jsonb_typeof(ctx.payload#>'{calculation,response,value,t1,plateAppearanceEnded}') IS DISTINCT FROM 'boolean'
 OR pg_catalog.jsonb_typeof(ctx.payload#>'{calculation,response,value,t1,after,stateFields,state.gameEnded}') IS DISTINCT FROM 'boolean'
 OR ctx.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'
 OR pg_catalog.jsonb_typeof("""
        + completion
        + """) IS DISTINCT FROM 'boolean' THEN
 RAISE EXCEPTION 'P3 CSV state display source unavailable' USING ERRCODE='42501'; END IF;
"""
    )
    state_prefix = "ctx.payload#>'{calculation,request,t1,before,stateFields}'"
    orders = "ctx.payload#>'{calculation,request,t1,before,battingOrderBySide}'"
    score = "ctx.payload#>'{calculation,request,t1,before,stateFields,state.score}'"
    half = "ctx.payload#>>'{calculation,request,t1,before,stateFields,state.half}'"
    guard += f""" IF pg_catalog.jsonb_typeof({state_prefix}) IS DISTINCT FROM 'object'
 OR ({half}) IS NULL OR ({half}) NOT IN ('top','bottom')
 OR pg_catalog.jsonb_typeof({score}) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof({orders}) IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C") FROM pg_catalog.jsonb_object_keys({score}) k)
 IS DISTINCT FROM ARRAY['away','home']::text[]
 OR (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C") FROM pg_catalog.jsonb_object_keys({orders}) k)
 IS DISTINCT FROM ARRAY['away','home']::text[] THEN
 RAISE EXCEPTION 'P3 CSV before display source unavailable' USING ERRCODE='42501'; END IF;
"""
    return guard + "\n".join(checks)


def plate_display_sql(root: Path) -> str:
    """既唯一display modelの有限文字列写像をSQLへ生成する。"""
    model = json.loads(
        (root / "backend/domain/play-export-display.model.json").read_bytes()
    )
    spec = model["plateResultDisplay"]
    if (
        set(spec) != {"kind", "aliases", "fielderFormats", "otherwise", "unfinished"}
        or spec["kind"] != "finite-legacy-label"
        or spec["otherwise"] != "source-label"
        or spec["unfinished"] != "null"
        or type(spec["aliases"]) is not dict
        or type(spec["fielderFormats"]) is not dict
    ):
        raise ValueError("P3 CSV打席表示の未知宣言")
    source = (
        root / "backend/src/pitchlog/exports/generated/coordinate_transform.py"
    ).read_text()
    tree = ast.parse(source)
    functions = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "plate_result_display"
    ]
    if (
        len(functions) != 1
        or hashlib.sha256(_segment(source, functions[0]).encode()).hexdigest()
        != "ffe0a455880c92be20f2a5f3b245e8da3783ae711d9c43c66a0af06617f8e046"
    ):
        raise ValueError("P3 CSV打席表示原典が一意でない")
    lines = [
        n
        for n in ast.walk(functions[0])
        if isinstance(n, ast.JoinedStr)
        and len(n.values) == 2
        and isinstance(n.values[0], ast.FormattedValue)
        and isinstance(n.values[0].value, ast.Name)
        and n.values[0].value.id == "fielder"
        and isinstance(n.values[1], ast.Constant)
        and type(n.values[1].value) is str
    ]
    doubles = [
        n
        for n in ast.walk(functions[0])
        if isinstance(n, ast.IfExp)
        and isinstance(n.body, ast.Constant)
        and type(n.body.value) is str
        and isinstance(n.orelse, ast.Constant)
        and n.orelse.value == ""
    ]
    if len(lines) != 1 or len(doubles) != 1:
        raise ValueError("P3 CSV打席表示suffixの未知AST")
    line_node = lines[0].values[1]
    double_node = doubles[0].body
    assert isinstance(line_node, ast.Constant) and type(line_node.value) is str
    assert isinstance(double_node, ast.Constant) and type(double_node.value) is str
    formats = {
        "fielder-balltype": "display_fielder || display_ball_type",
        "fielder-balltype-double": "display_fielder || display_ball_type || "
        + _literal(double_node.value),
        "fielder-line-double": "display_fielder || " + _literal(line_node.value),
    }
    clauses = []
    for key, value in spec["aliases"].items():
        if type(key) is not str or type(value) is not str:
            raise ValueError("P3 CSV表示aliasの型が不正")
        clauses.append("WHEN " + _literal(key) + " THEN " + _literal(value))
    for key, kind in spec["fielderFormats"].items():
        if type(key) is not str or kind not in formats:
            raise ValueError("P3 CSV打席表示formatが未知")
        clauses.append("WHEN " + _literal(key) + " THEN " + formats[kind])
    h = CSV_HEADERS["plays.csv"]
    formatted_keys = ",".join(_literal(k) for k in spec["fielderFormats"])
    return f"""
 display_label:=CASE WHEN ctx.d1=ctx.target_d1 THEN ctx.replacement_label
 ELSE ctx.original_csv_json->>{_literal(h[45])} END;
 display_fielder:=ctx.play_row->>'raw_error_position';
 display_ball_type:=ctx.original_csv_json->>{_literal(h[48])};
 IF ctx.payload#>'{{calculation,response,value,t1,plateAppearanceEnded}}'='true'::jsonb THEN
 IF display_label IS NULL OR display_label='' OR
 (display_label IN ({formatted_keys}) AND (display_fielder IS NULL
 OR display_fielder !~ '^[1-9]$' OR (display_label<>{_literal(next(k for k, v in spec["fielderFormats"].items() if v == "fielder-line-double"))} AND (display_ball_type IS NULL OR display_ball_type='')))) THEN
 RAISE EXCEPTION 'P3 CSV plate display source unavailable' USING ERRCODE='42501'; END IF;
 display_plate:=CASE display_label {" ".join(clauses)} ELSE display_label END;
 ELSE display_plate:=NULL; END IF;
 IF p_direct_json->{_literal(h[61])} IS DISTINCT FROM COALESCE(pg_catalog.to_jsonb(display_plate),'null'::jsonb)
 OR p_direct_json->{_literal(h[62])} IS DISTINCT FROM COALESCE(pg_catalog.to_jsonb(display_plate),'null'::jsonb) THEN
 RAISE EXCEPTION 'P3 CSV plate display mismatch' USING ERRCODE='42501'; END IF;
"""


def input_origin_sql() -> str:
    """実capsule/item/ARTと旧通常originから、既codecの正準文字列を組む。"""
    h = CSV_HEADERS["plays.csv"]
    return f"""
 origin_json:=(ctx.original_csv_json->>{_literal(h[72])})::jsonb;
 WHILE origin_json->>'formatVersion'='play-export-input-origin-p3-v1' LOOP
 IF pg_catalog.jsonb_typeof(origin_json->'originalInputOrigin') IS DISTINCT FROM 'object' THEN
 RAISE EXCEPTION 'P3 CSV old input origin unavailable' USING ERRCODE='42501'; END IF;
 origin_json:=origin_json->'originalInputOrigin';
 END LOOP;
 IF origin_json->>'formatVersion' IS DISTINCT FROM 'play-export-input-origin-v1'
 OR origin_json->>'operationKind' IS DISTINCT FROM 'play_input'
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_each(origin_json) v
 WHERE pg_catalog.jsonb_typeof(v.value) IS DISTINCT FROM 'string')
 OR ctx.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'
 OR ctx.payload#>>'{{calculation,formatVersion}}' IS DISTINCT FROM 'play-prefix-calculation-v3'
 OR (ctx.payload#>>'{{calculation,artifactSha256}}') !~ '^[a-f0-9]{{64}}$'
 OR ctx.payload#>>'{{calculation,artifactSha256}}' IS NULL THEN
 RAISE EXCEPTION 'P3 CSV input origin source unavailable' USING ERRCODE='42501'; END IF;
 expected_origin:=pg_catalog.jsonb_build_object(
 'formatVersion','play-export-input-origin-p3-v1',
 'operationKind',CASE WHEN ctx.d1=ctx.target_d1 THEN 'play_change' ELSE 'play_input' END,
 'projectionKind','p3-current','sourceFormat',ctx.payload->>'formatVersion',
 'calculationFormat',ctx.payload#>>'{{calculation,formatVersion}}',
 'calculationArtifactSha256',ctx.payload#>>'{{calculation,artifactSha256}}',
 'sourceEventId',ctx.source_event_id::text,'capsuleId',ctx.capsule_id::text,
 'itemDigest',ctx.item_digest,'originalInputOrigin',origin_json);
 SELECT '{{'||pg_catalog.string_agg(pg_catalog.to_jsonb(x.key)::text||':'||
 CASE WHEN x.key='originalInputOrigin' THEN
 (SELECT '{{'||pg_catalog.string_agg(pg_catalog.to_jsonb(y.key)::text||':'||y.value::text,
 ',' ORDER BY y.key COLLATE "C")||'}}' FROM pg_catalog.jsonb_each(origin_json) y)
 ELSE x.value::text END,',' ORDER BY x.key COLLATE "C")||'}}'
 INTO STRICT expected_origin_text FROM pg_catalog.jsonb_each(expected_origin) x;
 IF p_direct_json->>{_literal(h[72])} IS DISTINCT FROM expected_origin_text THEN
 RAISE EXCEPTION 'P3 CSV input origin mismatch' USING ERRCODE='42501'; END IF;
"""
