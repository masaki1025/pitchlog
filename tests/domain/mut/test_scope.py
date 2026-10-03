"""変異処理の影響範囲解決と内部時間予算を検査する。"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
ADR_PATH = ROOT / "docs/adr/ADR-003-domain-calc-method.md"
AUTHORITIES_PATH = ROOT / "backend/domain/step-authorities.json"

sys.path.insert(0, str(BACKEND_SRC))
SCOPE = importlib.import_module("pitchlog.domainmut.scope")


@dataclass(slots=True)
class _Clock:
    """決定的な経過時間を返す合成単調時計。"""

    current: float = 100.0

    def __call__(self) -> float:
        """現在の合成時刻を返す。"""
        return self.current

    def advance(self, seconds: float) -> None:
        """合成時刻を指定秒だけ進める。"""
        self.current += seconds


def _graph() -> Any:
    """差分の依存元を二段逆引きできる合成グラフを返す。"""
    return SCOPE.CalculationGraph(
        calculations=frozenset(
            {"syntheticCore", "syntheticAggregate", "syntheticView", "isolated"}
        ),
        dependencies={
            "syntheticCore": frozenset(),
            "syntheticAggregate": frozenset({"syntheticCore"}),
            "syntheticView": frozenset({"syntheticAggregate"}),
            "isolated": frozenset(),
        },
    )


def _catalog_entry() -> dict[str, Any]:
    """変異テスト規則の典拠カタログ行を返す。"""
    document = json.loads(AUTHORITIES_PATH.read_text(encoding="utf-8"))
    entries = document["authorityCatalog"]
    return next(entry for entry in entries if entry["id"] == SCOPE.AUTHORITY_ID)


def _markdown_section(document: str, heading: str) -> str:
    """見出しの文字列で節を特定し、次の同階層見出しまでを返す。"""
    lines = document.splitlines()
    start = lines.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        candidate = lines[index]
        if candidate.startswith("#" * level + " "):
            end = index
            break
    return "\n".join(lines[start:end])


DIRECT_TRIGGER_CASES = (
    (SCOPE.ChangeKind.INFRASTRUCTURE, SCOPE.FullRunTrigger.INFRASTRUCTURE),
    (SCOPE.ChangeKind.CONTRACT, SCOPE.FullRunTrigger.CONTRACT),
    (SCOPE.ChangeKind.ENTRYPOINT, SCOPE.FullRunTrigger.ENTRYPOINT),
    (
        SCOPE.ChangeKind.EQUIVALENCE_LEDGER,
        SCOPE.FullRunTrigger.EQUIVALENCE_LEDGER,
    ),
    (SCOPE.ChangeKind.GENERATOR, SCOPE.FullRunTrigger.GENERATOR),
    (SCOPE.ChangeKind.MANIFEST, SCOPE.FullRunTrigger.MANIFEST),
)


def test_seven_full_run_trigger_kinds_are_fixed() -> None:
    """全面発火条件の母集合を七種に固定する。"""
    assert len(DIRECT_TRIGGER_CASES) + 1 == 7
    assert len(SCOPE.FullRunTrigger) == 7
    assert set(SCOPE.FullRunTrigger) == {
        expected for _, expected in DIRECT_TRIGGER_CASES
    } | {SCOPE.FullRunTrigger.UNRESOLVED}


@pytest.mark.parametrize(("kind", "expected"), DIRECT_TRIGGER_CASES)
def test_each_direct_trigger_selects_full_scope(kind: Any, expected: Any) -> None:
    """六種の直接発火条件を一種ずつ全面実行へ解決する。"""
    graph = _graph()

    plan = SCOPE.resolve_mutation_scope((SCOPE.SemanticChange(kind),), graph)

    assert plan.mode is SCOPE.ScopeMode.FULL
    assert plan.triggers == frozenset({expected})
    assert plan.selected_calculations == graph.calculations
    assert plan.budget_seconds == SCOPE.FULL_BUDGET_SECONDS == 30 * 60


def test_unresolved_calculation_selects_full_scope_fail_closed() -> None:
    """逆引き不能な対象計算を七つ目の条件として全面へ倒す。"""
    graph = _graph()

    plan = SCOPE.resolve_mutation_scope(
        (SCOPE.SemanticChange(SCOPE.ChangeKind.CALCULATION, "unknown"),),
        graph,
    )

    assert plan.mode is SCOPE.ScopeMode.FULL
    assert plan.triggers == frozenset({SCOPE.FullRunTrigger.UNRESOLVED})
    assert plan.selected_calculations == graph.calculations


def test_unclosed_dependency_graph_selects_full_scope_fail_closed() -> None:
    """依存関係を逆引きできないグラフも全面へ倒す。"""
    graph = SCOPE.CalculationGraph(
        calculations=frozenset({"syntheticCore", "syntheticView"}),
        dependencies={"syntheticCore": frozenset()},
    )

    plan = SCOPE.resolve_mutation_scope(
        (
            SCOPE.SemanticChange(
                SCOPE.ChangeKind.CALCULATION,
                "syntheticCore",
            ),
        ),
        graph,
    )

    assert plan.mode is SCOPE.ScopeMode.FULL
    assert SCOPE.FullRunTrigger.UNRESOLVED in plan.triggers


def test_trigger_wording_and_authority_exist_in_adr() -> None:
    """七種の逐語と条項 ID の典拠が ADR-003 に実在する。"""
    adr = ADR_PATH.read_text(encoding="utf-8")
    entry = _catalog_entry()
    section = _markdown_section(adr, entry["section"])

    assert entry["verbatim"] in section
    assert SCOPE.FULL_TRIGGER_WORDING in adr
    assert "PR 必須分の合計で 10 分" in section
    assert "全面が発火した PR は上限を 30 分" in section


def test_changed_calculation_and_transitive_dependents_complete_as_diff() -> None:
    """変更対象と依存元だけが十分快速に差分実行を完了する。"""
    plan = SCOPE.resolve_mutation_scope(
        (
            SCOPE.SemanticChange(
                SCOPE.ChangeKind.CALCULATION,
                "syntheticCore",
            ),
        ),
        _graph(),
    )
    clock = _Clock()
    visited: list[str] = []

    def run_selected(deadline: Any) -> tuple[str, ...]:
        """選択対象を処理しながら同じ内部期限を検査する。"""
        for calculation in sorted(plan.selected_calculations):
            visited.append(calculation)
            clock.advance(1.0)
            deadline.checkpoint()
        return tuple(visited)

    execution = SCOPE.execute_with_internal_budget(
        plan,
        run_selected,
        clock=clock,
    )

    assert plan.mode is SCOPE.ScopeMode.DIFFERENTIAL
    assert plan.changed_calculations == frozenset({"syntheticCore"})
    assert plan.required_calculations == frozenset(
        {"syntheticCore", "syntheticAggregate", "syntheticView"}
    )
    assert "isolated" not in plan.selected_calculations
    assert plan.budget_seconds == SCOPE.DIFF_BUDGET_SECONDS == 10 * 60
    assert execution.value == tuple(sorted(plan.required_calculations))


def test_required_diff_scope_cannot_be_reduced() -> None:
    """対象を絞る操作が変更対象と依存元を削ることを拒否する。"""
    plan = SCOPE.resolve_mutation_scope(
        (
            SCOPE.SemanticChange(
                SCOPE.ChangeKind.CALCULATION,
                "syntheticCore",
            ),
        ),
        _graph(),
    )

    with pytest.raises(ValueError, match="必須範囲"):
        dataclasses.replace(
            plan,
            selected_calculations=frozenset({"syntheticCore"}),
        )


@pytest.mark.parametrize(
    ("change", "seconds"),
    (
        (
            SCOPE.SemanticChange(
                SCOPE.ChangeKind.CALCULATION,
                "syntheticCore",
            ),
            10 * 60 + 1,
        ),
        (SCOPE.SemanticChange(SCOPE.ChangeKind.INFRASTRUCTURE), 30 * 60 + 1),
    ),
)
def test_internal_timeout_fails_without_provisional_merge(
    change: Any,
    seconds: int,
) -> None:
    """差分と全面の内部上限超過を暫定結果へ変換せず fail にする。"""
    plan = SCOPE.resolve_mutation_scope((change,), _graph())
    clock = _Clock()

    def exceed_budget(deadline: Any) -> None:
        """処理中に内部時間予算を超過する。"""
        clock.advance(seconds)
        deadline.checkpoint()

    with pytest.raises(SCOPE.MutationTimeoutError) as error:
        SCOPE.execute_with_internal_budget(
            plan,
            exceed_budget,
            clock=clock,
        )

    assert error.value.merge_allowed is False


def test_timeout_api_has_no_provisional_merge_switch() -> None:
    """上限超過を許す設定が内部時間予算 API に存在しない。"""
    parameters = inspect.signature(SCOPE.execute_with_internal_budget).parameters

    assert set(parameters) == {"plan", "operation", "clock"}
    assert all(
        word not in parameter.lower()
        for parameter in parameters
        for word in ("merge", "provisional", "nightly")
    )


def test_exact_internal_budget_is_still_accepted() -> None:
    """十分快の境界そのものは超過でないことを遷移として示す。"""
    plan = SCOPE.resolve_mutation_scope(
        (
            SCOPE.SemanticChange(
                SCOPE.ChangeKind.CALCULATION,
                "syntheticCore",
            ),
        ),
        _graph(),
    )
    clock = _Clock()

    def reach_boundary(deadline: Any) -> str:
        """上限と一致する時刻で checkpoint を通す。"""
        clock.advance(plan.budget_seconds)
        deadline.checkpoint()
        return "completed"

    execution = SCOPE.execute_with_internal_budget(
        plan,
        reach_boundary,
        clock=clock,
    )

    assert execution.value == "completed"
    assert execution.elapsed_seconds == plan.budget_seconds
