"""既存の BOOT 機構が出した免除前の生結果を一つの判定へ束ねる。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NoReturn, cast

from pitchlog.domaincheck import boot_seal
from pitchlog.domaincheck.boot import clauses, phase2, report, stall
from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    EXIT_NONCONFORMING,
    CheckerExecutionError,
    CheckerViolation,
    exact_set_difference,
    read_json,
)

_RAW_EVIDENCE_STAGE = "raw-unexempted-checks"
_EVIDENCE_KEYS = frozenset(
    {"schemaVersion", "evidenceStage", "clauseResults"}
)
_RESULT_KEYS = frozenset({"clauseId", "outcome"})


class RawOutcome(StrEnum):
    """免除を適用していない個別検査の結果。"""

    CONFORMING = "conforming"
    NONCONFORMING = "nonconforming"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class RawClauseResult:
    """一つの条項に対する免除前の結果。

    Attributes:
        clause_id: ステップ 20 の対応表から得た条項 ID。
        outcome: 免除を適用する前の検査結果。
    """

    clause_id: str
    outcome: RawOutcome


@dataclass(frozen=True, slots=True)
class RawUnexemptedResults:
    """免除後の状態を表現できない生結果の専用型。

    Attributes:
        clause_results: 条項ごとの免除前の結果。
    """

    clause_results: tuple[RawClauseResult, ...]


RouteDetector = Callable[
    [Mapping[str, RawClauseResult], str],
    RawOutcome,
]


@dataclass(frozen=True, slots=True)
class DetectionRoute:
    """条項対応表の一行と実行可能な検出経路の接続。

    Attributes:
        clause_id: 経路が担当する条項 ID。
        criterion_authority: 違背判定の典拠。
        detector: 免除前の結果だけを読む検出関数。
    """

    clause_id: str
    criterion_authority: str
    detector: RouteDetector


@dataclass(frozen=True, slots=True)
class ExistingMechanisms:
    """再実装せずに束ねる既存機構の入口。

    Attributes:
        seal_verifier: ステップ 16 の固定封印検証。
        state_activator: ステップ 17 の発効遷移。
        state_observer: ステップ 17 の停滞・昇格遷移。
        state_reapprover: ステップ 17 の履歴に基づく再承認。
        phase2_evaluator: ステップ 18 の対象単位判定。
        report_acceptor: ステップ 19 の出力を含む緑の検証。
        clause_loader: ステップ 20 の正本逆引きと対応表検証。
    """

    seal_verifier: Callable[[Path], int]
    state_activator: Callable[[stall.StallState, str], stall.StallState]
    state_observer: Callable[[stall.StallState, str, int], stall.StallState]
    state_reapprover: Callable[
        [Path, stall.StallState, str, str, str],
        stall.StallState,
    ]
    phase2_evaluator: Callable[
        [
            Path,
            stall.StallState,
            phase2.SemanticSnapshot,
            phase2.SemanticSnapshot,
        ],
        phase2.Phase2Decision,
    ]
    report_acceptor: Callable[
        [Path, Collection[str]],
        dict[str, object],
    ]
    clause_loader: Callable[[Path], tuple[clauses.DerivedClause, ...]]


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を判定不能へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを判定不能として送出する。"""
        raise CheckerExecutionError(message)


def existing_mechanisms() -> ExistingMechanisms:
    """ステップ 16〜20 の既存機構を同一オブジェクトへ束ねる。"""
    return ExistingMechanisms(
        seal_verifier=boot_seal.verify_boot_seal,
        state_activator=stall.activate,
        state_observer=stall.observe_pr_integration,
        state_reapprover=stall.reapprove_from_git,
        phase2_evaluator=phase2.evaluate_phase2,
        report_acceptor=report.accept_transition_green,
        clause_loader=clauses.load_and_validate_registry,
    )


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ JSON object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
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


def _exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    """JSON object のキー集合を厳密に検査する。"""
    observed = frozenset(value)
    difference = exact_set_difference(expected, observed)
    if not difference.matches:
        raise CheckerExecutionError(
            f"{label}のキー集合が不一致: "
            f"不足={sorted(difference.missing)!r}, "
            f"未登録={sorted(difference.unexpected)!r}"
        )


