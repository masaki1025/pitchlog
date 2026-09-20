"""表示系五系統の変異・kill・等価候補への分岐を実機で検査する。"""

from __future__ import annotations

import copy
import importlib
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
FIXTURE_ROOT = ROOT / "backend/tests/domain/fixtures/synthetic_dsl"
COST_PATH = ROOT / "docs/features/domain-calc-dsl/mutation-cost.json"

sys.path.insert(0, str(BACKEND_SRC))
CORE = importlib.import_module("pitchlog.domaingen.core")
FORMATTER = importlib.import_module("pitchlog.domaingen.formatter")
ENGINE = importlib.import_module("pitchlog.domainmut.engine")
OPERATORS = importlib.import_module("pitchlog.domainmut.operators_display")


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object をUTF-8で読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="module")
def schemas() -> Any:
    """既存の宣言モデル・マニフェスト・語彙 schema を返す。"""
    return CORE.SourceSchemas(
        model=_read_json(ROOT / "backend/domain/model.schema.json"),
        manifest=_read_json(ROOT / "backend/domain/manifest.schema.json"),
        vocabulary=_read_json(ROOT / "backend/domain/vocabulary.schema.json"),
    )


def _display_rules(scale: int) -> list[dict[str, object]]:
    """五系統を実行観測できる合成表示規則を返す。"""
    atom = {
        "type": "DisplayAtom",
        "source": {
            "kind": "enum-map-output",
            "mapId": "sideName",
            "value": "left",
        },
    }
    return [
        {
            "kind": "numeric-primitive",
            "id": "fixedNumber",
            "primitive": {
                "kind": "fixed-decimal",
                "scale": scale,
                "rounding": "half-up",
                "leadingZero": False,
                "sign": "negative-only-hyphen-minus",
            },
        },
        {
            "kind": "numeric-primitive",
            "id": "percentageNumber",
            "primitive": {
                "kind": "percentage",
                "scale": 1,
                "rounding": "half-up",
                "leadingZero": False,
                "symbol": "percent",
            },
        },
        {
            "kind": "numeric-primitive",
            "id": "inningsNumber",
            "primitive": {
                "kind": "mixed-fraction",
                "denominator": 3,
                "integerSuffix": "回",
                "zeroRemainder": "omit-fraction",
                "fractionStyle": "ascii-numerator-slash-denominator",
            },
        },
        {
            "kind": "numeric-primitive",
            "id": "missingNumber",
            "primitive": {
                "kind": "null-substitute",
                "substitute": "−",
            },
        },
        {
            "kind": "enum-map",
            "id": "sideName",
            "enumId": "syntheticSide",
            "stability": "stable",
            "managedBy": "system",
            "members": [
                {"value": "left", "display": "左"},
                {"value": "right", "display": "右"},
            ],
        },
        {
            "kind": "template",
            "id": "pairedTemplate",
            "pattern": "[{left}|{right}]",
            "placeholders": {
                "left": copy.deepcopy(atom),
                "right": copy.deepcopy(atom),
            },
        },
    ]


def _intermediate(schemas: Any, scale: int = 1) -> dict[str, object]:
    """既存生成コアを通した合成表示宣言の中間表現を返す。"""
    model = _read_json(FIXTURE_ROOT / "model.json")
    manifest = _read_json(FIXTURE_ROOT / "manifest.json")
    rules = _display_rules(scale)
    model["displayRules"] = rules
    model["calculations"][0]["displayRuleRefs"] = [
        cast(str, rule["id"]) for rule in rules
    ]
    return CORE.generate_intermediate_representation(
        model,
        manifest,
        schemas,
        ROOT,
    )


def _target(schemas: Any, scale: int = 1) -> Any:
    """表示規則と formatter 呼出しを持つ固定の合成対象を返す。"""
    source = OPERATORS.DisplayMutationSource(
        intermediate=_intermediate(schemas, scale),
        invocation=OPERATORS.FormatterInvocation(
            rule_id="fixedNumber",
            numeric_value={"kind": "integer", "value": 7},
            language_value=7,
        ),
    )
    return ENGINE.SyntheticMutationTarget(
        calculation="syntheticDisplayCalculation",
        target_id="syntheticDisplayTarget",
        source=source,
    )


_PROBES = (
    (
        "fixedNumber",
        {"kind": "rational", "numerator": 1, "denominator": 8},
        None,
    ),
    (
        "percentageNumber",
        {"kind": "rational", "numerator": 1, "denominator": 200},
        None,
    ),
    (
        "inningsNumber",
        {"kind": "integer", "value": 2},
        None,
    ),
    ("missingNumber", None, None),
    ("sideName", "left", None),
    ("sideName", "right", None),
    ("pairedTemplate", None, {"left": "L", "right": "R"}),
)


