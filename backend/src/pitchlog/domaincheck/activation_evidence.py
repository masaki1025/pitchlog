"""BOOT-ACTIVATION の実行文脈を現在の commit へ束縛する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pitchlog.domaincheck.cli import CheckerExecutionError, CheckerViolation
from pitchlog.domaincheck.seal import _run_git

_KEYS = frozenset(
    {
        "schemaVersion",
        "runId",
        "event",
        "headSha",
        "executions",
        "executionDigest",
        "machineGuarantee",
        "limit",
    }
)
_EXECUTION_KEYS = frozenset({"command", "cwd", "exitCode", "outputDigest"})
_EVENTS = frozenset({"pull_request", "push", "workflow_dispatch"})
_MACHINE_GUARANTEE = "recorded-commands-exited-zero-at-recorded-head"
_LIMIT = (
    "ネットワークを使わないため GitHub の check suite conclusion は機械検証できない。"
    "機械が保証するのは列挙した command を実際に起動し、exit 0 と出力 digest を得た後に"
    "証跡を作り、その head SHA が検査中の HEAD と一致することまでである。"
    "GitHub 上の job conclusion と並列 job の success は人間が run を確認する。"
)


def current_head_oid(root: Path) -> str:
    """検査中の現在 HEAD を完全な commit OID として返す。"""
    result = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    oid = result.stdout.strip()
    if (
        result.returncode != 0
        or len(oid) != 40
        or any(character not in "0123456789abcdef" for character in oid)
    ):
        raise CheckerExecutionError("BOOT-ACTIVATION の HEAD を実測できない")
    return oid


def _validate_run_context(run_id: str, event: str) -> None:
    """GitHub が与える run ID と event の閉じた形を検査する。"""
    if not run_id.isdecimal() or run_id.startswith("0"):
        raise CheckerExecutionError("run ID は正の十進整数でなければならない")
    if event not in _EVENTS:
        raise CheckerExecutionError(f"未登録の GitHub event: {event}")


def _execution_digest(executions: object) -> str:
    """順序付き実行結果の canonical digest を返す。"""
    payload = json.dumps(
        executions,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def execute_commands(root: Path, commands: Sequence[str]) -> list[dict[str, object]]:
    """対象 command を実際に起動し、全件成功後の証跡材料を返す。

    Args:
        root: command を起動するリポジトリルート。
        commands: 順序付きの実行対象。空集合は許さない。

    Returns:
        command・cwd・exit・出力 digest の実測レコード。

    Raises:
        CheckerExecutionError: command が空または起動不能の場合。
        CheckerViolation: command が exit 0 で完了しない場合。
    """
    if not commands or any(not command.strip() for command in commands):
        raise CheckerExecutionError("実行対象 command 集合が空または不正")
    executions: list[dict[str, object]] = []
    for command in commands:
        try:
            result = subprocess.run(
                shlex.split(command),
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise CheckerExecutionError(f"command を起動できない: {command}") from error
        print(result.stdout, end="")
        print(result.stderr, end="")
        if result.returncode != 0:
            raise CheckerViolation(
                f"BOOT-ACTIVATION 対象 command が失敗: "
                f"exit={result.returncode} command={command}"
            )
        output = {"stdout": result.stdout, "stderr": result.stderr}
        executions.append(
            {
                "command": command,
                "cwd": ".",
                "exitCode": result.returncode,
                "outputDigest": _execution_digest(output),
            }
        )
    return executions


def build_runtime_evidence(
    root: Path,
    run_id: str,
    event: str,
    executions: Sequence[dict[str, object]],
) -> dict[str, object]:
    """成功した command 集合と現在 HEAD に束縛された実行時証跡を作る。"""
    _validate_run_context(run_id, event)
    measured = list(executions)
    _validate_executions(measured)
    return {
        "schemaVersion": 2,
        "runId": run_id,
        "event": event,
        "headSha": current_head_oid(root),
        "executions": measured,
        "executionDigest": _execution_digest(measured),
        "machineGuarantee": _MACHINE_GUARANTEE,
        "limit": _LIMIT,
    }


def _validate_executions(executions: object) -> list[dict[str, object]]:
    """実行結果の exact-set・非空・exit 0 を検査する。"""
    if not isinstance(executions, list) or not executions:
        raise CheckerViolation("BOOT-ACTIVATION の実行結果が空")
    checked: list[dict[str, object]] = []
    for index, raw in enumerate(executions):
        if not isinstance(raw, dict) or set(raw) != _EXECUTION_KEYS:
            raise CheckerViolation(f"実行結果 {index} のキー集合が不正")
        value = cast(dict[str, object], raw)
        if not isinstance(value.get("command"), str) or not value["command"]:
            raise CheckerViolation(f"実行結果 {index} の command が不正")
        if value.get("cwd") != "." or value.get("exitCode") != 0:
            raise CheckerViolation(f"実行結果 {index} がリポジトリルートの成功でない")
        digest = value.get("outputDigest")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise CheckerViolation(f"実行結果 {index} の出力 digest が不正")
        checked.append(value)
    commands = [cast(str, value["command"]) for value in checked]
    if len(commands) != len(set(commands)):
        raise CheckerViolation("BOOT-ACTIVATION の実行 command が重複している")
    return checked


def validate_runtime_evidence(
    root: Path,
    evidence: object,
    expected_commands: Sequence[str],
) -> None:
    """実行証跡の exact-set・対象 command・現在 HEAD の一致を検査する。"""
    if not isinstance(evidence, dict) or set(evidence) != _KEYS:
        raise CheckerViolation("BOOT-ACTIVATION 実行証跡のキー集合が不正")
    value = cast(dict[str, object], evidence)
    if value.get("schemaVersion") != 2:
        raise CheckerViolation("BOOT-ACTIVATION 実行証跡の版が不正")
    if value.get("headSha") != current_head_oid(root):
        raise CheckerViolation("BOOT-ACTIVATION 実行証跡が現在 HEAD と一致しない")
    executions = _validate_executions(value.get("executions"))
    commands = [cast(str, execution["command"]) for execution in executions]
    if not expected_commands or commands != list(expected_commands):
        raise CheckerViolation("BOOT-ACTIVATION の実行 command 集合が期待と一致しない")
    if value.get("executionDigest") != _execution_digest(executions):
        raise CheckerViolation("BOOT-ACTIVATION の実行結果 digest が一致しない")
    if value.get("machineGuarantee") != _MACHINE_GUARANTEE:
        raise CheckerViolation("BOOT-ACTIVATION の機械保証が不正")
    if value.get("limit") != _LIMIT:
        raise CheckerViolation("BOOT-ACTIVATION の人間確認境界が不正")
    run_id = value.get("runId")
    event = value.get("event")
    if not isinstance(run_id, str) or not isinstance(event, str):
        raise CheckerViolation("BOOT-ACTIVATION の run 文脈が文字列でない")
    try:
        _validate_run_context(run_id, event)
    except CheckerExecutionError as error:
        raise CheckerViolation(str(error)) from error


def _write(path: Path, evidence: object) -> None:
    """実行時証跡を整形済み JSON で書く。"""
    try:
        path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise CheckerExecutionError(f"実行時証跡を書けない: {path}: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    """実行文脈を出力または再検証し、判定不能を exit 2 に分離する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--event")
    parser.add_argument("--execute-command", action="append", default=[])
    parser.add_argument("--expected-command", action="append", default=[])
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.verify:
            evidence = json.loads(arguments.output.read_text(encoding="utf-8"))
            validate_runtime_evidence(
                arguments.root.resolve(),
                evidence,
                arguments.expected_command,
            )
        else:
            if arguments.run_id is None or arguments.event is None:
                raise CheckerExecutionError("生成時は run ID と event が必須")
            executions = execute_commands(
                arguments.root.resolve(),
                arguments.execute_command,
            )
            evidence = build_runtime_evidence(
                arguments.root.resolve(),
                arguments.run_id,
                arguments.event,
                executions,
            )
            _write(arguments.output, evidence)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        CheckerExecutionError,
        CheckerViolation,
    ) as error:
        print(f"BOOT-ACTIVATION 判定不能: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
