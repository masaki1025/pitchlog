"""BOOT-ACTIVATION の実行文脈を現在の commit へ束縛する。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pitchlog.domaincheck.cli import CheckerExecutionError, CheckerViolation
from pitchlog.domaincheck.seal import _run_git

_KEYS = frozenset(
    {"schemaVersion", "runId", "event", "headSha", "machineGuarantee", "limit"}
)
_MACHINE_GUARANTEE = "record-head-sha-equals-checked-out-head"
_LIMIT = (
    "ネットワークを使わないため GitHub の check suite conclusion は機械検証できない。"
    "機械が保証するのは実行時レコードの head SHA が検査中の HEAD と一致することまでで、"
    "GitHub 上での success は人間が run を確認する。"
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


def build_runtime_evidence(root: Path, run_id: str, event: str) -> dict[str, object]:
    """現在 HEAD に束縛された実行時証跡を作る。"""
    if not run_id or not event:
        raise CheckerExecutionError("run ID と event は空にできない")
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "event": event,
        "headSha": current_head_oid(root),
        "machineGuarantee": _MACHINE_GUARANTEE,
        "limit": _LIMIT,
    }


def validate_runtime_evidence(root: Path, evidence: object) -> None:
    """実行時証跡の exact-set と現在 HEAD の一致を検査する。"""
    if not isinstance(evidence, dict) or set(evidence) != _KEYS:
        raise CheckerViolation("BOOT-ACTIVATION 実行証跡のキー集合が不正")
    value = cast(dict[str, object], evidence)
    if value.get("schemaVersion") != 1:
        raise CheckerViolation("BOOT-ACTIVATION 実行証跡の版が不正")
    if value.get("headSha") != current_head_oid(root):
        raise CheckerViolation("BOOT-ACTIVATION 実行証跡が現在 HEAD と一致しない")
    if value.get("machineGuarantee") != _MACHINE_GUARANTEE:
        raise CheckerViolation("BOOT-ACTIVATION の機械保証が不正")
    if value.get("limit") != _LIMIT:
        raise CheckerViolation("BOOT-ACTIVATION の人間確認境界が不正")
    if not isinstance(value.get("runId"), str) or not value["runId"]:
        raise CheckerViolation("BOOT-ACTIVATION の run ID が空")
    if not isinstance(value.get("event"), str) or not value["event"]:
        raise CheckerViolation("BOOT-ACTIVATION の event が空")


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
    parser.add_argument("--run-id", default="local")
    parser.add_argument("--event", default="local")
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.verify:
            evidence = json.loads(arguments.output.read_text(encoding="utf-8"))
            validate_runtime_evidence(arguments.root.resolve(), evidence)
        else:
            evidence = build_runtime_evidence(
                arguments.root.resolve(),
                arguments.run_id,
                arguments.event,
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
