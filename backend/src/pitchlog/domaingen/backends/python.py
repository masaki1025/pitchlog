"""中間表現から Python のラッパー専用 fragment を生成する。"""

from __future__ import annotations

from pitchlog.domaingen.backends.common import (
    BackendGenerationError,
    BackendInput,
    GeneratedArtifact,
    Language,
    artifact,
)

_WRAPPER_MODULE_NAME = "__pitchlog_generated_wrapper__"


def generate(source: BackendInput) -> GeneratedArtifact:
    """一つの中間表現段から Python fragment を生成する。

    Args:
        source: 計算宣言とコア由来の段別 hash。

    Returns:
        直接 import を拒否する Python fragment。
    """
    if "typedProgram" in source.declaration:
        from pitchlog.domaingen.pregen_checks import validate_typed_program

        program = source.declaration["typedProgram"]
        if not isinstance(program, dict):
            raise ValueError("typedProgramの閉型が不正です")
        validate_typed_program(program)
        if (source.target_class, source.stage) == ("alpha", "python"):
            content = generate_typed_facts(program, source.source_hash)
        elif (source.target_class, source.stage) == ("beta-1-5", "typed-receiver"):
            content = generate_typed_receiver(program, source.source_hash)
        else:
            raise BackendGenerationError(
                f"typed Pythonの対象外段: {source.target_class}/{source.stage}"
            )
        return artifact(source, Language.PYTHON, content)
    lines = [
        f"if __name__ != {_WRAPPER_MODULE_NAME!r}:",
        "    raise ImportError('生成物はラッパー経由でのみ使用できます')",
        f"_PITCHLOG_SOURCE_HASH = {source.source_hash!r}",
        "",
    ]
    if source.target_class == "beta-7":
        lines.extend(
            [
                "def _pitchlog_generated(row, enum_display_map):",
                "    value = row['value']",
                "    return enum_display_map[value]",
            ]
        )
    else:
        lines.extend(
            [
                "def _pitchlog_generated(context):",
                "    return {",
                f"        'calculationId': {source.calculation_id!r},",
                "        'context': dict(context),",
                "    }",
            ]
        )
    return artifact(source, Language.PYTHON, "\n".join(lines) + "\n")


