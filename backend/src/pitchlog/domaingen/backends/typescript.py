"""中間表現から TypeScript のラッパー専用 fragment を生成する。"""

from __future__ import annotations

import json

from pitchlog.domaingen.backends.common import (
    BackendGenerationError,
    BackendInput,
    GeneratedArtifact,
    Language,
    artifact,
)


def generate(source: BackendInput) -> GeneratedArtifact:
    """一つの中間表現段から TypeScript fragment を生成する。

    Args:
        source: 計算宣言とコア由来の段別 hash。

    Returns:
        export を持たず、ラッパー印を要求する TypeScript fragment。
    """
    if "typedProgram" in source.declaration:
        from pitchlog.domaingen.pregen_checks import validate_typed_program

        program = source.declaration["typedProgram"]
        if not isinstance(program, dict):
            raise ValueError("typedProgramの閉型が不正です")
        validate_typed_program(program)
        if (source.target_class, source.stage) != ("alpha", "python"):
            raise BackendGenerationError(
                f"typed TypeScriptの対象外段: {source.target_class}/{source.stage}"
            )
        return artifact(
            source,
            Language.TYPESCRIPT,
            generate_typed_facts(program, source.source_hash),
        )
    calculation_id = json.dumps(source.calculation_id, ensure_ascii=False)
    source_hash = json.dumps(source.source_hash)
    content = "\n".join(
        [
            "const wrapper = globalThis as "
            "{ __PITCHLOG_GENERATED_WRAPPER__?: boolean };",
            "if (wrapper.__PITCHLOG_GENERATED_WRAPPER__ !== true) {",
            '  throw new Error("生成物はラッパー経由でのみ使用できます");',
            "}",
            f"const PITCHLOG_SOURCE_HASH = {source_hash};",
            "function pitchlogGenerated(",
            "  context: Readonly<Record<string, unknown>>,",
            "): unknown {",
            f"  return {{ calculationId: {calculation_id}, context }};",
            "}",
            "",
        ]
    )
    return artifact(source, Language.TYPESCRIPT, content)


