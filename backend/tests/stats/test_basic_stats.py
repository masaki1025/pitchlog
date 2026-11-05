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
        assert "LEFT JOIN sync_fence.stats_primitive_facts f" in sql
        assert "FROM sync_fence.stats_primitive_sources s" in sql
        assert "JOIN public.operation_events e" in sql
        assert "JOIN public.play_rows p" in sql
        assert "FROM public.event_slots slot" in sql
        assert "c.slot_version=s.slot_version" in sql
        assert "v.tenant_id=:tenant_id" in sql
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
    assert "event: unknown" in source
    assert "requestedMetrics?: readonly string[]" in source
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
    assert len(generate_primitive_bundle(*models)) == 8


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
    assert "def _pitchlog_generated(" in artifacts[0].content
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
    assert "def _pitchlog_generated(" not in receiver.content
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


def test_native_no_change_copy_supplies_pa_k_and_out_without_future_participants():
    """v3型のbefore/責任をコピーする数学試験。真正provider成功の証明ではない。"""
    from uuid import UUID

    from pitchlog.stats.facts import evaluate_native_projection

    case = next(
        c
        for c in json.loads(
            (
                ROOT
                / "docs/features/mvp-stats-primitives/primitive-cases.candidate.json"
            ).read_text()
        )["cases"]
        if c["case_id"] == "strikeout-out"
    )
    event = case["input"]["events"][0]
    pitcher = event["participants"]["actual_pitcher_id"]
    batter = event["participants"]["actual_batter_id"]
    people = {
        "pitcherId": pitcher,
        "batterId": batter,
        "catcherId": "00000000-0000-0000-0000-000000000001",
        "battingOrder": "1",
    }
    responsibility = {
        "kind": "no-change",
        "paStartSource": {
            "kind": "started-game",
            "id": "00000000-0000-0000-0000-000000000002",
        },
    }
    payload = {
        "formatVersion": "play-prefix-play-v3",
        "participants": people,
        "calculation": {
            "request": {
                "t1": {
                    "pitchEventKind": "pitch-event",
                    "before": {
                        "stateFields": {"state.inning": "1", "state.half": "top"}
                    },
                },
                "source": {"responsibility": responsibility},
            },
            "response": {
                "ok": True,
                "value": {
                    "t1": {
                        "statFlags": event["stat_flags"],
                        "plateAppearanceEnded": True,
                        "outEffect": {"count": "1"},
                    },
                    "beforeParticipants": people,
                    "participants": {
                        **people,
                        "batterId": "00000000-0000-0000-0000-000000000003",
                    },
                    "responsibility": responsibility,
                },
            },
        },
    }
    result = evaluate_native_projection(
        payload, source_event_id=UUID(event["source"]["source_event_id"])
    )
    for key in ("pitch_count", "pa", "ab", "k", "pitcher_k", "pitching_outs"):
        assert result["metrics"][key]["value"] == "1"
    assert result["metrics"]["pa"]["credits"][0]["player_id"] == batter
    assert result["metrics"]["pitcher_k"]["credits"][0]["player_id"] == pitcher
    for key in ("runs", "rbi", "runs_allowed", "stolen_bases"):
        assert result["metrics"][key]["state"] == "source_unavailable"
    assert result["metrics"]["doubles"]["value"] == "0"
    assert result["pa_row"] is None


def test_sole_reader_rejects_fake_handle_and_page_overflow():
    """型の合う自由handle/rowを認可や無制限pageへ昇格させない。"""
    from uuid import UUID

    from pitchlog.repositories.play_export_primitives import (
        PrimitiveReadError,
        ReadPlayExportPrimitives,
        _decode_page,
    )

    with pytest.raises(PrimitiveReadError):
        ReadPlayExportPrimitives(object(), maximum_integer_chars=100)
    event = UUID("00000000-0000-0000-0000-000000000001")
    rows = (("pa", "available", Decimal(0), 1, event),)
    page = _decode_page(rows, None, 1, 100)
    assert page.rows[0]["value"] == "0"
    with pytest.raises(PrimitiveReadError):
        _decode_page(rows * 2, None, 1, 100)
    with pytest.raises(PrimitiveReadError):
        _decode_page(rows, page.next_cursor, 1, 100)
    with pytest.raises(ValueError):
        _decode_page((("pa", "available", 1.5, 1, event),), None, 1, 100)


