"""見直しトリガーの評価記録を実測または PO 証拠へ束縛する。"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Collection, Mapping
from datetime import date
from functools import cache
from pathlib import Path, PurePosixPath
from typing import cast

from pitchlog.domaincheck.cli import CheckerExecutionError

EVIDENCE_ASSET = Path("backend/domain/review-trigger-evidence.json")
_TOP_KEYS = frozenset(
    {
        "schemaVersion",
        "poEvaluationLimit",
        "machineEvaluationLimit",
        "machineEvaluations",
        "manualDecisions",
    }
)
_MACHINE_KEYS = frozenset({"triggerId", "testNodes"})
_MANUAL_KEYS = frozenset(
    {
        "triggerId",
        "judge",
        "decisionDate",
        "fired",
        "evidenceLocation",
        "evidenceDigest",
    }
)
_RECONFIRMATION_KEYS = frozenset(
    {
        "judge",
        "decisionDate",
        "fired",
        "previousEvidenceDigest",
        "evidenceDigest",
        "reason",
    }
)
_EVIDENCE_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_NODE_ID = re.compile(
    r"(?P<path>tests/(?:[A-Za-z0-9_-]+/)*test_[A-Za-z0-9_]+\.py)"
    r"::(?P<function>test_[A-Za-z0-9_]+)"
)
_MACHINE_TRIGGER_NODES: dict[int, tuple[str, ...]] = {
    3: (
        "tests/domain/gen/test_formatter.py::"
        "test_alpha_python_typescript_and_reference_return_same_display",
        "tests/domain/gen/test_formatter.py::"
        "test_beta_seven_enum_map_receiver_and_reference_agree",
        "tests/domain/gen/test_formatter.py::"
        "test_all_target_matrix_classes_are_actually_generated",
    ),
    4: (
        "tests/domain/test_path_match.py::"
        "test_allowed_lossless_normalizations_pass_all_trigger_four_axes",
        "tests/domain/test_path_match.py::"
        "test_display_string_variations_are_not_normalized",
    ),
    6: (
        "tests/domain/test_collect_fe.py::"
        "test_dynamic_worker_is_reported_as_indeterminate",
        "tests/domain/test_closure_be.py::"
        "test_unresolved_dynamic_import_is_fail_closed",
        "tests/domain/test_display_binding.py::"
        "test_unresolved_display_path_is_fail_closed",
    ),
    9: (
        "tests/domain/test_history_depth.py::"
        "test_history_depth_is_derived_from_cases_and_maximum",
    ),
    12: (
        "tests/domain/mut/test_cost_record.py::"
        "test_recorded_scopes_recompute_product_and_budget_decision",
    ),
    13: (
        "tests/domain/test_display_binding.py::"
        "test_schema_selector_addition_changes_target_closure_without_code_list",
        "tests/domain/test_display_binding.py::"
        "test_matching_target_callsite_and_generated_formatter_pass",
    ),
    14: (
        "tests/domain/test_collect_layers.py::"
        "test_collector_computes_chain_instead_of_accepting_adapter_claim",
        "tests/domain/test_collect_layers.py::"
        "test_real_pytest_junit_output_is_counted_with_provenance",
    ),
    16: (
        "tests/domain/test_step_authorities.py::"
        "test_all_authorities_exist_verbatim_in_canonical_sources",
        "tests/domain/test_step_authorities.py::"
        "test_registry_has_exactly_all_sixty_steps",
    ),
}


class TriggerEvaluationError(CheckerExecutionError):
    """評価記録が独立実測または PO 証拠と一致しないことを表す。"""


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーの JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TriggerEvaluationError(f"{label} が JSON object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise TriggerEvaluationError(f"{label} が JSON array でない")
    return cast(list[object], value)


def _read_json(path: Path) -> dict[str, object]:
    """JSON 資産を object として読む。"""
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TriggerEvaluationError(f"評価証拠を読めない: {path}: {error}") from error


def _trigger_id(value: object, label: str) -> int:
    """Boolean でない正のトリガー ID を返す。"""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TriggerEvaluationError(f"{label} が正の整数でない")
    return value


def _pr197_delegated_digest(
    root: Path,
    identifier: int,
    decision: Mapping[str, object],
) -> str:
    """欠落・不正JSON・Git資格失敗を含め、委任不成立を閉拒否する。"""
    try:
        return _pr197_delegated_digest_impl(root, identifier, decision)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        raise TriggerEvaluationError(
            "PR197 trigger1 の委任証拠 digest が不一致"
        ) from error


def _pr197_delegated_digest_impl(
    root: Path,
    identifier: int,
    decision: Mapping[str, object],
) -> str:
    """旧本人記録を保存し、PR197のtrigger1だけを別の委任証拠で再確認する。"""
    from scripts import frozen_history

    def fail() -> TriggerEvaluationError:
        return TriggerEvaluationError("PR197 trigger1 の委任再確認証拠 digest が不一致")

    def git(*arguments: str) -> bytes:
        try:
            result = subprocess.run(
                ["git", "--no-replace-objects", "-C", str(root), *arguments],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise fail() from error
        return result.stdout

    record = _object(decision.get("delegatedReconfirmation"), "委任再確認")
    keys = {
        "judge",
        "decisionDate",
        "fired",
        "previousEvidenceDigest",
        "evidenceDigest",
        "reason",
        "pr",
        "branch",
        "sourceRevision",
        "authoritySha256",
        "reviewPath",
        "reviewSha256",
    }
    if (
        identifier != 1
        or set(record) != keys
        or record["judge"] != "Codex /root"
        or type(record["pr"]) is not int
        or record["pr"] != 197
        or record["branch"] != "feature/mvp-stats-native-foundation"
        or record["fired"] is not False
        or decision.get("fired") is not False
        or decision.get("evidenceLocation") != "backend/domain/model.schema.json"
        or not isinstance(record["reason"], str)
        or not record["reason"].strip()
    ):
        raise fail()
    if type(record["decisionDate"]) is not str:
        raise fail()
    try:
        checked_date = date.fromisoformat(record["decisionDate"])
        original_date = date.fromisoformat(str(decision["decisionDate"]))
    except ValueError as error:
        raise fail() from error
    if (
        checked_date.isoformat() != record["decisionDate"]
        or checked_date <= original_date
    ):
        raise fail()
    # 既独立固定原典の資格検査を再利用し、自由指定Gitを委任元にしない。
    frozen_history.read_original_pr197_pin("pr197_core_definition_ast_sha256", root)
    origin = frozen_history.PR197_PIN_ORIGIN_COMMIT
    git("merge-base", "--is-ancestor", origin, "HEAD")
    original = json.loads(git("show", f"{origin}:{EVIDENCE_ASSET.as_posix()}"))
    original_rows = [
        item for item in original["manualDecisions"] if item["triggerId"] == 1
    ]
    preserved = {
        key: value
        for key, value in decision.items()
        if key != "delegatedReconfirmation"
    }
    if original_rows != [preserved]:
        raise fail()
    authority_path = Path("docs/features/mvp-delegated-core-review/policy.json")
    path = root / authority_path
    authority = git("show", f"{origin}:{authority_path.as_posix()}")
    if (
        path.is_symlink()
        or not path.is_file()
        or record["authoritySha256"] != hashlib.sha256(authority).hexdigest()
    ):
        raise fail()
    policy = json.loads(authority)

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        """現policyの重複キーを後勝ちで補修しない。"""
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise fail()
            result[key] = value
        return result

    current_policy = _object(
        json.loads(path.read_bytes(), object_pairs_hook=unique),
        "現委任policy",
    )
    old_targets = policy["targets"]
    targets = current_policy.get("targets")
    if (
        type(targets) is not list
        or len(targets) < len(old_targets)
        or json.dumps(targets[: len(old_targets)], sort_keys=True)
        != json.dumps(old_targets, sort_keys=True)
        or json.dumps(
            {k: v for k, v in current_policy.items() if k != "targets"}, sort_keys=True
        )
        != json.dumps(
            {k: v for k, v in policy.items() if k != "targets"}, sort_keys=True
        )
    ):
        raise fail()
    seen_prs: set[int] = set()
    seen_branches: set[str] = set()
    for raw_target in targets:
        if type(raw_target) is not dict:
            raise fail()
        target = cast(dict[str, object], raw_target)
        pr = target.get("pr")
        branch = target.get("branch")
        if (
            set(target) != {"pr", "branch"}
            or type(pr) is not int
            or pr <= 0
            or type(branch) is not str
            or re.fullmatch(r"(?:feature|fix)/[a-z0-9][a-z0-9/._-]*", branch) is None
            or pr in seen_prs
            or branch in seen_branches
        ):
            raise fail()
        seen_prs.add(pr)
        seen_branches.add(branch)
    if (
        policy.get("enabled") is not True
        or policy.get("schema_version") != 1
        or policy.get("repository") != "masaki1025/pitchlog"
        or policy.get("source_kind") != "local_goal_thread_not_ui_identity_proof"
        or {"pr": 197, "branch": record["branch"]} not in policy.get("targets", [])
    ):
        raise fail()
    revision = record["sourceRevision"]
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise fail()
    if (
        git("rev-parse", "--verify", revision + "^{commit}").decode().strip()
        != revision
    ):
        raise fail()
    git("merge-base", "--is-ancestor", revision, "HEAD")
    review_relative = (
        "docs/features/mvp-stats-primitives/trigger1-delegated-review.json"
    )
    if record["reviewPath"] != review_relative:
        raise fail()
    review_path = root / review_relative
    if review_path.is_symlink() or not review_path.is_file():
        raise fail()
    raw_review = review_path.read_bytes()
    if record["reviewSha256"] != hashlib.sha256(raw_review).hexdigest():
        raise fail()
    review = _object(json.loads(raw_review), "委任非作者確認")
    if raw_review != (json.dumps(review, ensure_ascii=False, indent=2) + "\n").encode():
        raise fail()
    if (
        set(review) != {"author", "reviewer", "sourceRevision", "p0", "p1", "files"}
        or review["author"] != record["judge"]
        or not isinstance(review["reviewer"], str)
        or re.fullmatch(r"/root/[a-z0-9_]+", review["reviewer"]) is None
        or review["sourceRevision"] != revision
        or type(review["p0"]) is not int
        or review["p0"] != 0
        or type(review["p1"]) is not int
        or review["p1"] != 0
    ):
        raise fail()
    files = _object(review["files"], "委任対象全byte")
    expected_files = {
        "backend/src/pitchlog/domaincheck/trigger_evaluation.py",
        "tests/domain/test_review_triggers_complete.py",
        "backend/domain/model.schema.json",
    }
    if set(files) != expected_files:
        raise fail()
    for relative, digest in files.items():
        target = root / relative
        expected = git("show", f"{revision}:{relative}")
        if (
            target.is_symlink()
            or not target.is_file()
            or target.read_bytes() != expected
            or digest != hashlib.sha256(expected).hexdigest()
        ):
            raise fail()
    current = evidence_digest(root, "backend/domain/model.schema.json")
    if (
        record["previousEvidenceDigest"] != decision["evidenceDigest"]
        or record["evidenceDigest"] != current
        or current == decision["evidenceDigest"]
    ):
        raise fail()
    return current


def _validate_reconfirmations(
    decision: Mapping[str, object],
    *,
    identifier: int,
    judge: object,
    recorded: bool,
) -> None:
    """元の判定を保持したまま、証拠再確認の追記列を検証する。"""
    if "reconfirmations" not in decision:
        return
    records = _array(decision["reconfirmations"], "reconfirmations")
    if not records:
        raise TriggerEvaluationError(f"トリガー {identifier} の再確認記録が空")
    raw_original_date = decision["decisionDate"]
    assert isinstance(raw_original_date, str)
    previous_date = date.fromisoformat(raw_original_date)
    previous_digest: object = None
    for index, raw in enumerate(records):
        item = _object(raw, f"reconfirmations[{index}]")
        if set(item) != _RECONFIRMATION_KEYS:
            raise TriggerEvaluationError(
                f"トリガー {identifier} の再確認キー集合が不正"
            )
        raw_date = item["decisionDate"]
        try:
            if not isinstance(raw_date, str):
                raise ValueError
            checked_date = date.fromisoformat(raw_date)
        except ValueError as error:
            raise TriggerEvaluationError(
                f"トリガー {identifier} の再確認日が不正"
            ) from error
        if checked_date <= previous_date:
            raise TriggerEvaluationError(
                f"トリガー {identifier} の再確認日が判定日より後でない"
            )
        previous_date = checked_date
        if item["judge"] != judge or item["fired"] is not recorded:
            raise TriggerEvaluationError(
                f"トリガー {identifier} の再確認判定が元の判定と不一致"
            )
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise TriggerEvaluationError(f"トリガー {identifier} の再確認理由が不正")
        old_digest = item["previousEvidenceDigest"]
        new_digest = item["evidenceDigest"]
        if not all(
            isinstance(value, str) and _EVIDENCE_DIGEST_RE.fullmatch(value)
            for value in (old_digest, new_digest)
        ):
            raise TriggerEvaluationError(
                f"トリガー {identifier} の再確認 digest が不正"
            )
        if old_digest == new_digest or (
            previous_digest is not None and old_digest != previous_digest
        ):
            raise TriggerEvaluationError(
                f"トリガー {identifier} の再確認 digest の連鎖が不正"
            )
        previous_digest = new_digest
    if previous_digest != decision["evidenceDigest"]:
        raise TriggerEvaluationError(
            f"トリガー {identifier} の最新の再確認 digest が不一致"
        )


def _digest_file(path: Path) -> str:
    """一ファイルの内容 digest を返す。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_digest(root: Path, location: str) -> str:
    """証拠ファイルまたは証拠木を順序付き digest へ閉じる。"""
    relative = PurePosixPath(location)
    if relative.is_absolute() or ".." in relative.parts:
        raise TriggerEvaluationError(f"証拠パスが閉域外: {location}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise TriggerEvaluationError(f"証拠パスがリポジトリ外: {location}") from error
    if path.is_file():
        return f"sha256:{_digest_file(path)}"
    if not path.is_dir():
        raise TriggerEvaluationError(f"証拠が実在しない: {location}")
    entries = [
        {
            "path": item.relative_to(path).as_posix(),
            "sha256": _digest_file(item),
        }
        for item in sorted(path.rglob("*"))
        if item.is_file() and "__pycache__" not in item.parts
    ]
    if not entries:
        raise TriggerEvaluationError(f"証拠ディレクトリが空: {location}")
    payload = json.dumps(
        entries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@cache
def _run_test_nodes(root_text: str, nodes: tuple[str, ...]) -> bool:
    """Node を収集・実行し、assertion failure があれば発火とする。"""
    root = Path(root_text)
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *nodes],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    collected_count = sum(
        1 for line in collected.stdout.splitlines() if _NODE_ID.fullmatch(line.strip())
    )
    if collected.returncode != 0 or collected_count < 1:
        raise TriggerEvaluationError(
            "機械トリガーの pytest node を 1 件以上収集できない"
        )
    with tempfile.TemporaryDirectory(prefix="pitchlog-trigger-") as directory:
        junit_path = Path(directory) / "junit.xml"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                f"--junitxml={junit_path}",
                *nodes,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            junit = ET.parse(junit_path).getroot()
            suites = (
                [junit]
                if junit.tag == "testsuite"
                else list(junit.findall("testsuite"))
            )
            executed_count = sum(
                int(suite.attrib.get("tests", "0")) for suite in suites
            )
        except (OSError, ET.ParseError, ValueError) as error:
            raise TriggerEvaluationError(
                "機械トリガーの pytest 実行件数を読めない"
            ) from error
    if executed_count < 1:
        raise TriggerEvaluationError("機械トリガーを 1 件も実行していない")
    if result.returncode not in {0, 1}:
        raise TriggerEvaluationError(
            f"機械トリガーの pytest が判定不能: exit={result.returncode}"
        )
    return result.returncode == 1


def _validated_machine_nodes(
    root: Path,
    trigger_id: int,
    raw_nodes: object,
) -> tuple[str, ...]:
    """Node ID 文法・対象ファイル・関数実在を閉じて返す。"""
    nodes_raw = _array(raw_nodes, "machine.testNodes")
    if not nodes_raw or not all(isinstance(node, str) for node in nodes_raw):
        raise TriggerEvaluationError("machine.testNodes が空または文字列でない")
    nodes = tuple(cast(list[str], nodes_raw))
    matches = [_NODE_ID.fullmatch(node) for node in nodes]
    if any(match is None for match in matches):
        raise TriggerEvaluationError(
            "machine.testNodes は path::test_function 形式でなければならない"
        )
    expected_nodes = _MACHINE_TRIGGER_NODES.get(trigger_id)
    if expected_nodes is None or nodes != expected_nodes:
        raise TriggerEvaluationError(
            f"トリガー {trigger_id} の評価 node が固定対応と違う"
        )
    for node, match in zip(nodes, matches, strict=True):
        assert match is not None
        path = root / match.group("path")
        if not path.is_file():
            raise TriggerEvaluationError(f"pytest node のファイルが実在しない: {node}")
        source = path.read_text(encoding="utf-8")
        function_pattern = rf"^def {re.escape(match.group('function'))}\("
        if re.search(function_pattern, source, re.MULTILINE) is None:
            raise TriggerEvaluationError(f"pytest node の関数が実在しない: {node}")
    if len(nodes) != len(set(nodes)):
        raise TriggerEvaluationError("machine.testNodes が重複している")
    return nodes


def _evaluation_fired(row: Mapping[str, object]) -> bool | None:
    """厳密な評価レコードから発火値を返す。"""
    value = row.get("evaluation")
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"fired"}:
        raise TriggerEvaluationError("evaluation は fired だけを持たねばならない")
    fired = value["fired"]
    if not isinstance(fired, bool):
        raise TriggerEvaluationError("evaluation.fired は boolean でなければならない")
    return fired