def generate_typed_facts(program, source_hash: str) -> str:
    """閉型付きmodelから遷移一件の実行codeを直接生成する。"""
    from pitchlog.domaingen.core import typed_expression
    from pitchlog.domaingen.formatter import integer_target

    def expr(node, items=None):
        """検査済み式をこの言語へ下げる。"""
        return typed_expression(node, "python", program["fields"], items)

    lines = [
        '"""自動生成。単一遷移の寄与のみ。真正sourceの検証は呼出側。"""',
        f"SOURCE_MODEL_HASH = {source_hash!r}",
        'if __name__ != "__pitchlog_generated_wrapper__":',
        '    raise ImportError("生成targetは登録wrapper経由だけです")',
        integer_target("python", source_hash),
        '''

class MissingProjectionField(ValueError):
    """有限射影で真正観測がまだ供給されないfield。"""


def _p(owner, path):
    for part in path.split('.'):
        if owner is None:
            return None
        if type(owner) is not dict:
            raise ValueError("閉入力の親型が不正です")
        if part not in owner:
            raise MissingProjectionField("閉入力のfieldが不足しています")
        owner = owner[part]
    return owner


def _n(value):
    return parse_count(value)


def _check(value, kind, nullable, minimum=None, maximum=None, allowed=None):
    if value is None and nullable:
        return
    if allowed is not None and value not in allowed:
        raise ValueError("未知のenum値です")
    if kind == "integer":
        if type(value) is str and maximum is not None and len(value) > len(maximum):
            raise ValueError("既有限整数fieldの変換前上限違反")
        number = _n(value)
        if minimum is not None and number < _n(minimum):
            raise ValueError("整数範囲の下限違反")
        if maximum is not None and number > _n(maximum):
            raise ValueError("整数範囲の上限違反")
    elif kind == "boolean":
        if type(value) is not bool:
            raise ValueError("booleanが必要です")
    elif kind == "string":
        if type(value) is not str:
            raise ValueError("文字列が必要です")
    else:
        raise ValueError("未知の入力型です")


def _checked_ref(owner, path, kind, nullable, minimum, maximum, allowed):
    value = _p(owner, path)
    _check(value, kind, nullable, minimum, maximum, allowed)
    return value


def _append_credit(credits, player, amount):
    for credit in credits:
        if credit["player_id"] == player:
            credit["quantity"] = add_counts(credit["quantity"], amount)
            return
    credits.append({"player_id": player, "quantity": format_count(amount)})


def _zero():
    return {"state": "available", "value": "0", "display": "0", "reason": None, "credits": []}


def _missing(reason="MISSING_OBSERVATION"):
    return {"state": "source_unavailable", "value": None, "display": None, "reason": reason, "credits": []}


def add_counts(left, right):
    """生成された整数add primitive（全イベント畳込み入口ではない）。"""
    return format_count(_n(left) + _n(right))


def _pitchlog_generated(event, requested_metrics=None):
    """正規providerが検証した単一遷移を受ける。認可を代行しない。"""
''',  # noqa: E501 — 生成targetのliteral
    ]
    names = [m["id"] for m in program["metrics"]]
    lines.extend(
        [
            f"    known_metrics = {names!r}",
            "    if requested_metrics is not None:",
            "        if type(requested_metrics) not in (list, tuple) or len(requested_metrics)>26:",  # noqa: E501 — 生成targetのliteral
            "            raise ValueError('primitive射影の有限型違い')",
            "        if any(type(x) is not str or x not in known_metrics for x in requested_metrics):",  # noqa: E501 — 生成targetのliteral
            "            raise ValueError('未知primitive射影')",
            "        if len(set(requested_metrics)) != len(requested_metrics):",
            "            raise ValueError('primitive射影の重複')",
        ]
    )
    for record in program["closedRecords"]:
        names = [
            path[len(record) + 1 :]
            for path in program["fields"]
            if path.startswith(record + ".")
        ]
        lines.extend(
            [
                f"    record = _p(event, {record!r})",
                f"    if type(record) is not dict or len(record) != {len(names)} "
                f"or any(key not in record for key in {tuple(names)!r}):",
                '        raise ValueError("閉recordの未知/不足fieldです")',
            ]
        )
    validation_start = len(lines)
    for path, kind in program["fields"].items():
        lines.append(
            f"    _check(_p(event, {path!r}), {kind['type']!r}, {kind['nullable']!r}, {str(kind['minimum']) if 'minimum' in kind else None!r}, {str(kind['maximum']) if 'maximum' in kind else None!r}, {kind.get('enum')!r})"  # noqa: E501 — 生成targetのliteral
        )
    for name, coll in program["collections"].items():
        lines.extend(
            [
                f"    collection = _p(event, {name!r})",
                "    if collection is not None:",
                f"        if type(collection) is not list or len(collection) > {coll['maximumItems']}:",  # noqa: E501 — 生成targetのliteral
                '            raise ValueError("遷移内collectionの有限上限が不正です")',
                "        for item in collection:",
            ]
        )
        for path, kind in coll["fields"].items():
            lines.append(
                f"            _check(_p(item, {path!r}), {kind['type']!r}, {kind['nullable']!r})"  # noqa: E501 — 生成targetのliteral
            )
    eager = lines[validation_start:]
    lines[validation_start:] = ["    if requested_metrics is None:"] + [
        "    " + line for line in eager
    ]
    names = [m["id"] for m in program["metrics"]]
    lines.extend(
        [
            f"    metrics = {{name: _zero() for name in {names!r} if requested_metrics is None or name in requested_metrics}}",  # noqa: E501 — 生成targetのliteral
            f"    selected = {expr(program['selection'])}",
            "    if selected:",
        ]
    )
    for metric in program["metrics"]:
        metric_start = len(lines)
        mid, relation = metric["id"], metric["relation"]
        items = (
            program["collections"][relation]["fields"]
            if relation in program["collections"]
            else {}
        )
        guard = expr(metric["guard"], items)
        avail = expr(metric["available"])
        lines.extend(
            [
                f"        # {mid}",
                f"        if not ({avail}):",
                f"            metrics[{mid!r}] = _missing()",
                "        else:",
                "            quantity = 0",
                "            credits = []",
                "            missing = False",
            ]
        )
        if relation in program["collections"]:
            lines.extend(
                [
                    f"            collection = _p(event, {relation!r})",
                    "            if collection is None:",
                    "                missing = True",
                    "            else:",
                    f"                if type(collection) is not list or len(collection) > {program['collections'].get(relation, {}).get('maximumItems', 0)}:",  # noqa: E501 — 生成targetのliteral
                    "                    raise ValueError('遷移内collectionの有限上限違反')",  # noqa: E501 — 生成targetのliteral
                    "                for item in collection:",
                    f"                    if {guard}:",
                ]
            )
            indent = "                        "
        else:
            lines.append(f"            if {guard}:")
            indent = "                "
        lines.extend(
            [
                indent + f"amount = _n({expr(metric['quantity'], items)})",
                indent + f"player = {expr(metric['credit'], items)}",
                indent + "if amount and player is None:",
                indent + "    missing = True",
                indent + "elif amount:",
                indent + "    quantity += amount",
                indent + "    _append_credit(credits, player, amount)",
                f"            metrics[{mid!r}] = _missing('MISSING_ATTRIBUTION') if missing else {{'state': 'available', 'value': format_count(quantity), 'display': format_count(quantity), 'reason': None, 'credits': credits}}",  # noqa: E501 — 生成targetのliteral
            ]
        )
        body = lines[metric_start:]
        lines[metric_start:] = (
            [
                f"        if requested_metrics is None or {mid!r} in requested_metrics:",  # noqa: E501 — 生成targetのliteral
                "            try:",
            ]
            + ["        " + line for line in body]
            + [
                "            except MissingProjectionField:",
                "                if requested_metrics is None:",
                "                    raise",
                f"                metrics[{mid!r}] = _missing()",
            ]
        )
    pa = program["paProjection"]
    lines.extend(
        [
            "    pa_row = None",
            f"    if requested_metrics is None and selected and {expr(pa['guard'])}:",
            "        pa_row = {",
        ]
    )
    for key, value in pa["fields"].items():
        lines.append(f"            {key!r}: {expr(value)},")
    lines.append("        }")
    for key, mid in pa["metricFields"].items():
        lines.append(f"        pa_row[{key!r}] = metrics[{mid!r}]['value']")
        lines.append(f"        pa_row[{key + '_state'!r}] = metrics[{mid!r}]['state']")
    lines.append(
        f"    return {{'metrics': metrics, 'pa_row': pa_row, 'source_event_id': _p(event, 'source.source_event_id'), 'selected': selected, {('decisions' if program['version'] == 2 else 'pending')!r}: {program['decisions' if program['version'] == 2 else 'pendingDecisions']!r}}}"  # noqa: E501 — 生成targetのliteral
    )
    if program["version"] == 2:
        lines.append(generate_derived_facts(program, source_hash))
    return "\n".join(lines) + "\n"