@pytest.mark.parametrize(
    "revision,digest",
    [
        (True, None),
        (-1, None),
        (0, "a" * 64),
        (1, None),
        (1, "wire-v1:" + "a" * 64),
        (1, "A" * 64),
    ],
)
def test_native_save_cas_never_treats_bool_or_wire_fingerprint_as_series_revision(
    revision, digest
):
    """CAS型検査は資格を発行せず、S型をwire指紋/false0と区別する。"""
    from uuid import uuid4

    from pitchlog.stats.facts import prepare_native_evaluation

    with pytest.raises(ValueError):
        prepare_native_evaluation(
            {},
            attempt_id=uuid4(),
            phase_id=uuid4(),
            source_event_id=uuid4(),
            expected_revision=revision,
            expected_source_set_sha256=digest,
        )


def test_generated_canonical_s_is_independent_and_preserves_unsupported_sources(
    generated,
):
    """実原本Sの宣言をroot/COUNT/window共通sectionへ固定する。"""
    raw = generated["backend/src/pitchlog/exports/generated/play_primitives.sql"]
    sections = {
        part.split("\n", 1)[0]: part.split("\n", 1)[1]
        for part in raw.split("-- pitchlog-query: ")[1:]
    }
    assert set(sections) == {
        "window",
        "count",
        "current_totals",
        "canonical_members",
        "canonical_health",
    }
    canonical = sections["canonical_members"]
    assert (
        "stats_primitive_sources" not in canonical
        and "stats_fact_versions" not in canonical
    )
    for physical in (
        "public.event_slots",
        "public.operation_events",
        "public.play_rows",
        "public.idempotency_ledger",
        "public.recording_generations",
    ):
        assert physical in canonical
    assert "change.target_generation=slot.generation" in canonical
    assert "change.expected_version=slot.confirmed_version-1" in canonical
    assert "source_unavailable" in canonical and "native_variant" in canonical
    assert "LIMIT :canonical_page_size" in canonical
    assert "base_event_id" in canonical and "source_fingerprint" in canonical
    assert "canonical_source_set_sha256" in sections["count"]
    assert "c.source_fingerprint=s.source_fingerprint" in sections["count"]
    assert "f.source_set_sha256" not in raw
    assert "v.revision=:revision" in raw


def _generated_cte(sql, name):
    """生成済みSQLのCTE本文を括弧境界で取り出す検査補助。"""
    start = sql.index(name + " AS (") + len(name + " AS (")
    depth, quoted = 1, False
    for pos in range(start, len(sql)):
        char = sql[pos]
        if char == "'":
            quoted = not quoted
        elif not quoted:
            depth += (char == "(") - (char == ")")
            if depth == 0:
                return sql[start:pos]
    raise AssertionError("生成CTEが閉じていない")


