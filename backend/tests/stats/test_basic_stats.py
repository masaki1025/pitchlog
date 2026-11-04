"""共通参照・閉型拒否・実生成SQL・型付き受け口の境界を検証する。"""

from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pitchlog.domaingen.backends.common import BackendGenerationError
from pitchlog.domaingen.core import GenerationError, generate_primitive_bundle

ROOT = Path(__file__).resolve().parents[3]


def _models():
    return tuple(
        json.loads((ROOT / "backend/domain" / name).read_text())
        for name in ["play-export.model.json", "stats.model.json"]
    )


def _rehash(common, consumer):
    raw = (
        json.dumps(common, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    consumer["calculations"][0]["typedProgram"]["commonModelHash"] = (
        "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
    )


def _load_python(content):
    namespace: dict[str, Any] = {"__name__": "__pitchlog_generated_wrapper__"}
    exec(compile(content, "<generated>", "exec"), namespace)
    return namespace


@pytest.fixture(scope="module")
def generated():
    """期待値やproperty fileを一切入力せず生成する。"""
    return generate_primitive_bundle(*_models())


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "unknown-id",
        "wrong-type",
        "cycle",
        "unknown-expr",
        "wrong-guard",
        "wrong-item-type",
        "unbounded",
        "extra-key",
        "sql-injection",
    ],
)
def test_generation_rejects_unknown_refs_types_and_sql(mutation):
    """生成前拒否は実行できる別式への逃げ道を作らない。"""
    common, consumer = _models()
    p = common["calculations"][0]["typedProgram"]
    r = consumer["calculations"][0]["typedProgram"]
    if mutation == "hash":
        r["commonModelHash"] = "sha256:" + "0" * 64
    if mutation == "unknown-id":
        r["refs"][0]["id"] = "unknown"
    if mutation == "wrong-type":
        r["refs"][0]["type"] = "boolean"
    if mutation == "cycle":
        consumer["calculations"][0]["calculationId"] = common["calculations"][0][
            "calculationId"
        ]
    if mutation == "unknown-expr":
        p["metrics"][0]["quantity"] = {"op": "eval", "code": "1"}
    if mutation == "wrong-guard":
        p["metrics"][0]["guard"] = {"op": "literal", "value": 1}
    if mutation == "wrong-item-type":
        next(m for m in p["metrics"] if m["id"] == "runs")["quantity"] = {
            "op": "ref",
            "path": "item.valid_run",
        }
    if mutation == "unbounded":
        p["collections"]["runner_scores"]["maximumItems"] = 150000
    if mutation == "extra-key":
        p["metrics"][0]["quantity"]["expected"] = 1
    if mutation == "sql-injection":
        p["sql"]["facts"] = "public.facts;DROP TABLE games"
    if mutation not in {"hash", "unknown-id", "wrong-type", "cycle"}:
        _rehash(common, consumer)
    with pytest.raises((GenerationError, BackendGenerationError)):
        generate_primitive_bundle(common, consumer)


def test_receiver_preserves_real_zero_null_and_large_numeric(generated):
    """実DBが返すDecimalもfloat化せず、未知を0へ変えない。"""
    raw_receive = _load_python(
        generated["backend/src/pitchlog/stats/generated/receiver.py"]
    )["receive_fact_row"]

    def receive(row):
        """試験の資源予算を明示し、値域と混同しない。"""
        return raw_receive(row, maximum_integer_chars=10000)

    assert (
        receive(
            {
                "metric_id": "pa",
                "state": "available",
                "value": Decimal("9007199254740995"),
            }
        )["value"]
        == "9007199254740995"
    )
    assert (
        receive({"metric_id": "h", "state": "available", "value": 0})["display"] == "0"
    )
    assert (
        receive({"metric_id": "h", "state": "source_unavailable", "value": None})[
            "display"
        ]
        is None
    )
    for value in [True, 1.5, Decimal("1.5"), Decimal("NaN"), None, "01"]:
        with pytest.raises(ValueError):
            receive({"metric_id": "h", "state": "available", "value": value})
    with pytest.raises(ValueError):
        receive({"metric_id": "unknown", "state": "available", "value": 0})


