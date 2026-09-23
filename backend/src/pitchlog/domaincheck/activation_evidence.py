"""BOOT-ACTIVATION の実行文脈を現在の commit へ束縛する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import tempfile
import xml.etree.ElementTree as ET
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
_EXECUTION_KEYS = frozenset({"command", "cwd", "exitCode", "outputDigest", "selectors"})
_SELECTOR_KEYS = frozenset({"selector", "collectedCount", "executedCount"})
_EVENTS = frozenset({"pull_request", "push", "workflow_dispatch"})
_MACHINE_GUARANTEE = (
    "recorded-commands-and-each-pytest-selector-executed-at-recorded-head"
)
_LIMIT = (
    "ネットワークを使わないため GitHub の check suite conclusion は機械検証できない。"
    "機械が保証するのは列挙した command を実際に起動し、pytest は selector ごとの収集・"
    "実行件数が 1 以上であること、exit 0 と出力 digest を得た後に証跡を作り、その head "
    "SHA が検査中の HEAD と一致することまでである。"
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


def _pytest_parts(command: str) -> tuple[list[str], tuple[str, ...]] | None:
    """Pytest command を runner/options と path selector に分ける。

    pytest の option を selector と誤認しないよう閉じた構文だけを受理する。
    発効対象 command では ``-c`` だけが値を取る option である。
    """
    tokens = shlex.split(command)
    try:
        pytest_index = tokens.index("pytest")
    except ValueError:
        return None
    base = tokens[: pytest_index + 1]
    selectors: list[str] = []
    index = pytest_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token == "-c":
            if index + 1 >= len(tokens):
                raise CheckerExecutionError("pytest -c の値が無い")
            base.extend(tokens[index : index + 2])
            index += 2
            continue
        if token.startswith("-"):
            base.append(token)
        else:
            selectors.append(token)
        index += 1
    if not selectors:
        raise CheckerExecutionError("pytest command に selector が無い")
    return base, tuple(selectors)


def _collected_count(root: Path, base: Sequence[str], selector: str) -> int:
    """一 selector を実際に collect して件数を返す。"""
    result = subprocess.run(
        [*base, "--collect-only", "-q", selector],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    node_count = sum(
        1
        for line in result.stdout.splitlines()
        if "::test_" in line and not line.lstrip().startswith("<")
    )
    file_count = sum(
        int(match.group(1))
        for line in result.stdout.splitlines()
        if (match := re.fullmatch(r".+\.py:\s+([1-9]\d*)", line.strip()))
    )
    count = node_count or file_count
    if result.returncode != 0 or count < 1:
        raise CheckerViolation(f"pytest selector を 1 件以上収集できない: {selector}")
    return count


def _executed_counts(junit_path: Path, selectors: Sequence[str]) -> dict[str, int]:
    """JUnit XML から selector ごとの非 skip 実行件数を返す。"""
    try:
        root = ET.parse(junit_path).getroot()
    except (OSError, ET.ParseError) as error:
        raise CheckerExecutionError("pytest の JUnit XML を読めない") from error
    counts = {selector: 0 for selector in selectors}
    for testcase in root.iter("testcase"):
        if testcase.find("skipped") is not None:
            continue
        file_name = testcase.attrib.get("file", "").replace("\\", "/")
        if not file_name:
            class_name = testcase.attrib.get("classname", "")
            file_name = class_name.replace(".", "/") + ".py"
        for selector in selectors:
            path = selector.split("::", maxsplit=1)[0].rstrip("/")
            if file_name == path or file_name.startswith(f"{path}/"):
                counts[selector] += 1
    missing = sorted(selector for selector, count in counts.items() if count < 1)
    if missing:
        raise CheckerViolation(f"pytest selector の実行件数が 0: {missing!r}")
    return counts


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
        pytest_parts = _pytest_parts(command)
        selector_records: list[dict[str, object]] = []
        run_tokens = shlex.split(command)
        temporary: tempfile.TemporaryDirectory[str] | None = None
        junit_path: Path | None = None
        if pytest_parts is not None:
            base, selectors = pytest_parts
            collected = {
                selector: _collected_count(root, base, selector)
                for selector in selectors
            }
            temporary = tempfile.TemporaryDirectory(prefix="pitchlog-activation-")
            junit_path = Path(temporary.name) / "junit.xml"
            run_tokens.append(f"--junitxml={junit_path}")
        try:
            result = subprocess.run(
                run_tokens,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise CheckerExecutionError(f"command を起動できない: {command}") from error
        print(result.stdout, end="")
        print(result.stderr, end="")
        if result.returncode:
            if temporary is not None:
                temporary.cleanup()
            raise CheckerViolation(
                f"BOOT-ACTIVATION 対象 command が失敗: "
                f"exit={result.returncode} command={command}"
            )
        if pytest_parts is not None:
            assert junit_path is not None
            _, selectors = pytest_parts
            executed = _executed_counts(junit_path, selectors)
            selector_records = [
                {
                    "selector": selector,
                    "collectedCount": collected[selector],
                    "executedCount": executed[selector],
                }
                for selector in selectors
            ]
        if temporary is not None:
            temporary.cleanup()
        output = {"stdout": result.stdout, "stderr": result.stderr}
        executions.append(
            {
                "command": command,
                "cwd": ".",
                "exitCode": result.returncode,
                "outputDigest": _execution_digest(output),
                "selectors": selector_records,
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
        "schemaVersion": 3,
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
        selectors = value.get("selectors")
        if not isinstance(selectors, list):
            raise CheckerViolation(f"実行結果 {index} の selectors が配列でない")
        checked_selectors: list[str] = []
        for selector_index, raw_selector in enumerate(selectors):
            if (
                not isinstance(raw_selector, dict)
                or set(raw_selector) != _SELECTOR_KEYS
            ):
                raise CheckerViolation(
                    f"実行結果 {index} の selector {selector_index} が不正"
                )
            selector = raw_selector.get("selector")
            collected = raw_selector.get("collectedCount")
            executed = raw_selector.get("executedCount")
            if not isinstance(selector, str) or not selector:
                raise CheckerViolation(f"実行結果 {index} の selector が不正")
            if (
                not isinstance(collected, int)
                or isinstance(collected, bool)
                or collected < 1
                or not isinstance(executed, int)
                or isinstance(executed, bool)
                or executed < 1
            ):
                raise CheckerViolation(f"実行結果 {index} の selector 件数が 1 未満")
            checked_selectors.append(selector)
        command = cast(str, value["command"])
        parsed = _pytest_parts(command)
        expected_selectors = [] if parsed is None else list(parsed[1])
        if checked_selectors != expected_selectors:
            raise CheckerViolation(
                f"実行結果 {index} の selector 集合が command と不一致"
            )
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
    if value.get("schemaVersion") != 3:
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
