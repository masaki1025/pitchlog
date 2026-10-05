"""状況判定と終了判定のrawへ宣言規則を適用しnormalizedと突合する。"""

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
STATE_CONTRACT_PATH = PurePosixPath(
    "contracts/state-transition/state_transition_contract_v1.json"
)
EXPANDER_POLICY_PATH = PurePosixPath(
    "contracts/state-transition/expander_dependency_policy_v1.json"
)
GAME_END_CONTRACT_PATH = PurePosixPath(
    "contracts/state-transition/game_end_contract_v1.json"
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
    """展開器と整合する許可パスから状況判定ケースと規則を読む。"""
    schema = _read(root, SCHEMA_PATH)
    declaration = schema["x-pitchlog-stage1-normalization"]
    paths = declaration.get("claimBoundary", {}).get("allowedReadPaths")
    if not isinstance(paths, list) or len(paths) != 5 or len(set(paths)) != 5:
        raise NormalizationCheckError("突合器のallowedReadPathsが不正")
    allowed = {PurePosixPath(path) for path in paths}
    if not {SCHEMA_PATH, STATE_CONTRACT_PATH, GAME_END_CONTRACT_PATH} <= allowed or any(
        path.is_absolute() or ".." in path.parts for path in allowed
    ):
        raise NormalizationCheckError("突合器のallowedReadPathsに不正なパスがある")
    policy = _read(root, EXPANDER_POLICY_PATH)
    expander = next(
        (item for item in policy.get("expanders", [])
         if item.get("expanderId") == "state-transition-cases"), None
    )
    if expander is None or not (allowed - {GAME_END_CONTRACT_PATH}) <= {
        PurePosixPath(path) for path in expander.get("allowedReadPaths", [])
    }:
        raise NormalizationCheckError("突合器と展開器のallowedReadPathsが不一致")
    game_end_expander = next(
        (item for item in policy.get("expanders", [])
         if item.get("expanderId") == "game-end-cases"), None
    )
    if game_end_expander is None or GAME_END_CONTRACT_PATH not in {
        PurePosixPath(path)
        for path in game_end_expander.get("allowedReadPaths", [])
    }:
        raise NormalizationCheckError("終了判定契約と展開器のallowedReadPathsが不一致")
    documents = {
        path: _read(root, path)
        for path in allowed - {SCHEMA_PATH, GAME_END_CONTRACT_PATH}
    }
    contract = documents[STATE_CONTRACT_PATH]
    manifest = next((doc for doc in documents.values() if "seeds" in doc), None)
    vocabulary_items = [
        (path, doc) for path, doc in documents.items() if "axes" in doc
    ]
    if manifest is None or len(vocabulary_items) != 1:
        raise NormalizationCheckError("突合器の入力資産を一意に識別できない")
    seed_path, vocabulary = vocabulary_items[0]
    cases = contract.get("cases")
    if not isinstance(cases, list):
        raise NormalizationCheckError("casesが配列でない")
    return cases, NormalizationRules(schema, vocabulary, manifest, seed_path)


def load_game_end_inputs(root: Path) -> tuple[list[dict[str, Any]], NormalizationRules]:
    """同じ規則宣言と終了判定契約のケースを読む。"""
    _, rules = load_inputs(root)
    cases = _read(root, GAME_END_CONTRACT_PATH).get("cases")
    if not isinstance(cases, list):
        raise NormalizationCheckError("終了判定casesが配列でない")
    return cases, rules


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
    """リポジトリの状況判定と終了判定の全ケースを突合する。"""
    cases, rules = load_inputs(root)
    count = check_cases(cases, rules)
    game_end_cases = _read(root, GAME_END_CONTRACT_PATH).get("cases")
    if not isinstance(game_end_cases, list):
        raise NormalizationCheckError("終了判定casesが配列でない")
    return count + check_cases(game_end_cases, rules)


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
