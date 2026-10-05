"""状況判定ケースのrawへ宣言規則を適用しnormalizedと突合する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from state_transition_normalization import NormalizationError, NormalizationRules

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/state_transition_contract_schema_v1.json"
)
EXPANDER_POLICY_PATH = PurePosixPath(
    "contracts/state-transition/expander_dependency_policy_v1.json"
)


class NormalizationCheckError(ValueError):
    """ケースの正規化結果が宣言と一致しない場合を表す。"""


def _read(root: Path, path: PurePosixPath) -> dict[str, Any]:
    """宣言済みのJSON資産を読む。"""
    value = json.loads((root / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NormalizationCheckError(f"JSON objectでない: {path}")
    return value


def load_inputs(root: Path) -> tuple[list[dict[str, Any]], NormalizationRules]:
    """展開器と整合する許可パスから全ケースと規則を読む。"""
    schema = _read(root, SCHEMA_PATH)
    declaration = schema["x-pitchlog-stage1-normalization"]
    paths = declaration.get("claimBoundary", {}).get("allowedReadPaths")
    if not isinstance(paths, list) or len(paths) != 4 or len(set(paths)) != 4:
        raise NormalizationCheckError("突合器のallowedReadPathsが不正")
    allowed = {PurePosixPath(path) for path in paths}
    if SCHEMA_PATH not in allowed or any(
        path.is_absolute() or ".." in path.parts for path in allowed
    ):
        raise NormalizationCheckError("突合器のallowedReadPathsに不正なパスがある")
    policy = _read(root, EXPANDER_POLICY_PATH)
    expander = next(
        (item for item in policy.get("expanders", [])
         if item.get("expanderId") == "state-transition-cases"), None
    )
    if expander is None or not allowed <= {
        PurePosixPath(path) for path in expander.get("allowedReadPaths", [])
    }:
        raise NormalizationCheckError("突合器と展開器のallowedReadPathsが不一致")
    documents = {path: _read(root, path) for path in allowed if path != SCHEMA_PATH}
    contract = next((doc for doc in documents.values() if "cases" in doc), None)
    manifest = next((doc for doc in documents.values() if "seeds" in doc), None)
    vocabulary_items = [
        (path, doc) for path, doc in documents.items() if "axes" in doc
    ]
    if contract is None or manifest is None or len(vocabulary_items) != 1:
        raise NormalizationCheckError("突合器の入力資産を一意に識別できない")
    seed_path, vocabulary = vocabulary_items[0]
    cases = contract.get("cases")
    if not isinstance(cases, list):
        raise NormalizationCheckError("casesが配列でない")
    return cases, NormalizationRules(schema, vocabulary, manifest, seed_path)


def check_cases(cases: list[dict[str, Any]], rules: NormalizationRules) -> int:
    """全ケースで適用結果とnormalizedのJSON値を突合する。"""
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not {
            "raw", "normalizationRuleId", "normalized"
        } <= set(case):
            raise NormalizationCheckError(f"cases[{index}]に正規化の3点がない")
        rule_id = case["normalizationRuleId"]
        if not isinstance(rule_id, str):
            raise NormalizationCheckError(f"cases[{index}]の規則識別子が不正")
        try:
            actual = rules.normalize(case["raw"], rule_id)
        except NormalizationError as error:
            raise NormalizationCheckError(
                f"cases[{index}] {case.get('caseId')}: {error}"
            ) from error
        if json.dumps(actual, sort_keys=True, ensure_ascii=False) != json.dumps(
            case["normalized"], sort_keys=True, ensure_ascii=False
        ):
            differing = [
                key for key in set(actual) | set(case["normalized"])
                if actual.get(key) != case["normalized"].get(key)
            ] if isinstance(actual, dict) and isinstance(case["normalized"], dict) else []
            raise NormalizationCheckError(
                f"cases[{index}] {case.get('caseId')}: "
                f"{rule_id}の適用結果とnormalizedが不一致 ({sorted(differing)})"
            )
    return len(cases)


def check_repository(root: Path = ROOT) -> int:
    """リポジトリの全ケースを突合する。"""
    cases, rules = load_inputs(root)
    return check_cases(cases, rules)


def main(argv: list[str] | None = None) -> int:
    """CLIから全ケースを検査する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        count = check_repository(args.root.resolve())
    except (OSError, KeyError, ValueError, TypeError) as error:
        print(f"state-transition-normalization: 違反: {error}", file=sys.stderr)
        return 1
    print(f"state-transition-normalization: {count} cases一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