def _formatter_function(intermediate: Any, schemas: Any) -> Callable[..., object]:
    """既存生成器の alpha Python formatter を実行可能にして返す。"""
    CORE.validate_intermediate_representation(intermediate, schemas)
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
    exec(compile(matches[0].content, "<display-mutant>", "exec"), namespace)
    function = namespace["_pitchlog_format"]
    assert callable(function)
    return cast(Callable[..., object], function)


def _outputs(source: Any, schemas: Any) -> tuple[object, ...]:
    """既存 formatter と指定された呼出経路の表示結果を返す。"""
    function = _formatter_function(source.intermediate, schemas)
    outputs = tuple(
        function(rule_id, value, atoms)
        for rule_id, value, atoms in _PROBES
    )
    invocation = source.invocation
    if invocation.route is OPERATORS.FormatterRoute.FORMATTER:
        callsite_output = function(
            invocation.rule_id,
            invocation.numeric_value,
        )
    elif invocation.route is OPERATORS.FormatterRoute.RAW_VALUE:
        callsite_output = invocation.language_value
    else:
        callsite_output = str(invocation.language_value)
    return (*outputs, callsite_output)


@dataclass(frozen=True, slots=True)
class _DisplayExecutor:
    """表示差または schema 違反をプロパティ層のkillとして記録する。"""

    original: Any
    schemas: Any

    def execute(self, mutant: Any) -> Any:
        """既存 formatter を実行し、元の表示結果との差を判定する。"""
        changed = mutant.mutated
        assert isinstance(changed, OPERATORS.DisplayMutationSource)
        expected = _outputs(self.original.source, self.schemas)
        try:
            actual = _outputs(changed, self.schemas)
        except (CORE.GenerationError, FORMATTER.FormatterGenerationError):
            return ENGINE.MutationExecution(
                True,
                (
                    ENGINE.KillEvidence(
                        mutant_id=mutant.mutant_id,
                        calculation=mutant.calculation,
                        layer=ENGINE.KillLayer.VECTOR,
                        check_id=f"{mutant.target_id}.display-schema",
                    ),
                ),
            )
        if actual == expected:
            return ENGINE.MutationExecution(False, ())
        return ENGINE.MutationExecution(
            True,
            (
                ENGINE.KillEvidence(
                    mutant_id=mutant.mutant_id,
                    calculation=mutant.calculation,
                    layer=ENGINE.KillLayer.PROPERTY_INVARIANT,
                    check_id=f"{mutant.target_id}.display-output",
                ),
            ),
        )


def _executor(target: Any, schemas: Any) -> _DisplayExecutor:
    """元の表示対象に束縛した実行器を返す。"""
    return _DisplayExecutor(target, schemas)


@pytest.mark.parametrize("kind", tuple(OPERATORS.DisplayMutationKind))
def test_each_display_family_generates_mutants_individually(
    kind: Any,
    schemas: Any,
) -> None:
    """表示系五系統がそれぞれ独立に mutant を生成する。"""
    target = _target(schemas)
    operator = OPERATORS.DISPLAY_OPERATORS[kind]

    generation = operator.generate(target)

    assert generation.mutants
    assert not generation.unsupported
    assert all(mutant.mutated != target.source for mutant in generation.mutants)
    assert all(
        mutant.mutated.mutation_kind is kind for mutant in generation.mutants
    )


def test_display_operator_mother_set_is_exactly_five() -> None:
    """表示系統と演算子の母集合が過不足なく5件であることを固定する。"""
    kinds = set(OPERATORS.DisplayMutationKind)

    assert len(kinds) == 5
    assert set(OPERATORS.DISPLAY_OPERATORS) == kinds


def test_compound_family_variants_are_all_generated(schemas: Any) -> None:
    """複数操作を持つ系統が削減されず全変異を生成する。"""
    target = _target(schemas)
    details_by_kind = {
        kind: {
            mutant.mutated.mutation_detail
            for mutant in operator.generate(target).mutants
        }
        for kind, operator in OPERATORS.DISPLAY_OPERATORS.items()
    }

    template = details_by_kind[OPERATORS.DisplayMutationKind.TEMPLATE_PLACEHOLDER]
    assert any("delete" in detail for detail in template)
    assert any("swap" in detail for detail in template)
    enum_map = details_by_kind[OPERATORS.DisplayMutationKind.ENUM_MAP]
    assert any("value" in detail for detail in enum_map)
    assert any("order" in detail for detail in enum_map)
    primitive = details_by_kind[OPERATORS.DisplayMutationKind.PRIMITIVE_PARAMETER]
    assert {detail.rsplit("-", maxsplit=1)[1] for detail in primitive} == {
        "scale",
        "rounding",
        "leadingZero",
        "symbol",
        "zeroRemainder",
    }
    invocation = details_by_kind[OPERATORS.DisplayMutationKind.FORMATTER_INVOCATION]
    assert any("delete-call" in detail for detail in invocation)
    assert any("language-default" in detail for detail in invocation)