def test_sql_consumes_canonical_facts_not_raw_t1_or_json_rows(generated):
    """実表S/版のJOINとDB集計があり、生T1から寄与を作り直さない。"""
    grouped = generated["backend/src/pitchlog/stats/generated/stats.sql"]
    window = generated["backend/src/pitchlog/exports/generated/play_primitives.sql"]
    for sql in [grouped, window]:
        assert "FROM public.stats_primitive_facts f" in sql
        assert "JOIN public.operation_events e" in sql
        assert "JOIN public.play_rows p" in sql
        assert "JOIN public.event_slots slot" in sql
        assert "confirmed_version=f.slot_version" in sql
        assert "f.tenant_id=:tenant_id" in sql
        assert "v.model_sha256=:model_sha256" in sql
        assert "SUM(amount)" in sql
        assert "jsonb_array_elements" not in sql
        assert ":pitchlog_value" not in sql
        assert "statFlags" not in sql
    assert "GROUP BY player_id, metric_id" in grouped
    assert "completion_receipt_id IS NOT NULL" in grouped
    assert "coverage.computed_metric_keys" in grouped
    assert "year_start_jst" in grouped and "raw_game_type_keys" in grouped
    assert window.index("SUM(amount) OVER w") < window.index("WHERE (:after_d2 IS NULL")
    assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in window
    assert "LIMIT :page_size" in window


def test_generated_event_api_has_no_full_game_collection_entry(generated):
    """製品targetは一遷移と最大4人だけを扱い全件集計を公開しない。"""
    api = _load_python(generated["backend/src/pitchlog/stats/generated/facts.py"])
    assert "_pitchlog_generated" in api and "aggregate_games" not in api
    assert "events" not in api
    source = generated["frontend/src/lib/generated/statsPrimitives.ts"]
    assert "eventFacts(event: unknown)" in source
    assert "for (const event" not in source


@pytest.mark.parametrize("metric_index", range(26))
def test_each_metric_non_equivalent_quantity_mutation_is_killed(metric_index):
    """26群の数量式変異を原典の独立期待が検出する。"""
    common, consumer = _models()
    p = common["calculations"][0]["typedProgram"]
    metric = p["metrics"][metric_index]
    mid = metric["id"]
    cases = json.loads(
        (
            ROOT / "docs/features/mvp-stats-primitives/primitive-cases.candidate.json"
        ).read_text()
    )["cases"]
    case = next(
        c
        for c in cases
        if c["expected"]["status"] != "rejected"
        and c["input"]["scope"] != "t6_sufficient_statistics"
        and c["expected"]["totals"][mid]["state"] == "available"
        and int(c["expected"]["totals"][mid]["value"]) > 0
    )
    metric["quantity"] = {
        "op": "add",
        "args": [copy.deepcopy(metric["quantity"]), {"op": "literal", "value": 1}],
    }
    _rehash(common, consumer)
    api = _load_python(
        generate_primitive_bundle(common, consumer)[
            "backend/src/pitchlog/stats/generated/facts.py"
        ]
    )
    # 有限独立caseだけの比較。製品へ全game reducerを追加しない。
    observed = sum(
        int(api["_pitchlog_generated"](event)["metrics"][mid]["value"])
        for event in case["input"]["events"]
    )
    assert observed != int(case["expected"]["totals"][mid]["value"])


def test_typed_model_schema_and_property_catalog_are_closed():
    """新typed variantを公開schemaで検証し旧Calculation定義を保持する。"""
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "backend/domain/model.schema.json").read_text())
    validator = Draft202012Validator(schema)
    for model in _models():
        validator.validate(model)
    assert "properties" in schema["$defs"]["Calculation"]
    catalog = json.loads(
        (ROOT / "backend/domain/stats-property-catalog.json").read_text()
    )
    catalog_schema = json.loads(
        (ROOT / "backend/domain/stats-property-catalog.schema.json").read_text()
    )
    Draft202012Validator(catalog_schema).validate(catalog)
    assert catalog["expectationsAreGeneratorInputs"] is False