def _execute_generated_season_health(sql, mode, category="official", raw_keys=None):
    """実生成JOIN/健康/SUMを有限SQLite面で実行。PG/認可の証明ではない。"""
    import sqlite3

    metrics = [
        m["id"] for m in _models()[0]["calculations"][0]["typedProgram"]["metrics"]
    ]
    # 非作者の独立反例に固定されたゲーム別S。期待2球は人手の2入力から定める。
    digests = {
        "game-a": "83d90fee5ed5ea852feb8dbd42001a0986bae0eb4fb6f439e78d5c96700d4bcf",
        "game-b": "09c315e9312b3a8a259227641ee7600a6e62ccfd33832ef755fd885395ce0bcc",
    }
    conn = sqlite3.connect(":memory:")
    conn.execute("ATTACH DATABASE ':memory:' AS public")
    conn.execute("ATTACH DATABASE ':memory:' AS sync_fence")
    conn.create_function(
        "array_has",
        2,
        lambda key, encoded: None if encoded is None else key in json.loads(encoded),
    )

    class BoolAnd:
        """汎用SQL BOOL_ANDだけをSQLiteへ適合する。計数式は生成物を使う。"""

        def __init__(self):
            self.value = True

        def step(self, value):
            self.value = self.value and bool(value)

        def finalize(self):
            return self.value

    conn.create_aggregate("BOOL_AND", 1, BoolAnd)
    conn.executescript("""
CREATE TABLE public.games(tenant_id,id,scheduled_at,game_type_key,status,hidden_at,trashed_at);
CREATE TABLE sync_fence.stats_fact_versions(tenant_id,game_id,id,source_count,
 model_sha256,is_current,invalidated_at,completion_state,completion_receipt_id,
 public_pointer_receipt_id,source_set_sha256,computed_metric_keys);
CREATE TABLE canonical_scope(tenant_id,game_id);
CREATE TABLE canonical_health(tenant_id,game_id,game_count,canonical_source_count,
 unavailable_count,canonical_source_set_sha256);
CREATE TABLE canonical_s(tenant_id,game_id,source_event_id,recording_generation,d1,d2,
 slot_version,play_row_id,play_row_version,source_fingerprint,artifact_sha256,source_state);
CREATE TABLE sync_fence.stats_primitive_sources(tenant_id,game_id,fact_version_id,
 source_event_id,recording_generation,d1,d2,slot_version,play_row_id,play_row_version,
 source_fingerprint,artifact_sha256,computed_metric_keys);
CREATE TABLE sync_fence.stats_primitive_facts(tenant_id,game_id,fact_version_id,
 source_event_id,metric_id,player_id,state,amount);
""")  # noqa: E501 — 固定SQL literal
    games = ["game-a"] if mode == "single" else ["game-a", "game-b"]
    if mode == "foreign-extra":
        games += ["foreign-game"]
    for game in games:
        tenant = "foreign-tenant" if game == "foreign-game" else "tenant"
        digest = digests.get(game, "f" * 64)
        version = "version-" + game
        event = "event-" + game
        conn.execute(
            "INSERT INTO public.games VALUES(?,?,1,'game_official','finished',NULL,NULL)",  # noqa: E501 — 生成target/固定SQLのliteral
            (tenant, game),
        )
        model = "old-model" if mode == "wrong-model" and game == "game-b" else "model"
        version_digest = (
            "0" * 64 if mode == "wrong-digest" and game == "game-b" else digest
        )
        if not (mode == "missing-version" and game == "game-b"):
            conn.execute(
                "INSERT INTO sync_fence.stats_fact_versions VALUES(?,?,?,1,?,true,NULL,'confirmed_ended','receipt','pointer',?,?)",  # noqa: E501 — 固定SQL literal
                (tenant, game, version, model, version_digest, json.dumps(metrics)),
            )
        if tenant == "tenant":
            conn.execute("INSERT INTO canonical_scope VALUES(?,?)", (tenant, game))
            conn.execute(
                "INSERT INTO canonical_health VALUES(?,?,1,1,0,?)",
                (tenant, game, digest),
            )
        row = (
            tenant,
            game,
            event,
            1,
            1,
            1000,
            1,
            "play-" + game,
            1,
            "fp-" + game,
            "artifact",
            "included",
        )
        conn.execute("INSERT INTO canonical_s VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", row)
        if not (mode == "missing-source" and game == "game-b"):
            saved_event = event
            if mode == "same-count-swapped":
                saved_event = "event-game-b" if game == "game-a" else "event-game-a"
            source = (
                tenant,
                game,
                version,
                saved_event,
                *row[3:11],
                json.dumps(metrics),
            )
            conn.execute(
                "INSERT INTO sync_fence.stats_primitive_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",  # noqa: E501 — 固定SQL literal
                source,
            )
        # 各試合の真正値を模した閉じたT5入力: 1球、他の寄与なし。期待を生成物から写さない。  # noqa: E501 — 固定SQL literal
        conn.execute(
            "INSERT INTO sync_fence.stats_primitive_facts VALUES(?,?,?,?,?,'player','available',1)",  # noqa: E501 — 固定SQL literal
            (tenant, game, version, event, "pitch_count"),
        )
    ctes = [
        "version_scope",
        "source_members",
        "scope_health",
        "binding_health",
        "selected",
        "aggregate_facts",
    ]
    body = (
        "WITH requested_metrics(metric_id) AS (VALUES "
        + ",".join("('" + m + "')" for m in metrics)
        + "),"
    )
    body += ",".join(
        name + " AS (" + _generated_cte(sql, name) + ")"
        for name in ctes
        if name + " AS (" in sql
    )
    body += sql[sql.index("SELECT m.metric_id,") :]
    # 型/arrayの汎用適合のみ。predicate/JOIN/CASE/SUMは実生成SQLのまま実行する。
    import re

    body = body.replace("CAST(:player_id AS uuid)", "CAST(:player_id AS text)")
    body = body.replace(
        "g.game_type_key=ANY(:raw_game_type_keys)",
        "array_has(g.game_type_key,:raw_game_type_keys)",
    )
    body = re.sub(
        r"ARRAY\[([^\]]*)\]::text\[\]",
        lambda m: (
            "'"
            + json.dumps(re.findall(r"'([^']*)'", m.group(1)), separators=(",", ":"))
            + "'"
        ),
        body,
    )
    body = body.replace(
        "CAST(:raw_game_type_keys AS text[])", ":raw_game_type_keys"
    ).replace("NULL::text[]", "NULL")
    body = re.sub(
        r"g\.game_type_key=ANY\((\(CASE :named_category .*? END\))\)",
        r"array_has(g.game_type_key,\1)",
        body,
    )  # noqa: E501 — 固定SQL literal
    body = re.sub(
        r"m\.metric_id=ANY\((\w+\.computed_metric_keys)\)",
        r"array_has(m.metric_id,\1)",
        body,
    )
    try:
        return conn.execute(
            body,
            {
                "tenant_id": "tenant",
                "player_id": "player",
                "model_sha256": "model",
                "year_start_jst": 0,
                "year_end_jst": 10,
                "raw_game_type_keys": json.dumps(
                    ["game_official", "game_semi_official"]
                    if raw_keys is None
                    else raw_keys,
                    separators=(",", ":"),
                ),
                "named_category": category,
            },
        ).fetchall()
    finally:
        conn.close()