def _raw_outcome(
    results: Mapping[str, RawClauseResult],
    clause_id: str,
) -> RawOutcome:
    """指定条項の免除前の結果をそのまま返す。"""
    try:
        return results[clause_id].outcome
    except KeyError as error:
        raise CheckerExecutionError(
            f"免除前の結果がない: {clause_id}"
        ) from error


def _registry_entries(root: Path) -> tuple[dict[str, object], ...]:
    """検証済み対応表から条項行を返す。"""
    asset = _object(
        read_json(root / clauses.BOOT_CLAUSES_ASSET),
        "boot-clauses",
    )
    raw_entries = _array(asset.get("clauses"), "boot-clauses.clauses")
    return tuple(
        _object(entry, f"boot-clauses.clauses[{index}]")
        for index, entry in enumerate(raw_entries)
    )


def build_detection_routes(
    root: Path,
    mechanisms: ExistingMechanisms | None = None,
) -> tuple[DetectionRoute, ...]:
    """対応表を正として全条項の検出経路を生成する。

    Args:
        root: リポジトリルート。
        mechanisms: 差し替え可能な既存機構の束。省略時は製品実装を使う。

    Returns:
        対応表と同じ順序で一条項一経路を持つ検出経路列。
    """
    bundle = existing_mechanisms() if mechanisms is None else mechanisms
    derived = bundle.clause_loader(root)
    entries = _registry_entries(root)
    if len(entries) != len(derived):
        raise CheckerViolation("条項対応表と逆引き結果の件数が一致しない")
    routes: list[DetectionRoute] = []
    for clause, entry in zip(derived, entries, strict=True):
        detection = _object(
            entry.get("violationDetection"),
            f"boot-clauses.{clause.identifier}.violationDetection",
        )
        authority = _string(
            detection.get("criterionAuthority"),
            f"boot-clauses.{clause.identifier}.criterionAuthority",
        )
        routes.append(
            DetectionRoute(
                clause_id=clause.identifier,
                criterion_authority=authority,
                detector=_raw_outcome,
            )
        )
    assert_route_coverage(
        frozenset(clause.identifier for clause in derived),
        routes,
    )
    return tuple(routes)


def assert_route_coverage(
    required_clause_ids: Collection[str],
    routes: Collection[DetectionRoute],
) -> None:
    """対応表と実装経路の集合差および重複がないことを要求する。"""
    required = frozenset(required_clause_ids)
    route_ids = tuple(route.clause_id for route in routes)
    if len(route_ids) != len(set(route_ids)):
        raise CheckerViolation("同じ条項に検出経路が重複している")
    difference = exact_set_difference(required, frozenset(route_ids))
    if not difference.matches:
        raise CheckerViolation(
            "条項対応表と検出経路の集合差がある: "
            f"不足={sorted(difference.missing)!r}, "
            f"未登録={sorted(difference.unexpected)!r}"
        )


def parse_raw_results(value: object) -> RawUnexemptedResults:
    """機械可読入力を免除前の生結果専用型へ変換する。"""
    root = _object(value, "judge evidence")
    _exact_keys(root, _EVIDENCE_KEYS, "judge evidence")
    if root.get("schemaVersion") != 1:
        raise CheckerExecutionError("judge evidence.schemaVersionが 1 でない")
    if root.get("evidenceStage") != _RAW_EVIDENCE_STAGE:
        raise CheckerExecutionError(
            "judge evidenceは免除前の生結果でなければならない"
        )
    raw_results = _array(root.get("clauseResults"), "clauseResults")
    results: list[RawClauseResult] = []
    for index, raw_result in enumerate(raw_results):
        label = f"clauseResults[{index}]"
        result = _object(raw_result, label)
        _exact_keys(result, _RESULT_KEYS, label)
        clause_id = _string(result.get("clauseId"), f"{label}.clauseId")
        raw_outcome = _string(result.get("outcome"), f"{label}.outcome")
        try:
            outcome = RawOutcome(raw_outcome)
        except ValueError as error:
            raise CheckerExecutionError(
                f"{label}.outcomeが未知である: {raw_outcome}"
            ) from error
        results.append(RawClauseResult(clause_id, outcome))
    identifiers = [result.clause_id for result in results]
    if len(identifiers) != len(set(identifiers)):
        raise CheckerExecutionError("免除前の条項結果 ID が重複している")
    return RawUnexemptedResults(tuple(results))