def test_generation_never_reads_expectation_or_property_files(monkeypatch):
    """期待fileを読めなくしてもmodelだけの生成は変わらない。"""
    models = _models()
    original = Path.read_text

    def guarded(path, *args, **kwargs):
        if path.name in {
            "primitive-cases.candidate.json",
            "stats-property-catalog.json",
        }:
            raise AssertionError("独立期待を生成入力にした")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    assert len(generate_primitive_bundle(*models)) == 7


def test_integer_range_and_enum_refusals(generated):
    """実targetでも型付きfieldの範囲/未知enumを拒否する。"""
    api = _load_python(generated["backend/src/pitchlog/stats/generated/facts.py"])
    cases = json.loads(
        (
            ROOT / "docs/features/mvp-stats-primitives/primitive-cases.candidate.json"
        ).read_text()
    )["cases"]
    source = next(c for c in cases if c["case_id"] == "home-run-3-effective-runs")[
        "input"
    ]["events"][0]
    for path, value in [("out_effect", 4), ("event_kind", "unknown")]:
        event = copy.deepcopy(source)
        if path == "out_effect":
            event[path]["effective_count"] = value
        else:
            event[path] = value
        with pytest.raises(ValueError):
            api["_pitchlog_generated"](event)


def _public_intermediate(target_class, stages):
    """公開dispatcherへ渡す実共通宣言と段別provenanceを作る。"""
    common, _ = _models()
    return {
        "generatorVersion": "1.0.0",
        "calculations": [
            {
                "calculationId": "canonicalEventFacts",
                "sourceId": "REQ:E-1",
                "declaration": common["calculations"][0],
                "targets": [
                    {
                        "directTargetId": "stats-public",
                        "targetClass": target_class,
                        "stages": [
                            {
                                "stage": stage,
                                "generatedId": "stats-" + stage,
                                "sourceHash": "sha256:" + "a" * 64,
                            }
                            for stage in stages
                        ],
                    }
                ],
            }
        ],
    }


def test_existing_public_dispatcher_generates_alpha_facts():
    """公開alpha経路は共通段からPython/TSの単一遷移核を返す。"""
    from pitchlog.domaingen.backends import generate_language_artifacts

    artifacts = generate_language_artifacts(_public_intermediate("alpha", ["python"]))
    assert [(a.stage, a.language.value) for a in artifacts] == [
        ("python", "python"),
        ("python", "typescript"),
    ]
    assert "_pitchlog_generated(event)" in artifacts[0].content
    assert "dict(context)" not in artifacts[0].content
    assert "eventFacts" in artifacts[1].content
    assert all("receive_fact_row" not in a.content for a in artifacts)


def test_existing_public_dispatcher_generates_beta_receiver_not_event_kernel():
    """正規beta三段は保存済みfact SQLと実行可能なtyped受け口を返す。"""
    from pitchlog.domaingen.backends import generate_language_artifacts

    artifacts = generate_language_artifacts(
        _public_intermediate("beta-1-5", ["sql", "typed-receiver", "formatter"])
    )
    assert [(a.stage, a.language.value) for a in artifacts] == [
        ("sql", "sql"),
        ("typed-receiver", "python"),
    ]
    sql, receiver = artifacts
    assert "stats_primitive_facts" in sql.content
    assert ":pitchlog_value" not in sql.content
    assert "receive_fact_row" in receiver.content
    assert "_pitchlog_generated(event)" not in receiver.content
    api = _load_python(receiver.content)
    assert (
        api["receive_fact_row"](
            {"metric_id": "pa", "state": "available", "value": Decimal(2)},
            maximum_integer_chars=100,
        )["value"]
        == "2"
    )
    assert all(a.stage != "formatter" for a in artifacts)