@pytest.mark.parametrize(
    "mode,expected_pitch", [("single", 1), ("two", 2), ("foreign-extra", 2)]
)
def test_generated_season_joins_each_game_health_to_its_own_version(
    generated, mode, expected_pitch
):
    """単一/正常2試合/越境追加で別ゲームのSを比較しない。"""
    sql = generated["backend/src/pitchlog/stats/generated/stats.sql"]
    health = _generated_cte(sql, "canonical_health")
    assert "GROUP BY g.tenant_id,g.game_id" in health
    assert "FROM canonical_scope g LEFT JOIN canonical_s c" in health
    rows = _execute_generated_season_health(sql, mode)
    assert len(rows) == 27
    assert all(state == "available" for _, state, _ in rows)
    assert (
        next(value for metric, _, value in rows if metric == "pitch_count")
        == expected_pitch
    )


@pytest.mark.parametrize(
    "mode",
    [
        "missing-source",
        "missing-version",
        "wrong-model",
        "wrong-digest",
        "same-count-swapped",
    ],
)
def test_generated_season_rejects_one_game_health_gap(generated, mode):
    """片側欠測/モデル/版/同件数入替は全体を完全な0へしない。"""
    rows = _execute_generated_season_health(
        generated["backend/src/pitchlog/stats/generated/stats.sql"], mode
    )
    assert len(rows) == 27
    assert all(
        state == "source_unavailable" and value is None for _, state, value in rows
    )


