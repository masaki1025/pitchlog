"""変異テストの影響範囲と処理内部の時間予算を解決する。

`ADR-003 D-11 変異テスト規則` に従い、差分 PR は変更対象計算から
依存元を逆引きし、全面発火条件または逆引き不能時は全対象へ倒す。
変異の生成・実行・kill 判定は既存の変異エンジンへ委ねる。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

AUTHORITY_ID = "ADR-003 D-11 変異テスト規則"
FULL_TRIGGER_WORDING = (
    "発火条件は D-11(基盤・契約・入口・等価変異台帳・生成器・"
    "マニフェストの変更、および逆引き不能な変更)"
)
DIFF_BUDGET_SECONDS = 10 * 60
FULL_BUDGET_SECONDS = 30 * 60


class MutationScopeError(Exception):
    """影響範囲または時間予算の契約に適合しないことを表す。"""


class MutationTimeoutError(MutationScopeError):
    """処理内部の上限超過をマージ不可として表す。"""

    merge_allowed = False


class ScopeMode(StrEnum):
    """差分実行と全面実行の閉じた集合。"""

    DIFFERENTIAL = "differential"
    FULL = "full"


class FullRunTrigger(StrEnum):
    """ADR-003 D-11 が定める全面発火条件の七種。"""

    INFRASTRUCTURE = "infrastructure-change"
    CONTRACT = "contract-change"
    ENTRYPOINT = "entrypoint-change"
    EQUIVALENCE_LEDGER = "equivalence-ledger-change"
    GENERATOR = "generator-change"
    MANIFEST = "manifest-change"
    UNRESOLVED = "unresolved-change"


class ChangeKind(StrEnum):
    """影響範囲解決器が受け取る意味差分の閉じた集合。"""

    CALCULATION = "calculation"
    INFRASTRUCTURE = "infrastructure"
    CONTRACT = "contract"
    ENTRYPOINT = "entrypoint"
    EQUIVALENCE_LEDGER = "equivalence-ledger"
    GENERATOR = "generator"
    MANIFEST = "manifest"


_DIRECT_TRIGGERS = {
    ChangeKind.INFRASTRUCTURE: FullRunTrigger.INFRASTRUCTURE,
    ChangeKind.CONTRACT: FullRunTrigger.CONTRACT,
    ChangeKind.ENTRYPOINT: FullRunTrigger.ENTRYPOINT,
    ChangeKind.EQUIVALENCE_LEDGER: FullRunTrigger.EQUIVALENCE_LEDGER,
    ChangeKind.GENERATOR: FullRunTrigger.GENERATOR,
    ChangeKind.MANIFEST: FullRunTrigger.MANIFEST,
}


@dataclass(frozen=True, slots=True)
class SemanticChange:
    """パスではなく意味で分類済みの一変更。

    Attributes:
        kind: 対象計算の変更または全面発火に当たる変更種別。
        calculation: 対象計算変更のときだけ指定する計算 ID。
    """

    kind: ChangeKind
    calculation: str | None = None

    def __post_init__(self) -> None:
        """対象計算 ID の有無を変更種別と一致させる。"""
        if self.kind is ChangeKind.CALCULATION:
            if not self.calculation:
                raise ValueError("対象計算の変更に calculation ID がない")
        elif self.calculation is not None:
            raise ValueError("全面発火変更に calculation ID を指定できない")


@dataclass(frozen=True, slots=True)
class CalculationGraph:
    """対象計算と、その計算が直接依存する計算のグラフ。

    Attributes:
        calculations: 全対象計算の母集合。
        dependencies: 対象計算から直接依存先への対応。
    """

    calculations: frozenset[str]
    dependencies: Mapping[str, frozenset[str]]

    def __post_init__(self) -> None:
        """全面へ倒せるよう対象母集合の空だけを拒否する。"""
        if not self.calculations:
            raise ValueError("対象計算の母集合が空")


@dataclass(frozen=True, slots=True)
class MutationScopePlan:
    """解決済みの必須範囲と処理内部の上限。

    `required_calculations` を `selected_calculations` が包含することを型の
    構築時に検査し、対象を絞る操作で必須範囲を削れないようにする。
    """

    mode: ScopeMode
    all_calculations: frozenset[str]
    changed_calculations: frozenset[str]
    required_calculations: frozenset[str]
    selected_calculations: frozenset[str]
    triggers: frozenset[FullRunTrigger]
    budget_seconds: int

    def __post_init__(self) -> None:
        """差分・全面の範囲と時間予算を一体で検査する。"""
        if not self.required_calculations <= self.selected_calculations:
            raise ValueError("選択範囲が必須範囲を削っている")
        if not self.selected_calculations <= self.all_calculations:
            raise ValueError("選択範囲に未知の対象計算がある")
        if not self.changed_calculations <= self.required_calculations:
            raise ValueError("変更対象計算が必須範囲に含まれない")
        if self.mode is ScopeMode.FULL:
            if not self.triggers:
                raise ValueError("全面実行に発火条件がない")
            if self.selected_calculations != self.all_calculations:
                raise ValueError("全面実行が全対象計算を選択していない")
            if self.budget_seconds != FULL_BUDGET_SECONDS:
                raise ValueError("全面実行の内部上限が30分でない")
        else:
            if self.triggers:
                raise ValueError("差分実行に全面発火条件がある")
            if self.budget_seconds != DIFF_BUDGET_SECONDS:
                raise ValueError("差分実行の内部上限が10分でない")


def _graph_resolvable(graph: CalculationGraph) -> bool:
    """依存グラフが全対象について閉じているかを返す。"""
    if set(graph.dependencies) != set(graph.calculations):
        return False
    return all(
        dependencies <= graph.calculations
        for dependencies in graph.dependencies.values()
    )


def _dependent_closure(
    changed: frozenset[str],
    graph: CalculationGraph,
) -> frozenset[str]:
    """変更対象と、それへ直接・間接に依存する全対象を返す。"""
    required = set(changed)
    while True:
        additions = {
            calculation
            for calculation, dependencies in graph.dependencies.items()
            if dependencies.intersection(required)
        }
        expanded = required | additions
        if expanded == required:
            return frozenset(required)
        required = expanded


def _full_plan(
    graph: CalculationGraph,
    changed: frozenset[str],
    triggers: frozenset[FullRunTrigger],
) -> MutationScopePlan:
    """全対象と30分上限を持つ全面計画を返す。"""
    known_changed = changed & graph.calculations
    return MutationScopePlan(
        mode=ScopeMode.FULL,
        all_calculations=graph.calculations,
        changed_calculations=known_changed,
        required_calculations=graph.calculations,
        selected_calculations=graph.calculations,
        triggers=triggers,
        budget_seconds=FULL_BUDGET_SECONDS,
    )


def resolve_mutation_scope(
    changes: Iterable[SemanticChange],
    graph: CalculationGraph,
) -> MutationScopePlan:
    """意味差分から差分または全面の必須変異範囲を解決する。

    Args:
        changes: PR に含まれる分類済みの意味差分。
        graph: 対象計算と直接依存先の全グラフ。

    Returns:
        必須対象を削れない内部時間予算付き実行計画。
    """
    change_items = tuple(changes)
    changed = frozenset(
        change.calculation
        for change in change_items
        if change.kind is ChangeKind.CALCULATION
        and change.calculation is not None
    )
    direct_triggers = frozenset(
        _DIRECT_TRIGGERS[change.kind]
        for change in change_items
        if change.kind in _DIRECT_TRIGGERS
    )
    unresolved = not _graph_resolvable(graph) or bool(
        changed - graph.calculations
    )
    triggers = direct_triggers
    if unresolved:
        triggers = triggers | {FullRunTrigger.UNRESOLVED}
    if triggers:
        return _full_plan(graph, changed, frozenset(triggers))

    required = _dependent_closure(changed, graph)
    return MutationScopePlan(
        mode=ScopeMode.DIFFERENTIAL,
        all_calculations=graph.calculations,
        changed_calculations=changed,
        required_calculations=required,
        selected_calculations=required,
        triggers=frozenset(),
        budget_seconds=DIFF_BUDGET_SECONDS,
    )


Clock = Callable[[], float]
ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class MutationDeadline:
    """一回の変異処理が共有する単調時計の期限。"""

    mode: ScopeMode
    budget_seconds: int
    started_at: float
    _clock: Clock = field(repr=False, compare=False)

    @property
    def elapsed_seconds(self) -> float:
        """開始からの非負な経過秒を返す。"""
        return max(0.0, self._clock() - self.started_at)

    def checkpoint(self) -> None:
        """上限超過時に暫定結果を返さず例外にする。"""
        elapsed = self.elapsed_seconds
        if elapsed > self.budget_seconds:
            raise MutationTimeoutError(
                f"変異処理内部の上限超過: mode={self.mode.value}, "
                f"elapsed={elapsed}, budget={self.budget_seconds}"
            )


@dataclass(frozen=True, slots=True)
class BudgetExecution(Generic[ResultT]):
    """上限内で完了した変異処理だけが返せる結果。"""

    value: ResultT
    elapsed_seconds: float
    budget_seconds: int


def execute_with_internal_budget(
    plan: MutationScopePlan,
    operation: Callable[[MutationDeadline], ResultT],
    *,
    clock: Clock = time.monotonic,
) -> BudgetExecution[ResultT]:
    """差分10分・全面30分の処理内部上限で既存変異処理を包む。

    Args:
        plan: 影響範囲解決済みの実行計画。
        operation: 既存変異エンジンを呼ぶ処理。長い反復では渡された期限を
            checkpoint として利用できる。
        clock: 実行環境の単調時計。テストでは決定的な時計を注入する。

    Returns:
        上限内で完了した場合だけ得られる実行結果。

    Raises:
        MutationTimeoutError: 処理内部の上限を超えた場合。
    """
    started_at = clock()
    deadline = MutationDeadline(
        mode=plan.mode,
        budget_seconds=plan.budget_seconds,
        started_at=started_at,
        _clock=clock,
    )
    deadline.checkpoint()
    value = operation(deadline)
    deadline.checkpoint()
    return BudgetExecution(
        value=value,
        elapsed_seconds=deadline.elapsed_seconds,
        budget_seconds=deadline.budget_seconds,
    )


__all__ = [
    "AUTHORITY_ID",
    "DIFF_BUDGET_SECONDS",
    "FULL_BUDGET_SECONDS",
    "FULL_TRIGGER_WORDING",
    "BudgetExecution",
    "CalculationGraph",
    "ChangeKind",
    "FullRunTrigger",
    "MutationDeadline",
    "MutationScopeError",
    "MutationScopePlan",
    "MutationTimeoutError",
    "ScopeMode",
    "SemanticChange",
    "execute_with_internal_budget",
    "resolve_mutation_scope",
]