@pytest.mark.parametrize(
    "target_class,stages",
    [
        ("alpha", ["sql"]),
        ("alpha", ["typed-receiver"]),
        ("alpha", ["formatter"]),
        ("alpha", ["typescript"]),
        ("beta-1-5", ["typed-receiver", "sql", "formatter"]),
        ("beta-7", ["sql", "typed-receiver"]),
        ("beta-6-8", ["python"]),
    ],
)
def test_existing_public_dispatcher_rejects_wrong_typed_roles(target_class, stages):
    """typed演算を対象外class/stageへ公開経路から流用しない。"""
    from pitchlog.domaingen.backends import (
        BackendGenerationError,
        generate_language_artifacts,
    )

    with pytest.raises(BackendGenerationError):
        generate_language_artifacts(_public_intermediate(target_class, stages))


@pytest.mark.parametrize(
    "backend,target_class,stage",
    [
        ("python", "alpha", "sql"),
        ("python", "beta-1-5", "sql"),
        ("python", "beta-1-5", "formatter"),
        ("typescript", "beta-1-5", "typed-receiver"),
        ("typescript", "alpha", "typed-receiver"),
        ("sql", "alpha", "python"),
        ("sql", "alpha", "sql"),
        ("sql", "beta-1-5", "typed-receiver"),
        ("sql", "beta-7", "sql"),
    ],
)
def test_backend_direct_entry_rejects_wrong_typed_roles(backend, target_class, stage):
    """backend直接呼出でも閉stage判定を迂回できない。"""
    from importlib import import_module

    from pitchlog.domaingen.backends.common import BackendGenerationError, BackendInput

    common, _ = _models()
    source = BackendInput(
        generator_version="1.0.0",
        source_id="REQ:E-1",
        calculation_id="canonicalEventFacts",
        direct_target_id="stats-role",
        target_class=target_class,
        stage=stage,
        generated_id="stats-role",
        source_hash="sha256:" + "a" * 64,
        declaration=common["calculations"][0],
    )
    with pytest.raises(BackendGenerationError):
        import_module("pitchlog.domaingen.backends." + backend).generate(source)


def test_receiver_output_budget_is_not_a_numeric_value_domain(generated):
    """資源予算超過は例外であり0/NULL/近似値へ置換しない。"""
    api = _load_python(generated["backend/src/pitchlog/stats/generated/receiver.py"])
    receive = api["receive_fact_row"]
    value = "1" + "0" * 128
    assert (
        receive(
            {"metric_id": "pa", "state": "available", "value": value},
            maximum_integer_chars=200,
        )["value"]
        == value
    )
    with pytest.raises(api["OutputBudgetExceeded"]):
        receive(
            {"metric_id": "pa", "state": "available", "value": Decimal("1E+999999999")},
            maximum_integer_chars=200,
        )
    with pytest.raises(api["OutputBudgetExceeded"]):
        receive(
            {"metric_id": "pa", "state": "available", "value": value},
            maximum_integer_chars=128,
        )


def test_known_finite_field_rejects_long_input_before_integer_conversion(generated):
    """既定義outEffect0..3だけを変換前に制限する。"""
    api = _load_python(generated["backend/src/pitchlog/stats/generated/facts.py"])
    cases = json.loads(
        (
            ROOT / "docs/features/mvp-stats-primitives/primitive-cases.candidate.json"
        ).read_text()
    )["cases"]
    event = copy.deepcopy(
        next(c for c in cases if c["case_id"] == "strikeout-out")["input"]["events"][0]
    )
    event["out_effect"]["effective_count"] = "1" + "0" * 100000

    def forbidden(_value):
        raise AssertionError("有限fieldの長大値を先に整数変換した")

    api["_n"] = forbidden
    with pytest.raises(ValueError):
        api["_pitchlog_generated"](event)