@pytest.mark.parametrize(
    "category,raw",
    [
        ("unknown", ["game_official"]),
        ("practice", ["game_open", "game_intrasquad"]),
        ("official", ["game_other"]),
    ],
)
def test_generated_sql_cannot_turn_invalid_named_selection_into_zero(
    generated, category, raw
):
    """実SQLの閉selector guardが未知/不足/不一致をavailable0へしない。"""
    rows = _execute_generated_season_health(
        generated["backend/src/pitchlog/stats/generated/stats.sql"],
        "single",
        category,
        raw,
    )
    assert len(rows) == 27 and all(
        state == "source_unavailable" and value is None for _, state, value in rows
    )


def test_exact_ratio_receiver_and_single_round_preserve_sql_values(generated):
    """SQL受け口はratioをinteger metricへ偽装せず、全pairとNULLを検査する。"""
    api = _load_python(generated["backend/src/pitchlog/stats/generated/receiver.py"])
    receive = api["receive_rate_row"]
    rows = json.loads(
        (
            ROOT / "docs/features/mvp-stats-primitives/primitive-cases.candidate.json"
        ).read_text()
    )["current_v2_followup"]["cases"]
    for case in rows:
        if case.get("decision") != "D05":
            continue
        expected = case["expected"]["rates"]["ops"]
        ratio = expected["exact_ratio"]
        components = expected["components"]
        row = {
            "rate_id": "ops",
            "state": expected["state"],
            "value_state": expected["value_state"],
            "numerator": None if ratio is None else Decimal(ratio["numerator"]),
            "denominator": None if ratio is None else Decimal(ratio["denominator"]),
        }
        for key in ("obp", "slg"):
            for side in ("numerator", "denominator"):
                row[key + "_" + side] = (
                    None if components is None else Decimal(components[key][side])
                )
        assert receive(row, maximum_integer_chars=10000) == expected
    valid = {
        "rate_id": "ops",
        "state": "available",
        "value_state": "defined",
        "numerator": 2,
        "denominator": 3,
        "obp_numerator": 1,
        "obp_denominator": 3,
        "slg_numerator": 1,
        "slg_denominator": 3,
    }
    for key, value in [
        ("rate_id", "unknown"),
        ("numerator", True),
        ("numerator", 1.5),
        ("numerator", Decimal("1.2")),
        ("denominator", 0),
        ("obp_denominator", None),
        ("extra", 0),
        ("state", "source_unavailable"),
    ]:
        changed = {**valid, key: value}
        with pytest.raises(ValueError):
            receive(changed, maximum_integer_chars=10000)
    with pytest.raises(ValueError):
        receive(
            {**valid, "numerator": 2, "denominator": 2}, maximum_integer_chars=10000
        )
    with pytest.raises(ValueError):
        receive(
            {k: v for k, v in valid.items() if k != "obp_denominator"},
            maximum_integer_chars=10000,
        )
    with pytest.raises(api["OutputBudgetExceeded"]):
        receive({**valid, "numerator": "1" * 101}, maximum_integer_chars=100)


