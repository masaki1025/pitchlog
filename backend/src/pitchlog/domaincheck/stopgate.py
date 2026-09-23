"""見直しトリガーの評価結果から後続ステップの停止を判定する。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, Sequence

EXIT_ALLOW = 0
EXIT_EXECUTION_ERROR = 1
EXIT_REJECT = 2

_TOP_LEVEL_KEYS = {
    "version",
    "authority",
    "poName",
    "evaluationStepDerivation",
    "triggers",
}
_TRIGGER_KEYS = {
    "id",
    "description",
    "evaluationSteps",
    "evaluationDeadline",
    "evaluationMethod",
    "judge",
    "evidenceLocation",
    "firingCondition",
    "evaluation",
}
_EXPECTED_TRIGGER_IDS = set(range(1, 17))


class StopgateExecutionError(Exception):
    """停止ゲート自身を実行できない入力を表す。"""


class _ArgumentParser(argparse.ArgumentParser):
    """CLI 引数不備を exit 1 へ変換できるパーサ。"""

    def error(self, message: str) -> NoReturn:
        """構文エラーをゲート実行不能の例外として送出する。"""
        raise StopgateExecutionError(message)


@dataclass(frozen=True, slots=True)
class TriggerState:
    """停止判定に必要なトリガーの状態。

    Attributes:
        trigger_id: トリガー ID。
        evaluation_deadline: 評価を完了すべき最後のステップ。
        fired: 発火なら `True`、非発火なら `False`、未評価なら `None`。
    """

    trigger_id: int
    evaluation_deadline: int
    fired: bool | None


def _default_registry_path() -> Path:
    """リポジトリ配置の見直しトリガー資産パスを返す。"""
    backend_root = Path(__file__).resolve().parents[3]
    return backend_root / "domain/review-triggers.json"


def _default_repository_root() -> Path:
    """モジュール配置からリポジトリルートを返す。"""
    return Path(__file__).resolve().parents[4]


def _expect_int(value: object, label: str) -> int:
    """真偽値型を除く正の整数を受理する。"""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise StopgateExecutionError(f"{label}は正の整数でなければならない")
    return value


def _expect_nonempty_string(value: object, label: str) -> str:
    """空でない文字列を受理する。"""
    if not isinstance(value, str) or not value:
        raise StopgateExecutionError(f"{label}は空でない文字列でなければならない")
    return value


def _read_json_object(path: Path) -> dict[str, object]:
    """評価枠資産を JSON object として読み込む。"""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StopgateExecutionError(
            f"評価枠資産を読めない: {path}: {error}"
        ) from error
    if not isinstance(document, dict) or not all(
        isinstance(key, str) for key in document
    ):
        raise StopgateExecutionError("評価枠資産は JSON object でなければならない")
    return document


def _parse_evaluation(value: object, label: str) -> bool | None:
    """未評価と発火・非発火の評価レコードを解釈する。"""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"fired"}:
        raise StopgateExecutionError(
            f"{label}は null または fired だけの object である"
        )
    fired = value["fired"]
    if not isinstance(fired, bool):
        raise StopgateExecutionError(f"{label}.firedは boolean でなければならない")
    return fired


def _parse_trigger(raw: object, index: int) -> TriggerState:
    """1 件のトリガー枠を検査し、停止判定用状態へ変換する。"""
    label = f"triggers[{index}]"
    if not isinstance(raw, dict):
        raise StopgateExecutionError(f"{label}は object でなければならない")
    if set(raw) != _TRIGGER_KEYS:
        raise StopgateExecutionError(f"{label}のキー集合が不正である")

    trigger_id = _expect_int(raw["id"], f"{label}.id")
    deadline = _expect_int(raw["evaluationDeadline"], f"{label}.evaluationDeadline")
    evaluation_steps = raw["evaluationSteps"]
    if not isinstance(evaluation_steps, list) or not evaluation_steps:
        raise StopgateExecutionError(f"{label}.evaluationStepsは空でない array である")
    step_ids = [
        _expect_int(step_id, f"{label}.evaluationSteps") for step_id in evaluation_steps
    ]
    if len(step_ids) != len(set(step_ids)) or deadline != max(step_ids):
        raise StopgateExecutionError(f"{label}の評価ステップと期限が不正である")

    _expect_nonempty_string(raw["description"], f"{label}.description")
    _expect_nonempty_string(raw["evidenceLocation"], f"{label}.evidenceLocation")
    _expect_nonempty_string(raw["firingCondition"], f"{label}.firingCondition")
    if not isinstance(raw["evaluationMethod"], dict):
        raise StopgateExecutionError(
            f"{label}.evaluationMethodは object でなければならない"
        )
    if not isinstance(raw["judge"], list) or not raw["judge"]:
        raise StopgateExecutionError(f"{label}.judgeは空でない array である")

    return TriggerState(
        trigger_id=trigger_id,
        evaluation_deadline=deadline,
        fired=_parse_evaluation(raw["evaluation"], f"{label}.evaluation"),
    )


def load_trigger_states(path: Path) -> tuple[TriggerState, ...]:
    """評価枠資産を検査し、全トリガーの状態を返す。

    Args:
        path: 読み込む `review-triggers.json` のパス。

    Returns:
        ID 順のトリガー状態。

    Raises:
        StopgateExecutionError: 資産を読めないか形式が不正な場合。
    """
    document = _read_json_object(path)
    if set(document) != _TOP_LEVEL_KEYS or document.get("version") != 1:
        raise StopgateExecutionError("評価枠資産のトップレベルが不正である")
    raw_triggers = document.get("triggers")
    if not isinstance(raw_triggers, list) or len(raw_triggers) != 16:
        raise StopgateExecutionError(
            "評価枠資産は 16 件のトリガーを持たなければならない"
        )

    states = tuple(_parse_trigger(raw, index) for index, raw in enumerate(raw_triggers))
    trigger_ids = [state.trigger_id for state in states]
    if set(trigger_ids) != _EXPECTED_TRIGGER_IDS or len(trigger_ids) != len(
        set(trigger_ids)
    ):
        raise StopgateExecutionError(
            "トリガー ID は 1 から 16 を一度ずつ持たねばならない"
        )
    return tuple(sorted(states, key=lambda state: state.trigger_id))


def rejection_reasons(
    states: Sequence[TriggerState], current_step: int
) -> tuple[str, ...]:
    """発火済みと期限超過の未評価から拒否理由を返す。

    Args:
        states: 検査済みのトリガー状態。
        current_step: 実行しようとする現在のステップ。

    Returns:
        拒否理由。空なら後続を通してよい。
    """
    reasons: list[str] = []
    for state in states:
        if state.fired is True:
            reasons.append(f"トリガー {state.trigger_id} が発火済み")
        elif state.fired is None and state.evaluation_deadline < current_step:
            reasons.append(
                f"トリガー {state.trigger_id} が期限 "
                f"{state.evaluation_deadline} を超過して未評価"
            )
    return tuple(reasons)


def _parse_step(value: str) -> int:
    """CLI の現在ステップを正の整数に変換する。"""
    try:
        return _expect_int(int(value), "--step")
    except ValueError as error:
        raise argparse.ArgumentTypeError("--stepは正の整数である") from error
    except StopgateExecutionError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _build_parser() -> argparse.ArgumentParser:
    """停止ゲートの CLI パーサを作る。"""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--step", required=True, type=_parse_step)
    parser.add_argument("--registry", type=Path, default=_default_registry_path())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """現在ステップを通すか拒否するかを exit コードで返す。

    Args:
        argv: CLI 引数。`None` ならプロセス引数を使う。

    Returns:
        通過は 0、ゲート実行不能は 1、拒否は 2。
    """
    try:
        arguments = _build_parser().parse_args(argv)
        states = load_trigger_states(arguments.registry)
        if arguments.registry.resolve() == _default_registry_path().resolve():
            # 実資産では `fired` の自己申告だけを信用せず、全機械判定を再実行し、
            # PO 判定を日付・判定者・証拠 digest へ束縛する。
            from pitchlog.domaincheck import trigger_evaluation

            document = _read_json_object(arguments.registry)
            evaluated = {
                state.trigger_id
                for state in states
                if state.fired is not None
                and state.evaluation_deadline <= arguments.step
            }
            try:
                trigger_evaluation.validate_recorded_evaluations(
                    document,
                    _default_repository_root(),
                    trigger_ids=evaluated,
                )
            except trigger_evaluation.TriggerEvaluationError as error:
                raise StopgateExecutionError(str(error)) from error
        reasons = rejection_reasons(states, arguments.step)
    except StopgateExecutionError as error:
        print(f"停止ゲートを実行できません: {error}", file=sys.stderr)
        return EXIT_EXECUTION_ERROR

    if reasons:
        for reason in reasons:
            print(reason, file=sys.stderr)
        return EXIT_REJECT
    return EXIT_ALLOW


if __name__ == "__main__":
    raise SystemExit(main())
