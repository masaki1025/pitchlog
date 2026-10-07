"""基準ステップ時点の見直しトリガー評価完了を検査する。

評価の現在件数を不変条件にせず、基準ステップ以前に期限を迎えた枠だけへ
完了を要求する。発火後の拒否はステップ 5 の停止ゲートへ委ねる。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from pitchlog.domaincheck import stopgate, trigger_evaluation

EXPECTED_TRIGGER_COUNT = 16
EXPECTED_MANUAL_EVIDENCE_COUNT = 9
MANUAL_EVIDENCE_PATH_ALLOWLIST = (
    "backend/domain",
    "backend/tests/domain/fixtures",
    "docs/features/domain-calc-dsl",
)


class TriggerCompletionError(Exception):
    """評価完了検査に適合しないことを表す。"""


class IncompleteEvaluationError(TriggerCompletionError):
    """基準ステップまでに必要な評価が未完了であることを表す。"""


class EvidenceLocationError(TriggerCompletionError):
    """手動判定の証拠パスが閉域または実在条件を破ることを表す。"""


class FiredTriggerError(TriggerCompletionError):
    """既存の停止ゲートが発火済みトリガーを拒否したことを表す。"""


@dataclass(frozen=True, slots=True)
class ManualEvidence:
    """PO を含む一判定と検査済み証拠パスを表す。"""

    trigger_id: int
    location: str
    resolved_path: Path


@dataclass(frozen=True, slots=True)
class CompletionReport:
    """基準ステップに束縛された評価完了結果を表す。

    Attributes:
        as_of_step: 評価期限を比較した基準ステップ。
        trigger_count: 資産から実測したトリガー母集合の大きさ。
        applicable_trigger_ids: 期限が基準ステップ以下の ID 集合。
        evaluated_trigger_ids: 適用対象のうち評価済みの ID 集合。
        manual_evidence: PO を含む九判定の実在証拠。
    """

    as_of_step: int
    trigger_count: int
    applicable_trigger_ids: frozenset[int]
    evaluated_trigger_ids: frozenset[int]
    manual_evidence: tuple[ManualEvidence, ...]


def _default_registry_path() -> Path:
    """リポジトリ配置の見直しトリガー資産を返す。"""
    backend_root = Path(__file__).resolve().parents[3]
    return backend_root / "domain/review-triggers.json"


def _default_repository_root() -> Path:
    """モジュール配置からリポジトリルートを返す。"""
    return Path(__file__).resolve().parents[4]


def _positive_step(value: object) -> int:
    """真偽値でない正の基準ステップを返す。"""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TriggerCompletionError("as-of は正の整数でなければならない")
    return value


def _raw_triggers(document: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """停止ゲート検査済み資産からトリガー行を返す。"""
    raw = document.get("triggers")
    if not isinstance(raw, list) or len(raw) != EXPECTED_TRIGGER_COUNT:
        raise TriggerCompletionError(
            f"トリガー母集合が {EXPECTED_TRIGGER_COUNT} 件でない"
        )
    rows: list[dict[str, object]] = []
    for index, value in enumerate(raw):
        if not isinstance(value, dict) or not all(
            isinstance(key, str) for key in value
        ):
            raise TriggerCompletionError(f"triggers[{index}] が object でない")
        rows.append(cast(dict[str, object], value))
    return tuple(rows)


def _is_within_allowed_roots(location: str) -> bool:
    """証拠パスが許可された三閉域の内側なら真を返す。

    権限の判定ではなくパスの所在判定である。`is_allowed` を含む名前は
    テナント境界の規約が「権限判定を自前で書く形」として禁じるため使わない
    (`tenant-boundary-bypass` 条件 1)。
    """
    candidate = PurePosixPath(location)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    normalized = candidate.as_posix()
    if location not in {normalized, f"{normalized}/"}:
        return False
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in MANUAL_EVIDENCE_PATH_ALLOWLIST
    )


def _resolve_evidence(root: Path, location: object, trigger_id: int) -> Path:
    """Allowlist 内で実在し、リポジトリ外へ出ない証拠を返す。"""
    if not isinstance(location, str) or not _is_within_allowed_roots(location):
        raise EvidenceLocationError(
            f"トリガー {trigger_id} の証拠パスが allowlist 外: {location!r}"
        )
    repository_root = root.resolve()
    try:
        resolved = (repository_root / location).resolve(strict=True)
        resolved.relative_to(repository_root)
    except (OSError, ValueError) as error:
        raise EvidenceLocationError(
            f"トリガー {trigger_id} の証拠が実在しないか閉域外: {location}"
        ) from error
    return resolved


def _manual_evidence(
    rows: Sequence[Mapping[str, object]], root: Path
) -> tuple[ManualEvidence, ...]:
    """PO を含む判定行を導出し、九件の証拠を検査する。"""
    evidence: list[ManualEvidence] = []
    for row in rows:
        judges = row.get("judge")
        if not isinstance(judges, list) or not all(
            isinstance(judge, str) for judge in judges
        ):
            raise TriggerCompletionError("judge が文字列 array でない")
        if "PO" not in judges:
            continue
        trigger_id = row.get("id")
        if not isinstance(trigger_id, int) or isinstance(trigger_id, bool):
            raise TriggerCompletionError("PO 判定行の id が整数でない")
        location = row.get("evidenceLocation")
        resolved = _resolve_evidence(root, location, trigger_id)
        evidence.append(
            ManualEvidence(
                trigger_id=trigger_id,
                location=cast(str, location),
                resolved_path=resolved,
            )
        )
    if len(evidence) != EXPECTED_MANUAL_EVIDENCE_COUNT:
        raise TriggerCompletionError(
            "PO を含む証拠行が "
            f"{EXPECTED_MANUAL_EVIDENCE_COUNT} 件でない: {len(evidence)}"
        )
    trigger_ids = [item.trigger_id for item in evidence]
    if len(trigger_ids) != len(set(trigger_ids)):
        raise TriggerCompletionError("PO を含む証拠行のトリガー ID が重複")
    return tuple(sorted(evidence, key=lambda item: item.trigger_id))


def validate_trigger_completion(
    registry_path: Path,
    repository_root: Path,
    as_of_step: int,
    *,
    evaluation_evidence_path: Path | None = None,
) -> CompletionReport:
    """基準ステップまでの評価・証拠・停止状態を検査する。

    Args:
        registry_path: `review-triggers.json` のパス。
        repository_root: 証拠パスを解決するリポジトリルート。
        as_of_step: 期限がこの値以下の評価を必須とする基準ステップ。
        evaluation_evidence_path: 評価の独立実測と PO 決定を持つ証拠資産。

    Returns:
        期限内完了・証拠実在・非発火を確認した結果。

    Raises:
        IncompleteEvaluationError: 対象期限の評価が一件でも未完了の場合。
        EvidenceLocationError: PO 判定の証拠が閉域外または不在の場合。
        FiredTriggerError: 既存停止ゲートが発火を検出した場合。
        TriggerCompletionError: その他の完了契約に適合しない場合。
        stopgate.StopgateExecutionError: トリガー資産の形が不正な場合。
    """
    as_of = _positive_step(as_of_step)
    states = stopgate.load_trigger_states(registry_path)
    if len(states) != EXPECTED_TRIGGER_COUNT:
        raise TriggerCompletionError(
            f"トリガー母集合が {EXPECTED_TRIGGER_COUNT} 件でない"
        )
    applicable = frozenset(
        state.trigger_id for state in states if state.evaluation_deadline <= as_of
    )
    evaluated = frozenset(
        state.trigger_id
        for state in states
        if state.evaluation_deadline <= as_of and state.fired is not None
    )
    missing = applicable - evaluated
    if missing:
        raise IncompleteEvaluationError(
            f"基準ステップ {as_of} までの未評価: {sorted(missing)!r}"
        )

    document = stopgate._read_json_object(registry_path)
    manual_evidence = _manual_evidence(_raw_triggers(document), repository_root)
    trigger_evaluation.validate_recorded_evaluations(
        document,
        repository_root,
        evidence_path=evaluation_evidence_path,
        trigger_ids=evaluated,
    )

    # 発火判定の意味はステップ 5 の単一実装へ委ねる。
    reasons = stopgate.rejection_reasons(states, as_of)
    if reasons:
        raise FiredTriggerError(" / ".join(reasons))
    return CompletionReport(
        as_of_step=as_of,
        trigger_count=len(states),
        applicable_trigger_ids=applicable,
        evaluated_trigger_ids=evaluated,
        manual_evidence=manual_evidence,
    )


def _as_of(value: str) -> int:
    """CLI の基準ステップを正の整数へ変換する。"""
    try:
        return _positive_step(int(value))
    except (ValueError, TriggerCompletionError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _parser() -> argparse.ArgumentParser:
    """評価完了検査の CLI パーサを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, type=_as_of)
    parser.add_argument("--registry", type=Path, default=_default_registry_path())
    parser.add_argument(
        "--root",
        type=Path,
        default=_default_repository_root(),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """完了なら 0、発火なら 2、その他の不適合なら 1 を返す。"""
    arguments = _parser().parse_args(argv)
    try:
        validate_trigger_completion(
            arguments.registry,
            arguments.root,
            arguments.as_of,
        )
    except FiredTriggerError as error:
        print(str(error), file=sys.stderr)
        return stopgate.EXIT_REJECT
    except (TriggerCompletionError, stopgate.StopgateExecutionError) as error:
        print(str(error), file=sys.stderr)
        return stopgate.EXIT_EXECUTION_ERROR
    return stopgate.EXIT_ALLOW


if __name__ == "__main__":
    raise SystemExit(main())