def test_ratio_sql_reuses_full_count_selection_and_keeps_bounded_current_queries(
    generated,
):
    """count/ratesで同じtenant/JST/終了/S/版WHEREを使う実生成SQLを検査する。"""
    from sqlalchemy import text

    count = generated["backend/src/pitchlog/stats/generated/stats.sql"]
    rate = generated["backend/src/pitchlog/stats/generated/stats_rates.sql"]
    sections = dict(
        part.split("\n", 1) for part in rate.split("-- pitchlog-rate-query: ")[1:]
    )
    assert set(sections) == {"season.ops", "game.ops"}
    assert count.split("\n", 2)[-1].strip().removesuffix(";") in sections["season.ops"]
    for name, sql in sections.items():
        assert "GROUP BY player_id, metric_id" in sql
        assert "g.game_type_key=ANY((CASE :named_category" in sql
        for token in (
            "g.tenant_id=:tenant_id",
            "g.status='finished'",
            "v.completion_state='confirmed_ended'",
            "v.public_pointer_receipt_id IS NOT NULL",
            "g.scheduled_at>=:year_start_jst",
            "g.scheduled_at<:year_end_jst",
            "g.hidden_at IS NULL",
            "g.trashed_at IS NULL",
            "canonical_source_set_sha256",
            "v.model_sha256=:model_sha256",
            "g.id=v.game_id",
        ):
            assert token in sql
        assert "gcd(" in sql and "div(" in sql and "FLOAT" not in sql.upper()
        assert set(text(sql)._bindparams) == {
            "tenant_id",
            "player_id",
            "model_sha256",
            "year_start_jst",
            "year_end_jst",
            "named_category",
            "raw_game_type_keys",
            *({"game_id"} if name == "game.ops" else set()),
        }
    assert "AND g.id=:game_id" in sections["game.ops"]
    window = generated["backend/src/pitchlog/exports/generated/play_primitives.sql"]
    assert "LIMIT :page_size" in window and "LIMIT :canonical_page_size" in window


def test_ratio_sql_decimal_codec_keeps_5000_digit_pairs_at_precision_two(generated):
    """SQL numericの受け口もDecimal精度へ丸めず、global桁上限を変えない。"""
    import sys
    from decimal import localcontext

    receive = _load_python(
        generated["backend/src/pitchlog/stats/generated/receiver.py"]
    )["receive_rate_row"]
    before = sys.get_int_max_str_digits()
    n, d = "9" * 5000, "5" + "0" * 4999
    input_denominator = "1" + "0" * 5000
    with localcontext() as context:
        context.prec = 2
        row = {
            "rate_id": "ops",
            "state": "available",
            "value_state": "defined",
            "numerator": Decimal(n),
            "denominator": Decimal(d),
            "obp_numerator": Decimal(n),
            "obp_denominator": Decimal(input_denominator),
            "slg_numerator": Decimal(n),
            "slg_denominator": Decimal(input_denominator),
        }
        result = receive(row, maximum_integer_chars=10000)
    assert result["exact_ratio"] == {"numerator": n, "denominator": d}
    assert result["components"]["obp"]["denominator"] == input_denominator
    assert result["formatted_value"] == "2.000"
    assert sys.get_int_max_str_digits() == before


def test_bf_quantity_is_generated_from_d1_not_a_fixed_expected_response():
    """BF数量のD1変異も実行体へ伝播し固定1応答やcase lookupでないことを示す。"""
    from pitchlog.domaingen.core import _canonical_hash

    common, consumer = _models()
    common = copy.deepcopy(common)
    consumer = copy.deepcopy(consumer)
    common["calculations"][0]["typedProgram"]["metrics"][-1]["quantity"] = {
        "op": "literal",
        "value": 2,
    }
    consumer["calculations"][0]["typedProgram"]["commonModelHash"] = _canonical_hash(
        common
    )
    bundle = generate_primitive_bundle(common, consumer)
    api = _load_python(bundle["backend/src/pitchlog/stats/generated/facts.py"])
    cases = json.loads(
        (
            ROOT / "docs/features/mvp-stats-primitives/primitive-cases.candidate.json"
        ).read_text()
    )["current_v3_bf_followup"]["cases"]
    event = next(c for c in cases if c["case_id"] == "current-v3-bf-no-change-walk")[
        "input"
    ]["events"][0]
    actual = api["_pitchlog_generated"](event)["metrics"]["batters_faced"]
    assert actual == {
        "state": "available",
        "value": "2",
        "display": "2",
        "reason": None,
        "credits": [
            {"player_id": event["participants"]["actual_pitcher_id"], "quantity": "2"}
        ],
    }