def _judges(row: Mapping[str, object]) -> frozenset[str]:
    """トリガー行の判定者集合を返す。"""
    value = row.get("judge")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TriggerEvaluationError("judge が文字列 array でない")
    judges = frozenset(value)
    if not judges or judges - {"機械", "PO"}:
        raise TriggerEvaluationError(f"judge が閉じていない: {sorted(judges)!r}")
    return judges


def validate_recorded_evaluations(
    registry: Mapping[str, object],
    repository_root: Path,
    *,
    evidence_path: Path | None = None,
    trigger_ids: Collection[int] | None = None,
) -> None:
    """機械評価を実行し、PO 評価を日付・判定者・内容 digest へ束縛する。

    PO の判断内容そのものは機械に代行できない。本検査が保証するのは、判定者・
    判定日・発火値を持つ決定記録が存在し、指定された証拠内容がその後変わって
    いないことまでである。この限界は証拠資産にも逐語で保持する。
    """
    root = repository_root.resolve()
    evidence_file = evidence_path or root / EVIDENCE_ASSET
    evidence = _read_json(evidence_file)
    if set(evidence) != _TOP_KEYS or evidence.get("schemaVersion") != 2:
        raise TriggerEvaluationError("評価証拠のトップレベルが不正")
    limit = evidence.get("poEvaluationLimit")
    if not isinstance(limit, str) or "判断内容そのもの" not in limit:
        raise TriggerEvaluationError("PO 評価の機械保証限界が明記されていない")
    machine_limit = evidence.get("machineEvaluationLimit")
    if (
        not isinstance(machine_limit, str)
        or "テスト本体の意味" not in machine_limit
        or "保証範囲外" not in machine_limit
    ):
        raise TriggerEvaluationError("機械評価の意味保証限界が明記されていない")

    raw_rows = _array(registry.get("triggers"), "triggers")
    rows = [
        _object(value, f"triggers[{index}]") for index, value in enumerate(raw_rows)
    ]
    by_id = {_trigger_id(row.get("id"), "trigger.id"): row for row in rows}
    if len(by_id) != len(rows):
        raise TriggerEvaluationError("トリガー ID が重複している")
    selected = frozenset(by_id) if trigger_ids is None else frozenset(trigger_ids)
    unknown = selected - frozenset(by_id)
    if unknown:
        raise TriggerEvaluationError(f"未知のトリガー ID: {sorted(unknown)!r}")

    machine_rows = _array(evidence.get("machineEvaluations"), "machineEvaluations")
    machine_by_id: dict[int, tuple[str, ...]] = {}
    for index, raw in enumerate(machine_rows):
        item = _object(raw, f"machineEvaluations[{index}]")
        if set(item) != _MACHINE_KEYS:
            raise TriggerEvaluationError("machineEvaluations のキー集合が不正")
        identifier = _trigger_id(item.get("triggerId"), "machine.triggerId")
        if identifier in machine_by_id:
            raise TriggerEvaluationError(
                "machineEvaluations の triggerId が重複している"
            )
        machine_by_id[identifier] = _validated_machine_nodes(
            root,
            identifier,
            item.get("testNodes"),
        )
    expected_machine = {
        identifier for identifier, row in by_id.items() if "機械" in _judges(row)
    }
    if set(machine_by_id) != expected_machine:
        raise TriggerEvaluationError(
            "機械トリガーの実測経路が不一致: "
            f"不足={sorted(expected_machine - set(machine_by_id))!r}, "
            f"未知={sorted(set(machine_by_id) - expected_machine)!r}"
        )

    manual_rows = _array(evidence.get("manualDecisions"), "manualDecisions")
    manual_by_id: dict[int, dict[str, object]] = {}
    for index, raw in enumerate(manual_rows):
        item = _object(raw, f"manualDecisions[{index}]")
        if set(item) not in (
            _MANUAL_KEYS,
            _MANUAL_KEYS | {"reconfirmations"},
            _MANUAL_KEYS | {"delegatedReconfirmation"},
        ):
            raise TriggerEvaluationError("manualDecisions のキー集合が不正")
        identifier = _trigger_id(item.get("triggerId"), "manual.triggerId")
        if identifier in manual_by_id:
            raise TriggerEvaluationError("manualDecisions の triggerId が重複している")
        manual_by_id[identifier] = item
    expected_manual = {
        identifier for identifier, row in by_id.items() if "PO" in _judges(row)
    }
    if set(manual_by_id) != expected_manual:
        raise TriggerEvaluationError("PO トリガーの決定記録集合が不一致")

    for identifier in sorted(selected):
        row = by_id[identifier]
        recorded = _evaluation_fired(row)
        if recorded is None:
            continue
        judges = _judges(row)
        if "機械" in judges:
            measured = _run_test_nodes(str(root), machine_by_id[identifier])
            if recorded is not measured:
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の記録 {recorded} が"
                    f"機械実測 {measured} と不一致"
                )
        if "PO" in judges:
            decision = manual_by_id[identifier]
            if decision.get("judge") != registry.get("poName"):
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の PO 判定者が不正"
                )
            raw_date = decision.get("decisionDate")
            try:
                if not isinstance(raw_date, str):
                    raise ValueError
                date.fromisoformat(raw_date)
            except ValueError as error:
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の判定日が不正"
                ) from error
            if decision.get("fired") is not recorded:
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の PO 決定と評価記録が不一致"
                )
            _validate_reconfirmations(
                decision,
                identifier=identifier,
                judge=registry.get("poName"),
                recorded=recorded,
            )
            location = decision.get("evidenceLocation")
            if location != row.get("evidenceLocation") or not isinstance(location, str):
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の PO 証拠パスが不一致"
                )
            actual_digest = evidence_digest(root, location)
            confirmed_digest = (
                _pr197_delegated_digest(root, identifier, decision)
                if "delegatedReconfirmation" in decision
                else decision.get("evidenceDigest")
            )
            if confirmed_digest != actual_digest:
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の PO 証拠 digest が不一致"
                )


__all__ = [
    "EVIDENCE_ASSET",
    "TriggerEvaluationError",
    "evidence_digest",
    "validate_recorded_evaluations",
]