def generate_typed_facts(program, source_hash: str) -> str:
    """同じ閉宣言からBigIntを使う遷移寄与codeを生成する。"""
    from pitchlog.domaingen.core import typed_expression
    from pitchlog.domaingen.formatter import integer_target

    def expr(node, items=None):
        """検査済み式をこの言語へ下げる。"""
        return typed_expression(node, "typescript", program["fields"], items)

    def quoted(value):
        """文字列を安全なliteralへ符号化する。"""
        return json.dumps(value, ensure_ascii=False)

    lines = [
        "/** 自動生成。単一遷移だけを計算し、認可/全game集計を行わない。 */",
        f"export const SOURCE_MODEL_HASH = {quoted(source_hash)};",
        'if ((globalThis as { __PITCHLOG_GENERATED_WRAPPER__?: boolean }).__PITCHLOG_GENERATED_WRAPPER__ !== true) throw new Error("登録wrapperが必要です");',  # noqa: E501 — 生成targetのliteral
        integer_target("typescript", source_hash),
        """
class MissingProjectionField extends Error {}
function _p(owner: unknown, path: string): unknown {
  for (const part of path.split('.')) {
    if (owner === null) return null;
    if (typeof owner !== "object" || Array.isArray(owner)) throw new Error("閉入力の親型違い");
    if (!Object.hasOwn(owner, part)) throw new MissingProjectionField("閉入力のfield不足");
    owner = (owner as Record<string, unknown>)[part];
  }
  return owner;
}
function _n(value: unknown): bigint { return parseCount(value); }

function _check(value: unknown, kind: string, nullable: boolean, minimum: string|null=null, maximum: string|null=null, allowed: readonly unknown[]|null=null): void {
  if (value === null && nullable) return;
  if (allowed !== null && !allowed.includes(value)) throw new Error("未知enum");
  if (kind === "integer") {
    if (typeof value === "string" && maximum !== null && value.length > maximum.length) throw new Error("既有限field上限");
    const n=_n(value);
    if (minimum!==null && n<_n(minimum)) throw new Error("整数下限");
    if (maximum!==null && n>_n(maximum)) throw new Error("整数上限");
    return;
  }
  if (kind === "boolean" && typeof value === "boolean") return;
  if (kind === "string" && typeof value === "string") return;
  throw new Error("閉入力の型違い");
}
function _checked_ref(owner: unknown, path: string, kind: string, nullable: boolean, minimum: string|null, maximum: string|null, allowed: readonly unknown[]|null): unknown {
  const value=_p(owner,path); _check(value,kind,nullable,minimum,maximum,allowed); return value;
}
function _lookup(values: Readonly<Record<string, bigint>>, value: unknown): bigint {
  if (typeof value !== "string" || !Object.hasOwn(values, value)) throw new Error("未知enum");
  return values[value]!;
}
type Credit = { player_id: string; quantity: string };
type Metric = { state: "available" | "source_unavailable"; value: string | null; display: string | null; reason: string | null; credits: Credit[] };
function _appendCredit(credits: Credit[], player: string, amount: bigint): void {
  for (const credit of credits) {
    if (credit.player_id === player) { credit.quantity=addCounts(credit.quantity,amount); return; }
  }
  credits.push({player_id:player,quantity:formatCount(amount)!});
}
function _zero(): Metric { return {state:"available",value:"0",display:"0",reason:null,credits:[]}; }
function _missing(reason: "MISSING_OBSERVATION" | "MISSING_ATTRIBUTION"="MISSING_OBSERVATION"): Metric { return {state:"source_unavailable",value:null,display:null,reason,credits:[]}; }
export function addCounts(left: unknown, right: unknown): string { return formatCount(_n(left)+_n(right))!; }
export function eventFacts(event: unknown, requestedMetrics?: readonly string[]) {
""",  # noqa: E501 — 生成targetのliteral
    ]
    names = [m["id"] for m in program["metrics"]]
    lines.extend(
        [
            f"  const knownMetrics={quoted(names)};",
            "  if (requestedMetrics !== undefined && (!Array.isArray(requestedMetrics) || requestedMetrics.length>26 || requestedMetrics.some(x=>typeof x!=='string' || !knownMetrics.includes(x)) || new Set(requestedMetrics).size!==requestedMetrics.length)) throw new Error('primitive射影の有限型違い');",  # noqa: E501 — 生成targetのliteral
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
                "  {",
                f"    const record=_p(event,{quoted(record)});",
                '    if (record===null || typeof record!=="object" || '
                'Array.isArray(record)) throw new Error("閉record型違い");',
                "    let seen=0;",
                "    for (const key in record) {",
                "      if (!Object.hasOwn(record,key)) continue;",
                f"      if (++seen>{len(names)} || !{quoted(names)}.includes(key)) "
                "throw new Error('未知field');",
                "    }",
                f"    if (seen!=={len(names)}) throw new Error('不足field');",
                "  }",
            ]
        )
    validation_start = len(lines)
    for path, field in program["fields"].items():
        lines.append(
            f"  _check(_p(event, {quoted(path)}), {quoted(field['type'])}, {quoted(field['nullable'])}, {quoted(str(field['minimum']) if 'minimum' in field else None)}, {quoted(str(field['maximum']) if 'maximum' in field else None)}, {quoted(field.get('enum'))});"  # noqa: E501 — 生成targetのliteral
        )
    for name, coll in program["collections"].items():
        lines.extend(
            [
                "  {",
                f"    const collection = _p(event, {quoted(name)});",
                "    if (collection !== null) {",
                f"      if (!Array.isArray(collection) || collection.length > {coll['maximumItems']}) throw new Error('有限collection上限');",  # noqa: E501 — 生成targetのliteral
                "      for (const item of collection) {",
            ]
        )
        for path, field in coll["fields"].items():
            lines.append(
                f"        _check(_p(item, {quoted(path)}), {quoted(field['type'])}, {quoted(field['nullable'])});"  # noqa: E501 — 生成targetのliteral
            )
        lines.extend(["      }", "    }", "  }"])
    eager = lines[validation_start:]
    lines[validation_start:] = (
        ["  if (requestedMetrics === undefined) {"]
        + ["  " + line for line in eager]
        + ["  }"]
    )
    names = [m["id"] for m in program["metrics"]]
    lines.extend(
        [
            "  const metrics: Record<string, Metric> = {};",
            f"  for (const name of {quoted(names)}) if (requestedMetrics===undefined || requestedMetrics.includes(name)) metrics[name]=_zero();",  # noqa: E501 — 生成targetのliteral
            f"  const selected = {expr(program['selection'])};",
            "  if (selected) {",
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
        lines.extend(
            [
                f"    if (requestedMetrics===undefined || requestedMetrics.includes({quoted(mid)})) {{",  # noqa: E501 — 生成targetのliteral
                f"      if (!({expr(metric['available'])})) metrics[{quoted(mid)}]=_missing();",  # noqa: E501 — 生成targetのliteral
                "      else {",
                "        let quantity=0n;",
                "        const credits: Credit[]=[];",
                "        let missing=false;",
            ]
        )
        if relation in program["collections"]:
            lines.extend(
                [
                    f"        const collection=_p(event,{quoted(relation)});",
                    "        if (collection === null) missing=true;",
                    "        else {",
                    f'          if (!Array.isArray(collection) || collection.length>{program["collections"].get(relation, {}).get("maximumItems", 0)}) throw new Error("collection型違い");',  # noqa: E501 — 生成targetのliteral
                    "          for (const item of collection) {",
                    f"            if ({expr(metric['guard'], items)}) {{",
                ]
            )
            indent = "              "
        else:
            lines.append(f"        if ({expr(metric['guard'], items)}) {{")
            indent = "          "
        lines.extend(
            [
                indent + f"const amount=_n({expr(metric['quantity'], items)});",
                indent + f"const player={expr(metric['credit'], items)};",
                indent + 'if (amount > 0n && typeof player !== "string") missing=true;',
                indent + 'else if (amount > 0n && typeof player === "string") {',
                indent + "  quantity += amount;",
                indent + "  _appendCredit(credits,player,amount);",
                indent + "}",
                indent[:-2] + "}",
            ]
        )
        if relation in program["collections"]:
            lines.extend(["          }", "        }"])
        lines.extend(
            [
                f"        metrics[{quoted(mid)}]=missing ? _missing('MISSING_ATTRIBUTION') : {{state:'available',value:formatCount(quantity),display:formatCount(quantity),reason:null,credits}};",  # noqa: E501 — 生成targetのliteral
                "      }",
                "    }",
            ]
        )
        body = lines[metric_start:]
        lines[metric_start:] = (
            ["    try {"]
            + ["  " + line for line in body]
            + [
                "    } catch (error) {",
                "      if (requestedMetrics === undefined || !(error instanceof MissingProjectionField)) throw error;",  # noqa: E501 — 生成targetのliteral
                f"      metrics[{quoted(mid)}]=_missing();",
                "    }",
            ]
        )
    pa = program["paProjection"]
    lines.extend(
        [
            "  }",
            "  let paRow: Record<string, unknown> | null=null;",
            f"  if (requestedMetrics===undefined && selected && {expr(pa['guard'])}) {{",  # noqa: E501 — 生成targetのliteral
            "    paRow={",
        ]
    )
    for key, value in pa["fields"].items():
        lines.append(f"      {quoted(key)}:{expr(value)},")
    lines.append("    };")
    for key, mid in pa["metricFields"].items():
        lines.append(f"    paRow[{quoted(key)}]=metrics[{quoted(mid)}]!.value;")
        lines.append(
            f"    paRow[{quoted(key + '_state')}]=metrics[{quoted(mid)}]!.state;"
        )
    lines.extend(
        [
            "  }",
            f"  return {{metrics,pa_row:paRow,source_event_id:_p(event,'source.source_event_id'),selected,pending:{quoted(program['pendingDecisions'])} as const}};",  # noqa: E501 — 生成targetのliteral
            "}",
        ]
    )
    return "\n".join(lines) + "\n"
