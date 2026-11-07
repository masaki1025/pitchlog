"""native26の実生成物と有限D11証跡を接続する。製品の計算を複製しない。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from pitchlog.domaincheck.cli import canonical_json, validate_asset
from pitchlog.domaincheck.collect_layers import (
    StageExpectation,
    TargetExpectation,
    _validate_stage_io,
    collect_pytest_junit,
)
from pitchlog.domaincheck.path_match import (
    ComparisonContract,
    FieldContract,
    PathKey,
    PathSubmission,
    compare_path_set,
)

MANIFEST = "backend/domain/stats-native-d11-manifest.json"
SOURCE_CASES = "docs/features/mvp-stats-primitives/primitive-cases.candidate.json"


# 承認済みfinite profile。可変D11 manifest自身を必須集合の正にしない。
# 内容hashは独立stats生成profileと実fileから束縛し、ここへ手書きしない。
_FINITE_MANIFEST_JSON = json.dumps(
    {
        "propertyCatalog": {
            "path": "backend/domain/stats-native-d11-property-catalog.json",
            "schema": ("backend/domain/stats-native-d11-property-catalog.schema.json"),
            "provenance": "ADR-003 D-11 3 層表 プロパティ層",
        },
        "calculations": [
            {
                "calculation": "native-event-facts26-v2",
                "source": {
                    "path": "backend/domain/play-export.model.json",
                    "provenance": "NFR-018 (b)② 差分の検出可能性",
                },
                "generated": [
                    {
                        "generatedId": "nativeFactsPy",
                        "path": "backend/src/pitchlog/stats/generated/facts.py",
                        "artifactKind": "python",
                    },
                    {
                        "generatedId": "nativeFactsTs",
                        "path": "frontend/src/lib/generated/statsPrimitives.ts",
                        "artifactKind": "typescript",
                    },
                ],
                "entrypoints": [
                    {
                        "entrypointId": "nativeFactsRuntime",
                        "module": "backend/src/pitchlog/stats/facts.py",
                        "symbol": "pitchlog.stats.facts._EVENT_FACTS",
                        "adapter": (
                            "backend/src/pitchlog/domaincheck/runners/stats_native.py"
                        ),
                    }
                ],
                "directTargets": [
                    {
                        "directTargetId": "nativeFactsPy",
                        "targetClass": "alpha",
                        "kind": "single",
                        "generated": "nativeFactsPy",
                        "invocation": {
                            "adapter": (
                                "backend/src/pitchlog/domainche"
                                "ck/runners/stats_native.py"
                            ),
                            "operation": "execute_python",
                        },
                    },
                    {
                        "directTargetId": "nativeFactsTs",
                        "targetClass": "alpha",
                        "kind": "single",
                        "generated": "nativeFactsTs",
                        "invocation": {
                            "adapter": (
                                "backend/src/pitchlog/domainche"
                                "ck/runners/stats_native.py"
                            ),
                            "operation": "execute_typescript",
                        },
                    },
                ],
                "comparison": {"mode": "lossless"},
                "normalization": [],
                "vectors": [
                    {
                        "vectorId": "nativeFactsVectors",
                        "calculation": "native-event-facts26-v2",
                        "path": ("contracts/stats/native_event_facts_d11_v2.json"),
                        "runner": "pytest",
                        "expectedValueSchema": "#/$defs/ExpectedValue",
                        "provenance": "NFR-018 (b)② 差分の検出可能性",
                    }
                ],
                "properties": [
                    {
                        "propertyId": "native-event-facts26-v2-invariant",
                        "propertyKind": "invariant",
                        "path": "backend/tests/stats/test_stats_native_d11.py",
                        "provenance": "NFR-018 (b)② 差分の検出可能性",
                    },
                    {
                        "propertyId": "native-event-facts26-v2-equivalence",
                        "propertyKind": "equivalence",
                        "path": "backend/tests/stats/test_stats_native_d11.py",
                        "provenance": "NFR-018 (b)② 差分の検出可能性",
                    },
                ],
                "mutation": [
                    {
                        "mutationId": "native-event-facts26-v2-mutations",
                        "target": "backend/domain/play-export.model.json",
                        "operators": ["increment-quantity", "change-missing-to-zero"],
                    }
                ],
            },
            {
                "calculation": "native-current-totals26-v2",
                "source": {
                    "path": "backend/domain/play-export.model.json",
                    "provenance": "NFR-018 (b)② 差分の検出可能性",
                },
                "generated": [
                    {
                        "generatedId": "nativeSql",
                        "path": (
                            "backend/src/pitchlog/exports/generated/play_primitives.sql"
                        ),
                        "artifactKind": "sql",
                    },
                    {
                        "generatedId": "nativeReceiver",
                        "path": ("backend/src/pitchlog/stats/generated/receiver.py"),
                        "artifactKind": "typed-receiver",
                    },
                    {
                        "generatedId": "nativeCountFormatter",
                        "path": ("backend/src/pitchlog/stats/generated/receiver.py"),
                        "artifactKind": "formatter",
                    },
                ],
                "entrypoints": [
                    {
                        "entrypointId": "nativeTotalsRuntime",
                        "module": "backend/src/pitchlog/repositories/stats.py",
                        "symbol": "read_primitive_totals",
                        "adapter": (
                            "backend/src/pitchlog/domaincheck/runners/stats_native.py"
                        ),
                    }
                ],
                "directTargets": [
                    {
                        "directTargetId": "nativeTotalsComposite",
                        "targetClass": "beta-1-5",
                        "kind": "composite",
                        "components": [
                            {"stage": "sql", "generated": "nativeSql"},
                            {"stage": "typed-receiver", "generated": "nativeReceiver"},
                            {"stage": "formatter", "generated": "nativeCountFormatter"},
                        ],
                        "invocation": {
                            "adapter": (
                                "backend/src/pitchlog/domainche"
                                "ck/runners/stats_native.py"
                            ),
                            "operation": "execute_sql_composite",
                        },
                    }
                ],
                "comparison": {"mode": "lossless"},
                "normalization": [
                    {
                        "normalizationId": "nativeNumericExact",
                        "kind": "exact-numeric-representation",
                    }
                ],
                "vectors": [
                    {
                        "vectorId": "nativeTotalsVectors",
                        "calculation": "native-current-totals26-v2",
                        "path": ("contracts/stats/native_current_totals_d11_v2.json"),
                        "runner": "pytest",
                        "expectedValueSchema": "#/$defs/ExpectedValue",
                        "provenance": "NFR-018 (b)② 差分の検出可能性",
                    }
                ],
                "properties": [
                    {
                        "propertyId": "native-current-totals26-v2-invariant",
                        "propertyKind": "invariant",
                        "path": "backend/tests/db/test_stats_native_d11.py",
                        "provenance": "NFR-018 (b)② 差分の検出可能性",
                    },
                    {
                        "propertyId": "native-current-totals26-v2-equivalence",
                        "propertyKind": "equivalence",
                        "path": "backend/tests/db/test_stats_native_d11.py",
                        "provenance": "NFR-018 (b)② 差分の検出可能性",
                    },
                ],
                "mutation": [
                    {
                        "mutationId": "native-current-totals26-v2-mutations",
                        "target": ("backend/src/pitchlog/stats/generated/receiver.py"),
                        "operators": ["replace-display", "break-stage-link"],
                    }
                ],
            },
        ],
        "displayBindings": [
            {
                "displayItem": "nativePrimitiveCountDisplay",
                "callsite": "backend/src/pitchlog/stats/generated/receiver.py",
                "formatter": "nativeCountFormatter",
                "provenance": "付録A-1 表示書式の共通規定",
            }
        ],
    }
)

_FINITE_PROPERTIES_JSON = json.dumps(
    {
        "schemaVersion": 1,
        "catalogId": "stats-native-d11-properties",
        "scope": ["native-event-facts26-v2", "native-current-totals26-v2"],
        "predicates": [
            {
                "propertyId": "native-event-facts26-v2-invariant",
                "propertyKind": "invariant",
                "authorityId": "NFR-018 (b)② 差分の検出可能性",
                "predicate": (
                    "全26metricの非負整数/全credit総量一致/kno"
                    "wn0とunavailable-nullを区別"
                ),
            },
            {
                "propertyId": "native-event-facts26-v2-equivalence",
                "propertyKind": "equivalence",
                "authorityId": "NFR-018 (b)② 差分の検出可能性",
                "predicate": "".join(
                    ("独立規範の全fieldと実生成Python/", "TypeScriptの全応答が完全一致")
                ),
            },
            {
                "propertyId": "native-current-totals26-v2-invariant",
                "propertyKind": "invariant",
                "authorityId": "NFR-018 (b)② 差分の検出可能性",
                "predicate": "実SQL全26行/全field/非負整数/NULL状態/重複なし",
            },
            {
                "propertyId": "native-current-totals26-v2-equivalence",
                "propertyKind": "equivalence",
                "authorityId": "NFR-018 (b)② 差分の検出可能性",
                "predicate": (
                    "真正RRRO製品読取と実SQL→生成receiver→実生成"
                    "formatterの最終表示まで完全一致"
                ),
            },
        ],
    }
)

_ALPHA_META_JSON = json.dumps(
    {
        "schemaVersion": 1,
        "calculation": "native-event-facts26-v2",
        "scope": "single observed event facts; native qualification is separate; "
        "other old/current cases remain original regression obligations",
    }
)

_BETA_NORMATIVE_JSON = json.dumps(
    {
        "schemaVersion": 1,
        "calculation": "native-current-totals26-v2",
        "scope": "current_open one real created game, same pitcher, three "
        "nonterminal pitches, no observation of runs/RBI/steal; not "
        "official-ended/season/27 metrics",
        "cases": [
            {
                "caseId": "native-three-pitch-current-open-pitcher26",
                "request": {
                    "native_variant": "ordinary-v1",
                    "event_count": 3,
                    "player_role": "pitcher",
                    "generation": "actual-live-generation",
                    "scope": "current_open",
                },
                "expected": {
                    "comparison": "exact",
                    "expected": [
                        {
                            "metric_id": "ab",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "bb",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "catcher_interference_reached",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "doubles",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "fielding_errors",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "h",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "hbp",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "hits_allowed",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "home_runs_allowed",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "hr",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "k",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "pa",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "pitch_count",
                            "state": "available",
                            "value": "3",
                            "display": "3",
                        },
                        {
                            "metric_id": "pitcher_bb",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "pitcher_hbp",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "pitcher_k",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "pitching_outs",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "rbi",
                            "state": "source_unavailable",
                            "value": None,
                            "display": None,
                        },
                        {
                            "metric_id": "runner_interference_reached",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "runs",
                            "state": "source_unavailable",
                            "value": None,
                            "display": None,
                        },
                        {
                            "metric_id": "runs_allowed",
                            "state": "source_unavailable",
                            "value": None,
                            "display": None,
                        },
                        {
                            "metric_id": "sf",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "sh",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "stolen_bases",
                            "state": "source_unavailable",
                            "value": None,
                            "display": None,
                        },
                        {
                            "metric_id": "total_bases",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                        {
                            "metric_id": "triples",
                            "state": "available",
                            "value": "0",
                            "display": "0",
                        },
                    ],
                    "provenance": "NFR-018 (b)② 差分の検出可能性",
                },
                "derivation": "A-2: each actual pitch contributes1 to actual "
                "pitcher, three total3; known nonterminal "
                "PA/outs/hits etc0; native runs_rbi/steals "
                "completeness unavailable remains null, not0",
            }
        ],
    }
)


def read_json(root, path):
    """宣言済みローカルJSONだけを読む。"""
    return json.loads((Path(root) / path).read_text())


def digest(path):
    """内容hashを宣言と独立に採取する。"""
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _finite_manifest(profile):
    """固定registry全形へ独立生成8の実hashだけを埋める。"""
    expected = json.loads(_FINITE_MANIFEST_JSON)
    for calc in expected["calculations"]:
        generated = {g["generatedId"]: g for g in calc["generated"]}
        for target in calc["directTargets"]:
            for part in target.get("components", [target]):
                path = generated[part["generated"]]["path"]
                part["hash"] = "sha256:" + profile["generatedFiles"][path]
    return expected


def _finite_vectors(original, source_digest):
    """原独立期待から構造射影だけを行い、製品出力/数式を使わない。"""
    current = original["current_v2_followup"]
    all_current = current["regression_cases"] + current["cases"]
    refs = {
        "path": SOURCE_CASES,
        "sha256": source_digest,
        "legacyCaseIds": [c["case_id"] for c in original["cases"]],
        "currentCaseIds": [c["case_id"] for c in all_current],
    }
    if (
        len(original["cases"]),
        len(current["regression_cases"]),
        len(current["cases"]),
    ) != (55, 55, 20):
        raise ValueError("原規範の55/現75集合が不一致です")
    alpha = json.loads(_ALPHA_META_JSON)
    alpha["sourceReferences"] = refs
    cases = []
    for case in current["regression_cases"]:
        if (
            case["expected"]["status"] == "rejected"
            or case["input"]["scope"] == "t6_sufficient_statistics"
            or len(case["input"]["events"]) != 1
        ):
            continue
        event, expected = case["input"]["events"][0], case["expected"]
        metrics = {
            mid: {
                **value,
                "credits": [
                    {"player_id": c["player_id"], "quantity": c["quantity"]}
                    for c in expected["credits"]
                    if c["metric"] == mid
                ],
            }
            for mid, value in expected["totals"].items()
        }
        cases.append(
            {
                "caseId": case["case_id"],
                "request": event,
                "expected": {
                    "comparison": "exact",
                    "expected": {
                        "metrics": metrics,
                        "pa_row": expected["completed_pa_rows"][0]
                        if expected["completed_pa_rows"]
                        else None,
                        "decisions": expected["decisions"],
                        "selected": event["source"]["source_event_id"]
                        in expected["included_source_event_ids"],
                        "source_event_id": event["source"]["source_event_id"],
                    },
                    "provenance": "NFR-018 (b)② 差分の検出可能性",
                },
                "sourceCaseId": case["case_id"],
            }
        )
    if len(cases) != 27:
        raise ValueError("独立単一eventの全27caseが不一致です")
    alpha["cases"] = cases
    ids = {c["caseId"] for c in cases}
    alpha["notDeclaredAsExecutedHere"] = [
        c["case_id"] for c in all_current if c["case_id"] not in ids
    ]
    beta = json.loads(_BETA_NORMATIVE_JSON)
    beta["sourceReferences"] = refs
    return {alpha["calculation"]: alpha, beta["calculation"]: beta}


def validate_registration(root):
    """独立源本/生成8/finite registry/原規範の全実値へ閉じて確認する。"""
    root = Path(root)
    profile = read_json(root, "backend/domain/stats-manifest.json")
    expected_generated = {
        "backend/src/pitchlog/stats/generated/facts.py",
        "frontend/src/lib/generated/statsPrimitives.ts",
        "backend/src/pitchlog/exports/generated/play_primitives.sql",
        "backend/src/pitchlog/stats/generated/stats.sql",
        "backend/src/pitchlog/stats/generated/receiver.py",
        "backend/src/pitchlog/stats/generated/formatter.py",
        "frontend/src/lib/generated/statsFormatter.ts",
        "backend/src/pitchlog/stats/generated/stats_rates.sql",
    }
    expected_inputs = {
        "backend/domain/model.schema.json",
        "backend/domain/play-export.model.json",
        "backend/domain/stats.model.json",
        "backend/src/pitchlog/domaingen/core.py",
        "backend/src/pitchlog/domaingen/pregen_checks.py",
        "backend/src/pitchlog/domaingen/formatter.py",
        "backend/src/pitchlog/domaingen/backends/python.py",
        "backend/src/pitchlog/domaingen/backends/typescript.py",
        "backend/src/pitchlog/domaingen/backends/sql.py",
    }
    expected_references = {
        SOURCE_CASES,
        "docs/features/mvp-stats-primitives/primitive-input.candidate.json",
        "docs/features/mvp-stats-primitives/primitive-output.candidate.json",
    }
    groups = [
        ("generatedFiles", expected_generated),
        ("generationInputFiles", expected_inputs),
        ("independentContractReferencesNotGenerationInputs", expected_references),
    ]
    for name, expected_paths in groups:
        values = profile[name]
        # 不明pathを開く前に集合を閉じる。
        if type(values) is not dict or set(values) != expected_paths:
            raise ValueError("独立源本/生成/規範の固定path集合が不一致です")
        if any(
            type(h) is not str or digest(root / path) != "sha256:" + h
            for path, h in values.items()
        ):
            raise ValueError("独立源本/生成/規範のhashが不一致です")
    manifest = read_json(root, MANIFEST)
    expected_manifest = _finite_manifest(profile)
    if canonical_json(manifest) != canonical_json(expected_manifest):
        raise ValueError("D11 finite registryの全計算/入口/段/宣言集合が不一致です")
    validate_asset(manifest, read_json(root, "backend/domain/manifest.schema.json"))
    prop = expected_manifest["propertyCatalog"]
    properties = read_json(root, prop["path"])
    if canonical_json(properties) != canonical_json(
        json.loads(_FINITE_PROPERTIES_JSON)
    ):
        raise ValueError("D11の全property/規範述語が不一致です")
    validate_asset(properties, read_json(root, prop["schema"]))
    original = read_json(root, SOURCE_CASES)
    vectors_by_id = _finite_vectors(original, digest(root / SOURCE_CASES)[7:])
    for calc in expected_manifest["calculations"]:
        vectors = read_json(root, calc["vectors"][0]["path"])
        if canonical_json(vectors) != canonical_json(
            vectors_by_id[calc["calculation"]]
        ):
            raise ValueError("D11の原規範27+1case/全入力/全期待が不一致です")
    return manifest


def full_values_match(calculation, case, expected, entrypoint, direct):
    """全fieldをlossless直列化して既比較器へ渡しbool/int同値化を拒否する。"""
    key = PathKey(
        calculation, "nativeD11Full", case, "pytest", "nativeActual", "nativeDirect"
    )
    contract = ComparisonContract(
        "structured-only",
        (FieldContract("whole", "structured", "json", False, None),),
        frozenset(),
    )
    report = compare_path_set(
        [key],
        [
            PathSubmission(
                key,
                [{"whole": canonical_json(expected)}],
                [{"whole": canonical_json(entrypoint)}],
                [{"whole": canonical_json(direct)}],
            )
        ],
        {calculation: contract},
    )
    return report.complete


def execute_python(request):
    """native実経路も使う同じ唯一の生成関数を実行する。"""
    from pitchlog.stats.facts import _EVENT_FACTS

    return _EVENT_FACTS(request)


def execute_typescript(root, requests, directory):
    """実TS生成物をown toolchainで実行し、期待値は渡さない。"""
    root, directory = Path(root), Path(directory)
    target = directory / "stats-native-d11.cjs"
    subprocess.run(
        [
            str(root / "frontend/node_modules/.bin/esbuild"),
            str(root / "frontend/src/lib/generated/statsPrimitives.ts"),
            "--format=cjs",
            "--platform=node",
            f"--outfile={target}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    script = (
        "globalThis.__PITCHLOG_GENERATED_WRAPPER__=true;"
        "const fs=require('fs');const api=require(process.argv[1]);"
        "const x=JSON.parse(fs.readFileSync(0,'utf8'));"
        "process.stdout.write(JSON.stringify(x.map(v=>api.eventFacts(v))));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(target)],
        input=json.dumps(requests),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def receiver_formatter_rows(sql_rows, *, maximum_integer_chars=20000):
    """実SQL行を実receiver/同fileの実formatterへ通し、観測だけを返す。"""
    from pitchlog.stats.generated import receiver

    rows = []
    calls = []
    receiver_hash = digest(receiver.__file__)
    old_profile = sys.getprofile()

    def observe(frame, event, argument):
        if frame.f_code is receiver.format_count.__code__ and event in (
            "call",
            "return",
        ):
            calls.append(
                {
                    "event": event,
                    "symbol": "pitchlog.stats.generated.receiver.format_count",
                    "code_filename": frame.f_code.co_filename,
                    "artifact_hash": receiver_hash,
                    "input": frame.f_locals.get("value") if event == "call" else None,
                    "output": argument if event == "return" else None,
                }
            )

    try:
        sys.setprofile(observe)
        for metric, state, value in sql_rows:
            typed = receiver.receive_fact_row(
                {"metric_id": metric, "state": state, "value": value},
                maximum_integer_chars=maximum_integer_chars,
            )
            # 直接複合targetは全行を明示的に最終formatterへ通す。
            # unavailable/nullも同じ生成formatterがNoneを保持する。
            displayed = receiver.format_count(typed["value"])
            if displayed != typed["display"]:
                raise ValueError("製品receiverと直接formatterの表示が不一致です")
            rows.append({**typed, "display": displayed})
    finally:
        sys.setprofile(old_profile)
    return rows, calls


def execute_sql_composite(connection, parameters, *, root=None):
    """既producerの固定current_totalsだけを実DBへ実行し全結果を通す。"""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql.psycopg import dialect

    from pitchlog.authz.stats_primitive_sql import _verified_inputs

    root = Path(__file__).resolve().parents[5] if root is None else Path(root)
    _, sections, _, _ = _verified_inputs(root)
    compiled = text(sections["current_totals"]).compile(
        dialect=dialect(paramstyle="pyformat")
    )
    if type(parameters) is not dict or set(parameters) != set(compiled.params):
        raise ValueError("固定SQLの全bind集合が不一致です")
    issued_sql, bound = str(compiled), dict(parameters)
    cursor = connection.execute(issued_sql, bound)
    try:
        rows = cursor.fetchall()
    finally:
        cursor.close()
    output, calls = receiver_formatter_rows(rows)
    return output, rows, calls, {"issued_sql": issued_sql, "parameters": bound}


def validate_stage_trace(trace, calculation, target):
    """固定3段の全I/O・終端・実入口を型losslessに照合する。"""
    root = Path(__file__).resolve().parents[5]
    manifest = validate_registration(root)
    matches = [c for c in manifest["calculations"] if c["calculation"] == calculation]
    if len(matches) != 1 or calculation != "native-current-totals26-v2":
        raise ValueError("未知の複合計算です")
    fixed = matches[0]["directTargets"][0]
    if canonical_json(target) != canonical_json(fixed):
        raise ValueError("複合targetの全段/実artifact bindingが不一致です")
    expectation = TargetExpectation(
        calculation,
        fixed["directTargetId"],
        "composite",
        tuple(StageExpectation(r["stage"], r["hash"]) for r in fixed["components"]),
    )
    hashes, links = _validate_stage_io(trace, expectation)
    stages = trace.get("stageIO")
    if (
        not hashes
        or not links
        or type(stages) is not list
        or len(stages) != 3
        or "entrypointOutput" not in trace
    ):
        raise ValueError("D11全段/実入口のI/Oが欠落又は不一致です")
    pairs = [(stages[i]["output"], stages[i + 1]["input"]) for i in range(2)]
    pairs.extend(
        [
            (stages[-1]["output"], trace["directTargetOutput"]),
            (stages[-1]["output"], trace["entrypointOutput"]),
        ]
    )
    if any(canonical_json(a) != canonical_json(b) for a, b in pairs):
        raise ValueError("D11全段/終端/実入口の型lossless連鎖が不一致です")


def collect_execution_evidence(root, junit_path, *, require_sql=True):
    """実JUnitの全case×target×propertyを収集し未実行/skip/重複を拒否する。"""
    manifest = validate_registration(root)
    expectations = {}
    expected = set()
    for calc in manifest["calculations"]:
        if not require_sql and calc["calculation"] == "native-current-totals26-v2":
            continue
        vectors = read_json(root, calc["vectors"][0]["path"])
        for target in calc["directTargets"]:
            stages = (
                tuple(
                    StageExpectation(p["stage"], p["hash"])
                    for p in target["components"]
                )
                if target["kind"] == "composite"
                else (StageExpectation("single", target["hash"]),)
            )
            expectations[(calc["calculation"], target["directTargetId"])] = (
                TargetExpectation(
                    calc["calculation"],
                    target["directTargetId"],
                    target["kind"],
                    stages,
                )
            )
            for case in vectors["cases"]:
                for prop in calc["properties"]:
                    expected.add(
                        (
                            calc["calculation"],
                            case["caseId"],
                            target["directTargetId"],
                            prop["propertyKind"],
                        )
                    )
    document = ET.parse(junit_path)
    if any(
        test.find(tag) is not None
        for test in document.getroot().iter("testcase")
        for tag in ("skipped", "failure", "error")
    ):
        raise ValueError("D11 runnerにskip/未完/失敗が残っています")
    # 補助/変異は別assert。証跡対象自身のproperty欠落は残してcollectorに拒否させる。
    for suite in document.getroot().findall("testsuite"):
        for test in list(suite.findall("testcase")):
            if not test.get("name", "").startswith("test_d11_evidence"):
                suite.remove(test)
    for test in document.getroot().iter("testcase"):
        props = {
            p.get("name"): p.get("value", "")
            for p in test.findall("properties/property")
        }
        if "trace" in props:
            trace = json.loads(props["trace"])
            calculations = {c["calculation"]: c for c in manifest["calculations"]}
            calc = calculations.get(props.get("calculation"))
            if calc is None:
                raise ValueError("証跡の計算が未宣言です")
            kind = props.get("propertyKind")
            allowed_properties = {
                p["propertyKind"]: p["propertyId"] for p in calc["properties"]
            }
            vector = read_json(root, calc["vectors"][0]["path"])
            cases = {c["caseId"]: c for c in vector["cases"]}
            target_by_id = {t["directTargetId"]: t for t in calc["directTargets"]}
            if (
                kind not in allowed_properties
                or props.get("propertyId") != allowed_properties[kind]
                or trace.get("vector") != calc["vectors"][0]["vectorId"]
                or trace.get("entrypointId") != calc["entrypoints"][0]["entrypointId"]
                or trace.get("directTargetId") not in target_by_id
                or trace.get("case") not in cases
            ):
                raise ValueError("証跡の入口/vector/property/case/targetが未宣言です")
            case = cases[trace["case"]]
            if canonical_json(trace.get("expected")) != canonical_json(
                case["expected"]["expected"]
            ):
                raise ValueError("証跡期待値が独立規範の全期待と不一致です")
            target = target_by_id[trace["directTargetId"]]
            if target["kind"] == "composite":
                validate_stage_trace(trace, calc["calculation"], target)
            if not full_values_match(
                props["calculation"],
                trace["case"],
                trace["expected"],
                trace["entrypointOutput"],
                trace["directTargetOutput"],
            ):
                raise ValueError("D11の全field/型の比較が不一致です")
    filtered = Path(junit_path).with_name("native-d11-layer-evidence.xml")
    document.write(filtered, encoding="utf-8", xml_declaration=True)
    result = collect_pytest_junit(filtered, expectations)
    observed = [
        (e.calculation, e.case, e.direct_target_id, e.property_kind)
        for e in result.evidence
    ]
    if (
        not result.complete
        or set(observed) != expected
        or len(observed) != len(expected)
    ):
        raise ValueError("D11の全case/target/property/hash/連鎖が未成立です")
    return {
        "scope": "native26-D11" if require_sql else "alpha-only; real SQL pending",
        "evidence_count": len(observed),
        "real_sql_required": require_sql,
        "source_junit_sha256": digest(junit_path),
    }


def main(argv=None):
    """構造検査だけを発効成功にせず、正規pytest証跡の実行へ委譲する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[5]
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    validate_registration(args.root)
    if args.validate_only:
        print("structural-registration-only; SQL/PG/full-D11 not executed")
        return 0
    with tempfile.TemporaryDirectory(prefix="pitchlog-stats-d11-") as directory:
        junit = Path(directory) / "d11.xml"
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/stats/test_stats_native_d11.py",
                "tests/db/test_stats_native_d11.py",
                "-q",
                f"--junitxml={junit}",
            ],
            cwd=args.root / "backend",
            check=False,
        )
        if process.returncode:
            return process.returncode
        try:
            report = collect_execution_evidence(args.root, junit)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        print(json.dumps(report))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