def generate_typed_receiver(program, source_hash: str) -> str:
    """SQLの単一行を厳密なtyped値へ受け、NULLを0にしない。"""
    from pitchlog.domaingen.formatter import integer_target

    names = [m["id"] for m in program["metrics"]]
    return f'''"""自動生成typed receiver。集計を持たない。"""
from decimal import Decimal

SOURCE_MODEL_HASH = {source_hash!r}
METRIC_IDS = {tuple(names)!r}
{integer_target("python", source_hash)}

class OutputBudgetExceeded(ValueError):
    """型の値域とは別の明示的な出力資源予算超過。"""


def receive_fact_row(row, *, maximum_integer_chars):
    """閉列集合のSQL一行を検証する。"""
    if type(maximum_integer_chars) is not int or maximum_integer_chars < 1:
        raise ValueError("出力資源予算を明示してください")
    if type(row) is not dict or set(row) != {{"metric_id", "state", "value"}}:
        raise ValueError("SQL受け口の閉型が不正です")
    if row["metric_id"] not in METRIC_IDS:
        raise ValueError("未知のprimitiveです")
    state, value = row["state"], row["value"]
    if state == "source_unavailable" and value is None:
        return {{**row, "display": None}}
    if state != "available" or value is None:
        raise ValueError("0/NULLと状態が一致しません")
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("有限SQL numericが必要です")
        if not value.is_zero() and value.adjusted() >= maximum_integer_chars:
            raise OutputBudgetExceeded("SQL numericの出力資源予算超過")
        if value != int(value):
            raise ValueError("SQL numericは有限整数が必要です")
        value = int(value)
    if type(value) is str and len(value) > maximum_integer_chars:
        raise OutputBudgetExceeded("整数文字列の出力資源予算超過")
    if type(value) is int and value.bit_length() > maximum_integer_chars * 4:
        raise OutputBudgetExceeded("整数の出力資源予算超過")
    rendered = format_count(value)
    if len(rendered) > maximum_integer_chars:
        raise OutputBudgetExceeded("整数の出力資源予算超過")
    return {{**row, "value": rendered, "display": rendered}}
'''