def test_display_target_without_display_operator_fails(schemas: Any) -> None:
    """表示生成物を持つ対象で表示系演算子0件を拒否する。"""
    target = _target(schemas)

    with pytest.raises(ENGINE.MutationEngineError, match="表示系演算子がない"):
        OPERATORS.require_display_operator_application((target,), ())


@pytest.mark.parametrize("kind", tuple(OPERATORS.DisplayMutationKind))
def test_each_display_family_mutants_are_actually_killed(
    kind: Any,
    schemas: Any,
) -> None:
    """五系統のmutantを生成・実行し表示差またはschema違反でkillする。"""
    target = _target(schemas)
    operator = OPERATORS.DISPLAY_OPERATORS[kind]

    report = OPERATORS.run_display_mutations(
        (target,),
        (operator,),
        _executor(target, schemas),
    )

    result = report.calculations[0]
    assert report.complete
    assert result.generated
    assert result.killed == result.generated
    assert result.property_killed
    assert result.property_killed <= result.generated


def test_scale_zero_formatter_bypass_is_referred_not_killed(
    schemas: Any,
) -> None:
    """scale 0の既定文字列化をkillせず後続のPO台帳へ送る。"""
    target = _target(schemas, scale=0)
    operator = OPERATORS.DISPLAY_OPERATORS[
        OPERATORS.DisplayMutationKind.FORMATTER_INVOCATION
    ]
    generation = operator.generate(target)
    default_mutant = next(
        mutant
        for mutant in generation.mutants
        if "language-default" in mutant.mutated.mutation_detail
    )

    execution = _executor(target, schemas).execute(default_mutant)
    referrals = OPERATORS.equivalence_referrals(generation.mutants)

    assert not execution.killed
    assert default_mutant.equivalence_claimed
    assert [referral.mutant_id for referral in referrals] == [
        default_mutant.mutant_id
    ]
    assert referrals[0].ledger_path == "backend/domain/mutation-equivalents.json"
    assert referrals[0].required_judge == "PO"
    with pytest.raises(ENGINE.MutationEngineError, match="未記録の等価扱い"):
        OPERATORS.run_display_mutations(
            (target,),
            (operator,),
            _executor(target, schemas),
        )


def test_kill_and_equivalence_outcomes_are_unambiguous(schemas: Any) -> None:
    """同一mutant IDにkillと等価候補の二判定が成立しないことを実測する。"""
    operator = OPERATORS.DISPLAY_OPERATORS[
        OPERATORS.DisplayMutationKind.FORMATTER_INVOCATION
    ]
    killed: set[str] = set()
    equivalent: set[str] = set()
    for scale in (0, 1):
        target = _target(schemas, scale)
        generation = operator.generate(target)
        for mutant in generation.mutants:
            result = _executor(target, schemas).execute(mutant)
            if result.killed:
                killed.add(mutant.mutant_id)
            if mutant.equivalence_claimed:
                equivalent.add(mutant.mutant_id)

    assert killed
    assert equivalent
    assert killed.isdisjoint(equivalent)


def test_display_mutation_cost_record_has_measured_shape() -> None:
    """表示系コストが追記済みで、実測値そのものではなく形と積を検査する。"""
    asset = _read_json(COST_PATH)
    measurement = next(item for item in asset["measurements"] if item["step"] == 41)
    assert set(measurement) == {
        "step",
        "measuredAt",
        "measurementCommand",
        "environment",
        "syntheticTargets",
        "operatorFamilies",
        "estimatedTotalSeconds",
    }
    assert measurement["measurementCommand"]
    assert measurement["environment"]["python"]
    assert measurement["environment"]["platform"]
    assert measurement["syntheticTargets"]["familyCount"] == len(
        OPERATORS.DisplayMutationKind
    )
    estimated_total = 0.0
    for row in measurement["operatorFamilies"]:
        assert set(row) == {
            "family",
            "mutantCount",
            "suiteSamplesSeconds",
            "suiteSecondsPerMutant",
            "estimatedSeconds",
        }
        assert row["family"] in {
            kind.value for kind in OPERATORS.DisplayMutationKind
        }
        assert row["mutantCount"] > 0
        assert row["suiteSamplesSeconds"]
        assert all(sample > 0 for sample in row["suiteSamplesSeconds"])
        assert row["suiteSecondsPerMutant"] > 0
        assert math.isclose(
            row["estimatedSeconds"],
            row["mutantCount"] * row["suiteSecondsPerMutant"],
            rel_tol=1e-9,
        )
        estimated_total += row["estimatedSeconds"]
    assert {row["family"] for row in measurement["operatorFamilies"]} == {
        kind.value for kind in OPERATORS.DisplayMutationKind
    }
    assert math.isclose(
        measurement["estimatedTotalSeconds"],
        estimated_total,
        rel_tol=1e-9,
    )
