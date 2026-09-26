"""状態遷移契約の凍結基準宣言と追記専用の受理履歴を検証する。"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

FREEZE_FIELD = "freezeBaseline"
FREEZE_SERIES = "state-transition-contract-checks"
CRITERIA_SECTIONS = (
    "threeWayParity",
    "inputAxesDescriptor",
    "gapRegister",
)
ACCEPTANCE_ID_PATTERN = re.compile(r"^[^/#\s]+/[^/#\s]+#[1-9][0-9]*$")


class FreezeBaselineError(Exception):
    """凍結基準宣言を検証できない、または不一致の場合を表す。"""


def canonicalize(value: object) -> bytes:
    """基準識別値用の決定的な JSON 表現を返す。

    基準値は整数・文字列・真偽値・null・配列・object に限定し、object の
    キーを Unicode コードポイント順に並べ、空白なし・UTF-8 で符号化する。
    """
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise FreezeBaselineError(f"基準値を正規化できない: {error}") from error
    return encoded.encode("utf-8")


def criterion_identity(section: object) -> str:
    """checker 単位の基準 object の SHA-256 識別値を返す。"""
    return f"sha256:{hashlib.sha256(canonicalize(section)).hexdigest()}"


def current_identities(criteria: Mapping[str, Any]) -> list[dict[str, str]]:
    """全 checker 基準の識別値を安定順で返す。"""
    return [
        {
            "criterionId": section_name,
            "identity": criterion_identity(criteria[section_name]),
        }
        for section_name in CRITERIA_SECTIONS
    ]


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    """object のキー集合を exact-set で検査する。"""
    actual = set(value)
    if actual != expected:
        raise FreezeBaselineError(
            f"{label}のキーがexact-set不一致: "
            f"missing={sorted(expected - actual)!r}; "
            f"unexpected={sorted(actual - expected)!r}"
        )


def _require_non_empty_string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise FreezeBaselineError(f"{label}は空でない文字列でなければならない")
    return value


def validate_declaration(value: object) -> dict[str, Any]:
    """資産側の凍結基準宣言と履歴の内部整合を fail-closed で検証する。"""
    if not isinstance(value, dict):
        raise FreezeBaselineError(f"{FREEZE_FIELD}はJSON objectでなければならない")
    _require_exact_keys(
        value,
        {"schemaVersion", "series", "acceptance", "identitySpec", "criteria", "history"},
        FREEZE_FIELD,
    )
    if value.get("schemaVersion") != 1:
        raise FreezeBaselineError("freezeBaseline.schemaVersionは1でなければならない")
    if value.get("series") != FREEZE_SERIES:
        raise FreezeBaselineError("freezeBaseline.seriesが未対応である")

    acceptance = value.get("acceptance")
    if not isinstance(acceptance, dict):
        raise FreezeBaselineError("freezeBaseline.acceptanceがobjectでない")
    _require_exact_keys(
        acceptance,
        {
            "unit",
            "acceptanceIdSource",
            "baseRef",
            "baseCommit",
            "posteriorState",
        },
        "freezeBaseline.acceptance",
    )
    if acceptance.get("unit") != "pull_request":
        raise FreezeBaselineError("凍結基準の受理単位はpull_requestでなければならない")
    if acceptance.get("acceptanceIdSource") != "repository_and_pr_number":
        raise FreezeBaselineError("acceptanceIdSourceが未対応である")
    _require_non_empty_string(acceptance.get("baseRef"), "acceptance.baseRef")
    base_commit = _require_non_empty_string(
        acceptance.get("baseCommit"), "acceptance.baseCommit"
    )
    if re.fullmatch(r"[0-9a-f]{40}", base_commit) is None:
        raise FreezeBaselineError("acceptance.baseCommitが40桁のcommit SHAでない")
    if acceptance.get("posteriorState") != "pull-request-head":
        raise FreezeBaselineError("acceptance.posteriorStateが未対応である")

    identity_spec = value.get("identitySpec")
    if not isinstance(identity_spec, dict):
        raise FreezeBaselineError("freezeBaseline.identitySpecがobjectでない")
    _require_exact_keys(
        identity_spec,
        {"granularity", "algorithm", "canonicalization", "encoding"},
        "freezeBaseline.identitySpec",
    )
    if identity_spec != {
        "granularity": "checker-criteria-object",
        "algorithm": "SHA-256",
        "canonicalization": "json-sort-keys-no-whitespace-v1",
        "encoding": "UTF-8",
    }:
        raise FreezeBaselineError("freezeBaseline.identitySpecが未対応である")

    criteria = value.get("criteria")
    if not isinstance(criteria, dict):
        raise FreezeBaselineError("freezeBaseline.criteriaがobjectでない")
    if set(criteria) != set(CRITERIA_SECTIONS):
        raise FreezeBaselineError(
            "freezeBaseline.criteriaのchecker集合がexact-set不一致: "
            f"expected={sorted(CRITERIA_SECTIONS)!r}; actual={sorted(criteria)!r}"
        )
    for section_name in CRITERIA_SECTIONS:
        section = criteria.get(section_name)
        if not isinstance(section, dict) or not section:
            raise FreezeBaselineError(
                f"criteria.{section_name}は空でないobjectでなければならない"
            )

    history = value.get("history")
    if not isinstance(history, list) or not history:
        raise FreezeBaselineError("freezeBaseline.historyは空でない配列でなければならない")
    _validate_history_chain(history)
    expected_new = current_identities(criteria)
    last = history[-1]
    if last["newIdentity"] != {"present": True, "values": expected_new}:
        raise FreezeBaselineError(
            "最新受理記録のnewIdentityが現行基準の識別値と一致しない"
        )
    return value


def checker_criteria(
    declaration: Mapping[str, Any], checker_name: str
) -> dict[str, Any]:
    """検証済み宣言から checker 単位の基準を返す。"""
    validated = validate_declaration(dict(declaration))
    section = validated["criteria"].get(checker_name)
    if not isinstance(section, dict):
        raise FreezeBaselineError(f"checker基準を取得できない: {checker_name}")
    return section


def _validate_identity_state(value: object, label: str) -> None:
    """履歴の直前・直後識別値を検証する。"""
    if not isinstance(value, dict):
        raise FreezeBaselineError(f"{label}がobjectでない")
    _require_exact_keys(value, {"present", "values"}, label)
    present = value.get("present")
    values = value.get("values")
    if not isinstance(present, bool) or not isinstance(values, list):
        raise FreezeBaselineError(f"{label}の型が不正である")
    if not present and values:
        raise FreezeBaselineError(f"{label}は基準なしの場合valuesを空にする")
    if present and not values:
        raise FreezeBaselineError(f"{label}は基準ありの場合valuesを空にできない")
    seen: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise FreezeBaselineError(f"{label}.values[{index}]がobjectでない")
        _require_exact_keys(item, {"criterionId", "identity"}, f"{label}.values[{index}]")
        criterion_id = _require_non_empty_string(
            item.get("criterionId"), f"{label}.values[{index}].criterionId"
        )
        identity = _require_non_empty_string(
            item.get("identity"), f"{label}.values[{index}].identity"
        )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
            raise FreezeBaselineError(f"{label}の識別値がSHA-256形式でない")
        if criterion_id in seen:
            raise FreezeBaselineError(f"{label}でcriterionIdが重複している: {criterion_id}")
        seen.add(criterion_id)


def _validate_history_chain(history: Sequence[object]) -> None:
    """履歴レコードの型と内部の片方向連鎖を検証する。"""
    previous_new: object | None = None
    acceptance_ids: set[str] = set()
    for index, record in enumerate(history):
        label = f"freezeBaseline.history[{index}]"
        if not isinstance(record, dict):
            raise FreezeBaselineError(f"{label}がobjectでない")
        _require_exact_keys(
            record,
            {
                "acceptanceId",
                "series",
                "priorIdentity",
                "newIdentity",
                "changes",
                "fact",
                "reason",
                "approvedBy",
                "approvedDate",
            },
            label,
        )
        acceptance_id = _require_non_empty_string(
            record.get("acceptanceId"), f"{label}.acceptanceId"
        )
        if ACCEPTANCE_ID_PATTERN.fullmatch(acceptance_id) is None:
            raise FreezeBaselineError(f"{label}.acceptanceIdの形式が不正である")
        if acceptance_id in acceptance_ids:
            raise FreezeBaselineError(f"acceptanceIdが重複している: {acceptance_id}")
        acceptance_ids.add(acceptance_id)
        if record.get("series") != FREEZE_SERIES:
            raise FreezeBaselineError(f"{label}.seriesが未対応である")
        _validate_identity_state(record.get("priorIdentity"), f"{label}.priorIdentity")
        _validate_identity_state(record.get("newIdentity"), f"{label}.newIdentity")
        if previous_new is not None and record.get("priorIdentity") != previous_new:
            raise FreezeBaselineError(f"{label}のpriorIdentityが直前レコードと連鎖しない")
        previous_new = record.get("newIdentity")

        changes = record.get("changes")
        if not isinstance(changes, list) or not changes:
            raise FreezeBaselineError(f"{label}.changesを空にできない")
        changed_ids: set[str] = set()
        for change_index, change in enumerate(changes):
            change_label = f"{label}.changes[{change_index}]"
            if not isinstance(change, dict):
                raise FreezeBaselineError(f"{change_label}がobjectでない")
            _require_exact_keys(
                change,
                {"criterionId", "before", "after", "changedAspects"},
                change_label,
            )
            criterion_id = _require_non_empty_string(
                change.get("criterionId"), f"{change_label}.criterionId"
            )
            if criterion_id in changed_ids:
                raise FreezeBaselineError(
                    f"{label}.changesでcriterionIdが重複している: {criterion_id}"
                )
            changed_ids.add(criterion_id)
            for state_name in ("before", "after"):
                state = change.get(state_name)
                if not isinstance(state, dict) or set(state) not in (
                    {"present"},
                    {"present", "value"},
                ):
                    raise FreezeBaselineError(f"{change_label}.{state_name}の型が不正")
                if state.get("present") is False and set(state) != {"present"}:
                    raise FreezeBaselineError(
                        f"{change_label}.{state_name}は基準なしの場合valueを持てない"
                    )
                if state.get("present") is True and "value" not in state:
                    raise FreezeBaselineError(
                        f"{change_label}.{state_name}は基準ありの場合valueが必須"
                    )
            aspects = change.get("changedAspects")
            if not isinstance(aspects, list) or not aspects or not all(
                isinstance(item, str) and item for item in aspects
            ):
                raise FreezeBaselineError(f"{change_label}.changedAspectsが不正")
        for field in ("fact", "reason", "approvedBy", "approvedDate"):
            _require_non_empty_string(record.get(field), f"{label}.{field}")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["approvedDate"]) is None:
            raise FreezeBaselineError(f"{label}.approvedDateの形式が不正")


def _git(root: Path, arguments: Sequence[str]) -> str:
    """gitを実行し、失敗を基準未検証として拒否する。"""
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise FreezeBaselineError(f"gitを実行できない: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FreezeBaselineError(
            f"git {' '.join(arguments)}を実行できない: {detail}"
        )
    return result.stdout


def load_base_declaration(
    root: Path, descriptor_path: PurePosixPath, base_ref: str
) -> dict[str, Any] | None:
    """受理単位の比較元から直前の宣言を取得する。"""
    _git(root, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"])
    listed = _git(
        root,
        ["ls-tree", "-r", "--name-only", base_ref, "--", str(descriptor_path)],
    )
    paths = [line for line in listed.splitlines() if line]
    if not paths:
        return None
    if paths != [str(descriptor_path)]:
        raise FreezeBaselineError(
            f"比較元のdescriptor配置を一意に解決できない: {paths!r}"
        )
    raw = _git(root, ["show", f"{base_ref}:{descriptor_path}"])
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise FreezeBaselineError(
            f"比較元descriptorをJSONとして読めない: {error}"
        ) from error
    if not isinstance(document, dict) or FREEZE_FIELD not in document:
        raise FreezeBaselineError(
            "比較元descriptorは存在するが凍結基準宣言を取得できない"
        )
    return validate_declaration(document[FREEZE_FIELD])


def validate_append_only_transition(
    current: Mapping[str, Any], base: Mapping[str, Any] | None
) -> None:
    """比較元から現行への1受理分の追記だけを許す。"""
    current_value = validate_declaration(dict(current))
    current_history = current_value["history"]
    current_criteria = current_value["criteria"]
    if base is None:
        base_history: list[object] = []
        base_criteria: Mapping[str, Any] = {}
        expected_prior = {"present": False, "values": []}
    else:
        base_value = validate_declaration(dict(base))
        base_history = base_value["history"]
        base_criteria = base_value["criteria"]
        expected_prior = {
            "present": True,
            "values": current_identities(base_criteria),
        }

    if current_history[: len(base_history)] != base_history:
        raise FreezeBaselineError(
            "既存の凍結基準受理履歴が書き換えまたは削除されている"
        )
    changed_ids = [
        section
        for section in CRITERIA_SECTIONS
        if base_criteria.get(section) != current_criteria.get(section)
    ]
    expected_added = 1 if changed_ids else 0
    if len(current_history) != len(base_history) + expected_added:
        raise FreezeBaselineError(
            "基準遷移1回につき受理記録はちょうど1件でなければならない"
        )
    if not changed_ids:
        return

    record = current_history[-1]
    if record["priorIdentity"] != expected_prior:
        raise FreezeBaselineError("追加レコードのpriorIdentityが直前基準と一致しない")
    expected_changes = []
    for section in changed_ids:
        before = (
            {"present": False}
            if section not in base_criteria
            else {"present": True, "value": base_criteria[section]}
        )
        expected_changes.append(
            {
                "criterionId": section,
                "before": before,
                "after": {"present": True, "value": current_criteria[section]},
                "changedAspects": [
                    "set",
                    "value",
                    "placement",
                    "frozen-target-correspondence",
                    "identity-granularity-and-interpretation",
                ],
            }
        )
    if record["changes"] != expected_changes:
        raise FreezeBaselineError(
            "受理記録のchangesが比較元から導出した変更前後と一致しない"
        )


def validate_repository_history(
    root: Path,
    descriptor_path: PurePosixPath,
    declaration: Mapping[str, Any],
) -> None:
    """宣言したPR比較元と実リポジトリから追記専用遷移を検査する。"""
    current = validate_declaration(dict(declaration))
    base_ref = current["acceptance"]["baseRef"]
    base_commit = current["acceptance"]["baseCommit"]
    resolved = _git(root, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"])
    if resolved.strip() != base_commit:
        raise FreezeBaselineError(
            "受理記録のbaseCommitがbaseRefの実測値と一致しない: "
            f"{base_commit} != {resolved.strip()}"
        )
    base = load_base_declaration(root, descriptor_path, base_commit)
    validate_append_only_transition(current, base)
