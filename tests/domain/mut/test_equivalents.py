"""等価変異台帳の形・遷移・既存変異機構との接続を検査する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
LEDGER_PATH = ROOT / "backend/domain/mutation-equivalents.json"
FIXTURE_ROOT = ROOT / "backend/tests/domain/fixtures/synthetic_dsl"

sys.path.insert(0, str(BACKEND_SRC))
CORE = importlib.import_module("pitchlog.domaingen.core")
FORMATTER = importlib.import_module("pitchlog.domaingen.formatter")
ENGINE = importlib.import_module("pitchlog.domainmut.engine")
EQUIVALENTS = importlib.import_module("pitchlog.domainmut.equivalents")
OPERATORS = importlib.import_module("pitchlog.domainmut.operators_display")
SCOPE = importlib.import_module("pitchlog.domainmut.scope")


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を UTF-8 で読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _empty_ledger_document() -> dict[str, Any]:
    """実資産の現在値に依存せず空遷移を作った写しを返す。"""
    document = copy.deepcopy(_read_json(LEDGER_PATH))
    document["entries"] = []
    return document


def _entry(mutant_id: str, judge: str = "PO") -> dict[str, object]:
    """一 mutant の合成 PO 判定行を返す。"""
    return {
        "mutantId": mutant_id,
        "reason": "要求 case の表示が完全一致し、有効な kill 証跡がない",
        "judge": judge,
        "decisionDate": "2026-09-20",
    }


@pytest.fixture(scope="module")
def schemas() -> Any:
    """既存の宣言モデル・マニフェスト・語彙 schema を返す。"""
    return CORE.SourceSchemas(
        model=_read_json(ROOT / "backend/domain/model.schema.json"),
        manifest=_read_json(ROOT / "backend/domain/manifest.schema.json"),
        vocabulary=_read_json(ROOT / "backend/domain/vocabulary.schema.json"),
    )


def _intermediate(schemas: Any) -> dict[str, object]:
    """固定小数 scale 0 を持つ宣言を既存生成コアへ通す。"""
    model = _read_json(FIXTURE_ROOT / "model.json")
    manifest = _read_json(FIXTURE_ROOT / "manifest.json")
    model["displayRules"] = [
        {
            "kind": "numeric-primitive",
            "id": "fixedNumber",
            "primitive": {
                "kind": "fixed-decimal",
                "scale": 0,
                "rounding": "half-up",
                "leadingZero": False,
                "sign": "negative-only-hyphen-minus",
            },
        }
    ]
    model["calculations"][0]["displayRuleRefs"] = ["fixedNumber"]
    return CORE.generate_intermediate_representation(
        model,
        manifest,
        schemas,
        ROOT,
    )


def _formatter_function(
    intermediate: dict[str, object],
) -> Callable[[str, object], object]:
    """既存生成器の alpha Python formatter を実行可能にして返す。"""
    matches = [
        artifact
        for artifact in FORMATTER.generate_display_artifacts(intermediate)
        if artifact.target_class == "alpha"
        and artifact.language.value == "python"
        and artifact.purpose.value == "formatter"
    ]
    assert len(matches) == 1
    namespace: dict[str, object] = {
        "__name__": "__pitchlog_generated_wrapper__"
    }
    exec(compile(matches[0].content, "<equivalent-mutant>", "exec"), namespace)
    function = namespace["_pitchlog_format"]
    assert callable(function)
    return cast(Callable[[str, object], object], function)


def _target(schemas: Any) -> Any:
    """scale 0 の formatter 呼出しを持つ合成対象を返す。"""
    source = OPERATORS.DisplayMutationSource(
        intermediate=_intermediate(schemas),
        invocation=OPERATORS.FormatterInvocation(
            rule_id="fixedNumber",
            numeric_value={"kind": "integer", "value": 7},
            language_value=7,
        ),
    )
    return ENGINE.SyntheticMutationTarget(
        calculation="syntheticEquivalentCalculation",
        target_id="syntheticEquivalentTarget",
        source=source,
    )


def _operator() -> Any:
    """既存の formatter 呼出し変異演算子を返す。"""
    return OPERATORS.DISPLAY_OPERATORS[
        OPERATORS.DisplayMutationKind.FORMATTER_INVOCATION
    ]


def _route_output(source: Any, formatter: Callable[[str, object], object]) -> object:
    """生成 formatter または変異後の呼出し経路を実行する。"""
    invocation = source.invocation
    if invocation.route is OPERATORS.FormatterRoute.FORMATTER:
        return formatter(invocation.rule_id, invocation.numeric_value)
    if invocation.route is OPERATORS.FormatterRoute.RAW_VALUE:
        return invocation.language_value
    return str(invocation.language_value)


@dataclass(frozen=True, slots=True)
class _ScaleZeroExecutor:
    """実出力の差をプロパティ層の kill として記録する。"""

    expected: object
    formatter: Callable[[str, object], object]

    def execute(self, mutant: Any) -> Any:
        """変異後の経路を実行し、表示差だけを kill にする。"""
        changed = mutant.mutated
        assert isinstance(changed, OPERATORS.DisplayMutationSource)
        actual = _route_output(changed, self.formatter)
        if actual == self.expected:
            return ENGINE.MutationExecution(False, ())
        return ENGINE.MutationExecution(
            True,
            (
                ENGINE.KillEvidence(
                    mutant_id=mutant.mutant_id,
                    calculation=mutant.calculation,
                    layer=ENGINE.KillLayer.PROPERTY_INVARIANT,
                    check_id=f"{mutant.target_id}.scale-zero-output",
                ),
            ),
        )


def _executor(target: Any) -> _ScaleZeroExecutor:
    """元の生成 formatter 出力へ束縛した実行器を返す。"""
    formatter = _formatter_function(target.source.intermediate)
    expected = _route_output(target.source, formatter)
    return _ScaleZeroExecutor(expected, formatter)


def _default_mutant(generation: Any) -> Any:
    """言語既定文字列化へ置換した mutant を返す。"""
    return next(
        mutant
        for mutant in generation.mutants
        if mutant.mutated.invocation.route
        is OPERATORS.FormatterRoute.LANGUAGE_DEFAULT
    )


def _observation(mutant: Any, formatter: Callable[[str, object], object]) -> Any:
    """三つの整数 case で scale 0 の完全一致を実測する。"""
    cases = {
        "negative-integer": -2,
        "zero": 0,
        "positive-integer": 7,
    }
    executed: set[str] = set()
    matching: set[str] = set()
    for case_id, value in cases.items():
        expected = formatter(
            "fixedNumber",
            {"kind": "integer", "value": value},
        )
        actual = str(value)
        executed.add(case_id)
        if actual == expected:
            matching.add(case_id)
    source = mutant.mutated
    primitive = source.intermediate["displayRules"][0]["primitive"]
    return EQUIVALENTS.ScaleZeroFormatterObservation(
        mutant_id=mutant.mutant_id,
        operator_id=mutant.operator_id,
        primitive_kind=primitive["kind"],
        scale=primitive["scale"],
        replacement_route=source.invocation.route.value,
        required_case_ids=frozenset(cases),
        executed_case_ids=frozenset(executed),
        matching_case_ids=frozenset(matching),
        valid_kill_evidence_ids=frozenset(),
    )


def test_asset_and_an_explicit_empty_copy_are_accepted() -> None:
    """現在の行数を固定せず、実資産と空台帳の形を受理する。"""
    actual = EQUIVALENTS.validate_equivalence_ledger(_read_json(LEDGER_PATH))
    empty = EQUIVALENTS.validate_equivalence_ledger(_empty_ledger_document())

    assert actual.authority_id == EQUIVALENTS.AUTHORITY_ID
    assert empty.approved_ids == frozenset()


@pytest.mark.parametrize("key", ("schemaVersion", "entries"))
def test_missing_top_level_key_is_rejected(key: str) -> None:
    """トップレベルの必須キー欠落を拒否する。"""
    document = _empty_ledger_document()
    del document[key]

    with pytest.raises(EQUIVALENTS.EquivalenceLedgerError, match="missing"):
        EQUIVALENTS.validate_equivalence_ledger(document)


def test_unknown_top_level_key_is_rejected() -> None:
    """トップレベルの未知キーを拒否する。"""
    document = _empty_ledger_document()
    document["note"] = "未知キー"

    with pytest.raises(EQUIVALENTS.EquivalenceLedgerError, match="unknown"):
        EQUIVALENTS.validate_equivalence_ledger(document)


@pytest.mark.parametrize("key", ("mutantId", "reason", "judge", "decisionDate"))
def test_missing_entry_key_is_rejected(key: str) -> None:
    """各台帳行の四つの必須キー欠落を個別に拒否する。"""
    document = _empty_ledger_document()
    row = _entry("synthetic.mutant")
    del row[key]
    document["entries"] = [row]

    with pytest.raises(EQUIVALENTS.EquivalenceLedgerError, match="missing"):
        EQUIVALENTS.validate_equivalence_ledger(document)


def test_unknown_entry_key_is_rejected() -> None:
    """台帳行の未知キーを拒否する。"""
    document = _empty_ledger_document()
    row = _entry("synthetic.mutant")
    row["note"] = "未知キー"
    document["entries"] = [row]

    with pytest.raises(EQUIVALENTS.EquivalenceLedgerError, match="unknown"):
        EQUIVALENTS.validate_equivalence_ledger(document)


def test_operating_policy_is_also_an_exact_set() -> None:
    """運用規約内部でも未知キーと欠落キーを拒否する。"""
    unknown = _empty_ledger_document()
    unknown["operatingPolicy"]["exception"] = True
    missing = _empty_ledger_document()
    del missing["operatingPolicy"]["scaleZeroFormatterBypass"]["decision"][
        "nonEquivalentWhen"
    ]

    with pytest.raises(EQUIVALENTS.EquivalenceLedgerError, match="unknown"):
        EQUIVALENTS.validate_equivalence_ledger(unknown)
    with pytest.raises(EQUIVALENTS.EquivalenceLedgerError, match="missing"):
        EQUIVALENTS.validate_equivalence_ledger(missing)


def test_non_po_judge_is_rejected() -> None:
    """PO 以外による等価判定を拒否する。"""
    document = _empty_ledger_document()
    document["entries"] = [_entry("synthetic.mutant", judge="developer")]

    with pytest.raises(EQUIVALENTS.EquivalenceLedgerError, match="PO"):
        EQUIVALENTS.validate_equivalence_ledger(document)


def test_unrecorded_mutant_is_non_equivalent(schemas: Any) -> None:
    """実測が一致しても未記録 mutant を kill 要件から外さない。"""
    target = _target(schemas)
    generation = _operator().generate(target)
    mutant = _default_mutant(generation)
    formatter = _formatter_function(target.source.intermediate)
    observation = _observation(mutant, formatter)
    ledger = EQUIVALENTS.validate_equivalence_ledger(_empty_ledger_document())

    disposition = EQUIVALENTS.classify_scale_zero_formatter_bypass(
        observation,
        ledger,
    )

    assert disposition is EQUIVALENTS.EquivalenceDisposition.NON_EQUIVALENT
    with pytest.raises(ENGINE.MutationEngineError, match="未記録の等価扱い"):
        OPERATORS.run_display_mutations(
            (target,),
            (_operator(),),
            _executor(target),
            approved_equivalent_ids=ledger.approved_ids,
        )


def test_ledger_change_triggers_existing_full_scope_resolution() -> None:
    """台帳改変をステップ42の七種の一つとして全面発火させる。"""
    graph = SCOPE.CalculationGraph(
        calculations=frozenset({"syntheticA", "syntheticB"}),
        dependencies={
            "syntheticA": frozenset(),
            "syntheticB": frozenset({"syntheticA"}),
        },
    )

    plan = EQUIVALENTS.resolve_ledger_change_scope(graph)

    assert plan.mode is SCOPE.ScopeMode.FULL
    assert plan.triggers == frozenset(
        {SCOPE.FullRunTrigger.EQUIVALENCE_LEDGER}
    )
    assert plan.selected_calculations == graph.calculations


def test_recorded_equivalent_is_excluded_from_kill_requirement(
    schemas: Any,
) -> None:
    """PO 記録済みの等価 mutant を既存集合等式から実際に除外する。"""
    target = _target(schemas)
    generation = _operator().generate(target)
    mutant = _default_mutant(generation)
    formatter = _formatter_function(target.source.intermediate)
    observation = _observation(mutant, formatter)
    document = _empty_ledger_document()
    document["entries"] = [_entry(mutant.mutant_id)]
    ledger = EQUIVALENTS.validate_equivalence_ledger(document)

    disposition = EQUIVALENTS.classify_scale_zero_formatter_bypass(
        observation,
        ledger,
    )
    report = OPERATORS.run_display_mutations(
        (target,),
        (_operator(),),
        _executor(target),
        approved_equivalent_ids=ledger.approved_ids,
    )

    result = report.calculations[0]
    assert disposition is EQUIVALENTS.EquivalenceDisposition.APPROVED_EQUIVALENT
    assert report.complete
    assert mutant.mutant_id in result.approved_equivalents
    assert result.generated - result.approved_equivalents - result.killed == set()


def test_kill_and_equivalent_candidate_overlap_is_measured_as_zero(
    schemas: Any,
) -> None:
    """生成 mutant の kill と等価候補の重複件数を実出力で測る。"""
    target = _target(schemas)
    generation = _operator().generate(target)
    executor = _executor(target)
    killed = {
        mutant.mutant_id
        for mutant in generation.mutants
        if executor.execute(mutant).killed
    }
    candidates = {
        referral.mutant_id
        for referral in OPERATORS.equivalence_referrals(generation.mutants)
    }

    assert len(generation.mutants) == 2
    assert len(killed) == 1
    assert len(candidates) == 1
    assert len(killed & candidates) == 0


def test_scale_zero_decision_rejects_a_kill_and_approval_conflict(
    schemas: Any,
) -> None:
    """同一 mutant の kill と等価承認を二通りの判定として許さない。"""
    target = _target(schemas)
    generation = _operator().generate(target)
    mutant = _default_mutant(generation)
    formatter = _formatter_function(target.source.intermediate)
    observation = _observation(mutant, formatter)
    document = _empty_ledger_document()
    document["entries"] = [_entry(mutant.mutant_id)]
    ledger = EQUIVALENTS.validate_equivalence_ledger(document)
    conflict = replace(
        observation,
        valid_kill_evidence_ids=frozenset({"synthetic.valid-kill"}),
    )

    with pytest.raises(
        EQUIVALENTS.EquivalenceLedgerError,
        match="実測不成立",
    ):
        EQUIVALENTS.classify_scale_zero_formatter_bypass(conflict, ledger)
