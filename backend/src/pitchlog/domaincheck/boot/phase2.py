"""BOOT-GRANT の段階 2 適用除外を対象単位で判定する。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from pitchlog.domaincheck.boot.stall import StallState
from pitchlog.domaincheck.cli import (
    CheckerExecutionError,
    CheckerViolation,
    read_json,
)

_BOOT_SEAL_ASSET = Path("backend/domain/boot-seal.json")
_CHECK_SETS_ASSET = Path("backend/domain/check-sets.json")


@dataclass(frozen=True, slots=True)
class TargetDefinition:
    """対象欄から封印資産へ導出された対象。

    Attributes:
        identifier: 改名で変わらない安定 ID。
        name: 要件書の対象名。
        group: NFR-018 対象欄の導出グループ。
        ordinal: グループ内の安定位置。
    """

    identifier: str
    name: str
    group: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class TargetUniverse:
    """封印資産と導出規則が拘束する対象母集合。"""

    targets: tuple[TargetDefinition, ...]

    @property
    def identifiers(self) -> frozenset[str]:
        """安定 ID の集合を返す。"""
        return frozenset(target.identifier for target in self.targets)


@dataclass(frozen=True, slots=True)
class SemanticSnapshot:
    """対象ごとの 4 点を意味で収集したスナップショット。

    3 層検査はベクタ、プロパティ、変異の 3 集合に分ける。
    `None` は当該実測を判定できないことを表す。

    Attributes:
        declarations: 宣言モデルの正本を持つ対象 ID。
        generated: 生成物を持つ対象 ID。
        product_calls: 製品経路の呼び出し部を持つ対象 ID。
        vector_checks: 生のベクタ検査が緑の対象 ID。
        property_checks: 生のプロパティ検査が緑の対象 ID。
        mutation_checks: 生の変異検査が緑の対象 ID。
    """

    declarations: frozenset[str] | None
    generated: frozenset[str] | None
    product_calls: frozenset[str] | None
    vector_checks: frozenset[str] | None
    property_checks: frozenset[str] | None
    mutation_checks: frozenset[str] | None

    @classmethod
    def empty(cls) -> SemanticSnapshot:
        """全要素が実在しない判定可能なスナップショットを返す。"""
        empty = frozenset()
        return cls(empty, empty, empty, empty, empty, empty)

    @classmethod
    def missing(cls) -> SemanticSnapshot:
        """全要素が解決不能なスナップショットを返す。"""
        return cls(None, None, None, None, None, None)


class Phase2Status(StrEnum):
    """段階 2 判定の結果。"""

    NOT_PHASE2 = "not-phase2"
    PHASE2 = "phase2"
    INDETERMINATE_PHASE2 = "indeterminate-phase2"


@dataclass(frozen=True, slots=True)
class Phase2Decision:
    """対象単位の段階 2 判定と解消候補。

    Attributes:
        status: 段階 2 の適用状態。
        phase2_target_ids: BOOT-GRANT を適用除外にする対象 ID。
        resolution_target_ids: 4 点が同一変更に揃った解消候補。
        declaration_only_target_ids: 宣言だけが増えた対象 ID。
        partial_target_ids: 4 点の一部だけが増えた対象 ID。
        indeterminate_components: 実測できなかった構成要素。
        baseline_absence_treated_as_empty: 発効前例外を適用したか。
    """

    status: Phase2Status
    phase2_target_ids: frozenset[str]
    resolution_target_ids: frozenset[str]
    declaration_only_target_ids: frozenset[str]
    partial_target_ids: frozenset[str]
    indeterminate_components: tuple[str, ...]
    baseline_absence_treated_as_empty: bool

    @property
    def is_phase2(self) -> bool:
        """段階 2 として扱うなら `True` を返す。"""
        return self.status != Phase2Status.NOT_PHASE2


@dataclass(frozen=True, slots=True)
class _SemanticDelta:
    """同一 PR が増やした意味要素。"""

    declarations: frozenset[str]
    generated: frozenset[str]
    product_calls: frozenset[str]
    vector_checks: frozenset[str]
    property_checks: frozenset[str]
    mutation_checks: frozenset[str]

    @property
    def changed_targets(self) -> frozenset[str]:
        """意味要素が 1 つ以上増えた対象を返す。"""
        return frozenset().union(
            self.declarations,
            self.generated,
            self.product_calls,
            self.vector_checks,
            self.property_checks,
            self.mutation_checks,
        )

    @property
    def complete_targets(self) -> frozenset[str]:
        """4 点と 3 層すべてが同一 PR で増えた対象を返す。"""
        return (
            self.declarations
            & self.generated
            & self.product_calls
            & self.vector_checks
            & self.property_checks
            & self.mutation_checks
        )


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーの JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckerExecutionError(f"{label}が JSON object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise CheckerExecutionError(f"{label}が JSON array でない")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise CheckerExecutionError(f"{label}が空でない文字列でない")
    return value


def _positive_integer(value: object, label: str) -> int:
    """Boolean でない正の整数を返す。"""
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CheckerExecutionError(f"{label}が正の整数でない")
    return value


def load_target_universe(
    root: Path,
    *,
    read_asset: Callable[[Path], object] = read_json,
) -> TargetUniverse:
    """封印資産と対象導出規則から母集合を読む。

    Args:
        root: リポジトリルート。
        read_asset: 読み取った規範資産を呼出側が観測できる JSON reader。

    Returns:
        要件書対象欄に由来する安定 ID と名称の母集合。

    Raises:
        CheckerExecutionError: 資産の形または導出元の接続が不正な場合。
    """
    boot_seal = _object(read_asset(root / _BOOT_SEAL_ASSET), "boot-seal")
    check_sets = _object(read_asset(root / _CHECK_SETS_ASSET), "check-sets")
    sources = _object(boot_seal.get("sources"), "boot-seal.sources")
    target_rule = _object(
        sources.get("targetRule"),
        "boot-seal.sources.targetRule",
    )
    selector = _string(target_rule.get("selector"), "targetRule.selector")
    source = _string(target_rule.get("path"), "targetRule.path")
    if source != _CHECK_SETS_ASSET.as_posix() or selector != "targetDerivation":
        raise CheckerExecutionError("封印資産の対象導出元が不正")
    derivation = _object(check_sets.get(selector), "targetDerivation")
    if derivation.get("combination") != "set-union":
        raise CheckerExecutionError("対象導出規則が set-union でない")
    groups = _array(derivation.get("groups"), "targetDerivation.groups")
    group_ids = {
        _string(_object(group, "targetDerivation.groups[]").get("id"), "group.id")
        for group in groups
    }
    if not group_ids or len(group_ids) != len(groups):
        raise CheckerExecutionError("対象導出グループが空または重複している")

    derived = _object(boot_seal.get("derivedInputs"), "derivedInputs")
    raw_targets = _array(derived.get("targets"), "derivedInputs.targets")
    targets: list[TargetDefinition] = []
    positions: set[tuple[str, int]] = set()
    for index, raw_target in enumerate(raw_targets):
        target = _object(raw_target, f"derivedInputs.targets[{index}]")
        identifier = _string(target.get("id"), f"targets[{index}].id")
        name = _string(target.get("name"), f"targets[{index}].name")
        group = _string(target.get("group"), f"targets[{index}].group")
        ordinal = _positive_integer(
            target.get("ordinal"),
            f"targets[{index}].ordinal",
        )
        if group not in group_ids:
            raise CheckerExecutionError(f"対象 {identifier} の導出グループが未登録")
        position = (group, ordinal)
        if position in positions:
            raise CheckerExecutionError("対象の導出位置が重複している")
        positions.add(position)
        targets.append(TargetDefinition(identifier, name, group, ordinal))
    identifiers = [target.identifier for target in targets]
    names = [target.name for target in targets]
    if not targets:
        raise CheckerExecutionError("対象母集合が空である")
    if len(set(identifiers)) != len(identifiers):
        raise CheckerExecutionError("対象 ID が重複している")
    if len(set(names)) != len(names):
        raise CheckerExecutionError("対象名が重複している")
    return TargetUniverse(tuple(targets))


def _evidence_values(
    snapshot: SemanticSnapshot,
) -> tuple[tuple[str, frozenset[str] | None], ...]:
    """スナップショットの意味要素を名前付きで返す。"""
    return (
        ("declarations", snapshot.declarations),
        ("generated", snapshot.generated),
        ("product_calls", snapshot.product_calls),
        ("vector_checks", snapshot.vector_checks),
        ("property_checks", snapshot.property_checks),
        ("mutation_checks", snapshot.mutation_checks),
    )


def _validate_evidence(snapshot: SemanticSnapshot, label: str) -> None:
    """実測値の型と ID の形を検査する。"""
    for component, values in _evidence_values(snapshot):
        if values is None:
            continue
        if not isinstance(values, frozenset) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise CheckerExecutionError(
                f"{label}.{component}が空でない ID の frozenset でない"
            )


def _normalise_before(
    state: StallState,
    before: SemanticSnapshot,
) -> tuple[SemanticSnapshot, bool]:
    """発効前だけ比較元の資産不在を空集合にする。"""
    if state.effective:
        return before, False
    empty = frozenset()
    values = dict(_evidence_values(before))
    replaced = any(value is None for value in values.values())
    return (
        SemanticSnapshot(
            declarations=values["declarations"] or empty,
            generated=values["generated"] or empty,
            product_calls=values["product_calls"] or empty,
            vector_checks=values["vector_checks"] or empty,
            property_checks=values["property_checks"] or empty,
            mutation_checks=values["mutation_checks"] or empty,
        ),
        replaced,
    )


def _indeterminate_components(
    before: SemanticSnapshot,
    after: SemanticSnapshot,
) -> tuple[str, ...]:
    """前後のいずれかを観測できない意味要素を返す。"""
    before_values = dict(_evidence_values(before))
    after_values = dict(_evidence_values(after))
    return tuple(
        component
        for component in before_values
        if before_values[component] is None or after_values[component] is None
    )


def _delta(before: SemanticSnapshot, after: SemanticSnapshot) -> _SemanticDelta:
    """判定可能な前後差から意味要素の追加集合を返す。"""
    before_values = dict(_evidence_values(before))
    after_values = dict(_evidence_values(after))
    additions: dict[str, frozenset[str]] = {}
    for component in before_values:
        previous = before_values[component]
        current = after_values[component]
        if previous is None or current is None:
            raise CheckerExecutionError("判定不能な意味要素の差分は取れない")
        additions[component] = current - previous
    return _SemanticDelta(
        declarations=additions["declarations"],
        generated=additions["generated"],
        product_calls=additions["product_calls"],
        vector_checks=additions["vector_checks"],
        property_checks=additions["property_checks"],
        mutation_checks=additions["mutation_checks"],
    )


def classify_phase2(
    state: StallState,
    universe: TargetUniverse,
    before: SemanticSnapshot,
    after: SemanticSnapshot,
) -> Phase2Decision:
    """同一 PR の意味差分を対象単位で段階 2 判定する。

    Args:
        state: ステップ 17 が定義する発効・昇格状態。
        universe: 封印資産と導出規則から読んだ対象母集合。
        before: PR 適用前の意味実測。
        after: PR 適用後の意味実測。

    Returns:
        対象ごとの適用除外と解消候補を持つ判定。

    Raises:
        CheckerExecutionError: 入力の形が不正な場合。
        CheckerViolation: 未分類対象または 2 対象以上の追加の場合。
    """
    _validate_evidence(before, "before")
    _validate_evidence(after, "after")
    if not universe.targets:
        raise CheckerExecutionError("対象母集合が空である")
    target_ids = universe.identifiers
    after_declarations = after.declarations
    if after_declarations is not None:
        unknown_declarations = after_declarations - target_ids
        if unknown_declarations:
            raise CheckerViolation(
                f"NFR-018 柱書: 対象欄にない宣言={sorted(unknown_declarations)!r}"
            )

    normalised_before, baseline_empty = _normalise_before(state, before)
    indeterminate = _indeterminate_components(normalised_before, after)
    if indeterminate:
        return Phase2Decision(
            status=Phase2Status.INDETERMINATE_PHASE2,
            phase2_target_ids=target_ids,
            resolution_target_ids=frozenset(),
            declaration_only_target_ids=frozenset(),
            partial_target_ids=frozenset(),
            indeterminate_components=indeterminate,
            baseline_absence_treated_as_empty=baseline_empty,
        )

    delta = _delta(normalised_before, after)
    unknown = delta.changed_targets - target_ids
    if unknown:
        raise CheckerViolation(
            f"NFR-018 柱書: 未分類対象の意味差分={sorted(unknown)!r}"
        )
    complete = delta.complete_targets
    if len(complete) >= 2:
        raise CheckerViolation(
            f"ADR-003 帰結 1 段階 2: 対象計算は 1 件ごとに追加する={sorted(complete)!r}"
        )
    other_additions = (
        delta.generated
        | delta.product_calls
        | delta.vector_checks
        | delta.property_checks
        | delta.mutation_checks
    )
    declaration_only = delta.declarations - other_additions
    partial = delta.changed_targets - complete - declaration_only
    status = Phase2Status.PHASE2 if complete else Phase2Status.NOT_PHASE2
    return Phase2Decision(
        status=status,
        phase2_target_ids=complete,
        resolution_target_ids=complete,
        declaration_only_target_ids=declaration_only,
        partial_target_ids=partial,
        indeterminate_components=(),
        baseline_absence_treated_as_empty=baseline_empty,
    )


def evaluate_phase2(
    root: Path,
    state: StallState,
    before: SemanticSnapshot,
    after: SemanticSnapshot,
    *,
    read_asset: Callable[[Path], object] = read_json,
) -> Phase2Decision:
    """資産から母集合を読み、PR の意味差分を判定する。

    Args:
        root: リポジトリルート。
        state: ステップ 17 が定義する状態。
        before: PR 適用前の意味実測。
        after: PR 適用後の意味実測。
        read_asset: 読み取った規範資産を呼出側が観測できる JSON reader。

    Returns:
        対象単位の段階 2 判定。
    """
    return classify_phase2(
        state,
        load_target_universe(root, read_asset=read_asset),
        before,
        after,
    )