def generate_derived_facts(program, source_hash: str) -> str:
    """共通D1の有限集合とratio ASTだけから派生操作を生成する。"""
    from pitchlog.domaingen.core import rate_metric_dependencies, typed_rate_expression
    from pitchlog.domaingen.formatter import ratio_target

    names = tuple(m["id"] for m in program["metrics"])
    groups = program["namedScopes"]["groups"]
    lines = [
        ratio_target("python", source_hash),
        f"GAME_TYPE_SCOPES = {groups!r}",
        "def select_game_type_keys(named_category='all', raw_game_type_keys=None):",
        "    if type(named_category) is not str or named_category not in GAME_TYPE_SCOPES:",  # noqa: E501
        "        raise ValueError('未知のnamed categoryです')",
        "    keys = list(GAME_TYPE_SCOPES[named_category])",
        "    if raw_game_type_keys is not None and (type(raw_game_type_keys) is not list or any(type(x) is not str for x in raw_game_type_keys) or raw_game_type_keys != keys):",  # noqa: E501
        "        raise ValueError('named/raw集合が不一致です')",
        "    return keys",
        "def decision_metadata():",
        f"    return {program['decisions']!r}",
        "def derive_rates_with_components(metrics):",
        f"    values = _rate_inputs(metrics, {names!r})",
        "    results = {}",
        "    component_results = {}",
    ]
    for index, row in enumerate(program["derivedMetrics"]):
        parts = f"parts_{index}"
        component_items = [
            repr(c["id"])
            + ": "
            + typed_rate_expression(c["expression"], "python", parts)
            for c in row["components"]
        ]
        lines.append("    " + parts + " = {" + ", ".join(component_items) + "}")
        lines.append(f"    component_results[{row['id']!r}] = {{}}")
        for component in row["components"]:
            dependencies = rate_metric_dependencies({"components": [component]})
            component_id = component["id"]
            lines.append(
                f"    component_results[{row['id']!r}][{component_id!r}] = {{'state': 'available' if {parts}[{component_id!r}] is not None else 'source_unavailable', 'pair': {parts}[{component_id!r}], 'reason': None if {parts}[{component_id!r}] is not None else _rate_reason(metrics, {dependencies!r})}}"  # noqa: E501
            )
        expression = typed_rate_expression(row["expression"], "python", parts)
        dependencies = rate_metric_dependencies({"components": row["components"]})
        lines.append(
            f"    results[{row['id']!r}] = _rate_result({expression}, {parts}, {row['display']!r}, _rate_reason(metrics, {dependencies!r}))"  # noqa: E501
        )
    lines.extend(
        [
            "    return results, component_results",
            "def derive_rates(metrics):",
            "    return derive_rates_with_components(metrics)[0]",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_ratio_formatter(program, source_hash: str) -> str:
    """宣言済rate IDと表示bindingだけを公開formatterへ閉じる。"""
    from pitchlog.domaingen.formatter import ratio_formatter_target

    display = {row["id"]: row["display"] for row in program["derivedMetrics"]}
    return (
        ratio_formatter_target("python", source_hash)
        + "\n"
        + f"_RATE_DISPLAYS = {display!r}\n"
        + "def format_derived_rate(rate_id, value, components, reason='MISSING_OBSERVATION'):\n    if type(rate_id) is not str or rate_id not in _RATE_DISPLAYS:\n        raise ValueError('未知の派生率です')\n    return _rate_result(value, components, _RATE_DISPLAYS[rate_id], reason)\n"  # noqa: E501 — 生成target/固定SQLのliteral
    )


def generate_display_rates(rows, component_displays, source_hash: str) -> str:
    """T6専用の表示率だけを宣言から生成し、T5 artifactを変更しない。"""
    from pitchlog.domaingen.core import rate_metric_dependencies, typed_rate_expression
    from pitchlog.domaingen.formatter import rate_helpers_target

    lines = [
        "# generated=" + source_hash,
        '"""自動生成されたT6表示率。T5 artifactのfacts.pyを変更しない。"""',
        "",
        "from pitchlog.stats.generated.formatter import _rate_result, format_count",
        "",
        rate_helpers_target("python"),
        "_DISPLAY_RATES = " + repr({row["id"]: row["display"] for row in rows}),
        "_COMPONENT_DISPLAYS = " + repr(component_displays),
        "",
        "",
        "def format_innings(outs):",
        '    """アウト数をA-2の混合分数へ表示する。"""',
        "    if type(outs) is not int or outs < 0:",
        '        raise ValueError("投球回のアウト数は非負整数です")',
        "    whole, remainder = divmod(outs, 3)",
        '    return format_count(whole) + "回" + (format_count(remainder) + "/3" if remainder else "")',  # noqa: E501
        "",
        "",
        "def _display_result(value, components, display, reason):",
        '    """表示規則の先頭0だけを最後に適用し、比の値を再計算しない。"""',
        "    result = _rate_result(value, components, display, reason)",
        '    if result["state"] == "available" and any("format" in label for label in display["denominators"]):',  # noqa: E501
        "        labels = []",
        '        for label in display["denominators"]:',
        '            denominator = int(result["components"][label["component"]]["denominator"])',  # noqa: E501
        '            rendered = format_innings(denominator) if label.get("format") == "innings" else format_count(denominator)',  # noqa: E501
        '            labels.append(label["prefix"] + rendered + label["suffix"])',
        '        result = {**result, "display": result["formatted_value"] + "(" + "・".join(labels) + ")"}',  # noqa: E501
        '    if not display["leadingZero"] and result["formatted_value"] is not None:',
        '        original = result["formatted_value"]',
        '        formatted = original.removeprefix("0")',
        '        result = {**result, "formatted_value": formatted}',
        '        if result["display"] is not None:',
        "            result = {",
        "                **result,",
        '                "display": formatted + result["display"][len(original) :],',
        "            }",
        "    return result",
        "",
        "",
        "def _metric_value(metrics, key):",
        '    """十分統計の状態を表示率の入力へ写す。0と未取得を混同しない。"""',
        "    row = metrics[key]",
        '    if type(row) is not dict or row.get("state") not in (',
        '        "available",',
        '        "source_unavailable",',
        "    ):",
        '        raise ValueError("十分統計の状態が不正です")',
        '    if row["state"] == "source_unavailable":',
        "        return None",
        '    value = row.get("value")',
        "    if type(value) is not int or value < 0:",
        '        raise ValueError("十分統計の値が不正です")',
        "    return value",
        "",
        "",
        "def _reason(metrics, dependencies):",
        '    """最初の不足理由を保持し、未取得を0へ変えない。"""',
        "    for key in dependencies:",
        "        row = metrics[key]",
        '        if row["state"] == "source_unavailable":',
        '            return row.get("reason") or "MISSING_OBSERVATION"',
        '    return "MISSING_OBSERVATION"',
        "",
        "",
        "",
        "",
        'def format_component_rate(component_id, pair, reason="MISSING_OBSERVATION"):',
        '    """T5が計算した比componentを、T6の表示規則だけで表示する。"""',
        "    if type(component_id) is not str or component_id not in _COMPONENT_DISPLAYS:",  # noqa: E501
        '        raise ValueError("未知の表示componentです")',
        "    display = _COMPONENT_DISPLAYS[component_id]",
        "    result = _display_result(pair, {component_id: pair}, display, reason)",  # noqa: E501
        "    return result",
        "",
        "",
        "def derive_display_rates(metrics):",
        '    """宣言済みT6表示率を同じ生成済み表示規則で返す。"""',
        "    results = {}",
    ]
    for index, row in enumerate(rows):
        dependencies = rate_metric_dependencies({"components": row["components"]})
        lines.append(
            "    values = {"
            + ", ".join(
                f"{key!r}: _metric_value(metrics, {key!r})" for key in dependencies
            )
            + "}"
        )
        parts = f"parts_{index}"
        component_items = [
            repr(c["id"])
            + ": "
            + typed_rate_expression(c["expression"], "python", "values")
            for c in row["components"]
        ]
        lines.append("    " + parts + " = {" + ", ".join(component_items) + "}")
        expression = typed_rate_expression(row["expression"], "python", parts)
        lines.append(
            f"    results[{row['id']!r}] = _display_result({expression}, {parts}, _DISPLAY_RATES[{row['id']!r}], _reason(metrics, {dependencies!r}))"  # noqa: E501
        )
    lines.append("    return results")
    return "\n".join(lines) + "\n"


def generate_ratio_receiver(program, source_hash: str) -> str:
    """SQL比の全列をコピーし、未知/NULL不整合と非正準比を拒否する。"""
    components = {
        row["id"]: [c["id"] for c in row["components"]]
        for row in program["derivedMetrics"]
    }
    return (
        generate_ratio_formatter(program, source_hash)
        + f"\n_RATE_COMPONENTS = {components!r}\n"
        + r"""
def _receive_ratio_integer(value, budget):
    if value is None:
        return None
    if type(value) is Decimal:
        if not value.is_finite() or (
            not value.is_zero() and value.adjusted() >= budget
        ):
            raise OutputBudgetExceeded("比SQL numericの出力資源予算超過/非有限")
        if value != int(value):
            raise ValueError("比SQL numericは整数が必要です")
        value = int(value)
    if type(value) is str and len(value) > budget:
        raise OutputBudgetExceeded("比の出力資源予算超過")
    if type(value) is int and value.bit_length() > budget * 4:
        raise OutputBudgetExceeded("比の出力資源予算超過")
    rendered = format_count(value)
    if rendered is None or len(rendered) > budget:
        raise OutputBudgetExceeded("比の出力資源予算超過")
    return parse_count(rendered)


def receive_rate_row(row, *, maximum_integer_chars):
    if type(maximum_integer_chars) is not int or maximum_integer_chars < 1:
        raise ValueError("出力資源予算を明示してください")
    if (
        type(row) is not dict
        or type(row.get("rate_id")) is not str
        or row["rate_id"] not in _RATE_COMPONENTS
    ):
        raise ValueError("未知の派生率です")
    keys = _RATE_COMPONENTS[row["rate_id"]]
    expected = {"rate_id", "state", "value_state", "numerator", "denominator"} | {
        key + "_" + side for key in keys for side in ("numerator", "denominator")
    }
    if set(row) != expected:
        raise ValueError("比SQL受け口の閉型が不正です")
    value_n = _receive_ratio_integer(row["numerator"], maximum_integer_chars)
    value_d = _receive_ratio_integer(row["denominator"], maximum_integer_chars)
    components = {}
    for key in keys:
        n = _receive_ratio_integer(row[key + "_numerator"], maximum_integer_chars)
        d = _receive_ratio_integer(row[key + "_denominator"], maximum_integer_chars)
        if (n is None) != (d is None):
            raise ValueError("比componentのNULLが不整合です")
        components[key] = None if n is None else (n, d)
    if row["state"] == "source_unavailable" and row["value_state"] == "not_evaluated":
        if (
            value_n is not None
            or value_d is not None
            or any(pair is not None for pair in components.values())
        ):
            raise ValueError("source不足を0で補完できません")
        return format_derived_rate(row["rate_id"], None, components)
    if row["state"] != "available" or any(pair is None for pair in components.values()):
        raise ValueError("比SQLの状態が不一致です")
    if row["value_state"] == "undefined_zero_denominator":
        if (
            value_n is not None
            or value_d is not None
            or not any(
                pair is not None and pair[1] == 0 for pair in components.values()
            )
        ):
            raise ValueError("零除算とNULLが不一致です")
        return format_derived_rate(row["rate_id"], None, components)
    if (
        row["value_state"] != "defined"
        or value_n is None
        or value_d is None
        or value_d == 0
        or any(pair is not None and pair[1] == 0 for pair in components.values())
    ):
        raise ValueError("定義済み比の全値が不足しています")
    a, b = value_n, value_d
    while b:
        a, b = b, a % b
    if a != 1:
        raise ValueError("SQLの最終比は正準既約である必要があります")
    return format_derived_rate(row["rate_id"], (value_n, value_d), components)
"""
    )