def outcome_from_exit_code(exit_code: int) -> RawOutcome:
    """既存機構の 0・1・2 契約を免除前の結果型へ変換する。"""
    outcomes = {
        EXIT_CONFORMING: RawOutcome.CONFORMING,
        EXIT_NONCONFORMING: RawOutcome.NONCONFORMING,
        EXIT_INDETERMINATE: RawOutcome.INDETERMINATE,
    }
    try:
        return outcomes[exit_code]
    except KeyError as error:
        raise CheckerExecutionError(
            f"既存機構が未知の exit コードを返した: {exit_code}"
        ) from error


def run_raw_check(check: Callable[[], object]) -> RawOutcome:
    """既存機構を免除せず実行し、共通結果へ変換する。"""
    try:
        check()
    except CheckerViolation:
        return RawOutcome.NONCONFORMING
    except CheckerExecutionError:
        return RawOutcome.INDETERMINATE
    return RawOutcome.CONFORMING


def judge_raw_results(
    root: Path,
    raw_results: RawUnexemptedResults,
    mechanisms: ExistingMechanisms | None = None,
) -> int:
    """全条項の免除前の結果を 0・1・2 の判定へ集約する。

    判定不能は全体を fail-closed にするため、不適合より先に返す。

    Args:
        root: リポジトリルート。
        raw_results: 免除後の状態を表現できない専用型の生結果。
        mechanisms: 差し替え可能な既存機構の束。

    Returns:
        適合は 0、不適合は 1、判定不能は 2。

    Raises:
        CheckerExecutionError: 生結果の母集合が不足または過剰な場合。
        CheckerViolation: 対応表と検出経路の集合差がある場合。
    """
    routes = build_detection_routes(root, mechanisms)
    results_by_id = {
        result.clause_id: result for result in raw_results.clause_results
    }
    required_ids = frozenset(route.clause_id for route in routes)
    observed_ids = frozenset(results_by_id)
    difference = exact_set_difference(required_ids, observed_ids)
    if not difference.matches:
        raise CheckerExecutionError(
            "免除前の条項結果と検出経路の集合差がある: "
            f"不足={sorted(difference.missing)!r}, "
            f"未登録={sorted(difference.unexpected)!r}"
        )
    outcomes = tuple(
        route.detector(results_by_id, route.clause_id) for route in routes
    )
    if RawOutcome.INDETERMINATE in outcomes:
        return EXIT_INDETERMINATE
    if RawOutcome.NONCONFORMING in outcomes:
        return EXIT_NONCONFORMING
    return EXIT_CONFORMING


def _default_root() -> Path:
    """モジュール配置からリポジトリルートを返す。"""
    return Path(__file__).resolve().parents[5]


def _repository_path(root: Path, path: Path) -> Path:
    """リポジトリ内の入力ファイルを解決する。"""
    resolved_root = root.resolve()
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise CheckerExecutionError("--evidenceがリポジトリ外を指している") from error
    return resolved


def _parser() -> argparse.ArgumentParser:
    """移行判定器 CLI の引数パーサを返す。"""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_default_root())
    parser.add_argument("--evidence", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """免除前の全条項結果を読み、exit コードを分離して返す。"""
    try:
        arguments = _parser().parse_args(argv)
        root = arguments.root.resolve()
        if not root.is_dir():
            raise CheckerExecutionError(f"リポジトリルートを読めない: {root}")
        evidence_path = _repository_path(root, arguments.evidence)
        raw_results = parse_raw_results(read_json(evidence_path))
        return judge_raw_results(root, raw_results)
    except CheckerViolation as error:
        print(f"不適合: {error}", file=sys.stderr)
        return EXIT_NONCONFORMING
    except CheckerExecutionError as error:
        print(f"判定不能: {error}", file=sys.stderr)
        return EXIT_INDETERMINATE


if __name__ == "__main__":
    raise SystemExit(main())
